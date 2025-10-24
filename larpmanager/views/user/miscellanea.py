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
from typing import Optional

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
from larpmanager.utils.base import def_user_context, is_shuttle
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


def help_red(request: HttpRequest, n: int) -> HttpResponseRedirect:
    """Redirect to help page for a specific run."""
    # Set up context with user data and association ID
    ctx = def_user_context(request)

    # Get the run object or raise 404 if not found
    try:
        ctx["run"] = Run.objects.get(pk=n, event__assoc_id=ctx["a_id"])
    except ObjectDoesNotExist as err:
        raise Http404("Run does not exist") from err

    # Redirect to help page with run slug
    return redirect("help", s=ctx["run"].get_slug())


@login_required
def help(request: HttpRequest, s: Optional[str] = None) -> HttpResponse:
    """
    Display help page with question submission form and user's previous questions.

    Args:
        request: HTTP request object containing user session and form data
        s: Optional event slug for event-specific help context

    Returns:
        HttpResponse: Rendered help template with form and question list

    Raises:
        Http404: When event slug is provided but event/run not found
    """
    # Initialize context based on whether this is event-specific or general help
    if s:
        ctx = get_event_run(request, s, include_status=True)
    else:
        ctx = def_user_context(request)
        ctx["a_id"] = request.assoc["id"]

    # Handle form submission for new help questions
    if request.method == "POST":
        form = HelpQuestionForm(request.POST, request.FILES, ctx=ctx)
        if form.is_valid():
            # Create help question instance without saving to database yet
            hp = form.save(commit=False)
            hp.member = request.user.member

            # Associate question with organization if context is available
            if ctx["a_id"] != 0:
                hp.assoc_id = ctx["a_id"]

            # Save question and redirect to prevent form resubmission
            hp.save()
            messages.success(request, _("Question saved!"))
            return redirect(request.path_info)
    else:
        # Display empty form for GET requests
        form = HelpQuestionForm(ctx=ctx)

    # Prepare template context with form and user's question history
    ctx["form"] = form
    ctx["list"] = HelpQuestion.objects.filter(member=request.user.member).order_by("-created")

    # Filter questions by association context
    if ctx["a_id"] != 0:
        ctx["list"] = ctx["list"].filter(assoc_id=ctx["a_id"])
    else:
        ctx["list"] = ctx["list"].filter(assoc=None)

    return render(request, "larpmanager/member/help.html", ctx)


@login_required
def help_attachment(request: HttpRequest, p: int) -> HttpResponseRedirect:
    """
    Handle attachment download for help questions.

    Validates user permissions and redirects to the attachment URL if authorized.
    Only the question owner or users with association role can access attachments.

    Args:
        request: The HTTP request object containing user information
        p: Primary key of the HelpQuestion to get attachment from

    Returns:
        HttpResponseRedirect: Redirect to the attachment URL

    Raises:
        Http404: If HelpQuestion doesn't exist or user lacks permissions
    """
    # Get default user context with permissions
    ctx = def_user_context(request)

    # Attempt to retrieve the help question by primary key
    try:
        hp = HelpQuestion.objects.get(pk=p)
    except ObjectDoesNotExist as err:
        raise Http404("HelpQuestion does not exist") from err

    # Check access permissions: owner or association role required
    if hp.member != request.user.member and not ctx["assoc_role"]:
        raise Http404("illegal access")

    # Redirect to attachment URL for authorized users
    return redirect(hp.attachment.url)


def handout_ext(request: HttpRequest, s: str, cod: str) -> HttpResponse:
    """Generate and return a PDF for a specific event handout.

    Args:
        request: HTTP request object
        s: Event slug identifier
        cod: Handout code identifier

    Returns:
        PDF file response with the handout content
    """
    # Retrieve event/run context and fetch handout by code
    ctx = get_event_run(request, s)
    ctx["handout"] = get_object_or_404(Handout, event=ctx["event"], cod=cod)

    # Generate PDF and return as downloadable response
    fp = print_handout(ctx)
    return return_pdf(fp, str(ctx["handout"]))


def album_aux(request, context, parent_album):
    """Prepare album context with sub-albums and paginated uploads.

    Args:
        request: Django HTTP request object
        context: Context dictionary to update
        parent_album: Parent album instance or None for root level

    Returns:
        Rendered album page with sub-albums and uploads
    """
    context["subs"] = Album.objects.filter(run=context["run"], parent=parent_album, is_visible=True).order_by(
        "-created"
    )
    if parent_album is not None:
        upload_list = AlbumUpload.objects.filter(album=context["album"]).order_by("-created")
        paginator = Paginator(upload_list, 20)
        page_number = request.GET.get("page")
        try:
            upload_list = paginator.page(page_number)
        except PageNotAnInteger:
            upload_list = paginator.page(1)  # If page is not an integer, deliver first
        except EmptyPage:
            upload_list = paginator.page(
                paginator.num_pages
            )  # If page is out of range (e.g.  9999), deliver last page of results.
        context["page"] = upload_list
        context["name"] = f"{context['album']} - {str(context['run'])}"
    else:
        context["name"] = f"Album - {str(context['run'])}"
    context["parent"] = parent_album
    return render(request, "larpmanager/event/album.html", context)


@login_required
def album(request, s):
    ctx = get_event_run(request, s)
    return album_aux(request, ctx, None)


@login_required
def album_sub(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """View handler for displaying a specific photo album within an event run."""
    ctx = get_event_run(request, s)
    get_album(ctx, num)
    return album_aux(request, ctx, ctx["album"])


@login_required
def workshops(request: HttpRequest, s: str) -> HttpResponse:
    """
    Display workshops for a specific event with completion status for the current user.

    Args:
        request: The HTTP request object containing user information
        s: The event slug identifier

    Returns:
        HttpResponse: Rendered template with workshop list and completion status
    """
    # Get event context with signup and status validation
    ctx = get_event_run(request, s, signup=True, include_status=True)

    # Initialize workshop list for template context
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

    return render(request, "larpmanager/event/workshops/index.html", ctx)


def valid_workshop_answer(request, ctx):
    """Validate workshop quiz answers and determine pass/fail status.

    Args:
        request: HTTP request object containing quiz answers
        ctx: Context dictionary containing workshop questions

    Returns:
        bool: True if all answers are correct, False otherwise
    """
    res = True
    for el in ctx["list"]:
        el["correct"] = []
        el["answer"] = []
        for o in el["opt"]:
            if o["is_correct"]:
                el["correct"].append(o["id"])
            ix = f"{el['id']}_{o['id']}"
            if request.POST.get(ix, "") == "on":
                el["answer"].append(o["id"])
        el["correct"].sort()
        el["answer"].sort()
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
    ctx = get_event_run(request, s, signup=True, include_status=True)
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
def shuttle(request):
    """Display shuttle service requests for the current association.

    Args:
        request: HTTP request object

    Returns:
        Rendered shuttle template with active and recent requests
    """
    check_assoc_feature(request, "shuttle")
    # get last shuttle requests
    ref = datetime.now() - timedelta(days=5)
    ctx = def_user_context(request)
    ctx.update(
        {
            "list": ShuttleService.objects.exclude(status=ShuttleStatus.DONE)
            .filter(assoc_id=request.assoc["id"])
            .order_by("status", "date", "time"),
            "is_shuttle": is_shuttle(request),
            "past": ShuttleService.objects.filter(
                created__gt=ref.date(),
                status=ShuttleStatus.DONE,
                assoc_id=request.assoc["id"],
            ).order_by("status", "date", "time"),
        }
    )
    return render(request, "larpmanager/general/shuttle.html", ctx)


@login_required
def shuttle_new(request):
    """Handle creation of new shuttle service requests.

    Args:
        request: HTTP request object

    Returns:
        Redirect to shuttle list on success or form template on GET/invalid POST
    """
    check_assoc_feature(request, "shuttle")
    ctx = def_user_context(request)

    if request.method == "POST":
        form = ShuttleServiceForm(request.POST, request=request, ctx=ctx)
        if form.is_valid():
            el = form.save(commit=False)
            el.member = request.user.member
            el.save()
            return redirect("shuttle")
    else:
        form = ShuttleServiceForm(request=request, ctx=ctx)
    return render(
        request,
        "larpmanager/general/writing.html",
        {"form": form, "name": _("New shuttle request")},
    )


@login_required
def shuttle_edit(request, n):
    """Edit existing shuttle service request.

    Args:
        request: HTTP request object
        n: Shuttle service ID to edit

    Returns:
        HttpResponse: Rendered edit form or redirect after successful update
    """
    check_assoc_feature(request, "shuttle")
    ctx = def_user_context(request)

    shuttle = ShuttleService.objects.get(pk=n)
    if request.method == "POST":
        form = ShuttleServiceEditForm(request.POST, instance=shuttle, request=request, ctx=ctx)
        if form.is_valid():
            form.save()
            return redirect("shuttle")
    else:
        form = ShuttleServiceEditForm(instance=shuttle, request=request, ctx=ctx)
    return render(
        request,
        "larpmanager/general/writing.html",
        {"form": form, "name": _("Modify shuttle request")},
    )
