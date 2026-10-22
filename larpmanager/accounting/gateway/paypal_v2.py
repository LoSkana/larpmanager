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

"""PayPal payment gateway integration through the Orders v2 REST API."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import requests
from django.conf import settings as conf_settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from larpmanager.accounting.gateway import GatewayError, missing_gateway_keys
from larpmanager.accounting.invoice import invoice_received_money
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.utils.core.base import get_context, update_payment_details
from larpmanager.utils.larpmanager.tasks import notify_admins

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)

PAYPAL_V2_LIVE_URL = "https://api-m.paypal.com"
PAYPAL_V2_SANDBOX_URL = "https://api-m.sandbox.paypal.com"

PAYPAL_V2_TIMEOUT = 30

# Cancellations faster than this after the order creation are treated as gateway errors
PAYPAL_V2_BOUNCE_SECONDS = 5

# How long a pending capture blocks new payments of the same invoice key, PayPal can take days to settle it
PAYPAL_V2_PENDING_TIMEOUT = timedelta(days=7)

# Capture statuses of a completed payment, and of a payment PayPal still has to settle
PAYPAL_V2_COMPLETED = "COMPLETED"
PAYPAL_V2_PENDING = "PENDING"

# Currencies PayPal accepts only without decimals
PAYPAL_V2_ZERO_DECIMAL_CURRENCIES = {"HUF", "JPY", "TWD"}

PAYPAL_V2_ORDER_ID_RE = re.compile(r"[A-Za-z0-9-]{1,64}")


def is_paypal_v2_order_id(order_id: str | None) -> bool:
    """Return whether a string has the shape of a PayPal order id."""
    return bool(order_id and PAYPAL_V2_ORDER_ID_RE.fullmatch(order_id))


def paypal_v2_amount(amount: Decimal, currency: str) -> str:
    """Format an amount with the decimals PayPal requires for the currency."""
    precision = Decimal(1) if currency.upper() in PAYPAL_V2_ZERO_DECIMAL_CURRENCIES else Decimal("0.01")
    return str(amount.quantize(precision))


class PaypalV2CaptureRejectedError(GatewayError):
    """Raised when PayPal completed a capture that cannot be registered on the invoice."""


def _paypal_v2_pending_key(invoice: PaymentInvoice) -> str:
    """Return the cache key flagging a pending PayPal capture on the invoice key."""
    key_hash = hashlib.sha256(str(invoice.key or invoice.uuid).encode()).hexdigest()[:32]
    return f"paypal_v2_pending_{invoice.member_id}_{key_hash}"


def is_paypal_v2_pending(invoice: PaymentInvoice) -> bool:
    """Return whether a PayPal capture of the invoice key is still waiting to be settled."""
    return cache.get(_paypal_v2_pending_key(invoice)) is not None


def set_paypal_v2_pending(invoice: PaymentInvoice) -> None:
    """Flag the invoice key with a pending PayPal capture, blocking new payments until it is settled."""
    cache.set(
        _paypal_v2_pending_key(invoice), str(invoice.uuid), timeout=int(PAYPAL_V2_PENDING_TIMEOUT.total_seconds())
    )


def clear_paypal_v2_pending(invoice: PaymentInvoice) -> None:
    """Release the pending PayPal capture flag of the invoice key."""
    cache.delete(_paypal_v2_pending_key(invoice))


def paypal_v2_api_url(path: str) -> str:
    """Return the full PayPal API url of a path, sandbox or live according to settings."""
    base_url = PAYPAL_V2_SANDBOX_URL if conf_settings.PAYPAL_TEST else PAYPAL_V2_LIVE_URL
    return base_url + path


def _paypal_v2_token(context: dict) -> str:
    """Return an OAuth access token for the association PayPal app, cached until it expires."""
    client_id = context["paypal_v2_client_id"]
    secret = context["paypal_v2_secret"]
    credentials_hash = hashlib.sha256(f"{client_id}:{secret}".encode()).hexdigest()
    cache_key = f"paypal_v2_token_{credentials_hash}"

    token = cache.get(cache_key)
    if token:
        return token

    try:
        response = requests.post(
            paypal_v2_api_url("/v1/oauth2/token"),
            auth=(client_id, secret),
            data={"grant_type": "client_credentials"},
            timeout=PAYPAL_V2_TIMEOUT,
        )
    except requests.RequestException as err:
        msg = f"PayPal authentication request failed: {err}"
        raise GatewayError(msg) from err

    if response.status_code != 200:  # noqa: PLR2004 - HTTP OK
        msg = f"PayPal authentication failed with status {response.status_code}: {response.text}"
        raise GatewayError(msg)

    try:
        response_data = response.json()
        token = response_data["access_token"]
        expires_in = int(response_data.get("expires_in", 0))
    except (ValueError, KeyError) as err:
        msg = f"Invalid PayPal authentication response: {response.text}"
        raise GatewayError(msg) from err

    # Refresh the token a minute before PayPal expires it
    timeout = expires_in - 60
    if timeout > 0:
        cache.set(cache_key, token, timeout=timeout)
    return token


def _paypal_v2_request(context: dict, method: str, path: str, payload: dict | None = None) -> requests.Response:
    """Perform an authenticated request to the PayPal API."""
    headers = {
        "Authorization": f"Bearer {_paypal_v2_token(context)}",
        "Content-Type": "application/json",
    }
    try:
        return requests.request(
            method,
            paypal_v2_api_url(path),
            headers=headers,
            json=payload,
            timeout=PAYPAL_V2_TIMEOUT,
        )
    except requests.RequestException as err:
        msg = f"PayPal request {method} {path} failed: {err}"
        raise GatewayError(msg) from err


def get_paypal_v2_form(request: HttpRequest, context: dict, invoice: PaymentInvoice, amount: Decimal) -> None:
    """Create a PayPal order for the invoice and add the PayPal approval url to the context.

    Raises:
        GatewayError: If PayPal refuses the order or cannot be reached

    """
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                # PayPal refuses invoice ids already used by a capture, each order gets its own
                "invoice_id": f"{invoice.cod}-{secrets.token_hex(4)}",
                "custom_id": str(invoice.uuid),
                "description": invoice.causal[:127],
                "amount": {
                    "currency_code": context["payment_currency"],
                    "value": paypal_v2_amount(amount, context["payment_currency"]),
                },
            },
        ],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "user_action": "PAY_NOW",
                    "shipping_preference": "NO_SHIPPING",
                    "return_url": request.build_absolute_uri(reverse("accounting_paypal_return", args=[invoice.uuid])),
                    "cancel_url": request.build_absolute_uri(reverse("accounting_cancelled"))
                    + f"?invoice={invoice.uuid}",
                },
            },
        },
    }
    response = _paypal_v2_request(context, "POST", "/v2/checkout/orders", payload)
    if response.status_code not in (200, 201):
        msg = f"PayPal order creation failed with status {response.status_code}: {response.text}"
        raise GatewayError(msg)

    try:
        order = response.json()
        approve_url = next(link["href"] for link in order["links"] if link["rel"] in ("payer-action", "approve"))
    except (ValueError, KeyError, StopIteration) as err:
        msg = f"Invalid PayPal order response: {response.text}"
        raise GatewayError(msg) from err

    context["paypal_url"] = approve_url

    # Track the order on the invoice, to capture it on return
    invoice.txn_id = order["id"]
    invoice.save()


def _paypal_v2_receive_capture(context: dict, invoice: PaymentInvoice, capture: dict) -> bool:
    """Register a completed PayPal capture on the invoice, after checking its currency."""
    amount = capture.get("amount", {})
    expected_currency = context.get("payment_currency")
    if expected_currency and amount.get("currency_code", "").upper() != expected_currency.upper():
        logger.error(
            "PayPal: Currency mismatch. Expected: %s, Got: %s, Invoice: %s",
            expected_currency,
            amount.get("currency_code"),
            invoice.cod,
        )
        return False

    paypal_fee = capture.get("seller_receivable_breakdown", {}).get("paypal_fee", {}).get("value")
    return bool(
        invoice_received_money(
            invoice.cod,
            Decimal(amount["value"]),
            Decimal(paypal_fee) if paypal_fee else None,
            capture["id"],
            expected_amount=invoice.mc_gross,
            payment_method="paypal_v2",
        )
    )


def _paypal_v2_check_order_invoice(context: dict, invoice: PaymentInvoice, order_id: str) -> None:
    """Ensure a PayPal order was created for the invoice.

    Raises:
        GatewayError: If the order cannot be read or belongs to another invoice

    """
    response = _paypal_v2_request(context, "GET", f"/v2/checkout/orders/{order_id}")
    if response.status_code != 200:  # noqa: PLR2004 - HTTP OK
        msg = f"PayPal order {order_id} retrieval failed with status {response.status_code}: {response.text}"
        raise GatewayError(msg)

    try:
        custom_id = response.json()["purchase_units"][0].get("custom_id")
    except (ValueError, KeyError, IndexError) as err:
        msg = f"Invalid PayPal order response for order {order_id}: {response.text}"
        raise GatewayError(msg) from err

    if custom_id != str(invoice.uuid):
        msg = f"PayPal order {order_id} does not belong to invoice {invoice.cod}"
        raise GatewayError(msg)


def paypal_v2_capture(context: dict, invoice: PaymentInvoice, order_id: str | None = None) -> str:
    """Capture the PayPal order of an invoice the user has just approved.

    The order defaults to the last one created for the invoice; any other order is
    checked to belong to the invoice before being captured.

    Returns:
        The capture status (COMPLETED, PENDING, DECLINED, ...)

    Raises:
        GatewayError: If PayPal refuses the capture or cannot be reached
        PaypalV2CaptureRejectedError: If PayPal completed the capture but it does not match the invoice

    """
    order_id = order_id or invoice.txn_id
    if not order_id:
        msg = f"No PayPal order on invoice {invoice.cod}"
        raise GatewayError(msg)

    if order_id != invoice.txn_id:
        _paypal_v2_check_order_invoice(context, invoice, order_id)

    response = _paypal_v2_request(context, "POST", f"/v2/checkout/orders/{order_id}/capture")

    # Order already captured (e.g. page reloaded, or webhook arrived first): read its current state
    if response.status_code == 422 and "ORDER_ALREADY_CAPTURED" in response.text:  # noqa: PLR2004 - HTTP Unprocessable
        response = _paypal_v2_request(context, "GET", f"/v2/checkout/orders/{order_id}")

    if response.status_code not in (200, 201):
        msg = f"PayPal capture of order {order_id} failed with status {response.status_code}: {response.text}"
        raise GatewayError(msg)

    try:
        capture = response.json()["purchase_units"][0]["payments"]["captures"][0]
    except (ValueError, KeyError, IndexError) as err:
        msg = f"Invalid PayPal capture response for order {order_id}: {response.text}"
        raise GatewayError(msg) from err

    status = capture.get("status", "")
    if status == PAYPAL_V2_PENDING:
        set_paypal_v2_pending(invoice)
    if status == PAYPAL_V2_COMPLETED and not _paypal_v2_receive_capture(context, invoice, capture):
        msg = f"PayPal capture {capture.get('id')} of order {order_id} not accepted for invoice {invoice.cod}"
        raise PaypalV2CaptureRejectedError(msg)

    return status


def _paypal_v2_verify_webhook(request: HttpRequest, context: dict, raw_event: str) -> bool:
    """Verify the signature of a PayPal webhook notification through the PayPal API."""
    # Requests without the PayPal signature headers are not worth a verification call
    if not request.headers.get("Paypal-Transmission-Id") or not request.headers.get("Paypal-Transmission-Sig"):
        return False

    headers = {
        "auth_algo": request.headers.get("Paypal-Auth-Algo", ""),
        "cert_url": request.headers.get("Paypal-Cert-Url", ""),
        "transmission_id": request.headers.get("Paypal-Transmission-Id", ""),
        "transmission_sig": request.headers.get("Paypal-Transmission-Sig", ""),
        "transmission_time": request.headers.get("Paypal-Transmission-Time", ""),
        "webhook_id": context["paypal_v2_webhook_id"],
    }

    # Embed the raw event: re-serializing it could alter the signed payload
    body = json.dumps(headers)[:-1] + ', "webhook_event": ' + raw_event + "}"

    try:
        response = requests.post(
            paypal_v2_api_url("/v1/notifications/verify-webhook-signature"),
            headers={
                "Authorization": f"Bearer {_paypal_v2_token(context)}",
                "Content-Type": "application/json",
            },
            data=body.encode("utf-8"),
            timeout=PAYPAL_V2_TIMEOUT,
        )
        return response.status_code == 200 and response.json().get("verification_status") == "SUCCESS"  # noqa: PLR2004 - HTTP OK
    except (requests.RequestException, ValueError, GatewayError):
        logger.exception("PayPal webhook verification request failed")
        return False


def paypal_v2_webhook(request: HttpRequest) -> bool:  # noqa: PLR0911 - Multiple validation checks require multiple returns
    """Handle PayPal webhook notifications, registering completed captures and releasing denied ones.

    Returns:
        True if the notification was processed or ignored, False if it failed and PayPal should retry it

    """
    context = get_context(request)
    update_payment_details(context)
    if missing_gateway_keys("paypal_v2", context):
        logger.error("PayPal webhook: not configured for association %s", context["association_id"])
        return False

    try:
        raw_event = request.body.decode("utf-8")
    except UnicodeDecodeError:
        logger.exception("PayPal webhook: invalid payload encoding")
        return False

    if not _paypal_v2_verify_webhook(request, context, raw_event):
        logger.error("PayPal webhook: signature verification failed")
        return False

    try:
        event = json.loads(raw_event)
    except ValueError:
        logger.exception("PayPal webhook: invalid payload")
        return False

    event_type = event.get("event_type")
    if event_type not in ("PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.DENIED"):
        return True

    capture = event.get("resource", {})
    invoice = PaymentInvoice.objects.filter(
        uuid=capture.get("custom_id") or "",
        association_id=context["association_id"],
        method__slug="paypal_v2",
    ).first()
    if not invoice:
        logger.error("PayPal webhook: Invoice not found: %s", capture.get("custom_id"))
        # PayPal may have settled money that no invoice tracks, it must be reconciled by hand
        notify_admins(
            f"PayPal webhook - invoice not found - {capture.get('id')}",
            f"Association: {context['association_id']}<br />\n"
            f"Event: {escape(event_type)}<br />\n"
            f"Resource: {escape(json.dumps(capture))}",
        )
        return True

    # A settled capture, denied or completed, lets the invoice key be paid again
    clear_paypal_v2_pending(invoice)
    if event_type == "PAYMENT.CAPTURE.DENIED":
        return True

    if invoice.status in (PaymentStatus.CHECKED, PaymentStatus.CONFIRMED):
        return True

    # Rejected captures (wrong currency or amount) must be reconciled by hand, retrying them would not help
    if not _paypal_v2_receive_capture(context, invoice, capture):
        logger.error("PayPal webhook: capture %s not accepted for invoice %s", capture.get("id"), invoice.cod)
        notify_admins(
            f"PayPal webhook - capture not accepted - {capture.get('id')}",
            f"Association: {context['association_id']}<br />\n"
            f"Invoice: {escape(invoice.cod)}<br />\n"
            f"Resource: {escape(json.dumps(capture))}",
        )
    return True


def get_paypal_v2_cancel_error(context: dict, invoice: PaymentInvoice) -> str | None:
    """Return the gateway error behind a cancelled PayPal order, or None if the user cancelled it.

    An order is considered failed if PayPal cannot return it, or if the user came back
    too quickly after its creation to have actually seen the PayPal page.
    """
    order_id = invoice.txn_id
    if not order_id:
        return "PayPal order not found on invoice"

    try:
        response = _paypal_v2_request(context, "GET", f"/v2/checkout/orders/{order_id}")
    except GatewayError as err:
        return str(err)

    if response.status_code != 200:  # noqa: PLR2004 - HTTP OK
        return f"PayPal order {order_id} retrieval failed with status {response.status_code}: {response.text}"

    try:
        order = response.json()
        created = datetime.fromisoformat(order["create_time"])
    except (ValueError, KeyError):
        return None

    elapsed_seconds = int((timezone.now() - created).total_seconds())
    if elapsed_seconds < PAYPAL_V2_BOUNCE_SECONDS:
        return f"Order {order_id} ({order.get('status')}) cancelled {elapsed_seconds} seconds after creation"

    return None
