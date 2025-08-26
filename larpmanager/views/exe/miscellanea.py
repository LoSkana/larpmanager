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

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from larpmanager.forms.inventory import (
    ExeInventoryContainerForm,
    ExeInventoryItemForm,
    ExeInventoryMovementForm,
    ExeInventoryTagForm,
)
from larpmanager.forms.miscellanea import (
    ExeUrlShortnerForm,
)
from larpmanager.models.miscellanea import (
    InventoryContainer,
    InventoryItem,
    InventoryMovement,
    InventoryTag,
    UrlShortner,
)
from larpmanager.utils.base import check_assoc_permission
from larpmanager.utils.edit import exe_edit
from larpmanager.utils.miscellanea import get_inventory_optionals


@login_required
def exe_urlshortner(request):
    ctx = check_assoc_permission(request, "exe_urlshortner")
    ctx["list"] = UrlShortner.objects.filter(assoc_id=request.assoc["id"])
    return render(request, "larpmanager/exe/url_shortner.html", ctx)


@login_required
def exe_urlshortner_edit(request, num):
    return exe_edit(request, ExeUrlShortnerForm, num, "exe_urlshortner")


@login_required
def exe_inventory_containers(request):
    ctx = check_assoc_permission(request, "exe_inventory_containers")
    ctx["list"] = InventoryContainer.objects.filter(assoc_id=request.assoc["id"])
    return render(request, "larpmanager/exe/inventory/containers.html", ctx)


@login_required
def exe_inventory_containers_edit(request, num):
    return exe_edit(request, ExeInventoryContainerForm, num, "exe_inventory_containers")


@login_required
def exe_inventory_tags(request):
    ctx = check_assoc_permission(request, "exe_inventory_tags")
    ctx["list"] = InventoryTag.objects.filter(assoc_id=request.assoc["id"])
    return render(request, "larpmanager/exe/inventory/tags.html", ctx)


@login_required
def exe_inventory_tags_edit(request, num):
    return exe_edit(request, ExeInventoryTagForm, num, "exe_inventory_tags")


@login_required
def exe_inventory_items(request):
    ctx = check_assoc_permission(request, "exe_inventory_items")
    ctx["list"] = InventoryItem.objects.filter(assoc_id=request.assoc["id"])
    ctx["list"] = ctx["list"].select_related("container").prefetch_related("tags")
    get_inventory_optionals(ctx, [5])
    ctx["bulk"] = 1
    return render(request, "larpmanager/exe/inventory/items.html", ctx)


@login_required
def exe_inventory_items_edit(request, num):
    return exe_edit(request, ExeInventoryItemForm, num, "exe_inventory_items")


@login_required
def exe_inventory_movements(request):
    ctx = check_assoc_permission(request, "exe_inventory_movements")
    ctx["list"] = InventoryMovement.objects.filter(assoc_id=request.assoc["id"]).select_related("item")
    get_inventory_optionals(ctx, [3])
    return render(request, "larpmanager/exe/inventory/movements.html", ctx)


@login_required
def exe_inventory_movements_edit(request, num):
    return exe_edit(request, ExeInventoryMovementForm, num, "exe_inventory_movements")
