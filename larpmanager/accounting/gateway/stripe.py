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

"""Stripe payment gateway integration."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

import stripe
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse

from larpmanager.accounting.gateway import CURRENCY_TO_CENTS_MULTIPLIER
from larpmanager.accounting.invoice import invoice_received_money
from larpmanager.models.accounting import PaymentInvoice
from larpmanager.utils.core.base import get_context, update_payment_details

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


def get_stripe_form(
    request: HttpRequest,
    context: dict,
    invoice: PaymentInvoice,
    amount: Decimal,
) -> None:
    """Create Stripe payment form and session.

    Creates a Stripe product and price for the given invoice amount, then
    generates a checkout session for payment processing. Updates the invoice
    with the price ID for tracking purposes.

    Args:
        request: Django HTTP request object for building absolute URLs
        context: Context dictionary containing payment configuration including
             'stripe_sk_api' (secret key) and 'payment_currency'
        invoice: PaymentInvoice instance to be paid
        amount: Payment amount in the configured currency

    Returns:
        None: Updates context dictionary with 'stripe_ck' checkout session

    """
    # Set Stripe API key from context configuration
    stripe.api_key = context["stripe_sk_api"]

    # Create a new Stripe product with invoice description
    stripe_product = stripe.Product.create(name=invoice.causal)

    # Create price object with amount converted to cents
    # Stripe requires amounts in smallest currency unit (cents for EUR/USD)
    stripe_price = stripe.Price.create(
        unit_amount=str(int(amount.quantize(Decimal("0.01")) * CURRENCY_TO_CENTS_MULTIPLIER)),
        currency=context["payment_currency"],
        product=stripe_product.id,
    )

    # Create checkout session with success/cancel URLs
    checkout_session = stripe.checkout.Session.create(
        line_items=[
            {
                "price": stripe_price.id,
                "quantity": 1,
            },
        ],
        mode="payment",
        success_url=request.build_absolute_uri(reverse("accounting_payed", args=[invoice.uuid])),
        cancel_url=request.build_absolute_uri(reverse("accounting_cancelled")),
    )

    # Add checkout session to context for template rendering
    context["stripe_ck"] = checkout_session

    # Store price ID in invoice for payment tracking
    invoice.cod = stripe_price.id
    invoice.save()


def stripe_webhook(request: HttpRequest) -> HttpResponse | bool:
    """Handle Stripe webhook events for payment processing.

    Args:
        request: Django HTTP request object containing Stripe webhook data

    Returns:
        HttpResponse: Success or error response for webhook processing

    """
    context = get_context(request)
    update_payment_details(context)
    stripe.api_key = context["stripe_sk_api"]
    payload = request.body
    signature_header = request.META["HTTP_STRIPE_SIGNATURE"]
    endpoint_secret = context["stripe_webhook_secret"]

    # Construct event from webhook payload - raises ValueError or SignatureVerificationError on failure
    event = stripe.Webhook.construct_event(payload, signature_header, endpoint_secret)

    # Handle the event
    if event["type"] == "checkout.session.completed" or event["type"] == "checkout.session.async_payment_succeeded":
        session = stripe.checkout.Session.retrieve(
            event["data"]["object"]["id"],
            expand=["line_items"],
        )

        line_items = session.line_items
        # Validate that line items exist
        if not line_items.get("data") or len(line_items["data"]) == 0:
            logger.error("Stripe session %s has no line items", session.id)
            return False

        # assume only one
        first_line_item = line_items["data"][0]
        price_id = first_line_item["price"]["id"]

        # Get invoice to verify amount and currency
        try:
            invoice = PaymentInvoice.objects.get(cod=price_id)
        except ObjectDoesNotExist:
            logger.exception("Stripe webhook: Invoice not found for price_id: %s", price_id)
            return False

        # Verify currency if configured
        expected_currency = context.get("payment_currency")
        stripe_currency = first_line_item["price"]["currency"].upper()
        if expected_currency and stripe_currency != expected_currency.upper():
            logger.error(
                "Stripe webhook: Currency mismatch. Expected: %s, Got: %s, Invoice: %s",
                expected_currency,
                stripe_currency,
                price_id,
            )
            return False

        # Get amount in base currency
        stripe_amount = Decimal(str(first_line_item["price"]["unit_amount"])) / Decimal(
            str(CURRENCY_TO_CENTS_MULTIPLIER)
        )

        return invoice_received_money(
            price_id, expected_amount=invoice.mc_gross, gross_amount=stripe_amount, payment_method="stripe"
        )
    return True
