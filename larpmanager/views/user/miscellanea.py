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

import logging
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.miscellanea import (
    HelpQuestionForm,
    ShuttleServiceEditForm,
    ShuttleServiceForm,
)
from larpmanager.models.event import Run
from larpmanager.models.miscellanea import (
    Album,
    AlbumUpload,
    HelpQuestion,
    ShuttleService,
    ShuttleStatus,
    UrlShortner,
    Util,
    WorkshopMemberRel,
    WorkshopModule,
)
from larpmanager.models.writing import Handout
from larpmanager.utils.base import def_user_ctx, is_shuttle
from larpmanager.utils.common import get_album, get_workshop
from larpmanager.utils.event import get_event_run
from larpmanager.utils.exceptions import check_assoc_feature
from larpmanager.utils.pdf import (
    print_handout,
    return_pdf,
)

logger = logging.getLogger(__name__)


def url_short(request, s):
    el = get_object_or_404(UrlShortner, cod=s)
    return redirect(el.url)


def util(request, cod):
    try:
        u = Util.objects.get(cod=cod)
        return HttpResponseRedirect(u.download())
    except Exception as err:
        raise Http404("not found") from err


def help_red(request, n):
    ctx = def_user_ctx(request)
    ctx.update({"a_id": request.assoc["id"]})
    try:
        ctx["run"] = Run.objects.get(pk=n, event__assoc_id=ctx["a_id"])
    except ObjectDoesNotExist as err:
        raise Http404("Run does not exist") from err
    return redirect("help", s=ctx["run"].get_slug())


@login_required
def help(request: HttpRequest, s: str | None = None) -> HttpResponse:
    """
    Display help page with question submission form and user's previous questions.

    This view handles both displaying the help form and processing question submissions.
    It supports both organization-wide and event-specific help contexts.

    Args:
        request: HTTP request object containing user data and form submissions
        s: Optional event slug for event-specific help context. If None,
           displays organization-wide help.

    Returns:
        HttpResponse: Rendered help template containing the question form and
                     filtered list of user's previous questions.

    Note:
        - POST requests process form submissions and redirect on success
        - Questions are filtered by association context (event or organization)
        - Form context varies based on event slug presence
    """
    # Initialize context based on event slug presence
    if s:
        ctx = get_event_run(request, s, status=True)
    else:
        ctx = def_user_ctx(request)
        ctx["a_id"] = request.assoc["id"]

    # Process form submission for new help questions
    if request.method == "POST":
        form = HelpQuestionForm(request.POST, request.FILES, ctx=ctx)
        if form.is_valid():
            # Create question instance without saving to database yet
            hp = form.save(commit=False)
            hp.member = request.user.member

            # Associate question with current organization if available
            if ctx["a_id"] != 0:
                hp.assoc_id = ctx["a_id"]

            # Save question and redirect with success message
            hp.save()
            messages.success(request, _("Question saved!"))
            return redirect(request.path_info)
    else:
        # Initialize empty form for GET requests
        form = HelpQuestionForm(ctx=ctx)

    # Add form to context for template rendering
    ctx["form"] = form

    # Retrieve user's previous questions ordered by creation date
    ctx["list"] = HelpQuestion.objects.filter(member=request.user.member).order_by("-created")

    # Filter questions by association context
    if ctx["a_id"] != 0:
        ctx["list"] = ctx["list"].filter(assoc_id=ctx["a_id"])
    else:
        ctx["list"] = ctx["list"].filter(assoc=None)

    return render(request, "larpmanager/member/help.html", ctx)


@login_required
def help_attachment(request, p: int) -> HttpResponse:
    """
    Serve attachment file for a help question.

    Args:
        request: HTTP request object containing user information
        p: Primary key of the HelpQuestion to retrieve attachment for

    Returns:
        HttpResponse: Redirect to the attachment URL

    Raises:
        Http404: If HelpQuestion doesn't exist or user lacks access permissions
    """
    # Get user context for permission checking
    ctx = def_user_ctx(request)

    # Retrieve the help question object
    try:
        hp = HelpQuestion.objects.get(pk=p)
    except ObjectDoesNotExist as err:
        raise Http404("HelpQuestion does not exist") from err

    # Check if user has permission to access this attachment
    # Either the question owner or someone with association role
    if hp.member != request.user.member and not ctx["assoc_role"]:
        raise Http404("illegal access")

    # Redirect to the attachment file URL
    return redirect(hp.attachment.url)


def handout_ext(request, s, cod):
    ctx = get_event_run(request, s)
    ctx["handout"] = get_object_or_404(Handout, event=ctx["event"], cod=cod)
    fp = print_handout(ctx)
    return return_pdf(fp, str(ctx["handout"]))


def album_aux(request: HttpRequest, ctx: dict, parent: Album | None) -> HttpResponse:
    """Prepare album context with sub-albums and paginated uploads.

    This function builds the context for displaying an album page, including
    sub-albums and paginated uploads. It handles both root-level albums
    (when parent is None) and nested albums.

    Args:
        request: Django HTTP request object containing GET parameters
        ctx: Context dictionary to update with album data
        parent: Parent album instance for nested albums, or None for root level

    Returns:
        HttpResponse: Rendered album page template with context data

    Note:
        Pagination shows 20 uploads per page. Invalid page numbers default
        to first page, out-of-range pages default to last page.
    """
    # Fetch visible sub-albums for the current run, ordered by creation date
    ctx["subs"] = Album.objects.filter(run=ctx["run"], parent=parent, is_visible=True).order_by("-created")

    # Handle pagination for uploads only when viewing a specific album
    if parent is not None:
        # Get all uploads for the current album
        lst = AlbumUpload.objects.filter(album=ctx["album"]).order_by("-created")

        # Set up pagination with 20 items per page
        paginator = Paginator(lst, 20)
        page = request.GET.get("page")

        # Handle pagination edge cases and invalid page numbers
        try:
            lst = paginator.page(page)
        except PageNotAnInteger:
            lst = paginator.page(1)  # If page is not an integer, deliver first
        except EmptyPage:
            lst = paginator.page(
                paginator.num_pages
            )  # If page is out of range (e.g.  9999), deliver last page of results.

        # Set context for specific album view
        ctx["page"] = lst
        ctx["name"] = f"{ctx['album']} - {str(ctx['run'])}"
    else:
        # Set context for root album view
        ctx["name"] = f"Album - {str(ctx['run'])}"

    # Set parent reference and render template
    ctx["parent"] = parent
    return render(request, "larpmanager/event/album.html", ctx)


@login_required
def album(request, s):
    ctx = get_event_run(request, s)
    return album_aux(request, ctx, None)


@login_required
def album_sub(request, s, num):
    ctx = get_event_run(request, s)
    get_album(ctx, num)
    return album_aux(request, ctx, ctx["album"])


@login_required
def workshops(request: HttpRequest, s: str) -> HttpResponse:
    """Get workshops for an event and render the workshops index page.

    Args:
        request: The HTTP request object containing user information
        s: The event slug identifier

    Returns:
        HttpResponse: Rendered workshops index template with context data
    """
    # Get event context with signup and status information
    ctx = get_event_run(request, s, signup=True, status=True)

    # Initialize empty list for workshop data
    ctx["list"] = []

    # Process each workshop assigned to this event
    for workshop in ctx["event"].workshops.select_related().all().order_by("number"):
        # Get workshop display data
        dt = workshop.show()

        # Set completion check limit to 365 days ago
        limit = datetime.now() - timedelta(days=365)
        logger.debug(f"Workshop completion limit date: {limit}")

        # Check if user has completed this workshop within the time limit
        dt["done"] = (
            WorkshopMemberRel.objects.filter(member=request.user.member, workshop=workshop, created__gte=limit).count()
            >= 1
        )

        # Add workshop data to context list
        ctx["list"].append(dt)

    # Render and return the workshops index template
    return render(request, "larpmanager/event/workshops/index.html", ctx)


def valid_workshop_answer(request, ctx: dict) -> bool:
    """Validate workshop quiz answers and determine pass/fail status.

    Processes workshop quiz questions and compares user-submitted answers
    against correct answers. Updates the context with answer validation
    results for each question.

    Args:
        request: HTTP request object containing POST data with quiz answers
        ctx: Context dictionary containing workshop questions under 'list' key.
             Each question has 'id', 'opt' list with options containing
             'id' and 'is_correct' fields.

    Returns:
        bool: True if all answers are correct, False if any answer is wrong.

    Note:
        Modifies ctx in-place by adding 'correct', 'answer', and 'failed'
        fields to each question element.
    """
    res = True

    # Process each workshop question
    for el in ctx["list"]:
        el["correct"] = []
        el["answer"] = []

        # Extract correct answers and user submissions for this question
        for o in el["opt"]:
            # Collect IDs of correct options
            if o["is_correct"]:
                el["correct"].append(o["id"])

            # Check if user selected this option (POST field format: questionId_optionId)
            ix = f"{el['id']}_{o['id']}"
            if request.POST.get(ix, "") == "on":
                el["answer"].append(o["id"])

        # Sort lists for reliable comparison
        el["correct"].sort()
        el["answer"].sort()

        # Mark question as failed if answers don't match
        el["failed"] = el["correct"] != el["answer"]
        if el["failed"]:
            res = False

    return res


@login_required
def workshop_answer(request: HttpRequest, s: str, m: int) -> HttpResponse:
    """
    Handle workshop answer submission and validation.

    This function processes workshop submissions for LARP events, validates answers,
    tracks completion status, and manages progression through workshop modules.

    Args:
        request (HttpRequest): The HTTP request object containing user data and POST parameters
        s (str): Event slug identifier for the current event/run
        m (int): Workshop module number to process

    Returns:
        HttpResponse: Either a rendered template (answer form or failure page) or
                     a redirect response to next module or workshops overview

    Raises:
        Http404: If event, run, or workshop module is not found
        PermissionDenied: If user doesn't have access to the workshop
    """
    # Get event context and validate user access to workshop signup
    ctx = get_event_run(request, s, signup=True, status=True)
    get_workshop(ctx, m)

    # Check if user has already completed this workshop module
    completed = [el.pk for el in request.user.member.workshops.select_related().all()]
    if ctx["workshop"].pk in completed:
        messages.success(request, _("Workshop already done!"))
        return redirect("workshops", s=ctx["run"].get_slug())

    # Build list of questions for the current workshop module
    ctx["list"] = []
    for question in ctx["workshop"].questions.select_related().all().order_by("number"):
        ctx["list"].append(question.show())

    # For GET requests, display the workshop question form
    if request.method != "POST":
        return render(request, "larpmanager/event/workshops/answer.html", ctx)

    # Process POST request - validate submitted answers
    if valid_workshop_answer(request, ctx):
        # Create completion record for this workshop module
        WorkshopMemberRel.objects.create(member=request.user.member, workshop=ctx["workshop"])

        # Find remaining uncompleted workshop modules
        remaining = (
            WorkshopModule.objects.filter(event=ctx["event"], number__gt=ctx["workshop"].number)
            .exclude(pk__in=completed)
            .order_by("number")
        )

        # Redirect to next module or completion page based on remaining modules
        if len(remaining) > 0:
            messages.success(request, _("Completed module. Remaining: {number:d}").format(number=len(remaining)))
            return redirect(
                "workshop_answer",
                s=ctx["run"].get_slug(),
                m=remaining.first().number,
            )

        # All modules completed - redirect to workshops overview
        messages.success(request, _("Well done, you've completed all modules!"))
        return redirect("workshops", s=ctx["run"].get_slug())

    # Invalid answers - show failure page
    return render(request, "larpmanager/event/workshops/failed.html", ctx)


@login_required
def shuttle(request: HttpRequest) -> HttpResponse:
    """Display shuttle service requests for the current association.

    This view shows both active shuttle requests and recently completed ones.
    Requires the 'shuttle' feature to be enabled for the association.

    Args:
        request: The HTTP request object containing user and association data.

    Returns:
        HttpResponse: Rendered template displaying shuttle requests with context
        containing active requests, completed requests from last 5 days, and
        user permissions.
    """
    # Verify that shuttle feature is enabled for this association
    check_assoc_feature(request, "shuttle")

    # Define reference date for filtering recent completed requests (last 5 days)
    ref = datetime.now() - timedelta(days=5)

    # Initialize base context with user data
    ctx = def_user_ctx(request)

    # Add shuttle-specific data to context
    ctx.update(
        {
            # Get all active shuttle requests (excluding completed ones)
            "list": ShuttleService.objects.exclude(status=ShuttleStatus.DONE)
            .filter(assoc_id=request.assoc["id"])
            .order_by("status", "date", "time"),
            # Check if current user has shuttle permissions
            "is_shuttle": is_shuttle(request),
            # Get recently completed shuttle requests from last 5 days
            "past": ShuttleService.objects.filter(
                created__gt=ref.date(),
                status=ShuttleStatus.DONE,
                assoc_id=request.assoc["id"],
            ).order_by("status", "date", "time"),
        }
    )

    # Render template with shuttle data
    return render(request, "larpmanager/general/shuttle.html", ctx)


@login_required
def shuttle_new(request: HttpRequest) -> HttpResponse:
    """Handle creation of new shuttle service requests.

    Creates a new shuttle service request for authenticated users. Validates
    user permissions, processes form submission, and redirects on success.

    Args:
        request: The HTTP request object containing user data and form submission

    Returns:
        HttpResponse: Redirect to shuttle list on successful form submission,
                     or rendered form template for GET requests or validation errors

    Raises:
        PermissionDenied: If user lacks required 'shuttle' feature access
    """
    # Verify user has permission to access shuttle functionality
    check_assoc_feature(request, "shuttle")

    # Initialize context with default user data and association ID
    ctx = def_user_ctx(request)
    ctx.update({"a_id": request.assoc["id"]})

    if request.method == "POST":
        # Process form submission with POST data
        form = ShuttleServiceForm(request.POST, request=request, ctx=ctx)

        if form.is_valid():
            # Save form but don't commit to database yet
            el = form.save(commit=False)
            # Associate the shuttle request with current user
            el.member = request.user.member
            el.save()
            # Redirect to shuttle list after successful creation
            return redirect("shuttle")
    else:
        # Initialize empty form for GET requests
        form = ShuttleServiceForm(request=request, ctx=ctx)

    # Render form template with appropriate context
    return render(
        request,
        "larpmanager/general/writing.html",
        {"form": form, "name": _("New shuttle request")},
    )


@login_required
def shuttle_edit(request: HttpRequest, n: int) -> HttpResponse:
    """Edit existing shuttle service request.

    Args:
        request: The HTTP request object containing user data and form submission
        n: Primary key of the ShuttleService instance to edit

    Returns:
        HttpResponse: Rendered edit form template or redirect to shuttle list view
            after successful form submission and validation

    Raises:
        ShuttleService.DoesNotExist: If shuttle service with given ID doesn't exist
    """
    # Verify user has permission to access shuttle feature
    check_assoc_feature(request, "shuttle")

    # Initialize context with user data and association ID
    ctx = def_user_ctx(request)
    ctx.update({"a_id": request.assoc["id"]})

    # Retrieve the shuttle service instance to edit
    shuttle = ShuttleService.objects.get(pk=n)

    # Handle form submission (POST request)
    if request.method == "POST":
        form = ShuttleServiceEditForm(request.POST, instance=shuttle, request=request, ctx=ctx)

        # Validate form and save if valid, then redirect
        if form.is_valid():
            form.save()
            return redirect("shuttle")
    else:
        # Initialize form with existing shuttle data for GET request
        form = ShuttleServiceEditForm(instance=shuttle, request=request, ctx=ctx)

    # Render the edit form template
    return render(
        request,
        "larpmanager/general/writing.html",
        {"form": form, "name": _("Modify shuttle request")},
    )
