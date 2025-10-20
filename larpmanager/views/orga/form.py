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
    """
    Handle registration tickets management for event organizers.

    Displays a list of registration tickets for an event and handles ticket downloads.
    Requires 'orga_registration_tickets' permission to access.

    Args:
        request: HTTP request object containing user and POST data
        s: Event slug identifier for permission checking

    Returns:
        HttpResponse: Rendered tickets template or download response
    """
    # Check user permissions for managing registration tickets
    ctx = check_event_permission(request, s, "orga_registration_tickets")

    # Handle ticket download request via POST
    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_tickets_download(ctx)

    # Set template context for upload and download functionality
    ctx["upload"] = "registration_tickets"
    ctx["download"] = 1

    # Fetch ordered list of registration tickets for the event
    ctx["list"] = RegistrationTicket.objects.filter(event=ctx["event"]).order_by("order")
    # Get available ticket tiers for the event
    ctx["tiers"] = OrgaRegistrationTicketForm.get_tier_available(ctx["event"])

    return render(request, "larpmanager/orga/registration/tickets.html", ctx)


@login_required
def orga_registration_tickets_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_tickets", OrgaRegistrationTicketForm, num)


@login_required
def orga_registration_tickets_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_registration_tickets")
    exchange_order(ctx, RegistrationTicket, num, order)
    return redirect("orga_registration_tickets", s=ctx["run"].get_slug())


@login_required
def orga_registration_sections(request, s):
    ctx = check_event_permission(request, s, "orga_registration_sections")
    ctx["list"] = RegistrationSection.objects.filter(event=ctx["event"]).order_by("order")
    return render(request, "larpmanager/orga/registration/sections.html", ctx)


@login_required
def orga_registration_sections_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_sections", OrgaRegistrationSectionForm, num)


@login_required
def orga_registration_sections_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_registration_sections")
    exchange_order(ctx, RegistrationSection, num, order)
    return redirect("orga_registration_sections", s=ctx["run"].get_slug())


@login_required
def orga_registration_form(request: HttpRequest, s: str) -> HttpResponse:
    """
    Handle organization registration form view and download functionality.

    Args:
        request: The HTTP request object containing method and POST data
        s: The event slug identifier for permission checking

    Returns:
        HttpResponse: Either a file download response or rendered template
    """
    # Check user permissions for accessing organization registration forms
    ctx = check_event_permission(request, s, "orga_registration_form")

    # Handle form download request if POST method with download flag
    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_registration_form_download(ctx)

    # Set context variables for template rendering
    ctx["upload"] = "registration_form"
    ctx["download"] = 1

    # Fetch ordered registration questions with prefetched options for efficiency
    ctx["list"] = get_ordered_registration_questions(ctx).prefetch_related("options")

    # Add ordered options list to each registration question object
    for el in ctx["list"]:
        el.options_list = el.options.order_by("order")

    return render(request, "larpmanager/orga/registration/form.html", ctx)


@login_required
def orga_registration_form_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """
    Handle registration form question editing for organizers.

    This function allows organizers to edit registration form questions, including
    creating new questions and managing question options for single/multiple choice types.

    Parameters
    ----------
    request : HttpRequest
        The HTTP request object containing form data and user information
    s : str
        Event slug identifier for the specific event
    num : int
        Question number/ID to edit (0 for new question creation)

    Returns
    -------
    HttpResponse
        Either a rendered form edit page or a redirect response after successful save

    Notes
    -----
    - Automatically redirects to option creation for single/multiple choice questions
    - Validates that choice questions have at least one option before saving
    - Supports continuation workflow for creating multiple questions
    """
    # Check user permissions for registration form editing
    perm = "orga_registration_form"
    ctx = check_event_permission(request, s, perm)

    # Process form submission and handle save logic
    if backend_edit(request, ctx, OrgaRegistrationQuestionForm, num, assoc=False):
        set_suggestion(ctx, perm)

        # Handle continue workflow - redirect to create another question
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, s=ctx["run"].get_slug(), num=0)

        # Determine if we need to edit options for this question type
        edit_option = False
        if str(request.POST.get("new_option", "")) == "1":
            edit_option = True
        elif ctx["saved"].typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
            # Check if single/multiple choice questions have required options
            if not RegistrationOption.objects.filter(question_id=ctx["saved"].id).exists():
                edit_option = True
                messages.warning(
                    request,
                    _("You must define at least one option before saving a single-choice or multiple-choice question"),
                )

        # Redirect to option editing if needed, otherwise return to main form list
        if edit_option:
            return redirect(orga_registration_options_new, s=ctx["run"].get_slug(), num=ctx["saved"].id)
        return redirect(perm, s=ctx["run"].get_slug())

    # Load existing options for display in the edit form
    ctx["list"] = RegistrationOption.objects.filter(question=ctx["el"]).order_by("order")
    return render(request, "larpmanager/orga/registration/form_edit.html", ctx)


@login_required
def orga_registration_form_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_registration_form")
    exchange_order(ctx, RegistrationQuestion, num, order)
    return redirect("orga_registration_form", s=ctx["run"].get_slug())


@login_required
def orga_registration_options_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit registration options for an event.

    This function handles the editing of registration options for a specific event.
    It first checks if the user has permission to access the registration form,
    then verifies that registration questions exist before allowing option creation.

    Args:
        request: The HTTP request object containing user and session data
        s: The event slug identifier as a string
        num: The registration option number to edit as an integer

    Returns:
        HttpResponse: Either a redirect to the registration questions page if no
        questions exist, or the result of registration_option_edit function

    Raises:
        PermissionDenied: If user lacks required event permissions
    """
    # Check user permissions for accessing registration form functionality
    ctx = check_event_permission(request, s, "orga_registration_form")

    # Verify that at least one registration question exists for this event
    # Registration options require questions to be meaningful
    if not ctx["event"].get_elements(RegistrationQuestion).exists():
        # Display warning message to inform user about missing prerequisite
        messages.warning(
            request, _("You must create at least one registration question before you can create registration options")
        )
        # Redirect to registration questions creation page
        return redirect("orga_registration_form_edit", s=s, num=0)

    # Proceed with registration option editing if all prerequisites are met
    return registration_option_edit(ctx, num, request)


@login_required
def orga_registration_options_new(request, s, num):
    ctx = check_event_permission(request, s, "orga_registration_form")
    ctx["question_id"] = num
    return registration_option_edit(ctx, 0, request)


def registration_option_edit(ctx: dict, num: int, request: HttpRequest) -> HttpResponse:
    """
    Handle editing of registration option with form processing and redirect logic.

    Args:
        ctx: Context dictionary containing event and form data, including 'run' and 'saved' keys
        num: Option number/ID being edited for the registration form
        request: HTTP request object containing POST data and user information

    Returns:
        HttpResponse: Redirect response to next step or rendered edit form template

    Note:
        Uses backend_edit to process the OrgaRegistrationOptionForm. On successful edit,
        redirects to either the form edit view or new options view based on POST data.
    """
    # Process the registration option form using backend edit helper
    # Returns True if form was successfully processed and saved
    if backend_edit(request, ctx, OrgaRegistrationOptionForm, num, assoc=False):
        # Default redirect target is back to the form edit view
        redirect_target = "orga_registration_form_edit"

        # Check if user wants to continue adding more options
        if "continue" in request.POST:
            redirect_target = "orga_registration_options_new"

        # Redirect with the run slug and saved question ID as parameters
        return redirect(redirect_target, s=ctx["run"].get_slug(), num=ctx["saved"].question_id)

    # If form processing failed or this is a GET request, render the edit template
    return render(request, "larpmanager/orga/edit.html", ctx)


@login_required
def orga_registration_options_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_registration_form")
    exchange_order(ctx, RegistrationOption, num, order)
    return redirect("orga_registration_form_edit", s=ctx["run"].get_slug(), num=ctx["current"].question_id)


@login_required
def orga_registration_quotas(request, s):
    ctx = check_event_permission(request, s, "orga_registration_quotas")
    ctx["list"] = RegistrationQuota.objects.filter(event=ctx["event"]).order_by("number")
    return render(request, "larpmanager/orga/registration/quotas.html", ctx)


@login_required
def orga_registration_quotas_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_quotas", OrgaRegistrationQuotaForm, num)


@login_required
def orga_registration_installments(request, s):
    ctx = check_event_permission(request, s, "orga_registration_installments")
    ctx["list"] = RegistrationInstallment.objects.filter(event=ctx["event"]).order_by("order", "amount")
    return render(request, "larpmanager/orga/registration/installments.html", ctx)


@login_required
def orga_registration_installments_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_installments", OrgaRegistrationInstallmentForm, num)


@login_required
def orga_registration_surcharges(request, s):
    ctx = check_event_permission(request, s, "orga_registration_surcharges")
    ctx["list"] = RegistrationSurcharge.objects.filter(event=ctx["event"]).order_by("number")
    return render(request, "larpmanager/orga/registration/surcharges.html", ctx)


@login_required
def orga_registration_surcharges_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_surcharges", OrgaRegistrationSurchargeForm, num)
