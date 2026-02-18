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
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.forms.registration import RegistrationTransferForm
from larpmanager.models.event import Run
from larpmanager.models.registration import Registration
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.services.event import reset_all_run
from larpmanager.utils.services.transfer import (
    get_suggested_ticket_mapping,
    move_registration_between_runs,
    validate_transfer_feasibility,
)


@login_required
def orga_registration_transfer(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display form to select registration and target run for transfer."""
    context = check_event_context(request, event_slug, "orga_registrations")

    # Initialize the form with context data
    form = RegistrationTransferForm(context=context)
    context["form"] = form
    return render(request, "larpmanager/orga/registration/transfer.html", context)


@login_required
def orga_registration_transfer_preview(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Show preview of what will happen when transferring a registration.

    Args:
        request: HTTP request object containing registration_id and target_run_id
        event_slug: Event slug identifier

    Returns:
        HttpResponse: Rendered preview template or redirect if invalid

    """
    context = check_event_context(request, event_slug, "orga_registrations")

    if request.method != "POST":
        messages.error(request, _("Invalid request"))
        return redirect("orga_registration_transfer", event_slug=event_slug)

    # Get registration and target run from POST data
    registration_id = request.POST.get("registration_id")
    target_run_id = request.POST.get("target_run_id")

    if not registration_id or not target_run_id:
        messages.error(request, _("Please select both a registration and an event"))
        return redirect("orga_registration_transfer", event_slug=event_slug)

    # Get the registration
    try:
        registration = Registration.objects.select_related("member", "ticket", "run").get(
            pk=registration_id, run=context["run"]
        )
    except ObjectDoesNotExist:
        messages.error(request, _("Registration not found"))
        return redirect("orga_registration_transfer", event_slug=event_slug)

    # Get the target run
    try:
        target_run = Run.objects.select_related("event").get(pk=target_run_id)
    except ObjectDoesNotExist:
        messages.error(request, _("Target event not found"))
        return redirect("orga_registration_transfer", event_slug=event_slug)

    # Validate transfer feasibility
    validation_result = validate_transfer_feasibility(registration, target_run)

    context["registration"] = registration
    context["target_run"] = target_run
    context["validation"] = validation_result

    # Get suggested ticket mapping
    context["ticket_mapping"] = get_suggested_ticket_mapping(registration.run, target_run)

    return render(request, "larpmanager/orga/registration/transfer_preview.html", context)


@login_required
@require_POST
def orga_registration_transfer_confirm(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Execute the registration transfer.

    Args:
        request: HTTP request object containing registration_id and target_run_id
        event_slug: Event slug identifier

    Returns:
        HttpResponse: Redirect to registrations page with success/error message

    """
    context = check_event_context(request, event_slug, "orga_registrations")

    # Get registration and target run from POST data
    registration_id = request.POST.get("registration_id")
    target_run_id = request.POST.get("target_run_id")
    move_registration = request.POST.get("move_registration", "true") == "true"

    if not registration_id or not target_run_id:
        messages.error(request, _("Invalid request"))
        return redirect("orga_registration_transfer", event_slug=event_slug)

    # Get the registration
    try:
        registration = Registration.objects.select_related("member", "ticket", "run").get(
            pk=registration_id, run=context["run"]
        )
    except ObjectDoesNotExist:
        messages.error(request, _("Registration not found"))
        return redirect("orga_registration_transfer", event_slug=event_slug)

    # Get the target run
    try:
        target_run = Run.objects.select_related("event").get(pk=target_run_id)
    except ObjectDoesNotExist:
        messages.error(request, _("Target session not found"))
        return redirect("orga_registration_transfer", event_slug=event_slug)

    # Execute the transfer
    try:
        move_registration_between_runs(
            registration=registration,
            target_run=target_run,
            preserve_choices=True,
            preserve_answers=True,
            preserve_accounting=True,
        )

        action = _("moved") if move_registration else _("copied")
        member_name = registration.member.display_member()
        messages.success(
            request,
            _("Registration for %(member)s successfully %(action)s to %(event)s")
            % {"member": member_name, "action": action, "event": target_run},
        )

        # Clear all relevant caches for both source and target runs
        reset_all_run(context["run"].event, context["run"])
        reset_all_run(target_run.event, target_run)

        return redirect("orga_registrations", event_slug=context["run"].get_slug())

    except ValidationError as e:
        messages.error(request, str(e))
        return redirect("orga_registration_transfer", event_slug=event_slug)
