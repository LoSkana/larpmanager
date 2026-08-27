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
import secrets
import traceback
from datetime import timedelta
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.accounting.base import is_registration_provisional
from larpmanager.accounting.member import info_accounting
from larpmanager.accounting.registration import cancel_reg
from larpmanager.cache.association_text import get_association_text
from larpmanager.cache.basic import get_run_basic_cache
from larpmanager.cache.config import get_association_config, get_event_config
from larpmanager.cache.event_text import get_event_text
from larpmanager.cache.feature import get_association_features
from larpmanager.forms.base import get_question_key
from larpmanager.forms.registration import (
    PreRegistrationForm,
    RegistrationForm,
    RegistrationGiftForm,
    RequestApprovalForm,
)
from larpmanager.mail.registration import send_registration_request_received_email
from larpmanager.models.access import get_event_organizers
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    Discount,
)
from larpmanager.models.association import AssociationTextType
from larpmanager.models.event import (
    DevelopStatus,
    Event,
    EventTextType,
    PreRegistration,
    RegistrationStatus,
    Run,
)
from larpmanager.models.member import MembershipStatus
from larpmanager.models.registration import (
    Registration,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.utils.core.base import get_context, get_event, get_event_context
from larpmanager.utils.core.common import get_object_uuid
from larpmanager.utils.core.exceptions import (
    RedirectError,
    RewokedMembershipError,
    check_event_feature,
)
from larpmanager.utils.core.headers import get_url, hdr
from larpmanager.utils.edit.backend import user_edit
from larpmanager.utils.larpmanager.tasks import my_send_mail
from larpmanager.utils.registrations.casting_status import casting_preferences_pending
from larpmanager.utils.registrations.context import (
    _register_prepare,
    get_registration_gift,
)
from larpmanager.utils.registrations.discount import _check_discount
from larpmanager.utils.registrations.save import save_registration
from larpmanager.utils.registrations.signals import get_reduced_available_count
from larpmanager.utils.registrations.status import _set_membership_context

logger = logging.getLogger(__name__)


@login_required
def pre_register(request: HttpRequest, event_slug: str = "") -> HttpResponse:
    """Handle pre-registration for events before full registration opens.

    Allows users to express interest in events and set preference order,
    optionally with additional information. Manages list of existing
    pre-registrations and creates new ones.

    Args:
        request: HTTP request object with authenticated user
        event_slug: Optional event slug to pre-register for specific event, empty shows all

    Returns:
        HttpResponse: Pre-registration form page or redirect after successful save

    Side effects:
        - Creates PreRegistration records linking member to events
        - Saves preference order and additional info

    """
    # Handle specific event pre-registration vs all events listing
    if event_slug:
        # Get context for specific event and verify pre-register feature is active
        context = get_event(request, event_slug)
        context["sel"] = context["event"].uuid
        check_event_feature(request, context, "pre_register")

        status = context["run"].registration_status
        if status != RegistrationStatus.PRE:
            return redirect("register", event_slug=event_slug)

    else:
        # Show all available events for pre-registration
        context = get_context(request)
        context.update({"features": get_association_features(context["association_id"])})

    # Initialize event lists for template
    context["choices"] = []  # Events available for new pre-registration
    context["already"] = []  # Events user has already pre-registered for

    # Check if preference ordering is enabled
    context["preferences"] = get_association_config(context["association_id"], "pre_reg_preferences")

    # Build set of already pre-registered event IDs
    ch = {}
    que = PreRegistration.objects.filter(member=context["member"], event__association_id=context["association_id"])
    for el in que.order_by("pref"):
        ch[el.event_id] = True
        context["already"].append(el)

    # Find events available for pre-registration (events with at least one run in PRE status)
    seen_events = set()
    for run in Run.objects.filter(
        event__association_id=context["association_id"],
        event__template=False,
        registration_status=RegistrationStatus.PRE,
    ).select_related("event"):
        # Skip if we've already processed this event
        if run.event_id in seen_events:
            continue
        seen_events.add(run.event_id)

        # Skip if user already pre-registered
        if run.event_id in ch:
            continue

        context["choices"].append(run.event)

    # Handle form submission for new pre-registration
    if request.method == "POST":
        form = PreRegistrationForm(request.POST, context=context)
        if form.is_valid():
            new_event_uuid = form.cleaned_data["new_event"]
            # Only save if an event was actually selected
            if new_event_uuid != "":
                with transaction.atomic():
                    new_event = get_object_uuid(Event, new_event_uuid)
                    # Get new_pref from form or stored default if field was removed
                    new_pref = getattr(form, "_default_new_pref", form.cleaned_data.get("new_pref"))
                    PreRegistration(
                        member=context["member"],
                        event=new_event,
                        pref=new_pref,
                        info=form.cleaned_data["new_info"],
                    ).save()

            messages.success(request, _("Pre-registrations saved!"))
            return redirect("pre_register")
    else:
        form = PreRegistrationForm(context=context)
    context["form"] = form

    return render(request, "larpmanager/general/pre_register.html", context)


@login_required
def pre_register_remove(request: HttpRequest, event_slug: str) -> Any:
    """Remove user's pre-registration for an event."""
    context = get_event(request, event_slug)
    element = PreRegistration.objects.filter(member=context["member"], event=context["event"]).first()
    if element:
        element.delete()
        messages.success(request, _("Your pre-registration has been cancelled."))
    else:
        messages.warning(request, _("Pre-registration not found."))
    return redirect("pre_register")


@login_required
def register_exclusive(request: HttpRequest, event_slug: str, secret_code: Any = "", discount_code: Any = "") -> Any:
    """Handle exclusive event registration (delegates to main register function)."""
    return register(request, event_slug, secret_code, discount_code)


def registration_redirect(
    request: HttpRequest,
    context: dict,
    registration: Registration,
    run: Run,
    *,
    is_new_registration: bool,
) -> HttpResponse:
    """Handle post-registration redirect logic.

    Determines the appropriate redirect destination after a user completes
    or updates their event registration. Checks membership requirements,
    payment status, and redirects accordingly.

    Args:
        request: Django HTTP request object containing user and association data
        context: Dict context data
        registration: Registration instance for the current user's registration
        run: Run instance representing the event run being registered for
        is_new_registration: Whether this is a new registration (True) or an update (False)

    Returns:
        HttpResponse: Redirect response to the appropriate next step:
            - Profile page if membership compilation needed
            - Membership application if membership status requires it
            - Payment page if payment is outstanding
            - Event gallery if registration is complete

    Note:
        This function handles the post-registration workflow by checking
        feature flags and user status to determine the next required action.

    """
    # Redirect to profile if membership data not compiled
    if not context["membership"].compiled:
        message = _("To confirm your registration, please fill in your personal profile.")
        messages.success(request, message)
        return redirect("profile")

    # Check if membership feature is enabled and user needs to complete profile
    if "membership" in context["features"]:
        # Check membership status for non-waiting registrations
        membership_status = context["membership"].status
        if (
            membership_status in [MembershipStatus.EMPTY, MembershipStatus.JOINED]
            and registration.ticket.tier != TicketTier.WAITING
        ):
            message = _("To confirm your registration, apply to become a member of the Association.")
            messages.success(request, message)
            return redirect("membership")

    # Redirect to payment page if registration has outstanding payment alert
    if "payment" in context["features"] and registration.alert:
        message = _("To confirm your registration, please pay the amount indicated.")
        messages.success(request, message)
        return redirect("accounting_registration", registration_uuid=registration.uuid)

    # Redirect to casting page if casting is active and preferences not sent yet
    if casting_preferences_pending(run, registration, context["features"], context):
        message = _("Please select your casting preferences")
        messages.success(request, message)
        return redirect("casting", event_slug=run.get_slug())

    # All requirements satisfied - show success message and redirect to event page
    context = {"event": run}
    if is_new_registration:
        # Success message for new registration
        message = _("Registration confirmed at %(event)s!") % context
    else:
        # Success message for registration update
        message = _("Registration updated to %(event)s!") % context

    messages.success(request, message)
    return redirect("event", event_slug=registration.run.get_slug())


def register_info(request: HttpRequest, context: dict, form: object, registration: Any, discount_info: Any) -> None:
    """Display registration information and status.

    Args:
        request: HTTP request object
        context: Context dictionary to populate with registration data
        form: Registration form instance
        registration: Registration object if exists
        discount_info: Discount information

    Side effects:
        Updates context with form data, terms, conditions, and membership status

    """
    context["form"] = form
    context["lang"] = context["member"].language
    context["discount_apply"] = discount_info
    context["custom_text"] = get_event_text(context["event"].id, EventTextType.REGISTER)
    context["event_terms_conditions"] = get_event_text(context["event"].id, EventTextType.TOC)
    context["association_terms_conditions"] = get_association_text(context["association_id"], AssociationTextType.TOC)
    context["hide_unavailable"] = get_event_config(
        context["event"].id, "registration_hide_unavailable", context=context
    )
    context["no_provisional"] = get_event_config(context["event"].id, "payment_no_provisional", context=context)

    init_form_submitted(context, form, request, registration)

    if registration:
        registration.provisional = is_registration_provisional(registration)

    _set_membership_context(
        context,
        context["run"],
        context["member"],
        registration,
        get_run_basic_cache(context["run"].id, context=context),
    )


def init_form_submitted(context: dict, form: object, request: HttpRequest, registration: Any = None) -> None:
    """Initialize form submission data in context.

    Args:
        context: Context dictionary to update
        form: Form object containing questions
        request: HTTP request object with POST data
        registration: Registration object (optional)

    """
    context["submitted"] = request.POST.dict()
    if hasattr(form, "questions"):
        for question in form.questions:
            if question["id"] in form.singles:
                # Use question["uuid"] for form field keys (internal form processing)
                context["submitted"][get_question_key(question)] = str(form.singles[question["id"]].option.uuid)

    if registration:
        if registration.ticket_id:
            context["submitted"]["ticket"] = str(registration.ticket.uuid)
        if registration.quotas:
            context["submitted"]["quotas"] = registration.quotas
        if registration.additionals:
            context["submitted"]["additionals"] = registration.additionals

    if "ticket" in context:
        context["submitted"]["ticket"] = context["ticket"]

    if not context["submitted"].get("ticket") and hasattr(form, "initial") and form.initial.get("ticket"):
        context["submitted"]["ticket"] = str(form.initial["ticket"])


@login_required
def register(
    request: HttpRequest,
    event_slug: str,
    secret_code: str = "",
    discount_code: str = "",
    ticket_uuid: str = "",
) -> HttpResponse:
    """Handle event registration form display and submission.

    Manages the complete registration process including ticket selection,
    form validation, payment processing, and membership verification.

    Args:
        request: Django HTTP request object
        event_slug: Event slug identifier
        secret_code: Optional scenario code for registration context
        discount_code: Optional discount code to apply
        ticket_uuid: if provided, ticket UUID string to select (default: "")

    Returns:
        HttpResponse: Rendered registration page or redirect response

    Raises:
        RewokedMembershipError: When user membership has been revoked

    """
    # Get event and run context with status validation (no visibility check)
    context = get_event_context(request, event_slug, include_status=True, check_visibility=False)
    current_run = context["run"]
    current_event = context["event"]

    # Set up registration context for the current run
    registration = context.get("registration")

    # Prevent new registrations or changes on concluded or cancelled runs: existing ones stay readable
    concluded = current_run.development in [DevelopStatus.DONE, DevelopStatus.CANC]
    if concluded and (not registration or request.method == "POST"):
        msg = _("Registration closed") + " - "
        if current_run.development == DevelopStatus.DONE:
            msg += _("This event has concluded")
        else:
            msg += _("This event has been cancelled")
        messages.warning(request, msg)
        return redirect("event", event_slug=current_run.get_slug())
    context["registration_readonly"] = concluded

    # A pending signup request cannot be edited through the normal form: send back to its status page
    if registration and registration.pending:
        messages.info(request, _("Your signup request is awaiting organizer approval"))
        return redirect("event", event_slug=current_run.get_slug())

    # Apply ticket selection if provided, verifying it belongs to this event
    _apply_ticket(context, ticket_uuid, current_event.pk)

    # Check if payment features are enabled for this association
    context["payment_feature"] = "payment" in get_association_features(context["association_id"])

    # Prepare new registration or load existing one
    is_new_registration = _register_prepare(context, registration)

    # Handle registration redirects for new registrations (skipped is a valid ticket link is provided)
    if is_new_registration and not context.get("ticket"):
        # If the approval process is enabled, players must submit a signup request instead
        if get_event_config(current_event.id, "registration_approval_process", context=context):
            return redirect("request_signup", event_slug=current_run.get_slug())

        redirect_response = _check_redirect_registration(request, context, secret_code)
        if redirect_response:
            return redirect_response

    # Verify user membership status and permissions
    current_membership = context["membership"]
    if current_membership.status in [MembershipStatus.REWOKED]:
        raise RewokedMembershipError

    # Process form submission or display registration form
    if request.method == "POST":
        form = RegistrationForm(request.POST, context=context, instance=registration)
        form.sel_ticket_map(request.POST.get("ticket", ""))
        # Validate form and save registration if valid
        if form.is_valid():
            saved_registration = save_registration(
                context,
                form,
                current_run,
                current_event,
                registration,
            )
            return registration_redirect(
                request, context, saved_registration, current_run, is_new_registration=is_new_registration
            )
    else:
        # Display empty form for GET requests
        form = RegistrationForm(context=context, instance=registration)

    # Prepare additional registration information and render page
    register_info(request, context, form, registration, discount_code)
    return render(request, "larpmanager/event/register.html", context)


def _apply_ticket(context: dict, ticket_uuid: str | None, event_id: int) -> None:
    """Apply ticket information to context if ticket exists and belongs to the event.

    Args:
        context: Context dictionary to update with ticket data
        ticket_uuid: Ticket UUID string to retrieve, or None
        event_id: Event ID to verify ticket ownership

    """
    if not ticket_uuid:
        return

    # Retrieve ticket and verify it belongs to the event
    ticket = get_object_uuid(RegistrationTicket, ticket_uuid, event_id=event_id)
    context["tier"] = ticket.tier
    run_status = context.get("run_status", {})

    try:
        # Remove closed status for staff/NPC tickets
        if ticket.tier in [TicketTier.STAFF, TicketTier.NPC] and "closed" in run_status:
            del run_status["closed"]

        # Store ticket UUID in context (used for form initialization)
        context["ticket"] = str(ticket.uuid)
    except ObjectDoesNotExist:
        # Ticket not found or doesn't belong to this event - ignore silently
        pass


@login_required
def request_signup(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Player-facing page to submit a signup approval request when the approval process is enabled."""
    context = get_event_context(request, event_slug, include_status=True, check_visibility=False)
    current_run = context["run"]
    current_event = context["event"]

    if not get_event_config(current_event.id, "registration_approval_process", context=context):
        raise Http404

    # Already has a registration (pending or confirmed): nothing to request
    if context.get("registration"):
        return redirect("register", event_slug=current_run.get_slug())

    pending_instance = Registration(run=current_run, member=context["member"])

    if request.method == "POST":
        form = RequestApprovalForm(request.POST, instance=pending_instance, context=context)
        if form.is_valid():
            saved_registration = form.save()
            send_registration_request_received_email(saved_registration)
            messages.success(request, _("Your signup request has been submitted!"))
            return redirect("event", event_slug=current_run.get_slug())
    else:
        form = RequestApprovalForm(instance=pending_instance, context=context)

    context["form"] = form
    context["approval_text"] = get_event_text(
        current_event.id, EventTextType.REGISTRATION_APPROVAL, context["member"].language
    )

    return render(request, "larpmanager/event/request_signup.html", context)


def _check_redirect_registration(request: HttpRequest, context: dict, secret_code: str | None) -> HttpResponse | None:  # noqa: PLR0911
    """Check if registration should be redirected based on event status and settings.

    This function performs various checks to determine if a user's registration
    attempt should be redirected or blocked based on event configuration,
    timing, and access controls.

    Args:
        request: Django HTTP request object containing user and session data
        context: Context dictionary containing event, run data, features, and tier info
        event: Event model instance being registered for
        secret_code: Optional secret code for registration access, None if not provided

    Returns:
        HttpResponse object for redirect/error pages if registration should be
        blocked or redirected, None if registration can proceed normally

    Raises:
        Http404, if an invalid registration secret code is provided when secret
        registration is enabled

    """
    # Check if event registration is closed
    if "closed" in context.get("run_status", {}):
        return render(request, "larpmanager/event/closed.html", context)

    # Validate secret code if secret registration is enabled
    if "registration_secret" in context["features"] and secret_code:
        # Constant-time compare to avoid leaking the code via timing
        if not secrets.compare_digest(str(context["run"].registration_secret or ""), str(secret_code)):
            msg = _("The registration code is not active at the moment")
            messages.warning(request, msg)
            return redirect("register", event_slug=context["event"].slug)
        # Secret code is correct, allow registration bypassing other checks
        return None

    # Get registration status from run
    registration_status = context["run"].registration_status

    # Handle closed status
    if registration_status == RegistrationStatus.CLOSED:
        return render(request, "larpmanager/event/not_open.html", context)

    # Redirect to external registration link if configured
    # Skip redirect for staff and NPC tiers who register internally
    if (
        registration_status == RegistrationStatus.EXTERNAL
        and context["run"].register_link
        and ("tier" not in context or context["tier"] not in [TicketTier.STAFF, TicketTier.NPC])
    ):
        return redirect(context["run"].register_link)

    # Check registration timing for future opening
    if registration_status == RegistrationStatus.FUTURE and (
        not context["run"].registration_open or context["run"].registration_open > timezone.now()
    ):
        return render(request, "larpmanager/event/not_open.html", context)

    # Handle pre-registration status - redirect to pre-register page
    if registration_status == RegistrationStatus.PRE:
        return redirect("pre_register", event_slug=context["event"].slug)

    return None


def register_reduced(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Return count of available reduced-price tickets for an event run."""
    context = get_event_context(request, event_slug, check_visibility=False)
    # Count reduced tickets still available for this run
    ct = get_reduced_available_count(context["run"])
    return JsonResponse({"res": ct})


@login_required
def register_conditions(request: HttpRequest, event_slug: str | None = None) -> HttpResponse:
    """Render registration conditions page with event and association terms.

    Args:
        request: HTTP request object
        event_slug: Optional event slug for event-specific conditions

    Returns:
        Rendered HTML response with terms and conditions

    """
    # Initialize base user context
    context = get_context(request)

    # Add event-specific context if event slug provided
    if event_slug:
        context["event"] = get_event(request, event_slug)["event"]
        context["event_text"] = get_event_text(context["event"].id, EventTextType.TOC)

    # Add association terms and conditions
    context["association_text"] = get_association_text(context["association_id"], AssociationTextType.TOC)

    return render(request, "larpmanager/event/register_conditions.html", context)


# ~ def discount_bring_friend(request: HttpRequest, context: dict, cod):
# ~ # check if there is a registration with that cod
# ~ try:
# ~ friend = Registration.objects.get(uuid=cod)
# ~ except Exception as e:
# ~ Return jsonrespone ({'really': 'ko', 'msg': _ ("Discount code not valid")})
# ~ if friend.member == context["member"]:
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('Nice Try! But no, I'm sorry.')})
# ~ # check same event
# ~ if friend.run.event != context['event']:
# ~ Return Jsonresonse ({'res': 'ko', 'msg': _ ('Code applicable only to run of the same event!')})
# ~ # check future run
# ~ if friend.run.end < timezone.now().date():
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('Code not valid for runs passed!')})
# ~ # get discount friend
# ~ disc = Discount.objects.get(typ=DiscountType.FRIEND, runs__in=[context['run']])
# ~ if disc.max_redeem > 0:
# ~ if AccountingItemDiscount.objects.filter(disc=disc, run=context['run']).count() > disc.max_redeem:
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('We are sorry, the maximum number of concessions has been reached a friend')})
# ~ # check if not already registered
# ~ try:
# ~ reg = Registration.objects.get(member=context["member"], run=context['run'])
# ~ if disc.only_reg:
# ~ Return jsonrespone ({'really': 'ko', 'msg': _ ("Discounts only applicable with new registrations")})
# ~ except Exception as e:
# ~ pass
# ~ # check there are no discount stores a friend
# ~ if AccountingItemDiscount.objects.filter(member=context["member"], run=context['run'], disc__typ=DiscountType.STANDARD).count() > 0:
# ~ Return jsonrespone ({'really': 'ko', 'msg': _ ("Discount not combinable with other benefits.")})
# ~ # check the user TO don't already have the discount
# ~ try:
# ~ ac = AccountingItemDiscount.objects.get(disc=disc, member=context["member"], run=context['run'])
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('You have already used a personal code')})
# ~ except Exception as e:
# ~ pass
# ~ if AccountingItemDiscount.objects.filter(member=context["member"], run=context['run'], disc__typ=DiscountType.PLAYAGAIN).count() > 0:
@login_required
@require_POST
def discount(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Handle discount code application for user registration.

    This function validates and applies discount codes for event registrations,
    creating temporary discount reservations that expire after 15 minutes.

    Args:
        request: Django HTTP request object containing POST data with discount code
        event_slug: Event slug identifier used to retrieve the event context

    Returns:
        JsonResponse: JSON response containing either success message with
                     reservation details or error message with validation failure

    Raises:
        ObjectDoesNotExist: When discount code is not found for the event run

    """

    def error(msg: str) -> JsonResponse:
        """Return a JSON error response."""
        return JsonResponse({"res": "ko", "msg": msg})

    # Get event context and validate discount feature availability
    context = get_event_context(request, event_slug, check_visibility=False)

    if "discount" not in context["features"]:
        return error(_("Not available, kiddo"))

    # Extract and validate discount code from request
    cod = request.POST.get("cod")
    try:
        disc = Discount.objects.filter(runs__in=[context["run"]], cod=cod).distinct().get()
    except ObjectDoesNotExist:
        # Strip CR/LF from the user-supplied code before logging
        safe_cod = str(cod).replace("\r", "").replace("\n", "") if cod else cod
        logger.warning("Discount code not found: %s", safe_cod)
        logger.debug(traceback.format_exc())
        return error(_("Discount code not valid"))

    # Clean up expired discount reservations
    now = timezone.now()
    AccountingItemDiscount.objects.filter(expires__lte=now).delete()

    # Extract context variables for discount validation
    member = context["member"]
    run = context["run"]
    event = context["event"]

    # Validate eligibility and reserve atomically to prevent race conditions
    with transaction.atomic():
        # Lock the discount row so concurrent requests serialise here
        disc = Discount.objects.select_for_update().get(pk=disc.pk)

        check = _check_discount(disc, member, run, event)
        if check:
            return error(check)

        # Create temporary discount reservation with 15-minute expiration
        AccountingItemDiscount.objects.create(
            value=disc.value,
            member=member,
            expires=now + timedelta(minutes=15),
            disc=disc,
            run=run,
            association_id=context["association_id"],
        )

    # Return success response with reservation confirmation
    return JsonResponse(
        {
            "res": "ok",
            "msg": _(
                "The discount has been added! It has been reserved for you for 15 minutes, after which it will be removed",
            ),
        },
    )


@login_required
def discount_list(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Get list of valid discount items for the current user and event run.

    This function retrieves all non-expired discount items for the authenticated user
    within the specified event run context. Expired items are automatically cleaned up.

    Args:
        request: The HTTP request object containing user authentication
        event_slug: Event slug identifier

    Returns:
        JsonResponse containing a list of discount items with name, value, and expiration

    """
    # Get the event run context from the request and identifier
    context = get_event_context(request, event_slug, check_visibility=False)
    now = timezone.now()

    # Bulk delete expired discount items for this user and run
    AccountingItemDiscount.objects.filter(member=context["member"], run=context["run"], expires__lte=now).delete()

    # Get remaining valid discount items with optimized query
    # Filter for current user/run and non-expired items
    discount_items = (
        AccountingItemDiscount.objects.filter(member=context["member"], run=context["run"])
        .select_related("disc")
        .filter(models.Q(expires__isnull=True) | models.Q(expires__gt=now))
    )

    # Build response list efficiently
    # Convert discount items to JSON-serializable format
    lst = []
    for aid in discount_items:
        j = {"name": aid.disc.name, "value": aid.value}
        # Format expiration time or set empty string for permanent discounts
        if aid.expires:
            j["expires"] = aid.expires.strftime("%H:%M")
        else:
            j["expires"] = ""
        lst.append(j)

    return JsonResponse({"lst": lst})


@login_required
def unregister(request: HttpRequest, event_slug: str) -> Any:
    """Handle user cancellation from an event.

    If player_cancellation_disable is set, sends a cancellation request email to organizers
    instead of cancelling directly, and notifies the player to wait for staff response.
    """
    context = get_event_context(request, event_slug, signup=True, include_status=True)

    # check if user is actually registered
    try:
        registration = Registration.objects.get(
            run=context["run"], member=context["member"], cancellation_date__isnull=True
        )
    except ObjectDoesNotExist as err:
        msg = "Registration does not exist"
        raise Http404(msg) from err

    cancellation_disabled = get_event_config(context["event"].id, "player_cancellation_disable", context=context)

    if request.method == "POST":
        if cancellation_disabled:
            member = context["member"]
            run = context["run"]
            event = context["event"]

            cancel_url = get_url(
                f"{run.get_slug()}/manage/registrations/{registration.uuid}/delete/",
                event,
            )
            email_context = {"event": run, "user": member}
            email_subject = hdr(event) + _("Cancellation request for %(event)s") % email_context
            email_body = (
                _("The participant <b>%(user)s</b> has requested to cancel their registration for <b>%(event)s</b>")
                % email_context
            )
            email_body += ".<br /><br />"
            email_body += _("To process the cancellation, click here:") + " "
            email_body += f"<a href='{cancel_url}'>{cancel_url}</a>"
            for organizer in get_event_organizers(run.id):
                my_send_mail(email_subject, email_body, organizer, run)

            mes = _("Your cancellation request has been sent to the staff; please wait for their response")
            messages.success(request, mes)
        else:
            cancel_reg(registration)
            mes = _("Your registration for %(event)s has been cancelled.") % {"event": context["event"]}
            messages.success(request, mes)
        return redirect("accounting")

    context["registration"] = registration
    context["event_terms_conditions"] = get_event_text(context["event"].id, EventTextType.TOC)
    context["association_terms_conditions"] = get_association_text(context["association_id"], AssociationTextType.TOC)
    return render(request, "larpmanager/event/unregister.html", context)


@login_required
def gift(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display gift registrations and their payment status for the current user.

    This view shows all gift registrations (registrations with redeem codes) for the
    current user in a specific event run, along with their payment status and accounting
    information.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: Event slug identifier

    Returns:
        HttpResponse: Rendered gift.html template containing the registration list
        and payment information context

    Raises:
        Http404: If the event or run is not found
        PermissionDenied: If registration is not open or user lacks permissions

    """
    # Get event context and verify registration access
    context = get_event_context(request, event_slug, feature_slug="gift", include_status=True, check_visibility=False)
    check_registration_open(context, request)

    # Filter registrations for current user with redeem codes (gift registrations)
    context["list"] = Registration.objects.filter(
        run=context["run"],
        member=context["member"],
        redeem_code__isnull=False,
        cancellation_date__isnull=True,
    )

    # Load accounting information (payments, pending transactions, etc.)
    info_accounting(context)

    # Attach payment and accounting info to each registration
    for registration in context["list"]:
        # Check for pending payments
        for el in context["payments_todo"]:
            if registration.id == el.id:
                registration.payment = el

        # Check for pending transactions
        for el in context["payments_pending"]:
            if registration.id == el.id:
                registration.pending = el

        # Attach additional registration info
        for el in context["registration_list"]:
            if registration.id == el.id:
                registration.info = el

    return render(request, "larpmanager/event/gift.html", context)


def check_registration_open(context: dict, request: HttpRequest) -> None:
    """Check if registrations are open, redirect to home if closed."""
    if not context.get("run_status", {})["open"]:
        messages.warning(request, _("Registrations not open!"))
        msg = "home"
        raise RedirectError(msg)


@login_required
def gift_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create new gift registration."""
    return _form_gift(request, event_slug)


@login_required
def gift_edit(request: HttpRequest, event_slug: str, gift_uuid: str) -> HttpResponse:
    """Edit a gift registration."""
    return _form_gift(request, event_slug, gift_uuid)


def _form_gift(request: HttpRequest, event_slug: str, gift_uuid: str | None = None) -> HttpResponse:
    """Handle gift registration modifications.

    This function manages the editing of gift registrations, allowing users to
    modify gift card details or cancel them entirely. It validates permissions,
    handles form processing, and manages the gift registration lifecycle.

    Args:
        request: The HTTP request object containing user data and form submission
        event_slug: Event identifier string used to locate the specific event
        gift_uuid: The registration UUID to be gifted

    Returns:
        HttpResponse: Either renders the gift edit form template or redirects
        to the gift list page after successful save/cancel operations

    Raises:
        Http404: If the event, run, or registration cannot be found
        PermissionDenied: If user lacks permission to edit gift registrations

    """
    # Get event context and verify user has gift management permissions
    context = get_event_context(request, event_slug, feature_slug="gift", include_status=True, check_visibility=False)
    check_registration_open(context, request)

    # Retrieve the specific gift registration and prepare form context
    registration = get_registration_gift(context, gift_uuid)
    context["registration"] = registration
    _register_prepare(context, registration)

    # Define custom save callback for gift registrations
    def save_gift_callback(form: RegistrationGiftForm, ctx: dict) -> Registration:
        """Save gift registration using the specialized save_registration function."""
        return save_registration(ctx, form, ctx["run"], ctx["event"], registration, gifted=True)

    # Define custom delete callback for gift registrations
    def delete_gift_callback(reg: Registration) -> None:
        """Cancel gift registration using the specialized cancel_reg function."""
        cancel_reg(reg)

    # Use user_edit to handle form processing with custom callbacks
    if user_edit(
        request,
        context,
        RegistrationGiftForm,
        "registration",
        gift_uuid,
        save_callback=save_gift_callback,
        delete_callback=delete_gift_callback,
    ):
        # Redirect back to gift list after successful operation
        return redirect("gift", event_slug=event_slug)

    # Prepare context for template rendering
    context["gift"] = True

    # Initialize form submission state and validation
    init_form_submitted(context, context["form"], request, registration)

    return render(request, "larpmanager/event/gift_edit.html", context)


@login_required
def gift_redeem(request: HttpRequest, event_slug: str, code: str) -> HttpResponse:
    """Handle gift code redemption for event registrations.

    Processes the redemption of a gift code for event registrations. If the user
    is already registered for the event, they are redirected with a success message.
    Otherwise, the function handles both GET (display form) and POST (process redemption)
    requests for gift code redemption.

    Args:
        request (HttpRequest): The HTTP request object containing user and method info
        event_slug (str): Event slug identifier for the specific event
        code (str): Gift redemption code to be validated and processed

    Returns:
        HttpResponse: Either renders the redemption form template for GET requests
                     or redirects to the event page after successful redemption

    Raises:
        Http404: When no valid registration is found matching the provided code
                and association constraints

    """
    # Get event context and validate user permissions for gift redemption
    context = get_event_context(request, event_slug, feature_slug="gift", include_status=True, check_visibility=False)

    # Check if user is already registered for this event
    if context["registration"]:
        messages.success(request, _("You cannot redeem a membership, you are already a member!"))
        return redirect("event", event_slug=context["run"].get_slug())

    # Attempt to find valid registration with the provided redemption code
    try:
        registration = Registration.objects.get(
            redeem_code=code,
            cancellation_date__isnull=True,
            run__event__association_id=context["association_id"],
        )
    except Exception as err:
        msg = "registration not found"
        raise Http404(msg) from err

    # Process POST request - complete the gift redemption
    if request.method == "POST":
        # Use atomic transaction to ensure data consistency during redemption
        with transaction.atomic():
            registration.member = context["member"]
            registration.redeem_code = None
            registration.save()

        # Notify user of successful redemption and redirect to event page
        messages.success(request, _("Your gifted registration has been redeemed!"))
        return redirect("event", event_slug=context["run"].get_slug())

    # Add registration object to context for template rendering
    context["registration"] = registration

    return render(request, "larpmanager/event/gift_redeem.html", context)
