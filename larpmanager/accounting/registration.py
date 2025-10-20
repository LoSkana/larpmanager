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

import logging
import math
from datetime import datetime
from decimal import Decimal
from typing import Optional

from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.accounting.token_credit import handle_tokes_credits
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.links import reset_event_links
from larpmanager.mail.registration import update_registration_status_bkg
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemOther,
    AccountingItemPayment,
    AccountingItemTransaction,
    OtherChoices,
    PaymentChoices,
)
from larpmanager.models.casting import AssignmentTrait
from larpmanager.models.event import DevelopStatus, Event, Run
from larpmanager.models.form import RegistrationChoice
from larpmanager.models.member import MembershipStatus, get_user_membership
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationInstallment,
    RegistrationSurcharge,
    TicketTier,
)
from larpmanager.models.utils import get_sum
from larpmanager.utils.common import get_time_diff, get_time_diff_today
from larpmanager.utils.tasks import background_auto

logger = logging.getLogger(__name__)


def get_reg_iscr(instance) -> int:
    """Calculate total registration signup fee including discounts.

    Computes the total registration fee by adding base ticket price, additional
    tickets, pay-what-you-want amount, registration choices, and surcharges,
    then subtracting applicable discounts (excluding gifted registrations).

    Args:
        instance: Registration instance to calculate fee for. Must have attributes:
                 ticket, additionals, pay_what, member_id, run_id, redeem_code, surcharge

    Returns:
        int: Total signup fee after applying discounts and surcharges, minimum 0

    Note:
        Discounts are not applied to registrations with redeem codes (gifted registrations).
    """
    # Initialize total registration fee
    tot_iscr = 0

    # Add base ticket price and additional tickets
    if instance.ticket:
        tot_iscr += instance.ticket.price

        if instance.additionals:
            tot_iscr += instance.ticket.price * instance.additionals

    # Add pay-what-you-want amount
    if instance.pay_what:
        tot_iscr += instance.pay_what

    # Add registration choice options pricing
    for c in RegistrationChoice.objects.filter(reg=instance).select_related("option"):
        tot_iscr += c.option.price

    # Apply discounts only for non-gifted registrations
    if not instance.redeem_code:
        que = AccountingItemDiscount.objects.filter(member_id=instance.member_id, run_id=instance.run_id)
        for el in que.select_related("disc"):
            tot_iscr -= el.disc.value

    # Add any surcharge amount
    tot_iscr += instance.surcharge

    # Ensure total is never negative
    tot_iscr = max(0, tot_iscr)

    return tot_iscr


def get_reg_payments(reg, acc_payments=None) -> int:
    """Calculate total payments made for a registration.

    This function computes the total amount paid for a registration by summing
    all associated accounting item payments. It also populates a payments
    dictionary on the registration object for detailed breakdown.

    Args:
        reg: Registration instance to calculate payments for
        acc_payments: Optional queryset of AccountingItemPayment objects.
            If None, will query all non-hidden payments for the registration.

    Returns:
        Total amount paid as an integer

    Side Effects:
        Sets reg.payments dictionary with payment breakdown where keys are
        payment objects and values are total amounts paid per payment.
    """
    # Query payments if not provided
    if acc_payments is None:
        acc_payments = AccountingItemPayment.objects.filter(
            reg=reg,
        ).exclude(hide=True)

    # Initialize tracking variables
    tot_payed = 0
    reg.payments = {}

    # Process each accounting item payment
    for aip in acc_payments:
        # Initialize payment entry if not exists
        if aip.pay not in reg.payments:
            reg.payments[aip.pay] = 0

        # Add payment value to both total and payment-specific tracking
        reg.payments[aip.pay] += aip.value
        tot_payed += aip.value

    return tot_payed


def get_reg_transactions(reg: Registration) -> int:
    """Calculate total transaction fees for a registration.

    Computes the sum of all accounting item transaction values that are marked
    as user burden for the given registration.

    Args:
        reg: Registration instance to calculate fees for

    Returns:
        Total transaction fees in cents that are user burden

    Example:
        >>> registration = Registration.objects.get(id=1)
        >>> total_fees = get_reg_transactions(registration)
        >>> print(f"Total fees: {total_fees}")
    """
    # Initialize running total for transaction fees
    tot_trans = 0

    # Get all user burden transactions for this registration
    acc_transactions = AccountingItemTransaction.objects.filter(reg=reg, user_burden=True)

    # Sum up all transaction values
    for ait in acc_transactions:
        tot_trans += ait.value

    return tot_trans


def get_accounting_refund(reg: Registration) -> None:
    """Get refund information for a registration.

    Retrieves all cancellation-related accounting items for the given registration
    and calculates total refund amounts grouped by refund type. Results are stored
    in the registration's refunds attribute as a dictionary.

    Args:
        reg: Registration instance to get refunds for. Must have run_id and member_id
             attributes.

    Returns:
        None: Function modifies reg.refunds in place.

    Side Effects:
        - Sets reg.refunds dictionary with refund amounts by type
        - May set reg.acc_refunds if not already present
    """
    # Initialize refunds dictionary to store refund amounts by type
    reg.refunds = {}

    # Fetch accounting refund items if not already cached on the registration
    if not hasattr(reg, "acc_refunds"):
        reg.acc_refunds = AccountingItemOther.objects.filter(
            run_id=reg.run_id, member_id=reg.member_id, cancellation=True
        )

    # Early return if no refunds exist for this registration
    if not reg.acc_refunds:
        return

    # Calculate total refund amounts grouped by refund type
    for aio in reg.acc_refunds:
        # Initialize refund type entry if not present
        if aio.oth not in reg.refunds:
            reg.refunds[aio.oth] = 0
        # Accumulate refund value for this type
        reg.refunds[aio.oth] += aio.value


def quota_check(reg, start, alert: int, assoc_id: int) -> None:
    """Check payment quotas and deadlines for a registration.

    Calculates payment quotas based on event start date and registration timing.
    Sets quota amount and deadline for next payment.

    Args:
        reg: Registration instance to check quotas for
        start: Event start date
        alert: Alert threshold in days before event
        assoc_id: Association ID for payment deadline calculation

    Side effects:
        Sets reg.quota, reg.deadline, and reg.qsr attributes on the registration instance
    """
    # Early return if no event start date provided
    if not start:
        return

    # Calculate days until event and total days since registration
    reg.days_event = get_time_diff_today(start)
    reg.tot_days = get_time_diff(start, reg.created.date())

    # Initialize quota calculation variables
    qs = Decimal(1.0 / reg.quotas)  # Quota step percentage
    cnt = 0  # Current quota counter
    qsr = 0  # Cumulative quota percentage
    first_deadline = True

    # Iterate through each quota payment
    for _i in range(0, reg.quotas):
        qsr += qs
        cnt += 1

        # Calculate deadline for current quota
        if cnt == 1:
            # First quota deadline is immediate (8 days from registration)
            deadline = get_payment_deadline(reg, 8, assoc_id)
        else:
            # Subsequent deadlines calculated based on remaining time to event
            left = reg.tot_days * 1.0 * (reg.quotas - (cnt - 1)) / reg.quotas
            deadline = math.floor(reg.days_event - left)

        # Skip if deadline is beyond alert threshold
        if deadline >= alert:
            continue

        reg.qsr = qsr

        # Calculate quota amount
        if cnt == reg.quotas:
            # Last quota: remaining unpaid amount
            reg.quota = reg.tot_iscr - reg.tot_payed
        else:
            # Regular quota: proportional amount minus already paid
            reg.quota = reg.tot_iscr * qsr - reg.tot_payed
            reg.quota = math.floor(reg.quota)

        # Skip if no payment needed for this quota
        if reg.quota <= 0:
            continue

        # Set first valid deadline
        if first_deadline and deadline:
            first_deadline = False
            reg.deadline = deadline

        # Skip expired deadlines and continue to next quota
        if not deadline or deadline < 0:
            continue

        return


def installment_check(reg: Registration, alert: int, assoc_id: int) -> None:
    """Check installment payment schedule for a registration.

    Processes configured installments for the event and determines
    next payment amount and deadline based on the installment schedule.
    Updates the registration's quota and deadline fields as side effects.

    Args:
        reg: Registration instance to check installments for
        alert: Alert threshold in days for deadline filtering
        assoc_id: Association ID used for payment deadline calculation

    Returns:
        None

    Side Effects:
        - Sets reg.quota to the amount due for the next installment
        - Sets reg.deadline to the deadline for the next payment
    """
    # Early return if registration has no ticket
    if not reg.ticket:
        return

    tot = 0

    # Get all installments for this event, ordered by sequence
    que = RegistrationInstallment.objects.filter(event_id=reg.run.event_id)
    que = que.annotate(tickets_map=ArrayAgg("tickets")).order_by("order")

    first_deadline = True

    # Process each installment in order
    for i in que:
        # Filter installments that apply to this ticket type
        tickets_id = [ticket_id for ticket_id in i.tickets_map if ticket_id is not None]
        if tickets_id and reg.ticket_id not in tickets_id:
            continue

        # Calculate deadline for this installment
        deadline = _get_deadline_installment(assoc_id, i, reg)

        # Skip installments that are still within alert threshold
        if deadline and deadline >= alert:
            continue

        # Calculate cumulative amount due up to this installment
        if i.amount:
            tot += i.amount
        else:
            tot = reg.tot_iscr

        # Ensure total doesn't exceed registration total
        tot = min(tot, reg.tot_iscr)

        # Calculate outstanding amount for this installment
        reg.quota = max(tot - reg.tot_payed, 0)

        logger.debug(f"Registration {reg.id} installment quota calculated: {reg.quota}")

        # Skip if nothing is due for this installment
        if reg.quota <= 0:
            continue

        # Set deadline for the first applicable installment
        if first_deadline and deadline:
            first_deadline = False
            reg.deadline = deadline

        # Skip to next installment if deadline has passed
        if not deadline or deadline < 0:
            continue

        return

    # Fallback: if no installments found, use registration date and full amount
    if not tot:
        reg.deadline = get_time_diff_today(reg.created.date())
        reg.quota = reg.tot_iscr - reg.tot_payed


def _get_deadline_installment(assoc_id: int, i: RegistrationInstallment, reg: Registration) -> int | None:
    """Calculate deadline for a specific installment.

    Args:
        assoc_id: Association ID for payment deadline calculation
        i: RegistrationInstallment instance containing deadline configuration
        reg: Registration instance for deadline calculation context

    Returns:
        Days until deadline as integer, or None if no deadline is configured
    """
    # Check if installment has a relative deadline in days
    if i.days_deadline:
        deadline = get_payment_deadline(reg, i.days_deadline, assoc_id)
    # Check if installment has an absolute deadline date
    elif i.date_deadline:
        deadline = get_time_diff_today(i.date_deadline)
    # No deadline configured for this installment
    else:
        deadline = None
    return deadline


def get_payment_deadline(reg: Registration, i: int, assoc_id: int) -> int:
    """Calculate payment deadline based on registration and membership dates.

    Determines the payment deadline by finding the maximum time difference between
    today and either the registration creation date or membership date, then adds
    the specified number of days.

    Args:
        reg: Registration instance containing creation date and optional membership
        i: Number of days to add to the base date calculation
        assoc_id: Association ID used for membership lookup

    Returns:
        The total number of days until the payment deadline, calculated as the
        maximum of registration or membership age plus the additional days
    """
    # Calculate days since registration was created
    dd = get_time_diff_today(reg.created.date())

    # Ensure membership is loaded for this registration
    if not hasattr(reg, "membership"):
        reg.membership = get_user_membership(reg.member, assoc_id)

    # Use membership date if available and more recent than registration
    if reg.membership.date:
        dd = max(dd, get_time_diff_today(reg.membership.date))

    # Add the specified number of days to the base calculation
    return dd + i


def registration_payments_status(reg: Registration) -> None:
    """Determine registration payment status based on total amounts.

    Calculates and sets the payment_status field on the registration based on
    the comparison between total amount owed and total amount paid.

    Args:
        reg: Registration instance to check and update payment status for.
             Must have tot_iscr (total registration amount) and tot_payed
             (total amount paid) attributes.

    Returns:
        None: Modifies the reg.payment_status field in-place.

    Note:
        Payment status codes:
        - 'c': Complete (paid in full)
        - 'n': Not paid (no payments made)
        - 'p': Partial (underpaid)
        - 't': Overpaid (paid more than owed)
    """
    # Initialize payment status to empty string
    reg.payment_status = ""

    # Only process if there's an amount owed
    if reg.tot_iscr > 0:
        # Check if payment matches exactly what's owed
        if reg.tot_payed == reg.tot_iscr:
            reg.payment_status = "c"  # Complete payment
        elif reg.tot_payed == 0:
            reg.payment_status = "n"  # No payment made
        elif reg.tot_payed < reg.tot_iscr:
            reg.payment_status = "p"  # Partial payment
        else:
            reg.payment_status = "t"  # Overpaid (more than owed)


def cancel_run(instance: Run) -> None:
    """Cancel all registrations for a run and process refunds.

    Cancels all active registrations for the specified run and processes
    appropriate refunds based on payment methods used.

    Args:
        instance: Run instance to cancel registrations for

    Side Effects:
        - Cancels all non-cancelled registrations for the run
        - Deletes token and credit payments for all registrations
        - Creates credit entries for money payments as refunds
        - Marks all registrations as refunded
    """
    # Cancel all active registrations for this run
    for r in Registration.objects.filter(cancellation_date__isnull=True, run=instance):
        cancel_reg(r)

    # Process refunds for all non-refunded registrations
    for r in Registration.objects.filter(refunded=False, run=instance):
        # Remove token payments (tokens are returned to pool)
        AccountingItemPayment.objects.filter(
            member_id=r.member_id, pay=PaymentChoices.TOKEN, reg__run=instance
        ).delete()

        # Remove credit payments (credits are returned to balance)
        AccountingItemPayment.objects.filter(
            member_id=r.member_id, pay=PaymentChoices.CREDIT, reg__run=instance
        ).delete()

        # Calculate total money payments for this member/run
        money = get_sum(
            AccountingItemPayment.objects.filter(member_id=r.member_id, pay=PaymentChoices.MONEY, reg__run=instance)
        )

        # Create credit entry for money refund if there were money payments
        if money > 0:
            AccountingItemOther.objects.create(
                member_id=r.member_id,
                oth=OtherChoices.CREDIT,
                descr=f"Refund per {instance}",
                run=instance,
                value=money,
            )

        # Mark registration as refunded
        r.refunded = True
        r.save()


def cancel_reg(reg: Registration) -> None:
    """Cancel a specific registration and clean up related data.

    This function performs a complete cancellation of a registration by setting
    the cancellation date and removing all associated data including characters,
    traits, discounts, and bonus items.

    Args:
        reg: Registration instance to cancel

    Returns:
        None

    Side Effects:
        - Sets registration cancellation_date to current datetime
        - Deletes all registration character relationships
        - Removes trait assignments for the member in this run
        - Deletes accounting item discounts for the member in this run
        - Removes bonus credits and tokens associated with this registration
        - Resets event links for the member in the associated organization
    """
    # Set cancellation timestamp
    reg.cancellation_date = datetime.now()
    reg.save()

    # Remove character associations for this registration
    RegistrationCharacterRel.objects.filter(reg=reg).delete()

    # Clean up trait assignments for this member and run
    AssignmentTrait.objects.filter(run_id=reg.run_id, member_id=reg.member_id).delete()

    # Remove any accounting discounts for this member and run
    AccountingItemDiscount.objects.filter(run_id=reg.run_id, member_id=reg.member_id).delete()

    # Delete bonus credits and tokens linked to this registration
    AccountingItemOther.objects.filter(ref_addit=reg.id).delete()

    # Reset member's event links for the organization
    reset_event_links(reg.member.id, reg.run.event.assoc_id)


def get_display_choice(choices: list[tuple[str, str]], k: str) -> str:
    """Get display name for a choice field value.

    Args:
        choices: List of (key, display_name) tuples representing available choices
        k: Key to look up display name for

    Returns:
        Display name for the key, empty string if not found

    Examples:
        >>> choices = [('active', 'Active'), ('inactive', 'Inactive')]
        >>> get_display_choice(choices, 'active')
        'Active'
        >>> get_display_choice(choices, 'unknown')
        ''
    """
    # Iterate through all available choice tuples
    for key, d in choices:
        # Check if current key matches the requested key
        if key == k:
            return d

    # Return empty string if no matching key found
    return ""


def round_to_nearest_cent(number: float) -> float:
    """Round a number to the nearest cent with tolerance for small differences.

    This function rounds a number to one decimal place (nearest cent) but only
    applies the rounding if the difference between the original and rounded
    values is within an acceptable tolerance. This prevents excessive rounding
    errors while still providing useful cent-level precision.

    Args:
        number: The numeric value to round to the nearest cent.

    Returns:
        The rounded number if within tolerance, otherwise the original number
        as a float.

    Example:
        >>> round_to_nearest_cent(12.34)
        12.3
        >>> round_to_nearest_cent(12.39)
        12.4
        >>> round_to_nearest_cent(12.345)
        12.345
    """
    # Round to nearest cent (one decimal place)
    rounded = round(number * 10) / 10

    # Define maximum acceptable rounding difference
    max_rounding = 0.03

    # Check if rounding difference is within tolerance
    if abs(float(number) - rounded) <= max_rounding:
        return rounded

    # Return original value if rounding would cause too much error
    return float(number)


def process_registration_pre_save(registration):
    """Process registration before saving.

    Args:
        registration: Registration instance being saved
    """
    registration.surcharge = get_date_surcharge(registration, registration.run.event)
    registration.member.join(registration.run.event.assoc)


def get_date_surcharge(reg: Optional[Registration], event: Event) -> int:
    """Calculate date-based surcharge for a registration.

    Calculates the total surcharge amount based on when a registration was created
    relative to the event's surcharge dates. Staff, NPC, and waiting list tickets
    are exempt from surcharges.

    Args:
        reg: Registration instance. If None, uses current date for calculation.
        event: Event instance to get surcharges for.

    Returns:
        Total surcharge amount in cents based on registration date.
    """
    # Skip surcharges for special ticket tiers
    if reg and reg.ticket:
        t = reg.ticket.tier
        if t in (TicketTier.WAITING, TicketTier.STAFF, TicketTier.NPC):
            return 0

    # Use registration creation date or current date
    dt = datetime.now().date()
    if reg and reg.created:
        dt = reg.created

    # Get all surcharges that apply before the registration date
    surs = RegistrationSurcharge.objects.filter(event=event, date__lt=dt)
    if not surs:
        return 0

    # Sum all applicable surcharges
    tot = 0
    for s in surs:
        tot += s.amount

    return tot


def handle_registration_accounting_updates(registration: Registration) -> None:
    """Handle post-save accounting updates for registrations.

    This function performs several critical accounting operations after a registration
    is saved, including transferring payments from cancelled registrations, updating
    accounting calculations, and triggering status change notifications.

    Args:
        registration: Registration instance that was saved. Must have a valid member
                     relationship for processing to continue.

    Returns:
        None

    Note:
        This function modifies the registration's accounting fields and may trigger
        background email notifications for status changes.
    """
    # Early return if no member is associated with the registration
    if not registration.member:
        return

    # Transfer payments from cancelled registrations to the current one
    # Only process if the current registration is not cancelled
    if not registration.cancellation_date:
        # Find all cancelled registrations for the same run and member
        cancelled = Registration.objects.filter(
            run_id=registration.run_id, member_id=registration.member_id, cancellation_date__isnull=False
        )
        cancelled = list(cancelled.values_list("pk", flat=True))

        # Transfer accounting items from cancelled registrations
        if cancelled:
            for typ in [AccountingItemPayment, AccountingItemTransaction]:
                for el in typ.objects.filter(reg__id__in=cancelled):
                    el.reg = registration
                    el.save()

    # Store the provisional status before accounting updates
    old_provisional = is_reg_provisional(registration)

    # Recalculate all accounting fields for the registration
    update_registration_accounting(registration)

    # Bulk update accounting fields without triggering another save signal
    # This prevents recursive save operations while updating calculated fields
    updates = {}
    for field in ["tot_payed", "tot_iscr", "quota", "alert", "deadline", "payment_date"]:
        updates[field] = getattr(registration, field)
    Registration.objects.filter(pk=registration.pk).update(**updates)

    # Trigger background email notification if registration status changed from provisional
    if old_provisional and not is_reg_provisional(registration):
        update_registration_status_bkg(registration.id)


def process_accounting_discount_post_save(discount_item):
    """Process accounting discount item after save.

    Args:
        discount_item: AccountingItemDiscount instance that was saved
    """
    if discount_item.run and not discount_item.expires:
        for reg in Registration.objects.filter(member_id=discount_item.member_id, run_id=discount_item.run_id):
            reg.save()


def log_registration_ticket_saved(ticket):
    """Process registration ticket after save.

    Args:
        ticket: RegistrationTicket instance that was saved
    """
    logger.debug(f"RegistrationTicket saved: {ticket} at {datetime.now()}")
    check_reg_events(ticket.event)


def process_registration_option_post_save(option):
    """Process registration option after save.

    Args:
        option: RegistrationOption instance that was saved
    """
    logger.debug(f"RegistrationOption saved: {option} at {datetime.now()}")
    check_reg_events(option.question.event)


def check_reg_events(event: Event) -> None:
    """Trigger background accounting updates for all registrations in an event.

    This function collects all registration IDs from all runs within the given event
    and queues them for background processing to update their accounting information.

    Args:
        event: Event instance to update registrations for. Must have a 'runs'
               relationship that contains Run objects with 'registrations'.

    Returns:
        None

    Side Effects:
        Queues a background task via check_reg_bkg() to update accounting
        for all collected registrations.

    Example:
        >>> event = Event.objects.get(id=1)
        >>> check_reg_events(event)  # Queues accounting updates for all registrations
    """
    # Initialize list to collect all registration IDs
    regs = []

    # Iterate through all runs in the event
    for run in event.runs.all():
        # Extract registration IDs for current run and convert to strings
        for reg_id in run.registrations.values_list("id", flat=True):
            regs.append(str(reg_id))

    # Queue background task with comma-separated registration IDs
    check_reg_bkg(",".join(regs))


@background_auto(queue="acc")
def check_reg_bkg(reg_ids):
    if isinstance(reg_ids, int):
        check_reg_bkg_go(reg_ids)
    elif isinstance(reg_ids, str):
        for reg_id in reg_ids.split(","):
            check_reg_bkg_go(reg_id)
    else:
        for reg_id in reg_ids:
            check_reg_bkg_go(reg_id)


def check_reg_bkg_go(reg_id: int | None) -> None:
    """Update accounting for a single registration in background task.

    This function retrieves a registration by ID and triggers a save operation
    to update its accounting information. It's designed to be called as a
    background task and handles missing registrations gracefully.

    Args:
        reg_id: Registration ID to update. If None or falsy, function returns early.

    Returns:
        None

    Side Effects:
        Triggers registration save to update accounting if registration exists.
        The save operation may update related accounting records and balances.
    """
    # Early return if no registration ID provided
    if not reg_id:
        return

    try:
        # Retrieve the registration instance from database
        instance = Registration.objects.get(pk=reg_id)

        # Trigger save to update accounting information
        # This will run any post_save signals and update related records
        instance.save()
    except ObjectDoesNotExist:
        # Registration not found - silently ignore as this is a background task
        return


def update_registration_accounting(reg: Registration) -> None:
    """Update comprehensive accounting information for a registration.

    Calculates total signup fee, payments received, outstanding balance,
    payment quotas, and deadlines based on event configuration.

    Args:
        reg (Registration): Registration instance to update accounting for

    Returns:
        None

    Side Effects:
        Updates the following registration attributes:
        - reg.tot_iscr: Total inscription amount
        - reg.tot_payed: Total amount paid
        - reg.quota: Payment quota amount
        - reg.deadline: Payment deadline
        - reg.alert: Alert flag for upcoming deadlines
        - reg.payment_date: Date when payment was completed (if applicable)
    """
    # Skip processing for cancelled or completed runs
    for s in [DevelopStatus.CANC, DevelopStatus.DONE]:
        if reg.run.development == s:
            return

    max_rounding = 0.05

    # Extract basic event information
    start = reg.run.start
    features = get_event_features(reg.run.event_id)
    assoc_id = reg.run.event.assoc_id

    # Calculate total inscription fee and payments
    reg.tot_iscr = get_reg_iscr(reg)
    tot_trans = get_reg_transactions(reg)
    reg.tot_payed = get_reg_payments(reg)

    # Adjust for transactions and round to nearest cent
    reg.tot_payed -= tot_trans
    reg.tot_payed = Decimal(round_to_nearest_cent(reg.tot_payed))

    # Initialize payment tracking fields
    reg.quota = 0
    reg.deadline = 0
    reg.alert = False

    # Check if payment is complete (within rounding tolerance)
    remaining = reg.tot_iscr - reg.tot_payed
    if -max_rounding < remaining <= max_rounding:
        if not reg.payment_date:
            reg.payment_date = datetime.now()
        return

    # Skip further processing if registration is cancelled
    if reg.cancellation_date:
        return

    # Handle membership requirements for non-LAOG events
    if "membership" in features and "laog" not in features:
        if not hasattr(reg, "membership"):
            reg.membership = get_user_membership(reg.member, assoc_id)
        if reg.membership.status != MembershipStatus.ACCEPTED:
            return

    # Process tokens and credits
    handle_tokes_credits(assoc_id, features, reg, remaining)

    # Get payment alert threshold from event configuration
    alert = int(reg.run.event.get_config("payment_alert", 30, bypass_cache=True))

    # Calculate payment schedule based on feature flags
    if "reg_installments" in features:
        installment_check(reg, alert, assoc_id)
    else:
        quota_check(reg, start, alert, assoc_id)

    # Skip alert setting if quota is negligible
    if reg.quota <= max_rounding:
        return

    # Set alert flag based on deadline proximity
    reg.alert = reg.deadline < alert


def update_member_registrations(member):
    """Trigger accounting updates for all registrations of a member.

    Args:
        member: Member instance to update registrations for

    Side effects:
        Saves all registrations to trigger accounting recalculation
    """
    for reg in Registration.objects.filter(member=member):
        reg.save()
