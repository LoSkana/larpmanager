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

from __future__ import annotations

import csv
import logging
import math
from decimal import Decimal
from io import StringIO
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.utils.core.common import clean, detect_delimiter
from larpmanager.utils.larpmanager.tasks import notify_admins

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from django.core.files.uploadedfile import InMemoryUploadedFile

logger = logging.getLogger(__name__)


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
            causal_parts = pending_invoice.causal.split()
            causal_code: str = causal_parts[0] if causal_parts else ""

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
            # amount_difference > 0 means overpayment (ok), < 0 means underpayment (skip)
            amount_difference: float = math.ceil(float(payment_amount_string)) - math.ceil(
                float(pending_invoice.mc_gross),
            )
            if amount_difference < 0:
                # Payment is less than invoice amount - skip this invoice
                continue

            # Mark invoice as verified and increment counter
            verified_payments_count += 1
            with transaction.atomic():
                pending_invoice.verified = True
                pending_invoice.save()

    return verified_payments_count


def invoice_received_money(
    invoice_code: str,
    gross_amount: float | Decimal | None = None,
    processing_fee: float | Decimal | None = None,
    transaction_id: str | None = None,
    expected_amount: float | Decimal | None = None,
    payment_method: str | None = None,
) -> bool | None:
    """Process received payment for a payment invoice.

    Updates payment invoice status and financial details when money is received
    from payment processors like PayPal or bank transfers.

    Args:
        invoice_code: Invoice code to identify the payment
        gross_amount: Optional gross amount received from payment processor
        processing_fee: Optional processing fee charged by payment processor
        transaction_id: Optional transaction ID from payment processor
        expected_amount: Optional expected payment amount for verification
        payment_method: Optional payment method name for logging

    Returns:
        True if payment was processed successfully, None if invalid invoice code
        or verification fails

    Raises:
        No exceptions are raised - invalid invoices are handled gracefully
        with admin notifications.

    Side Effects:
        - Updates invoice status to CHECKED
        - Saves financial details (gross amount, fees, transaction ID)
        - Sends admin notification for invalid payment codes or amount mismatches

    """
    # Attempt to retrieve the payment invoice by code
    try:
        invoice = PaymentInvoice.objects.get(cod=invoice_code)
    except ObjectDoesNotExist:
        # Notify administrators of invalid payment attempt
        logger.exception("Invalid payment: Invoice not found: %s", invoice_code)
        return None

    # Verify payment amount if provided and expected amount is available
    if gross_amount is not None and expected_amount is not None:
        received_amount = Decimal(str(gross_amount)) if not isinstance(gross_amount, Decimal) else gross_amount
        expected = Decimal(str(expected_amount)) if not isinstance(expected_amount, Decimal) else expected_amount

        # Allow small rounding differences (1 cent tolerance)
        amount_tolerance = Decimal("0.01")

        # Reject if received amount is less than expected (underpayment)
        if received_amount < (expected - amount_tolerance):
            method_name = payment_method or invoice.method.slug
            logger.error(
                "Payment alert: Insufficient Amount - Expected: %s, Received: %s, Invoice: %s, TxnID: %s, Method: %s, Association: %s",
                expected,
                received_amount,
                invoice_code,
                transaction_id,
                method_name,
                invoice.association.slug,
            )
            return None

        # Log warning for overpayment (but still accept)
        if received_amount > (expected + amount_tolerance):
            method_name = payment_method or invoice.method.slug
            logger.warning(
                "Payment overpayment detected. Expected: %s, Received: %s, Invoice: %s, Method: %s",
                expected,
                received_amount,
                invoice_code,
                method_name,
            )

    # Process payment updates within atomic transaction
    with transaction.atomic():
        # Validate payment amount to prevent underpayment attacks
        if gross_amount:
            # Check that received amount is at least the expected amount
            expected_amount = float(invoice.mc_gross) if invoice.mc_gross else 0
            received_amount = float(gross_amount)

            # Allow small rounding differences (1 cent tolerance)
            tolerance = 0.01
            if received_amount < (expected_amount - tolerance):
                error_msg = (
                    f"Underpayment detected - Invoice: {invoice_code}, "
                    f"Expected: {expected_amount:.2f}, Received: {received_amount:.2f}"
                )
                logger.error(error_msg)
                notify_admins("Payment underpayment detected", error_msg)
                return False

            invoice.mc_gross = Decimal(gross_amount)

        # Update processing fee if provided
        if processing_fee is not None:
            invoice.mc_fee = Decimal(str(processing_fee)) if not isinstance(processing_fee, Decimal) else processing_fee

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
