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

"""PayPal payment gateway integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from paypal.standard.forms import PayPalPaymentsForm
from paypal.standard.models import ST_PP_COMPLETED

from larpmanager.accounting.base import get_payment_details
from larpmanager.accounting.invoice import invoice_received_money
from larpmanager.models.accounting import PaymentInvoice

if TYPE_CHECKING:
    from decimal import Decimal

    from django.http import HttpRequest

logger = logging.getLogger(__name__)


def get_paypal_form(request: HttpRequest, context: dict, invoice: PaymentInvoice, amount: Decimal) -> None:
    """Create PayPal payment form.

    Args:
        request: Django HTTP request object
        context: Context dictionary with payment configuration
        invoice: PaymentInvoice instance
        amount (float): Payment amount

    Returns:
        dict: PayPal form context data

    """
    paypal_payment_data = {
        "business": context["paypal_id"],
        "amount": amount,
        "currency_code": context["payment_currency"],
        "item_name": invoice.causal,
        "invoice": invoice.cod,
        "notify_url": request.build_absolute_uri(reverse("paypal-ipn")),
        "return": request.build_absolute_uri(reverse("accounting_payed", args=[invoice.uuid])),
        "cancel_return": request.build_absolute_uri(reverse("accounting_cancelled")),
    }
    context["paypal_form"] = PayPalPaymentsForm(initial=paypal_payment_data)


def handle_valid_paypal_ipn(ipn_obj: Any) -> bool | None:
    """Handle valid PayPal IPN notifications.

    Args:
        ipn_obj: IPN object from PayPal

    Returns:
        Result from invoice_received_money or None

    """
    if ipn_obj.payment_status == ST_PP_COMPLETED:
        # SECURITY: Verify receiver email matches expected business email
        # This prevents attackers from crediting invoices with payments to their own PayPal account
        try:
            invoice = PaymentInvoice.objects.get(cod=ipn_obj.invoice)
        except ObjectDoesNotExist:
            logger.exception("PayPal IPN: Invoice not found: %s, TxnID: %s", ipn_obj.invoice, ipn_obj.txn_id)
            return None

        # Get payment configuration for invoice's association
        payment_config = get_payment_details(invoice.association)
        expected_paypal_email = payment_config.get("paypal_id")
        if not expected_paypal_email:
            logger.error("PayPal IPN: No PayPal ID configured for association %s", invoice.association.slug)
            return None

        # Verify receiver email matches (case-insensitive)
        if ipn_obj.receiver_email.lower() != expected_paypal_email.lower():
            logger.error(
                "PayPal IPN: Receiver email mismatch. Expected: %s, Got: %s, Invoice: %s, TxnID: %s",
                expected_paypal_email,
                ipn_obj.receiver_email,
                ipn_obj.invoice,
                ipn_obj.txn_id,
            )
            return None

        # Verify payment currency matches expected currency
        expected_currency = payment_config.get("payment_currency")
        if expected_currency and ipn_obj.mc_currency != expected_currency:
            logger.error(
                "PayPal IPN: Currency mismatch. Expected: %s, Got: %s, Invoice: %s",
                expected_currency,
                ipn_obj.mc_currency,
                ipn_obj.invoice,
            )
            return None

        return invoice_received_money(
            ipn_obj.invoice,
            ipn_obj.mc_gross,
            ipn_obj.mc_fee,
            ipn_obj.txn_id,
            expected_amount=invoice.mc_gross,
            payment_method="paypal",
        )
    return None


def handle_invalid_paypal_ipn(invalid_ipn_object: Any) -> None:
    """Handle invalid PayPal IPN notifications."""
    invoice_code = getattr(invalid_ipn_object, "invoice", "unknown")
    logger.error("PayPal IPN validation failed for invoice: %s", invoice_code)
