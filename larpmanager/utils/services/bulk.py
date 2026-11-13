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

import datetime as dt

from larpmanager.cache.bulk import get_bulk_options_cache
from larpmanager.cache.character import clear_event_cache_all_runs
from larpmanager.cache.config import get_association_config, get_event_config
from larpmanager.cache.question import get_cached_registration_questions, get_cached_writing_questions
from larpmanager.cache.registration_counts import clear_registration_counts_cache
from larpmanager.cache.registration_lookup import get_registration_tickets
from larpmanager.cache.run import get_event_and_children_runs
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import ProgressStep
from larpmanager.models.experience import AbilityExp, AbilityTypeExp, DeliveryExp
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    RegistrationChoice,
    WritingAnswer,
    WritingChoice,
    WritingQuestionType,
)
from larpmanager.models.member import LogOperationType, Member
from larpmanager.models.miscellanea import (
    WarehouseArea,
    WarehouseContainer,
    WarehouseItem,
    WarehouseItemAssignment,
    WarehouseTag,
)
from larpmanager.models.registration import Registration
from larpmanager.models.writing import (
    Character,
    CharacterConfig,
    CharacterStatus,
    Faction,
    Plot,
    Prologue,
    get_event_elements,
)
from larpmanager.utils.auth.admin import is_lm_admin
from larpmanager.utils.core.exceptions import ReturnNowError
from larpmanager.utils.services.miscellanea import (
    warehouse_add_assignment,
    warehouse_assigned_quantities,
    warehouse_available_quantity,
)

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
    if not get_association_config(context["association_id"], "allow_bulk_delete", context=context):
        raise PermissionDenied


def _bulk_op(idx: int, objs: Any) -> dict:
    """Build a bulk operation entry using the correct label."""
    return {"idx": idx, "label": Operations(idx).label, "objs": objs}


def _add_bulk_delete_option(request: HttpRequest, context: dict) -> None:
    """Append bulk delete option to context bulk list if enabled for the association and user has the required role."""
    if not get_association_config(context["association_id"], "allow_bulk_delete", context=context):
        return
    if _check_delete_role(request, context):
        objs = [{"uuid": 1, "name": _("Are you sure? The items might not be recoverable.")}]
        context["bulk"].append(_bulk_op(Operations.DEL_BULK, objs))


def _restore_writing_answers(element_id: int, deleted_at: Any) -> None:
    """Restore soft-deleted WritingAnswers and WritingChoices for a writing element.

    Only restores entries deleted within 1 second of the parent object's deletion
    (i.e. cascade-deleted together with it) and whose question/option is still active.
    """
    window_start = deleted_at - dt.timedelta(seconds=1)
    window_end = deleted_at + dt.timedelta(seconds=1)
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
    # Per-question operations are encoded as "<operation>_<question uuid>"
    try:
        operation_code = int(request.POST.get("operation", "0").split("_")[0])
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
    ADD_CHAR_DELIVERY = 11, _("Add to xp award")
    DEL_CHAR_DELIVERY = 12, _("Remove from xp award")
    ADD_CHAR_PROLOGUE = 13, _("Add prologue")
    DEL_CHAR_PROLOGUE = 14, _("Remove prologue")
    SET_CHAR_PROGRESS = 15, _("Set progress step")
    SET_CHAR_ASSIGNED = 16, _("Set assigned staff member")
    SET_CHAR_STATUS = 17, _("Set character status")
    DEL_BULK = 18, _("Delete")
    ADD_PLOT_CHAR = 19, _("Add character")
    DEL_PLOT_CHAR = 20, _("Remove character")
    SET_PLOT_PROGRESS = 21, _("Set progress step")
    SET_PLOT_ASSIGNED = 22, _("Set assigned staff member")
    ADD_FACT_CHAR = 23, _("Add character")
    DEL_FACT_CHAR = 24, _("Remove character")
    SET_FACT_PROGRESS = 25, _("Set progress step")
    SET_FACT_ASSIGNED = 26, _("Set assigned staff member")
    SET_ITEM_AREA_REMAINING = 27, _("Add to area")
    SET_CHAR_HIDE = 28, _("Set hidden")
    SET_CHAR_LOCKED = 29, _("Set locked")
    MOVE_ASSIGNMENT_AREA = 30, _("Move to area")
    DEL_ASSIGNMENT = 31, _("Remove from area")
    SET_ASSIGNMENT_LOADED = 32, _("Set loaded")
    SET_ASSIGNMENT_DEPLOYED = 33, _("Set deployed")
    DEL_ITEM_AREA = 34, _("Remove from area")
    SET_CHAR_QUESTION = 35, _("Set value")
    SET_REG_QUESTION = 36, _("Set value")
    SET_REG_TICKET = 37, _("Set ticket")
    ADD_CHAR_QUESTION = 38, _("Add value")
    DEL_CHAR_QUESTION = 39, _("Remove value")
    ADD_REG_QUESTION = 40, _("Add value")
    DEL_REG_QUESTION = 41, _("Remove value")


def _scoped_bulk_queryset(context: dict, model_class: type, object_uuids: list[str]) -> QuerySet:
    """Return the given UUIDs scoped to the current tenant.

    WarehouseItem is association-scoped; all other bulk models are
    event-scoped via Event.get_event_elements. Scoping here prevents cross-tenant
    reads/deletes from raw POST UUIDs.
    """
    if model_class is WarehouseItem:
        base = WarehouseItem.objects.filter(association_id=context["association_id"])
    elif model_class is Registration:
        base = Registration.objects.filter(run_id=context["run"].id)
    else:
        base = get_event_elements(context["event"].id, model_class, context=context)
    return base.filter(uuid__in=object_uuids)


def _create_bulk_logs(
    context: dict,
    operation_name: int,
    target_name: str | None,
    object_uuids: list[str],
    model_class: BaseModel,
) -> None:
    """Create individual log entries for each element in a bulk operation."""
    objects = _scoped_bulk_queryset(context, model_class, object_uuids)
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


def exec_bulk(
    request: HttpRequest,
    context: dict,
    operation_mapping: dict,
    model_class: type,
    *,
    allow_delete: bool = False,
) -> JsonResponse:
    """Execute bulk operations on a collection of objects.

    Args:
        request: HTTP request object containing bulk operation parameters
        context: Context dictionary with operation-specific data
        operation_mapping: Dictionary mapping operation names to their handler functions
        model_class: Django model class of the objects being modified (for logging)
        allow_delete: Whether the caller offers bulk delete; must mirror the
            listing built for GET, so an operation never exposed in the page
            cannot be reached with a raw POST

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
        if not allow_delete:
            return JsonResponse({"error": "unknow operation"}, status=400)
        _require_role_delete(request, context)
        _check_bulk_delete_enabled(context)
        try:
            _create_bulk_logs(context, operation_name, None, object_uuids, model_class)
            _scoped_bulk_queryset(context, model_class, object_uuids).delete()
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
    except (ObjectDoesNotExist, ValueError):
        # Target object missing, or an invalid target value (e.g. bad status)
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
        raise ReturnNowError(exec_bulk(request, context, operation_type_to_handler, WarehouseItem, allow_delete=True))

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


def _get_event_area(context: dict, area_uuid: str) -> WarehouseArea:
    """Return an area of the current event by UUID."""
    return get_event_elements(context["event"].id, WarehouseArea, context=context).get(uuid=area_uuid)


def exec_set_item_area_remaining(context: dict, target: str, uuids: list[str]) -> str:
    """Add each selected item to a target event area.

    Finite-stock items get their whole remaining stock (skipped if nothing is left);
    unlimited items get an assignment without quantity, if not already present.
    """
    area = _get_event_area(context, target)
    with transaction.atomic():
        items = list(
            WarehouseItem.objects.select_for_update().filter(
                association_id=context["association_id"],
                uuid__in=uuids,
            )
        )
        assigned_by_item = warehouse_assigned_quantities([item for item in items if item.quantity is not None])
        for item in items:
            if item.quantity is None:
                WarehouseItemAssignment.objects.get_or_create(
                    item=item, area=area, defaults={"event": context["event"]}
                )
                continue
            available = warehouse_available_quantity(item, assigned_by_item.get(item.id, 0))
            if available <= 0:
                continue
            warehouse_add_assignment(item, area, context["event"], available)

    return area.name


def exec_del_item_area(context: dict, target: str, uuids: list[str]) -> str:
    """Remove the selected items from a target event area."""
    area = _get_event_area(context, target)
    with transaction.atomic():
        for assignment in WarehouseItemAssignment.objects.select_for_update().filter(
            area=area,
            item__association_id=context["association_id"],
            item__uuid__in=uuids,
        ):
            assignment.delete()
    return area.name


def handle_bulk_orga_items(request: HttpRequest, context: dict) -> None:
    """Handle bulk operations on warehouse items scoped to a single event.

    Supports adding items to an area of the current event, and removing them from it.
    """
    if request.POST:
        mapping = {
            Operations.SET_ITEM_AREA_REMAINING: exec_set_item_area_remaining,
            Operations.DEL_ITEM_AREA: exec_del_item_area,
        }
        raise ReturnNowError(exec_bulk(request, context, mapping, WarehouseItem))

    areas = (
        get_event_elements(context["event"].id, WarehouseArea, context=context).values("uuid", "name").order_by("name")
    )
    context["bulk"] = [
        _bulk_op(Operations.SET_ITEM_AREA_REMAINING, areas),
        _bulk_op(Operations.DEL_ITEM_AREA, areas),
    ]


def _get_assignments(context: dict, uuids: list[str]) -> QuerySet[WarehouseItemAssignment]:
    """Return the event's warehouse assignments with the given UUIDs, locked for update."""
    return (
        get_event_elements(context["event"].id, WarehouseItemAssignment, context=context)
        .select_for_update()
        .filter(uuid__in=uuids)
    )


def _merge_assignment(source: WarehouseItemAssignment, target: WarehouseItemAssignment) -> None:
    """Merge a source assignment into a target one of the same item, then delete the source."""
    if source.quantity is not None or target.quantity is not None:
        target.quantity = (target.quantity or 0) + (source.quantity or 0)
    target.notes = "; ".join(note for note in (target.notes, source.notes) if note)[:1000]
    target.loaded = target.loaded and source.loaded
    target.deployed = target.deployed and source.deployed
    target.save()
    source.delete()


def exec_move_assignment_area(context: dict, target: str, uuids: list[str]) -> str:
    """Move the selected assignments to a target area, merging into existing ones of the same item."""
    area = _get_event_area(context, target)
    with transaction.atomic():
        for assignment in _get_assignments(context, uuids):
            if assignment.area_id == area.id:
                continue
            existing = (
                WarehouseItemAssignment.objects.select_for_update()
                .filter(item_id=assignment.item_id, area=area)
                .first()
            )
            if existing:
                _merge_assignment(assignment, existing)
            else:
                assignment.area = area
                assignment.save()
    return area.name


def exec_del_assignment(context: dict, target: str, uuids: list[str]) -> str:  # noqa: ARG001
    """Remove the selected assignments from their area."""
    with transaction.atomic():
        for assignment in _get_assignments(context, uuids):
            assignment.delete()
    return ""


def _exec_set_assignment_flag(context: dict, target: str, uuids: list[str], field: str) -> str:
    """Set a boolean flag on the selected assignments, target being '1' or '0'."""
    if target not in ("0", "1"):
        msg = f"invalid flag value {target}"
        raise ValueError(msg)
    value = target == "1"
    with transaction.atomic():
        for assignment in _get_assignments(context, uuids):
            setattr(assignment, field, value)
            assignment.save()
    return str(_("Yes") if value else _("No"))


def exec_set_assignment_loaded(context: dict, target: str, uuids: list[str]) -> str:
    """Set the loaded flag on the selected assignments."""
    return _exec_set_assignment_flag(context, target, uuids, "loaded")


def exec_set_assignment_deployed(context: dict, target: str, uuids: list[str]) -> str:
    """Set the deployed flag on the selected assignments."""
    return _exec_set_assignment_flag(context, target, uuids, "deployed")


def handle_bulk_orga_manifest(request: HttpRequest, context: dict) -> None:
    """Handle bulk operations on warehouse item assignments of a single event.

    Supports moving assignments to another area, removing them, and setting loaded/deployed flags.
    """
    if request.POST:
        mapping = {
            Operations.MOVE_ASSIGNMENT_AREA: exec_move_assignment_area,
            Operations.DEL_ASSIGNMENT: exec_del_assignment,
            Operations.SET_ASSIGNMENT_LOADED: exec_set_assignment_loaded,
            Operations.SET_ASSIGNMENT_DEPLOYED: exec_set_assignment_deployed,
        }
        raise ReturnNowError(exec_bulk(request, context, mapping, WarehouseItemAssignment))

    areas = (
        get_event_elements(context["event"].id, WarehouseArea, context=context).values("uuid", "name").order_by("name")
    )
    flags = [{"uuid": "1", "name": _("Yes")}, {"uuid": "0", "name": _("No")}]
    confirm = [{"uuid": "1", "name": _("Selected items will be removed from their area")}]
    context["bulk"] = [
        _bulk_op(Operations.MOVE_ASSIGNMENT_AREA, areas),
        _bulk_op(Operations.DEL_ASSIGNMENT, confirm),
        _bulk_op(Operations.SET_ASSIGNMENT_LOADED, flags),
        _bulk_op(Operations.SET_ASSIGNMENT_DEPLOYED, flags),
    ]


def _get_chars(context: dict, character_uuids: list[str]) -> QuerySet[Character]:
    """Return characters filtered by event and provided UUIDs."""
    return get_event_elements(context["event"].id, Character, context=context).filter(uuid__in=character_uuids)


def exec_add_char_fact(context: dict, target: str, uuids: list[str]) -> str:
    """Add characters to a faction."""
    fact = get_event_elements(context["event"].id, Faction, context=context).get(uuid=target)
    fact.characters.add(*_get_chars(context, uuids))
    return fact.name


def exec_del_char_fact(context: dict, target: str, uuids: list[str]) -> str:
    """Remove characters from a faction."""
    fact = get_event_elements(context["event"].id, Faction, context=context).get(uuid=target)
    fact.characters.remove(*_get_chars(context, uuids))
    return fact.name


def exec_add_char_plot(context: dict, target: str, uuids: list[str]) -> str:
    """Add characters to a plot element."""
    plot = get_event_elements(context["event"].id, Plot, context=context).get(uuid=target)
    plot.characters.add(*_get_chars(context, uuids))
    return plot.name


def exec_del_char_plot(context: dict, target: str, uuids: list[str]) -> str:
    """Remove characters from a plot element."""
    plot = get_event_elements(context["event"].id, Plot, context=context).get(uuid=target)
    plot.characters.remove(*_get_chars(context, uuids))
    return plot.name


def exec_add_plot_char(context: dict, target: str, uuids: list[str]) -> str:
    """Add a character to selected plots."""
    char = get_event_elements(context["event"].id, Character, context=context).get(uuid=target)
    for plot in get_event_elements(context["event"].id, Plot, context=context).filter(uuid__in=uuids):
        plot.characters.add(char)
    return char.name


def exec_del_plot_char(context: dict, target: str, uuids: list[str]) -> str:
    """Remove a character from selected plots."""
    char = get_event_elements(context["event"].id, Character, context=context).get(uuid=target)
    for plot in get_event_elements(context["event"].id, Plot, context=context).filter(uuid__in=uuids):
        plot.characters.remove(char)
    return char.name


def exec_set_plot_progress(context: dict, target: str, uuids: list[str]) -> str:
    """Set progress step for selected plots."""
    progress_step = get_event_elements(context["event"].id, ProgressStep, context=context).get(uuid=target)
    get_event_elements(context["event"].id, Plot, context=context).filter(uuid__in=uuids).update(progress=progress_step)
    return progress_step.name


def _get_assoc_member(context: dict, target: str) -> Member:
    """Fetch a member by UUID, scoped to the current association."""
    return Member.objects.filter(memberships__association_id=context["association_id"]).distinct().get(uuid=target)


def exec_set_plot_assigned(context: dict, target: str, uuids: list[str]) -> str:
    """Assign selected plots to a staff member."""
    member = _get_assoc_member(context, target)
    get_event_elements(context["event"].id, Plot, context=context).filter(uuid__in=uuids).update(assigned=member)
    return member.name


def exec_add_char_delivery(
    context: dict,
    target: str,
    uuids: list[str],
) -> str:
    """Add characters to a delivery."""
    delivery = get_event_elements(context["event"].id, DeliveryExp, context=context).get(uuid=target)
    delivery.characters.add(*_get_chars(context, uuids))
    return delivery.name


def exec_del_char_delivery(context: dict, target: str, uuids: list[str]) -> str:
    """Remove characters from delivery."""
    delivery = get_event_elements(context["event"].id, DeliveryExp, context=context).get(uuid=target)
    delivery.characters.remove(*_get_chars(context, uuids))
    return delivery.name


def exec_add_char_prologue(context: dict, target: str, uuids: list[str]) -> str:
    """Add characters to a prologue."""
    prologue = get_event_elements(context["event"].id, Prologue, context=context).get(uuid=target)
    prologue.characters.add(*_get_chars(context, uuids))
    return prologue.name


def exec_del_char_prologue(
    context: dict,
    target: str,
    uuids: list[str],
) -> str:
    """Remove characters from a prologue."""
    prologue = get_event_elements(context["event"].id, Prologue, context=context).get(uuid=target)
    prologue.characters.remove(*_get_chars(context, uuids))
    return prologue.name


def exec_set_char_progress(
    context: dict,
    target: str,
    uuids: list[str],
) -> str:
    """Update progress step for specified characters."""
    progress_step = get_event_elements(context["event"].id, ProgressStep, context=context).get(uuid=target)
    get_event_elements(context["event"].id, Character, context=context).filter(uuid__in=uuids).update(
        progress=progress_step
    )
    return progress_step.name


def exec_set_char_assigned(context: dict, target: str, uuids: list[str]) -> str:
    """Assign characters to a member."""
    member = _get_assoc_member(context, target)
    get_event_elements(context["event"].id, Character, context=context).filter(uuid__in=uuids).update(assigned=member)
    return member.name


def exec_set_char_status(context: dict, target: str, uuids: list[str]) -> str:
    """Update character status for specified characters in the event."""
    # Validate the status against the allowed choices before writing raw POST
    if target not in CharacterStatus.values:
        msg = "invalid character status"
        raise ValueError(msg)
    # Save each changed character so status emails and cache refreshes fire
    characters = (
        get_event_elements(context["event"].id, Character, context=context)
        .filter(uuid__in=uuids)
        .exclude(status=target)
        .select_related("player", "event")
    )
    for character in characters:
        character.status = target
        character.save()
    return dict(CharacterStatus.choices).get(target, target)


_BOOL_TARGETS = {"1": True, "0": False}


def _get_bulk_bool_target(target: str) -> bool:
    """Parse a bulk operation's boolean target value ("1"/"0")."""
    if target not in _BOOL_TARGETS:
        msg = "invalid boolean target"
        raise ValueError(msg)
    return _BOOL_TARGETS[target]


def _bulk_bool_choices() -> list[dict]:
    """Build the Yes/No target choices used by boolean bulk operations."""
    return [{"uuid": "1", "name": _("Yes")}, {"uuid": "0", "name": _("No")}]


def exec_set_char_hide(context: dict, target: str, uuids: list[str]) -> str:
    """Set the hidden flag for specified characters in the event."""
    value = _get_bulk_bool_target(target)
    get_event_elements(context["event"].id, Character, context=context).filter(uuid__in=uuids).update(hide=value)
    return _("Yes") if value else _("No")


def exec_set_char_locked(context: dict, target: str, uuids: list[str]) -> str:
    """Set the locked flag for specified characters in the event."""
    value = _get_bulk_bool_target(target)
    get_event_elements(context["event"].id, Character, context=context).filter(uuid__in=uuids).update(locked=value)
    return _("Yes") if value else _("No")


def _get_char_question_types(context: dict) -> set:
    """Return the set of active writing question types for characters in this event."""
    event_id = context["event"].id
    questions = get_cached_writing_questions(event_id, QuestionApplicable.CHARACTER)
    return {question["typ"] for question in questions}


def _add_char_hide_locked_options(context: dict) -> None:
    """Append hide/locked toggle operations if the corresponding question type is active."""
    question_types = _get_char_question_types(context)
    if WritingQuestionType.HIDE in question_types:
        context["bulk"].append(_bulk_op(Operations.SET_CHAR_HIDE, _bulk_bool_choices()))
    if WritingQuestionType.LOCKED in question_types:
        context["bulk"].append(_bulk_op(Operations.SET_CHAR_LOCKED, _bulk_bool_choices()))


def _choice_questions(questions: list[dict], typ: str) -> list[dict]:
    """Return the questions of the given type that have at least one option."""
    return [question for question in questions if question["typ"] == typ and question["options"]]


BULK_QUESTION_NAME_MAX_LENGTH = 30

# Per-question bulk operations: (operation, question type, label)
CHAR_QUESTION_OPS = (
    (Operations.SET_CHAR_QUESTION, BaseQuestionType.SINGLE, _("Set '%(name)s'")),
    (Operations.ADD_CHAR_QUESTION, BaseQuestionType.MULTIPLE, _("Add to '%(name)s'")),
    (Operations.DEL_CHAR_QUESTION, BaseQuestionType.MULTIPLE, _("Remove from '%(name)s'")),
)
REG_QUESTION_OPS = (
    (Operations.SET_REG_QUESTION, BaseQuestionType.SINGLE, _("Set '%(name)s'")),
    (Operations.ADD_REG_QUESTION, BaseQuestionType.MULTIPLE, _("Add to '%(name)s'")),
    (Operations.DEL_REG_QUESTION, BaseQuestionType.MULTIPLE, _("Remove from '%(name)s'")),
)


def _bulk_question_ops(question_ops: tuple, questions: list[dict]) -> list[dict]:
    """Build the per-question bulk operations of choice questions, listing their options as targets."""
    return [
        {
            "idx": f"{int(operation)}_{question['uuid']}",
            "label": label % {"name": question["name"][:BULK_QUESTION_NAME_MAX_LENGTH]},
            "objs": [{"uuid": option["uuid"], "name": option["name"]} for option in question["options"]],
        }
        for question in questions
        for operation, typ, label in question_ops
        if question["typ"] == typ and question["options"]
    ]


def _find_question_option(questions: list[dict], option_uuid: str, typ: str) -> tuple[dict, dict]:
    """Return the question of the given type and its option matching the given option UUID."""
    for question in _choice_questions(questions, typ):
        for option in question["options"]:
            if str(option["uuid"]) == option_uuid:
                return question, option
    msg = "invalid option"
    raise ValueError(msg)


def _char_questions(context: dict) -> list[dict]:
    """Return the cached character writing questions of the event."""
    return get_cached_writing_questions(context["event"].id, QuestionApplicable.CHARACTER)


def _set_single_choice(
    choice_model: type, owner_field: str, owner_ids: list[int], question_id: int, option_id: int
) -> set[int]:
    """Make option the only choice of question for each owner, touching only owners with a different value.

    Returns the ids of the owners whose choice changed.
    """
    choices = choice_model.objects.filter(**{f"{owner_field}__in": owner_ids}, question_id=question_id)
    with transaction.atomic():
        stale = choices.exclude(option_id=option_id)
        changed_ids = set(stale.values_list(owner_field, flat=True))
        stale.delete()
        already_set = set(choices.filter(option_id=option_id).values_list(owner_field, flat=True))
        missing_ids = [owner_id for owner_id in owner_ids if owner_id not in already_set]
        choice_model.objects.bulk_create(
            [
                choice_model(**{owner_field: owner_id}, question_id=question_id, option_id=option_id)
                for owner_id in missing_ids
            ]
        )
    return changed_ids | set(missing_ids)


def _add_choice(
    choice_model: type, owner_field: str, owner_ids: list[int], question_id: int, option_id: int
) -> set[int]:
    """Add option to the choices of question for each owner not having it yet.

    Returns the ids of the owners whose choices changed.
    """
    choices = choice_model.objects.filter(**{f"{owner_field}__in": owner_ids}, question_id=question_id)
    already_set = set(choices.filter(option_id=option_id).values_list(owner_field, flat=True))
    missing_ids = [owner_id for owner_id in owner_ids if owner_id not in already_set]
    choice_model.objects.bulk_create(
        [
            choice_model(**{owner_field: owner_id}, question_id=question_id, option_id=option_id)
            for owner_id in missing_ids
        ]
    )
    return set(missing_ids)


def _remove_choice(
    choice_model: type, owner_field: str, owner_ids: list[int], question_id: int, option_id: int
) -> set[int]:
    """Remove option from the choices of question for each owner.

    Returns the ids of the owners whose choices changed.
    """
    choices = choice_model.objects.filter(
        **{f"{owner_field}__in": owner_ids}, question_id=question_id, option_id=option_id
    )
    changed_ids = set(choices.values_list(owner_field, flat=True))
    choices.delete()
    return changed_ids


# Question type and choice update function of each per-question operation
QUESTION_CHOICE_ACTIONS = {
    Operations.SET_CHAR_QUESTION: (BaseQuestionType.SINGLE, _set_single_choice),
    Operations.ADD_CHAR_QUESTION: (BaseQuestionType.MULTIPLE, _add_choice),
    Operations.DEL_CHAR_QUESTION: (BaseQuestionType.MULTIPLE, _remove_choice),
    Operations.SET_REG_QUESTION: (BaseQuestionType.SINGLE, _set_single_choice),
    Operations.ADD_REG_QUESTION: (BaseQuestionType.MULTIPLE, _add_choice),
    Operations.DEL_REG_QUESTION: (BaseQuestionType.MULTIPLE, _remove_choice),
}


def _exec_char_question(operation: Operations, context: dict, target: str, uuids: list[str]) -> str:
    """Update the choices of a writing question for the specified characters, according to operation."""
    typ, update_choices = QUESTION_CHOICE_ACTIONS[operation]
    question, option = _find_question_option(_char_questions(context), target, typ)
    character_ids = list(
        get_event_elements(context["event"].id, Character, context=context)
        .filter(uuid__in=uuids)
        .values_list("id", flat=True)
    )
    with transaction.atomic():
        changed_ids = update_choices(WritingChoice, "element_id", character_ids, question["id"], option["id"])
    if changed_ids:
        clear_event_cache_all_runs(context["event"].id)
        for run in get_event_and_children_runs(context["event"].id):
            clear_registration_counts_cache(run.id)

    return f"{question['name']}: {option['name']}"


def exec_set_char_question(context: dict, target: str, uuids: list[str]) -> str:
    """Set the chosen option of a single choice writing question for the specified characters."""
    return _exec_char_question(Operations.SET_CHAR_QUESTION, context, target, uuids)


def exec_add_char_question(context: dict, target: str, uuids: list[str]) -> str:
    """Add an option to a multiple choice writing question for the specified characters."""
    return _exec_char_question(Operations.ADD_CHAR_QUESTION, context, target, uuids)


def exec_del_char_question(context: dict, target: str, uuids: list[str]) -> str:
    """Remove an option from a multiple choice writing question for the specified characters."""
    return _exec_char_question(Operations.DEL_CHAR_QUESTION, context, target, uuids)


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
            Operations.SET_CHAR_HIDE: exec_set_char_hide,
            Operations.SET_CHAR_LOCKED: exec_set_char_locked,
            Operations.SET_CHAR_QUESTION: exec_set_char_question,
            Operations.ADD_CHAR_QUESTION: exec_add_char_question,
            Operations.DEL_CHAR_QUESTION: exec_del_char_question,
        }
        # Execute the bulk operation and raise exception to return result
        raise ReturnNowError(exec_bulk(request, context, mapping, Character, allow_delete=True))

    # Initialize bulk operations list for GET requests
    context["bulk"] = []
    event_id = context["event"].id

    # Add faction-related operations if faction feature is enabled
    if "faction" in context["features"]:
        factions = get_bulk_options_cache(event_id, "factions")
        context["bulk"].extend(
            [
                _bulk_op(Operations.ADD_CHAR_FACT, factions),
                _bulk_op(Operations.DEL_CHAR_FACT, factions),
            ],
        )

    # Add plot-related operations if plot feature is enabled
    if "plot" in context["features"]:
        plots = get_bulk_options_cache(event_id, "plots")
        context["bulk"].extend(
            [
                _bulk_op(Operations.ADD_CHAR_PLOT, plots),
                _bulk_op(Operations.DEL_CHAR_PLOT, plots),
            ],
        )

    # Add prologue-related operations if prologue feature is enabled
    if "prologue" in context["features"]:
        prologues = get_bulk_options_cache(event_id, "prologues")
        context["bulk"].extend(
            [
                _bulk_op(Operations.ADD_CHAR_PROLOGUE, prologues),
                _bulk_op(Operations.DEL_CHAR_PROLOGUE, prologues),
            ],
        )

    # Add XP delivery operations if experience feature is enabled
    if "experience" in context["features"]:
        deliveries = get_bulk_options_cache(event_id, "deliveries")
        context["bulk"].extend(
            [
                _bulk_op(Operations.ADD_CHAR_DELIVERY, deliveries),
                _bulk_op(Operations.DEL_CHAR_DELIVERY, deliveries),
            ],
        )

    # Add progress step operation if progress feature is enabled
    if "progress" in context["features"]:
        context["bulk"].append(
            _bulk_op(Operations.SET_CHAR_PROGRESS, get_bulk_options_cache(event_id, "progress_steps")),
        )

    # Add staff assignment operation if assigned feature is enabled
    if "assigned" in context["features"]:
        context["bulk"].append(
            _bulk_op(Operations.SET_CHAR_ASSIGNED, get_bulk_options_cache(event_id, "staffers")),
        )

    # Add status assignment operation if enabled
    if get_event_config(context["event"].id, "user_character_approval", context=context):
        status_choices = [{"uuid": choice[0], "name": choice[1]} for choice in CharacterStatus.choices]
        context["bulk"].append(
            _bulk_op(Operations.SET_CHAR_STATUS, status_choices),
        )

    _add_char_hide_locked_options(context)
    context["bulk"].extend(_bulk_question_ops(CHAR_QUESTION_OPS, _char_questions(context)))
    _add_bulk_delete_option(request, context)


def handle_bulk_plots(request: HttpRequest, context: dict) -> None:
    """Handle bulk operations for plot management."""
    if request.POST:
        mapping = {
            Operations.ADD_PLOT_CHAR: exec_add_plot_char,
            Operations.DEL_PLOT_CHAR: exec_del_plot_char,
            Operations.SET_PLOT_PROGRESS: exec_set_plot_progress,
            Operations.SET_PLOT_ASSIGNED: exec_set_plot_assigned,
        }
        raise ReturnNowError(exec_bulk(request, context, mapping, Plot, allow_delete=True))

    event_id = context["event"].id

    characters = get_bulk_options_cache(event_id, "characters")
    context["bulk"] = [
        _bulk_op(Operations.ADD_PLOT_CHAR, characters),
        _bulk_op(Operations.DEL_PLOT_CHAR, characters),
    ]

    if "progress" in context["features"]:
        context["bulk"].append(
            _bulk_op(Operations.SET_PLOT_PROGRESS, get_bulk_options_cache(event_id, "progress_steps")),
        )

    if "assigned" in context["features"]:
        context["bulk"].append(
            _bulk_op(Operations.SET_PLOT_ASSIGNED, get_bulk_options_cache(event_id, "staffers")),
        )

    _add_bulk_delete_option(request, context)


def exec_add_faction_char(context: dict, target: str, uuids: list[str]) -> str:
    """Add a character to selected factions."""
    char = get_event_elements(context["event"].id, Character, context=context).get(uuid=target)
    for faction in get_event_elements(context["event"].id, Faction, context=context).filter(uuid__in=uuids):
        faction.characters.add(char)
    return char.name


def exec_del_faction_char(context: dict, target: str, uuids: list[str]) -> str:
    """Remove a character from selected factions."""
    char = get_event_elements(context["event"].id, Character, context=context).get(uuid=target)
    for faction in get_event_elements(context["event"].id, Faction, context=context).filter(uuid__in=uuids):
        faction.characters.remove(char)
    return char.name


def exec_set_faction_progress(context: dict, target: str, uuids: list[str]) -> str:
    """Set progress step for selected factions."""
    progress_step = get_event_elements(context["event"].id, ProgressStep, context=context).get(uuid=target)
    get_event_elements(context["event"].id, Faction, context=context).filter(uuid__in=uuids).update(
        progress=progress_step
    )
    return progress_step.name


def exec_set_faction_assigned(context: dict, target: str, uuids: list[str]) -> str:
    """Assign selected factions to a staff member."""
    member = _get_assoc_member(context, target)
    get_event_elements(context["event"].id, Faction, context=context).filter(uuid__in=uuids).update(assigned=member)
    return member.name


def handle_bulk_factions(request: HttpRequest, context: dict) -> None:
    """Handle bulk operations for faction management."""
    if request.POST:
        mapping = {
            Operations.ADD_FACT_CHAR: exec_add_faction_char,
            Operations.DEL_FACT_CHAR: exec_del_faction_char,
            Operations.SET_FACT_PROGRESS: exec_set_faction_progress,
            Operations.SET_FACT_ASSIGNED: exec_set_faction_assigned,
        }
        raise ReturnNowError(exec_bulk(request, context, mapping, Faction, allow_delete=True))

    context["bulk"] = []
    event_id = context["event"].id

    characters = get_bulk_options_cache(event_id, "characters")
    context["bulk"] = [
        _bulk_op(Operations.ADD_FACT_CHAR, characters),
        _bulk_op(Operations.DEL_FACT_CHAR, characters),
    ]

    if "progress" in context["features"]:
        context["bulk"].append(
            _bulk_op(Operations.SET_FACT_PROGRESS, get_bulk_options_cache(event_id, "progress_steps")),
        )

    if "assigned" in context["features"]:
        context["bulk"].append(
            _bulk_op(Operations.SET_FACT_ASSIGNED, get_bulk_options_cache(event_id, "staffers")),
        )

    _add_bulk_delete_option(request, context)


def exec_set_quest_type(
    context: dict,
    target: str,
    uuids: list[str],
) -> str:
    """Set quest type for multiple quests."""
    quest_type = get_event_elements(context["event"].id, QuestType, context=context).get(uuid=target)
    get_event_elements(context["event"].id, Quest, context=context).filter(uuid__in=uuids).update(typ=quest_type)
    return quest_type.name


def handle_bulk_quest(request: HttpRequest, context: dict) -> None:
    """Handle bulk operations for quest management.

    Args:
        request: HTTP request object
        context: Context dictionary containing event and other data

    """
    # Handle POST request - execute bulk operations
    if request.POST:
        raise ReturnNowError(
            exec_bulk(request, context, {Operations.SET_QUEST_TYPE: exec_set_quest_type}, Quest, allow_delete=True)
        )

    context["bulk"] = [
        _bulk_op(Operations.SET_QUEST_TYPE, get_bulk_options_cache(context["event"].id, "quest_types")),
    ]
    _add_bulk_delete_option(request, context)


def exec_set_quest(
    context: dict,
    target: str,
    uuids: list[str],
) -> str:
    """Assign a quest to multiple traits."""
    # Retrieve the target quest from the event
    quest = get_event_elements(context["event"].id, Quest, context=context).get(uuid=target)
    # Update all specified traits to use this quest
    get_event_elements(context["event"].id, Trait, context=context).filter(uuid__in=uuids).update(quest=quest)
    return quest.name


def handle_bulk_trait(request: HttpRequest, context: dict) -> None:
    """Handle bulk trait operations for quest assignment."""
    if request.POST:
        # Execute bulk operation for setting quest traits
        raise ReturnNowError(
            exec_bulk(request, context, {Operations.SET_TRAIT_QUEST: exec_set_quest}, Trait, allow_delete=True)
        )

    context["bulk"] = [
        _bulk_op(Operations.SET_TRAIT_QUEST, get_bulk_options_cache(context["event"].id, "quests")),
    ]
    _add_bulk_delete_option(request, context)


def exec_set_ability_type(
    context: dict,
    target: str | int,
    uuids: list[str],
) -> str:
    """Update ability type for selected abilities in bulk."""
    # Get target ability type from event elements
    typ = get_event_elements(context["event"].id, AbilityTypeExp, context=context).get(uuid=target)
    # Update all selected abilities with new type
    get_event_elements(context["event"].id, AbilityExp, context=context).filter(uuid__in=uuids).update(typ=typ)
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
            exec_bulk(
                request, context, {Operations.SET_ABILITY_TYPE: exec_set_ability_type}, AbilityExp, allow_delete=True
            )
        )

    context["bulk"] = [
        _bulk_op(Operations.SET_ABILITY_TYPE, get_bulk_options_cache(context["event"].id, "ability_types")),
    ]
    _add_bulk_delete_option(request, context)


def _exec_reg_question(operation: Operations, context: dict, target: str, uuids: list[str]) -> str:
    """Update the choices of a registration question for the specified registrations, according to operation."""
    typ, update_choices = QUESTION_CHOICE_ACTIONS[operation]
    question, option = _find_question_option(get_cached_registration_questions(context["event"].id), target, typ)
    registration_ids = list(_scoped_bulk_queryset(context, Registration, uuids).values_list("id", flat=True))
    with transaction.atomic():
        changed_ids = update_choices(
            RegistrationChoice, "registration_id", registration_ids, question["id"], option["id"]
        )
        _recompute_registrations(context, changed_ids)

    return f"{question['name']}: {option['name']}"


def exec_set_reg_question(context: dict, target: str, uuids: list[str]) -> str:
    """Set the chosen option of a single choice registration question for the specified registrations."""
    return _exec_reg_question(Operations.SET_REG_QUESTION, context, target, uuids)


def exec_add_reg_question(context: dict, target: str, uuids: list[str]) -> str:
    """Add an option to a multiple choice registration question for the specified registrations."""
    return _exec_reg_question(Operations.ADD_REG_QUESTION, context, target, uuids)


def exec_del_reg_question(context: dict, target: str, uuids: list[str]) -> str:
    """Remove an option from a multiple choice registration question for the specified registrations."""
    return _exec_reg_question(Operations.DEL_REG_QUESTION, context, target, uuids)


def _recompute_registrations(context: dict, registration_ids: set[int], ticket_id: int | None = None) -> None:
    """Re-save the changed registrations, optionally setting their ticket, to update totals, accounting and caches."""
    if not registration_ids:
        return
    with transaction.atomic():
        for registration in Registration.objects.filter(run_id=context["run"].id, id__in=registration_ids):
            if ticket_id is not None:
                registration.ticket_id = ticket_id
            registration.save()
    clear_registration_counts_cache(context["run"].id)


def exec_set_reg_ticket(context: dict, target: str, uuids: list[str]) -> str:
    """Set the ticket of the specified registrations."""
    ticket = next(
        (ticket for ticket in get_registration_tickets(context["event"].id) if str(ticket["uuid"]) == target), None
    )
    if not ticket:
        msg = "invalid ticket"
        raise ValueError(msg)
    to_change = _scoped_bulk_queryset(context, Registration, uuids).exclude(ticket_id=ticket["id"])
    _recompute_registrations(context, set(to_change.values_list("id", flat=True)), ticket_id=ticket["id"])

    return ticket["name"]


def handle_bulk_registrations(request: HttpRequest, context: dict) -> None:
    """Handle bulk operations on registrations: set the ticket, update the choices of choice questions."""
    if request.POST:
        mapping = {
            Operations.SET_REG_TICKET: exec_set_reg_ticket,
            Operations.SET_REG_QUESTION: exec_set_reg_question,
            Operations.ADD_REG_QUESTION: exec_add_reg_question,
            Operations.DEL_REG_QUESTION: exec_del_reg_question,
        }
        raise ReturnNowError(exec_bulk(request, context, mapping, Registration))

    tickets = [
        {"uuid": ticket["uuid"], "name": ticket["name"]} for ticket in get_registration_tickets(context["event"].id)
    ]
    context["bulk"] = [_bulk_op(Operations.SET_REG_TICKET, tickets)]
    context["bulk"].extend(_bulk_question_ops(REG_QUESTION_OPS, get_cached_registration_questions(context["event"].id)))
