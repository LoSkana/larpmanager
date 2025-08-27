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

from larpmanager.models.member import Log
from larpmanager.models.miscellanea import (
    InventoryContainer,
    InventoryItem,
    InventoryTag,
)
from larpmanager.models.writing import Faction, Plot, Character
from larpmanager.utils.exceptions import ReturnJson


def _get_bulk_params(request, ctx):
    operation = int(request.POST.get("operation", "0"))
    target = int(request.POST.get("target", "0"))
    ids = [int(x) for x in request.POST.getlist("ids[]", [])]

    if not ids:
        raise ReturnJson(JsonResponse({"error": "no ids"}, status=400))

    eid = ctx["a_id"]
    if "run" in ctx:
        eid = ctx["run"].id

    Log.objects.create(
        member=request.user.member,
        cls=f"bulk {operation} {target}",
        eid=eid,
        dct={
            'operation': operation,
            'target': target,
            'ids': ids
        }
    )

    return ids, operation, target


class Operations:
    MOVE_ITEM_BOX = 1
    ADD_ITEM_TAG = 2
    DEL_ITEM_TAG = 3
    ADD_CHAR_FACT = 4
    DEL_CHAR_FACT = 5
    ADD_CHAR_PLOT = 5
    DEL_CHAR_PLOT = 7

def handle_bulk_items(request, ctx):
    if request.POST:
        raise ReturnJson(exec_bulk_items(request, ctx))

    containers = InventoryContainer.objects.filter(assoc_id=request.assoc["id"]).values("id", "name").order_by("name")
    tags = InventoryTag.objects.filter(assoc_id=request.assoc["id"]).values("id", "name").order_by("name")
    ctx["bulk"] = [
        {"idx": Operations.MOVE_ITEM_BOX, "label": _("Move to container"), "objs": containers},
        {"idx": Operations.ADD_ITEM_TAG, "label": _("Add tag"), "objs": tags},
        {"idx": Operations.DEL_ITEM_TAG, "label": _("Remove tag"), "objs": tags},
    ]

def exec_bulk_items(request, ctx):
    ids, operation, target = _get_bulk_params(request, ctx)

    try:
        if operation == Operations.ADD_ITEM_TAG:
            tag = InventoryTag.objects.get(assoc_id=request.assoc["id"], pk=target)
            tag.items.add(
                *InventoryItem.objects.filter(assoc_id=request.assoc["id"], pk__in=ids).values_list("pk", flat=True)
            )

        elif operation == Operations.DEL_ITEM_TAG:
            tag = InventoryTag.objects.get(assoc_id=request.assoc["id"], pk=target)
            tag.items.remove(
                *InventoryItem.objects.filter(assoc_id=request.assoc["id"], pk__in=ids).values_list("pk", flat=True)
            )

        elif operation == Operations.MOVE_ITEM_BOX:
            container = InventoryContainer.objects.get(assoc_id=request.assoc["id"], pk=target)
            InventoryItem.objects.filter(assoc_id=request.assoc["id"], pk__in=ids).update(container=container)

    except ObjectDoesNotExist:
        return JsonResponse({"error": "not found"}, status=400)

    return JsonResponse({"res": "ok"})

def handle_bulk_characters(request, ctx):
    if request.POST:
        raise ReturnJson(exec_bulk_characters(request))

    ctx["bulk"] = []

    if "faction" in ctx["features"]:
        factions = ctx["event"].get_elements(Faction).values("id", "name").order_by("name")
        ctx["bulk"].extend([
            {"idx": Operations.ADD_CHAR_FACT, "label": _("Add to faction"), "objs": factions},
            {"idx": Operations.DEL_CHAR_FACT, "label": _("Remove from faction"), "objs": factions},
        ])

    if "plot" in ctx["features"]:
        plots = ctx["event"].get_elements(Plot).values("id", "name").order_by("name")
        ctx["bulk"].extend([
            {"idx": Operations.ADD_CHAR_PLOT, "label": _("Add to plot"), "objs": plots},
            {"idx": Operations.DEL_CHAR_PLOT, "label": _("Remove from plot"), "objs": plots},
        ])


def exec_bulk_characters(request, ctx):
    ids, operation, target = _get_bulk_params(request, ctx)

    chars = ctx["event"].get_elements(Character).filter(pk__in=ids).values_list("pk", flat=True)

    try:
        if operation == Operations.ADD_CHAR_FACT:
            fact = ctx["event"].get_elements(Faction).get(pk=target)
            fact.items.add(*chars)

        elif operation == Operations.DEL_CHAR_FACT:
            fact = ctx["event"].get_elements(Faction).get(pk=target)
            fact.items.remove(*chars)

        if operation == Operations.ADD_CHAR_PLOT:
            plot = ctx["event"].get_elements(Plot).get(pk=target)
            plot.items.add(*chars)

        elif operation == Operations.DEL_CHAR_PLOT:
            plot = ctx["event"].get_elements(Plot).get(pk=target)
            plot.items.remove(*chars)


    except ObjectDoesNotExist:
        return JsonResponse({"error": "not found"}, status=400)

    return JsonResponse({"res": "ok"})