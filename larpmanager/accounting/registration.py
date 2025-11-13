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

"""Registration accounting utilities for ticket pricing and payment calculation."""

from __future__ import annotations

import logging
import math
from decimal import Decimal
from typing import TYPE_CHECKING

from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

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
from larpmanager.models.event import DevelopStatus, Event, Run
from larpmanager.models.form import RegistrationChoice, RegistrationOption
from larpmanager.models.member import Member, MembershipStatus, get_user_membership
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationInstallment,
    RegistrationSurcharge,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.utils import get_sum
from larpmanager.utils.common import get_time_diff, get_time_diff_today
from larpmanager.utils.tasks import background_auto

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date

    from django.db.models import QuerySet

logger = logging.getLogger(__name__)


def get_reg_iscr(registration: Registration) -> int:
    """Calculate total registration signup fee including discounts.

    Computes the total registration fee by summing base ticket price, additional
    tickets, pay-what-you-want amounts, registration choices, and surcharges,
    then applying any applicable discounts (except for gifted registrations).

    Args:
        registration: Registration instance to calculate fee for. Must have attributes:
            ticket, additionals, pay_what, member_id, run_id, redeem_code, surcharge

    Returns:
        int: Total signup fee after applying discounts and surcharges, minimum 0

    Note:
        Discounts are not applied to registrations with redeem codes (gifted registrations).

    """
    # Initialize total registration fee
    total_registration_fee = 0

    # Add base ticket price and additional tickets
    if registration.ticket:
        total_registration_fee += registration.ticket.price

        if registration.additionals:
            total_registration_fee += registration.ticket.price * registration.additionals

    # Add pay-what-you-want amount
    if registration.pay_what:
        total_registration_fee += registration.pay_what

    # Add registration choice options (extras, meals, etc.)
    for choice in RegistrationChoice.objects.filter(reg=registration).select_related("option"):
        total_registration_fee += choice.option.price

    # Apply discounts only for non-gifted registrations
    if not registration.redeem_code:
        discount_items = AccountingItemDiscount.objects.filter(
            member_id=registration.member_id,
            run_id=registration.run_id,
        )
        for discount_item in discount_items.select_related("disc"):
            total_registration_fee -= discount_item.disc.value

    # Add any surcharges
    total_registration_fee += registration.surcharge

    # Ensure fee is never negative
    return max(0, total_registration_fee)


def get_reg_payments(
    registration: Registration, accounting_payments: QuerySet[AccountingItemPayment] | None = None
) -> int:
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


def get_reg_transactions(registration: Registration) -> int:
    """Calculate total transaction fees for a registration.

    Args:
        registration: Registration instance to calculate fees for

    Returns:
        int: Total transaction fees that are user burden

    """
    total_transaction_fees = 0

    accounting_transactions = AccountingItemTransaction.objects.filter(reg=registration, user_burden=True)

    for accounting_item_transaction in accounting_transactions:
        total_transaction_fees += accounting_item_transaction.value

    return total_transaction_fees


def get_accounting_refund(registration: Registration) -> None:
    """Get refund information for a registration.

    Args:
        registration: Registration instance to get refunds for

    Side effects:
        Sets registration.refunds dictionary with refund amounts by type

    """
    registration.refunds = {}

    if not hasattr(registration, "acc_refunds"):
        registration.acc_refunds = AccountingItemOther.objects.filter(
            run_id=registration.run_id,
            member_id=registration.member_id,
            cancellation=True,
        )

    if not registration.acc_refunds:
        return

    for accounting_item_other in registration.acc_refunds:
        if accounting_item_other.oth not in registration.refunds:
            registration.refunds[accounting_item_other.oth] = 0
        registration.refunds[accounting_item_other.oth] += accounting_item_other.value


def quota_check(reg: Registration, start: date, alert: int, association_id: int) -> None:
    """Check payment quotas and deadlines for a registration.

    Calculates payment quotas based on event start date and registration timing.
    Sets quota amount and deadline for next payment.

    Args:
        reg: Registration instance to check quotas for
        start: Event start date
        alert: Alert threshold in days
        association_id: Association ID for payment deadline calculation

    Side effects:
        Sets reg.quota, reg.deadline, and reg.qsr attributes

    """
    if not start:
        return

    # Validate quotas to prevent division by zero
    if reg.quotas == 0:
        logger.error("Registration %s has zero quotas, cannot calculate payment schedule", reg.pk)
        return

    reg.days_event = get_time_diff_today(start)
    reg.tot_days = get_time_diff(start, reg.created.date())

    quota_share = Decimal(1.0 / reg.quotas)
    quota_count = 0
    quota_share_ratio = 0
    first_deadline = True
    for _i in range(reg.quotas):
        quota_share_ratio += quota_share
        quota_count += 1

        # if first, deadline is immediately
        if quota_count == 1:
            deadline = get_payment_deadline(reg, 8, association_id)
        # else, deadline is computed in days to the event
        else:
            days_left = reg.tot_days * 1.0 * (reg.quotas - (quota_count - 1)) / reg.quotas
            deadline = math.floor(reg.days_event - days_left)

        if deadline >= alert:
            continue

        reg.qsr = quota_share_ratio

        # if last quota
        if quota_count == reg.quotas:
            reg.quota = reg.tot_iscr - reg.tot_payed
        else:
            reg.quota = reg.tot_iscr * quota_share_ratio - reg.tot_payed
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


def installment_check(reg: Registration, alert: int, association_id: int) -> None:
    """Check installment payment schedule for a registration.

    Processes configured installments for the event and determines
    next payment amount and deadline based on the installment schedule.
    Updates the registration's quota and deadline fields as side effects.

    Args:
        reg: Registration instance to check installments for
        alert: Alert threshold in days for deadline filtering
        association_id: Association ID used for payment deadline calculation

    Returns:
        None

    Side Effects:
        - Sets reg.quota to the amount due for the next installment
        - Sets reg.deadline to the deadline for the next payment

    """
    # Early return if registration has no ticket
    if not reg.ticket:
        return

    cumulative_amount = 0

    # Get all installments for this event, ordered by sequence
    installments_query = RegistrationInstallment.objects.filter(event_id=reg.run.event_id)
    installments_query = installments_query.annotate(tickets_map=ArrayAgg("tickets")).order_by("order")

    is_first_deadline = True

    # Process each installment in order
    for installment in installments_query:
        # Filter installments that apply to this ticket type
        applicable_ticket_ids = [ticket_id for ticket_id in installment.tickets_map if ticket_id is not None]
        if applicable_ticket_ids and reg.ticket_id not in applicable_ticket_ids:
            continue

        # Calculate deadline for this installment
        deadline_days = _get_deadline_installment(association_id, installment, reg)

        # Skip installments that are still within alert threshold
        if deadline_days and deadline_days >= alert:
            continue

        # Calculate cumulative amount due up to this installment
        if installment.amount:
            cumulative_amount += installment.amount
        else:
            cumulative_amount = reg.tot_iscr

        # Ensure total doesn't exceed registration total
        cumulative_amount = min(cumulative_amount, reg.tot_iscr)

        # Calculate outstanding amount for this installment
        reg.quota = max(cumulative_amount - reg.tot_payed, 0)

        logger.debug("Registration %s installment quota calculated: %s", reg.id, reg.quota)

        # Skip if nothing is due for this installment
        if reg.quota <= 0:
            continue

        # Set deadline for the first applicable installment
        if is_first_deadline and deadline_days:
            is_first_deadline = False
            reg.deadline = deadline_days

        # Skip to next installment if deadline has passed
        if not deadline_days or deadline_days < 0:
            continue

        return

    # Fallback: if no installments found, use registration date and full amount
    if not cumulative_amount:
        reg.deadline = get_time_diff_today(reg.created.date())
        reg.quota = reg.tot_iscr - reg.tot_payed


def _get_deadline_installment(
    association_id: int, installment: RegistrationInstallment, registration: Registration
) -> int | None:
    """Calculate deadline for a specific installment.

    Args:
        association_id: Association ID for payment deadline calculation
        installment: RegistrationInstallment instance
        registration: Registration instance

    Returns:
        int or None: Days until deadline, None if no deadline configured

    """
    if installment.days_deadline:
        deadline = get_payment_deadline(registration, installment.days_deadline, association_id)
    elif installment.date_deadline:
        deadline = get_time_diff_today(installment.date_deadline)
    else:
        deadline = None
    return deadline


def get_payment_deadline(registration: Registration, days_to_add: int, association_id: int) -> int:
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


def registration_payments_status(registration: Registration) -> None:
    """Determine registration payment status and balance.

    Args:
        registration: Registration instance to check status for

    Returns:
        tuple: (is_paid, balance) where is_paid is boolean and balance is amount owed

    """
    registration.payment_status = ""
    if registration.tot_iscr > 0:
        if registration.tot_payed == registration.tot_iscr:
            registration.payment_status = "c"
        elif registration.tot_payed == 0:
            registration.payment_status = "n"
        elif registration.tot_payed < registration.tot_iscr:
            registration.payment_status = "p"
        else:
            registration.payment_status = "t"


def cancel_run(instance: Run) -> None:
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
            member_id=r.member_id,
            pay=PaymentChoices.TOKEN,
            reg__run=instance,
        ).delete()
        AccountingItemPayment.objects.filter(
            member_id=r.member_id,
            pay=PaymentChoices.CREDIT,
            reg__run=instance,
        ).delete()
        money = get_sum(
            AccountingItemPayment.objects.filter(member_id=r.member_id, pay=PaymentChoices.MONEY, reg__run=instance),
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


def cancel_reg(registration: Registration) -> None:
    """Cancel a specific registration and clean up related data.

    Args:
        registration: Registration instance to cancel

    Side effects:
        Sets cancellation date, deletes characters, traits, discounts,
        bonus items, and resets event links

    """
    registration.cancellation_date = timezone.now()
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
    reset_event_links(registration.member_id, registration.run.event.association_id)


def get_display_choice(choices: list[tuple[str, str]], key: str) -> str:
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


def round_to_nearest_cent(amount: float) -> float:
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


def process_registration_pre_save(registration: Registration) -> None:
    """Process registration before saving.

    Args:
        registration: Registration instance being saved

    """
    registration.surcharge = get_date_surcharge(registration, registration.run.event)
    registration.member.join(registration.run.event.association)


def get_date_surcharge(registration: Registration | None, event: Event) -> int:
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

    reference_date = timezone.now().date()
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
        cancelled_registrations = Registration.objects.filter(
            run_id=registration.run_id,
            member_id=registration.member_id,
            cancellation_date__isnull=False,
        )
        cancelled_registration_ids = list(cancelled_registrations.values_list("pk", flat=True))

        # Transfer both payments and transactions from cancelled registrations
        if cancelled_registration_ids:
            for accounting_item_type in [AccountingItemPayment, AccountingItemTransaction]:
                for accounting_item in accounting_item_type.objects.filter(reg__id__in=cancelled_registration_ids):
                    accounting_item.reg = registration
                    accounting_item.save()

    # Store provisional status before accounting updates
    was_provisional_before_update = is_reg_provisional(registration)

    # Recalculate all accounting fields for this registration
    update_registration_accounting(registration)

    # Bulk update accounting fields without triggering model save signals
    updated_fields = {}
    for field_name in ["tot_payed", "tot_iscr", "quota", "alert", "deadline", "payment_date"]:
        updated_fields[field_name] = getattr(registration, field_name)
    Registration.objects.filter(pk=registration.pk).update(**updated_fields)

    # Send confirmation email if registration status changed from provisional to confirmed
    if was_provisional_before_update and not is_reg_provisional(registration):
        update_registration_status_bkg(registration.id)


def process_accounting_discount_post_save(discount_item: AccountingItemDiscount) -> None:
    """Process accounting discount item after save.

    Args:
        discount_item: AccountingItemDiscount instance that was saved

    """
    if discount_item.run and not discount_item.expires:
        for reg in Registration.objects.filter(member_id=discount_item.member_id, run_id=discount_item.run_id):
            reg.save()


def log_registration_ticket_saved(ticket: RegistrationTicket) -> None:
    """Process registration ticket after save.

    Args:
        ticket: RegistrationTicket instance that was saved

    """
    logger.debug("RegistrationTicket saved: %s at %s", ticket, timezone.now())
    check_reg_events(ticket.event)


def process_registration_option_post_save(option: RegistrationOption) -> None:
    """Process registration option after save.

    Args:
        option: RegistrationOption instance that was saved

    """
    logger.debug("RegistrationOption saved: %s at %s", option, timezone.now())
    check_reg_events(option.question.event)


def check_reg_events(event: Event) -> None:
    """Trigger background accounting updates for all registrations in an event.

    Args:
        event: Event instance to update registrations for

    Side effects:
        Queues background task to update accounting for all registrations

    """
    registration_ids: list[str] = []
    for run in event.runs.all():
        for registration_id in run.registrations.values_list("id", flat=True):
            registration_ids.append(str(registration_id))
    check_registration_background(",".join(registration_ids))


@background_auto(queue="acc")
def check_registration_background(registration_ids: int | str | Iterable[int]) -> None:
    """Process one or more registration IDs by invoking `check_reg_bkg_go` for each.

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


def trigger_registration_accounting(registration_id: int | None) -> None:
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
    for cancelled_or_done_status in [DevelopStatus.CANC, DevelopStatus.DONE]:
        if reg.run.development == cancelled_or_done_status:
            return

    max_rounding_tolerance = 0.05

    # Extract basic event information
    event_start_date = reg.run.start
    event_features = get_event_features(reg.run.event_id)
    association_id = reg.run.event.association_id

    # Calculate total inscription fee and payments
    reg.tot_iscr = get_reg_iscr(reg)
    total_transactions = get_reg_transactions(reg)
    reg.tot_payed = get_reg_payments(reg)

    # Adjust for transactions and round to nearest cent
    reg.tot_payed -= total_transactions
    reg.tot_payed = Decimal(round_to_nearest_cent(reg.tot_payed))

    # Initialize payment tracking fields
    reg.quota = 0
    reg.deadline = 0
    reg.alert = False

    # Check if payment is complete (within rounding tolerance)
    remaining_balance = reg.tot_iscr - reg.tot_payed
    if -max_rounding_tolerance < remaining_balance <= max_rounding_tolerance:
        if not reg.payment_date:
            reg.payment_date = timezone.now()
        return

    # Skip further processing if registration is cancelled
    if reg.cancellation_date:
        return

    # Handle membership requirements for non-LAOG events
    if "membership" in event_features and "laog" not in event_features:
        if not hasattr(reg, "membership"):
            reg.membership = get_user_membership(reg.member, association_id)
        if reg.membership.status != MembershipStatus.ACCEPTED:
            return

    # Process tokens and credits
    handle_tokes_credits(association_id, event_features, reg, remaining_balance)

    # Get payment alert threshold from event configuration
    alert_days_threshold = int(get_event_config(reg.run.event_id, "payment_alert", default_value=30, bypass_cache=True))

    # Calculate payment schedule based on feature flags
    if "reg_installments" in event_features:
        installment_check(reg, alert_days_threshold, association_id)
    else:
        quota_check(reg, event_start_date, alert_days_threshold, association_id)

    # Skip alert setting if quota is negligible
    if reg.quota <= max_rounding_tolerance:
        return

    # Set alert flag based on deadline proximity
    reg.alert = reg.deadline < alert_days_threshold


def update_member_registrations(member: Member) -> None:
    """Trigger accounting updates for all registrations of a member.

    Args:
        member: Member instance to update registrations for

    Side effects:
        Saves all registrations to trigger accounting recalculation

    """
    for registration in Registration.objects.filter(member=member):
        registration.save()
