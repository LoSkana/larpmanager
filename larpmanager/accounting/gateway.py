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

"""Payment gateway integration for PayPal, Stripe, and Redsys."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import re
from pprint import pformat
from typing import Any, ClassVar

import requests
import satispaython
import stripe
from Crypto.Cipher import DES3
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.urls import reverse
from paypal.standard.forms import PayPalPaymentsForm
from paypal.standard.models import ST_PP_COMPLETED
from satispaython.utils import load_key

from larpmanager.accounting.invoice import invoice_received_money
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.models.association import Association
from larpmanager.models.utils import generate_id
from larpmanager.utils.core.base import get_context, update_payment_details
from larpmanager.utils.core.common import generate_number
from larpmanager.utils.larpmanager.tasks import notify_admins

logger = logging.getLogger(__name__)

# Currency conversion constants
# Payment gateways typically require amounts in smallest currency unit (cents for EUR/USD)
CURRENCY_TO_CENTS_MULTIPLIER = 100


def get_satispay_form(request: HttpRequest, context: dict[str, Any], invoice: PaymentInvoice, amount: float) -> None:
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
    context["redirect"] = request.build_absolute_uri(reverse("acc_payed", args=[invoice.id]))
    context["callback"] = request.build_absolute_uri(reverse("acc_webhook_satispay")) + "?payment_id={uuid}"

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
    satispay_response = satispaython.create_payment(
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
    response = satispaython.get_payment_details(key_id, rsa_key, invoice.cod)

    # Validate API response status code
    expected_success_code = 200
    if response.status_code != expected_success_code:
        return

    # Parse response and extract payment details
    try:
        payment_data = json.loads(response.content)
        payment_amount = int(payment_data["amount_unit"]) / float(CURRENCY_TO_CENTS_MULTIPLIER)
        payment_status = payment_data["status"]
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        error_msg = f"Failed to parse Satispay payment verification: {e}\nResponse: {response.content}"
        logger.exception(error_msg)
        notify_admins("Satispay verification JSON error", error_msg)
        return

    # Process payment if Satispay marked it as accepted
    if payment_status == "ACCEPTED":
        invoice_received_money(invoice.cod, payment_amount)


def satispay_webhook(request: HttpRequest) -> None:
    """Handle Satispay webhook notifications.

    Args:
        request: Django HTTP request with payment_id parameter

    """
    payment_id = request.GET.get("payment_id", "")
    context = get_context(request)
    satispay_verify(context, payment_id)


def get_paypal_form(request: HttpRequest, context: dict, invoice: PaymentInvoice, amount: float) -> None:
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
        "amount": float(amount),
        "currency_code": context["payment_currency"],
        "item_name": invoice.causal,
        "invoice": invoice.cod,
        "notify_url": request.build_absolute_uri(reverse("paypal-ipn")),
        "return": request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
        "cancel_return": request.build_absolute_uri(reverse("acc_cancelled")),
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
        # Validate receiver email to prevent payment hijacking
        # Get invoice to verify against expected PayPal business account
        try:
            invoice = PaymentInvoice.objects.get(cod=ipn_obj.invoice)
            context = {"association_id": invoice.association_id}
            update_payment_details(context)

            # Check that the receiver email matches the configured PayPal account
            if ipn_obj.receiver_email != context.get("paypal_id"):
                # Not a valid payment - receiver email doesn't match
                notify_admins(
                    "PayPal receiver email mismatch",
                    f"Expected: {context.get('paypal_id')}, Received: {ipn_obj.receiver_email}, Invoice: {ipn_obj.invoice}"
                )
                return None
        except ObjectDoesNotExist:
            notify_admins("PayPal IPN - invoice not found", f"Invoice code: {ipn_obj.invoice}")
            return None

        return invoice_received_money(ipn_obj.invoice, ipn_obj.mc_gross, ipn_obj.mc_fee, ipn_obj.txn_id)
    return None


def handle_invalid_paypal_ipn(invalid_ipn_object: Any) -> None:
    """Handle invalid PayPal IPN notifications.

    Args:
        invalid_ipn_object: Invalid IPN object from PayPal

    """
    if invalid_ipn_object:
        logger.info("PayPal IPN object: %s", invalid_ipn_object)
    # TODO: send mail
    formatted_ipn_body = pformat(invalid_ipn_object)
    logger.info("PayPal IPN body: %s", formatted_ipn_body)
    notify_admins("paypal ko", formatted_ipn_body)


def get_stripe_form(
    request: HttpRequest,
    context: dict[str, Any],
    invoice: PaymentInvoice,
    amount: float,
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
        unit_amount=str(int(round(amount, 2) * CURRENCY_TO_CENTS_MULTIPLIER)),
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
        success_url=request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
        cancel_url=request.build_absolute_uri(reverse("acc_cancelled")),
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
        return invoice_received_money(price_id)
    return True


def get_sumup_form(
    request: HttpRequest,
    context: dict[str, Any],
    invoice: PaymentInvoice,
    amount: float,
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
            "amount": float(amount),
            "currency": context["payment_currency"],
            "merchant_code": context["sumup_merchant_id"],
            "description": invoice.causal,
            # Configure callback URLs for payment flow
            "return_url": request.build_absolute_uri(reverse("acc_webhook_sumup")),
            "redirect_url": request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
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
    expected_success_code = 200
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


def sumup_webhook(request: HttpRequest) -> bool:
    """Handle SumUp webhook notifications for payment processing.

    Processes incoming webhook requests from SumUp payment gateway,
    validates the signature, and triggers invoice payment processing
    for successful transactions.

    Args:
        request: HTTP request object containing webhook payload from SumUp

    Returns:
        bool: True if payment was processed successfully, False if payment
              failed or was not successful

    """
    # Validate webhook signature to prevent unauthorized requests
    signature_header = request.META.get("HTTP_X_SUMUP_SIGNATURE")

    # Get invoice to retrieve association for webhook secret
    try:
        webhook_payload = json.loads(request.body)
        payment_id = webhook_payload["id"]

        # Get invoice to retrieve association context
        invoice = PaymentInvoice.objects.get(cod=payment_id)
        context = {"association_id": invoice.association_id}
        update_payment_details(context)

        # Verify webhook signature if secret is configured
        sumup_webhook_secret = context.get("sumup_webhook_secret")
        if sumup_webhook_secret:
            if not signature_header:
                error_msg = "SumUp webhook signature header missing"
                logger.error(error_msg)
                notify_admins("SumUp webhook security error", error_msg)
                return False

            # Compute expected HMAC-SHA256 signature
            expected_signature = hmac.new(
                sumup_webhook_secret.encode(),
                request.body,
                hashlib.sha256
            ).hexdigest()

            # Verify signature matches
            if not hmac.compare_digest(signature_header, expected_signature):
                error_msg = f"SumUp webhook signature mismatch. Payment ID: {payment_id}"
                logger.error(error_msg)
                notify_admins("SumUp webhook signature verification failed", error_msg)
                return False

        payment_status = webhook_payload["status"]
    except (json.JSONDecodeError, KeyError) as e:
        error_msg = f"Failed to parse SumUp webhook payload: {e}\nBody: {request.body}"
        logger.exception(error_msg)
        notify_admins("SumUp webhook JSON error", error_msg)
        return False
    except ObjectDoesNotExist:
        error_msg = f"SumUp webhook - invoice not found: {payment_id}"
        logger.error(error_msg)  # noqa: TRY400
        notify_admins("SumUp webhook - invalid invoice", error_msg)
        return False

    # Check if the payment status indicates failure or non-success
    if payment_status != "SUCCESSFUL":
        return False

    # Process the successful payment using the transaction ID
    return invoice_received_money(payment_id)


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


def get_redsys_form(request: HttpRequest, context: dict[str, Any], invoice: PaymentInvoice, amount: float) -> None:
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
        "DS_MERCHANT_AMOUNT": float(amount),
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
            "DS_MERCHANT_MERCHANTURL": request.build_absolute_uri(reverse("acc_webhook_redsys")),
            "DS_MERCHANT_URLOK": request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
            "DS_MERCHANT_URLKO": request.build_absolute_uri(reverse("acc_redsys_ko")),
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
        return invoice_received_money(order_code)

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
            "DS_MERCHANT_AMOUNT": int(params["DS_MERCHANT_AMOUNT"] * CURRENCY_TO_CENTS_MULTIPLIER),
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
            error_message = f"Different signature redsys: {signature} vs {computed_signature.decode()}"
            error_message += debug_info

            return notify_admins("Redsys signature verification failed", error_message)

        # Return order number for successful payment processing
        return order_number
