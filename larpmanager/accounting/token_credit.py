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

from django.db.models import F
from django.db.models.functions import Abs
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from larpmanager.cache.feature import get_assoc_features
from larpmanager.models.accounting import AccountingItemExpense, AccountingItemOther, AccountingItemPayment
from larpmanager.models.event import Run
from larpmanager.models.member import get_user_membership
from larpmanager.models.registration import Registration
from larpmanager.models.utils import get_sum


def registration_tokens_credits(reg, remaining, features, assoc_id):
    if "token_credit" not in features:
        return

    if reg.run.event.get_config("token_credit_disable_t", False):
        return

    # check token credits
    member = reg.member
    membership = get_user_membership(member, assoc_id)
    if membership.tokens > 0:
        tk_use = min(remaining, membership.tokens)
        reg.tot_payed += tk_use
        membership.tokens -= tk_use
        membership.save()
        AccountingItemPayment.objects.create(
            pay=AccountingItemPayment.TOKEN,
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
            pay=AccountingItemPayment.CREDIT,
            value=cr_use,
            member=reg.member,
            reg=reg,
            assoc_id=assoc_id,
        )


def get_runs_paying_incomplete():
    reg_que = Registration.objects.filter(cancellation_date__isnull=True)
    reg_que = reg_que.exclude(run__development__in=[Run.CANC, Run.DONE])
    reg_que = reg_que.annotate(diff=Abs(F("tot_payed") - F("tot_iscr"))).exclude(diff__lt=0.05)
    return reg_que


@receiver(post_save, sender=AccountingItemPayment)
def post_save_AccountingItemPayment(sender, instance, created, **kwargs):
    if not created and instance.reg:
        update_token_credit(instance, instance.pay == AccountingItemPayment.TOKEN)


@receiver(post_delete, sender=AccountingItemPayment)
def post_delete_AccountingItemPayment(sender, instance, **kwargs):
    if instance.reg:
        update_token_credit(instance, instance.pay == AccountingItemPayment.TOKEN)


@receiver(post_save, sender=AccountingItemOther)
def post_save_AccountingItemOther_accounting(sender, instance, **kwargs):
    if not instance.member:
        return

    update_token_credit(instance, instance.oth == AccountingItemOther.TOKEN)


@receiver(post_save, sender=AccountingItemExpense)
def post_save_AccountingItemExpense_accounting(sender, instance, **kwargs):
    if not instance.member or not instance.is_approved:
        return

    update_token_credit(instance, False)


def update_token_credit(instance, token=True):
    assoc_id = instance.assoc_id

    # skip if not active
    if "token_credit" not in get_assoc_features(assoc_id):
        return

    membership = get_user_membership(instance.member, assoc_id)

    # token case
    if token:
        tk_given = AccountingItemOther.objects.filter(
            member=instance.member, oth=AccountingItemOther.TOKEN, assoc_id=assoc_id
        )
        tk_used = AccountingItemPayment.objects.filter(
            member=instance.member, pay=AccountingItemPayment.TOKEN, assoc_id=assoc_id
        )
        membership.tokens = get_sum(tk_given) - get_sum(tk_used)
        membership.save()

    # credit or refund case
    else:
        cr_expenses = AccountingItemExpense.objects.filter(member=instance.member, is_approved=True, assoc_id=assoc_id)
        cr_given = AccountingItemOther.objects.filter(
            member=instance.member, oth=AccountingItemOther.CREDIT, assoc_id=assoc_id
        )
        cr_used = AccountingItemPayment.objects.filter(
            member=instance.member, pay=AccountingItemPayment.CREDIT, assoc_id=assoc_id
        )
        cr_refunded = AccountingItemOther.objects.filter(
            member=instance.member, oth=AccountingItemOther.REFUND, assoc_id=assoc_id
        )
        membership.credit = get_sum(cr_expenses) + get_sum(cr_given) - (get_sum(cr_used) + get_sum(cr_refunded))
        membership.save()

    # trigger accounting update on registrations with missing remaining
    available = membership.credit + membership.tokens
    for reg in get_runs_paying_incomplete().filter(member=instance.member):
        remaining = reg.tot_iscr - reg.tot_payed
        reg.save()
        available -= remaining
        if available < 0:
            break
