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

"""Sumup payment gateway integration."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from decimal import Decimal

import requests
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest
from django.urls import reverse

from larpmanager.accounting.invoice import invoice_received_money
from larpmanager.models.accounting import PaymentInvoice
from larpmanager.utils.core.base import get_context, update_payment_details
from larpmanager.utils.larpmanager.tasks import notify_admins

logger = logging.getLogger(__name__)


def get_sumup_form(
    request: HttpRequest,
    context: dict,
    invoice: PaymentInvoice,
    amount: Decimal,
) -> None:
    """Generate SumUp payment form for invoice processing.

    Creates a SumUp checkout session by first authenticating with the SumUp API
    to obtain an access token, then creating a checkout with the invoice details.
    Updates the invoice code with the checkout ID for tracking purposes.

    Args:
        request: Django HTTP request object containing request metadata
        context: Context dictionary containing SumUp payment configuration:
            - sumup_client_id: SumUp API client ID
            - sumup_client_secret: SumUp API client secret
            - sumup_merchant_id: SumUp merchant identifier
            - payment_currency: Currency code for the payment
        invoice: Invoice instance to process payment for
        amount: Payment amount to charge (will be converted to float)

    Raises:
        KeyError: If required configuration keys are missing from context
        requests.RequestException: If API requests fail
        json.JSONDecodeError: If API response is not valid JSON

    """
    # Authenticate with SumUp API to obtain access token
    authentication_url = "https://api.sumup.com/token"
    authentication_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    authentication_payload = {
        "client_id": context["sumup_client_id"],
        "client_secret": context["sumup_client_secret"],
        "grant_type": "client_credentials",
    }

    # Make authentication request and extract token
    authentication_response = requests.request(
        "POST",
        authentication_url,
        headers=authentication_headers,
        data=authentication_payload,
        timeout=30,
    )

    # Validate authentication response
    expected_success_code = 200
    if authentication_response.status_code != expected_success_code:
        error_msg = f"SumUp authentication failed with status {authentication_response.status_code}: {authentication_response.text}"
        logger.error(error_msg)
        notify_admins("SumUp authentication failed", error_msg)
        msg = "Payment gateway authentication failed"
        raise Http404(msg)

    try:
        authentication_response_data = json.loads(authentication_response.text)
        access_token = authentication_response_data["access_token"]
    except (json.JSONDecodeError, KeyError) as e:
        error_msg = f"Failed to parse SumUp authentication response: {e}\nResponse: {authentication_response.text}"
        logger.exception(error_msg)
        notify_admins("SumUp authentication JSON error", error_msg)
        msg = "Invalid response from payment gateway"
        raise Http404(msg) from e

    # Prepare checkout creation request with invoice details
    checkout_url = "https://api.sumup.com/v0.1/checkouts"
    checkout_payload = json.dumps(
        {
            "checkout_reference": invoice.cod,
            "amount": float(amount.quantize(Decimal("0.01"))),
            "currency": context["payment_currency"],
            "merchant_code": context["sumup_merchant_id"],
            "description": invoice.causal,
            # Configure callback URLs for payment flow
            "return_url": request.build_absolute_uri(reverse("accounting_webhook_sumup")),
            "redirect_url": request.build_absolute_uri(reverse("accounting_payed", args=[invoice.uuid])),
            "payment_type": "boleto",
        },
    )

    # Set authorization headers with obtained token
    checkout_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    # Create checkout session and extract checkout ID
    checkout_response = requests.request(
        "POST",
        checkout_url,
        headers=checkout_headers,
        data=checkout_payload,
        timeout=30,
    )

    # Validate checkout response
    expected_success_code = 201
    if checkout_response.status_code != expected_success_code:
        error_msg = f"SumUp checkout failed with status {checkout_response.status_code}: {checkout_response.text}"
        logger.error(error_msg)
        notify_admins("SumUp checkout failed", error_msg)
        msg = "Payment checkout creation failed"
        raise Http404(msg)

    try:
        checkout_response_data = json.loads(checkout_response.text)
        checkout_id = checkout_response_data["id"]
    except (json.JSONDecodeError, KeyError) as e:
        error_msg = f"Failed to parse SumUp checkout response: {e}\nResponse: {checkout_response.text}"
        logger.exception(error_msg)
        notify_admins("SumUp checkout JSON error", error_msg)
        msg = "Invalid response from payment gateway"
        raise Http404(msg) from e

    # Store checkout ID in context and update invoice for tracking
    context["sumup_checkout_id"] = checkout_id
    invoice.cod = checkout_id
    invoice.save()


def sumup_webhook(request: HttpRequest) -> bool:  # noqa: PLR0911 - Multiple security checks require multiple returns
    """Handle SumUp webhook notifications for payment processing.

    Processes incoming webhook requests from SumUp payment gateway,
    validates the HMAC signature, payment status, and triggers invoice
    payment processing for successful transactions.

    Args:
        request: HTTP request object containing webhook payload from SumUp

    Returns:
        bool: True if payment was processed successfully, False if payment
              failed, signature invalid, or was not successful

    """
    # Get context and payment configuration
    context = get_context(request)
    update_payment_details(context)

    # Verify HMAC signature if configured
    sumup_webhook_secret = context.get("sumup_webhook_secret")
    if sumup_webhook_secret:
        # Get signature from headers
        signature_header = request.META.get("HTTP_X_SUMUP_SIGNATURE")
        if not signature_header:
            logger.error("SumUp webhook: Missing signature header")
            return False

        # Compute expected signature using HMAC-SHA256
        expected_signature = hmac.new(sumup_webhook_secret.encode("utf-8"), request.body, hashlib.sha256).hexdigest()

        # Verify signature matches
        if not hmac.compare_digest(signature_header, expected_signature):
            logger.error(
                "SumUp webhook: Invalid signature. Expected: %s, Got: %s", expected_signature, signature_header
            )
            return False

    # Parse the JSON payload from the webhook request body
    try:
        webhook_payload = json.loads(request.body)
        payment_status = webhook_payload["status"]
        payment_id = webhook_payload["id"]
    except (json.JSONDecodeError, KeyError) as e:
        error_msg = f"Failed to parse SumUp webhook payload: {e}\nBody: {request.body}"
        logger.exception(error_msg)
        notify_admins("SumUp webhook JSON error", error_msg)
        return False

    # Check if the payment status indicates failure or non-success
    if payment_status != "SUCCESSFUL":
        return False

    # Get invoice to verify amount and currency
    try:
        invoice = PaymentInvoice.objects.get(cod=payment_id)
    except ObjectDoesNotExist:
        logger.exception("SumUp webhook: Invoice not found: %s", payment_id)
        return False

    # Extract amount and currency from webhook payload
    sumup_amount = webhook_payload.get("amount")
    sumup_currency = webhook_payload.get("currency")

    # Verify currency if available
    expected_currency = context.get("payment_currency")
    if expected_currency and sumup_currency and sumup_currency != expected_currency:
        logger.error(
            "SumUp webhook: Currency mismatch. Expected: %s, Got: %s, Invoice: %s",
            expected_currency,
            sumup_currency,
            payment_id,
        )
        return False

    # Process the successful payment using the transaction ID
    sumup_amount_decimal = Decimal(str(sumup_amount)) if sumup_amount is not None else None
    return invoice_received_money(
        payment_id, expected_amount=invoice.mc_gross, gross_amount=sumup_amount_decimal, payment_method="sumup"
    )
