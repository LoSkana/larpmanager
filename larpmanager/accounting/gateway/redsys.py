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

"""Redsys payment gateway integration."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
from decimal import Decimal
from pprint import pformat
from typing import TYPE_CHECKING, Any, ClassVar

from Crypto.Cipher import DES3
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse

from larpmanager.accounting.gateway import CURRENCY_TO_CENTS_MULTIPLIER
from larpmanager.accounting.invoice import invoice_received_money
from larpmanager.models.accounting import PaymentInvoice
from larpmanager.models.association import Association
from larpmanager.models.utils import generate_id
from larpmanager.utils.core.base import get_context, update_payment_details
from larpmanager.utils.core.common import generate_number
from larpmanager.utils.larpmanager.tasks import notify_admins

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


def redsys_invoice_cod() -> str:
    """Generate a unique Redsys invoice code.

    Returns:
        str: A 12-character unique invoice code.

    Raises:
        ValueError: If unable to generate unique code after 5 attempts.

    """
    # Try up to 5 times to generate a unique code
    max_attempts = 5
    for _attempt_number in range(max_attempts):
        # Generate 12-character code: 5 random numbers + 7 character ID
        invoice_code = generate_number(5) + generate_id(7)

        # Check if code is unique in database
        if not PaymentInvoice.objects.filter(cod=invoice_code).exists():
            return invoice_code

    # Raise error if all attempts failed
    msg = "Too many attempts to generate the code"
    raise ValueError(msg)


def get_redsys_form(request: HttpRequest, context: dict, invoice: PaymentInvoice, amount: Decimal) -> None:
    """Create Redsys payment form with encrypted parameters.

    Generates a secure payment form for Redsys payment gateway by creating
    encrypted parameters and updating the invoice with a unique code.

    Args:
        request: Django HTTP request object containing association data
        context: Context dictionary with Redsys payment configuration including
             merchant code, terminal, currency, secret key, and sandbox flag
        invoice: PaymentInvoice instance to be updated with payment code
        amount: Payment amount in decimal format

    Returns:
        None: Updates context dictionary in-place with 'redsys_form' key containing
              encrypted payment data ready for form submission

    Side Effects:
        - Updates invoice.cod with generated payment code
        - Saves invoice to database
        - Adds 'redsys_form' to context dictionary

    """
    # Generate unique invoice code and save to database
    invoice.cod = redsys_invoice_cod()
    invoice.save()

    # Prepare basic payment parameters for Redsys gateway
    payment_parameters = {
        "DS_MERCHANT_AMOUNT": amount,
        "DS_MERCHANT_CURRENCY": int(context["redsys_merchant_currency"]),
        "DS_MERCHANT_ORDER": invoice.cod,
        "DS_MERCHANT_PRODUCTDESCRIPTION": invoice.causal,
        "DS_MERCHANT_TITULAR": context["name"],
    }

    # Add merchant identification and terminal configuration
    payment_parameters.update(
        {
            "DS_MERCHANT_MERCHANTCODE": context["redsys_merchant_code"],
            "DS_MERCHANT_MERCHANTNAME": context["name"],
            "DS_MERCHANT_TERMINAL": context["redsys_merchant_terminal"],
            "DS_MERCHANT_TRANSACTIONTYPE": "0",  # Standard payment
        },
    )

    # Configure callback URLs for payment flow
    payment_parameters.update(
        {
            "DS_MERCHANT_MERCHANTURL": request.build_absolute_uri(reverse("accounting_webhook_redsys")),
            "DS_MERCHANT_URLOK": request.build_absolute_uri(reverse("accounting_payed", args=[invoice.uuid])),
            "DS_MERCHANT_URLKO": request.build_absolute_uri(reverse("accounting_redsys_ko")),
        },
    )

    # Add optional payment methods if configured
    if context.get("key"):
        payment_parameters["DS_MERCHANT_PAYMETHODS"] = context["key"]

    # Determine sandbox mode from configuration
    is_sandbox_mode = int(context["redsys_sandbox"]) == 1

    # Initialize Redsys client with merchant credentials
    redsys_payment_client = RedSysClient(
        business_code=context["redsys_merchant_code"],
        secret_key=context["redsys_secret_key"],
        sandbox=is_sandbox_mode,
    )

    # Generate encrypted form data and add to context
    context["redsys_form"] = redsys_payment_client.redsys_generate_request(payment_parameters)


def redsys_webhook(request: HttpRequest) -> bool:
    """Handle RedSys payment webhook notifications.

    Processes incoming webhook requests from RedSys payment gateway,
    validates the signature, and updates payment status accordingly.

    Args:
        request: Django HTTP request object containing webhook data

    Returns:
        bool: True if payment was successfully processed, False otherwise

    """
    # Initialize user context and update payment details
    context = get_context(request)
    update_payment_details(context)

    # Extract RedSys parameters and signature from POST data
    merchant_parameters = request.POST["Ds_MerchantParameters"]
    signature = request.POST["Ds_Signature"]

    # Initialize RedSys client with merchant credentials
    redsys_payment_client = RedSysClient(
        business_code=context["redsys_merchant_code"],
        secret_key=context["redsys_secret_key"],
    )

    # Validate the webhook signature and extract order code
    order_code = redsys_payment_client.redsys_check_response(signature, merchant_parameters, context)

    # Process successful payment if signature validation passed
    if order_code:
        # Get invoice to verify amount
        try:
            invoice = PaymentInvoice.objects.get(cod=order_code)
        except ObjectDoesNotExist:
            logger.exception("Redsys webhook: Invoice not found: %s", order_code)
            return False

        # Decode merchant parameters to get payment details
        try:
            payment_data = json.loads(base64.b64decode(merchant_parameters).decode())
            # Redsys amount is in cents
            redsys_amount = Decimal(str(int(payment_data.get("Ds_Amount", 0)))) / Decimal(
                str(CURRENCY_TO_CENTS_MULTIPLIER)
            )
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.exception("Redsys webhook: Failed to parse payment amount from merchant parameters")
            redsys_amount = None

        return invoice_received_money(
            order_code, expected_amount=invoice.mc_gross, gross_amount=redsys_amount, payment_method="redsys"
        )

    return False


class RedSysClient:
    """Client."""

    DATA: ClassVar[list] = [
        "DS_MERCHANT_AMOUNT",
        "DS_MERCHANT_CURRENCY",
        "DS_MERCHANT_ORDER",
        "DS_MERCHANT_PRODUCTDESCRIPTION",
        "DS_MERCHANT_TITULAR",
        "DS_MERCHANT_MERCHANTCODE",
        "DS_MERCHANT_MERCHANTURL",
        "DS_MERCHANT_URLOK",
        "DS_MERCHANT_URLKO",
        "DS_MERCHANT_MERCHANTNAME",
        "DS_MERCHANT_CONSUMERLANGUAGE",
        "DS_MERCHANT_MERCHANTSIGNATURE",
        "DS_MERCHANT_TERMINAL",
        "DS_MERCHANT_TRANSACTIONTYPE",
    ]

    LANG_MAP: ClassVar[dict] = {
        "es": "001",
        "en": "002",
        "ca": "003",
        "fr": "004",
        "de": "005",
        "nl": "006",
        "it": "007",
        "sv": "008",
        "pt": "009",
        "pl": "011",
        "gl": "012",
        "eu": "013",
        "da": "208",
    }

    ALPHANUMERIC_CHARACTERS = re.compile(b"[^a-zA-Z0-9]")

    def __init__(self, business_code: str, secret_key: str, *, sandbox: bool = False) -> None:
        """Initialize Redsys payment gateway with merchant credentials.

        Args:
            business_code: Merchant code provided by Redsys
            secret_key: Secret key for transaction signing
            sandbox: Whether to use sandbox environment

        """
        # Initialize all data parameters to None
        for param in self.DATA:
            setattr(self, param, None)

        # Set merchant credentials
        self.Ds_Merchant_MerchantCode = business_code
        self.secret_key = secret_key

        # Configure environment URL based on sandbox flag
        if sandbox:
            self.redsys_url = "https://sis-t.redsys.es:25443/sis/realizarPago"
        else:
            self.redsys_url = "https://sis.redsys.es/sis/realizarPago"

    @staticmethod
    def decode_parameters(merchant_parameters: str) -> dict:
        """Given the Ds_MerchantParameters from Redsys, decode it and eval the json file.

        :param merchant_parameters: Base 64 encoded json structure returned by
               Redsys
        :return merchant_parameters: Json structure with all parameters.
        """
        if not isinstance(merchant_parameters, str):
            msg = f"merchant_parameters must be str, got {type(merchant_parameters)}"
            raise TypeError(msg)

        try:
            return json.loads(base64.b64decode(merchant_parameters).decode())
        except (json.JSONDecodeError, ValueError) as e:
            error_msg = f"Failed to decode Redsys parameters: {e}\nParameters: {merchant_parameters}"
            logger.exception(error_msg)
            notify_admins("Redsys decode error", error_msg)
            msg = "Invalid Redsys parameters"
            raise ValueError(msg) from e

    def encrypt_order(self, order: str) -> bytes:
        """Create a unique key for every request using Triple DES encryption."""
        if not isinstance(order, str):
            msg = f"order must be str, got {type(order)}"
            raise TypeError(msg)
        initialization_vector = b"\0\0\0\0\0\0\0\0"
        decoded_secret_key = base64.b64decode(self.secret_key)
        triple_des_cipher = DES3.new(decoded_secret_key, DES3.MODE_CBC, IV=initialization_vector)
        padded_order = order.encode().ljust(16, b"\0")
        return triple_des_cipher.encrypt(padded_order)

    @staticmethod
    def sign_hmac256(encrypted_order: bytes, merchant_parameters: bytes) -> bytes:
        """Use the encrypted_order to sign merchant data using HMAC SHA256 and encode with Base64.

        :param encrypted_order: Encrypted Ds_Merchant_Order
        :param merchant_parameters: Redsys already encoded parameters
        :return Generated signature as a base64 encoded string.
        """
        if not isinstance(encrypted_order, bytes):
            msg = f"encrypted_order must be bytes, got {type(encrypted_order)}"
            raise TypeError(msg)
        if not isinstance(merchant_parameters, bytes):
            msg = f"merchant_parameters must be bytes, got {type(merchant_parameters)}"
            raise TypeError(msg)
        hmac_signature = hmac.new(encrypted_order, merchant_parameters, hashlib.sha256).digest()
        return base64.b64encode(hmac_signature)

    def redsys_generate_request(self, params: dict[str, Any]) -> dict[str, str]:
        """Generate Redsys Ds_MerchantParameters and Ds_Signature.

        :param params: dict with all transaction parameters
        :return dict url, signature, parameters and type signature.
        """
        merchant_parameters = {
            "DS_MERCHANT_AMOUNT": int(
                params["DS_MERCHANT_AMOUNT"].quantize(Decimal("0.01")) * CURRENCY_TO_CENTS_MULTIPLIER
            ),
            "DS_MERCHANT_ORDER": params["DS_MERCHANT_ORDER"].zfill(10),
            "DS_MERCHANT_MERCHANTCODE": params["DS_MERCHANT_MERCHANTCODE"][:9],
            "DS_MERCHANT_CURRENCY": params["DS_MERCHANT_CURRENCY"] or 978,  # EUR
            "DS_MERCHANT_TRANSACTIONTYPE": (params["DS_MERCHANT_TRANSACTIONTYPE"] or "0"),
            "DS_MERCHANT_TERMINAL": params["DS_MERCHANT_TERMINAL"] or "1",
            "DS_MERCHANT_URLOK": params["DS_MERCHANT_URLOK"][:250],
            "DS_MERCHANT_URLKO": params["DS_MERCHANT_URLKO"][:250],
            "DS_MERCHANT_MERCHANTURL": params["DS_MERCHANT_MERCHANTURL"][:250],
            "DS_MERCHANT_PRODUCTDESCRIPTION": (params["DS_MERCHANT_PRODUCTDESCRIPTION"][:125]),
            "DS_MERCHANT_TITULAR": params["DS_MERCHANT_TITULAR"][:60],
            "DS_MERCHANT_MERCHANTNAME": params["DS_MERCHANT_MERCHANTNAME"][:25],
            "DS_MERCHANT_CONSUMERLANGUAGE": self.LANG_MAP.get(params.get("DS_MERCHANT_CONSUMERLANGUAGE"), "001"),
        }

        # Encode merchant_parameters in json + base64
        base64_encoded_parameters = base64.b64encode(json.dumps(merchant_parameters).encode())
        # Encrypt order
        encrypted_order = self.encrypt_order(merchant_parameters["DS_MERCHANT_ORDER"])
        # Sign parameters
        signature = self.sign_hmac256(encrypted_order, base64_encoded_parameters).decode()
        return {
            "Ds_Redsys_Url": self.redsys_url,
            "Ds_SignatureVersion": "HMAC_SHA256_V1",
            "Ds_MerchantParameters": base64_encoded_parameters.decode(),
            "Ds_Signature": signature,
        }

    def redsys_check_response(self, signature: str, b64_merchant_parameters: str, context: dict) -> str | None:
        """Verify Redsys payment response signature and extract order number.

        Validates the cryptographic signature of payment response from Redsys gateway
        to ensure authenticity and prevent tampering. Checks payment status and
        sends notifications to executives on failure.

        Args:
            signature: Received HMAC-SHA256 signature from Redsys
            b64_merchant_parameters: Base64-encoded JSON merchant parameters
            context: Context dictionary containing association ID (a_id)

        Returns:
            str: Order number if signature valid and payment successful
            None: If signature invalid or payment failed

        Side effects:
            - Sends error emails to association executives on payment failure
            - Logs error messages for signature verification failures

        """
        # Decode Base64-encoded merchant parameters from Redsys
        try:
            merchant_parameters = json.loads(base64.b64decode(b64_merchant_parameters).decode())
        except (json.JSONDecodeError, ValueError) as e:
            error_msg = f"Failed to decode Redsys merchant parameters: {e}\nParameters: {b64_merchant_parameters}"
            logger.exception(error_msg)
            return notify_admins("Redsys webhook JSON error", error_msg)

        # Get association for executive notifications
        Association.objects.get(pk=context["association_id"])

        # Validate response code presence
        if "Ds_Response" not in merchant_parameters:
            return notify_admins("Ds_Response not found", str(merchant_parameters))

        # Check payment response code (0-99 indicates success)
        try:
            response_code = int(merchant_parameters["Ds_Response"])
        except (ValueError, KeyError):
            response_code = -1

        # Response codes 0-99 indicate successful payment, anything else is failure
        max_successful_response_code = 99
        if response_code < 0 or response_code > max_successful_response_code:
            error_msg = f"Parameters: {merchant_parameters}"
            return notify_admins("Invalid Redsys response code", error_msg)

        # Extract order number from merchant parameters
        try:
            order_number = merchant_parameters["Ds_Order"]
        except KeyError as e:
            error_msg = f"Ds_Order not found in merchant parameters: {e}\nParameters: {merchant_parameters}"
            return notify_admins("Redsys Ds_Order missing", error_msg)

        # Encrypt order number using 3DES for signature verification
        encrypted_order = self.encrypt_order(order_number)

        # Use original base64 parameters for signature verification
        computed_signature = self.sign_hmac256(encrypted_order, b64_merchant_parameters.encode())

        # Normalize both signatures to standard Base64 format for comparison
        # Redsys sends URL-safe Base64 (using - and _ instead of + and /)
        # Convert both to standard format to ensure comparison works
        normalized_received_sig = signature.replace("-", "+").replace("_", "/")
        normalized_computed_sig = computed_signature.decode().replace("-", "+").replace("_", "/")

        # Verify signature matches to ensure payment authenticity
        if normalized_received_sig != normalized_computed_sig:
            # Debug information for signature mismatch
            debug_info = f"""
                Signature Verification Failed:
                - Received signature (original): {signature}
                - Computed signature (original): {computed_signature.decode()}
                - Received signature (normalized): {normalized_received_sig}
                - Computed signature (normalized): {normalized_computed_sig}
                - Order number: {order_number}
                - Order length: {len(order_number)}
                - Encrypted order (hex): {encrypted_order.hex()}
                - Base64 params (first 100 chars): {b64_merchant_parameters[:100]}...
                - Merchant parameters: {pformat(merchant_parameters)}
                """
            error_message = (
                f"Redsys Security Alert: Signature Verification Failed - {signature} vs {computed_signature.decode()}"
            )
            error_message += debug_info
            logger.error(error_message)
            return None

        # Return order number for successful payment processing
        return order_number
