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
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.registration import (
    OrgaRegistrationInstallmentForm,
    OrgaRegistrationOptionForm,
    OrgaRegistrationQuestionForm,
    OrgaRegistrationQuotaForm,
    OrgaRegistrationSectionForm,
    OrgaRegistrationSurchargeForm,
    OrgaRegistrationTicketForm,
)
from larpmanager.models.form import (
    RegistrationOption,
    RegistrationQuestion,
    get_ordered_registration_questions,
)
from larpmanager.models.registration import (
    RegistrationInstallment,
    RegistrationQuota,
    RegistrationSection,
    RegistrationSurcharge,
    RegistrationTicket,
)
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.core.common import exchange_order
from larpmanager.utils.io.download import orga_registration_form_download, orga_tickets_download
from larpmanager.utils.services.edit import (
    form_edit_handler,
    options_ajax_handler,
    options_edit_handler,
    orga_edit,
)


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
    context["list"] = RegistrationTicket.objects.filter(event=context["event"]).order_by("order")
    # Get available ticket tiers for the current event
    context["tiers"] = OrgaRegistrationTicketForm.get_tier_available(context["event"], context)

    return render(request, "larpmanager/orga/registration/tickets.html", context)


@login_required
def orga_registration_tickets_edit(request: HttpRequest, event_slug: str, ticket_uuid: str) -> HttpResponse:
    """Edit a specific registration ticket."""
    return orga_edit(request, event_slug, "orga_registration_tickets", OrgaRegistrationTicketForm, ticket_uuid)


@login_required
def orga_registration_tickets_order(
    request: HttpRequest, event_slug: str, ticket_uuid: str, order: int
) -> HttpResponse:
    """Reorder registration tickets for an event."""
    context = check_event_context(request, event_slug, "orga_registration_tickets")
    exchange_order(context, RegistrationTicket, ticket_uuid, order)
    return redirect("orga_registration_tickets", event_slug=context["run"].get_slug())


@login_required
def orga_registration_sections(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display registration sections for an event."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_registration_sections")

    # Retrieve and order registration sections
    context["list"] = RegistrationSection.objects.filter(event=context["event"]).order_by("order")

    return render(request, "larpmanager/orga/registration/sections.html", context)


@login_required
def orga_registration_sections_edit(request: HttpRequest, event_slug: str, section_uuid: str) -> HttpResponse:
    """Edit a specific registration section for an event."""
    return orga_edit(request, event_slug, "orga_registration_sections", OrgaRegistrationSectionForm, section_uuid)


@login_required
def orga_registration_sections_order(
    request: HttpRequest,
    event_slug: str,
    section_uuid: str,
    order: int,
) -> HttpResponse:
    """Reorder registration sections within an event.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        section_uuid: Section UUID
        order: Direction to move ('up' or 'down')

    Returns:
        Redirect to registration sections page

    """
    # Verify user has permission to manage registration sections
    context = check_event_context(request, event_slug, "orga_registration_sections")

    # Exchange order of sections and save changes
    exchange_order(context, RegistrationSection, section_uuid, order)

    return redirect("orga_registration_sections", event_slug=context["run"].get_slug())


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

    # Sort options by order field for each question
    for el in context["list"]:
        el.options_list = el.options.order_by("order")

    return render(request, "larpmanager/orga/registration/form.html", context)


@login_required
def orga_registration_form_edit(request: HttpRequest, event_slug: str, question_uuid: str) -> HttpResponse:
    """Handle registration form question editing for organizers.

    This view allows organizers to edit registration questions, handle form submissions,
    and redirect to appropriate pages based on the question type and user actions.

    Args:
        request: The HTTP request object containing form data and user information
        event_slug: Event slug identifier for the specific event
        question_uuid: Question UUID to edit (0 for new questions)

    Returns:
        Either a rendered form edit page or a redirect response after successful save

    Notes:
        - Handles both creation (num=0) and editing of existing questions
        - Automatically redirects to option creation for single/multiple choice questions
        - Validates that choice questions have at least one option defined

    """
    # Check user permissions for registration form editing
    perm = "orga_registration_form"
    context = check_event_context(request, event_slug, perm)

    return form_edit_handler(
        request,
        context,
        question_uuid,
        perm,
        RegistrationOption,
        OrgaRegistrationQuestionForm,
        "orga_registration_form_edit",
        perm,
        "larpmanager/orga/registration/form_edit.html",
    )


@login_required
def orga_registration_form_order(request: HttpRequest, event_slug: str, question_uuid: str, order: int) -> HttpResponse:
    """Reorders registration form questions for an event."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_registration_form")

    # Update question order in database
    exchange_order(context, RegistrationQuestion, question_uuid, order)

    return redirect("orga_registration_form", event_slug=context["run"].get_slug())


@login_required
def orga_registration_options_edit(request: HttpRequest, event_slug: str, option_uuid: str) -> HttpResponse:
    """Edit registration options for an event.

    Validates that registration questions exist before allowing creation of
    registration options. Redirects to question creation if none exist.

    For new options (option_uuid="0"), expects question_uuid in GET or POST parameters.

    Args:
        request: The HTTP request object
        event_slug: Event slug identifier
        option_uuid: Registration option UUID to edit (0 for new options)

    Returns:
        HttpResponse: Rendered registration option edit page, redirect, or JsonResponse for AJAX

    """
    # Check if this is an AJAX request
    if not request.headers.get("X-Requested-With") == "XMLHttpRequest":
        raise Http404

    # Check user permissions for registration form management
    context = check_event_context(request, event_slug, "orga_registration_form")

    # For new options without question_uuid, verify that questions exist
    if option_uuid == "0":
        question_uuid = request.GET.get("question_uuid") or request.POST.get("question_uuid")
        if not question_uuid and not context["event"].get_elements(RegistrationQuestion).exists():
            # Display warning message to user about missing prerequisites
            messages.warning(
                request,
                _("You must create at least one registration question before you can create registration options"),
            )
            # Redirect to registration questions creation page
            return redirect("orga_registration_form_edit", event_slug=event_slug, question_uuid="0")

    return options_edit_handler(
        request, context, option_uuid, RegistrationQuestion, RegistrationOption, OrgaRegistrationOptionForm
    )


@login_required
def orga_registration_options_ajax(request: HttpRequest, event_slug: str, option_uuid: str) -> JsonResponse:
    """Handle AJAX requests for registration option form loading.

    Returns form HTML for creating/editing registration options in a modal.
    Supports both new options (option_uuid="0") and existing ones.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        option_uuid: Option UUID to edit (0 for new options)

    Returns:
        JsonResponse with form HTML or error message
    """
    # Check user permissions
    context = check_event_context(request, event_slug, "orga_registration_form")

    return options_ajax_handler(
        request, context, option_uuid, RegistrationQuestion, RegistrationOption, OrgaRegistrationOptionForm
    )


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
    exchange_order(context, RegistrationOption, option_uuid, order)

    # Redirect back to the form edit page with scroll_to parameter
    url = reverse(
        "orga_registration_form_edit",
        kwargs={
            "event_slug": context["run"].get_slug(),
            "question_uuid": context["current"].question.uuid,
        },
    )
    return HttpResponseRedirect(f"{url}?scroll_to=options")


@login_required
def orga_registration_quotas(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage registration quotas for an event."""
    # Check event permissions and build context
    context = check_event_context(request, event_slug, "orga_registration_quotas")

    # Retrieve and order quotas by number
    context["list"] = RegistrationQuota.objects.filter(event=context["event"]).order_by("number")

    return render(request, "larpmanager/orga/registration/quotas.html", context)


@login_required
def orga_registration_quotas_edit(request: HttpRequest, event_slug: str, quota_uuid: str) -> HttpResponse:
    """Edit a specific registration quota for an event."""
    return orga_edit(request, event_slug, "orga_registration_quotas", OrgaRegistrationQuotaForm, quota_uuid)


@login_required
def orga_registration_installments(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage registration installments for an event."""
    # Verify user has permission to access registration installment management
    context = check_event_context(request, event_slug, "orga_registration_installments")

    # Retrieve all installments for this event, ordered by sequence and amount
    context["list"] = RegistrationInstallment.objects.filter(event=context["event"]).order_by("order", "amount")

    return render(request, "larpmanager/orga/registration/installments.html", context)


@login_required
def orga_registration_installments_edit(request: HttpRequest, event_slug: str, installment_uuid: str) -> HttpResponse:
    """Edit a specific registration installment for an event."""
    return orga_edit(
        request, event_slug, "orga_registration_installments", OrgaRegistrationInstallmentForm, installment_uuid
    )


@login_required
def orga_registration_surcharges(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display registration surcharges for an event."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_registration_surcharges")

    # Fetch and order surcharges by number
    context["list"] = RegistrationSurcharge.objects.filter(event=context["event"]).order_by("number")

    return render(request, "larpmanager/orga/registration/surcharges.html", context)


@login_required
def orga_registration_surcharges_edit(request: HttpRequest, event_slug: str, surcharge_uuid: str) -> HttpResponse:
    """Edit a registration surcharge for an event."""
    return orga_edit(request, event_slug, "orga_registration_surcharges", OrgaRegistrationSurchargeForm, surcharge_uuid)
