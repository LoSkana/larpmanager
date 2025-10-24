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
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import transaction

from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.utils.common import clean, detect_delimiter
from larpmanager.utils.tasks import notify_admins


def invoice_verify(ctx: dict, csv_upload: InMemoryUploadedFile) -> int:
    """Verify and match payments from CSV upload against pending invoices.

    Processes a CSV file containing payment data and matches entries against
    pending payment invoices using causal codes, registration codes, or transaction IDs.
    Marks matching invoices as verified when payment amounts are sufficient.

    Args:
        ctx (dict): Context dictionary containing 'todo' key with list of pending invoices
        csv_upload (InMemoryUploadedFile): Uploaded CSV file containing payment data with
            format [amount, causal, ...] where amount uses dot for thousands
            and comma for decimal separator

    Returns:
        int: Number of successfully verified payments

    Note:
        CSV format expected: [amount, causal, ...] where amount uses dot for thousands
        and comma for decimal separator. Only processes unverified invoices where
        payment amount meets or exceeds invoice amount.
    """
    # Decode CSV content and detect delimiter
    content: str = csv_upload.read().decode("utf-8")
    delim: str = detect_delimiter(content)
    csv_data = csv.reader(StringIO(content), delimiter=delim)

    counter: int = 0

    # Process each row in the CSV file
    for row in csv_data:
        causal: str = row[1]
        amount_str: str = row[0].replace(".", "").replace(",", ".")

        # Skip rows with missing causal or amount data
        if not causal or not amount_str:
            continue

        # Check payment against all pending invoices
        for el in ctx["todo"]:
            # Skip already verified invoices
            if el.verified:
                continue

            # Try to match causal code directly
            found: bool = clean(el.causal) in clean(causal)
            code: str = el.causal.split()[0]

            # Check for random causal codes (16 characters)
            random_causal_length: int = 16
            if not found and len(code) == random_causal_length:
                found = code in clean(causal)

            # Try matching registration code if available
            if not found and el.reg_cod:
                found = clean(el.reg_cod) in clean(causal)

            # Try matching transaction ID if available
            if not found and el.txn_id:
                found = clean(el.txn_id) in clean(causal)

            # Skip if no match found
            if not found:
                continue

            # Verify payment amount is sufficient (rounded up)
            amount_diff: float = math.ceil(float(amount_str)) - math.ceil(float(el.mc_gross))
            if amount_diff > 0:
                continue

            # Mark invoice as verified and increment counter
            counter += 1
            with transaction.atomic():
                el.verified = True
                el.save()

    return counter


def invoice_received_money(
    invoice_code: str, gross_amount: float = None, processing_fee: float = None, transaction_id: str = None
) -> bool:
    """Process received payment for a payment invoice.

    Updates payment invoice status and financial details when money is received
    from payment processors like PayPal or bank transfers.

    Args:
        invoice_code: Invoice code to identify the payment
        gross_amount: Optional gross amount received from payment processor
        processing_fee: Optional processing fee charged by payment processor
        transaction_id: Optional transaction ID from payment processor

    Returns:
        True if payment was processed successfully, None if invalid invoice code

    Raises:
        No exceptions are raised - invalid invoices are handled gracefully
        with admin notifications.

    Side Effects:
        - Updates invoice status to CHECKED
        - Saves financial details (gross amount, fees, transaction ID)
        - Sends admin notification for invalid payment codes
    """
    # Attempt to retrieve the payment invoice by code
    try:
        invoice = PaymentInvoice.objects.get(cod=invoice_code)
    except ObjectDoesNotExist:
        # Notify administrators of invalid payment attempt
        notify_admins("invalid payment", "wrong invoice: " + invoice_code)
        return

    # Process payment updates within atomic transaction
    with transaction.atomic():
        # Update gross amount if provided
        if gross_amount:
            invoice.mc_gross = gross_amount

        # Update processing fee if provided
        if processing_fee:
            invoice.mc_fee = processing_fee

        # Update transaction ID if provided
        if transaction_id:
            invoice.txn_id = transaction_id

        # Skip processing if already checked or confirmed
        if invoice.status in (PaymentStatus.CHECKED, PaymentStatus.CONFIRMED):
            return True

        # Mark invoice as checked and save changes
        invoice.status = PaymentStatus.CHECKED
        invoice.save()

    return True
