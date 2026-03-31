# LarpManager - https://larpmanager.com
# Copyright (C) 2025 Scanagatta Mauro
#
# This file is part of LarpManager and is dual-licensed:
#
# 1. Under the terms of the GNU Affero General Public License (AGPL) version 3,
#    as published by the Free Software Foundation. You may use, modify, and
#    distribute this file under those terms.
#
# 2. Under a commercial license, allowing use in closed-source or proprietary
#    environments without the obligations of the AGPL.
#
# If you have obtained this file under the AGPL, and you make it available over
# a network, you must also make the complete source code available under the same license.
#
# For more information or to purchase a commercial license, contact:
# commercial@larpmanager.com
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import models, transaction
from django.http import HttpRequest, JsonResponse
from django.utils.translation import gettext_lazy as _

from larpmanager.utils.edit.backend import save_log

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from larpmanager.models.base import BaseModel

import datetime

from larpmanager.cache.config import get_association_config, get_event_config
from larpmanager.models.access import get_event_staffers
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import ProgressStep
from larpmanager.models.experience import AbilityExp, AbilityTypeExp, DeliveryExp
from larpmanager.models.form import WritingAnswer, WritingChoice
from larpmanager.models.member import LogOperationType, Member
from larpmanager.models.miscellanea import (
    WarehouseContainer,
    WarehouseItem,
    WarehouseTag,
)
from larpmanager.models.writing import Character, CharacterConfig, CharacterStatus, Faction, Plot, Prologue
from larpmanager.utils.auth.admin import is_lm_admin
from larpmanager.utils.core.exceptions import ReturnNowError

RECOVERABLE_MODELS: dict[str, type] = {
    "character": Character,
    "plot": Plot,
    "faction": Faction,
    "quest": Quest,
    "trait": Trait,
    "ability": AbilityExp,
    "warehouse_item": WarehouseItem,
}


def _check_delete_role(request: HttpRequest, context: dict) -> bool:
    """Return True if the user has role required to bulk delete (admin or organizer)."""
    if is_lm_admin(request):
        return True
    if 1 in context.get("association_role", {}):
        return True
    return any(1 in roles for roles in context.get("event_role", {}).values())


def _require_role_delete(request: HttpRequest, context: dict) -> None:
    """Raise PermissionDenied if the user has not role required to bulk delete."""
    if not _check_delete_role(request, context):
        raise PermissionDenied


def _check_bulk_delete_enabled(context: dict) -> None:
    """Raise PermissionDenied if bulk delete is not enabled for this association."""
    if not get_association_config(context["association_id"], "allow_bulk_delete", default_value=False, context=context):
        raise PermissionDenied


def _bulk_op(idx: int, objs: Any) -> dict:
    """Build a bulk operation entry using the correct label."""
    return {"idx": idx, "label": Operations(idx).label, "objs": objs}


def _add_bulk_delete_option(request: HttpRequest, context: dict) -> None:
    """Append bulk delete option to context bulk list if enabled for the association and user has the required role."""
    if not get_association_config(context["association_id"], "allow_bulk_delete", default_value=False, context=context):
        return
    if _check_delete_role(request, context):
        objs = [{"uuid": 1, "name": _("Are you sure? The items might be not recoverable")}]
        context["bulk"].append(_bulk_op(Operations.DEL_BULK, objs))


def _restore_writing_answers(element_id: int, deleted_at: Any) -> None:
    """Restore soft-deleted WritingAnswers and WritingChoices for a writing element.

    Only restores entries deleted within 1 second of the parent object's deletion
    (i.e. cascade-deleted together with it) and whose question/option is still active.
    """
    window_start = deleted_at - datetime.timedelta(seconds=1)
    window_end = deleted_at + datetime.timedelta(seconds=1)
    for answer in WritingAnswer.all_objects.filter(
        element_id=element_id,
        deleted__range=(window_start, window_end),
        question__deleted__isnull=True,
    ):
        answer.undelete()
    for choice in WritingChoice.all_objects.filter(
        element_id=element_id,
        deleted__range=(window_start, window_end),
        question__deleted__isnull=True,
        option__deleted__isnull=True,
    ):
        choice.undelete()


def restore_object(model_class: type, uuid: str) -> None:
    """Undelete a soft-deleted object and reassign its sequential number if applicable.

    For event-scoped writing elements, also restores any soft-deleted WritingAnswers
    and WritingChoices whose question is still active.
    """
    with transaction.atomic():
        obj = model_class.all_objects.select_for_update().get(uuid=uuid, deleted__isnull=False)
        if hasattr(obj, "number"):
            obj.number = None
        deleted_at = obj.deleted
        if isinstance(obj, Character):
            # Restore cascade-deleted CharacterConfigs before undeleting the Character.
            CharacterConfig.all_objects.filter(character=obj, deleted__isnull=False, deleted_by_cascade=True).update(
                deleted=None, deleted_by_cascade=False
            )
        obj.undelete()
        if hasattr(obj, "event"):
            _restore_writing_answers(obj.pk, deleted_at)


def _get_bulk_params(request: HttpRequest) -> tuple[list[str], int, int]:
    """Extract and validate bulk operation parameters from request.

    Extracts operation ID, target ID, and a list of entity UUIDs from the request,
    validates the data types, and logs the bulk operation attempt.

    Args:
        request: HTTP request object containing POST data with operation parameters

    Returns:
        :tuple[list[str], int, int]: A tuple containing:
            - entity_uuids: List of validated UUID strings for bulk operation
            - operation_code: Integer operation code (defaults to 0 if invalid)
            - target_code: Integer target code (defaults to 0 if invalid)

    Raises:
        ReturnNowError: If no valid UUIDs are provided in the request

    """
    # Extract and validate operation parameter, default to 0 for invalid values
    try:
        operation_code = int(request.POST.get("operation", "0"))
    except (ValueError, TypeError):
        operation_code = 0

    # Extract and validate target parameter
    target_code = request.POST.get("target", "0")

    # Process list of UUIDs, filtering out invalid entries
    entity_uuids = [
        raw_uuid for raw_uuid in request.POST.getlist("uuids[]", []) if raw_uuid and isinstance(raw_uuid, str)
    ]

    # Validate that at least one valid UUID was provided
    if not entity_uuids:
        raise ReturnNowError(JsonResponse({"error": "no uuids"}, status=400))

    # Return parameters
    return entity_uuids, operation_code, target_code


class Operations(models.IntegerChoices):
    """Bulk operation types with their human-readable labels."""

    MOVE_ITEM_BOX = 1, _("Move to container")
    ADD_ITEM_TAG = 2, _("Add tag")
    DEL_ITEM_TAG = 3, _("Remove tag")
    ADD_CHAR_FACT = 4, _("Add to faction")
    DEL_CHAR_FACT = 5, _("Remove from faction")
    ADD_CHAR_PLOT = 6, _("Add to plot")
    DEL_CHAR_PLOT = 7, _("Remove from plot")
    SET_QUEST_TYPE = 8, _("Set quest type")
    SET_TRAIT_QUEST = 9, _("Set quest")
    SET_ABILITY_TYPE = 10, _("Set ability type")
    ADD_CHAR_DELIVERY = 11, _("Add to xp delivery")
    DEL_CHAR_DELIVERY = 12, _("Remove from xp delivery")
    ADD_CHAR_PROLOGUE = 13, _("Add prologue")
    DEL_CHAR_PROLOGUE = 14, _("Remove prologue")
    SET_CHAR_PROGRESS = 15, _("Set progress step")
    SET_CHAR_ASSIGNED = 16, _("Set assigned staff member")
    SET_CHAR_STATUS = 17, _("Set character status")
    DEL_BULK = 18, _("Delete")


def _create_bulk_logs(
    context: dict,
    operation_name: int,
    target_name: str | None,
    object_uuids: list[str],
    model_class: BaseModel,
) -> None:
    """Create individual log entries for each element in a bulk operation."""
    objects = model_class.objects.filter(uuid__in=object_uuids)
    label = Operations(operation_name).label
    log_info = f"{label}: {target_name}" if target_name else label
    for obj in objects:
        save_log(
            context=context,
            cls=model_class,
            element=obj,
            operation_type=LogOperationType.BULK,
            info=log_info,
        )


def exec_bulk(request: HttpRequest, context: dict, operation_mapping: dict, model_class: type) -> JsonResponse:
    """Execute bulk operations on a collection of objects.

    Args:
        request: HTTP request object containing bulk operation parameters
        context: Context dictionary with operation-specific data
        operation_mapping: Dictionary mapping operation names to their handler functions
        model_class: Django model class of the objects being modified (for logging)

    Returns:
        JsonResponse: Success response with "ok" status or error response with
        appropriate error message and HTTP status code

    Raises:
        ObjectDoesNotExist: When target objects for the operation are not found

    """
    # Extract bulk operation parameters from request
    object_uuids, operation_name, operation_target = _get_bulk_params(request)

    # Handle delete separately: log before deletion so objects are still queryable
    if operation_name == Operations.DEL_BULK:
        _require_role_delete(request, context)
        _check_bulk_delete_enabled(context)
        try:
            _create_bulk_logs(context, operation_name, None, object_uuids, model_class)
            model_class.objects.filter(uuid__in=object_uuids).delete()
        except ObjectDoesNotExist:
            return JsonResponse({"error": "not found"}, status=400)
        return JsonResponse({"res": "ok"})

    # Validate that the requested operation is supported
    if operation_name not in operation_mapping:
        return JsonResponse({"error": "unknow operation"}, status=400)

    try:
        # Execute the bulk operation using the mapped handler function
        target_name = operation_mapping[operation_name](context, operation_target, object_uuids)

        # Create log entries for each affected element
        _create_bulk_logs(context, operation_name, target_name, object_uuids, model_class)
    except ObjectDoesNotExist:
        # Handle case where target objects don't exist
        return JsonResponse({"error": "not found"}, status=400)

    # Return success response
    return JsonResponse({"res": "ok"})


def _get_inv_items(warehouse_item_uuids: list[str], context: dict) -> QuerySet[WarehouseItem]:
    """Get warehouse items filtered by association."""
    return WarehouseItem.objects.filter(
        association_id=context["association_id"],
        uuid__in=warehouse_item_uuids,
    )


def exec_add_item_tag(
    context: Any,
    target: str,
    uuids: list[str],
) -> str:
    """Add items to a warehouse tag."""
    tag = WarehouseTag.objects.get(association_id=context["association_id"], uuid=target)
    tag.items.add(*_get_inv_items(uuids, context))
    return tag.name


def exec_del_item_tag(context: dict, target: str, uuids: list[str]) -> str:
    """Remove items from a warehouse tag."""
    tag = WarehouseTag.objects.get(association_id=context["association_id"], uuid=target)
    tag.items.remove(*_get_inv_items(uuids, context))
    return tag.name


def exec_move_item_box(
    context: Any,
    target: str,
    uuids: list[str],
) -> str:
    """Move warehouse items to a target container."""
    # Retrieve the target container for the association
    container = WarehouseContainer.objects.get(association_id=context["association_id"], uuid=target)

    # Update all specified items to the new container
    WarehouseItem.objects.filter(association_id=context["association_id"], uuid__in=uuids).update(container=container)
    return container.name


def handle_bulk_items(request: HttpRequest, context: dict) -> None:
    """Handle bulk operations on warehouse items.

    This function processes bulk operations for warehouse items including adding/removing
    tags and moving items between containers. For POST requests, it executes the
    specified bulk operation. For GET requests, it populates the context with available
    bulk operation choices.

    Args:
        request: HTTP request object containing operation data and association info
        context: Context dictionary to update with bulk operation choices

    Raises:
        ReturnNowError: If POST request processed successfully with operation results

    """
    if request.POST:
        # Define mapping of operation types to their execution functions
        operation_type_to_handler = {
            Operations.ADD_ITEM_TAG: exec_add_item_tag,
            Operations.DEL_ITEM_TAG: exec_del_item_tag,
            Operations.MOVE_ITEM_BOX: exec_move_item_box,
        }
        # Execute the bulk operation and raise ReturnNowError with results
        raise ReturnNowError(exec_bulk(request, context, operation_type_to_handler, WarehouseItem))

    # Fetch available containers for the current association
    available_containers = (
        WarehouseContainer.objects.filter(association_id=context["association_id"])
        .values("uuid", "name")
        .order_by("name")
    )
    # Fetch available tags for the current association
    available_tags = (
        WarehouseTag.objects.filter(association_id=context["association_id"]).values("uuid", "name").order_by("name")
    )

    # Populate context with bulk operation choices and their associated objects
    context["bulk"] = [
        _bulk_op(Operations.MOVE_ITEM_BOX, available_containers),
        _bulk_op(Operations.ADD_ITEM_TAG, available_tags),
        _bulk_op(Operations.DEL_ITEM_TAG, available_tags),
    ]
    _add_bulk_delete_option(request, context)


def _get_chars(context: dict, character_uuids: list[str]) -> QuerySet[Character]:
    """Return characters filtered by event and provided UUIDs."""
    return context["event"].get_elements(Character).filter(uuid__in=character_uuids)


def exec_add_char_fact(context: dict, target: str, uuids: list[str]) -> str:
    """Add characters to a faction."""
    fact = context["event"].get_elements(Faction).get(uuid=target)
    fact.characters.add(*_get_chars(context, uuids))
    return fact.name


def exec_del_char_fact(context: dict, target: str, uuids: list[str]) -> str:
    """Remove characters from a faction."""
    fact = context["event"].get_elements(Faction).get(uuid=target)
    fact.characters.remove(*_get_chars(context, uuids))
    return fact.name


def exec_add_char_plot(context: dict, target: str, uuids: list[str]) -> str:
    """Add characters to a plot element."""
    plot = context["event"].get_elements(Plot).get(uuid=target)
    plot.characters.add(*_get_chars(context, uuids))
    return plot.name


def exec_del_char_plot(context: dict, target: str, uuids: list[str]) -> str:
    """Remove characters from a plot element."""
    plot = context["event"].get_elements(Plot).get(uuid=target)
    plot.characters.remove(*_get_chars(context, uuids))
    return plot.name


def exec_add_char_delivery(
    context: dict,
    target: str,
    uuids: list[str],
) -> str:
    """Add characters to a delivery."""
    delivery = context["event"].get_elements(DeliveryExp).get(uuid=target)
    delivery.characters.add(*_get_chars(context, uuids))
    return delivery.name


def exec_del_char_delivery(context: dict, target: str, uuids: list[str]) -> str:
    """Remove characters from delivery."""
    delivery = context["event"].get_elements(DeliveryExp).get(uuid=target)
    delivery.characters.remove(*_get_chars(context, uuids))
    return delivery.name


def exec_add_char_prologue(context: dict, target: str, uuids: list[str]) -> str:
    """Add characters to a prologue."""
    prologue = context["event"].get_elements(Prologue).get(uuid=target)
    prologue.characters.add(*_get_chars(context, uuids))
    return prologue.name


def exec_del_char_prologue(
    context: dict,
    target: str,
    uuids: list[str],
) -> str:
    """Remove characters from a prologue."""
    prologue = context["event"].get_elements(Prologue).get(uuid=target)
    prologue.characters.remove(*_get_chars(context, uuids))
    return prologue.name


def exec_set_char_progress(
    context: dict,
    target: str,
    uuids: list[str],
) -> str:
    """Update progress step for specified characters."""
    progress_step = context["event"].get_elements(ProgressStep).get(uuid=target)
    context["event"].get_elements(Character).filter(uuid__in=uuids).update(progress=progress_step)
    return progress_step.name


def exec_set_char_assigned(context: dict, target: str, uuids: list[str]) -> str:
    """Assign characters to a member."""
    member = Member.objects.get(uuid=target)
    context["event"].get_elements(Character).filter(uuid__in=uuids).update(assigned=member)
    return member.name


def exec_set_char_status(context: dict, target: str, uuids: list[str]) -> str:
    """Update character status for specified characters in the event."""
    context["event"].get_elements(Character).filter(uuid__in=uuids).update(status=target)
    return dict(CharacterStatus.choices).get(target, target)


def handle_bulk_characters(request: HttpRequest, context: dict) -> None:
    """Process bulk operations on character objects.

    Handles mass character modifications, faction assignments, and other
    batch character management tasks for efficient character administration.

    Args:
        request: Django HTTP request object containing POST data with operation details.
        context: Context dictionary containing event and selection data. Modified in-place
            to include operation results and status messages.

    Returns:
        None: Function modifies context in-place.

    Raises:
        ReturnNowError: When POST request is processed, containing execution results.

    """
    # Handle POST request by executing the requested bulk operation
    if request.POST:
        # Map operation codes to their corresponding execution functions
        mapping = {
            Operations.ADD_CHAR_FACT: exec_add_char_fact,
            Operations.DEL_CHAR_FACT: exec_del_char_fact,
            Operations.ADD_CHAR_PLOT: exec_add_char_plot,
            Operations.DEL_CHAR_PLOT: exec_del_char_plot,
            Operations.ADD_CHAR_DELIVERY: exec_add_char_delivery,
            Operations.DEL_CHAR_DELIVERY: exec_del_char_delivery,
            Operations.ADD_CHAR_PROLOGUE: exec_add_char_prologue,
            Operations.DEL_CHAR_PROLOGUE: exec_del_char_prologue,
            Operations.SET_CHAR_PROGRESS: exec_set_char_progress,
            Operations.SET_CHAR_ASSIGNED: exec_set_char_assigned,
            Operations.SET_CHAR_STATUS: exec_set_char_status,
        }
        # Execute the bulk operation and raise exception to return result
        raise ReturnNowError(exec_bulk(request, context, mapping, Character))

    # Initialize bulk operations list for GET requests
    context["bulk"] = []

    # Add faction-related operations if faction feature is enabled
    if "faction" in context["features"]:
        factions = context["event"].get_elements(Faction).values("uuid", "name").order_by("name")
        context["bulk"].extend(
            [
                _bulk_op(Operations.ADD_CHAR_FACT, factions),
                _bulk_op(Operations.DEL_CHAR_FACT, factions),
            ],
        )

    # Add plot-related operations if plot feature is enabled
    if "plot" in context["features"]:
        plots = context["event"].get_elements(Plot).values("uuid", "name").order_by("name")
        context["bulk"].extend(
            [
                _bulk_op(Operations.ADD_CHAR_PLOT, plots),
                _bulk_op(Operations.DEL_CHAR_PLOT, plots),
            ],
        )

    # Add prologue-related operations if prologue feature is enabled
    if "prologue" in context["features"]:
        prologues = context["event"].get_elements(Prologue).values("uuid", "name").order_by("name")
        context["bulk"].extend(
            [
                _bulk_op(Operations.ADD_CHAR_PROLOGUE, prologues),
                _bulk_op(Operations.DEL_CHAR_PROLOGUE, prologues),
            ],
        )

    # Add XP delivery operations if experience feature is enabled
    if "experience" in context["features"]:
        delivery = context["event"].get_elements(DeliveryExp).values("uuid", "name")
        context["bulk"].extend(
            [
                _bulk_op(Operations.ADD_CHAR_DELIVERY, delivery),
                _bulk_op(Operations.DEL_CHAR_DELIVERY, delivery),
            ],
        )

    # Add progress step operation if progress feature is enabled
    if "progress" in context["features"]:
        progress_steps = context["event"].get_elements(ProgressStep).values("uuid", "name").order_by("order")
        context["bulk"].append(
            _bulk_op(Operations.SET_CHAR_PROGRESS, progress_steps),
        )

    # Add staff assignment operation if assigned feature is enabled
    if "assigned" in context["features"]:
        # Get event staff members using the same function used in writing utils
        event_staff = get_event_staffers(context["event"])
        staff_members = [{"uuid": m.uuid, "name": m.show_nick()} for m in event_staff]
        context["bulk"].append(
            _bulk_op(Operations.SET_CHAR_ASSIGNED, staff_members),
        )

    # Add status assignment operation if enabled
    if get_event_config(context["event"].id, "user_character_approval", default_value=False, context=context):
        status_choices = [{"uuid": choice[0], "name": choice[1]} for choice in CharacterStatus.choices]
        context["bulk"].append(
            _bulk_op(Operations.SET_CHAR_STATUS, status_choices),
        )
    _add_bulk_delete_option(request, context)


def exec_set_quest_type(
    context: dict,
    target: str,
    uuids: list[str],
) -> str:
    """Set quest type for multiple quests."""
    quest_type = context["event"].get_elements(QuestType).get(uuid=target)
    context["event"].get_elements(Quest).filter(uuid__in=uuids).update(typ=quest_type)
    return quest_type.name


def handle_bulk_quest(request: HttpRequest, context: dict) -> None:
    """Handle bulk operations for quest management.

    Args:
        request: HTTP request object
        context: Context dictionary containing event and other data

    """
    # Handle POST request - execute bulk operations
    if request.POST:
        raise ReturnNowError(exec_bulk(request, context, {Operations.SET_QUEST_TYPE: exec_set_quest_type}, Quest))

    # Get available quest types for the event, ordered by name
    quest_types = context["event"].get_elements(QuestType).values("uuid", "name").order_by("name")

    # Set up bulk operation options in context
    context["bulk"] = [
        _bulk_op(Operations.SET_QUEST_TYPE, quest_types),
    ]
    _add_bulk_delete_option(request, context)


def exec_set_quest(
    context: dict,
    target: str,
    uuids: list[str],
) -> str:
    """Assign a quest to multiple traits."""
    # Retrieve the target quest from the event
    quest = context["event"].get_elements(Quest).get(uuid=target)
    # Update all specified traits to use this quest
    context["event"].get_elements(Trait).filter(uuid__in=uuids).update(quest=quest)
    return quest.name


def handle_bulk_trait(request: HttpRequest, context: dict) -> None:
    """Handle bulk trait operations for quest assignment."""
    if request.POST:
        # Execute bulk operation for setting quest traits
        raise ReturnNowError(exec_bulk(request, context, {Operations.SET_TRAIT_QUEST: exec_set_quest}, Trait))

    # Get available quests for the current event
    quests = context["event"].get_elements(Quest).values("uuid", "name").order_by("name")

    # Configure bulk operation options
    context["bulk"] = [
        _bulk_op(Operations.SET_TRAIT_QUEST, quests),
    ]
    _add_bulk_delete_option(request, context)


def exec_set_ability_type(
    context: dict,
    target: str | int,
    uuids: list[str],
) -> str:
    """Update ability type for selected abilities in bulk."""
    # Get target ability type from event elements
    typ = context["event"].get_elements(AbilityTypeExp).get(uuid=target)
    # Update all selected abilities with new type
    context["event"].get_elements(AbilityExp).filter(uuid__in=uuids).update(typ=typ)
    return typ.name


def handle_bulk_ability(request: HttpRequest, context: dict) -> None:
    """Handle bulk operations for abilities.

    Args:
        request: HTTP request object
        context: Context dictionary containing event data

    """
    if request.POST:
        # Execute bulk operation and return early if POST request
        raise ReturnNowError(
            exec_bulk(request, context, {Operations.SET_ABILITY_TYPE: exec_set_ability_type}, AbilityExp)
        )

    # Get ability types for the event, ordered by name
    ability_types = context["event"].get_elements(AbilityTypeExp).values("uuid", "name").order_by("name")

    # Setup bulk operations context
    context["bulk"] = [
        _bulk_op(Operations.SET_ABILITY_TYPE, ability_types),
    ]
    _add_bulk_delete_option(request, context)
