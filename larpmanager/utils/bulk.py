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

from larpmanager.models.miscellanea import (
    InventoryContainer,
    InventoryItem,
    InventoryTag,
)


class Operations:
    MOVE_ITEM_BOX = 1
    ADD_ITEM_TAG = 2
    DEL_ITEM_TAG = 3


def prepare_bulk_items(request, ctx):
    containers = InventoryContainer.objects.filter(assoc_id=request.assoc["id"]).values("id", "name").order_by("name")
    tags = InventoryTag.objects.filter(assoc_id=request.assoc["id"]).values("id", "name").order_by("name")
    ctx["bulk"] = [
        {"idx": Operations.MOVE_ITEM_BOX, "label": _("Move to container"), "objs": containers},
        {"idx": Operations.ADD_ITEM_TAG, "label": _("Add tag"), "objs": tags},
        {"idx": Operations.DEL_ITEM_TAG, "label": _("Remove tag"), "objs": tags},
    ]


def handle_bulk_items(request, ctx):
    operation = int(request.POST.get("operation", "0"))
    target = int(request.POST.get("target", "0"))
    ids = [int(x) for x in request.POST.getlist("ids[]", [])]

    if not ids:
        return JsonResponse({"error": "no ids"}, status=400)

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
