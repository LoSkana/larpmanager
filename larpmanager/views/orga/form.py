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
    BaseQuestionType,
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
from larpmanager.utils.common import exchange_order
from larpmanager.utils.download import orga_registration_form_download, orga_tickets_download
from larpmanager.utils.edit import backend_edit, orga_edit, set_suggestion
from larpmanager.utils.event import check_event_permission


@login_required
def orga_registration_tickets(request: HttpRequest, s: str) -> HttpResponse:
    """Handle organization registration tickets management.

    Manages the display and download of registration tickets for an event.
    Supports both GET requests for displaying the tickets page and POST
    requests for downloading tickets.

    Args:
        request: The HTTP request object containing user data and method info
        s: The event slug identifier for permission checking and context

    Returns:
        HttpResponse: Rendered tickets template or download response
    """
    # Check user permissions for accessing registration tickets management
    ctx = check_event_permission(request, s, "orga_registration_tickets")

    # Handle POST request for ticket download functionality
    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_tickets_download(ctx)

    # Set up context variables for template rendering
    ctx["upload"] = "registration_tickets"
    ctx["download"] = 1

    # Fetch registration tickets ordered by their sequence number
    ctx["list"] = RegistrationTicket.objects.filter(event=ctx["event"]).order_by("order")
    # Get available ticket tiers for the current event
    ctx["tiers"] = OrgaRegistrationTicketForm.get_tier_available(ctx["event"])

    return render(request, "larpmanager/orga/registration/tickets.html", ctx)


@login_required
def orga_registration_tickets_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_tickets", OrgaRegistrationTicketForm, num)


@login_required
def orga_registration_tickets_order(request: HttpRequest, s: str, num: int, order: str) -> HttpResponse:
    """Reorder registration tickets for an event."""
    ctx = check_event_permission(request, s, "orga_registration_tickets")
    exchange_order(ctx, RegistrationTicket, num, order)
    return redirect("orga_registration_tickets", s=ctx["run"].get_slug())


@login_required
def orga_registration_sections(request: HttpRequest, s: str) -> HttpResponse:
    """Display registration sections for an event."""
    # Check permissions and get event context
    ctx = check_event_permission(request, s, "orga_registration_sections")

    # Retrieve and order registration sections
    ctx["list"] = RegistrationSection.objects.filter(event=ctx["event"]).order_by("order")

    return render(request, "larpmanager/orga/registration/sections.html", ctx)


@login_required
def orga_registration_sections_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_sections", OrgaRegistrationSectionForm, num)


@login_required
def orga_registration_sections_order(
    request: HttpRequest,
    s: str,
    num: int,
    order: str,
) -> HttpResponse:
    """Reorder registration sections within an event.

    Args:
        request: HTTP request object
        s: Event slug identifier
        num: Current position of the section
        order: Direction to move ('up' or 'down')

    Returns:
        Redirect to registration sections page
    """
    # Verify user has permission to manage registration sections
    ctx = check_event_permission(request, s, "orga_registration_sections")

    # Exchange order of sections and save changes
    exchange_order(ctx, RegistrationSection, num, order)

    return redirect("orga_registration_sections", s=ctx["run"].get_slug())


@login_required
def orga_registration_form(request: HttpRequest, s: str) -> HttpResponse:
    """Handle the organization registration form view.

    Displays the registration form configuration page for event organizers,
    allowing them to view and download the current registration questions.

    Args:
        request: The HTTP request object containing user and POST data
        s: The event slug identifier for permission checking

    Returns:
        HttpResponse: Rendered registration form page or download response
    """
    # Check if user has permission to access the registration form management
    ctx = check_event_permission(request, s, "orga_registration_form")

    # Handle download request for registration form data
    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_registration_form_download(ctx)

    # Configure context for template rendering
    ctx["upload"] = "registration_form"
    ctx["download"] = 1

    # Fetch ordered registration questions with their options
    ctx["list"] = get_ordered_registration_questions(ctx).prefetch_related("options")

    # Sort options by order field for each question
    for el in ctx["list"]:
        el.options_list = el.options.order_by("order")

    return render(request, "larpmanager/orga/registration/form.html", ctx)


@login_required
def orga_registration_form_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """
    Handle registration form question editing for organizers.

    This view allows organizers to edit registration questions, handle form submissions,
    and redirect to appropriate pages based on the question type and user actions.

    Args:
        request : HttpRequest
            The HTTP request object containing form data and user information
        s : str
            Event slug identifier for the specific event
        num : int
            Question number/ID to edit (0 for new questions)

    Returns
        HttpResponse
            Either a rendered form edit page or a redirect response after successful save

    Notes
        - Handles both creation (num=0) and editing of existing questions
        - Automatically redirects to option creation for single/multiple choice questions
        - Validates that choice questions have at least one option defined
    """
    # Check user permissions for registration form editing
    perm = "orga_registration_form"
    ctx = check_event_permission(request, s, perm)

    # Process form submission using backend edit helper
    if backend_edit(request, ctx, OrgaRegistrationQuestionForm, num, is_association_based=False):
        # Set suggestion flag for the current permission
        set_suggestion(ctx, perm)

        # Handle "continue editing" action - redirect to create new question
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, s=ctx["run"].get_slug(), num=0)

        # Determine if we need to redirect to option editing
        edit_option = False

        # Check if user explicitly requested to add options
        if str(request.POST.get("new_option", "")) == "1":
            edit_option = True
        # For choice questions, ensure at least one option exists
        elif ctx["saved"].typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
            if not RegistrationOption.objects.filter(question_id=ctx["saved"].id).exists():
                edit_option = True
                messages.warning(
                    request,
                    _("You must define at least one option before saving a single-choice or multiple-choice question"),
                )

        # Redirect to option creation if needed, otherwise back to form list
        if edit_option:
            return redirect(orga_registration_options_new, s=ctx["run"].get_slug(), num=ctx["saved"].id)
        return redirect(perm, s=ctx["run"].get_slug())

    # Prepare context for rendering the edit form
    ctx["list"] = RegistrationOption.objects.filter(question=ctx["el"]).order_by("order")
    return render(request, "larpmanager/orga/registration/form_edit.html", ctx)


@login_required
def orga_registration_form_order(request: HttpRequest, s: str, num: int, order: str) -> HttpResponse:
    """Reorders registration form questions for an event."""
    # Check permissions and get event context
    ctx = check_event_permission(request, s, "orga_registration_form")

    # Update question order in database
    exchange_order(ctx, RegistrationQuestion, num, order)

    return redirect("orga_registration_form", s=ctx["run"].get_slug())


@login_required
def orga_registration_options_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit registration options for an event.

    Validates that registration questions exist before allowing creation of
    registration options. Redirects to question creation if none exist.

    Args:
        request: The HTTP request object
        s: Event slug identifier
        num: Registration option number to edit

    Returns:
        HttpResponse: Rendered registration option edit page or redirect
    """
    # Check user permissions for registration form management
    ctx = check_event_permission(request, s, "orga_registration_form")

    # Verify that registration questions exist before proceeding
    if not ctx["event"].get_elements(RegistrationQuestion).exists():
        # Display warning message to user about missing prerequisites
        messages.warning(
            request, _("You must create at least one registration question before you can create registration options")
        )
        # Redirect to registration questions creation page
        return redirect("orga_registration_form_edit", s=s, num=0)

    # Proceed with registration option editing
    return registration_option_edit(ctx, num, request)


@login_required
def orga_registration_options_new(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Create new registration option for specified question."""
    ctx = check_event_permission(request, s, "orga_registration_form")
    ctx["question_id"] = num
    return registration_option_edit(ctx, 0, request)


def registration_option_edit(context, option_number, request):
    """
    Handle editing of registration option with form processing and redirect logic.

    Args:
        context: Context dictionary with event and form data
        option_number: Option number/ID being edited
        request: HTTP request object

    Returns:
        HttpResponse: Redirect to next step or rendered edit form
    """
    if backend_edit(request, context, OrgaRegistrationOptionForm, option_number, is_association_based=False):
        redirect_target = "orga_registration_form_edit"
        if "continue" in request.POST:
            redirect_target = "orga_registration_options_new"
        return redirect(redirect_target, s=context["run"].get_slug(), num=context["saved"].question_id)

    return render(request, "larpmanager/orga/edit.html", context)


@login_required
def orga_registration_options_order(
    request: HttpRequest,
    s: str,
    num: int,
    order: str,
) -> HttpResponse:
    """Reorder registration options within a form question.

    Args:
        request: The HTTP request object
        s: Event/run slug identifier
        num: Question ID containing the options to reorder
        order: Direction to move the option ('up' or 'down')

    Returns:
        Redirect to the registration form edit page
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s, "orga_registration_form")

    # Exchange the order of registration options
    exchange_order(ctx, RegistrationOption, num, order)

    # Redirect back to the form edit page
    return redirect("orga_registration_form_edit", s=ctx["run"].get_slug(), num=ctx["current"].question_id)


@login_required
def orga_registration_quotas(request: HttpRequest, s: str) -> HttpResponse:
    """Display and manage registration quotas for an event."""
    # Check event permissions and build context
    ctx = check_event_permission(request, s, "orga_registration_quotas")

    # Retrieve and order quotas by number
    ctx["list"] = RegistrationQuota.objects.filter(event=ctx["event"]).order_by("number")

    return render(request, "larpmanager/orga/registration/quotas.html", ctx)


@login_required
def orga_registration_quotas_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_quotas", OrgaRegistrationQuotaForm, num)


@login_required
def orga_registration_installments(request: HttpRequest, s: str) -> HttpResponse:
    """Display and manage registration installments for an event.

    Renders a page showing all payment installment options configured for the event,
    ordered by sequence and amount.

    Args:
        request: The HTTP request object
        s: Event slug identifier

    Returns:
        Rendered installments management page
    """
    # Verify user has permission to access registration installment management
    ctx = check_event_permission(request, s, "orga_registration_installments")

    # Retrieve all installments for this event, ordered by sequence and amount
    ctx["list"] = RegistrationInstallment.objects.filter(event=ctx["event"]).order_by("order", "amount")

    return render(request, "larpmanager/orga/registration/installments.html", ctx)


@login_required
def orga_registration_installments_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_installments", OrgaRegistrationInstallmentForm, num)


@login_required
def orga_registration_surcharges(request: HttpRequest, s: str) -> HttpResponse:
    """Display registration surcharges for an event."""
    # Check permissions and get event context
    ctx = check_event_permission(request, s, "orga_registration_surcharges")

    # Fetch and order surcharges by number
    ctx["list"] = RegistrationSurcharge.objects.filter(event=ctx["event"]).order_by("number")

    return render(request, "larpmanager/orga/registration/surcharges.html", ctx)


@login_required
def orga_registration_surcharges_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_surcharges", OrgaRegistrationSurchargeForm, num)
