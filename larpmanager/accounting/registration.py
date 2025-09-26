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

from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

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
from larpmanager.models.event import DevelopStatus
from larpmanager.models.form import RegistrationChoice, RegistrationOption
from larpmanager.models.member import MembershipStatus, get_user_membership
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

logger = logging.getLogger(__name__)


def get_reg_iscr(instance):
    """Calculate total registration signup fee including discounts.

    Args:
        instance: Registration instance to calculate fee for

    Returns:
        int: Total signup fee after applying discounts and surcharges
    """
    # update registration totatal signup fee
    tot_iscr = 0

    if instance.ticket:
        tot_iscr += instance.ticket.price

    if instance.additionals:
        tot_iscr += instance.ticket.price * instance.additionals

    if instance.pay_what:
        tot_iscr += instance.pay_what

    for c in RegistrationChoice.objects.filter(reg=instance).select_related("option"):
        tot_iscr += c.option.price

    # no discount for gifted
    if not instance.redeem_code:
        que = AccountingItemDiscount.objects.filter(member=instance.member, run=instance.run)
        for el in que.select_related("disc"):
            tot_iscr -= el.disc.value

    tot_iscr += instance.surcharge

    tot_iscr = max(0, tot_iscr)

    return tot_iscr


def get_reg_payments(reg, acc_payments=None):
    """Calculate total payments made for a registration.

    Args:
        reg: Registration instance
        acc_payments: Optional queryset of payments, will query if None

    Returns:
        int: Total amount paid

    Side effects:
        Sets reg.payments dictionary with payment breakdown
    """
    if acc_payments is None:
        acc_payments = AccountingItemPayment.objects.filter(
            reg=reg,
        ).exclude(hide=True)

    tot_payed = 0
    reg.payments = {}

    for aip in acc_payments:
        if aip.pay not in reg.payments:
            reg.payments[aip.pay] = 0
        reg.payments[aip.pay] += aip.value
        tot_payed += aip.value

    return tot_payed


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
        reg.acc_refunds = AccountingItemOther.objects.filter(run_id=reg.run_id, member=reg.member, cancellation=True)

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


def installment_check(reg, alert, assoc_id):
    """Check installment payment schedule for a registration.

    Processes configured installments for the event and determines
    next payment amount and deadline.

    Args:
        reg: Registration instance to check installments for
        alert: Alert threshold in days
        assoc_id: Association ID for payment deadline calculation

    Side effects:
        Sets reg.quota and reg.deadline based on installment schedule
    """
    if not reg.ticket:
        return

    tot = 0

    que = RegistrationInstallment.objects.filter(event=reg.run.event)
    que = que.annotate(tickets_map=ArrayAgg("tickets")).order_by("order")

    first_deadline = True

    # for all installments
    for i in que:
        tickets_id = [i for i in i.tickets_map if i is not None]
        if tickets_id and reg.ticket_id not in tickets_id:
            continue

        deadline = _get_deadline_installment(assoc_id, i, reg)

        if deadline and deadline >= alert:
            continue

        if i.amount:
            tot += i.amount
        else:
            tot = reg.tot_iscr

        tot = min(tot, reg.tot_iscr)

        reg.quota = max(tot - reg.tot_payed, 0)

        logger.debug(f"Registration {reg.id} installment quota calculated: {reg.quota}")

        if reg.quota <= 0:
            continue

        if first_deadline and deadline:
            first_deadline = False
            reg.deadline = deadline

        # go to next installment if deadline was missed
        if not deadline or deadline < 0:
            continue

        return

    # If not installment is found
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


def get_payment_deadline(reg, i, assoc_id):
    """Calculate payment deadline based on registration and membership dates.

    Args:
        reg: Registration instance
        i: Number of days to add to base date
        assoc_id: Association ID for membership lookup

    Returns:
        int: Days until payment deadline
    """
    dd = get_time_diff_today(reg.created.date())
    if not hasattr(reg, "membership"):
        reg.membership = get_user_membership(reg.member, assoc_id)
    if reg.membership.date:
        dd = max(dd, get_time_diff_today(reg.membership.date))
    return dd + i


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
        AccountingItemPayment.objects.filter(member=r.member, pay=PaymentChoices.TOKEN, reg__run=instance).delete()
        AccountingItemPayment.objects.filter(member=r.member, pay=PaymentChoices.CREDIT, reg__run=instance).delete()
        money = get_sum(
            AccountingItemPayment.objects.filter(member=r.member, pay=PaymentChoices.MONEY, reg__run=instance)
        )
        if money > 0:
            AccountingItemOther.objects.create(
                member=r.member,
                oth=OtherChoices.CREDIT,
                descr=f"Refund per {instance}",
                run=instance,
                value=money,
            )
        r.refunded = True
        r.save()


def cancel_reg(reg):
    """Cancel a specific registration and clean up related data.

    Args:
        reg: Registration instance to cancel

    Side effects:
        Sets cancellation date, deletes characters, traits, discounts,
        bonus items, and resets event links
    """
    reg.cancellation_date = datetime.now()
    reg.save()

    # delete characters related
    RegistrationCharacterRel.objects.filter(reg=reg).delete()

    # delete trait assignments
    AssignmentTrait.objects.filter(run=reg.run, member=reg.member).delete()

    # delete discounts
    AccountingItemDiscount.objects.filter(run=reg.run, member=reg.member).delete()

    # delete bonus credits / tokens
    AccountingItemOther.objects.filter(ref_addit=reg.id).delete()

    # Reset event links
    reset_event_links(reg.member.id, reg.run.event.assoc_id)


def get_display_choice(choices, k):
    """Get display name for a choice field value.

    Args:
        choices: List of (key, display_name) tuples
        k: Key to look up display name for

    Returns:
        str: Display name for the key, empty string if not found
    """
    for key, d in choices:
        if key == k:
            return d
    return ""


def round_to_nearest_cent(number):
    """Round a number to the nearest cent with tolerance for small differences.

    Args:
        number: Number to round

    Returns:
        float: Rounded number, original if difference exceeds tolerance
    """
    rounded = round(number * 10) / 10
    max_rounding = 0.03
    if abs(float(number) - rounded) <= max_rounding:
        return rounded
    return float(number)


@receiver(pre_save, sender=Registration)
def pre_save_registration(sender, instance, *args, **kwargs):
    instance.surcharge = get_date_surcharge(instance, instance.run.event)
    instance.member.join(instance.run.event.assoc)


def get_date_surcharge(reg, event):
    """Calculate date-based surcharge for a registration.

    Args:
        reg: Registration instance (None for current date)
        event: Event instance to get surcharges for

    Returns:
        int: Total surcharge amount based on registration date
    """
    if reg and reg.ticket:
        t = reg.ticket.tier
        if t in (TicketTier.WAITING, TicketTier.STAFF, TicketTier.NPC):
            return 0

    dt = datetime.now().date()
    if reg and reg.created:
        dt = reg.created

    surs = RegistrationSurcharge.objects.filter(event=event, date__lt=dt)
    if not surs:
        return 0

    tot = 0
    for s in surs:
        tot += s.amount

    return tot


@receiver(post_save, sender=Registration)
def post_save_registration_accounting(sender, instance, **kwargs):
    """
    Handle post-save accounting updates for registrations.

    Args:
        sender: Model class that sent the signal
        instance: Registration instance that was saved
        **kwargs: Additional signal arguments
    """
    if not instance.member:
        return

    # find cancelled registrations to transfer payments
    if not instance.cancellation_date:
        cancelled = Registration.objects.filter(
            run=instance.run, member=instance.member, cancellation_date__isnull=False
        )
        cancelled = list(cancelled.values_list("pk", flat=True))
        if cancelled:
            for typ in [AccountingItemPayment, AccountingItemTransaction]:
                for el in typ.objects.filter(reg__id__in=cancelled):
                    el.reg = instance
                    el.save()

    old_provisional = is_reg_provisional(instance)

    # update accounting
    update_registration_accounting(instance)

    # update accounting without triggering a new save
    updates = {}
    for field in ["tot_payed", "tot_iscr", "quota", "alert", "deadline", "payment_date"]:
        updates[field] = getattr(instance, field)
    Registration.objects.filter(pk=instance.pk).update(**updates)

    # send mail if not provisional anymore
    if old_provisional and not is_reg_provisional(instance):
        update_registration_status_bkg(instance.id)


@receiver(post_save, sender=AccountingItemDiscount)
def post_save_accounting_item_discount_accounting(sender, instance, **kwargs):
    if instance.run and not instance.expires:
        for reg in Registration.objects.filter(member=instance.member, run=instance.run):
            reg.save()


@receiver(post_save, sender=RegistrationTicket)
def post_save_registration_ticket(sender, instance, created, **kwargs):
    logger.debug(f"RegistrationTicket saved: {instance} at {datetime.now()}")
    check_reg_events(instance.event)


@receiver(post_save, sender=RegistrationOption)
def post_save_registration_option(sender, instance, created, **kwargs):
    logger.debug(f"RegistrationOption saved: {instance} at {datetime.now()}")
    check_reg_events(instance.question.event)


def check_reg_events(event):
    """Trigger background accounting updates for all registrations in an event.

    Args:
        event: Event instance to update registrations for

    Side effects:
        Queues background task to update accounting for all registrations
    """
    regs = []
    for run in event.runs.all():
        for reg_id in run.registrations.values_list("id", flat=True):
            regs.append(str(reg_id))
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


def check_reg_bkg_go(reg_id):
    """Update accounting for a single registration in background task.

    Args:
        reg_id: Registration ID to update

    Side effects:
        Triggers registration save to update accounting if registration exists
    """
    if not reg_id:
        return
    try:
        instance = Registration.objects.get(pk=reg_id)
        instance.save()
    except ObjectDoesNotExist:
        return


def update_registration_accounting(reg):
    """Update comprehensive accounting information for a registration.

    Calculates total signup fee, payments received, outstanding balance,
    payment quotas, and deadlines based on event configuration.

    Args:
        reg: Registration instance to update accounting for

    Side effects:
        Updates reg.tot_iscr, reg.tot_payed, reg.quota, reg.deadline, reg.alert
    """
    for s in [DevelopStatus.CANC, DevelopStatus.DONE]:
        if reg.run.development == s:
            return

    max_rounding = 0.05

    start = reg.run.start
    features = get_event_features(reg.run.event_id)
    assoc_id = reg.run.event.assoc_id

    # get registration account item
    reg.tot_iscr = get_reg_iscr(reg)
    # get all transaction
    tot_trans = get_reg_transactions(reg)
    # get  all payments
    reg.tot_payed = get_reg_payments(reg)
    reg.tot_payed -= tot_trans
    reg.tot_payed = Decimal(round_to_nearest_cent(reg.tot_payed))

    reg.quota = 0
    reg.deadline = 0
    reg.alert = False

    remaining = reg.tot_iscr - reg.tot_payed
    if -max_rounding < remaining <= max_rounding:
        if not reg.payment_date:
            reg.payment_date = datetime.now()
        return

    if reg.cancellation_date:
        return

    if "membership" in features and "laog" not in features:
        if not hasattr(reg, "membership"):
            reg.membership = get_user_membership(reg.member, assoc_id)
        if reg.membership.status != MembershipStatus.ACCEPTED:
            return

    handle_tokes_credits(assoc_id, features, reg, remaining)

    alert = int(reg.run.event.get_config("payment_alert", 30))

    if "reg_installments" in features:
        installment_check(reg, alert, assoc_id)
    else:
        quota_check(reg, start, alert, assoc_id)

    if reg.quota <= max_rounding:
        return

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
