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
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, JsonResponse
from django.utils.translation import gettext_lazy as _

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
from larpmanager.models.writing import Character, Faction, Plot, Prologue
from larpmanager.utils.exceptions import ReturnNowError


def _get_bulk_params(request, ctx) -> tuple[list[int], int, int]:
    """
    Extract and validate bulk operation parameters from request.

    Extracts operation ID, target ID, and a list of entity IDs from the request,
    validates the data types, and logs the bulk operation attempt.

    Parameters
    ----------
    request : HttpRequest
        HTTP request object containing POST data with operation parameters
    ctx : dict
        Context dictionary containing event/run information and association ID

    Returns
    -------
    tuple[list[int], int, int]
        A tuple containing:
        - ids: List of validated integer IDs for bulk operation
        - operation: Integer operation code (defaults to 0 if invalid)
        - target: Integer target code (defaults to 0 if invalid)

    Raises
    ------
    ReturnNowError
        If no valid IDs are provided in the request
    """
    # Extract and validate operation parameter, default to 0 for invalid values
    try:
        operation = int(request.POST.get("operation", "0"))
    except (ValueError, TypeError):
        operation = 0

    # Extract and validate target parameter, default to 0 for invalid values
    try:
        target = int(request.POST.get("target", "0"))
    except (ValueError, TypeError):
        target = 0

    # Process list of IDs, filtering out invalid entries
    ids = []
    for x in request.POST.getlist("ids[]", []):
        try:
            ids.append(int(x))
        except (ValueError, TypeError):
            # Skip invalid ID values and continue processing
            continue

    # Validate that at least one valid ID was provided
    if not ids:
        raise ReturnNowError(JsonResponse({"error": "no ids"}, status=400))

    # Determine entity ID for logging (use run ID if available, otherwise association ID)
    eid = ctx["a_id"]
    if "run" in ctx:
        eid = ctx["run"].id

    # Log the bulk operation attempt with all relevant parameters
    Log.objects.create(
        member=request.user.member,
        cls=f"bulk {operation} {target}",
        eid=eid,
        dct={"operation": operation, "target": target, "ids": ids},
    )

    return ids, operation, target


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


def exec_bulk(request: HttpRequest, ctx: dict, mapping: dict) -> JsonResponse:
    """Execute bulk operations on a collection of objects.

    Args:
        request: HTTP request object containing bulk operation parameters
        ctx: Context dictionary with operation-specific data
        mapping: Dictionary mapping operation names to their handler functions

    Returns:
        JsonResponse: Success response with "ok" status or error response with
        appropriate error message and HTTP status code

    Raises:
        ObjectDoesNotExist: When target objects for the operation are not found
    """
    # Extract bulk operation parameters from request
    ids, operation, target = _get_bulk_params(request, ctx)

    # Validate that the requested operation is supported
    if operation not in mapping:
        return JsonResponse({"error": "unknow operation"}, status=400)

    try:
        # Execute the bulk operation using the mapped handler function
        mapping[operation](request, ctx, target, ids)
    except ObjectDoesNotExist:
        # Handle case where target objects don't exist
        return JsonResponse({"error": "not found"}, status=400)

    # Return success response
    return JsonResponse({"res": "ok"})


def _get_inv_items(ids, request):
    return WarehouseItem.objects.filter(assoc_id=request.assoc["id"], pk__in=ids).values_list("pk", flat=True)


def exec_add_item_tag(request, ctx, target, ids):
    tag = WarehouseTag.objects.get(assoc_id=request.assoc["id"], pk=target)
    tag.items.add(*_get_inv_items(ids, request))


def exec_del_item_tag(request, ctx, target, ids):
    tag = WarehouseTag.objects.get(assoc_id=request.assoc["id"], pk=target)
    tag.items.remove(*_get_inv_items(ids, request))


def exec_move_item_box(request, ctx, target, ids):
    container = WarehouseContainer.objects.get(assoc_id=request.assoc["id"], pk=target)
    WarehouseItem.objects.filter(assoc_id=request.assoc["id"], pk__in=ids).update(container=container)


def handle_bulk_items(request: HttpRequest, ctx: dict) -> None:
    """Handle bulk operations on warehouse items.

    This function processes bulk operations for warehouse items including adding/removing
    tags and moving items between containers. For POST requests, it executes the
    specified bulk operation. For GET requests, it populates the context with available
    bulk operation choices.

    Args:
        request: HTTP request object containing operation data and association info
        ctx: Context dictionary to update with bulk operation choices

    Raises:
        ReturnNowError: If POST request processed successfully with operation results
    """
    if request.POST:
        # Define mapping of operation types to their execution functions
        mapping = {
            Operations.ADD_ITEM_TAG: exec_add_item_tag,
            Operations.DEL_ITEM_TAG: exec_del_item_tag,
            Operations.MOVE_ITEM_BOX: exec_move_item_box,
        }
        # Execute the bulk operation and raise ReturnNowError with results
        raise ReturnNowError(exec_bulk(request, ctx, mapping))

    # Fetch available containers for the current association
    containers = WarehouseContainer.objects.filter(assoc_id=request.assoc["id"]).values("id", "name").order_by("name")
    # Fetch available tags for the current association
    tags = WarehouseTag.objects.filter(assoc_id=request.assoc["id"]).values("id", "name").order_by("name")

    # Populate context with bulk operation choices and their associated objects
    ctx["bulk"] = [
        {"idx": Operations.MOVE_ITEM_BOX, "label": _("Move to container"), "objs": containers},
        {"idx": Operations.ADD_ITEM_TAG, "label": _("Add tag"), "objs": tags},
        {"idx": Operations.DEL_ITEM_TAG, "label": _("Remove tag"), "objs": tags},
    ]


def _get_chars(ctx, ids):
    return ctx["event"].get_elements(Character).filter(pk__in=ids).values_list("pk", flat=True)


def exec_add_char_fact(request, ctx, target, ids):
    fact = ctx["event"].get_elements(Faction).get(pk=target)
    fact.characters.add(*_get_chars(ctx, ids))


def exec_del_char_fact(request, ctx, target, ids):
    fact = ctx["event"].get_elements(Faction).get(pk=target)
    fact.characters.remove(*_get_chars(ctx, ids))


def exec_add_char_plot(request, ctx, target, ids):
    plot = ctx["event"].get_elements(Plot).get(pk=target)
    plot.characters.add(*_get_chars(ctx, ids))


def exec_del_char_plot(request, ctx, target, ids):
    plot = ctx["event"].get_elements(Plot).get(pk=target)
    plot.characters.remove(*_get_chars(ctx, ids))


def exec_add_char_delivery(request, ctx, target, ids):
    delivery = ctx["event"].get_elements(DeliveryPx).get(pk=target)
    delivery.characters.add(*_get_chars(ctx, ids))


def exec_del_char_delivery(request, ctx, target, ids):
    delivery = ctx["event"].get_elements(DeliveryPx).get(pk=target)
    delivery.characters.remove(*_get_chars(ctx, ids))


def exec_add_char_prologue(request, ctx, target, ids):
    prologue = ctx["event"].get_elements(Prologue).get(pk=target)
    prologue.characters.add(*_get_chars(ctx, ids))


def exec_del_char_prologue(request, ctx, target, ids):
    prologue = ctx["event"].get_elements(Prologue).get(pk=target)
    prologue.characters.remove(*_get_chars(ctx, ids))


def exec_set_char_progress(request, ctx, target, ids):
    progress_step = ctx["event"].get_elements(ProgressStep).get(pk=target)
    ctx["event"].get_elements(Character).filter(pk__in=ids).update(progress=progress_step)


def exec_set_char_assigned(request, ctx, target, ids):
    member = Member.objects.get(pk=target)
    ctx["event"].get_elements(Character).filter(pk__in=ids).update(assigned=member)


def handle_bulk_characters(request: HttpRequest, ctx: dict[str, Any]) -> None:
    """Process bulk operations on character objects.

    Handles mass character modifications, faction assignments, and other
    batch character management tasks for efficient character administration.

    Args:
        request: Django HTTP request object containing POST data with operation details.
        ctx: Context dictionary containing event and selection data. Modified in-place
            to include operation results and status messages.

    Returns:
        None: Function modifies ctx in-place.

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
        }
        # Execute the bulk operation and raise exception to return result
        raise ReturnNowError(exec_bulk(request, ctx, mapping))

    # Initialize bulk operations list for GET requests
    ctx["bulk"] = []

    # Add faction-related operations if faction feature is enabled
    if "faction" in ctx["features"]:
        factions = ctx["event"].get_elements(Faction).values("id", "name").order_by("name")
        ctx["bulk"].extend(
            [
                {"idx": Operations.ADD_CHAR_FACT, "label": _("Add to faction"), "objs": factions},
                {"idx": Operations.DEL_CHAR_FACT, "label": _("Remove from faction"), "objs": factions},
            ]
        )

    # Add plot-related operations if plot feature is enabled
    if "plot" in ctx["features"]:
        plots = ctx["event"].get_elements(Plot).values("id", "name").order_by("name")
        ctx["bulk"].extend(
            [
                {"idx": Operations.ADD_CHAR_PLOT, "label": _("Add to plot"), "objs": plots},
                {"idx": Operations.DEL_CHAR_PLOT, "label": _("Remove from plot"), "objs": plots},
            ]
        )

    # Add prologue-related operations if prologue feature is enabled
    if "prologue" in ctx["features"]:
        prologues = ctx["event"].get_elements(Prologue).values("id", "name").order_by("name")
        ctx["bulk"].extend(
            [
                {"idx": Operations.ADD_CHAR_PROLOGUE, "label": _("Add prologue"), "objs": prologues},
                {"idx": Operations.DEL_CHAR_PROLOGUE, "label": _("Remove prologue"), "objs": prologues},
            ]
        )

    # Add XP delivery operations if px feature is enabled
    if "px" in ctx["features"]:
        delivery = ctx["event"].get_elements(DeliveryPx).values("id", "name")
        ctx["bulk"].extend(
            [
                {"idx": Operations.ADD_CHAR_DELIVERY, "label": _("Add to xp delivery"), "objs": delivery},
                {"idx": Operations.DEL_CHAR_DELIVERY, "label": _("Remove from xp delivery"), "objs": delivery},
            ]
        )

    # Add progress step operation if progress feature is enabled
    if "progress" in ctx["features"]:
        progress_steps = ctx["event"].get_elements(ProgressStep).values("id", "name").order_by("order")
        ctx["bulk"].append(
            {"idx": Operations.SET_CHAR_PROGRESS, "label": _("Set progress step"), "objs": progress_steps}
        )

    # Add staff assignment operation if assigned feature is enabled
    if "assigned" in ctx["features"]:
        # Get event staff members using the same function used in writing utils
        event_staff = get_event_staffers(ctx["event"])
        staff_members = [{"id": m.id, "name": m.show_nick()} for m in event_staff]
        ctx["bulk"].append(
            {"idx": Operations.SET_CHAR_ASSIGNED, "label": _("Set assigned staff member"), "objs": staff_members}
        )


def exec_set_quest_type(request, ctx, target, ids):
    quest_type = ctx["event"].get_elements(QuestType).get(pk=target)
    ctx["event"].get_elements(Quest).filter(pk__in=ids).update(typ=quest_type)


def handle_bulk_quest(request, ctx):
    if request.POST:
        raise ReturnNowError(exec_bulk(request, ctx, {Operations.SET_QUEST_TYPE: exec_set_quest_type}))

    quest_types = ctx["event"].get_elements(QuestType).values("id", "name").order_by("name")
    ctx["bulk"] = [
        {"idx": Operations.SET_QUEST_TYPE, "label": _("Set quest type"), "objs": quest_types},
    ]


def exec_set_quest(request, ctx, target, ids):
    quest = ctx["event"].get_elements(Quest).get(pk=target)
    ctx["event"].get_elements(Trait).filter(pk__in=ids).update(quest=quest)


def handle_bulk_trait(request, ctx):
    if request.POST:
        raise ReturnNowError(exec_bulk(request, ctx, {Operations.SET_TRAIT_QUEST: exec_set_quest}))

    quests = ctx["event"].get_elements(Quest).values("id", "name").order_by("name")
    ctx["bulk"] = [
        {"idx": Operations.SET_TRAIT_QUEST, "label": _("Set quest"), "objs": quests},
    ]


def exec_set_ability_type(request, ctx, target, ids):
    typ = ctx["event"].get_elements(AbilityTypePx).get(pk=target)
    ctx["event"].get_elements(AbilityPx).filter(pk__in=ids).update(typ=typ)


def handle_bulk_ability(request, ctx):
    if request.POST:
        raise ReturnNowError(exec_bulk(request, ctx, {Operations.SET_ABILITY_TYPE: exec_set_ability_type}))

    quests = ctx["event"].get_elements(AbilityTypePx).values("id", "name").order_by("name")
    ctx["bulk"] = [
        {"idx": Operations.SET_ABILITY_TYPE, "label": _("Set ability type"), "objs": quests},
    ]
