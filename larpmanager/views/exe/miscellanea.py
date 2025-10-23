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
from django.http import HttpResponse
from django.shortcuts import render

from larpmanager.forms.miscellanea import ExeUrlShortnerForm
from larpmanager.forms.warehouse import (
    ExeWarehouseContainerForm,
    ExeWarehouseItemForm,
    ExeWarehouseMovementForm,
    ExeWarehouseTagForm,
)
from larpmanager.models.miscellanea import (
    UrlShortner,
    WarehouseContainer,
    WarehouseItem,
    WarehouseMovement,
    WarehouseTag,
)
from larpmanager.utils.base import check_assoc_permission
from larpmanager.utils.bulk import handle_bulk_items
from larpmanager.utils.edit import exe_edit
from larpmanager.utils.miscellanea import get_warehouse_optionals


@login_required
def exe_urlshortner(request):
    ctx = check_assoc_permission(request, "exe_urlshortner")
    ctx["list"] = UrlShortner.objects.filter(assoc_id=request.assoc["id"])
    return render(request, "larpmanager/exe/url_shortner.html", ctx)


@login_required
def exe_urlshortner_edit(request, num):
    return exe_edit(request, ExeUrlShortnerForm, num, "exe_urlshortner")


@login_required
def exe_warehouse_containers(request):
    ctx = check_assoc_permission(request, "exe_warehouse_containers")
    ctx["list"] = WarehouseContainer.objects.filter(assoc_id=request.assoc["id"])
    return render(request, "larpmanager/exe/warehouse/containers.html", ctx)


@login_required
def exe_warehouse_containers_edit(request, num):
    return exe_edit(request, ExeWarehouseContainerForm, num, "exe_warehouse_containers")


@login_required
def exe_warehouse_tags(request):
    ctx = check_assoc_permission(request, "exe_warehouse_tags")
    ctx["list"] = WarehouseTag.objects.filter(assoc_id=request.assoc["id"]).prefetch_related("items")
    return render(request, "larpmanager/exe/warehouse/tags.html", ctx)


@login_required
def exe_warehouse_tags_edit(request, num):
    return exe_edit(request, ExeWarehouseTagForm, num, "exe_warehouse_tags")


@login_required
def exe_warehouse_items(request) -> HttpResponse:
    """Display warehouse items for organization administrators."""
    # Check user permissions for warehouse management
    ctx = check_assoc_permission(request, "exe_warehouse_items")

    # Handle any bulk operations on items
    handle_bulk_items(request, ctx)

    # Get warehouse items for current association with related data
    ctx["list"] = WarehouseItem.objects.filter(assoc_id=request.assoc["id"])
    ctx["list"] = ctx["list"].select_related("container").prefetch_related("tags")

    # Add optional warehouse context data
    get_warehouse_optionals(ctx, [5])

    return render(request, "larpmanager/exe/warehouse/items.html", ctx)


@login_required
def exe_warehouse_items_edit(request, num):
    return exe_edit(request, ExeWarehouseItemForm, num, "exe_warehouse_items")


@login_required
def exe_warehouse_movements(request):
    ctx = check_assoc_permission(request, "exe_warehouse_movements")
    ctx["list"] = WarehouseMovement.objects.filter(assoc_id=request.assoc["id"]).select_related("item")
    get_warehouse_optionals(ctx, [3])
    return render(request, "larpmanager/exe/warehouse/movements.html", ctx)


@login_required
def exe_warehouse_movements_edit(request, num):
    return exe_edit(request, ExeWarehouseMovementForm, num, "exe_warehouse_movements")
