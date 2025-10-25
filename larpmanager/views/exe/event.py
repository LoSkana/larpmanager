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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_assoc_config, get_event_config
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.links import reset_event_links
from larpmanager.cache.registration import get_reg_counts
from larpmanager.forms.event import (
    ExeEventForm,
    ExeTemplateForm,
    ExeTemplateRolesForm,
    OrgaAppearanceForm,
    OrgaConfigForm,
    OrgaRunForm,
)
from larpmanager.models.access import EventRole
from larpmanager.models.event import (
    Event,
    Run,
)
from larpmanager.utils.base import check_assoc_permission, def_user_context
from larpmanager.utils.common import get_event_template
from larpmanager.utils.deadlines import check_run_deadlines
from larpmanager.utils.edit import backend_edit, backend_get, exe_edit
from larpmanager.views.manage import _get_registration_status
from larpmanager.views.orga.event import full_event_edit
from larpmanager.views.orga.registration import get_pre_registration
from larpmanager.views.user.event import get_coming_runs


@login_required
def exe_events(request: HttpRequest) -> HttpResponse:
    """Display events for the current association with registration status and counts."""
    # Check permissions and get association context
    context = check_assoc_permission(request, "exe_events")

    # Get all runs for the association, ordered by end date
    context["list"] = Run.objects.filter(event__assoc_id=context["a_id"]).select_related("event").order_by("end")

    # Add registration status and counts to each run
    for run in context["list"]:
        run.registration_status = _get_registration_status(run)
        run.counts = get_reg_counts(run)

    return render(request, "larpmanager/exe/events.html", context)


@login_required
def exe_events_edit(request: HttpRequest, num: int) -> HttpResponse:
    """Handle editing of existing events or creation of new executive events.

    This function manages both the creation of new events and the editing of existing events/runs.
    For new events (num=0), it creates the event and automatically adds the requesting user as an organizer.
    For existing events (num>0), it delegates to the full event edit functionality.

    Args:
        request: HTTP request object containing user session and form data
        num: Event number identifier (0 for new event creation, >0 for existing event editing)

    Returns:
        HttpResponse: Either a redirect to the appropriate page after successful operation
                     or a rendered event form template for user input

    Raises:
        PermissionDenied: If user lacks required association permissions
        Http404: If specified event number doesn't exist
    """
    # Check user has executive events permission for the association
    context = check_assoc_permission(request, "exe_events")

    if num:
        # Handle editing of existing event or run
        # Retrieve the run object and set it in context
        backend_get(context, Run, num, "event")
        # Delegate to full event edit with executive flag enabled
        return full_event_edit(context, request, context["el"].event, context["el"], is_executive=True)

    # Handle creation of new event
    # Set executive context flag for form rendering
    context["exe"] = True

    # Process form submission and handle creation logic
    if backend_edit(request, context, ExeEventForm, num, quiet=True):
        # Check if event was successfully created (saved context and new event)
        if "saved" in context and num == 0:
            # Automatically add requesting user as event organizer
            # Get or create organizer role (number=1 is standard organizer role)
            (er, created) = EventRole.objects.get_or_create(event=context["saved"], number=1)
            if not er.name:
                er.name = "Organizer"
            # Add current user's member profile to organizer role
            er.members.add(request.user.member)
            er.save()

            # Refresh cached event links for user navigation
            reset_event_links(request.user.id, context["a_id"])

            # Prepare success message encouraging quick setup completion
            msg = (
                _("Your event has been created")
                + "! "
                + _("Now please complete the quick setup by selecting the features most useful for this event")
            )
            messages.success(request, msg)
            # Redirect to quick setup page for new event
            return redirect("orga_quick", s=context["saved"].slug)
        # Redirect back to events list after successful edit
        return redirect("exe_events")

    # Configure form context and render edit template
    context["add_another"] = False
    return render(request, "larpmanager/exe/edit.html", context)


@login_required
def exe_runs_edit(request, num):
    return exe_edit(request, OrgaRunForm, num, "exe_events", additional_field="event")


@login_required
def exe_events_appearance(request, num):
    return exe_edit(request, OrgaAppearanceForm, num, "exe_events", additional_context={"add_another": False})


@login_required
def exe_templates(request: HttpRequest) -> HttpResponse:
    """View for managing event templates in the organization.

    Displays a list of template events with their associated roles,
    creating default organizer role if none exist.
    """
    # Check user permissions for template management
    context = check_assoc_permission(request, "exe_templates")

    # Get all template events for the organization, ordered by last update
    context["list"] = Event.objects.filter(assoc_id=context["a_id"], template=True).order_by("-updated")

    # Ensure each template has at least one role (organizer by default)
    for el in context["list"]:
        el.roles = EventRole.objects.filter(event=el).order_by("number")
        if not el.roles:
            el.roles = [EventRole.objects.create(event=el, number=1, name="Organizer")]

    return render(request, "larpmanager/exe/templates.html", context)


@login_required
def exe_templates_edit(request, num):
    return exe_edit(request, ExeTemplateForm, num, "exe_templates")


@login_required
def exe_templates_config(request: HttpRequest, num: int) -> HttpResponse:
    """Configure templates for organization events."""
    # Initialize user context and get event template
    add_ctx = def_user_context(request)
    get_event_template(add_ctx, num)

    # Update context with event features and configuration
    add_ctx["features"].update(get_event_features(add_ctx["event"].id))
    add_ctx["add_another"] = False

    return exe_edit(request, OrgaConfigForm, num, "exe_templates", additional_context=add_ctx)


@login_required
def exe_templates_roles(request: HttpRequest, eid: int, num: int | None) -> HttpResponse:
    """Edit or create template roles for an event."""
    add_ctx = def_user_context(request)
    get_event_template(add_ctx, eid)
    return exe_edit(request, ExeTemplateRolesForm, num, "exe_templates", additional_context=add_ctx)


@login_required
def exe_pre_registrations(request) -> HttpResponse:
    """Display pre-registration statistics for all association events.

    This function retrieves and displays pre-registration data for all events
    belonging to the current association. It shows either preference-based
    counts or total registration counts depending on configuration.

    Args:
        request: Django HTTP request object containing user and association data

    Returns:
        HttpResponse: Rendered HTML page showing pre-registration statistics
            with counts organized by preference level or total counts
    """
    # Check user permissions and initialize context
    context = check_assoc_permission(request, "exe_pre_registrations")
    context["list"] = []
    context["pr"] = []
    context["seen"] = []

    # Get preference configuration for the association
    context["preferences"] = get_assoc_config(request.assoc["id"], "pre_reg_preferences", False)

    # Iterate through all non-template events for this association
    for event in Event.objects.filter(assoc_id=request.assoc["id"], template=False):
        # Skip events that don't have pre-registration active
        if not get_event_config(event.id, "pre_register_active", False):
            continue

        # Get pre-registration data for current event
        pr = get_pre_registration(event)

        if context["preferences"]:
            # Process preference-based registration counts (1-5 scale)
            event.count = {}
            for idx in range(1, 6):
                event.count[idx] = 0
                # Set actual count if preference level exists in data
                if idx in pr:
                    event.count[idx] = pr[idx]
        else:
            # Use simple total count for non-preference based systems
            event.total = len(pr["list"])

        # Add processed event to results list
        context["list"].append(event)

    return render(request, "larpmanager/exe/pre_registrations.html", context)


@login_required
def exe_deadlines(request: HttpRequest) -> HttpResponse:
    """Display upcoming run deadlines for the association."""
    # Check user has permission to view deadlines
    context = check_assoc_permission(request, "exe_deadlines")

    # Get upcoming runs and check their deadlines
    runs = get_coming_runs(request.assoc["id"])
    context["list"] = check_run_deadlines(runs)

    return render(request, "larpmanager/exe/deadlines.html", context)
