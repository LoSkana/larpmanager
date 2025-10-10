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
from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Value, When

from larpmanager.cache.feature import get_assoc_features
from larpmanager.models.accounting import (
    AccountingItemExpense,
    AccountingItemOther,
    AccountingItemPayment,
    OtherChoices,
    PaymentChoices,
)
from larpmanager.models.event import DevelopStatus
from larpmanager.models.member import get_user_membership
from larpmanager.models.registration import Registration
from larpmanager.models.utils import get_sum


def registration_tokens_credits_use(reg, remaining, assoc_id):
    """Apply available tokens and credits to a registration payment.

    Automatically uses member's available tokens first, then credits
    to pay for outstanding registration balance.

    Args:
        reg: Registration instance to apply payments to
        remaining: Outstanding balance amount
        features: Event features dictionary
        assoc_id: Association ID for membership lookup

    Side effects:
        Creates AccountingItemPayment records and updates membership balances
        Updates reg.tot_payed with applied amounts
    """
    if remaining < 0:
        return

    with transaction.atomic():
        # check token credits
        member = reg.member
        membership = get_user_membership(member, assoc_id)
        if membership.tokens > 0:
            tk_use = min(remaining, membership.tokens)
            reg.tot_payed += tk_use
            membership.tokens -= tk_use
            membership.save()
            AccountingItemPayment.objects.create(
                pay=PaymentChoices.TOKEN,
                value=tk_use,
                member=reg.member,
                reg=reg,
                assoc_id=assoc_id,
            )
            remaining -= tk_use

        if membership.credit > 0:
            cr_use = min(remaining, membership.credit)
            reg.tot_payed += cr_use
            membership.credit -= cr_use
            membership.save()
            AccountingItemPayment.objects.create(
                pay=PaymentChoices.CREDIT,
                value=cr_use,
                member=reg.member,
                reg=reg,
                assoc_id=assoc_id,
            )


def registration_tokens_credits_overpay(reg, overpay, assoc_id):
    """
    Offsets an overpayment by reducing or deleting `AccountingItemPayment`
    rows with pay=TOKEN or CREDIT.

    Rows are locked (SELECT FOR UPDATE) and ordered by:
    CREDIT first, then TOKEN, then by value (desc) and id (desc).
    Each row is reduced until the overpayment is covered, deleting the row
    if its value reaches zero. Executed inside a single atomic transaction.

    Args:
        reg : Registration to adjust.
        overpay : Positive amount to reverse.
        assoc_id : Association id used to filter payments
    """

    if overpay <= 0:
        return

    with transaction.atomic():
        qs = (
            AccountingItemPayment.objects.select_for_update()
            .filter(reg=reg, assoc_id=assoc_id, pay__in=[PaymentChoices.TOKEN, PaymentChoices.CREDIT])
            .annotate(
                pay_priority=Case(
                    When(pay=PaymentChoices.CREDIT, then=Value(0)),
                    When(pay=PaymentChoices.TOKEN, then=Value(1)),
                    output_field=IntegerField(),
                )
            )
            .order_by("pay_priority", "-value", "-id")
        )

        reversed_total = 0
        remaining = overpay

        for item in qs:
            if remaining <= 0:
                break
            cut = min(remaining, item.value)
            new_val = item.value - cut

            if new_val <= 0:
                item.delete()
            else:
                item.value = new_val
                item.save(update_fields=["value"])

            reversed_total += cut
            remaining -= cut


def get_regs_paying_incomplete(assoc=None):
    """Get registrations with incomplete payments (excluding small differences).

    Args:
        assoc: Optional association to filter by

    Returns:
        QuerySet: Registrations with payment differences > 0.05
    """
    reg_que = get_regs(assoc)
    reg_que = reg_que.annotate(diff=F("tot_payed") - F("tot_iscr"))
    reg_que = reg_que.filter(Q(diff__lte=-0.05) | Q(diff__gte=0.05))
    return reg_que


def get_regs(assoc):
    """Get active registrations (not cancelled, not from completed events).

    Args:
        assoc: Optional association to filter by

    Returns:
        QuerySet: Active registrations
    """
    reg_que = Registration.objects.filter(cancellation_date__isnull=True)
    reg_que = reg_que.exclude(run__development__in=[DevelopStatus.CANC, DevelopStatus.DONE])
    if assoc:
        reg_que = reg_que.filter(run__event__assoc=assoc)
    return reg_que


def update_token_credit_on_payment_save(instance, created):
    """Handle accounting item payment post-save token/credit updates.

    Args:
        instance: AccountingItemPayment instance that was saved
        created: Boolean indicating if instance was created
    """
    if not created and instance.reg:
        update_token_credit(instance, instance.pay == PaymentChoices.TOKEN)


def update_token_credit_on_payment_delete(instance):
    """Handle accounting item payment post-delete token/credit updates.

    Args:
        instance: AccountingItemPayment instance that was deleted
    """
    if instance.reg:
        update_token_credit(instance, instance.pay == PaymentChoices.TOKEN)


def update_token_credit_on_other_save(accounting_item):
    """Handle accounting item other save for token/credit updates.

    Args:
        accounting_item: AccountingItemOther instance that was saved
    """
    if not accounting_item.member:
        return

    update_token_credit(accounting_item, accounting_item.oth == OtherChoices.TOKEN)


def update_credit_on_expense_save(expense_item):
    """Handle accounting item expense save for credit updates.

    Args:
        expense_item: AccountingItemExpense instance that was saved
    """
    if not expense_item.member or not expense_item.is_approved:
        return

    update_token_credit(expense_item, False)


def update_token_credit(instance, token=True):
    """Update member's token or credit balance based on accounting items.

    Recalculates and updates membership token or credit balance by summing
    all relevant accounting items (given, used, expenses, refunds).

    Args:
        instance: Accounting item instance that triggered the update
        token: If True, update tokens; if False, update credits

    Side effects:
        Updates membership.tokens or membership.credit
        Triggers accounting updates on affected registrations
    """
    assoc_id = instance.assoc_id

    # skip if not active
    if "token_credit" not in get_assoc_features(assoc_id):
        return

    membership = get_user_membership(instance.member, assoc_id)

    # token case
    if token:
        tk_given = AccountingItemOther.objects.filter(member=instance.member, oth=OtherChoices.TOKEN, assoc_id=assoc_id)
        tk_used = AccountingItemPayment.objects.filter(
            member=instance.member, pay=PaymentChoices.TOKEN, assoc_id=assoc_id
        )
        membership.tokens = get_sum(tk_given) - get_sum(tk_used)
        membership.save()

    # credit or refund case
    else:
        cr_expenses = AccountingItemExpense.objects.filter(member=instance.member, is_approved=True, assoc_id=assoc_id)
        cr_given = AccountingItemOther.objects.filter(
            member=instance.member, oth=OtherChoices.CREDIT, assoc_id=assoc_id
        )
        cr_used = AccountingItemPayment.objects.filter(
            member=instance.member, pay=PaymentChoices.CREDIT, assoc_id=assoc_id
        )
        cr_refunded = AccountingItemOther.objects.filter(
            member=instance.member, oth=OtherChoices.REFUND, assoc_id=assoc_id
        )
        membership.credit = get_sum(cr_expenses) + get_sum(cr_given) - (get_sum(cr_used) + get_sum(cr_refunded))
        membership.save()

    # trigger accounting update on registrations with missing remaining
    for reg in get_regs_paying_incomplete(instance.assoc).filter(member=instance.member):
        reg.save()


def handle_tokes_credits(assoc_id, features, reg, remaining):
    if "token_credit" not in features or reg.run.event.get_config("token_credit_disable_t", False):
        return

    if remaining > 0:
        registration_tokens_credits_use(reg, remaining, assoc_id)
    else:
        registration_tokens_credits_overpay(reg, -remaining, assoc_id)
