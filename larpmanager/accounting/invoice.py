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
import re
from decimal import Decimal
from io import StringIO
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.utils.core.common import clean, detect_delimiter

if TYPE_CHECKING:
    from django.core.files.uploadedfile import InMemoryUploadedFile

logger = logging.getLogger(__name__)


def parse_payment_amount(value: str) -> float | None:
    """Parse a monetary amount string into a float.

    Handles both decimal separator conventions, thousands separators,
    currency symbols and surrounding whitespace:
    "1.234,56" -> 1234.56, "1,234.56" -> 1234.56, "1234.56" -> 1234.56,
    "1234,56" -> 1234.56, "EUR 12,50" -> 12.5, "1.234" -> 1234.0 (thousands).

    Args:
        value: Raw amount string from the CSV

    Returns:
        Parsed amount, or None if the string contains no valid number

    """
    cleaned = re.sub(r"[^\d,.\-]", "", value)
    if not cleaned:
        return None

    last_dot = cleaned.rfind(".")
    last_comma = cleaned.rfind(",")
    if last_comma > last_dot:
        # Comma is the decimal separator unless it matches a pure thousands
        # grouping pattern like "1,000" or "1,234,567" (no dot present)
        cleaned = cleaned.replace(".", "")
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", cleaned):
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    elif last_dot > last_comma:
        # Dot is the decimal separator unless it matches a pure thousands
        # grouping pattern like "1.234" or "1.234.567" (no comma present)
        cleaned = cleaned.replace(",", "")
        if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", cleaned):
            cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_row_payment(row: list[str]) -> tuple[str, float] | None:
    """Extract causal and amount from a CSV row.

    Args:
        row: CSV row with format [amount, causal, ...]

    Returns:
        Tuple of (causal, amount), or None if the row is malformed,
        missing the causal, or the amount is unparsable (e.g. header rows)

    """
    min_columns = 2
    if len(row) < min_columns:
        return None

    payment_causal = row[1]
    payment_amount = parse_payment_amount(row[0])
    if not payment_causal or payment_amount is None:
        return None

    return payment_causal, payment_amount


def _invoice_matches(pending_invoice: PaymentInvoice, payment_causal: str) -> bool:
    """Check whether a CSV payment causal matches a pending invoice.

    All comparisons go through clean(), which lowercases and strips symbols,
    spaces and accents, so formatting differences in the bank statement
    (punctuation, casing, extra whitespace) do not prevent a match.

    Args:
        pending_invoice: Pending invoice to match against
        payment_causal: Causal text from the bank CSV row

    Returns:
        True if the payment causal matches the invoice by causal text,
        causal without the special code prefix, invoice code
        or transaction ID

    """
    cleaned_payment: str = clean(payment_causal)

    # Try to match causal text directly
    if clean(pending_invoice.causal) in cleaned_payment:
        return True

    # With the payment_special_code setting the causal is prefixed with
    # "{cod} - "; also try the causal without the code, since payers
    # often omit it in the bank transfer reason
    special_code_prefix: str = f"{pending_invoice.cod} - "
    if pending_invoice.causal.startswith(special_code_prefix):
        causal_without_code = pending_invoice.causal[len(special_code_prefix) :]
        if clean(causal_without_code) in cleaned_payment:
            return True

    # Try matching the invoice code, communicated to the payer in the
    # wire transfer instructions
    if pending_invoice.cod and clean(pending_invoice.cod) in cleaned_payment:
        return True

    # Try matching transaction ID if available
    return bool(pending_invoice.txn_id and clean(pending_invoice.txn_id) in cleaned_payment)


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
        # Skip malformed rows, missing causal or unparsable amount (e.g. header rows)
        row_payment = _extract_row_payment(row)
        if row_payment is None:
            continue

        payment_causal, payment_amount = row_payment

        # Check payment against all pending invoices
        for pending_invoice in context["todo"]:
            # Skip already verified invoices
            if pending_invoice.verified:
                continue

            # Skip if no match found
            if not _invoice_matches(pending_invoice, payment_causal):
                continue

            # Verify payment amount is sufficient (rounded up)
            # amount_difference > 0 means overpayment (ok), < 0 means underpayment (skip)
            amount_difference: float = math.ceil(payment_amount) - math.ceil(
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
        # Update gross amount if provided
        if gross_amount is not None:
            invoice.mc_gross = Decimal(str(gross_amount)) if not isinstance(gross_amount, Decimal) else gross_amount

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
