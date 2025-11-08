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

"""Invoice generation and CSV import/export utilities."""

import csv
import math
from io import StringIO

from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import transaction

from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.utils.common import clean, detect_delimiter
from larpmanager.utils.tasks import notify_admins


def invoice_verify(context: dict, csv_upload: InMemoryUploadedFile) -> int:
    """Verify and match payments from CSV upload against pending invoices.

    Processes a CSV file containing payment data and matches entries against
    pending payment invoices using causal codes, registration codes, or transaction IDs.
    Marks matching invoices as verified when payment amounts are sufficient.

    Args:
        context (dict): Context dictionary containing 'todo' key with list of pending invoices
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
    csv_content: str = csv_upload.read().decode("utf-8")
    delimiter: str = detect_delimiter(csv_content)
    csv_data = csv.reader(StringIO(csv_content), delimiter=delimiter)

    verified_payments_count: int = 0

    # Process each row in the CSV file
    for row in csv_data:
        payment_causal: str = row[1]
        payment_amount_string: str = row[0].replace(".", "").replace(",", ".")

        # Skip rows with missing causal or amount data
        if not payment_causal or not payment_amount_string:
            continue

        # Check payment against all pending invoices
        for pending_invoice in context["todo"]:
            # Skip already verified invoices
            if pending_invoice.verified:
                continue

            # Try to match causal code directly
            causal_match_found: bool = clean(pending_invoice.causal) in clean(payment_causal)
            causal_code: str = pending_invoice.causal.split()[0]

            # Check for random causal codes (16 characters)
            random_causal_length: int = 16
            if not causal_match_found and len(causal_code) == random_causal_length:
                causal_match_found = causal_code in clean(payment_causal)

            # Try matching registration code if available
            if not causal_match_found and pending_invoice.reg_cod:
                causal_match_found = clean(pending_invoice.reg_cod) in clean(payment_causal)

            # Try matching transaction ID if available
            if not causal_match_found and pending_invoice.txn_id:
                causal_match_found = clean(pending_invoice.txn_id) in clean(payment_causal)

            # Skip if no match found
            if not causal_match_found:
                continue

            # Verify payment amount is sufficient (rounded up)
            amount_difference: float = math.ceil(float(payment_amount_string)) - math.ceil(
                float(pending_invoice.mc_gross)
            )
            if amount_difference > 0:
                continue

            # Mark invoice as verified and increment counter
            verified_payments_count += 1
            with transaction.atomic():
                pending_invoice.verified = True
                pending_invoice.save()

    return verified_payments_count


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
