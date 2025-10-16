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

from datetime import datetime, timedelta
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.forms.miscellanea import (
    OneTimeAccessTokenForm,
    OneTimeContentForm,
    OrgaAlbumForm,
    OrgaProblemForm,
    UploadAlbumsForm,
    UtilForm,
    WorkshopModuleForm,
    WorkshopOptionForm,
    WorkshopQuestionForm,
)
from larpmanager.forms.warehouse import (
    OrgaWarehouseAreaForm,
    OrgaWarehouseItemAssignmentForm,
)
from larpmanager.models.miscellanea import (
    Album,
    OneTimeAccessToken,
    OneTimeContent,
    Problem,
    Util,
    WarehouseArea,
    WarehouseItem,
    WarehouseItemAssignment,
    WorkshopMemberRel,
    WorkshopModule,
    WorkshopOption,
    WorkshopQuestion,
)
from larpmanager.models.registration import Registration
from larpmanager.utils.common import get_album_cod, get_element
from larpmanager.utils.edit import orga_edit
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.miscellanea import get_warehouse_optionals, upload_albums
from larpmanager.utils.writing import writing_post


@login_required
def orga_albums(request, s):
    ctx = check_event_permission(request, s, "orga_albums")
    ctx["list"] = Album.objects.filter(run=ctx["run"]).order_by("-created")
    return render(request, "larpmanager/orga/albums.html", ctx)


@login_required
def orga_albums_edit(request, s, num):
    return orga_edit(request, s, "orga_albums", OrgaAlbumForm, num)


@login_required
def orga_albums_upload(request, s, a):
    ctx = check_event_permission(request, s, "orga_albums")
    get_album_cod(ctx, a)
    if request.method == "POST":
        form = UploadAlbumsForm(request, s.POST, request.FILES)
        if form.is_valid():
            upload_albums(ctx["album"], request.FILES["elem"])
            messages.success(request, s, _("Photos and videos successfully uploaded") + "!")
            return redirect(request, s.path_info)
    else:
        form = UploadAlbumsForm()
    ctx["form"] = form
    return render(request, "larpmanager/orga/albums_upload.html", ctx)


@login_required
def orga_utils(request, s):
    ctx = check_event_permission(request, s, "orga_utils")
    ctx["list"] = Util.objects.filter(event=ctx["event"]).order_by("number")
    return render(request, "larpmanager/orga/utils.html", ctx)


@login_required
def orga_utils_edit(request, s, num):
    return orga_edit(request, s, "orga_utils", UtilForm, num)


@login_required
def orga_workshops(request, s):
    """Display workshop completion status for registered members.

    Args:
        request: HTTP request object
        s: Event slug

    Returns:
        HttpResponse: Rendered workshops status template
    """
    ctx = check_event_permission(request, s, "orga_workshops")
    # get number of modules
    workshops = ctx["event"].workshops.all()
    limit = datetime.now() - timedelta(days=365)
    ctx["pinocchio"] = []
    ctx["list"] = []
    # count workshops done by players
    for reg in Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True):
        reg.num = 0
        for w in workshops:
            if WorkshopMemberRel.objects.filter(member=reg.member, workshop=w, created__gte=limit).count() >= 1:
                reg.num += 1
        if reg.num != len(workshops):
            ctx["pinocchio"].append(reg.member)
        ctx["list"].append(reg)
    return render(request, "larpmanager/orga/workshop/workshops.html", ctx)


@login_required
def orga_workshop_modules(request, s):
    ctx = check_event_permission(request, s, "orga_workshop_modules")
    ctx["list"] = WorkshopModule.objects.filter(event=ctx["event"]).order_by("number")
    return render(request, "larpmanager/orga/workshop/modules.html", ctx)


@login_required
def orga_workshop_modules_edit(request, s, num):
    return orga_edit(request, s, "orga_workshop_modules", WorkshopModuleForm, num)


@login_required
def orga_workshop_questions(request, s):
    ctx = check_event_permission(request, s, "orga_workshop_questions")
    if request.method == "POST":
        return writing_post(request, ctx, WorkshopQuestion, "workshop_question")
    ctx["list"] = WorkshopQuestion.objects.filter(module__event=ctx["event"]).order_by("module__number", "number")
    return render(request, "larpmanager/orga/workshop/questions.html", ctx)


@login_required
def orga_workshop_questions_edit(request, s, num):
    return orga_edit(request, s, "orga_workshop_questions", WorkshopQuestionForm, num)


@login_required
def orga_workshop_options(request, s):
    ctx = check_event_permission(request, s, "orga_workshop_options")
    if request.method == "POST":
        return writing_post(request, ctx, WorkshopOption, "workshop_option")
    ctx["list"] = WorkshopOption.objects.filter(question__module__event=ctx["event"]).order_by(
        "question__module__number", "question__number", "is_correct"
    )
    return render(request, "larpmanager/orga/workshop/options.html", ctx)


@login_required
def orga_workshop_options_edit(request, s, num):
    return orga_edit(request, s, "orga_workshop_options", WorkshopOptionForm, num)


@login_required
def orga_problems(request, s):
    ctx = check_event_permission(request, s, "orga_problems")
    ctx["list"] = Problem.objects.filter(event=ctx["event"]).order_by("status", "-severity")
    return render(request, "larpmanager/orga/problems.html", ctx)


@login_required
def orga_problems_edit(request, s, num):
    return orga_edit(request, s, "orga_problems", OrgaProblemForm, num)


@login_required
def orga_warehouse_area(request, s):
    ctx = check_event_permission(request, s, "orga_warehouse_area")
    ctx["list"] = ctx["event"].get_elements(WarehouseArea)
    return render(request, "larpmanager/orga/warehouse/area.html", ctx)


@login_required
def orga_warehouse_area_edit(request, s, num):
    return orga_edit(request, s, "orga_warehouse_area", OrgaWarehouseAreaForm, num)


@login_required
def orga_warehouse_area_assignments(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Manage warehouse area item assignments for event organizers.

    This function handles the display and management of warehouse item assignments
    for a specific warehouse area within an event. It retrieves all available items,
    calculates availability based on existing assignments, and presents them in a
    sorted order with assigned items prioritized.

    Args:
        request: Django HTTP request object containing user session and form data
        s: Event slug identifier used to locate the specific event
        num: Warehouse area ID number to identify the target warehouse area

    Returns:
        HttpResponse: Rendered warehouse area assignments page with context data
            including sorted items, assignment information, and availability status

    Raises:
        PermissionDenied: If user lacks required warehouse area permissions
        Http404: If warehouse area with specified ID does not exist
    """
    # Check user permissions and get base context with event and area data
    ctx = check_event_permission(request, s, "orga_warehouse_area")
    get_element(ctx, num, "area", WarehouseArea)

    # Configure optional warehouse display settings for quantity columns
    get_warehouse_optionals(ctx, [6, 7])
    if ctx["optionals"]["quantity"]:
        ctx["no_header_cols"] = [8, 9]

    # Retrieve all warehouse items for the association with prefetched tags
    item_all: dict[int, Any] = {}
    for item in WarehouseItem.objects.filter(assoc_id=ctx["a_id"]).prefetch_related("tags").select_related("container"):
        # Set initial availability to item's total quantity
        item.available = item.quantity or 0
        item_all[item.id] = item

    # Process existing warehouse item assignments to calculate availability
    for el in ctx["event"].get_elements(WarehouseItemAssignment).filter(event=ctx["event"]):
        item = item_all[el.item_id]

        # Mark items assigned to current area and track assignment details
        if el.area_id == ctx["area"].pk:
            item.assigned = {"quantity": el.quantity, "notes": el.notes}
        else:
            # Reduce available quantity for items assigned to other areas
            item.available -= el.quantity or 0

    def _assigned_updated(it: Any) -> Any:
        """Helper function to extract assignment update timestamp for sorting."""
        if getattr(it, "assigned", None):
            return it.assigned.get("updated") or getattr(it, "updated", None) or datetime.min
        return datetime.min

    # Sort items: assigned items first, then by recent updates, name, and ID
    ordered_items = sorted(
        item_all.values(),
        key=lambda it: (
            bool(getattr(it, "assigned", None)),  # Assigned items first (True via reverse)
            _assigned_updated(it),  # Most recently updated first (via reverse)
            getattr(it, "name", ""),  # Alphabetical name fallback
            it.id,  # Stable ID tiebreaker
        ),
        reverse=True,
    )

    # Rebuild dictionary preserving sorted order for template rendering
    ctx["item_all"] = {it.id: it for it in ordered_items}
    return render(request, "larpmanager/orga/warehouse/assignments.html", ctx)


@login_required
def orga_warehouse_checks(request, s):
    ctx = check_event_permission(request, s, "orga_warehouse_checks")
    ctx["items"] = {}
    for el in ctx["event"].get_elements(WarehouseItemAssignment).select_related("area", "item"):
        if el.item_id not in ctx["items"]:
            item = el.item
            item.assignment_list = []
            ctx["items"][el.item_id] = item
        ctx["items"][el.item_id].assignment_list.append(el)
    get_warehouse_optionals(ctx, [])
    return render(request, "larpmanager/orga/warehouse/checks.html", ctx)


@login_required
def orga_warehouse_manifest(request, s):
    ctx = check_event_permission(request, s, "orga_warehouse_manifest")
    ctx["area_list"] = {}
    get_warehouse_optionals(ctx, [])

    for el in ctx["event"].get_elements(WarehouseItemAssignment).select_related("area", "item", "item__container"):
        if el.area_id not in ctx["area_list"]:
            ctx["area_list"][el.area_id] = el.area
        if not hasattr(ctx["area_list"][el.area_id], "items"):
            ctx["area_list"][el.area_id].items = []
        ctx["area_list"][el.area_id].items.append(el)

    return render(request, "larpmanager/orga/warehouse/manifest.html", ctx)


@login_required
def orga_warehouse_assignment_item_edit(request, s, num):
    return orga_edit(request, s, "orga_warehouse_manifest", OrgaWarehouseItemAssignmentForm, num)


@require_POST
def orga_warehouse_assignment_manifest(request, s):
    """Update warehouse item assignment status via AJAX.

    Args:
        request: Django HTTP request object with POST data
        s: Event slug identifier

    Returns:
        JsonResponse with success status or error message
    """
    ctx = check_event_permission(request, s, "orga_warehouse_manifest")
    idx = request.POST.get("idx")
    type = request.POST.get("type").lower()
    value = request.POST.get("value").lower() == "true"

    try:
        assign = WarehouseItemAssignment.objects.get(pk=idx)
    except ObjectDoesNotExist:
        return JsonResponse({"error": "not found"}, status=400)

    if assign.event_id != ctx["event"].id:
        return JsonResponse({"error": "not your event"}, status=400)

    map_field = {"load": "loaded", "depl": "deployed"}
    field = map_field.get(type, "")
    setattr(assign, field, value)
    assign.save()

    return JsonResponse({"ok": True})


@require_POST
def orga_warehouse_assignment_area(request, s, num):
    """Handle warehouse item assignment to a specific area.

    Args:
        request: HTTP request object containing POST data with item assignment details
        s: Event slug identifier
        num: Area number identifier

    Returns:
        JsonResponse: Success confirmation with {"ok": True}
    """
    ctx = check_event_permission(request, s, "orga_warehouse_manifest")
    get_element(ctx, num, "area", WarehouseArea)

    idx = request.POST.get("idx")
    notes = request.POST.get("notes")
    quantity = int(request.POST.get("quantity", "0"))
    selected = request.POST.get("selected").lower() == "true"

    if not selected:
        WarehouseItemAssignment.objects.filter(item_id=idx, area=ctx["area"]).delete()
        return JsonResponse({"ok": True})

    (assign, _cr) = WarehouseItemAssignment.objects.get_or_create(item_id=idx, area=ctx["area"], event=ctx["event"])
    assign.quantity = quantity
    assign.notes = notes
    assign.save()

    return JsonResponse({"ok": True})


@login_required
def orga_onetimes(request, s):
    """List all one-time contents for an event."""
    ctx = check_event_permission(request, s, "orga_onetimes")
    ctx["list"] = OneTimeContent.objects.filter(event=ctx["event"]).order_by("-created")
    return render(request, "larpmanager/orga/onetimes.html", ctx)


@login_required
def orga_onetimes_edit(request, s, num):
    """Edit or create a one-time content."""
    return orga_edit(request, s, "orga_onetimes", OneTimeContentForm, num)


@login_required
def orga_onetimes_tokens(request, s):
    ctx = check_event_permission(request, s, "orga_onetimes")
    ctx["list"] = OneTimeAccessToken.objects.filter(content__event=ctx["event"]).order_by("-created")
    return render(request, "larpmanager/orga/onetimes_tokens.html", ctx)


@login_required
def orga_onetimes_tokens_edit(request, s, num):
    return orga_edit(request, s, "orga_onetimes_tokens", OneTimeAccessTokenForm, num)
