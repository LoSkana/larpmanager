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

"""Satispay payment gateway integration.

Vendored from satispaython 0.4.0 (PyPI, unmaintained: https://github.com/otto-torino/satispaython).
"""

# ruff: noqa: D101, D102, D103, D107 -- vendored third-party API, kept close to upstream
# ruff: noqa: FBT001, FBT002, FBT003 -- `staging` bool matches upstream signature

from __future__ import annotations

import json
import logging
import math
from base64 import b64encode
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, generate_private_key
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import Http404, HttpRequest
from django.urls import reverse
from httpx import URL, AsyncClient, Auth, Client, Headers, Request, Response

from larpmanager.accounting.gateway import CURRENCY_TO_CENTS_MULTIPLIER
from larpmanager.accounting.invoice import invoice_received_money
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.utils.core.base import get_context, update_payment_details
from larpmanager.utils.larpmanager.tasks import notify_admins

if TYPE_CHECKING:
    from collections.abc import Generator
    from os import PathLike

logger = logging.getLogger(__name__)


class SatispayAuth(Auth):
    """Signs outgoing requests with the Satispay HTTP signature scheme."""

    requires_request_body = True

    def __init__(self, key_id: str, rsa_key: RSAPrivateKey) -> None:
        self._key_id = key_id
        self._rsa_key = rsa_key

    @staticmethod
    def _get_formatted_date() -> str:
        date = datetime.now(UTC)
        return date.strftime("%a, %d %b %Y %H:%M:%S %z")

    @staticmethod
    def _compute_digest(request: Request) -> str:
        digest = sha256(request.content).digest()
        digest = b64encode(digest).decode()
        return f"SHA-256={digest}"

    @staticmethod
    def _compose_string(request: Request, date: str, digest: str) -> str:
        method, target, host = request.method, request.url.path, request.url.host
        return f"(request-target): {method.lower()} {target}\nhost: {host}\ndate: {date}\ndigest: {digest}"

    def _sign_string(self, string: str) -> str:
        signature = self._rsa_key.sign(string.encode(), PKCS1v15(), SHA256())
        return b64encode(signature).decode()

    def _compose_authorization_header(self, signature: str) -> str:
        return (
            f'Signature keyId="{self._key_id}", '
            f'algorithm="rsa-sha256", '
            f'headers="(request-target) host date digest", '
            f'signature="{signature}"'
        )

    def _generate_authorization_headers(self, request: Request) -> Headers:
        date = self._get_formatted_date()
        digest = self._compute_digest(request)
        string = self._compose_string(request, date, digest)
        signature = self._sign_string(string)
        authorization_header = self._compose_authorization_header(signature)
        headers = {"Host": request.url.host, "Date": date, "Digest": digest, "Authorization": authorization_header}
        return Headers(headers)

    def auth_flow(self, request: Request) -> Generator[Request, Response, None]:
        authorization_headers = self._generate_authorization_headers(request)
        request.headers.update(authorization_headers)
        yield request


class SatispayClientMixin:
    """Shared request-preparation logic for the sync and async clients."""

    @staticmethod
    def _initialize(
        key_id: str,
        rsa_key: RSAPrivateKey,
        headers: Headers,
        staging: bool,
    ) -> tuple[SatispayAuth, Headers, URL]:
        auth = SatispayAuth(key_id, rsa_key)
        headers.update({"Accept": "application/json"})
        if staging:
            base_url = URL("https://staging.authservices.satispay.com")
        else:
            base_url = URL("https://authservices.satispay.com")
        return auth, headers, base_url

    @staticmethod
    def _prepare_create_payment(
        amount_unit: int,
        currency: str,
        body_params: dict,
        headers: Headers,
    ) -> tuple[URL, dict, Headers]:
        target = URL("/g_business/v1/payments")
        headers.update({"Content-Type": "application/json"})
        body_params.update({"flow": "MATCH_CODE", "amount_unit": amount_unit, "currency": currency})
        return target, body_params, headers

    @staticmethod
    def _prepare_get_payment_details(payment_id: str) -> URL:
        return URL(f"/g_business/v1/payments/{payment_id}")


class SatispayClient(Client, SatispayClientMixin):
    def __init__(self, key_id: str, rsa_key: RSAPrivateKey, staging: bool = False, **kwargs: object) -> None:
        headers = kwargs.pop("headers", Headers())
        auth, headers, base_url = self._initialize(key_id, rsa_key, headers, staging)
        super().__init__(auth=auth, headers=headers, base_url=base_url, **kwargs)

    def create_payment(
        self,
        amount_unit: int,
        currency: str,
        body_params: dict | None = None,
        headers: Headers | None = None,
    ) -> Response:
        body_params, headers = body_params or {}, headers or Headers()
        target, body, headers = self._prepare_create_payment(amount_unit, currency, body_params, headers)
        return self.post(target, content=json.dumps(body).encode(), headers=headers)

    def get_payment_details(self, payment_id: str, headers: Headers | None = None) -> Response:
        target = self._prepare_get_payment_details(payment_id)
        return self.get(target, headers=headers)


class AsyncSatispayClient(AsyncClient, SatispayClientMixin):
    def __init__(self, key_id: str, rsa_key: RSAPrivateKey, staging: bool = False, **kwargs: object) -> None:
        headers = kwargs.pop("headers", Headers())
        auth, headers, base_url = self._initialize(key_id, rsa_key, headers, staging)
        super().__init__(auth=auth, headers=headers, base_url=base_url, **kwargs)

    async def create_payment(
        self,
        amount_unit: int,
        currency: str,
        body_params: dict | None = None,
        headers: Headers | None = None,
    ) -> Response:
        body_params, headers = body_params or {}, headers or Headers()
        target, body, headers = self._prepare_create_payment(amount_unit, currency, body_params, headers)
        return await self.post(target, content=json.dumps(body).encode(), headers=headers)

    async def get_payment_details(self, payment_id: str, headers: Headers | None = None) -> Response:
        target = self._prepare_get_payment_details(payment_id)
        return await self.get(target, headers=headers)


def obtain_key_id(token: str, rsa_key: RSAPrivateKey, staging: bool = False) -> Response:
    target = "/g_business/v1/authentication_keys"
    key_encoding = Encoding.PEM
    key_format = PublicFormat.SubjectPublicKeyInfo
    public_key = rsa_key.public_key().public_bytes(key_encoding, key_format)
    body = {"public_key": public_key.decode(), "token": token}
    with SatispayClient("PLACEHOLDER", rsa_key, staging) as client:
        return client.post(target, content=json.dumps(body).encode())


def test_authentication(key_id: str, rsa_key: RSAPrivateKey) -> Response:
    target = "/wally-services/protocol/tests/signature"
    headers = {"Content-Type": "application/json"}
    with SatispayClient(key_id, rsa_key, True) as client:
        return client.post(target, headers=headers)


def create_payment(
    key_id: str,
    rsa_key: RSAPrivateKey,
    amount_unit: int,
    currency: str,
    body_params: dict | None = None,
    headers: Headers | None = None,
    staging: bool = False,
) -> Response:
    with SatispayClient(key_id, rsa_key, staging) as client:
        return client.create_payment(amount_unit, currency, body_params, headers)


def get_payment_details(
    key_id: str,
    rsa_key: RSAPrivateKey,
    payment_id: str,
    headers: Headers | None = None,
    staging: bool = False,
) -> Response:
    with SatispayClient(key_id, rsa_key, staging) as client:
        return client.get_payment_details(payment_id, headers)


def generate_key(path: PathLike | None = None, password: str | None = None) -> RSAPrivateKey:
    rsa_key = generate_private_key(65537, 4096)
    if path:
        write_key(rsa_key, path, password)
    return rsa_key


def write_key(rsa_key: RSAPrivateKey, path: PathLike, password: str | None = None) -> None:
    encryption_algorithm = BestAvailableEncryption(password.encode()) if password else NoEncryption()
    pem = rsa_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, encryption_algorithm)
    Path(path).write_bytes(pem)


def load_key(path: PathLike, password: str | None = None) -> RSAPrivateKey:
    password_bytes = password.encode() if password else None
    return load_pem_private_key(Path(path).read_bytes(), password_bytes)


def format_datetime(date: datetime) -> str:
    return date.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# --- LarpManager integration (uses the vendored client above) ---


def get_satispay_form(request: HttpRequest, context: dict, invoice: PaymentInvoice, amount: Decimal) -> None:
    """Create Satispay payment form and initialize payment.

    Creates a new Satispay payment request using the provided invoice and amount,
    then updates the invoice with the payment ID and returns the context data
    needed for the payment form.

    Args:
        request: Django HTTP request object used to build absolute URIs
        context: Context dictionary containing payment configuration including
            satispay_key_id, payment_currency, and other payment settings
        invoice: PaymentInvoice instance to be updated with payment ID
        amount: Payment amount in the base currency unit

    Returns:
        Updated context dictionary containing payment form data with
        redirect URL, callback URL, and payment ID

    Raises:
        Http404: If Satispay API call fails or returns non-200 status code

    """
    # Build redirect and callback URLs for payment flow
    context["redirect"] = request.build_absolute_uri(reverse("accounting_payed", args=[invoice.uuid]))
    context["callback"] = request.build_absolute_uri(reverse("accounting_webhook_satispay")) + "?payment_id={uuid}"

    # Load Satispay authentication credentials
    satispay_key_id = context["satispay_key_id"]
    satispay_rsa_key = load_key("main/satispay/private.pem")

    # Future implementation for payment expiration

    # Prepare body parameters with callback URL
    body_params = {
        "callback_url": context["callback"],
        "redirect_url": context["redirect"],
        "external_code": invoice.causal,
    }

    # Create payment request with Satispay API (amount in cents)
    satispay_response = create_payment(
        satispay_key_id,
        satispay_rsa_key,
        math.ceil(amount * CURRENCY_TO_CENTS_MULTIPLIER),
        context["payment_currency"],
        body_params,
    )

    # Validate API response and handle errors
    expected_success_status_code = 200
    if satispay_response.status_code != expected_success_status_code:
        notify_admins("satispay ko", str(satispay_response.content))
        msg = "something went wrong :( "
        raise Http404(msg)

    # Parse response and update invoice with payment ID
    try:
        response_data = json.loads(satispay_response.content)
        invoice_id = response_data["id"]
    except (json.JSONDecodeError, KeyError) as e:
        error_msg = f"Failed to parse Satispay response: {e}\nResponse: {satispay_response.content}"
        logger.exception(error_msg)
        notify_admins("Satispay JSON parsing error", error_msg)
        msg = "Invalid response from payment gateway"
        raise Http404(msg) from e

    with transaction.atomic():
        invoice.cod = invoice_id
        invoice.save()

    # Add payment ID to context for form rendering
    context["pay_id"] = invoice_id


def satispay_check(context: dict) -> None:
    """Check status of pending Satispay payments.

    Args:
        context: Context dictionary with payment configuration

    """
    update_payment_details(context)

    if "satispay_key_id" not in context:
        return

    que = PaymentInvoice.objects.filter(
        method__slug="satispay",
        status=PaymentStatus.CREATED,
    )
    if not que.exists():
        return

    for invoice in que:
        satispay_verify(context, invoice.cod)


def satispay_verify(context: dict, payment_code: str) -> None:
    """Verify Satispay payment status and process if accepted.

    This function verifies a Satispay payment by checking the payment status
    through the Satispay API and processes the payment if it has been accepted.

    Args:
        context: Dict context information
        payment_code: Payment code/identifier to verify against Satispay API

    Returns:
        None: Function performs side effects but returns nothing

    Note:
        Logs warnings for various error conditions and returns early on failures.
        Only processes payments with status "ACCEPTED" from Satispay.

    """
    # Initialize context and update payment details from request
    update_payment_details(context)

    # Retrieve invoice by payment code, log and return if not found
    try:
        invoice = PaymentInvoice.objects.get(cod=payment_code)
    except ObjectDoesNotExist:
        logger.warning("Not found - invoice %s", payment_code)
        return

    # Validate that invoice uses Satispay payment method
    if invoice.method.slug != "satispay":
        logger.warning("Wrong slug method - invoice %s", payment_code)
        return

    # Check if payment is still in created status (not already processed)
    if invoice.status != PaymentStatus.CREATED:
        logger.warning("Already confirmed - invoice %s", payment_code)
        return

    # Load Satispay API credentials and private key for authentication
    key_id = context["satispay_key_id"]
    rsa_key = load_key("main/satispay/private.pem")

    # Make API call to Satispay to get current payment status
    response = get_payment_details(key_id, rsa_key, invoice.cod)

    # Validate API response status code
    expected_success_code = 200
    if response.status_code != expected_success_code:
        return

    # Parse response and extract payment details
    try:
        payment_data = json.loads(response.content)
        payment_amount = Decimal(str(int(payment_data["amount_unit"]))) / Decimal(str(CURRENCY_TO_CENTS_MULTIPLIER))
        payment_status = payment_data["status"]
        payment_currency = payment_data.get("currency")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        error_msg = f"Failed to parse Satispay payment verification: {e}\nResponse: {response.content}"
        logger.exception(error_msg)
        notify_admins("Satispay verification JSON error", error_msg)
        return

    # Verify currency if available
    expected_currency = context.get("payment_currency")
    if expected_currency and payment_currency and payment_currency != expected_currency:
        logger.error(
            "Satispay Security Alert: Currency Mismatch - Expected: %s, Got: %s, Invoice: %s - REJECTED",
            expected_currency,
            payment_currency,
            invoice.cod,
        )
        return

    # Process payment if Satispay marked it as accepted
    if payment_status == "ACCEPTED":
        invoice_received_money(invoice.cod, payment_amount, expected_amount=invoice.mc_gross, payment_method="satispay")


def satispay_webhook(request: HttpRequest) -> None:
    """Handle Satispay webhook notifications."""
    payment_id = request.GET.get("payment_id", "")
    context = get_context(request)
    satispay_verify(context, payment_id)
