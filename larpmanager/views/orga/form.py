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

from django.contrib.auth.decorators import login_required
from django.db.models import F, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from larpmanager.cache.registration import get_registration_tickets
from larpmanager.forms.registration import OrgaRegistrationTicketForm
from larpmanager.models.form import RegistrationOption, RegistrationQuestion
from larpmanager.models.registration import (
    RegistrationInstallment,
    RegistrationQuota,
    RegistrationSection,
    RegistrationSurcharge,
)
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.core.common import get_element
from larpmanager.utils.edit.backend import (
    backend_order,
)
from larpmanager.utils.edit.orga import (
    OrgaAction,
    form_edit_handler,
    options_edit_handler,
    orga_delete,
    orga_edit,
    orga_new,
    orga_order,
)
from larpmanager.utils.io.download import orga_registration_form_download, orga_tickets_download


@login_required
def orga_registration_tickets(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Handle organization registration tickets management.

    Manages the display and download of registration tickets for an event.
    Supports both GET requests for displaying the tickets page and POST
    requests for downloading tickets.

    Args:
        request: The HTTP request object containing user data and method info
        event_slug: Event identifier string for permission checking and context

    Returns:
        HttpResponse: Rendered tickets template or download response

    """
    # Check user permissions for accessing registration tickets management
    context = check_event_context(request, event_slug, "orga_registration_tickets")

    # Handle POST request for ticket download functionality
    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_tickets_download(context)

    # Set up context variables for template rendering
    context["upload"] = "registration_tickets"
    context["download"] = 1

    # Fetch registration tickets ordered by their sequence number
    context["list"] = get_registration_tickets(context["event"].id)
    # Get available ticket tiers for the current event
    context["tiers"] = OrgaRegistrationTicketForm.get_tier_available(context["event"], context)

    return render(request, "larpmanager/orga/registration/tickets.html", context)


@login_required
def orga_registration_tickets_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration ticket."""
    return orga_new(request, event_slug, OrgaAction.REGISTRATION_TICKETS)


@login_required
def orga_registration_tickets_edit(request: HttpRequest, event_slug: str, ticket_uuid: str) -> HttpResponse:
    """Edit a specific registration ticket."""
    return orga_edit(request, event_slug, OrgaAction.REGISTRATION_TICKETS, ticket_uuid)


@login_required
def orga_registration_tickets_delete(request: HttpRequest, event_slug: str, ticket_uuid: str) -> HttpResponse:
    """Delete ticket for event."""
    return orga_delete(request, event_slug, OrgaAction.REGISTRATION_TICKETS, ticket_uuid)


@login_required
def orga_registration_tickets_order(
    request: HttpRequest, event_slug: str, ticket_uuid: str, order: int
) -> HttpResponse:
    """Reorder registration tickets for an event."""
    return orga_order(request, event_slug, OrgaAction.REGISTRATION_TICKETS, ticket_uuid, order)


@login_required
def orga_registration_sections(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display registration sections for an event."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_registration_sections")

    # Retrieve and order registration sections
    context["list"] = RegistrationSection.objects.filter(event=context["event"]).order_by("order")

    return render(request, "larpmanager/orga/registration/sections.html", context)


@login_required
def orga_registration_sections_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration section for an event."""
    return orga_new(request, event_slug, OrgaAction.REGISTRATION_SECTIONS)


@login_required
def orga_registration_sections_edit(request: HttpRequest, event_slug: str, section_uuid: str) -> HttpResponse:
    """Edit a specific registration section for an event."""
    return orga_edit(request, event_slug, OrgaAction.REGISTRATION_SECTIONS, section_uuid)


@login_required
def orga_registration_sections_delete(request: HttpRequest, event_slug: str, section_uuid: str) -> HttpResponse:
    """Delete section for event."""
    return orga_delete(request, event_slug, OrgaAction.REGISTRATION_SECTIONS, section_uuid)


@login_required
def orga_registration_sections_order(
    request: HttpRequest,
    event_slug: str,
    section_uuid: str,
    order: int,
) -> HttpResponse:
    """Reorder registration sections within an event."""
    return orga_order(request, event_slug, OrgaAction.REGISTRATION_SECTIONS, section_uuid, order)


def get_ordered_registration_questions(context: dict) -> QuerySet[RegistrationQuestion]:
    """Get registration questions ordered by section and question order."""
    questions = context["event"].get_elements(RegistrationQuestion)
    return questions.order_by(F("section__order").asc(nulls_first=True), "order")


@login_required
def orga_registration_form(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Handle the organization registration form view.

    Displays the registration form configuration page for event organizers,
    allowing them to view and download the current registration questions.

    Args:
        request: The HTTP request object containing user and POST data
        event_slug: Event identifier string for permission checking

    Returns:
        HttpResponse: Rendered registration form page or download response

    """
    # Check if user has permission to access the registration form management
    context = check_event_context(request, event_slug, "orga_registration_form")

    # Handle download request for registration form data
    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_registration_form_download(context)

    # Configure context for template rendering
    context["upload"] = "registration_form"
    context["download"] = 1

    # Fetch ordered registration questions with their options
    context["list"] = get_ordered_registration_questions(context).prefetch_related("options")

    return render(request, "larpmanager/orga/registration/form.html", context)


@login_required
def orga_registration_form_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration form question."""
    return form_edit_handler(
        request,
        event_slug,
        "orga_registration_form",
        None,
    )


@login_required
def orga_registration_form_edit(request: HttpRequest, event_slug: str, question_uuid: str) -> HttpResponse:
    """Edit registration form question for organizers."""
    return form_edit_handler(
        request,
        event_slug,
        "orga_registration_form",
        question_uuid,
    )


@login_required
def orga_registration_form_delete(request: HttpRequest, event_slug: str, question_uuid: str) -> HttpResponse:
    """Delete question for event."""
    return orga_delete(
        request,
        event_slug,
        OrgaAction.REGISTRATION_FORM,
        question_uuid,
    )


@login_required
def orga_registration_form_order(request: HttpRequest, event_slug: str, question_uuid: str, order: int) -> HttpResponse:
    """Reorders registration form questions for an event."""
    return orga_order(request, event_slug, OrgaAction.REGISTRATION_FORM, question_uuid, order)


@login_required
def orga_registration_options_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration option."""
    return options_edit_handler(request, event_slug, "orga_registration_form", None)


@login_required
def orga_registration_options_edit(request: HttpRequest, event_slug: str, option_uuid: str) -> HttpResponse:
    """Edit registration options for an event."""
    return options_edit_handler(request, event_slug, "orga_registration_form", option_uuid)


@login_required
def orga_registration_options_list(
    request: HttpRequest, event_slug: str, question_uuid: str | None = None
) -> HttpResponse:
    """Display the list of options for a registration form question in an iframe.

    This view shows only the options list section, designed to be loaded in an iframe
    within the form edit page.

    Args:
        request: The HTTP request object
        event_slug: Event slug identifier
        question_uuid: Question UUID to show options for

    Returns:
        HttpResponse with the options list template
    """
    # Check user permissions for registration form management
    context = check_event_context(request, event_slug, "orga_registration_form")
    context["frame"] = 1

    if question_uuid:
        # Get the question
        get_element(context, question_uuid, "el", RegistrationQuestion)

        # Load existing options for the question
        options_queryset = RegistrationOption.objects.filter(question=context["el"])
        context["list"] = options_queryset.order_by("order")

    return render(request, "larpmanager/orga/registration/options_list.html", context)


@login_required
def orga_registration_options_order(
    request: HttpRequest,
    event_slug: str,
    option_uuid: str,
    order: int,
) -> HttpResponse:
    """Reorder registration options within a form question.

    Args:
        request: The HTTP request object
        event_slug: Event/run slug identifier
        option_uuid: Option UUID to reorder
        order: Direction to move the option (1 or 0)

    Returns:
        Redirect to the registration form edit page

    """
    # Check user permissions and get event context
    context = check_event_context(request, event_slug, "orga_registration_form")

    # Exchange the order of registration options
    backend_order(context, RegistrationOption, option_uuid, order)

    # Redirect back to the form edit page
    url = reverse(
        "orga_registration_form_edit",
        kwargs={
            "event_slug": context["run"].get_slug(),
            "question_uuid": context["current"].question.uuid,
        },
    )
    return HttpResponseRedirect(url)


@login_required
def orga_registration_options_delete(request: HttpRequest, event_slug: str, option_uuid: str) -> HttpResponse:
    """Delete registration option for an event."""
    return orga_delete(request, event_slug, OrgaAction.REGISTRATION_FORM_OPTION, option_uuid)


@login_required
def orga_registration_quotas(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage registration quotas for an event."""
    # Check event permissions and build context
    context = check_event_context(request, event_slug, "orga_registration_quotas")

    # Retrieve and order quotas by number
    context["list"] = RegistrationQuota.objects.filter(event=context["event"]).order_by("number")

    return render(request, "larpmanager/orga/registration/quotas.html", context)


@login_required
def orga_registration_quotas_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration quota for an event."""
    return orga_new(request, event_slug, OrgaAction.REGISTRATION_QUOTAS)


@login_required
def orga_registration_quotas_edit(request: HttpRequest, event_slug: str, quota_uuid: str) -> HttpResponse:
    """Edit a specific registration quota for an event."""
    return orga_edit(request, event_slug, OrgaAction.REGISTRATION_QUOTAS, quota_uuid)


@login_required
def orga_registration_quotas_delete(request: HttpRequest, event_slug: str, quota_uuid: str) -> HttpResponse:
    """Delete quota for event."""
    return orga_delete(request, event_slug, OrgaAction.REGISTRATION_QUOTAS, quota_uuid)


@login_required
def orga_registration_installments(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage registration installments for an event."""
    # Verify user has permission to access registration installment management
    context = check_event_context(request, event_slug, "orga_registration_installments")

    # Retrieve all installments for this event, ordered by sequence and amount
    context["list"] = RegistrationInstallment.objects.filter(event=context["event"]).order_by("order", "amount")

    return render(request, "larpmanager/orga/registration/installments.html", context)


@login_required
def orga_registration_installments_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration installment for an event."""
    return orga_new(request, event_slug, OrgaAction.REGISTRATION_INSTALLMENTS)


@login_required
def orga_registration_installments_edit(request: HttpRequest, event_slug: str, installment_uuid: str) -> HttpResponse:
    """Edit a specific registration installment for an event."""
    return orga_edit(request, event_slug, OrgaAction.REGISTRATION_INSTALLMENTS, installment_uuid)


@login_required
def orga_registration_installments_delete(request: HttpRequest, event_slug: str, installment_uuid: str) -> HttpResponse:
    """Delete installment for event."""
    return orga_delete(request, event_slug, OrgaAction.REGISTRATION_INSTALLMENTS, installment_uuid)


@login_required
def orga_registration_surcharges(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display registration surcharges for an event."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_registration_surcharges")

    # Fetch and order surcharges by number
    context["list"] = RegistrationSurcharge.objects.filter(event=context["event"]).order_by("number")

    return render(request, "larpmanager/orga/registration/surcharges.html", context)


@login_required
def orga_registration_surcharges_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration surcharge for an event."""
    return orga_new(request, event_slug, OrgaAction.REGISTRATION_SURCHARGES)


@login_required
def orga_registration_surcharges_edit(request: HttpRequest, event_slug: str, surcharge_uuid: str) -> HttpResponse:
    """Edit a registration surcharge for an event."""
    return orga_edit(request, event_slug, OrgaAction.REGISTRATION_SURCHARGES, surcharge_uuid)


@login_required
def orga_registration_surcharges_delete(request: HttpRequest, event_slug: str, surcharge_uuid: str) -> HttpResponse:
    """Delete surcharge for event."""
    return orga_delete(request, event_slug, OrgaAction.REGISTRATION_SURCHARGES, surcharge_uuid)
