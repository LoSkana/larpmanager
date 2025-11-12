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

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.accounting.member import info_accounting
from larpmanager.accounting.registration import cancel_reg
from larpmanager.cache.association_text import get_association_text
from larpmanager.cache.config import get_association_config, get_event_config
from larpmanager.cache.event_text import get_event_text
from larpmanager.cache.feature import get_association_features
from larpmanager.forms.registration import (
    PreRegistrationForm,
    RegistrationForm,
    RegistrationGiftForm,
)
from larpmanager.mail.base import bring_friend_instructions
from larpmanager.mail.registration import update_registration_status_bkg
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemMembership,
    AccountingItemOther,
    Discount,
    DiscountType,
    OtherChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
)
from larpmanager.models.association import AssociationTextType
from larpmanager.models.event import (
    Event,
    EventTextType,
    PreRegistration,
    Run,
)
from larpmanager.models.member import Member, MembershipStatus
from larpmanager.models.registration import (
    Registration,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.utils import my_uuid
from larpmanager.utils.base import get_context, get_event, get_event_context
from larpmanager.utils.exceptions import (
    RedirectError,
    RewokedMembershipError,
    check_event_feature,
)
from larpmanager.utils.registration import check_assign_character, get_reduced_available_count

logger = logging.getLogger(__name__)


def _check_pre_register_redirect(context: dict, event_slug: str) -> HttpResponse | None:
    """Check if pre-registration should redirect to regular registration.

    Args:
        context: Event context dictionary
        event_slug: Event slug for redirect URL

    Returns:
        HttpResponse redirect if should redirect, None otherwise

    """
    # Check if pre-registration is active for this specific event
    if not get_event_config(context["event"].id, "pre_register_active", default_value=False):
        return redirect("register", event_slug=event_slug)

    # Check if registration is open and we're past the open date
    if "registration_open" in context["features"]:
        if context["run"].registration_open and context["run"].registration_open <= timezone.now():
            return redirect("register", event_slug=event_slug)

    return None


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
        context["sel"] = context["event"].id
        check_event_feature(request, context, "pre_register")

        # Check if we should redirect to regular registration
        redirect_response = _check_pre_register_redirect(context, event_slug)
        if redirect_response:
            return redirect_response
    else:
        # Show all available events for pre-registration
        context = get_context(request)
        context.update({"features": get_association_features(context["association_id"])})

    # Initialize event lists for template
    context["choices"] = []  # Events available for new pre-registration
    context["already"] = []  # Events user has already pre-registered for

    # Check if preference ordering is enabled
    context["preferences"] = get_association_config(
        context["association_id"], "pre_reg_preferences", default_value=False
    )

    # Build set of already pre-registered event IDs
    ch = {}
    que = PreRegistration.objects.filter(member=context["member"], event__association_id=context["association_id"])
    for el in que.order_by("pref"):
        ch[el.event_id] = True
        context["already"].append(el)

    # Find events available for pre-registration
    for r in Event.objects.filter(association_id=context["association_id"], template=False):
        # Skip if pre-registration not active for this event
        if not get_event_config(r.id, "pre_register_active", default_value=False):
            continue

        # Skip if user already pre-registered
        if r.id in ch:
            continue

        context["choices"].append(r)

    # Handle form submission for new pre-registration
    if request.method == "POST":
        form = PreRegistrationForm(request.POST, context=context)
        if form.is_valid():
            nr = form.cleaned_data["new_event"]
            # Only save if an event was actually selected
            if nr != "":
                with transaction.atomic():
                    PreRegistration(
                        member=context["member"],
                        event_id=nr,
                        pref=form.cleaned_data["new_pref"],
                        info=form.cleaned_data["new_info"],
                    ).save()

            messages.success(request, _("Pre-registrations saved") + "!")
            return redirect("pre_register")
    else:
        form = PreRegistrationForm(context=context)
    context["form"] = form

    return render(request, "larpmanager/general/pre_register.html", context)


@login_required
def pre_register_remove(request: HttpRequest, event_slug: str):
    """Remove user's pre-registration for an event.

    Args:
        request: Django HTTP request object (must be authenticated)
        event_slug: Event slug to remove pre-registration from

    Returns:
        HttpResponse: Redirect to pre-registration list

    """
    context = get_event(request, event_slug)
    element = PreRegistration.objects.get(member=context["member"], event=context["event"])
    element.delete()
    messages.success(request, _("Pre-registration cancelled!"))
    return redirect("pre_register")


@login_required
def register_exclusive(request: HttpRequest, event_slug: str, secret_code="", discount_code=""):
    """Handle exclusive event registration (delegates to main register function).

    Args:
        request: Django HTTP request object
        event_slug: Event slug
        secret_code: Secret code (optional)
        discount_code: Discount code (optional)

    Returns:
        HttpResponse: Result from register function

    """
    return register(request, event_slug, secret_code, discount_code)


def save_registration(
    request: HttpRequest,
    context: dict[str, Any],
    form: Any,  # Registration form instance
    run: Run,
    event: Event,
    reg: Registration | None,
    *,
    gifted: bool = False,
) -> Registration:
    """Save registration data and handle payment processing.

    This function creates or updates a registration record within a database transaction,
    handling standard registration data, questions, discounts, and special features.

    Args:
        request: Django HTTP request object containing user information
        context: Context dictionary with form data, event info, and feature flags
        form: Registration form instance with cleaned data
        run: Run instance being registered for
        event: Event instance associated with the run
        reg: Existing registration instance to update, or None to create new
        gifted: Whether this is a gifted registration requiring redeem code

    Returns:
        Registration: The saved registration instance

    Note:
        This function handles special features like user_character assignment
        and bring_friend functionality based on context feature flags.

    """
    # pprint(form.cleaned_data)  # Debug output for form data

    # Create or update registration within atomic transaction
    with transaction.atomic():
        # Initialize new registration if none provided
        if not reg:
            reg = Registration()
            reg.run = run
            reg.member = context["member"]
            # Generate redeem code for gifted registrations
            if gifted:
                reg.redeem_code = my_uuid(16)
            reg.save()

        # Determine if registration should be provisional
        provisional = is_reg_provisional(reg)

        # Save standard registration fields and data
        save_registration_standard(context, event, form, reg, gifted=gifted, provisional=provisional)

        # Process and save registration-specific questions
        form.save_reg_questions(reg, is_organizer=False)

        # Confirm and finalize any pending discounts for this member/run
        que = AccountingItemDiscount.objects.filter(member=context["member"], run=reg.run)
        for el in que:
            # Remove expiration date to confirm discount usage
            if el.expires is not None:
                el.expires = None
                el.save()

        # Save the updated registration instance
        reg.save()

        # Handle special feature processing based on context flags
        if "user_character" in context["features"]:
            check_assign_character(request, context)
        if "bring_friend" in context["features"]:
            save_registration_bring_friend(context, form, reg, request)

    # Send background notification email for registration update
    update_registration_status_bkg(reg.id)

    return reg


def save_registration_standard(
    context: dict,
    event: Event,
    form: RegistrationForm,
    reg: Registration,
    *,
    gifted: bool,
    provisional: bool,
) -> None:
    """Save standard registration with ticket and payment processing.

    Processes a standard registration by updating modification counter,
    handling additional participants, quotas, ticket selection, and
    custom payment amounts based on form data.

    Args:
        context: Context dictionary containing event and form data, including 'tot_payed'
        event: Event instance for validation and processing
        form: Registration form instance with cleaned_data
        gifted: Whether this is a gifted registration (skips modification counter)
        provisional: Whether registration is provisional (skips modification counter)
        reg: Registration instance to update with form data

    Raises:
        Http404: When ticket doesn't exist, belongs to wrong event, or has lower price
                than current ticket for paid registrations

    Side Effects:
        Modifies the registration instance with form data including:
        - Increments modification counter for non-gifted, non-provisional registrations
        - Updates additionals count, quotas, ticket selection, and payment amount

    """
    # Increment modification counter for standard registrations
    if not gifted and not provisional:
        reg.modified = reg.modified + 1

    # Process additional participants count
    if "additionals" in form.cleaned_data:
        reg.additionals = int(form.cleaned_data["additionals"])

    # Handle quota assignments if present
    if form.cleaned_data.get("quotas"):
        reg.quotas = int(form.cleaned_data["quotas"])

    # Process ticket selection and validation
    if "ticket" in form.cleaned_data:
        try:
            sel = RegistrationTicket.objects.filter(pk=form.cleaned_data["ticket"]).select_related("event").first()
        except Exception as err:
            msg = "RegistrationTicket does not exists"
            raise Http404(msg) from err

        # Validate ticket exists and belongs to correct event
        if sel and sel.event != event:
            msg = "RegistrationTicket wrong event"
            raise Http404(msg)

        # Prevent downgrading ticket price for paid registrations
        if context["tot_payed"] and reg.ticket and reg.ticket.price > 0 and sel.price < reg.ticket.price:
            msg = "lower price"
            raise Http404(msg)
        reg.ticket = sel

    # Set custom payment amount if specified
    if form.cleaned_data.get("pay_what"):
        reg.pay_what = int(form.cleaned_data["pay_what"])


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
    # Check if membership feature is enabled and user needs to complete profile
    if "membership" in context["features"]:
        # Redirect to profile if membership data not compiled
        if not context["membership"].compiled:
            message = _("To confirm your registration, please fill in your personal profile") + "."
            messages.success(request, message)
            return redirect("profile")

        # Check membership status for non-waiting registrations
        membership_status = context["membership"].status
        if (
            membership_status in [MembershipStatus.EMPTY, MembershipStatus.JOINED]
            and registration.ticket.tier != TicketTier.WAITING
        ):
            message = _("To confirm your registration, apply to become a member of the Association") + "."
            messages.success(request, message)
            return redirect("membership")

    # Check if payment feature is enabled and payment is required
    if "payment" in context["features"]:
        # Redirect to payment page if registration has outstanding payment alert
        if registration.alert:
            message = _("To confirm your registration, please pay the amount indicated") + "."
            messages.success(request, message)
            return redirect("acc_reg", reg_id=registration.id)

    # All requirements satisfied - show success message and redirect to event gallery
    context = {"event": run}
    if is_new_registration:
        # Success message for new registration
        message = _("Registration confirmed at %(event)s!") % context
    else:
        # Success message for registration update
        message = _("Registration updated to %(event)s!") % context

    messages.success(request, message)
    return redirect("gallery", event_slug=registration.run.get_slug())


def save_registration_bring_friend(context: dict, form, reg: Registration, request: HttpRequest) -> None:
    """Process bring-a-friend discount codes for registration.

    This function handles the bring-a-friend functionality by:
    1. Sending instructions email to the registrant
    2. Validating the provided friend code
    3. Creating accounting entries for both parties
    4. Applying discounts to both the registrant and their friend

    Args:
        context: Context dictionary containing bring friend configuration including:
            - bring_friend_discount_from: Discount amount for code user
            - bring_friend_discount_to: Discount amount for code owner
            - run: Event run instance
            - a_id: Association ID
        form: Registration form with bring_friend field containing the friend code
        reg: Registration instance for the current registrant
        request: Django HTTP request object containing user information

    Raises:
        Http404: When the provided friend code is not found in the database

    """
    # Send bring-a-friend instructions email to the new registrant
    bring_friend_instructions(reg, context)

    # Early return if no bring_friend field in form data
    if "bring_friend" not in form.cleaned_data:
        return
    logger.debug("Bring friend form data: %s", form.cleaned_data)

    # Extract and validate the friend code from form
    cod = form.cleaned_data["bring_friend"]
    logger.debug("Processing bring friend code: %s", cod)
    if not cod:
        return

    # Look up the registration associated with the friend code
    try:
        friend = Registration.objects.get(special_cod=cod)
    except Exception as err:
        msg = "I'm sorry, this friend code was not found"
        raise Http404(msg) from err

    # Create accounting entries atomically for both parties
    with transaction.atomic():
        # Create discount token for the person using the friend code
        AccountingItemOther.objects.create(
            member=context["member"],
            value=int(context["bring_friend_discount_from"]),
            run=context["run"],
            oth=OtherChoices.TOKEN,
            descr=_("You have use a friend code") + f" - {friend.member.display_member()} - {cod}",
            association_id=context["association_id"],
            ref_addit=reg.id,
        )

        # Create discount token for the friend whose code was used
        AccountingItemOther.objects.create(
            member=friend.member,
            value=int(context["bring_friend_discount_to"]),
            run=context["run"],
            oth=OtherChoices.TOKEN,
            descr=_("Your friend code has been used") + f" - {context['member'].display_member()} - {cod}",
            association_id=context["association_id"],
            ref_addit=friend.id,
        )

        # Trigger accounting update for the friend's registration
        friend.save()


def register_info(request: HttpRequest, context: dict, form, registration, discount_info) -> None:
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
        context["event"].id, "registration_hide_unavailable", default_value=False, context=context
    )
    context["no_provisional"] = get_event_config(
        context["event"].id, "payment_no_provisional", default_value=False, context=context
    )

    init_form_submitted(context, form, request, registration)

    if registration:
        registration.provisional = is_reg_provisional(registration)

    if context["run"].start and "membership" in context["features"]:
        membership_query = AccountingItemMembership.objects.filter(
            year=context["run"].start.year,
            member=context["member"],
        )
        if membership_query.count() > 0:
            context["membership_fee"] = "done"
        elif timezone.now().year != context["run"].start.year:
            context["membership_fee"] = "future"
        else:
            context["membership_fee"] = "todo"

        context["membership_amount"] = get_association_config(
            context["association_id"], "membership_fee", default_value=0
        )


def init_form_submitted(context, form, request, registration=None) -> None:
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
            if question.id in form.singles:
                context["submitted"]["q" + str(question.id)] = form.singles[question.id].option_id

    if registration:
        if registration.ticket_id:
            context["submitted"]["ticket"] = registration.ticket_id
        if registration.quotas:
            context["submitted"]["quotas"] = registration.quotas
        if registration.additionals:
            context["submitted"]["additionals"] = registration.additionals

    if "ticket" in context:
        context["submitted"]["ticket"] = context["ticket"]


@login_required
def register(
    request: HttpRequest,
    event_slug: str,
    secret_code: str = "",
    discount_code: str = "",
    ticket_id: int = 0,
) -> HttpResponse:
    """Handle event registration form display and submission.

    Manages the complete registration process including ticket selection,
    form validation, payment processing, and membership verification.

    Args:
        request: Django HTTP request object
        event_slug: Event slug identifier
        secret_code: Optional scenario code for registration context
        discount_code: Optional discount code to apply
        ticket_id: Ticket ID to pre-select (default: 0)

    Returns:
        HttpResponse: Rendered registration page or redirect response

    Raises:
        RewokedMembershipError: When user membership has been revoked

    """
    # Get event and run context with status validation
    context = get_event_context(request, event_slug, include_status=True)
    current_run = context["run"]
    current_event = context["event"]

    # Set up registration context for the current run
    if hasattr(current_run, "reg"):
        context["run_reg"] = current_run.reg
    else:
        context["run_reg"] = None

    # Apply ticket selection if provided
    _apply_ticket(context, ticket_id)

    # Check if payment features are enabled for this association
    context["payment_feature"] = "payment" in get_association_features(context["association_id"])

    # Prepare new registration or load existing one
    is_new_registration = _register_prepare(context, context["run_reg"])

    # Handle registration redirects for new registrations
    if is_new_registration:
        redirect_response = _check_redirect_registration(request, context, current_event, secret_code)
        if redirect_response:
            return redirect_response

    # Add any available bring-a-friend discounts
    _add_bring_friend_discounts(context)

    # Verify user membership status and permissions
    current_membership = context["membership"]
    if current_membership.status in [MembershipStatus.REWOKED]:
        raise RewokedMembershipError

    # Process form submission or display registration form
    if request.method == "POST":
        form = RegistrationForm(request.POST, context=context, instance=context["run_reg"])
        form.sel_ticket_map(request.POST.get("ticket", ""))
        # Validate form and save registration if valid
        if form.is_valid():
            saved_registration = save_registration(
                request,
                context,
                form,
                current_run,
                current_event,
                context["run_reg"],
            )
            return registration_redirect(
                request, context, saved_registration, current_run, is_new_registration=is_new_registration
            )
    else:
        # Display empty form for GET requests
        form = RegistrationForm(context=context, instance=context["run_reg"])

    # Prepare additional registration information and render page
    register_info(request, context, form, context["run_reg"], discount_code)
    return render(request, "larpmanager/event/register.html", context)


def _apply_ticket(context: dict, ticket_id: int | None) -> None:
    """Apply ticket information to context if ticket exists.

    Args:
        context: Context dictionary to update with ticket data
        ticket_id: Ticket ID to retrieve, or None

    """
    if not ticket_id:
        return

    try:
        # Retrieve ticket and set tier in context
        ticket = RegistrationTicket.objects.get(pk=ticket_id)
        context["tier"] = ticket.tier

        # Remove closed status for staff/NPC tickets
        if ticket.tier in [TicketTier.STAFF, TicketTier.NPC] and "closed" in context["run"].status:
            del context["run"].status["closed"]

        # Store ticket ID in context
        context["ticket"] = ticket_id
    except ObjectDoesNotExist:
        pass


def _check_redirect_registration(
    request: HttpRequest, context: dict, event, secret_code: str | None
) -> HttpResponse | None:
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
    if "closed" in context["run"].status:
        return render(request, "larpmanager/event/closed.html", context)

    # Validate secret code if secret registration is enabled
    if "registration_secret" in context["features"] and secret_code:
        if context["run"].registration_secret != secret_code:
            msg = "wrong registration code"
            raise Http404(msg)
        return None

    # Redirect to external registration link if configured
    # Skip redirect for staff and NPC tiers who register internally
    if "register_link" in context["features"] and event.register_link:
        if "tier" not in context or context["tier"] not in [TicketTier.STAFF, TicketTier.NPC]:
            return redirect(event.register_link)

    # Check registration timing and pre-registration options
    if "registration_open" in context["features"]:
        if not context["run"].registration_open or context["run"].registration_open > timezone.now():
            # Redirect to pre-registration if available and active
            if "pre_register" in context["features"] and get_event_config(
                event.id, "pre_register_active", default_value=False
            ):
                return redirect("pre_register", event_slug=context["event"].slug)
            return render(request, "larpmanager/event/not_open.html", context)

    return None


def _add_bring_friend_discounts(context: dict) -> None:
    """Add bring-a-friend discount configuration to context if feature is enabled."""
    if "bring_friend" not in context["features"]:
        return

    # Retrieve discount configuration for both directions (to/from)
    for discount_config_name in ["bring_friend_discount_to", "bring_friend_discount_from"]:
        context[discount_config_name] = get_event_config(
            context["event"].id, discount_config_name, default_value=0, context=context
        )


def _register_prepare(context, registration):
    """Prepare registration context with payment information and locks.

    Args:
        context: Context dictionary to update
        registration: Existing registration instance or None for new registration

    Returns:
        bool: True if this is a new registration, False if updating existing

    """
    is_new_registration = True
    context["tot_payed"] = 0
    if registration:
        context["tot_payed"] = registration.tot_payed
        is_new_registration = False

        # we lock changing values with lower prices if there is already a payment (done or submitted)
        has_pending_payment = (
            PaymentInvoice.objects.filter(
                idx=registration.id,
                member_id=registration.member_id,
                status=PaymentStatus.SUBMITTED,
                typ=PaymentType.REGISTRATION,
            ).count()
            > 0
        )
        context["payment_lock"] = has_pending_payment or registration.tot_payed > 0

    return is_new_registration


def register_reduced(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Return count of available reduced-price tickets for an event run."""
    context = get_event_context(request, event_slug)
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
# ~ friend = Registration.objects.get(special_cod=cod)
# ~ except Exception as e:
# ~ Return jsonrespone ({'really': 'ko', 'msg': _ ("Discount code not valid")})
# ~ if friend.member == context["member"]:
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('Nice Try! But no, I'm sorry.')})
# ~ # check same event
# ~ if friend.run.event != context['event']:
# ~ Return Jsonresonse ({'res': 'ko', 'msg': _ ('Code applicable only to run of the same event!')})
# ~ # check future run
# ~ if friend.run.end < datetime.now().date():
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
# ~ Return jsonrespone ({'really': 'ko', 'msg': _ ("Discount not combinable with other benefits") + "."})
# ~ # check the user TO don't already have the discount
# ~ try:
# ~ ac = AccountingItemDiscount.objects.get(disc=disc, member=context["member"], run=context['run'])
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('You have already used a personal code')})
# ~ except Exception as e:
# ~ pass
# ~ if AccountingItemDiscount.objects.filter(member=context["member"], run=context['run'], disc__typ=DiscountType.PLAYAGAIN).count() > 0:
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('Discount not comulary with Play Again')})
# ~ # all green! proceed
# ~ now = datetime.now()
# ~ AccountingItemDiscount.objects.create(disc=disc, value=disc.value, member=context["member"], expires=now + timedelta(minutes = 15), run=context['run'], detail=friend.id, association_id=context['association_id'])
# ~ Return Jsonresonse ({'res': 'ok', 'msg': _ ('The facility has been added! It was reserved for you for 15 minutes, after which it will be removed')})


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
    context = get_event_context(request, event_slug)

    if "discount" not in context["features"]:
        return error(_("Not available, kiddo"))

    # Extract and validate discount code from request
    cod = request.POST.get("cod")
    try:
        disc = Discount.objects.get(runs__in=[context["run"]], cod=cod)
    except ObjectDoesNotExist:
        logger.warning("Discount code not found: %s", cod)
        logger.debug(traceback.format_exc())
        return error(_("Discount code not valid"))

    # Clean up expired discount reservations
    now = timezone.now()
    AccountingItemDiscount.objects.filter(expires__lte=now).delete()

    # Extract context variables for discount validation
    member = context["member"]
    run = context["run"]
    event = context["event"]

    # Validate discount eligibility and constraints
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


def _check_discount(discount, member, run, event):
    """Validate if a discount can be applied to a member's registration.

    Args:
        discount: Discount object to validate
        member: Member attempting to use discount
        run: Event run instance
        event: Event instance

    Returns:
        str or None: Error message if invalid, None if valid

    """
    if _is_discount_invalid_for_registration(discount, member, run):
        return _("Discounts only applicable with new registrations")

    if _is_discount_already_used(discount, member, run):
        return _("Code already used")

    if _is_type_already_used(discount.typ, member, run):
        return _("Non-cumulative code")

    if discount.max_redeem > 0 and _is_discount_maxed(discount, run):
        return _("Sorry, this facilitation code has already been used the maximum number allowed")

    if not _validate_exclusive_logic(discount, member, run, event):
        return _("Discount not combinable with other benefits") + "."

    return None


def _is_discount_invalid_for_registration(discount: Discount, member: Member, run: Run) -> bool:
    """Check if discount is invalid due to existing registration.

    Returns True if discount is registration-only and member already registered.
    """
    # Discount not limited to registration-only
    if not discount.only_reg:
        return False

    # Check if member has active registration for this run
    return Registration.objects.filter(member=member, run=run, cancellation_date__isnull=True).exists()


def _is_discount_already_used(discount: Discount, member: Member, run: Run) -> bool:
    """Check if discount has already been used by member for run."""
    return AccountingItemDiscount.objects.filter(disc=discount, member=member, run=run).exists()


def _is_type_already_used(
    discount_type: DiscountType,
    member: Member,
    run: Run,
) -> bool:
    """Check if a discount type has already been used by a member for a run."""
    return AccountingItemDiscount.objects.filter(disc__typ=discount_type, member=member, run=run).exists()


def _is_discount_maxed(discount: Discount, run: Run) -> bool:
    """Check if discount has exceeded maximum redemptions for a run."""
    redemption_count = AccountingItemDiscount.objects.filter(disc=discount, run=run).count()
    return redemption_count > discount.max_redeem


def _validate_exclusive_logic(discount: Discount, member: Member, run: Run, event: Event) -> bool:
    """Validate exclusive discount logic for member registrations.

    Ensures that PLAYAGAIN discounts are mutually exclusive with other discounts
    and validates eligibility requirements.

    Args:
        discount: The discount to validate
        member: The member applying for the discount
        run: The specific run for this registration
        event: The event containing multiple runs

    Returns:
        True if the discount can be applied, False otherwise

    """
    # For PLAYAGAIN discount: no other discounts and has another registration
    if discount.typ == DiscountType.PLAYAGAIN:
        # Check if member already has any discount for this run
        if AccountingItemDiscount.objects.filter(member=member, run=run).exists():
            return False

        # Verify member has registration in another run of the same event
        if not Registration.objects.filter(member=member, run__event=event).exclude(run=run).exists():
            return False

    # If PLAYAGAIN discount was already applied, no other allowed
    elif AccountingItemDiscount.objects.filter(member=member, run=run, disc__typ=DiscountType.PLAYAGAIN).exists():
        return False

    return True


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
    context = get_event_context(request, event_slug)
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
def unregister(request: HttpRequest, event_slug: str):
    """Handle user self-unregistration from an event.

    Args:
        request: HTTP request object from authenticated user
        event_slug: Event slug string

    Returns:
        HttpResponse: Confirmation form or redirect to accounting page after cancellation

    """
    context = get_event_context(request, event_slug, signup=True, include_status=True)

    # check if user is actually registered
    try:
        reg = Registration.objects.get(run=context["run"], member=context["member"], cancellation_date__isnull=True)
    except ObjectDoesNotExist as err:
        msg = "Registration does not exist"
        raise Http404(msg) from err

    if request.method == "POST":
        cancel_reg(reg)
        mes = _("You have correctly cancelled the registration to the %(event)s event") % {"event": context["event"]}
        messages.success(request, mes)
        return redirect("accounting")

    context["reg"] = reg
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
    context = get_event_context(request, event_slug, signup=False, feature_slug="gift", include_status=True)
    check_registration_open(context, request)

    # Filter registrations for current user with redeem codes (gift registrations)
    context["list"] = Registration.objects.filter(
        run=context["run"],
        member=context["member"],
        redeem_code__isnull=False,
        cancellation_date__isnull=True,
    )

    # Load accounting information (payments, pending transactions, etc.)
    info_accounting(request, context)

    # Attach payment and accounting info to each registration
    for reg in context["list"]:
        # Check for pending payments
        for el in context["payments_todo"]:
            if reg.id == el.id:
                reg.payment = el

        # Check for pending transactions
        for el in context["payments_pending"]:
            if reg.id == el.id:
                reg.pending = el

        # Attach additional registration info
        for el in context["registration_list"]:
            if reg.id == el.id:
                reg.info = el

    return render(request, "larpmanager/event/gift.html", context)


def check_registration_open(context: dict, request: HttpRequest) -> None:
    """Check if registrations are open, redirect to home if closed."""
    if not context["run"].status["open"]:
        messages.warning(request, _("Registrations not open!"))
        msg = "home"
        raise RedirectError(msg)


@login_required
def gift_edit(request: HttpRequest, event_slug: str, gift_id: int) -> HttpResponse:
    """Handle gift registration modifications.

    This function manages the editing of gift registrations, allowing users to
    modify gift card details or cancel them entirely. It validates permissions,
    handles form processing, and manages the gift registration lifecycle.

    Args:
        request: The HTTP request object containing user data and form submission
        event_slug: Event identifier string used to locate the specific event
        gift_id: The registration ID for the gift card being edited

    Returns:
        HttpResponse: Either renders the gift edit form template or redirects
        to the gift list page after successful save/cancel operations

    Raises:
        Http404: If the event, run, or registration cannot be found
        PermissionDenied: If user lacks permission to edit gift registrations

    """
    # Get event context and verify user has gift management permissions
    context = get_event_context(request, event_slug, signup=False, feature_slug="gift", include_status=True)
    check_registration_open(context, request)

    # Retrieve the specific gift registration and prepare form context
    reg = get_registration_gift(context, gift_id, request)
    _register_prepare(context, reg)

    # Handle POST requests for form submission (save or delete operations)
    if request.method == "POST":
        form = RegistrationGiftForm(request.POST, context=context, instance=reg)

        # Validate form data before processing
        if form.is_valid():
            # Check if this is a deletion request
            if "delete" in request.POST and request.POST["delete"] == "1":
                cancel_reg(reg)
                messages.success(request, _("Gift card cancelled!"))
            else:
                # Save the updated registration data
                save_registration(request, context, form, context["run"], context["event"], reg, gifted=True)
                messages.success(request, _("Operation completed") + "!")

            # Redirect back to gift list after successful operation
            return redirect("gift", event_slug=event_slug)
    else:
        # Handle GET requests by creating a new form with existing data
        form = RegistrationGiftForm(context=context, instance=reg)

    # Prepare context for template rendering
    context["form"] = form
    context["gift"] = True

    # Initialize form submission state and validation
    init_form_submitted(context, form, request, reg)

    return render(request, "larpmanager/event/gift_edit.html", context)


def get_registration_gift(context: dict, registration_id: int | None, request: HttpRequest) -> Registration | None:
    """Get a registration with gift redeem code for the current user.

    Args:
        context: Context dictionary containing run information
        registration_id: Registration primary key to lookup
        request: HTTP request object with authenticated user

    Returns:
        Registration object if found and valid, None otherwise

    Raises:
        Http404: If registration lookup fails or invalid parameters provided

    """
    registration = None

    # Early return if no registration ID provided
    if registration_id:
        try:
            # Query for valid gift registration matching all criteria
            registration = Registration.objects.get(
                pk=registration_id,
                run=context["run"],
                member=context["member"],
                redeem_code__isnull=False,  # Must have a redeem code (gift)
                cancellation_date__isnull=True,  # Must not be cancelled
            )
        except Exception as error:
            # Convert any lookup error to 404 for security
            msg = "what are you trying to do?"
            raise Http404(msg) from error

    return registration


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
                     or redirects to the gallery page after successful redemption

    Raises:
        Http404: When no valid registration is found matching the provided code
                and association constraints

    """
    # Get event context and validate user permissions for gift redemption
    context = get_event_context(request, event_slug, signup=False, feature_slug="gift", include_status=True)

    # Check if user is already registered for this event
    if context["run"].reg:
        messages.success(request, _("You cannot redeem a membership, you are already a member!"))
        return redirect("gallery", event_slug=context["run"].get_slug())

    # Attempt to find valid registration with the provided redemption code
    try:
        reg = Registration.objects.get(
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
            reg.member = context["member"]
            reg.redeem_code = None
            reg.save()

        # Notify user of successful redemption and redirect to event gallery
        messages.success(request, _("Your gifted registration has been redeemed!"))
        return redirect("gallery", event_slug=context["run"].get_slug())

    # Add registration object to context for template rendering
    context["reg"] = reg

    return render(request, "larpmanager/event/gift_redeem.html", context)
