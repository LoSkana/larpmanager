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

import csv
import math
from io import StringIO

from django.core.exceptions import ObjectDoesNotExist

from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.utils.common import clean, detect_delimiter
from larpmanager.utils.tasks import notify_admins


def invoice_verify(request, ctx, csv_upload):
    content = csv_upload.read().decode("utf-8")
    delim = detect_delimiter(content)
    csv_data = csv.reader(StringIO(content), delimiter=delim)

    counter = 0

    for row in csv_data:
        causal = row[1]
        amount = row[0].replace(".", "").replace(",", ".")

        if not causal:
            continue

        if not amount:
            continue

        # check in all todos
        for el in ctx["todo"]:
            if el.verified:
                continue

            found = clean(el.causal) in clean(causal)
            code = el.causal.split()[0]

            random_causal_length = 16

            if not found and len(code) == random_causal_length:
                found = code in clean(causal)

            if not found and el.reg_cod:
                found = clean(el.reg_cod) in clean(causal)

            if not found and el.txn_id:
                found = clean(el.txn_id) in clean(causal)

            if not found:
                continue

            a_dist = math.ceil(float(amount)) - math.ceil(float(el.mc_gross))
            if a_dist > 0:
                continue

            counter += 1

            el.verified = True
            el.save()

    return counter


def invoice_received_money(cod, gross=None, fee=None, txn_id=None):
    try:
        invoice = PaymentInvoice.objects.get(cod=cod)
    except ObjectDoesNotExist:
        notify_admins("invalid payment", "wrong invoice: " + cod)
        return

    if gross:
        invoice.mc_gross = gross

    if fee:
        invoice.mc_fee = fee

    if txn_id:
        invoice.txn_id = txn_id

    if invoice.status in (PaymentStatus.CHECKED, PaymentStatus.CONFIRMED):
        return True

    # ~ invoice.mc_gross = ipn_obj.mc_gross
    # ~ invoice.mc_fee = ipn_obj.mc_fee
    # ~ invoice.txn_id = ipn_obj.txn_id
    invoice.status = PaymentStatus.CHECKED
    invoice.save()

    # print(invoice)

    return True
