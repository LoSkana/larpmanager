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
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Union

from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.accounting.token_credit import handle_tokes_credits
from larpmanager.cache.config import get_event_config
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
from larpmanager.models.event import DevelopStatus
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

    Computes the total registration fee by summing base ticket price, additional
    tickets, pay-what-you-want amounts, registration choices, and surcharges,
    then applying any applicable discounts (except for gifted registrations).

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

    # Add registration choice options (extras, meals, etc.)
    for c in RegistrationChoice.objects.filter(reg=instance).select_related("option"):
        tot_iscr += c.option.price

    # Apply discounts only for non-gifted registrations
    if not instance.redeem_code:
        que = AccountingItemDiscount.objects.filter(member_id=instance.member_id, run_id=instance.run_id)
        for el in que.select_related("disc"):
            tot_iscr -= el.disc.value

    # Add any surcharges
    tot_iscr += instance.surcharge

    # Ensure fee is never negative
    tot_iscr = max(0, tot_iscr)

    return tot_iscr


def get_reg_payments(registration, accounting_payments=None):
    """Calculate total payments made for a registration.

    Args:
        registration: Registration instance
        accounting_payments: Optional queryset of payments, will query if None

    Returns:
        int: Total amount paid

    Side effects:
        Sets registration.payments dictionary with payment breakdown
    """
    if accounting_payments is None:
        accounting_payments = AccountingItemPayment.objects.filter(
            reg=registration,
        ).exclude(hide=True)

    total_paid = 0
    registration.payments = {}

    for accounting_item_payment in accounting_payments:
        if accounting_item_payment.pay not in registration.payments:
            registration.payments[accounting_item_payment.pay] = 0
        registration.payments[accounting_item_payment.pay] += accounting_item_payment.value
        total_paid += accounting_item_payment.value

    return total_paid


def get_reg_transactions(reg):
    """Calculate total transaction fees for a registration.

    Args:
        reg: Registration instance to calculate fees for

    Returns:
        int: Total transaction fees that are user burden
    """
    tot_trans = 0

    acc_transactions = AccountingItemTransaction.objects.filter(reg=reg, user_burden=True)

    for ait in acc_transactions:
        tot_trans += ait.value

    return tot_trans


def get_accounting_refund(reg):
    """Get refund information for a registration.

    Args:
        reg: Registration instance to get refunds for

    Side effects:
        Sets reg.refunds dictionary with refund amounts by type
    """
    reg.refunds = {}

    if not hasattr(reg, "acc_refunds"):
        reg.acc_refunds = AccountingItemOther.objects.filter(
            run_id=reg.run_id, member_id=reg.member_id, cancellation=True
        )

    if not reg.acc_refunds:
        return

    for aio in reg.acc_refunds:
        if aio.oth not in reg.refunds:
            reg.refunds[aio.oth] = 0
        reg.refunds[aio.oth] += aio.value


def quota_check(reg, start, alert, assoc_id):
    """Check payment quotas and deadlines for a registration.

    Calculates payment quotas based on event start date and registration timing.
    Sets quota amount and deadline for next payment.

    Args:
        reg: Registration instance to check quotas for
        start: Event start date
        alert: Alert threshold in days
        assoc_id: Association ID for payment deadline calculation

    Side effects:
        Sets reg.quota, reg.deadline, and reg.qsr attributes
    """
    if not start:
        return

    reg.days_event = get_time_diff_today(start)
    reg.tot_days = get_time_diff(start, reg.created.date())

    qs = Decimal(1.0 / reg.quotas)
    cnt = 0
    qsr = 0
    first_deadline = True
    for _i in range(0, reg.quotas):
        qsr += qs
        cnt += 1

        # if first, deadline is immediately
        if cnt == 1:
            deadline = get_payment_deadline(reg, 8, assoc_id)
        # else, deadline is computed in days to the event
        else:
            left = reg.tot_days * 1.0 * (reg.quotas - (cnt - 1)) / reg.quotas
            deadline = math.floor(reg.days_event - left)

        if deadline >= alert:
            continue

        reg.qsr = qsr

        # if last quota
        if cnt == reg.quotas:
            reg.quota = reg.tot_iscr - reg.tot_payed
        else:
            reg.quota = reg.tot_iscr * qsr - reg.tot_payed
            reg.quota = math.floor(reg.quota)

        if reg.quota <= 0:
            continue

        if first_deadline and deadline:
            first_deadline = False
            reg.deadline = deadline

        # go to next quota if deadline was missed
        if not deadline or deadline < 0:
            continue

        return


def installment_check(reg: "Registration", alert: int, assoc_id: int) -> None:
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


def _get_deadline_installment(assoc_id, i, reg):
    """Calculate deadline for a specific installment.

    Args:
        assoc_id: Association ID for payment deadline calculation
        i: RegistrationInstallment instance
        reg: Registration instance

    Returns:
        int or None: Days until deadline, None if no deadline configured
    """
    if i.days_deadline:
        deadline = get_payment_deadline(reg, i.days_deadline, assoc_id)
    elif i.date_deadline:
        deadline = get_time_diff_today(i.date_deadline)
    else:
        deadline = None
    return deadline


def get_payment_deadline(registration, days_to_add, association_id):
    """Calculate payment deadline based on registration and membership dates.

    Args:
        registration: Registration instance
        days_to_add: Number of days to add to base date
        association_id: Association ID for membership lookup

    Returns:
        int: Days until payment deadline
    """
    days_since_registration = get_time_diff_today(registration.created.date())
    if not hasattr(registration, "membership"):
        registration.membership = get_user_membership(registration.member, association_id)
    if registration.membership.date:
        days_since_registration = max(days_since_registration, get_time_diff_today(registration.membership.date))
    return days_since_registration + days_to_add


def registration_payments_status(reg):
    """Determine registration payment status and balance.

    Args:
        reg: Registration instance to check status for

    Returns:
        tuple: (is_paid, balance) where is_paid is boolean and balance is amount owed
    """
    reg.payment_status = ""
    if reg.tot_iscr > 0:
        if reg.tot_payed == reg.tot_iscr:
            reg.payment_status = "c"
        elif reg.tot_payed == 0:
            reg.payment_status = "n"
        elif reg.tot_payed < reg.tot_iscr:
            reg.payment_status = "p"
        else:
            reg.payment_status = "t"


def cancel_run(instance):
    """Cancel all registrations for a run and process refunds.

    Args:
        instance: Run instance to cancel registrations for

    Side effects:
        Cancels all non-cancelled registrations and processes refunds
        for non-refunded registrations
    """
    for r in Registration.objects.filter(cancellation_date__isnull=True, run=instance):
        cancel_reg(r)
    for r in Registration.objects.filter(refunded=False, run=instance):
        AccountingItemPayment.objects.filter(
            member_id=r.member_id, pay=PaymentChoices.TOKEN, reg__run=instance
        ).delete()
        AccountingItemPayment.objects.filter(
            member_id=r.member_id, pay=PaymentChoices.CREDIT, reg__run=instance
        ).delete()
        money = get_sum(
            AccountingItemPayment.objects.filter(member_id=r.member_id, pay=PaymentChoices.MONEY, reg__run=instance)
        )
        if money > 0:
            AccountingItemOther.objects.create(
                member_id=r.member_id,
                oth=OtherChoices.CREDIT,
                descr=f"Refund per {instance}",
                run=instance,
                value=money,
            )
        r.refunded = True
        r.save()


def cancel_reg(registration):
    """Cancel a specific registration and clean up related data.

    Args:
        registration: Registration instance to cancel

    Side effects:
        Sets cancellation date, deletes characters, traits, discounts,
        bonus items, and resets event links
    """
    registration.cancellation_date = datetime.now()
    registration.save()

    # delete characters related
    RegistrationCharacterRel.objects.filter(reg=registration).delete()

    # delete trait assignments
    AssignmentTrait.objects.filter(run_id=registration.run_id, member_id=registration.member_id).delete()

    # delete discounts
    AccountingItemDiscount.objects.filter(run_id=registration.run_id, member_id=registration.member_id).delete()

    # delete bonus credits / tokens
    AccountingItemOther.objects.filter(ref_addit=registration.id).delete()

    # Reset event links
    reset_event_links(registration.member_id, registration.run.event.assoc_id)


def get_display_choice(choices, key):
    """Get display name for a choice field value.

    Args:
        choices: List of (key, display_name) tuples
        key: Key to look up display name for

    Returns:
        str: Display name for the key, empty string if not found
    """
    for choice_key, display_name in choices:
        if choice_key == key:
            return display_name
    return ""


def round_to_nearest_cent(amount):
    """Round a number to the nearest cent with tolerance for small differences.

    Args:
        amount: Number to round

    Returns:
        float: Rounded number, original if difference exceeds tolerance
    """
    rounded_amount = round(amount * 10) / 10
    rounding_tolerance = 0.03
    if abs(float(amount) - rounded_amount) <= rounding_tolerance:
        return rounded_amount
    return float(amount)


def process_registration_pre_save(registration):
    """Process registration before saving.

    Args:
        registration: Registration instance being saved
    """
    registration.surcharge = get_date_surcharge(registration, registration.run.event)
    registration.member.join(registration.run.event.assoc)


def get_date_surcharge(registration, event):
    """Calculate date-based surcharge for a registration.

    Args:
        registration: Registration instance (None for current date)
        event: Event instance to get surcharges for

    Returns:
        int: Total surcharge amount based on registration date
    """
    if registration and registration.ticket:
        ticket_tier = registration.ticket.tier
        if ticket_tier in (TicketTier.WAITING, TicketTier.STAFF, TicketTier.NPC):
            return 0

    reference_date = datetime.now().date()
    if registration and registration.created:
        reference_date = registration.created

    applicable_surcharges = RegistrationSurcharge.objects.filter(event=event, date__lt=reference_date)
    if not applicable_surcharges:
        return 0

    total_surcharge = 0
    for surcharge in applicable_surcharges:
        total_surcharge += surcharge.amount

    return total_surcharge


def handle_registration_accounting_updates(registration: Registration) -> None:
    """Handle post-save accounting updates for registrations.

    This function manages the transfer of payments from cancelled registrations,
    updates accounting calculations, and triggers status notifications when
    a registration moves from provisional to confirmed status.

    Args:
        registration: Registration instance that was saved. Must have valid
            run_id and member_id for payment transfers to work properly.

    Returns:
        None

    Note:
        This function performs database updates and may trigger background
        email notifications for status changes.
    """
    # Early return if no member associated with registration
    if not registration.member:
        return

    # Transfer payments from cancelled registrations to this active one
    if not registration.cancellation_date:
        # Find all cancelled registrations for same run and member
        cancelled = Registration.objects.filter(
            run_id=registration.run_id, member_id=registration.member_id, cancellation_date__isnull=False
        )
        cancelled = list(cancelled.values_list("pk", flat=True))

        # Transfer both payments and transactions from cancelled registrations
        if cancelled:
            for typ in [AccountingItemPayment, AccountingItemTransaction]:
                for el in typ.objects.filter(reg__id__in=cancelled):
                    el.reg = registration
                    el.save()

    # Store provisional status before accounting updates
    old_provisional = is_reg_provisional(registration)

    # Recalculate all accounting fields for this registration
    update_registration_accounting(registration)

    # Bulk update accounting fields without triggering model save signals
    updates = {}
    for field in ["tot_payed", "tot_iscr", "quota", "alert", "deadline", "payment_date"]:
        updates[field] = getattr(registration, field)
    Registration.objects.filter(pk=registration.pk).update(**updates)

    # Send confirmation email if registration status changed from provisional to confirmed
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


def check_reg_events(event):
    """Trigger background accounting updates for all registrations in an event.

    Args:
        event: Event instance to update registrations for

    Side effects:
        Queues background task to update accounting for all registrations
    """
    registration_ids = []
    for run in event.runs.all():
        for registration_id in run.registrations.values_list("id", flat=True):
            registration_ids.append(str(registration_id))
    check_registration_background(",".join(registration_ids))


@background_auto(queue="acc")
def check_registration_background(registration_ids: Union[int, str, Iterable[int]]) -> None:
    """
    Process one or more registration IDs by invoking `check_reg_bkg_go` for each.

    Args:
        registration_ids (Union[int, str, Iterable[int]]):
            - int: a single registration ID
            - str: a comma-separated list of registration IDs
            - Iterable[int]: a collection (e.g. list, tuple) of registration IDs

    Behavior:
        - If an int is provided, calls `check_reg_bkg_go` once.
        - If a string is provided, splits it by commas and processes each ID.
        - If an iterable is provided, iterates through and processes each ID.
    """
    if not registration_ids:
        return

    # Single integer case
    if isinstance(registration_ids, int):
        trigger_registration_accounting(registration_ids)
        return

    # Comma-separated string case
    if isinstance(registration_ids, str):
        for registration_id in registration_ids.split(","):
            trigger_registration_accounting(int(registration_id.strip()))
        return

    # Iterable of IDs case
    for registration_id in registration_ids:
        trigger_registration_accounting(registration_id)


def trigger_registration_accounting(registration_id):
    """Update accounting for a single registration in background task.

    Args:
        registration_id: Registration ID to update

    Side effects:
        Triggers registration save to update accounting if registration exists
    """
    if not registration_id:
        return
    try:
        registration = Registration.objects.get(pk=registration_id)
        registration.save()
    except ObjectDoesNotExist:
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
    alert = int(get_event_config(reg.run.event_id, "payment_alert", 30, bypass_cache=True))

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
