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

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import _format_decimal, is_registration_provisional
from larpmanager.accounting.member import get_membership_fee_for_reg
from larpmanager.cache.basic import RunBasicCache, get_run_basic_cache
from larpmanager.cache.config import get_association_config
from larpmanager.cache.feature import get_event_features
from larpmanager.models.accounting import AccountingItemMembership, PaymentInvoice, PaymentStatus, PaymentType
from larpmanager.models.event import PreRegistration, RegistrationStatus, Run
from larpmanager.models.member import Member, Membership, MembershipStatus, get_user_membership
from larpmanager.utils.core.common import format_datetime, get_time_diff_today
from larpmanager.utils.core.exceptions import RewokedMembershipError
from larpmanager.utils.registrations.availability import registration_available
from larpmanager.utils.registrations.casting_status import registration_status_characters
from larpmanager.utils.registrations.characters import registration_find

if TYPE_CHECKING:
    from larpmanager.models.registration import Registration


def get_match_reg(r: Run, my_regs: list[Registration]) -> Registration | None:
    """Find registration matching the given run ID."""
    # Iterate through registrations to find matching run
    for m in my_regs:
        if m and m.run_id == r.id:
            return m
    return None


def _status_membership_fee(
    run: Run,
    member: Member,
    user_membership: Membership,
    run_status: dict,
    registration_text: str,
    run_cache: RunBasicCache,
) -> bool:
    """Check if we need to show text regarding membership payment."""
    if user_membership.status != MembershipStatus.ACCEPTED:
        return False

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
    context: dict | None,
    run_cache: RunBasicCache,
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
        run_cache: Basic cache data for the run (association_id, currency_symbol, etc.)

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
    user_membership = get_user_membership(member, run_cache["association_id"])

    # Build base registration message with ticket info if available
    is_provisional = is_registration_provisional(
        registration, features=features, event_id=run.event_id, context=context
    )
    registration_message, registration_message_long = _registration_messages(
        registration, is_provisional=is_provisional, run_cache=run_cache
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
    if "membership" in features and _status_membership_fee(
        run, member, user_membership, run_status, registration_text, run_cache
    ):
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


def _registration_messages(
    registration: Registration, *, is_provisional: bool, run_cache: RunBasicCache
) -> tuple[str, str]:
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
            "currency": run_cache["currency_symbol"],
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

        currency_symbol = get_run_basic_cache(registration.run_id, context=context)["currency_symbol"]
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


def _set_membership_context(
    context: dict, run: Run, member: Member, registration: Any, run_cache: RunBasicCache
) -> None:
    """Set membership data in context for template rendering."""
    if not run.start or "membership" not in context.get("features", {}):
        return
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
            run_cache = get_run_basic_cache(run.id, context=context)
            _set_membership_context(context, run, member, registration, run_cache)
            registration_status_signed(
                run, registration, member, features, register_url, run_status, context, run_cache
            )
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
