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

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, JsonResponse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_event_config
from larpmanager.models.access import get_event_staffers
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import ProgressStep
from larpmanager.models.experience import AbilityPx, AbilityTypePx, DeliveryPx
from larpmanager.models.member import Log, Member
from larpmanager.models.miscellanea import (
    WarehouseContainer,
    WarehouseItem,
    WarehouseTag,
)
from larpmanager.models.writing import Character, CharacterStatus, Faction, Plot, Prologue
from larpmanager.utils.exceptions import ReturnNowError

if TYPE_CHECKING:
    from django.db.models import QuerySet


def _get_bulk_params(request: HttpRequest, context: dict) -> tuple[list[int], int, int]:
    """Extract and validate bulk operation parameters from request.

    Extracts operation ID, target ID, and a list of entity IDs from the request,
    validates the data types, and logs the bulk operation attempt.

    Args:
        request: HTTP request object containing POST data with operation parameters
        context: Context dictionary containing event/run information and association ID

    Returns:
        :tuple[list[int], int, int]: A tuple containing:
            - entity_ids: List of validated integer IDs for bulk operation
            - operation_code: Integer operation code (defaults to 0 if invalid)
            - target_code: Integer target code (defaults to 0 if invalid)

    Raises:
        ReturnNowError: If no valid IDs are provided in the request

    """
    # Extract and validate operation parameter, default to 0 for invalid values
    try:
        operation_code = int(request.POST.get("operation", "0"))
    except (ValueError, TypeError):
        operation_code = 0

    # Extract and validate target parameter, default to 0 for invalid values
    try:
        target_code = int(request.POST.get("target", "0"))
    except (ValueError, TypeError):
        target_code = 0

    # Process list of IDs, filtering out invalid entries
    entity_ids = []
    for raw_id in request.POST.getlist("ids[]", []):
        try:
            entity_ids.append(int(raw_id))
        except (ValueError, TypeError):  # noqa: PERF203 - Need per-item error handling to filter invalid IDs
            # Skip invalid ID values and continue processing
            continue

    # Validate that at least one valid ID was provided
    if not entity_ids:
        raise ReturnNowError(JsonResponse({"error": "no ids"}, status=400))

    # Determine entity ID for logging (use run ID if available, otherwise association ID)
    entity_id_for_log = context["association_id"]
    if "run" in context:
        entity_id_for_log = context["run"].id

    # Log the bulk operation attempt with all relevant parameters
    Log.objects.create(
        member=context["member"],
        cls=f"bulk {operation_code} {target_code}",
        eid=entity_id_for_log,
        dct={"operation": operation_code, "target": target_code, "ids": entity_ids},
    )

    return entity_ids, operation_code, target_code


class Operations:
    MOVE_ITEM_BOX = 1
    ADD_ITEM_TAG = 2
    DEL_ITEM_TAG = 3
    ADD_CHAR_FACT = 4
    DEL_CHAR_FACT = 5
    ADD_CHAR_PLOT = 6
    DEL_CHAR_PLOT = 7
    SET_QUEST_TYPE = 8
    SET_TRAIT_QUEST = 9
    SET_ABILITY_TYPE = 10
    ADD_CHAR_DELIVERY = 11
    DEL_CHAR_DELIVERY = 12
    ADD_CHAR_PROLOGUE = 13
    DEL_CHAR_PROLOGUE = 14
    SET_CHAR_PROGRESS = 15
    SET_CHAR_ASSIGNED = 16
    SET_CHAR_STATUS = 17


def exec_bulk(request: HttpRequest, context: dict, operation_mapping: dict) -> JsonResponse:
    """Execute bulk operations on a collection of objects.

    Args:
        request: HTTP request object containing bulk operation parameters
        context: Context dictionary with operation-specific data
        operation_mapping: Dictionary mapping operation names to their handler functions

    Returns:
        JsonResponse: Success response with "ok" status or error response with
        appropriate error message and HTTP status code

    Raises:
        ObjectDoesNotExist: When target objects for the operation are not found

    """
    # Extract bulk operation parameters from request
    object_ids, operation_name, operation_target = _get_bulk_params(request, context)

    # Validate that the requested operation is supported
    if operation_name not in operation_mapping:
        return JsonResponse({"error": "unknow operation"}, status=400)

    try:
        # Execute the bulk operation using the mapped handler function
        operation_mapping[operation_name](context, operation_target, object_ids)
    except ObjectDoesNotExist:
        # Handle case where target objects don't exist
        return JsonResponse({"error": "not found"}, status=400)

    # Return success response
    return JsonResponse({"res": "ok"})


def _get_inv_items(warehouse_item_ids: list[int], context: dict) -> list[int]:
    """Get warehouse item IDs filtered by association."""
    return WarehouseItem.objects.filter(
        association_id=context["association_id"],
        pk__in=warehouse_item_ids,
    ).values_list("pk", flat=True)


def exec_add_item_tag(
    context,
    target: int,
    ids: list[int],
) -> None:
    """Add items to a warehouse tag."""
    tag = WarehouseTag.objects.get(association_id=context["association_id"], pk=target)
    tag.items.add(*_get_inv_items(ids, context))


def exec_del_item_tag(context: dict[str, Any], target: int, ids: str) -> None:
    """Remove items from a warehouse tag."""
    tag = WarehouseTag.objects.get(association_id=context["association_id"], pk=target)
    tag.items.remove(*_get_inv_items(ids, context))


def exec_move_item_box(
    context,
    target: int,
    ids: list[int],
) -> None:
    """Move warehouse items to a target container."""
    # Retrieve the target container for the association
    container = WarehouseContainer.objects.get(association_id=context["association_id"], pk=target)

    # Update all specified items to the new container
    WarehouseItem.objects.filter(association_id=context["association_id"], pk__in=ids).update(container=container)


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
        raise ReturnNowError(exec_bulk(request, context, operation_type_to_handler))

    # Fetch available containers for the current association
    available_containers = (
        WarehouseContainer.objects.filter(association_id=context["association_id"])
        .values("id", "name")
        .order_by("name")
    )
    # Fetch available tags for the current association
    available_tags = (
        WarehouseTag.objects.filter(association_id=context["association_id"]).values("id", "name").order_by("name")
    )

    # Populate context with bulk operation choices and their associated objects
    context["bulk"] = [
        {"idx": Operations.MOVE_ITEM_BOX, "label": _("Move to container"), "objs": available_containers},
        {"idx": Operations.ADD_ITEM_TAG, "label": _("Add tag"), "objs": available_tags},
        {"idx": Operations.DEL_ITEM_TAG, "label": _("Remove tag"), "objs": available_tags},
    ]


def _get_chars(context: dict, character_ids: list) -> list:
    """Return character IDs filtered by event and provided IDs."""
    return context["event"].get_elements(Character).filter(pk__in=character_ids).values_list("pk", flat=True)


def exec_add_char_fact(context: dict, target, ids) -> None:
    """Add characters to a faction."""
    fact = context["event"].get_elements(Faction).get(pk=target)
    fact.characters.add(*_get_chars(context, ids))


def exec_del_char_fact(context: dict, target: int, ids: list[int]) -> None:
    """Remove characters from a faction."""
    fact = context["event"].get_elements(Faction).get(pk=target)
    fact.characters.remove(*_get_chars(context, ids))


def exec_add_char_plot(context: dict, target: int, ids: list[int]) -> None:
    """Add characters to a plot element."""
    plot = context["event"].get_elements(Plot).get(pk=target)
    plot.characters.add(*_get_chars(context, ids))


def exec_del_char_plot(context: dict, target: int, ids: list[int]) -> None:
    """Remove characters from a plot element."""
    plot = context["event"].get_elements(Plot).get(pk=target)
    plot.characters.remove(*_get_chars(context, ids))


def exec_add_char_delivery(
    context: dict[str, Any],
    target: int | str,
    ids: list[int] | str,
) -> None:
    """Add characters to a delivery."""
    delivery = context["event"].get_elements(DeliveryPx).get(pk=target)
    delivery.characters.add(*_get_chars(context, ids))


def exec_del_char_delivery(context: dict, target: int, ids: list[int]) -> None:
    """Remove characters from delivery."""
    delivery = context["event"].get_elements(DeliveryPx).get(pk=target)
    delivery.characters.remove(*_get_chars(context, ids))


def exec_add_char_prologue(context: dict[str, Any], target: int, ids: list[int]) -> None:
    """Add characters to a prologue."""
    prologue = context["event"].get_elements(Prologue).get(pk=target)
    prologue.characters.add(*_get_chars(context, ids))


def exec_del_char_prologue(
    context: dict[str, Any],
    target: int,
    ids: list[int],
) -> None:
    """Remove characters from a prologue."""
    prologue = context["event"].get_elements(Prologue).get(pk=target)
    prologue.characters.remove(*_get_chars(context, ids))


def exec_set_char_progress(
    context: dict,
    target: int,
    ids: list[int],
) -> None:
    """Update progress step for specified characters."""
    progress_step = context["event"].get_elements(ProgressStep).get(pk=target)
    context["event"].get_elements(Character).filter(pk__in=ids).update(progress=progress_step)


def exec_set_char_assigned(context: dict[str, Any], target: str, ids: list[int]) -> None:
    """Assign characters to a member."""
    member = Member.objects.get(pk=target)
    context["event"].get_elements(Character).filter(pk__in=ids).update(assigned=member)


def exec_set_char_status(context: dict, target: str, ids: list[int]) -> None:
    """Update character status for specified characters in the event."""
    context["event"].get_elements(Character).filter(pk__in=ids).update(status=target)


def handle_bulk_characters(request: HttpRequest, context: dict[str, Any]) -> None:
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
        raise ReturnNowError(exec_bulk(request, context, mapping))

    # Initialize bulk operations list for GET requests
    context["bulk"] = []

    # Add faction-related operations if faction feature is enabled
    if "faction" in context["features"]:
        factions = context["event"].get_elements(Faction).values("id", "name").order_by("name")
        context["bulk"].extend(
            [
                {"idx": Operations.ADD_CHAR_FACT, "label": _("Add to faction"), "objs": factions},
                {"idx": Operations.DEL_CHAR_FACT, "label": _("Remove from faction"), "objs": factions},
            ],
        )

    # Add plot-related operations if plot feature is enabled
    if "plot" in context["features"]:
        plots = context["event"].get_elements(Plot).values("id", "name").order_by("name")
        context["bulk"].extend(
            [
                {"idx": Operations.ADD_CHAR_PLOT, "label": _("Add to plot"), "objs": plots},
                {"idx": Operations.DEL_CHAR_PLOT, "label": _("Remove from plot"), "objs": plots},
            ],
        )

    # Add prologue-related operations if prologue feature is enabled
    if "prologue" in context["features"]:
        prologues = context["event"].get_elements(Prologue).values("id", "name").order_by("name")
        context["bulk"].extend(
            [
                {"idx": Operations.ADD_CHAR_PROLOGUE, "label": _("Add prologue"), "objs": prologues},
                {"idx": Operations.DEL_CHAR_PROLOGUE, "label": _("Remove prologue"), "objs": prologues},
            ],
        )

    # Add XP delivery operations if px feature is enabled
    if "px" in context["features"]:
        delivery = context["event"].get_elements(DeliveryPx).values("id", "name")
        context["bulk"].extend(
            [
                {"idx": Operations.ADD_CHAR_DELIVERY, "label": _("Add to xp delivery"), "objs": delivery},
                {"idx": Operations.DEL_CHAR_DELIVERY, "label": _("Remove from xp delivery"), "objs": delivery},
            ],
        )

    # Add progress step operation if progress feature is enabled
    if "progress" in context["features"]:
        progress_steps = context["event"].get_elements(ProgressStep).values("id", "name").order_by("order")
        context["bulk"].append(
            {"idx": Operations.SET_CHAR_PROGRESS, "label": _("Set progress step"), "objs": progress_steps},
        )

    # Add staff assignment operation if assigned feature is enabled
    if "assigned" in context["features"]:
        # Get event staff members using the same function used in writing utils
        event_staff = get_event_staffers(context["event"])
        staff_members = [{"id": m.id, "name": m.show_nick()} for m in event_staff]
        context["bulk"].append(
            {"idx": Operations.SET_CHAR_ASSIGNED, "label": _("Set assigned staff member"), "objs": staff_members},
        )

    # Add status assignment operation if enabled
    if get_event_config(context["event"].id, "user_character_approval", default_value=False, context=context):
        status_choices = [{"id": choice[0], "name": choice[1]} for choice in CharacterStatus.choices]
        context["bulk"].append(
            {"idx": Operations.SET_CHAR_STATUS, "label": _("Set character status"), "objs": status_choices},
        )


def exec_set_quest_type(
    context: dict[str, Any],
    target: int,
    ids: list[int],
) -> None:
    """Set quest type for multiple quests."""
    quest_type = context["event"].get_elements(QuestType).get(pk=target)
    context["event"].get_elements(Quest).filter(pk__in=ids).update(typ=quest_type)


def handle_bulk_quest(request: HttpRequest, context: dict) -> None:
    """Handle bulk operations for quest management.

    Args:
        request: HTTP request object
        context: Context dictionary containing event and other data

    """
    # Handle POST request - execute bulk operations
    if request.POST:
        raise ReturnNowError(exec_bulk(request, context, {Operations.SET_QUEST_TYPE: exec_set_quest_type}))

    # Get available quest types for the event, ordered by name
    quest_types = context["event"].get_elements(QuestType).values("id", "name").order_by("name")

    # Set up bulk operation options in context
    context["bulk"] = [
        {"idx": Operations.SET_QUEST_TYPE, "label": _("Set quest type"), "objs": quest_types},
    ]


def exec_set_quest(
    context: dict[str, Any],
    target: int,
    ids: list[int],
) -> None:
    """Assign a quest to multiple traits."""
    # Retrieve the target quest from the event
    quest = context["event"].get_elements(Quest).get(pk=target)
    # Update all specified traits to use this quest
    context["event"].get_elements(Trait).filter(pk__in=ids).update(quest=quest)


def handle_bulk_trait(request: HttpRequest, context: dict) -> None:
    """Handle bulk trait operations for quest assignment."""
    if request.POST:
        # Execute bulk operation for setting quest traits
        raise ReturnNowError(exec_bulk(request, context, {Operations.SET_TRAIT_QUEST: exec_set_quest}))

    # Get available quests for the current event
    quests = context["event"].get_elements(Quest).values("id", "name").order_by("name")

    # Configure bulk operation options
    context["bulk"] = [
        {"idx": Operations.SET_TRAIT_QUEST, "label": _("Set quest"), "objs": quests},
    ]


def exec_set_ability_type(
    context: dict[str, Any],
    target: str | int,
    ids: list[int] | QuerySet,
) -> None:
    """Update ability type for selected abilities in bulk."""
    # Get target ability type from event elements
    typ = context["event"].get_elements(AbilityTypePx).get(pk=target)
    # Update all selected abilities with new type
    context["event"].get_elements(AbilityPx).filter(pk__in=ids).update(typ=typ)


def handle_bulk_ability(request: HttpRequest, context: dict) -> None:
    """Handle bulk operations for abilities.

    Args:
        request: HTTP request object
        context: Context dictionary containing event data

    """
    if request.POST:
        # Execute bulk operation and return early if POST request
        raise ReturnNowError(exec_bulk(request, context, {Operations.SET_ABILITY_TYPE: exec_set_ability_type}))

    # Get ability types for the event, ordered by name
    ability_types = context["event"].get_elements(AbilityTypePx).values("id", "name").order_by("name")

    # Setup bulk operations context
    context["bulk"] = [
        {"idx": Operations.SET_ABILITY_TYPE, "label": _("Set ability type"), "objs": ability_types},
    ]
