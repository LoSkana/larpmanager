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

from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _

from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.experience import AbilityPx, AbilityTypePx, DeliveryPx
from larpmanager.models.member import Log
from larpmanager.models.miscellanea import (
    WarehouseContainer,
    WarehouseItem,
    WarehouseTag,
)
from larpmanager.models.writing import Character, Faction, Plot, Prologue
from larpmanager.utils.exceptions import ReturnNowError


def _get_bulk_params(request, ctx):
    """
    Extract and validate bulk operation parameters from request.

    Args:
        request: HTTP request object
        ctx: Context dictionary with event/run information

    Returns:
        tuple: (ids, operation, target) extracted from request

    Raises:
        ReturnNowError: If no valid IDs are provided
    """
    try:
        operation = int(request.POST.get("operation", "0"))
    except (ValueError, TypeError):
        operation = 0

    try:
        target = int(request.POST.get("target", "0"))
    except (ValueError, TypeError):
        target = 0

    ids = []
    for x in request.POST.getlist("ids[]", []):
        try:
            ids.append(int(x))
        except (ValueError, TypeError):
            continue

    if not ids:
        raise ReturnNowError(JsonResponse({"error": "no ids"}, status=400))

    eid = ctx["a_id"]
    if "run" in ctx:
        eid = ctx["run"].id

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


def exec_bulk(request, ctx, mapping):
    ids, operation, target = _get_bulk_params(request, ctx)
    if operation not in mapping:
        return JsonResponse({"error": "unknow operation"}, status=400)

    try:
        mapping[operation](request, ctx, target, ids)
    except ObjectDoesNotExist:
        return JsonResponse({"error": "not found"}, status=400)

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


def handle_bulk_items(request, ctx):
    """Handle bulk operations on warehouse items.

    Args:
        request: HTTP request object containing operation data
        ctx: Context dictionary to update with bulk operation choices

    Raises:
        ReturnNowError: If POST request processed successfully
    """
    if request.POST:
        mapping = {
            Operations.ADD_ITEM_TAG: exec_add_item_tag,
            Operations.DEL_ITEM_TAG: exec_del_item_tag,
            Operations.MOVE_ITEM_BOX: exec_move_item_box,
        }
        raise ReturnNowError(exec_bulk(request, ctx, mapping))

    containers = WarehouseContainer.objects.filter(assoc_id=request.assoc["id"]).values("id", "name").order_by("name")
    tags = WarehouseTag.objects.filter(assoc_id=request.assoc["id"]).values("id", "name").order_by("name")
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


def handle_bulk_characters(request, ctx):
    """Process bulk operations on character objects.

    Handles mass character modifications, faction assignments, and other
    batch character management tasks for efficient character administration.

    Args:
        request: Django HTTP request object containing POST data with operation details
        ctx (dict): Context dictionary containing event and selection data

    Returns:
        None: Function modifies ctx in-place, adding operation results and status messages
    """
    if request.POST:
        mapping = {
            Operations.ADD_CHAR_FACT: exec_add_char_fact,
            Operations.DEL_CHAR_FACT: exec_del_char_fact,
            Operations.ADD_CHAR_PLOT: exec_add_char_plot,
            Operations.DEL_CHAR_PLOT: exec_del_char_plot,
            Operations.ADD_CHAR_DELIVERY: exec_add_char_delivery,
            Operations.DEL_CHAR_DELIVERY: exec_del_char_delivery,
            Operations.ADD_CHAR_PROLOGUE: exec_add_char_prologue,
            Operations.DEL_CHAR_PROLOGUE: exec_add_char_prologue,
        }
        raise ReturnNowError(exec_bulk(request, ctx, mapping))

    ctx["bulk"] = []

    if "faction" in ctx["features"]:
        factions = ctx["event"].get_elements(Faction).values("id", "name").order_by("name")
        ctx["bulk"].extend(
            [
                {"idx": Operations.ADD_CHAR_FACT, "label": _("Add to faction"), "objs": factions},
                {"idx": Operations.DEL_CHAR_FACT, "label": _("Remove from faction"), "objs": factions},
            ]
        )

    if "plot" in ctx["features"]:
        plots = ctx["event"].get_elements(Plot).values("id", "name").order_by("name")
        ctx["bulk"].extend(
            [
                {"idx": Operations.ADD_CHAR_PLOT, "label": _("Add to plot"), "objs": plots},
                {"idx": Operations.DEL_CHAR_PLOT, "label": _("Remove from plot"), "objs": plots},
            ]
        )

    if "prologue" in ctx["features"]:
        prologues = ctx["event"].get_elements(Prologue).values("id", "name").order_by("name")
        ctx["bulk"].extend(
            [
                {"idx": Operations.ADD_CHAR_PROLOGUE, "label": _("Add prologue"), "objs": prologues},
                {"idx": Operations.DEL_CHAR_PROLOGUE, "label": _("Remove prologue"), "objs": prologues},
            ]
        )

    if "px" in ctx["features"]:
        delivery = ctx["event"].get_elements(DeliveryPx).values("id", "name")
        ctx["bulk"].extend(
            [
                {"idx": Operations.ADD_CHAR_DELIVERY, "label": _("Add to xp delivery"), "objs": delivery},
                {"idx": Operations.DEL_CHAR_DELIVERY, "label": _("Remove from xp delivery"), "objs": delivery},
            ]
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
