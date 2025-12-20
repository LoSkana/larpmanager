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
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.miscellanea import (
    HelpQuestionForm,
    ShuttleServiceEditForm,
    ShuttleServiceForm,
)
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
from larpmanager.utils.core.base import get_context, get_event_context, is_shuttle
from larpmanager.utils.core.common import get_album, get_workshop
from larpmanager.utils.core.exceptions import check_association_feature
from larpmanager.utils.io.pdf import (
    print_handout,
)

logger = logging.getLogger(__name__)


def url_short(request: HttpRequest, url_cod: str) -> HttpResponseRedirect:  # noqa: ARG001
    """Redirect to the URL associated with the given shortened code."""
    el = get_object_or_404(UrlShortner, cod=url_cod)
    return redirect(el.url)


def util(request: HttpRequest, util_cod: str) -> HttpResponseRedirect:  # noqa: ARG001
    """Redirect to download URL for the specified utility."""
    try:
        # Retrieve utility object by code
        u = Util.objects.get(cod=util_cod)
        # Redirect to download URL
        return HttpResponseRedirect(u.download())
    except Exception as err:
        msg = "not found"
        raise Http404(msg) from err


@login_required
def user_help(request: HttpRequest, event_slug: str | None = None) -> HttpResponse:
    """Display help page with question submission form and user's previous questions.

    Args:
        request: HTTP request object containing user session and form data
        event_slug: Optional event slug for event-specific help context

    Returns:
        HttpResponse: Rendered help template with form and question list

    Raises:
        Http404: When event slug is provided but event/run not found

    """
    # Initialize context based on whether this is event-specific or general help
    context = get_event_context(request, event_slug, include_status=True) if event_slug else get_context(request)

    # Handle form submission for new help questions
    if request.method == "POST":
        form = HelpQuestionForm(request.POST, request.FILES, context=context)
        if form.is_valid():
            # Create help question instance without saving to database yet
            hp = form.save(commit=False)
            hp.member = context["member"]

            # Associate question with organization if context is available
            if context["association_id"] != 0:
                hp.association_id = context["association_id"]

            # Save question and redirect to prevent form resubmission
            hp.save()
            messages.success(request, _("Question saved!"))
            return redirect(request.path_info)
    else:
        # Display empty form for GET requests
        form = HelpQuestionForm(context=context)

    # Prepare template context with form and user's question history
    context["form"] = form
    context["list"] = HelpQuestion.objects.filter(member=context["member"]).order_by("-created")

    # Filter questions by association context
    if context["association_id"] != 0:
        context["list"] = context["list"].filter(association_id=context["association_id"])
    else:
        context["list"] = context["list"].filter(association=None)

    return render(request, "larpmanager/member/help.html", context)


@login_required
def help_attachment(request: HttpRequest, attachment_id: int) -> HttpResponseRedirect:
    """Handle attachment download for help questions.

    Validates user permissions and redirects to the attachment URL if authorized.
    Only the question owner or users with association role can access attachments.

    Args:
        request: The HTTP request object containing user information
        attachment_id: Primary key of the HelpQuestion to get attachment from

    Returns:
        HttpResponseRedirect: Redirect to the attachment URL

    Raises:
        Http404: If HelpQuestion doesn't exist or user lacks permissions

    """
    # Get default user context with permissions
    context = get_context(request)

    # Attempt to retrieve the help question by primary key
    try:
        hp = HelpQuestion.objects.get(pk=attachment_id)
    except ObjectDoesNotExist as err:
        msg = "HelpQuestion does not exist"
        raise Http404(msg) from err

    # Check access permissions: owner or association role required
    if hp.member != context["member"] and not context["association_role"]:
        msg = "illegal access"
        raise Http404(msg)

    # Redirect to attachment URL for authorized users
    return redirect(hp.attachment.url)


def handout_ext(request: HttpRequest, event_slug: str, code: str) -> HttpResponse:
    """Generate and return a PDF for a specific event handout.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        code: Handout code identifier

    Returns:
        PDF file response with the handout content

    """
    # Retrieve event/run context and fetch handout by code
    context = get_event_context(request, event_slug)
    context["handout"] = get_object_or_404(Handout, event=context["event"], cod=code)

    # Generate PDF response
    return print_handout(context)


def album_aux(request: HttpRequest, context: dict, parent_album: Any) -> Any:
    """Prepare album context with sub-albums and paginated uploads.

    Args:
        request: Django HTTP request object
        context: Context dictionary to update
        parent_album: Parent album instance or None for root level

    Returns:
        Rendered album page with sub-albums and uploads

    """
    context["subs"] = Album.objects.filter(run=context["run"], parent=parent_album, is_visible=True).order_by(
        "-created",
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
                paginator.num_pages,
            )  # If page is out of range (e.g.  9999), deliver last page of results.
        context["page"] = upload_list
        context["name"] = f"{context['album']} - {context['run']!s}"
    else:
        context["name"] = f"Album - {context['run']!s}"
    context["parent"] = parent_album
    return render(request, "larpmanager/event/album.html", context)


@login_required
def album(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render photo album view for an event."""
    context = get_event_context(request, event_slug)
    return album_aux(request, context, None)


@login_required
def album_sub(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """View handler for displaying a specific photo album within an event run."""
    context = get_event_context(request, event_slug)
    get_album(context, num)
    return album_aux(request, context, context["album"])


@login_required
def workshops(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display workshops for a specific event with completion status for the current user.

    Args:
        request: The HTTP request object containing user information
        event_slug: Event identifier string

    Returns:
        HttpResponse: Rendered template with workshop list and completion status

    """
    # Get event context with signup and status validation
    context = get_event_context(request, event_slug, signup=True, include_status=True)

    # Initialize workshop list for template context
    context["list"] = []

    # Set completion check limit to 365 days ago
    limit = timezone.now() - timedelta(days=365)
    logger.debug("Workshop completion limit date: %s", limit)

    # Pre-fetch all workshop completions
    workshops = list(context["event"].workshops.select_related().all().order_by("number"))
    workshop_ids = [w.id for w in workshops]
    workshop_completions = set(
        WorkshopMemberRel.objects.filter(
            member=context["member"], workshop_id__in=workshop_ids, created__gte=limit
        ).values_list("workshop_id", flat=True)
    )

    # Process each workshop assigned to this event
    for workshop in workshops:
        # Get workshop display data
        dt = workshop.show()

        # Check if user has completed this workshop using pre-fetched set
        dt["done"] = workshop.id in workshop_completions

        # Add workshop data to context list
        context["list"].append(dt)

    return render(request, "larpmanager/event/workshops/index.html", context)


def valid_workshop_answer(request: HttpRequest, context: dict) -> Any:
    """Validate workshop quiz answers and determine pass/fail status.

    Args:
        request: HTTP request object containing quiz answers
        context: Context dictionary containing workshop questions

    Returns:
        bool: True if all answers are correct, False otherwise

    """
    all_answers_correct = True
    for question in context["list"]:
        question["correct"] = []
        question["answer"] = []
        for option in question["opt"]:
            if option["is_correct"]:
                question["correct"].append(option["id"])
            form_field_key = f"{question['id']}_{option['id']}"
            if request.POST.get(form_field_key, "") == "on":
                question["answer"].append(option["id"])
        question["correct"].sort()
        question["answer"].sort()
        question["failed"] = question["correct"] != question["answer"]
        if question["failed"]:
            all_answers_correct = False
    return all_answers_correct


@login_required
def workshop_answer(request: HttpRequest, event_slug: str, workshop_module_id: int) -> HttpResponse:
    """Handle workshop answer submission and validation.

    This function processes workshop submissions for LARP events, validates answers,
    tracks completion status, and manages progression through workshop modules.

    Args:
        request (HttpRequest): The HTTP request object containing user data and POST parameters
        event_slug (str): Event slug identifier for the current event/run
        workshop_module_id (int): Workshop module number to process

    Returns:
        HttpResponse: Either a rendered template (answer form or failure page) or
                     a redirect response to next module or workshops overview

    Raises:
        Http404: If event, run, or workshop module is not found
        PermissionDenied: If user doesn't have access to the workshop

    """
    # Get event context and validate user access to workshop signup
    context = get_event_context(request, event_slug, signup=True, include_status=True)
    get_workshop(context, workshop_module_id)

    # Check if user has already completed this workshop module
    completed = [el.pk for el in context["member"].workshops.select_related().all()]
    if context["workshop"].pk in completed:
        messages.success(request, _("Workshop already done!"))
        return redirect("workshops", event_slug=context["run"].get_slug())

    # Build list of questions for the current workshop module
    context["list"] = []
    for question in context["workshop"].questions.select_related().all().order_by("number"):
        context["list"].append(question.show())

    # For GET requests, display the workshop question form
    if request.method != "POST":
        return render(request, "larpmanager/event/workshops/answer.html", context)

    # Process POST request - validate submitted answers
    if valid_workshop_answer(request, context):
        # Create completion record for this workshop module
        WorkshopMemberRel.objects.create(member=context["member"], workshop=context["workshop"])

        # Find remaining uncompleted workshop modules
        remaining = (
            WorkshopModule.objects.filter(event=context["event"], number__gt=context["workshop"].number)
            .exclude(pk__in=completed)
            .order_by("number")
        )

        # Redirect to next module or completion page based on remaining modules
        if len(remaining) > 0:
            messages.success(request, _("Completed module. Remaining: {number:d}").format(number=len(remaining)))
            return redirect(
                "workshop_answer",
                s=context["run"].get_slug(),
                m=remaining.first().number,
            )

        # All modules completed - redirect to workshops overview
        messages.success(request, _("Well done, you've completed all modules!"))
        return redirect("workshops", event_slug=context["run"].get_slug())

    # Invalid answers - show failure page
    return render(request, "larpmanager/event/workshops/failed.html", context)


@login_required
def shuttle(request: HttpRequest) -> Any:
    """Display shuttle service requests for the current association.

    Args:
        request: HTTP request object

    Returns:
        Rendered shuttle template with active and recent requests

    """
    context = get_context(request)
    check_association_feature(request, context, "shuttle")
    # get last shuttle requests
    ref = timezone.now() - timedelta(days=5)
    context.update(
        {
            "list": ShuttleService.objects.exclude(status=ShuttleStatus.DONE)
            .filter(association_id=context["association_id"])
            .order_by("status", "date", "time"),
            "is_shuttle": is_shuttle(request),
            "past": ShuttleService.objects.filter(
                created__gt=ref.date(),
                status=ShuttleStatus.DONE,
                association_id=context["association_id"],
            ).order_by("status", "date", "time"),
        },
    )
    return render(request, "larpmanager/general/shuttle.html", context)


@login_required
def shuttle_new(request: HttpRequest) -> Any:
    """Handle creation of new shuttle service requests.

    Args:
        request: HTTP request object

    Returns:
        Redirect to shuttle list on success or form template on GET/invalid POST

    """
    context = get_context(request)
    check_association_feature(request, context, "shuttle")

    if request.method == "POST":
        form = ShuttleServiceForm(request.POST, request=request, context=context)
        if form.is_valid():
            el = form.save(commit=False)
            el.member = context["member"]
            el.save()
            return redirect("shuttle")
    else:
        form = ShuttleServiceForm(request=request, context=context)
    return render(
        request,
        "larpmanager/general/writing.html",
        {"form": form, "name": _("New shuttle request")},
    )


@login_required
def shuttle_edit(request: HttpRequest, shuttle_id: Any) -> Any:
    """Edit existing shuttle service request.

    Args:
        request: HTTP request object
        shuttle_id: Shuttle service ID to edit

    Returns:
        HttpResponse: Rendered edit form or redirect after successful update

    """
    context = get_context(request)
    check_association_feature(request, context, "shuttle")

    shuttle = ShuttleService.objects.get(pk=shuttle_id)
    if request.method == "POST":
        form = ShuttleServiceEditForm(request.POST, instance=shuttle, request=request, context=context)
        if form.is_valid():
            form.save()
            return redirect("shuttle")
    else:
        form = ShuttleServiceEditForm(instance=shuttle, request=request, context=context)
    return render(
        request,
        "larpmanager/general/writing.html",
        {"form": form, "name": _("Modify shuttle request")},
    )
