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
from larpmanager.utils.base import check_event_context
from larpmanager.utils.common import get_album_cod, get_element
from larpmanager.utils.edit import orga_edit
from larpmanager.utils.miscellanea import get_warehouse_optionals, upload_albums
from larpmanager.utils.writing import writing_post


@login_required
def orga_albums(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display albums for an event run in the organizer dashboard."""
    context = check_event_context(request, event_slug, "orga_albums")
    context["list"] = Album.objects.filter(run=context["run"]).order_by("-created")
    return render(request, "larpmanager/orga/albums.html", context)


@login_required
def orga_albums_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_albums", OrgaAlbumForm, num)


@login_required
def orga_albums_upload(request: HttpRequest, event_slug: str, a: str) -> HttpResponse:
    """Upload photos and videos to an event album.

    Args:
        request: The HTTP request object containing user data and files
        event_slug: Event slug identifier
        a: The album code/identifier string

    Returns:
        HttpResponse: Rendered upload form or redirect after successful upload

    Raises:
        PermissionDenied: If user lacks orga_albums permission for the event
    """
    # Check user permissions and get event context
    context = check_event_context(request, event_slug, "orga_albums")

    # Retrieve and validate the album using the provided code
    get_album_cod(context, a)

    # Handle POST request for file upload
    if request.method == "POST":
        # Create form with uploaded files and POST data
        form = UploadAlbumsForm(request, event_slug.POST, request.FILES)

        # Validate form data and process upload
        if form.is_valid():
            # Upload files to the specified album
            upload_albums(context["album"], request.FILES["elem"])

            # Show success message and redirect to same page
            messages.success(request, event_slug, _("Photos and videos successfully uploaded") + "!")
            return redirect(request, event_slug.path_info)
    else:
        # Create empty form for GET request
        form = UploadAlbumsForm()

    # Add form to context and render upload template
    context["form"] = form
    return render(request, "larpmanager/orga/albums_upload.html", context)


@login_required
def orga_utils(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render utility items management page for event organizers."""
    context = check_event_context(request, event_slug, "orga_utils")
    context["list"] = Util.objects.filter(event=context["event"]).order_by("number")
    return render(request, "larpmanager/orga/utils.html", context)


@login_required
def orga_utils_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_utils", UtilForm, num)


@login_required
def orga_workshops(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display workshop completion status for registered members.

    Shows which registered members have completed all required workshops within
    the last 365 days. Members who haven't completed all workshops are flagged
    in the 'pinocchio' list.

    Args:
        request: HTTP request object containing user session and data
        event_slug: Event slug identifier used to locate the specific event

    Returns:
        HttpResponse: Rendered template showing workshop completion status
            with context containing workshop data and member completion info
    """
    # Check user permissions and get event context
    context = check_event_context(request, event_slug, "orga_workshops")

    # Get all workshops for this event
    workshops = context["event"].workshops.all()

    # Set time limit for workshop completion (365 days ago)
    limit = datetime.now() - timedelta(days=365)

    # Initialize context lists for template rendering
    context["pinocchio"] = []  # Members who haven't completed all workshops
    context["list"] = []  # All registered members with completion counts

    # Process each active registration for the event run
    for reg in Registration.objects.filter(run=context["run"], cancellation_date__isnull=True):
        # Count completed workshops for this member
        reg.num = 0
        for w in workshops:
            # Check if member completed this workshop within time limit
            if WorkshopMemberRel.objects.filter(member=reg.member, workshop=w, created__gte=limit).count() >= 1:
                reg.num += 1

        # Add member to pinocchio list if they haven't completed all workshops
        if reg.num != len(workshops):
            context["pinocchio"].append(reg.member)

        # Add registration to main list with completion count
        context["list"].append(reg)

    return render(request, "larpmanager/orga/workshop/workshops.html", context)


@login_required
def orga_workshop_modules(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display workshop modules for event organizers.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier

    Returns:
        Rendered workshop modules page
    """
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_workshop_modules")

    # Retrieve and order workshop modules
    context["list"] = WorkshopModule.objects.filter(event=context["event"]).order_by("number")

    return render(request, "larpmanager/orga/workshop/modules.html", context)


@login_required
def orga_workshop_modules_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_workshop_modules", WorkshopModuleForm, num)


@login_required
def orga_workshop_questions(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Handle workshop questions management for organizers."""
    # Check user permissions for workshop questions management
    context = check_event_context(request, event_slug, "orga_workshop_questions")

    # Process POST requests for creating/updating questions
    if request.method == "POST":
        return writing_post(request, context, WorkshopQuestion, "workshop_question")

    # Retrieve and order workshop questions by module and question number
    context["list"] = WorkshopQuestion.objects.filter(module__event=context["event"]).order_by(
        "module__number", "number"
    )

    return render(request, "larpmanager/orga/workshop/questions.html", context)


@login_required
def orga_workshop_questions_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_workshop_questions", WorkshopQuestionForm, num)


@login_required
def orga_workshop_options(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Handle workshop options management for organizers.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier

    Returns:
        Rendered template response or POST redirect
    """
    # Check user permissions for workshop options management
    context = check_event_context(request, event_slug, "orga_workshop_options")

    # Handle POST requests for creating/updating workshop options
    if request.method == "POST":
        return writing_post(request, context, WorkshopOption, "workshop_option")

    # Fetch and order workshop options for the event
    context["list"] = WorkshopOption.objects.filter(question__module__event=context["event"]).order_by(
        "question__module__number", "question__number", "is_correct"
    )

    # Render the workshop options template
    return render(request, "larpmanager/orga/workshop/options.html", context)


@login_required
def orga_workshop_options_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_workshop_options", WorkshopOptionForm, num)


@login_required
def orga_problems(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display filterable list of reported problems for an event."""
    # Check event access permissions
    context = check_event_context(request, event_slug, "orga_problems")

    # Fetch problems ordered by status and severity
    context["list"] = Problem.objects.filter(event=context["event"]).order_by("status", "-severity")

    return render(request, "larpmanager/orga/problems.html", context)


@login_required
def orga_problems_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_problems", OrgaProblemForm, num)


@login_required
def orga_warehouse_area(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render warehouse area management page for event organizers."""
    # Check organizer permissions and get event context
    context = check_event_context(request, event_slug, "orga_warehouse_area")

    # Retrieve all warehouse areas for the event
    context["list"] = context["event"].get_elements(WarehouseArea)

    return render(request, "larpmanager/orga/warehouse/area.html", context)


@login_required
def orga_warehouse_area_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_warehouse_area", OrgaWarehouseAreaForm, num)


@login_required
def orga_warehouse_area_assignments(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Manage warehouse area item assignments for event organizers.

    This function handles the display and management of warehouse item assignments
    for a specific warehouse area within an event. It retrieves all available items,
    calculates availability based on existing assignments, and presents them in a
    sorted order with assigned items prioritized.

    Args:
        request: Django HTTP request object containing user session and form data
        event_slug: Event slug identifier used to locate the specific event
        num: Warehouse area ID number to identify the target warehouse area

    Returns:
        HttpResponse: Rendered warehouse area assignments page with context data
            including sorted items, assignment information, and availability status

    Raises:
        PermissionDenied: If user lacks required warehouse area permissions
        Http404: If warehouse area with specified ID does not exist
    """
    # Check user permissions and get base context with event and area data
    context = check_event_context(request, event_slug, "orga_warehouse_area")
    get_element(context, num, "area", WarehouseArea)

    # Configure optional warehouse display settings for quantity columns
    get_warehouse_optionals(context, [6, 7])
    if context["optionals"]["quantity"]:
        context["no_header_cols"] = [8, 9]

    # Retrieve all warehouse items for the association with prefetched tags
    item_all: dict[int, Any] = {}
    for item in (
        WarehouseItem.objects.filter(association_id=context["association_id"])
        .prefetch_related("tags")
        .select_related("container")
    ):
        # Set initial availability to item's total quantity
        item.available = item.quantity or 0
        item_all[item.id] = item

    # Process existing warehouse item assignments to calculate availability
    for el in context["event"].get_elements(WarehouseItemAssignment).filter(event=context["event"]):
        item = item_all[el.item_id]

        # Mark items assigned to current area and track assignment details
        if el.area_id == context["area"].pk:
            item.assigned = {"quantity": el.quantity, "notes": el.notes}
        else:
            # Reduce available quantity for items assigned to other areas
            item.available -= el.quantity or 0

    def _assigned_updated(assignment_item: Any) -> Any:
        """Helper function to extract assignment update timestamp for sorting."""
        if getattr(assignment_item, "assigned", None):
            return assignment_item.assigned.get("updated") or getattr(assignment_item, "updated", None) or datetime.min
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
    context["item_all"] = {it.id: it for it in ordered_items}
    return render(request, "larpmanager/orga/warehouse/assignments.html", context)


@login_required
def orga_warehouse_checks(request, event_slug: str) -> HttpResponse:
    """
    Display warehouse item assignments for organization event management.

    Args:
        request: The HTTP request object containing user session and data
        event_slug: Event identifier string for the specific event

    Returns:
        HttpResponse: Rendered template with warehouse items and their assignments
    """
    # Check user permissions for warehouse management in this event
    context = check_event_context(request, event_slug, "orga_warehouse_checks")

    # Initialize items dictionary to store warehouse items with assignments
    context["items"] = {}

    # Iterate through all warehouse item assignments for this event
    for el in context["event"].get_elements(WarehouseItemAssignment).select_related("area", "item"):
        # Check if item is already in our items dictionary
        if el.item_id not in context["items"]:
            # First time seeing this item, initialize it with empty assignment list
            item = el.item
            item.assignment_list = []
            context["items"][el.item_id] = item

        # Add this assignment to the item's assignment list
        context["items"][el.item_id].assignment_list.append(el)

    # Add warehouse optional configurations to context
    get_warehouse_optionals(context, [])

    # Render the warehouse checks template with populated context
    return render(request, "larpmanager/orga/warehouse/checks.html", context)


@login_required
def orga_warehouse_manifest(request: HttpRequest, event_slug: str) -> HttpResponse:
    """
    Generate a warehouse manifest view for an organization event.

    This function creates a manifest of warehouse items organized by area
    for the specified event. It checks permissions, retrieves warehouse
    item assignments, and groups them by their assigned areas.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: Event identifier string as a string

    Returns:
        HttpResponse: Rendered template response with warehouse manifest data

    Raises:
        PermissionDenied: If user lacks orga_warehouse_manifest permission
    """
    # Check user permissions and get base context for the event
    context = check_event_context(request, event_slug, "orga_warehouse_manifest")

    # Initialize empty area list and get warehouse optional configurations
    context["area_list"] = {}
    get_warehouse_optionals(context, [])

    # Iterate through warehouse item assignments for this event
    # Group items by their assigned areas for manifest organization
    for el in context["event"].get_elements(WarehouseItemAssignment).select_related("area", "item", "item__container"):
        # Create area entry if it doesn't exist in the area list
        if el.area_id not in context["area_list"]:
            context["area_list"][el.area_id] = el.area

        # Initialize items list for the area if not already present
        if not hasattr(context["area_list"][el.area_id], "items"):
            context["area_list"][el.area_id].items = []

        # Add the warehouse item assignment to the area's items list
        context["area_list"][el.area_id].items.append(el)

    # Render the warehouse manifest template with organized data
    return render(request, "larpmanager/orga/warehouse/manifest.html", context)


@login_required
def orga_warehouse_assignment_item_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_warehouse_manifest", OrgaWarehouseItemAssignmentForm, num)


@require_POST
def orga_warehouse_assignment_manifest(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Update warehouse item assignment status via AJAX.

    This function handles AJAX requests to update the loaded/deployed status
    of warehouse item assignments for a specific event. It validates permissions,
    retrieves the assignment, and updates the appropriate field.

    Args:
        request: Django HTTP request object containing POST data with:
            - idx: Primary key of the WarehouseItemAssignment
            - type: Field type to update ('load' or 'depl')
            - value: Boolean value as string ('true'/'false')
        event_slug: Event slug identifier for permission checking

    Returns:
        JsonResponse: Contains either success confirmation or error message
            - Success: {"ok": True}
            - Error: {"error": "description"} with appropriate HTTP status

    Raises:
        ObjectDoesNotExist: When assignment with given idx doesn't exist
    """
    # Check user permissions for warehouse manifest access
    context = check_event_context(request, event_slug, "orga_warehouse_manifest")

    # Extract and validate POST parameters
    idx = request.POST.get("idx")
    type = request.POST.get("type").lower()
    value = request.POST.get("value").lower() == "true"

    # Retrieve the warehouse item assignment
    try:
        assign = WarehouseItemAssignment.objects.get(pk=idx)
    except ObjectDoesNotExist:
        return JsonResponse({"error": "not found"}, status=400)

    # Verify assignment belongs to the current event
    if assign.event_id != context["event"].id:
        return JsonResponse({"error": "not your event"}, status=400)

    # Map request type to model field and update
    map_field = {"load": "loaded", "depl": "deployed"}
    field = map_field.get(type, "")
    setattr(assign, field, value)
    assign.save()

    return JsonResponse({"ok": True})


@require_POST
def orga_warehouse_assignment_area(request: HttpRequest, event_slug: str, num: str) -> JsonResponse:
    """Handle warehouse item assignment to a specific area.

    Manages the assignment of warehouse items to specific areas within an event.
    Supports both adding new assignments and removing existing ones based on selection state.

    Args:
        request (HttpRequest): HTTP request object containing POST data with item assignment details
        s (str): Event slug identifier
        num (str): Area number identifier

    Returns:
        JsonResponse: Success confirmation with {"ok": True}

    Raises:
        ValidationError: If required permissions are not met or area doesn't exist
    """
    # Check event permissions and retrieve the warehouse area
    context = check_event_context(request, event_slug, "orga_warehouse_manifest")
    get_element(context, num, "area", WarehouseArea)

    # Extract assignment parameters from POST data
    idx = request.POST.get("idx")
    notes = request.POST.get("notes")
    quantity = int(request.POST.get("quantity", "0"))
    selected = request.POST.get("selected").lower() == "true"

    # Handle item deselection - remove existing assignment
    if not selected:
        WarehouseItemAssignment.objects.filter(item_id=idx, area=context["area"]).delete()
        return JsonResponse({"ok": True})

    # Handle item selection - create or update assignment
    (assign, _cr) = WarehouseItemAssignment.objects.get_or_create(
        item_id=idx, area=context["area"], event=context["event"]
    )
    assign.quantity = quantity
    assign.notes = notes
    assign.save()

    return JsonResponse({"ok": True})


@login_required
def orga_onetimes(request, event_slug):
    """List all one-time contents for an event."""
    context = check_event_context(request, event_slug, "orga_onetimes")
    context["list"] = OneTimeContent.objects.filter(event=context["event"]).order_by("-created")
    return render(request, "larpmanager/orga/onetimes.html", context)


@login_required
def orga_onetimes_edit(request, event_slug, num):
    """Edit or create a one-time content."""
    return orga_edit(request, event_slug, "orga_onetimes", OneTimeContentForm, num)


@login_required
def orga_onetimes_tokens(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display one-time access tokens for an event.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier

    Returns:
        Rendered template with token list
    """
    # Check user has permission to view one-time tokens for this event
    context = check_event_context(request, event_slug, "orga_onetimes")

    # Fetch all tokens for the event, ordered by creation date
    context["list"] = OneTimeAccessToken.objects.filter(content__event=context["event"]).order_by("-created")

    return render(request, "larpmanager/orga/onetimes_tokens.html", context)


@login_required
def orga_onetimes_tokens_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_onetimes_tokens", OneTimeAccessTokenForm, num)
