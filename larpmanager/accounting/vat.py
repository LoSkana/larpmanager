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

from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver

from larpmanager.cache.feature import get_assoc_features
from larpmanager.models.accounting import AccountingItemPayment, AccountingItemTransaction


@receiver(post_save, sender=AccountingItemPayment)
def post_save_AccountingItemPayment_vat(sender, instance, created, **kwargs):
    if "vat" not in get_assoc_features(instance.assoc_id):
        return

    # Get total previous payments and transactions for the same member and run
    previous_pays = get_previous_sum(instance, AccountingItemPayment)
    previous_trans = get_previous_sum(instance, AccountingItemTransaction)
    previous_paid = previous_pays - previous_trans

    # Get VAT configuration (e.g. 22 becomes 0.22)
    vat_ticket = int(instance.assoc.get_config("vat_ticket", 0)) / 100.0
    vat_options = int(instance.assoc.get_config("vat_options", 0)) / 100.0

    # Determine the full ticket amount (either from pay_what or ticket price)
    ticket_total = 0
    if instance.reg.pay_what is not None:
        ticket_total += instance.reg.pay_what
    if instance.reg.ticket:
        ticket_total += instance.reg.ticket.price

    # Check transaction for this payment
    paid = instance.value
    que = AccountingItemTransaction.objects.filter(inv=instance.inv)
    for trans in que:
        paid -= trans.value

    # Compute how much of the ticket is still unpaid
    remaining_ticket = max(0, ticket_total - previous_paid)

    # Split the current payment value between ticket and options
    quota_ticket = float(min(paid, remaining_ticket))
    quota_options = float(paid) - float(quota_ticket)

    # Compute VAT based on the split and respective rates
    vat = max(0.0, quota_ticket * vat_ticket + quota_options * vat_options)
    updates = {"vat": vat}
    AccountingItemPayment.objects.filter(pk=instance.pk).update(**updates)


def get_previous_sum(aip, typ):
    return (
        typ.objects.filter(reg__member=aip.reg.member, reg__run=aip.reg.run, created__lt=aip.created).aggregate(
            total=Sum("value")
        )["total"]
        or 0
    )
