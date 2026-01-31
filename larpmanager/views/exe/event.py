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

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

from larpmanager.cache.config import get_association_config, get_event_config
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.links import reset_event_links
from larpmanager.forms.event import (
    ExeTemplateForm,
    ExeTemplateRolesForm,
    OrgaConfigForm,
    OrgaRunForm,
)
from larpmanager.models.access import EventRole
from larpmanager.models.event import (
    Event,
    Run,
)
from larpmanager.utils.core.base import check_association_context, get_context
from larpmanager.utils.core.common import get_coming_runs, get_event_template
from larpmanager.utils.services.edit import backend_get, exe_delete, exe_edit
from larpmanager.utils.users.deadlines import check_run_deadlines
from larpmanager.views.manage import _get_registration_counts, _get_registration_status
from larpmanager.views.orga.event import full_event_edit
from larpmanager.views.orga.registration import get_pre_registration


@login_required
def exe_events(request: HttpRequest) -> HttpResponse:
    """Display events for the current association with registration status and counts."""
    # Check permissions and get association context
    context = check_association_context(request, "exe_events")

    # Get all runs for the association, ordered by end date
    context["list"] = (
        Run.objects.filter(event__association_id=context["association_id"]).select_related("event").order_by("end")
    )

    # Add registration status and counts to each run
    for run in context["list"]:
        run.registration_status = _get_registration_status(run)
        run.registration_counts = _get_registration_counts(run)

    return render(request, "larpmanager/exe/events.html", context)


@login_required
def exe_events_edit(request: HttpRequest, event_uuid: str) -> HttpResponse:
    """Handle editing of existing events or creation of new events.

    Args:
        request: HTTP request object containing user session and form data
        event_uuid: Event number UUID (0 for new event creation)

    Returns:
        HttpResponse: Either a redirect to the appropriate page after successful operation
                     or a rendered event form template for user input

    Raises:
        PermissionDenied: If user lacks required association permissions
        Http404: If specified event number doesn't exist

    """
    # Check user has executive events permission for the association
    context = check_association_context(request, "exe_events")

    # Determine if this is creation or editing
    if event_uuid != "0":
        # Retrieve the run object for editing
        backend_get(context, Run, event_uuid, "event")
        event = context["el"].event
        run = context["el"]
        on_created = None
    else:
        # Prepare for creation
        event = None
        run = None
        context["exe"] = True

        if context.get("onboarding"):
            context["welcome_message"] = True
            context["tutorial"] = None
            context["config"] = None
            context["is_sidebar_open"] = False

        # Define callback for post-creation operations
        def on_created(created_event: Event) -> None:
            """Post-creation callback for setting up organizer role and sticky message."""
            # Automatically add requesting user as event organizer
            (er, _created) = EventRole.objects.get_or_create(event=created_event, number=1)
            if not er.name:
                er.name = "Organizer"
            er.members.add(context["member"])
            er.save()

            # Refresh cached event links for user navigation
            reset_event_links(context["member"].id, context["association_id"])

    # Use unified full_event_edit for both creation and editing
    context["add_another"] = False
    return full_event_edit(
        context,
        request,
        event,
        run,
        is_executive=True,
        on_created_callback=on_created,
    )


@login_required
def exe_runs_edit(request: HttpRequest, run_uuid: str) -> HttpResponse:
    """Edit organization-wide run with event field."""
    return exe_edit(request, OrgaRunForm, run_uuid, "exe_events", additional_field="event")


@login_required
def exe_templates(request: HttpRequest) -> HttpResponse:
    """View for managing event templates in the organization.

    Displays a list of template events with their associated roles,
    creating default organizer role if none exist.
    """
    # Check user permissions for template management
    context = check_association_context(request, "exe_templates")

    # Get all template events for the organization, ordered by last update
    context["list"] = Event.objects.filter(association_id=context["association_id"], template=True).order_by("-updated")

    # Ensure each template has at least one role (organizer by default)
    for el in context["list"]:
        el.roles = EventRole.objects.filter(event=el).order_by("number")
        if not el.roles:
            el.roles = [EventRole.objects.create(event=el, number=1, name="Organizer")]

    return render(request, "larpmanager/exe/templates.html", context)


@login_required
def exe_templates_edit(request: HttpRequest, template_uuid: str) -> HttpResponse:
    """Edit an existing executive template."""
    return exe_edit(request, ExeTemplateForm, template_uuid, "exe_templates")


@login_required
def exe_templates_delete(request: HttpRequest, template_uuid: str) -> HttpResponse:
    """Delete template."""
    return exe_delete(request, ExeTemplateForm, template_uuid, "exe_templates")


@login_required
def exe_templates_config(request: HttpRequest, template_uuid: str) -> HttpResponse:
    """Configure templates for organization events."""
    # Initialize user context and get event template
    add_ctx = get_context(request)
    get_event_template(add_ctx, template_uuid)

    # Update context with event features and configuration
    add_ctx["features"].update(get_event_features(add_ctx["event"].id))
    add_ctx["add_another"] = False

    return exe_edit(request, OrgaConfigForm, template_uuid, "exe_templates", additional_context=add_ctx)


@login_required
def exe_templates_roles(request: HttpRequest, template_uuid: str, role_uuid: str | None) -> HttpResponse:
    """Edit or create template roles for an event."""
    add_ctx = get_context(request)
    get_event_template(add_ctx, template_uuid)
    return exe_edit(request, ExeTemplateRolesForm, role_uuid, "exe_templates", additional_context=add_ctx)


@login_required
def exe_pre_registrations(request: HttpRequest) -> HttpResponse:
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
    context = check_association_context(request, "exe_pre_registrations")
    context["list"] = []
    context["pr"] = []
    context["seen"] = []

    # Get preference configuration for the association
    context["preferences"] = get_association_config(
        context["association_id"], "pre_reg_preferences", default_value=False, context=context
    )

    # Iterate through all non-template events for this association
    for event in Event.objects.filter(association_id=context["association_id"], template=False):
        # Skip events that don't have pre-registration active
        if not get_event_config(event.id, "pre_register_active", default_value=False, context=context):
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
    context = check_association_context(request, "exe_deadlines")

    # Get upcoming runs and check their deadlines
    runs = get_coming_runs(context["association_id"])
    context["list"] = check_run_deadlines(runs)

    return render(request, "larpmanager/exe/deadlines.html", context)
