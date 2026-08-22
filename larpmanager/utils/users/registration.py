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

import math
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import _format_decimal, is_registration_provisional
from larpmanager.accounting.member import get_membership_fee_for_reg
from larpmanager.cache.accounting import clear_registration_accounting_cache
from larpmanager.cache.basic import get_run_association_id, get_run_basic_cache, get_run_event_id
from larpmanager.cache.config import get_association_config, get_event_config
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.question import get_cached_registration_questions, skip_registration_question
from larpmanager.cache.registration import clear_registration_counts_cache, get_registration_counts
from larpmanager.cache.run import get_event_run_ids
from larpmanager.models.accounting import AccountingItemMembership, PaymentInvoice, PaymentStatus, PaymentType
from larpmanager.models.casting import Casting
from larpmanager.models.event import Event, PreRegistration, RegistrationStatus, Run
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    WritingChoice,
    WritingOption,
)
from larpmanager.models.member import Member, Membership, MembershipStatus, get_user_membership
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket, TicketTier
from larpmanager.models.writing import Character, CharacterConfig, CharacterStatus
from larpmanager.utils.core.common import (
    feature_visible,
    format_datetime,
    get_event_class_parent,
    get_event_elements,
    get_time_diff_today,
)
from larpmanager.utils.core.exceptions import PendingApprovalError, RewokedMembershipError, SignupError, WaitingError

if TYPE_CHECKING:
    from django.db.models import QuerySet


def registration_available(run: Run, features: dict, run_status: dict, context: dict | None = None) -> None:
    """Check if registration is available based on capacity and rules.

    Validates registration availability considering maximum participants,
    ticket quotas, and advanced registration constraints. Updates the run's
    status dictionary with availability information.

    Args:
        run: The run object containing event and status information
        features: Dictionary of enabled features for the event
        run_status: Dictionary with run status
        context: Optional context dictionary containing cached data
    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    # Skip advanced registration rules if no maximum participant limit is set
    if run.event.max_pg == 0:
        run_status["primary"] = True
        return

    # Get registration counts if not provided
    registration_counts = context.get("registration_counts")
    if registration_counts is None:
        registration_counts = get_registration_counts(run)

    # Calculate remaining primary tickets
    remaining_primary_tickets = run.event.max_pg - registration_counts.get("count_player", 0)

    # Get event features if not provided
    if not features:
        features = get_event_features(run.event_id)

    # Check if primary tickets are available
    if remaining_primary_tickets > 0:
        run_status["primary"] = True

        # Show urgency warning when tickets are running low
        percentage_threshold_for_urgency = 0.3
        absolute_threshold_for_urgency = 10
        if (
            remaining_primary_tickets < absolute_threshold_for_urgency
            or remaining_primary_tickets * 1.0 / run.event.max_pg < percentage_threshold_for_urgency
        ):
            run_status["count"] = remaining_primary_tickets
            run_status["additional"] = _(" Hurry: only %(num)d tickets available.") % {"num": remaining_primary_tickets}
        return

    # Check if filler tickets are available (fallback option)
    if "filler" in features and _available_filler(run, run_status, registration_counts):
        return

    # Check if waiting list is available (last resort option)
    if "waiting" in features and _available_waiting(run, run_status, registration_counts):
        return

    # No registration options available - mark as closed
    run_status["closed"] = True
    return


def _available_waiting(run: Run, run_status: dict, registration_counts: dict) -> bool:
    """Check if waiting list spots are available for a registration.

    Args:
        run: Run object
        registration_counts: Dictionary containing registration counts including 'count_wait'
        run_status: Dictionary with run status

    Returns:
        bool: True if waiting list spots are available, False otherwise

    """
    # Handle infinite waiting list capacity
    if run.event.max_waiting == 0:
        run_status["waiting"] = True
        run_status["count"] = None  # Infinite
        return True

    # Check if limited waiting list has available spots
    if run.event.max_waiting > 0:
        # Calculate remaining waiting list capacity
        remaining_waiting_spots = run.event.max_waiting - registration_counts["count_wait"]

        # Set status if spots are available
        if remaining_waiting_spots > 0:
            run_status["waiting"] = True
            run_status["count"] = remaining_waiting_spots
            run_status["additional"] = _(" Hurry: only %(num)d tickets available.") % {"num": remaining_waiting_spots}
            return True

    # No waiting list spots available
    return False


def _available_filler(run: Run, run_status: dict, registration_counts: Any) -> bool:
    """Check if filler tickets are available for the given registration.

    Args:
        run: Run object
        registration_counts: Dictionary containing registration counts including 'count_fill'
        run_status: Dictionary with run status

    Returns:
        bool: True if filler tickets are available, False otherwise

    """
    # Handle infinite filler tickets case
    if run.event.max_filler == 0:
        run_status["filler"] = True
        run_status["count"] = None  # Infinite
        return True

    # Handle limited filler tickets case
    if run.event.max_filler > 0:
        # Calculate remaining filler tickets
        remaining_filler = run.event.max_filler - registration_counts["count_fill"]

        # Check if any filler tickets are still available
        if remaining_filler > 0:
            run_status["filler"] = True
            run_status["count"] = remaining_filler
            # Add urgency message for limited availability
            run_status["additional"] = _(" Hurry: only %(num)d tickets available.") % {"num": remaining_filler}
            return True

    # No filler tickets available
    return False


def get_match_reg(r: Run, my_regs: list[Registration]) -> Registration | None:
    """Find registration matching the given run ID."""
    # Iterate through registrations to find matching run
    for m in my_regs:
        if m and m.run_id == r.id:
            return m
    return None


def _status_membership_fee(
    run: Run, member: Member, user_membership: Membership, run_status: dict, registration_text: str
) -> bool:
    """Check if we need to show text regarding membership payment."""
    if user_membership.status != MembershipStatus.ACCEPTED:
        return False

    run_cache = get_run_basic_cache(run.id)
    association_id = run_cache["association_id"]
    fee = int(get_association_config(association_id, "membership_fee"))
    if not fee:
        return False

    current_year = timezone.now().year
    # Check if event is in current year and if membership fee has been paid
    if not run.start or run.start.year != current_year:
        return False

    # Check if membership fee exists for current year
    membership_fee_exists = AccountingItemMembership.objects.filter(
        member=member,
        association_id=association_id,
        year=current_year,
    ).exists()

    if membership_fee_exists:
        return False

    # Check if there's a pending membership payment
    pending_membership_payment = PaymentInvoice.objects.filter(
        member=member,
        association_id=association_id,
        status=PaymentStatus.SUBMITTED,
        typ=PaymentType.MEMBERSHIP,
    ).exists()

    if pending_membership_payment:
        return False

    membership_url = reverse("accounting_membership")
    run_status["text"] = registration_text
    run_status["status_type"] = "action_needed"
    run_status["action"] = {
        "url": membership_url,
        "label": _("Pay membership fee"),
        "label_long": _(
            "Pay the %(year)d annual membership fee of %(amount)s%(currency)s, required to attend this event"
        )
        % {
            "year": current_year,
            "amount": fee,
            "currency": run_cache["currency_symbol"],
        },
    }
    return True


def registration_status_signed(  # noqa: C901, PLR0911 - Complex registration status logic with feature checks
    run: Run,
    registration: Registration,
    member: Member,
    features: dict[str, Any],
    register_url: str,
    run_status: dict,
    context: dict | None = None,
) -> None:
    """Update the registration status for a signed user based on membership and payment features.

    Args:
        run: The run object containing event and status information
        registration: The registration object with ticket and user details
        member: The member object for the registered user
        features: Dictionary of enabled features for the event
        register_url: URL for the registration page
        run_status: Dictionary with run status
        context: Optional context dictionary containing cached data:
            - character_rels_dict: Dictionary mapping registration IDs to lists of RegistrationCharacterRel objects
            - payment_invoices_dict: Dictionary mapping registration IDs to lists of PaymentInvoice objects

    Raises:
        RewokedMembershipError: When membership status is revoked

    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    # Signup request still awaiting organizer approval: nothing else to check yet
    if registration.pending:
        run_status["text"] = _("Signup request pending")
        run_status["status_type"] = "request_pending"
        run_status["action"] = {
            "label": _("Awaiting approval"),
            "label_long": _("Your signup request is awaiting organizer approval"),
        }
        run_status["can_pay"] = False
        return

    # Initialize character registration status for the run
    registration_status_characters(run, registration, run_status, features, context)

    # Get user membership for the event's association
    user_membership = get_user_membership(member, get_run_association_id(run.id))

    # Build base registration message with ticket info if available
    is_provisional = is_registration_provisional(
        registration, features=features, event_id=run.event_id, context=context
    )
    registration_message, registration_message_long = _registration_messages(
        run, registration, is_provisional=is_provisional
    )

    # Append ticket name if ticket exists
    if registration.ticket:
        registration_message += f" ({registration.ticket.name})"
        registration_message_long += f" ({registration.ticket.name})"
    registration_text = registration_message
    run_status["text_long"] = registration_message_long
    run_status["url"] = register_url

    # Handle membership feature requirements and status checks
    if "membership" in features:
        # Check for revoked membership status and raise error
        if user_membership.status in [MembershipStatus.REWOKED]:
            raise RewokedMembershipError

        # Handle incomplete membership applications (empty, joined, uploaded)
        if user_membership.status in [MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED]:
            membership_url = reverse("membership")
            run_status["text"] = registration_text
            run_status["status_type"] = "action_needed"
            run_status["action"] = {
                "url": membership_url,
                "label": _("Upload membership application"),
                "label_long": _(
                    "Fill in and upload your membership application, needed before you can pay for your registration"
                ),
            }
            run_status["can_pay"] = False
            return

        # Handle pending membership approval (submitted but not approved)
        if user_membership.status in [MembershipStatus.SUBMITTED]:
            run_status["text"] = registration_text
            run_status["status_type"] = "pending"
            run_status["action"] = {
                "label": _("Pending approval"),
                "label_long": _(
                    "Your membership application is being reviewed by the organization. "
                    "Payment will be available once it has been approved."
                ),
            }
            run_status["can_pay"] = False
            return

    # Set base text before payment check (may be overridden for submitted/wire cases)
    run_status["text"] = registration_text

    # Check payment status and return if payment handling is complete
    if "payment" in features and _status_payment(register_url, registration, run_status, context):
        return

    # Check for missing membership fee if membership feature is enabled
    if "membership" in features and _status_membership_fee(run, member, user_membership, run_status, registration_text):
        return

    # Check for incomplete user profile and prompt completion
    if not user_membership.compiled:
        profile_url = reverse("profile")
        run_status["text"] = registration_text
        run_status["status_type"] = "action_needed"
        run_status["action"] = {
            "url": profile_url,
            "label": _("Complete your profile"),
            "label_long": _("Fill in the missing information in your profile to complete your registration"),
        }
        return

    # Handle provisional registration status
    if is_provisional:
        payment_url = reverse("accounting_registration", args=[registration.uuid])
        run_status["text"] = registration_text
        run_status["status_type"] = "provisional"
        run_status["action"] = {
            "url": payment_url,
            "label": _("Proceed with payment"),
            "label_long": _("Your registration is provisional: complete the payment to confirm your spot"),
        }
        return

    # Set final confirmed registration status for completed registrations
    run_status["text"] = registration_text


def _registration_messages(run: Run, registration: Registration, *, is_provisional: bool) -> tuple[str, str]:
    """Build the short and long registration status messages."""
    if not is_provisional:
        return _("Registration confirmed"), _("Your registration for this event has been confirmed")

    registration_message = _("Provisional registration")
    registration_message_long = _("Your registration is provisional, and will be confirmed once payment is made")
    remaining_amount = (registration.tot_iscr or 0) - (registration.tot_payed or 0)
    if remaining_amount > 0:
        registration_message_long = _(
            "Your registration is provisional, and will be confirmed once the payment of %(amount)s%(currency)s is made"
        ) % {
            "amount": _format_decimal(remaining_amount),
            "currency": get_run_basic_cache(run.id)["currency_symbol"],
        }
    return registration_message, registration_message_long


def _status_payment(
    register_url: str,
    registration: Registration,
    run_status: dict,
    context: dict | None = None,
) -> bool:
    """Check payment status and update registration status text accordingly.

    Handles pending payments, wire transfers, and payment alerts with
    appropriate messaging and links to payment processing pages.

    Args:
        register_url: URL for the registration page
        registration: The registration object with payment details
        run_status: Dictionary with run status
        context: Optional context dictionary containing cached data:
            - payment_invoices_dict: Dictionary mapping registration IDs to lists of PaymentInvoice objects

    Returns:
        True if payment status was processed and status text updated, False otherwise

    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    ticket_suffix = f" ({registration.ticket.name})" if registration.ticket else ""

    submitted_text = _("Payment submitted") + ticket_suffix
    submitted_text_long = _("Your payment has been submitted, and is awaiting manual verification") + ticket_suffix

    run_status["url"] = register_url

    payment_invoices_dict = context.get("payment_invoices_dict")

    # Get payment invoices for this registration
    if payment_invoices_dict is not None:
        invoices = payment_invoices_dict.get(registration.id, [])
        # Filter for pending payments
        pending_invoices = [
            invoice
            for invoice in invoices
            if invoice.status == PaymentStatus.SUBMITTED and invoice.typ == PaymentType.REGISTRATION
        ]
        # Filter for wire transfer payments
        wire_created_invoices = [
            invoice
            for invoice in invoices
            if invoice.status == PaymentStatus.CREATED
            and invoice.typ == PaymentType.REGISTRATION
            and hasattr(invoice, "method")
            and invoice.method
            and invoice.method.slug == "wire"
        ]
    else:
        # Fallback to database queries if no precalculated data available
        pending_invoices = list(
            PaymentInvoice.objects.filter(
                idx=registration.id,
                member_id=registration.member_id,
                status=PaymentStatus.SUBMITTED,
                typ=PaymentType.REGISTRATION,
            ),
        )
        wire_created_invoices = list(
            PaymentInvoice.objects.filter(
                idx=registration.id,
                member_id=registration.member_id,
                status=PaymentStatus.CREATED,
                typ=PaymentType.REGISTRATION,
                method__slug="wire",
            ),
        )

    # Handle pending payment status
    if pending_invoices:
        run_status["text"] = submitted_text
        run_status["text_long"] = submitted_text_long
        run_status["status_type"] = "pending"
        run_status["action"] = {
            "label": _("Payment awaiting verification"),
            "label_long": _(
                "Your payment has been received and is being verified by the organizers; no further action is needed at the moment"
            ),
        }
        context["pending_invoices"] = True
        run_status["payment_pending"] = True
        return True

    # Process payment alerts for unpaid registrations
    if registration.alert:
        payment_url = reverse("accounting_registration", args=[registration.uuid])

        label = ""
        label_long = ""
        if registration.deadline < 0:
            label = _("Payment overdue: %(amount)s%(currency)s")
            label_long = _(
                "The payment deadline has passed: settle the outstanding %(amount)s%(currency)s as soon as possible to keep your registration"
            )
        elif registration.quota and registration.deadline > 0:
            label = _("Payment due: %(amount)s%(currency)s within %(days)d days")
            label_long = _(
                "A payment of %(amount)s%(currency)s is due within %(days)d days to confirm your registration"
            )

        note = None
        if wire_created_invoices:
            note = _("If you have made a wire transfer, please upload its receipt for processing")

        currency_symbol = get_run_basic_cache(registration.run_id)["currency_symbol"]
        total_amount = registration.quota
        if context.get("membership_fee") == "bundled" and context.get("membership_amount"):
            membership_amount = Decimal(str(context["membership_amount"]))
            total_amount = (total_amount or 0) + membership_amount
            if note is None and registration.run.start:
                note = (
                    _("Includes membership fee")
                    + f" {registration.run.start.year}: {_format_decimal(membership_amount)}{currency_symbol}"
                )

        label_params = {
            "amount": _format_decimal(total_amount),
            "currency": currency_symbol,
            "days": registration.deadline,
        }
        run_status["status_type"] = "action_needed"
        run_status["action"] = {
            "url": payment_url,
            "label": label % label_params,
            "label_long": label_long % label_params,
            "note": note,
        }

        return True

    return False


def _set_membership_context(context: dict, run: Run, member: Member, registration: Any) -> None:
    """Set membership data in context for template rendering."""
    if not run.start or "membership" not in context.get("features", {}):
        return
    run_cache = get_run_basic_cache(run.id)
    association_id = run_cache["association_id"]
    event_year = run.start.year
    context["membership_amount"] = get_association_config(association_id, "membership_fee")
    currency_symbol = run_cache["currency_symbol"]
    context["membership_amount_display"] = ""
    if context["membership_amount"]:
        amount = Decimal(str(context["membership_amount"]))
        context["membership_amount_display"] = f"({_format_decimal(amount)}{currency_symbol})"

    paid_item = AccountingItemMembership.objects.filter(
        year=event_year,
        member=member,
        association_id=association_id,
        deleted__isnull=True,
    ).first()
    if paid_item:
        context["membership_fee"] = "done"
        context["membership_amount_paid"] = paid_item.value
        context["membership_amount_paid_display"] = ""
        if paid_item.value:
            context["membership_amount_paid_display"] = f"({_format_decimal(paid_item.value)}{currency_symbol})"
        return

    membership_fee_separated = get_association_config(association_id, "membership_fee_separated")
    if membership_fee_separated:
        if timezone.now().year != event_year:
            context["membership_fee"] = "future"
        else:
            context["membership_fee"] = "todo"
        return

    if get_membership_fee_for_reg(association_id, member.id, run, registration):
        context["membership_fee"] = "bundled"


def registration_status(context: dict, run: Run, member: Member) -> dict:
    """Determine registration status and availability for users.

    Checks registration constraints, deadlines, and feature requirements
    to determine if a user can register for an event.

    Args:
        run: Event run object to check registration status for
        member: Member object attempting registration
        context: Dict context dictionary, optionally containing cached data for efficiency:
            - my_regs: Pre-filtered user registrations
            - features_map: Cached features mapping
            - registration_counts: Pre-calculated registration counts dictionary
            - character_rels_dict: Dictionary mapping registration IDs to lists of RegistrationCharacterRel objects
            - payment_invoices_dict: Dictionary mapping registration IDs to lists of PaymentInvoice objects
            - pre_registrations_dict: Dictionary mapping event IDs to PreRegistration objects

    Returns:
        Dict with run status informations

    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    run_status = {
        "open": True,
        "details": "",
        "text": "",
        "text_long": "",
        "additional": "",
        "can_pay": True,
        "registration": None,
    }

    # Find user's registration if not already provided
    cached_registrations = context.get("my_regs")
    if cached_registrations is not None:
        registration = cached_registrations.get(run.id) or (registration_find(run, member) if member else None)
        context["registration"] = registration
    elif "registration" in context:
        registration = context["registration"]
    else:
        registration = registration_find(run, member)
        context["registration"] = registration

    run_status["registration"] = registration

    features = _get_features_map(run, context)

    registration_available(run, features, run_status, context)
    register_url = reverse("register", args=[run.get_slug()])

    if member:
        membership = context["membership"]
        if membership.status in [MembershipStatus.REWOKED]:
            return run_status

        if registration:
            _set_membership_context(context, run, member, registration)
            registration_status_signed(run, registration, member, features, register_url, run_status, context)
            return run_status

    if run.end and get_time_diff_today(run.end) < 0:
        return run_status

    return _check_run_status(context, run, member, run_status, register_url)


def _check_run_status(context: dict, run: Run, member: Member, run_status: dict, register_url: str) -> dict:
    """Fill run status dict based on run registrations status field."""
    # Check registration status field
    status = run.registration_status

    # Handle closed status
    if status == RegistrationStatus.CLOSED:
        run_status["open"] = False
        run_status["text"] = _("Registration closed")
        run_status["text_long"] = _("Registrations for this event are currently closed")
        return run_status

    # Handle external registration - redirect is handled in view layer
    if status == RegistrationStatus.EXTERNAL:
        run_status["open"] = True
        run_status["text"] = _("Registration is open!")
        run_status["text_long"] = _("Registrations are open: sign up now to secure your spot!")
        run_status["url"] = register_url
        return run_status

    # Handle pre-registration status
    if status == RegistrationStatus.PRE:
        return _status_preregister(run, member, run_status, context)

    # Handle future registration opening, or normal open
    return _status_future_open(run, register_url, run_status)


def _status_future_open(run: Run, register_url: str, run_status: dict) -> dict:
    """Update run status based on availability."""
    if run.registration_status == RegistrationStatus.FUTURE:
        current_datetime = timezone.now()

        run_status["open"] = False
        run_status["text"] = run_status.get("text") or _("Registrations not open!")
        run_status["text_long"] = run_status.get("text_long") or _("Registrations for this event have not opened yet")

        if not run.registration_open:
            return run_status

        if run.registration_open > current_datetime:
            run_status["details"] = _("Registration opens on: %(date)s") % {
                "date": run.registration_open.strftime(format_datetime),
            }
            return run_status

    if run.registration_status == RegistrationStatus.CLOSING:
        current_datetime = timezone.now()

        if run.registration_open and run.registration_open < current_datetime:
            run_status["open"] = False
            run_status["text"] = run_status.get("text") or _("Registrations closed")
            run_status["text_long"] = run_status.get("text_long") or _(
                "Registrations for this event are currently closed"
            )
            return run_status

    # signup open, not already signed in
    messages = {
        "primary": _("Registration is open!"),
        "filler": _("Sign up as a reserve!"),
        "waiting": _("Join the waiting list!"),
    }
    messages_long = {
        "primary": _("Registrations are open: sign up now to secure your spot!"),
        "filler": _("Primary spots are sold out, but you can still sign up as a reserve!"),
        "waiting": _("The event is sold out, but you can join the waiting list to be notified if a spot frees up!"),
    }

    # pick the first matching message (or None)
    selected_key = next((key for key in messages if key in run_status), None)
    selected_message = messages.get(selected_key)
    selected_message_long = messages_long.get(selected_key)

    # if it's a primary/filler, copy over the additional details
    if selected_message and any(key in run_status for key in ("primary", "filler")):
        run_status["details"] = run_status["additional"]

    # wrap in a link if we have a message, otherwise show closed
    if selected_message:
        run_status["text"] = selected_message
        run_status["text_long"] = selected_message_long
        run_status["url"] = register_url
        if run.registration_status == RegistrationStatus.CLOSING and run.registration_open:
            closing_details = _("Registration closes on: %(date)s") % {
                "date": run.registration_open.strftime(format_datetime),
            }
            if run_status.get("details"):
                run_status["details"] += " - " + closing_details
            else:
                run_status["details"] = closing_details
    else:
        run_status["text"] = _("Registration closed")
        run_status["text_long"] = _("Registrations for this event are currently closed")

    return run_status


def _status_preregister(run: Run, member: Member, run_status: dict, context: dict | None = None) -> dict:
    """Update run status based on user's pre-registration state."""
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    run_status["open"] = False

    # Get cached pre-registrations dictionary from context
    pre_registrations_dict = context.get("pre_registrations_dict")

    # Check if user already has a pre-registration for this event
    has_pre_registration = False
    if member:
        # Use cached data if available, otherwise query database
        if pre_registrations_dict is not None:
            # Use cached data if available
            has_pre_registration = run.event_id in pre_registrations_dict
        else:
            # Fallback to database query if no cache provided
            has_pre_registration = PreRegistration.objects.filter(
                event_id=run.event_id,
                member=member,
                deleted__isnull=True,
            ).exists()

    # Set status message based on pre-registration state
    if has_pre_registration:
        status_message = _("Pre-registration confirmed!")
        run_status["text"] = status_message
        run_status["text_long"] = _(
            "Your pre-registration has been confirmed: you will be notified when registrations open"
        )

    else:
        # Create pre-registration link for unauthenticated or non-pre-registered users
        status_message = _("Pre-register to the event!")
        status_message_long = _("Pre-registrations are open: pre-register to be notified when registrations open!")
        preregister_url = reverse("pre_register", args=[run.event.slug])
        run_status["text"] = status_message
        run_status["text_long"] = status_message_long
        run_status["url"] = preregister_url

    return run_status


def _get_features_map(run: Run, context: dict) -> Any:
    """Get features map from context or create it if not available."""
    if context is None:
        context = {}

    features_map = context.get("features_map")
    if features_map is None:
        features_map = {}
    if run.event_id not in features_map:
        features_map[run.event_id] = get_event_features(run.event_id)
    return features_map[run.event_id]


def registration_find(run: Run, member: Member) -> Registration | None:
    """Find registration for a user to a run.

    Searches for an active registration (non-cancelled, non-redeemed) for the given
    user and run.

    Args:
        run: The Run object to find registration for
        member: The Member object to search registration for

    Returns:
        Registration | None: The found registration or None if not found

    """
    # Early return if user is not authenticated
    if not member:
        return None

    # Query database for active registration (non-cancelled, non-redeemed)
    try:
        registration_queryset = Registration.objects.select_related("ticket")
        return registration_queryset.get(
            run=run,
            member=member,
            redeem_code__isnull=True,
            cancellation_date__isnull=True,
        )
    except ObjectDoesNotExist:
        # No active registration found for this user and run
        return None


def check_character_maximum(event: Any, member: Any) -> tuple[bool, int]:
    """Check if member has reached the maximum character limit for an event.

    Args:
        event: The event to check character limits for
        member: The member whose character count to verify

    Returns:
        Tuple of (has_reached_limit, max_allowed_characters)

    """
    # Get all characters for this member in the event
    characters = get_event_elements(event.id, Character).filter(player=member)

    # Get IDs of inactive characters (those with CharacterConfig inactive=True)
    inactive_character_ids = CharacterConfig.objects.filter(
        character__in=characters,
        name="inactive",
        value="True",
    ).values_list("character_id", flat=True)

    # Count only active characters (exclude inactive ones)
    current_character_count = characters.exclude(id__in=inactive_character_ids).count()

    # Get the maximum allowed characters from event configuration
    maximum_characters_allowed = int(get_event_config(event.id, "user_character_max"))

    # Return whether limit is reached and the maximum allowed
    return current_character_count >= maximum_characters_allowed, maximum_characters_allowed


def get_character_play_max(event_id: int, context: dict | None = None) -> int:
    """Return how many characters a player can play at the same time in an event."""
    return max(1, int(get_event_config(event_id, "character_play_max", context=context)))


def get_player_characters_ids(member: Member, event: Event, context: dict | None = None) -> set[int]:
    """Get ids of the player's characters for an event, from the batched cache when available.

    Args:
        member: Player owning the characters
        event: Event the characters belong to
        context: Optional context dictionary, optionally containing cached data:
            - player_characters_dict: Dictionary mapping event IDs to lists of
              (id, uuid, name, status) tuples

    Returns:
        Set of character IDs owned by the player in the event

    """
    player_characters_dict = (context or {}).get("player_characters_dict")
    if player_characters_dict is not None:
        entries = player_characters_dict.get(get_event_class_parent(event.id, Character), [])
        return {entry[0] for entry in entries}

    return set(get_player_characters(member, event).values_list("id", flat=True))


def get_player_pending_characters(member: Member, event_id: int, context: dict | None = None) -> list[tuple[str, str]]:
    """Get (uuid, name) of the player's characters awaiting confirmation, from the batched cache when available.

    Args:
        member: Player owning the characters
        event_id: Event ID the characters belong to
        context: Optional context dictionary, optionally containing cached data:
            - player_characters_dict: Dictionary mapping event IDs to lists of
              (id, uuid, name, status) tuples

    Returns:
        List of (uuid, name) for characters with status CREATION or REVIEW

    """
    pending_statuses = {CharacterStatus.CREATION, CharacterStatus.REVIEW}

    player_characters_dict = (context or {}).get("player_characters_dict")
    if player_characters_dict is not None:
        entries = player_characters_dict.get(get_event_class_parent(event_id, Character), [])
        return [(uuid, name) for _id, uuid, name, status in entries if status in pending_statuses]

    query = get_event_elements(event_id, Character).filter(player=member, status__in=pending_statuses)
    return list(query.values_list("uuid", "name"))


def registration_status_characters(
    run: Run, registration: Registration, run_status: dict, features: dict, context: dict | None = None
) -> None:
    """Update registration status with character assignment information.

    Displays assigned characters with approval status and provides links
    for character creation or selection based on event configuration.

    Args:
        run: The run object containing status information
        registration: The registration object with character relationships
        features: Dictionary of enabled event features
        run_status: Dictionary with run status
        context: Optional context dictionary containing cached data:
            - character_rels_dict: Dictionary mapping registration IDs to lists of RegistrationCharacterRel objects

    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    character_rels_dict = context.get("character_rels_dict")

    # Get character relationships either from provided dict or database query
    if character_rels_dict is not None:
        registration_character_rels = character_rels_dict.get(registration.id, [])
    else:
        query = RegistrationCharacterRel.objects.filter(registration_id=registration.id)
        registration_character_rels = query.order_by("character__number").select_related("character")

    # Build list of character links with names and approval status
    character_links_data = [
        _get_character_links(run, context, features, character_rel) for character_rel in registration_character_rels
    ]
    run_status["character_links"] = character_links_data
    character_links = [_character_links_html(character_entry) for character_entry in character_links_data]

    # Add character information to status details based on number of characters
    if len(character_links) == 1:
        run_status["details_characters"] = format_html("{}: {}", _("Your character is"), character_links[0])
    elif len(character_links) > 1:
        run_status["details_characters"] = format_html(
            "{}: {}",
            _("Your characters are"),
            format_html_join(" - ", "{}", ((link,) for link in character_links)),
        )

    assigned_count = len(character_links)
    is_assigned = assigned_count > 0

    # Count the player's own characters still available to be chosen
    selectable_count = 0
    owned_count = 0
    can_switch = False
    play_max = get_character_play_max(run.event_id, context)
    if "user_character" in features:
        owned_ids = get_player_characters_ids(registration.member, run.event, context)
        assigned_ids = {character_rel.character_id for character_rel in registration_character_rels}
        selectable_count = len(owned_ids - assigned_ids)
        owned_count = len(owned_ids)

        # With no free slot, the played character can still be swapped, if the player created it
        can_switch = play_max == 1 and bool(assigned_ids) and assigned_ids <= owned_ids

    _status_approval(
        run,
        registration,
        run_status,
        features,
        {
            "assigned": assigned_count,
            "selectable": selectable_count,
            "owned": owned_count,
            "play_max": play_max,
        },
        can_switch=can_switch,
        context=context,
    )
    _status_casting(run, registration, run_status, features, context, is_character_assigned=is_assigned)


def _get_character_links(run: Run, context: dict, features: dict, character_rel: RegistrationCharacterRel) -> dict:
    """Builds structured data with links for the character quick access bar."""
    character_url = reverse("character", args=[run.get_slug(), character_rel.character.uuid])
    character_name = character_rel.character.name
    character_uuid = character_rel.character.uuid

    # Use custom name if provided
    if character_rel.custom_name:
        character_name = character_rel.custom_name

    # Add approval status if character approval is enabled and not approved
    approval_required = get_event_config(run.event_id, "user_character_approval", context=context)
    if approval_required and character_rel.character.status != CharacterStatus.APPROVED:
        character_name += f" ({_(character_rel.character.get_status_display())})"

    # Create clickable link for character
    character_links = [
        {
            "url": character_url,
            "label": character_name,
            "tooltip": _("Access your character sheet"),
            "icon": "fa-solid fa-person",
        }
    ]

    allowed_sidebar = context.get("demo_allowed_sidebar")

    if feature_visible("user_character", features, allowed_sidebar):
        character_links.append(
            {
                "url": reverse("character_edit", args=[run.get_slug(), character_uuid]),
                "label": _("Edit"),
                "tooltip": _("Edit your character's details"),
                "icon": "fa-solid fa-pen-to-square",
            }
        )

    if feature_visible("experience", features, allowed_sidebar) and get_event_config(
        run.event_id, "exp_user", context=context
    ):
        character_links.append(
            {
                "url": reverse("character_abilities", args=[run.get_slug(), character_uuid]),
                "label": _("Abilities"),
                "tooltip": _("Buy abilities for your character"),
                "icon": "fa-solid fa-bolt",
            }
        )

    if feature_visible("custom_character", features, allowed_sidebar):
        character_links.append(
            {
                "url": reverse("character_customize", args=[run.get_slug(), character_uuid]),
                "label": _("Customize"),
                "tooltip": _("Modify the character details to make it yours"),
                "icon": "fa-solid fa-palette",
            }
        )

    if feature_visible("player_relationships", features, allowed_sidebar):
        character_links.append(
            {
                "url": reverse("character_relationships", args=[run.get_slug(), character_uuid]),
                "label": _("Relationships"),
                "tooltip": _("Fill in your character's relationships"),
                "icon": "fa-solid fa-people-arrows",
            }
        )

    if feature_visible("help", features, allowed_sidebar):
        character_links.append(
            {
                "url": reverse("help", args=[run.get_slug()]),
                "label": _("Questions"),
                "tooltip": _("Write your questions about the character directly to the authors here."),
                "icon": "fa-solid fa-circle-question",
            }
        )

    return {"name": character_name, "links": character_links}


def _character_links_html(character_entry: dict) -> str:
    """Render the character quick access links as an HTML snippet."""
    character_link_snippets = [
        format_html(
            '<span class="lm_tooltip"><a href="{}">{}</a><span class="lm_tooltiptext">{}!</span></span>',
            link["url"],
            link["label"],
            link["tooltip"],
        )
        for link in character_entry["links"]
    ]

    return format_html_join(" | ", "{}", ((snippet,) for snippet in character_link_snippets))


def _get_character_options_availability(run: Run) -> list[dict[str, Any]]:
    """Return occupancy info for limited character options that don't depend on other options.

    Only options with a max_available limit and no prerequisites (requirements) are
    included, since those are the only ones whose availability can be shown upfront,
    before the player has started answering the character form.

    Args:
        run: The run to compute option occupancy for.

    Returns:
        List of dicts with name, question name, max_available and used count.

    """
    counts = get_registration_counts(run)

    options = WritingOption.objects.filter(
        event_id=run.event_id,
        question__applicable=QuestionApplicable.CHARACTER,
        max_available__gt=0,
        requirements__isnull=True,
    ).select_related("question")

    return [
        {
            "question": option.question.name,
            "name": option.name,
            "available": option.max_available - counts.get(f"option_char_{option.id}", 0),
        }
        for option in options
    ]


def _status_approval(
    run: Run,
    registration: Registration,
    run_status: dict,
    features: dict,
    character_counts: dict,
    *,
    can_switch: bool,
    context: dict | None = None,
) -> None:
    """Add character creation/selection actions to run status based on feature availability.

    This function checks if the user_character feature is enabled and the registration
    is not on a waiting list, then fills run_status["character_actions"] with the available
    actions (create a new character, choose an existing one, confirm a character pending
    approval), and run_status["character_change"] / run_status["character_create"] with the
    links to swap the played character or to create another one, shown only on the event page.

    Args:
        run: Run object containing event information
        registration: The registration object
        features: Dictionary of enabled features for the event
        run_status: Dictionary with run status
        character_counts: Counts of assigned, selectable and owned characters, plus the play maximum
        can_switch: Whether the played character can be swapped for another one of the player
        context: Optional context dictionary, used to read the user_character_approval config

    """
    # Check if user_character feature is enabled
    if "user_character" not in features:
        return

    # Skip if registration is on waiting list
    if registration.ticket and registration.ticket.tier == TicketTier.WAITING:
        return

    # Get character creation limits for this user and event
    reached_maximum, maximum_characters = check_character_maximum(run.event, registration.member)

    assigned_count = character_counts["assigned"]
    selectable_count = character_counts["selectable"]
    owned_count = character_counts["owned"]
    play_max = character_counts["play_max"]

    character_actions = []

    # With more characters allowed, the player already created one is only offered to create another
    if not reached_maximum and owned_count and maximum_characters > 1:
        run_status["character_create"] = {
            "url": reverse("character_create", args=[run.get_slug()]),
            "label": _("Create another character"),
            "tooltip": _("Create another character!"),
            "icon": "fa-solid fa-wand-magic-sparkles",
        }
    # Show character creation action if user can create more characters
    elif not reached_maximum:
        character_actions.append(
            {
                "url": reverse("character_create", args=[run.get_slug()]),
                "label": _("Create your character"),
                "label_long": _("Create the character you will play in this event!"),
                "tooltip": _("Create your character!"),
                "icon": "fa-solid fa-wand-magic-sparkles",
                "status_type": "todo",
                "status_icon": "fa-solid fa-list-check",
                "options_availability": _get_character_options_availability(run),
            }
        )

    # Show character selection action if the player has free slots and characters to choose from
    if selectable_count and assigned_count < play_max:
        character_actions.append(
            {
                "url": reverse("character_list", args=[run.get_slug()]),
                "label": _("Choose your character"),
                "label_long": _("Choose the character you will play in this event!"),
                "tooltip": _("Choose your character!"),
                "icon": "fa-solid fa-users-viewfinder",
                "status_type": "todo",
                "status_icon": "fa-solid fa-list-check",
            }
        )

    # Offer the change link when all slots are taken, but the player can swap the played character
    elif selectable_count and can_switch:
        run_status["character_change"] = {
            "url": reverse("character_list", args=[run.get_slug()]),
            "label": _("Change your character"),
            "tooltip": _("Change your character!"),
            "icon": "fa-solid fa-right-left",
        }

    # Offer a confirm action for the player's own characters still awaiting proposal to the staff
    if "user_character" in features and get_event_config(run.event_id, "user_character_approval", context=context):
        pending_characters = get_player_pending_characters(registration.member, run.event_id, context)
        character_actions.extend(
            {
                "url": reverse("character_confirm", args=[run.get_slug(), character_uuid]),
                "label": _("Confirm character"),
                "label_long": _("Confirm your character %(name)s is ready to propose to the staff!")
                % {"name": character_name},
                "tooltip": _("Confirm your character!"),
                "icon": "fa-solid fa-check",
                "status_type": "todo",
                "status_icon": "fa-solid fa-list-check",
            }
            for character_uuid, character_name in pending_characters
        )

    if character_actions:
        run_status["character_actions"] = character_actions


def casting_preferences_pending(
    run: Run,
    registration: Registration,
    features: dict,
    context: dict | None = None,
    *,
    is_character_assigned: bool = False,
) -> bool:
    """Return True if casting is active and the member still needs to submit preferences.

    Skipped once the character is assigned (casting already happened), once the
    member has already submitted preferences for this run, if the ticket is on
    the waiting list, or if characters aren't visible to players yet.
    """
    if "casting" not in features:
        return False

    if registration.ticket and registration.ticket.tier == TicketTier.WAITING:
        return False

    if is_character_assigned:
        return False

    field_visibility = get_event_config(run.event_id, "writing_field_visibility", context=context)
    if field_visibility and not (context or {}).get("show_character"):
        return False

    return not Casting.objects.filter(run=run, member=registration.member, typ=0).exists()


def _status_casting(
    run: Run,
    registration: Registration,
    run_status: dict,
    features: dict,
    context: dict | None = None,
    *,
    is_character_assigned: bool,
) -> None:
    """Add a reminder link to submit casting preferences, if not already done."""
    if not casting_preferences_pending(
        run, registration, features, context, is_character_assigned=is_character_assigned
    ):
        return

    run_status["casting_action"] = {
        "url": reverse("casting", args=[run.get_slug()]),
        "label": _("Select your preferences"),
        "label_long": _("Select your casting preferences!"),
        "icon": "fa-solid fa-people-arrows",
    }


def get_registration_options(instance: object) -> list[tuple[str, str]]:
    """Get formatted list of registration options and answers for display.

    This function retrieves all registration questions for a given event run,
    filters out skipped questions based on features, and returns the answers
    in a formatted list of question-answer pairs.

    Args:
        instance: Registration instance containing the run and event information.

    Returns:
        List of tuples where each tuple contains:
            - question_name (str): The name of the registration question
            - answer_text (str): The formatted answer text (comma-separated for choices)

    Note:
        Questions are filtered based on event features and individual skip conditions.
        Choice questions are formatted as comma-separated option names.

    """
    formatted_results = []
    applicable_questions = []
    question_ids_cache = []

    # Get event features and filter applicable questions
    event_id = get_run_event_id(instance.run_id)
    event_features = get_event_features(event_id)
    for question in get_cached_registration_questions(event_id):
        if skip_registration_question(question, instance, event_features):
            continue
        applicable_questions.append(question)
        question_ids_cache.append(question["id"])

    # Fetch text answers for all relevant questions
    text_answers_by_question = {}
    for answer in RegistrationAnswer.objects.filter(
        question_id__in=question_ids_cache,
        registration=instance,
        question__typ__in=[BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, BaseQuestionType.EDITOR],
    ):
        text_answers_by_question[answer.question_id] = answer.text

    # Fetch choice answers and group by question
    choice_options_by_question = {}
    for choice in RegistrationChoice.objects.filter(
        question_id__in=question_ids_cache,
        registration=instance,
        question__typ__in=[BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE],
    ).select_related(
        "option",
    ):
        if choice.question_id not in choice_options_by_question:
            choice_options_by_question[choice.question_id] = []
        choice_options_by_question[choice.question_id].append(choice.option)

    # Build result list with question names and formatted answers
    if len(applicable_questions) > 0:
        for question in applicable_questions:
            # Handle multiple choice questions
            if question["id"] in choice_options_by_question:
                formatted_choices = ",".join([option.name for option in choice_options_by_question[question["id"]]])
                formatted_results.append((question["name"], formatted_choices))

            # Handle text answer questions
            if question["id"] in text_answers_by_question:
                formatted_results.append((question["name"], text_answers_by_question[question["id"]]))

    return formatted_results


def get_player_characters(member: Member, event: Event) -> QuerySet[Character]:
    """Get all characters a player has for an event, ordered by most recently updated."""
    return get_event_elements(event.id, Character).filter(player=member).order_by("-updated")


def get_player_signup(context: dict) -> Registration | None:
    """Get active registration for current user in the given run context."""
    if "registration" in context and context["registration"] is not None:
        return context["registration"]

    # Filter registrations for current run and user, excluding cancelled ones
    active_registrations = Registration.objects.filter(
        run=context["run"],
        member=context["member"],
        cancellation_date__isnull=True,
    )

    # Return first registration if exists
    if active_registrations:
        return active_registrations[0]

    return None


def check_signup(context: dict) -> None:
    """Check if player signup is valid and not in waiting status."""
    # Skip signup check for event staff (admins/organizers)
    if context.get("staff"):
        return

    # Get registration
    registration = get_player_signup(context)
    if not registration:
        raise SignupError(context["run"].get_slug())

    # Signup request still awaiting organizer approval
    if registration.pending:
        raise PendingApprovalError(context["run"].get_slug())

    # Check if registration is in waiting list
    if registration.ticket and registration.ticket.tier == TicketTier.WAITING:
        raise WaitingError(context["run"].get_slug())


def check_assign_character(context: dict) -> None:
    """Check and assign characters to player signup.

    Automatically assigns available characters to a player's signup up to the number of
    characters playable at the same time (character_play_max), skipping characters that
    are inactive or already assigned to this registration. When the player owns more
    assignable characters than free slots, nothing is assigned: the choice is left to
    the player on the character list page.

    Args:
        context: Context dictionary containing event data

    Returns:
        None: Function performs side effects only

    """
    # Get registration
    registration = get_player_signup(context)
    if not registration:
        return

    # Get the number of characters the player can play at the same time
    character_play_max = get_character_play_max(context["event"].id, context)

    # Get currently assigned character IDs for this registration
    assigned_character_ids = set(registration.rcrs.values_list("character_id", flat=True))

    # Skip if player already plays the maximum number of characters
    free_slots = character_play_max - len(assigned_character_ids)
    if free_slots <= 0:
        return

    # Get all characters belonging to this player for the event
    characters = get_player_characters(context["member"], context["event"])
    if not characters:
        return

    # Get IDs of inactive characters (those with CharacterConfig inactive=True)
    character_ids = [char.id for char in characters]
    inactive_character_ids = set(
        CharacterConfig.objects.filter(character_id__in=character_ids, name="inactive", value="True").values_list(
            "character_id",
            flat=True,
        ),
    )

    # Filter to get assignable characters (active and not already assigned)
    assignable_characters = [
        char for char in characters if char.id not in inactive_character_ids and char.id not in assigned_character_ids
    ]
    if not assignable_characters:
        return

    # Leave the choice to the player when there are more candidates than free slots
    if len(assignable_characters) > free_slots:
        return

    # Auto-assign the remaining characters
    for character in assignable_characters:
        RegistrationCharacterRel.objects.create(character_id=character.id, registration=registration)


def get_reduced_available_count(run: Any) -> int:
    """Calculate remaining reduced ticket slots based on patron registrations and ratio.

    Args:
        run: Run object to calculate reduced tickets for

    Returns:
        Number of reduced tickets still available

    """
    # Get the ratio for reduced tickets per patron registrations
    reduced_tickets_per_patron_ratio = int(get_event_config(run.event_id, "reduced_ratio"))

    # Count current reduced and patron registrations (excluding cancelled)
    reduced_registrations_count = Registration.objects.filter(
        run=run,
        ticket__tier=TicketTier.REDUCED,
        cancellation_date__isnull=True,
    ).count()
    patron_registrations_count = Registration.objects.filter(
        run=run,
        ticket__tier=TicketTier.PATRON,
        cancellation_date__isnull=True,
        tot_payed__gt=0,
    ).count()

    # Calculate available reduced slots: floor(patron_count * ratio / 10) - used_reduced
    return (
        math.floor(patron_registrations_count * reduced_tickets_per_patron_ratio / 10.0) - reduced_registrations_count
    )


def process_registration_event_change(registration: Registration) -> None:
    """Handle registration updates when switching between events.

    When a registration is moved from one event to another, this function attempts
    to preserve the registration data by finding equivalent tickets, questions, and
    options in the new event based on name matching.

    Args:
        registration: The Registration instance being saved with a potentially
                     changed event assignment.

    Returns:
        None

    Note:
        This function performs case-insensitive name matching to find equivalent
        elements in the target event. If no matching elements are found, the
        corresponding fields are set to None.

    """
    # Early return if this is a new registration (no existing data to migrate)
    if not registration.pk:
        return

    try:
        # Fetch the previous state to compare event changes
        previous_registration = Registration.objects.get(pk=registration.pk)
    except ObjectDoesNotExist:
        return

    # Skip processing if the event hasn't actually changed
    if get_run_event_id(previous_registration.run_id) == get_run_event_id(registration.run_id):
        return

    # Attempt to find a matching ticket in the new event by name
    # This preserves the ticket assignment when moving between events
    ticket_name = registration.ticket.name
    try:
        registration.ticket = get_event_elements(registration.run.event_id, RegistrationTicket).get(
            name__iexact=ticket_name
        )
    except ObjectDoesNotExist:
        registration.ticket = None

    cached_questions = get_cached_registration_questions(registration.run.event_id)

    # Process all registration choices (question/option pairs)
    # Try to find matching questions and options in the new event
    for registration_choice in RegistrationChoice.objects.filter(
        registration=registration, question__typ__in=[BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]
    ):
        question_name = registration_choice.question.name
        option_name = registration_choice.option.name

        try:
            # Find matching question and option in the new event
            matched_question = next(q for q in cached_questions if q["name"].lower() == question_name.lower())
            registration_choice.question_id = matched_question["id"]
            registration_choice.option = get_event_elements(registration.run.event_id, RegistrationOption).get(
                question_id=matched_question["id"],
                name__iexact=option_name,
            )
            registration_choice.save()
        except (StopIteration, ObjectDoesNotExist):
            # Clear the choice if no matching question/option found
            registration_choice.question = None
            registration_choice.option = None

    # Process all registration answers (free-form question responses)
    # Attempt to preserve answers by finding matching questions
    for registration_answer in RegistrationAnswer.objects.filter(
        registration=registration,
        question__typ__in=[BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, BaseQuestionType.EDITOR],
    ):
        question_name = registration_answer.question.name

        try:
            # Find matching question in the new event to preserve the answer
            matched_question = next(q for q in cached_questions if q["name"].lower() == question_name.lower())
            registration_answer.question_id = matched_question["id"]
            registration_answer.save()
        except StopIteration:
            # Clear the answer if no matching question found
            registration_answer.question = None


def check_character_ticket_options(registration: Registration, character: Character) -> None:
    """Remove writing choices incompatible with registration ticket.

    Removes writing choices for a character that are not available
    for the specific ticket type of the registration.

    Args:
        registration: Registration object containing ticket information
        character: Character object to check writing choices for

    """
    # Get the ticket ID from the registration
    registration_ticket_id = registration.ticket.id

    # Track choice IDs that need to be deleted
    incompatible_choice_ids = []

    # Iterate through all writing choices for this character
    choices = WritingChoice.objects.filter(element_id=character.id).prefetch_related("option__tickets")
    for writing_choice in choices:
        # Get list of ticket IDs that allow this writing option
        allowed_ticket_ids = [ticket.pk for ticket in writing_choice.option.tickets.all()]

        # If option has ticket restrictions and current ticket not allowed
        if allowed_ticket_ids and registration_ticket_id not in allowed_ticket_ids:
            incompatible_choice_ids.append(writing_choice.id)

    # Remove all incompatible choices in a single query
    WritingChoice.objects.filter(pk__in=incompatible_choice_ids).delete()


def process_character_ticket_options(instance: Registration) -> None:
    """Process ticket options for characters associated with a registration instance.

    This function checks ticket options for both characters directly associated
    with the registration instance and characters belonging to the member in
    the same event.

    Args:
        instance: Registration instance containing member, ticket, and run information.
                 Must have attributes: member, ticket, run, characters.

    Returns:
        None

    """
    # Early return if no member is associated with the instance
    if not instance.member:
        return

    # Early return if no ticket is associated with the instance
    if not instance.ticket:
        return

    # Get the event from the registration run
    event = instance.run.event

    # Process ticket options for characters directly linked to this registration,
    # plus all characters owned by the member in this event
    characters = set(instance.characters.all()) | set(
        get_event_elements(event.id, Character).filter(player=instance.member)
    )
    for character in characters:
        check_character_ticket_options(instance, character)


def reset_registration_ticket(instance: RegistrationTicket) -> None:
    """Clear accounting cache for all runs in the ticket's event."""
    for run_id in get_event_run_ids(instance.event_id):
        clear_registration_accounting_cache(run_id)
        clear_registration_counts_cache(run_id)
