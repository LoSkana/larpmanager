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
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from larpmanager.cache.warehouse import get_association_warehouse_cache
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
from larpmanager.utils.core.base import check_association_context
from larpmanager.utils.edit.backend import exe_delete, exe_edit
from larpmanager.utils.services.bulk import handle_bulk_items
from larpmanager.utils.services.miscellanea import get_warehouse_optionals


@login_required
def exe_urlshortner(request: HttpRequest) -> HttpResponse:
    """Render URL shortener management page for association executives."""
    # Check user has permission to access URL shortener management
    context = check_association_context(request, "exe_urlshortner")

    # Get all URL shorteners for the current association
    context["list"] = UrlShortner.objects.filter(association_id=context["association_id"])

    return render(request, "larpmanager/exe/url_shortner.html", context)


@login_required
def exe_urlshortner_new(request: HttpRequest) -> HttpResponse:
    """Create a new URL shortener entry."""
    return exe_edit(request, ExeUrlShortnerForm, None, "exe_urlshortner")


@login_required
def exe_urlshortner_edit(request: HttpRequest, url_uuid: str) -> HttpResponse:
    """Edit an existing URL shortener entry."""
    return exe_edit(request, ExeUrlShortnerForm, url_uuid, "exe_urlshortner")


@login_required
def exe_urlshortner_delete(request: HttpRequest, url_uuid: str) -> HttpResponse:
    """Delete url."""
    return exe_delete(request, ExeUrlShortnerForm, url_uuid, "exe_urlshortner")


@login_required
def exe_warehouse_containers(request: HttpRequest) -> HttpResponse:
    """Display list of warehouse containers for the current association."""
    # Check user permissions for warehouse container management
    context = check_association_context(request, "exe_warehouse_containers")

    # Fetch all containers belonging to the current association
    context["list"] = WarehouseContainer.objects.filter(association_id=context["association_id"])

    return render(request, "larpmanager/exe/warehouse/containers.html", context)


@login_required
def exe_warehouse_containers_new(request: HttpRequest) -> HttpResponse:
    """Create a new warehouse container."""
    return exe_edit(request, ExeWarehouseContainerForm, None, "exe_warehouse_containers")


@login_required
def exe_warehouse_containers_edit(request: HttpRequest, container_uuid: str) -> HttpResponse:
    """Edit warehouse container using generic edit handler."""
    return exe_edit(request, ExeWarehouseContainerForm, container_uuid, "exe_warehouse_containers")


@login_required
def exe_warehouse_containers_delete(request: HttpRequest, container_uuid: str) -> HttpResponse:
    """Delete container."""
    return exe_delete(request, ExeWarehouseContainerForm, container_uuid, "exe_warehouse_containers")


@login_required
def exe_warehouse_tags(request: HttpRequest) -> HttpResponse:
    """Display warehouse tags for the current organization."""
    # Check user has permission to view warehouse tags
    context = check_association_context(request, "exe_warehouse_tags")

    # Fetch all tags for the organization with related items
    context["list"] = WarehouseTag.objects.filter(association_id=context["association_id"]).prefetch_related("items")

    return render(request, "larpmanager/exe/warehouse/tags.html", context)


@login_required
def exe_warehouse_tags_new(request: HttpRequest) -> HttpResponse:
    """Create a new warehouse tag."""
    return exe_edit(request, ExeWarehouseTagForm, None, "exe_warehouse_tags")


@login_required
def exe_warehouse_tags_edit(request: HttpRequest, tag_uuid: str) -> HttpResponse:
    """Edit warehouse tag via generic edit view."""
    return exe_edit(request, ExeWarehouseTagForm, tag_uuid, "exe_warehouse_tags")


@login_required
def exe_warehouse_tags_delete(request: HttpRequest, tag_uuid: str) -> HttpResponse:
    """Delete tag."""
    return exe_delete(request, ExeWarehouseTagForm, tag_uuid, "exe_warehouse_tags")


@login_required
def exe_warehouse_items(request: HttpRequest) -> HttpResponse:
    """Display warehouse items for organization administrators."""
    # Check user permissions for warehouse management
    context = check_association_context(request, "exe_warehouse_items")

    # Handle any bulk operations on items
    handle_bulk_items(request, context)

    warehouse_cache = get_association_warehouse_cache(context["association_id"])

    # Get warehouse items for current association with related data
    items = WarehouseItem.objects.filter(association_id=context["association_id"])
    items = items.select_related("container").prefetch_related("tags")

    # Attach cached tags to each item
    items_list = []
    for item in items:
        if item.id in warehouse_cache:
            item.tags_cached = warehouse_cache[item.id]["tags"]
        else:
            item.tags_cached = []
        items_list.append(item)
    context["list"] = items_list

    # Add optional warehouse context data
    get_warehouse_optionals(context, [5])

    return render(request, "larpmanager/exe/warehouse/items.html", context)


@login_required
def exe_warehouse_items_new(request: HttpRequest) -> HttpResponse:
    """Create a new warehouse item."""
    return exe_edit(request, ExeWarehouseItemForm, None, "exe_warehouse_items")


@login_required
def exe_warehouse_items_edit(request: HttpRequest, item_uuid: str) -> HttpResponse:
    """Delegate to exe_edit for warehouse item form handling."""
    return exe_edit(request, ExeWarehouseItemForm, item_uuid, "exe_warehouse_items")


@login_required
def exe_warehouse_items_delete(request: HttpRequest, item_uuid: str) -> HttpResponse:
    """Delete item."""
    return exe_delete(request, ExeWarehouseItemForm, item_uuid, "exe_warehouse_items")


@login_required
def exe_warehouse_movements(request: HttpRequest) -> HttpResponse:
    """Render warehouse movements list for association."""
    # Check permissions and initialize context
    context = check_association_context(request, "exe_warehouse_movements")

    # Fetch movements with item details
    context["list"] = WarehouseMovement.objects.filter(association_id=context["association_id"]).select_related("item")

    # Add optional warehouse fields
    get_warehouse_optionals(context, [3])

    return render(request, "larpmanager/exe/warehouse/movements.html", context)


@login_required
def exe_warehouse_movements_new(request: HttpRequest) -> HttpResponse:
    """Create a new warehouse movement."""
    return exe_edit(request, ExeWarehouseMovementForm, None, "exe_warehouse_movements")


@login_required
def exe_warehouse_movements_edit(request: HttpRequest, movement_uuid: str) -> HttpResponse:
    """Edit a specific warehouse movement by delegating to the generic exe_edit view."""
    return exe_edit(request, ExeWarehouseMovementForm, movement_uuid, "exe_warehouse_movements")


@login_required
def exe_warehouse_movements_delete(request: HttpRequest, movement_uuid: str) -> HttpResponse:
    """Delete movement."""
    return exe_delete(request, ExeWarehouseMovementForm, movement_uuid, "exe_warehouse_movements")
