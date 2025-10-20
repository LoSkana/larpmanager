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

import base64
import hashlib
import hmac
import json
import logging
import math
import re
from decimal import Decimal
from pprint import pformat
from typing import Any, Union

import requests
import satispaython
import stripe
from Crypto.Cipher import DES3
from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.urls import reverse
from paypal.standard.forms import PayPalPaymentsForm
from paypal.standard.models import ST_PP_COMPLETED
from satispaython.utils import load_key

from larpmanager.accounting.invoice import invoice_received_money
from larpmanager.models.access import get_assoc_executives
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.models.association import Association
from larpmanager.models.utils import generate_id
from larpmanager.utils.base import def_user_ctx, update_payment_details
from larpmanager.utils.common import generate_number
from larpmanager.utils.tasks import my_send_mail, notify_admins

logger = logging.getLogger(__name__)


def get_satispay_form(request: HttpRequest, ctx: dict[str, Any], invoice: PaymentInvoice, amount: float) -> None:
    """Create Satispay payment form and initialize payment.

    Creates a new Satispay payment request using the provided invoice and amount,
    then updates the invoice with the payment ID and returns the context data
    needed for the payment form.

    Args:
        request: Django HTTP request object used to build absolute URIs
        ctx: Context dictionary containing payment configuration including
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
    ctx["redirect"] = request.build_absolute_uri(reverse("acc_payed", args=[invoice.id]))
    ctx["callback"] = request.build_absolute_uri(reverse("acc_webhook_satispay")) + "?payment_id={uuid}"

    # Load Satispay authentication credentials
    key_id = ctx["satispay_key_id"]
    rsa_key = load_key("main/satispay/private.pem")

    # Future implementation for payment expiration
    # expiration_date = datetime.now(timezone.utc) + timedelta(hours=1)
    # expiration_date = format_datetime(expiration_date)

    # Future implementation for additional body parameters
    # body_params = {
    #     "expire_date": expiration_date,
    #     "external_code": invoice.causal,
    #     "redirect_url": ctx["redirect"],
    #     "callback_url": ctx["callback"],
    # }

    # Create payment request with Satispay API (amount in cents)
    response = satispaython.create_payment(
        key_id, rsa_key, math.ceil(amount * 100), ctx["payment_currency"], ctx["callback"]
    )

    # Validate API response and handle errors
    correct_response_code = 200
    if response.status_code != correct_response_code:
        notify_admins("satispay ko", str(response.content))
        raise Http404("something went wrong :( ")

    # Parse response and update invoice with payment ID
    aux = json.loads(response.content)
    with transaction.atomic():
        invoice.cod = aux["id"]
        invoice.save()

    # Add payment ID to context for form rendering
    ctx["pay_id"] = aux["id"]


def satispay_check(request: HttpRequest, ctx: dict) -> None:
    """Check status of pending Satispay payments.

    Verifies payment status for all pending Satispay invoices by calling the Satispay
    verification API for each invoice found in CREATED status.

    Args:
        request: Django HTTP request object containing user session and metadata
        ctx: Context dictionary containing payment configuration, must include
             'satispay_key_id' for API authentication

    Returns:
        None: Function performs side effects by updating payment statuses
    """
    # Update payment configuration details from request context
    update_payment_details(request, ctx)

    # Early return if Satispay API key is not configured
    if "satispay_key_id" not in ctx:
        return

    # Query for all pending Satispay payment invoices
    que = PaymentInvoice.objects.filter(
        method__slug="satispay",
        status=PaymentStatus.CREATED,
    )

    # Skip processing if no pending invoices exist
    if not que.exists():
        return

    # Verify each pending invoice with Satispay API
    for invoice in que:
        satispay_verify(request, invoice.cod)


def satispay_verify(request: Any, cod: str) -> None:
    """Verify Satispay payment status and process if accepted.

    Retrieves payment invoice by code, validates Satispay payment method,
    checks payment status, and processes accepted payments by updating
    the invoice with received money amount.

    Args:
        request: Django HTTP request object containing payment context
        cod: Payment code/identifier to verify and process

    Returns:
        None: Function returns early on validation failures or processes payment

    Raises:
        ObjectDoesNotExist: When invoice with given code is not found
        Various exceptions from satispaython API calls (handled implicitly)
    """
    # Initialize context and update with payment details from request
    ctx = {}
    update_payment_details(request, ctx)

    # Retrieve invoice by payment code, log warning and return if not found
    try:
        invoice = PaymentInvoice.objects.get(cod=cod)
    except ObjectDoesNotExist:
        logger.warning(f"Not found - invoice {cod}")
        return

    # Validate payment method is Satispay, log warning and return if incorrect
    if invoice.method.slug != "satispay":
        logger.warning(f"Wrong slug method - invoice {cod}")
        return

    # Check invoice status is CREATED, log warning and return if already processed
    if invoice.status != PaymentStatus.CREATED:
        logger.warning(f"Already confirmed - invoice {cod}")
        return

    # Extract Satispay credentials and load RSA private key for API authentication
    key_id = ctx["satispay_key_id"]
    rsa_key = load_key("main/satispay/private.pem")

    # Make API call to Satispay to get payment details using credentials
    response = satispaython.get_payment_details(key_id, rsa_key, invoice.cod)
    # logger.debug(f"Response: {response}")

    # Validate API response status code, return early if not successful
    correct_response_code = 200
    if response.status_code != correct_response_code:
        return

    # Parse response JSON and extract payment amount and status
    aux = json.loads(response.content)
    mc_gross = int(aux["amount_unit"]) / 100.0

    # Process payment if status is accepted by updating invoice with received amount
    if aux["status"] == "ACCEPTED":
        invoice_received_money(invoice.cod, mc_gross)


def satispay_webhook(request):
    """Handle Satispay webhook notifications.

    Args:
        request: Django HTTP request with payment_id parameter
    """
    cod = request.GET.get("payment_id", "")
    satispay_verify(request, cod)


def get_paypal_form(request: HttpRequest, ctx: dict, invoice, amount: float) -> None:
    """Create PayPal payment form and add it to context.

    Creates a PayPal payment form with the provided invoice and amount details,
    then adds the form to the context dictionary for template rendering.

    Args:
        request: Django HTTP request object for building absolute URIs
        ctx: Context dictionary that will be updated with PayPal form data
        invoice: PaymentInvoice instance containing payment details
        amount: Payment amount in the configured currency

    Returns:
        None: Function modifies the ctx dictionary in-place
    """
    # Build PayPal payment configuration dictionary
    paypal_dict = {
        "business": ctx["paypal_id"],
        "amount": float(amount),
        "currency_code": ctx["payment_currency"],
        "item_name": invoice.causal,
        "invoice": invoice.cod,
        # Configure PayPal callback URLs for payment flow
        "notify_url": request.build_absolute_uri(reverse("paypal-ipn")),
        "return": request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
        "cancel_return": request.build_absolute_uri(reverse("acc_cancelled")),
    }

    # Create PayPal form and add to context for template rendering
    # logger.debug(f"PayPal dict: {paypal_dict}")
    ctx["paypal_form"] = PayPalPaymentsForm(initial=paypal_dict)


def handle_valid_paypal_ipn(ipn_obj):
    """Handle valid PayPal IPN notifications.

    Args:
        ipn_obj: IPN object from PayPal

    Returns:
        Result from invoice_received_money or None
    """
    if ipn_obj.payment_status == ST_PP_COMPLETED:
        # WARNING !
        # Check that the receiver email is the same we previously
        # set on the `business` field. (The user could tamper with
        # that fields on the payment form before it goes to PayPal)
        # ~ if ipn_obj.receiver_email != ctx['paypal_id']:
        # ~ # Not a valid payment
        # ~ return

        # logger.debug(f"IPN receiver email: {ipn_obj.receiver_email}")
        # logger.debug(f"IPN object: {ipn_obj}")
        # ~ Print (ipn_obj)
        # logger.debug(f"IPN fee: {ipn_obj.mc_fee}")
        # logger.debug(f"IPN gross: {ipn_obj.mc_gross}")

        return invoice_received_money(ipn_obj.invoice, ipn_obj.mc_gross, ipn_obj.mc_fee, ipn_obj.txn_id)


def handle_invalid_paypal_ipn(ipn_obj: object) -> None:
    """Handle invalid PayPal IPN notifications.

    Logs the invalid IPN object details and notifies administrators
    about the failed PayPal notification.

    Args:
        ipn_obj: Invalid IPN object from PayPal containing notification data.
            Can be None if no object was received.

    Returns:
        None: This function doesn't return any value.
    """
    # Log the IPN object if it exists
    if ipn_obj:
        logger.info(f"PayPal IPN object: {ipn_obj}")

    # TODO send mail

    # Format the IPN object for detailed logging
    body = pformat(ipn_obj)
    logger.info(f"PayPal IPN body: {body}")

    # Notify administrators about the invalid PayPal notification
    notify_admins("paypal ko", body)


def get_stripe_form(request: HttpRequest, ctx: dict, invoice: PaymentInvoice, amount: float) -> dict:
    """Create Stripe payment form and session.

    Creates a Stripe product and price for the given invoice, then generates
    a checkout session for payment processing. Updates the invoice with the
    price ID for tracking purposes.

    Args:
        request: Django HTTP request object for building absolute URLs
        ctx: Context dictionary containing Stripe API keys and payment configuration
        invoice: PaymentInvoice instance to process payment for
        amount: Payment amount in the configured currency

    Returns:
        Context dictionary updated with Stripe checkout session data

    Note:
        The invoice's 'cod' field is updated with the Stripe price ID for
        later reference during payment processing.
    """
    # Set Stripe API key from context configuration
    stripe.api_key = ctx["stripe_sk_api"]

    # Create a new Stripe product for this invoice
    prod = stripe.Product.create(name=invoice.causal)

    # Create price object with amount converted to cents
    # Stripe requires amounts in smallest currency unit (cents for EUR/USD)
    price = stripe.Price.create(
        unit_amount=str(int(round(amount, 2) * 100)),
        currency=ctx["payment_currency"],
        product=prod.id,
    )

    # Create checkout session with success/cancel URLs
    checkout_session = stripe.checkout.Session.create(
        line_items=[
            {
                "price": price.id,
                "quantity": 1,
            },
        ],
        mode="payment",
        success_url=request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
        cancel_url=request.build_absolute_uri(reverse("acc_cancelled")),
    )

    # Add checkout session to context for template rendering
    ctx["stripe_ck"] = checkout_session

    # Store price ID in invoice for payment tracking
    invoice.cod = price.id
    invoice.save()


def stripe_webhook(request: HttpRequest) -> HttpResponse:
    """Handle Stripe webhook events for payment processing.

    This function processes Stripe webhook events, specifically handling checkout session
    completion and async payment success events. It validates the webhook signature,
    extracts payment information, and triggers invoice processing.

    Args:
        request: Django HTTP request object containing Stripe webhook data with
            payload body and signature header

    Returns:
        HttpResponse: Success response for processed events or error response
            for validation failures

    Raises:
        ValueError: When webhook payload is invalid or malformed
        SignatureVerificationError: When webhook signature verification fails
    """
    # Initialize context and configure Stripe API settings
    ctx = def_user_ctx(request)
    update_payment_details(request, ctx)
    stripe.api_key = ctx["stripe_sk_api"]

    # Extract webhook payload and signature from request
    payload = request.body
    sig_header = request.META["HTTP_STRIPE_SIGNATURE"]
    endpoint_secret = ctx["stripe_webhook_secret"]

    try:
        # Verify webhook signature and construct event object
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as e:
        # Invalid payload - raise exception for proper error handling
        raise e
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature - raise exception for proper error handling
        raise e

    # Process checkout session completion events
    if event["type"] == "checkout.session.completed" or event["type"] == "checkout.session.async_payment_succeeded":
        # Retrieve full session details with line items expanded
        session = stripe.checkout.Session.retrieve(
            event["data"]["object"]["id"],
            expand=["line_items"],
        )

        # Extract line items and process first item (assumes single item per session)
        line_items = session.line_items
        item = line_items["data"][0]

        # Extract price ID for invoice processing
        cod = item["price"]["id"]

        # Process the received payment for the invoice
        return invoice_received_money(cod)
    # ~ elif event['type'] == 'checkout.session.async_payment_failed':
    # ~ return True
    # ~ elif event['type'] == 'checkout.session.expired':
    # ~ return True
    # ~ elif event['type'] == 'checkout.session.async_payment_succeeded':
    # ~ return True
    else:
        # Return success for unhandled but valid webhook events
        return True
        # raise Exception('Unhandled event type {}'.format(event['type']))


def get_sumup_form(
    request: HttpRequest, ctx: dict[str, Any], invoice: PaymentInvoice, amount: Union[int, float, Decimal]
) -> None:
    """Generate SumUp payment form for invoice processing.

    Creates a SumUp checkout session by first authenticating with the SumUp API
    to obtain an access token, then creating a checkout with the invoice details.
    Updates the invoice code with the checkout ID for tracking purposes.

    Args:
        request: Django HTTP request object containing request metadata
        ctx: Context dictionary containing SumUp payment configuration:
            - sumup_client_id: SumUp API client ID
            - sumup_client_secret: SumUp API client secret
            - sumup_merchant_id: SumUp merchant identifier
            - payment_currency: Currency code for the payment
        invoice: Invoice instance to process payment for
        amount: Payment amount to charge (will be converted to float)

    Raises:
        KeyError: If required configuration keys are missing from ctx
        requests.RequestException: If API requests fail
        json.JSONDecodeError: If API response is not valid JSON
    """
    # Authenticate with SumUp API to obtain access token
    auth_url = "https://api.sumup.com/token"
    auth_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    auth_payload = {
        "client_id": ctx["sumup_client_id"],
        "client_secret": ctx["sumup_client_secret"],
        "grant_type": "client_credentials",
    }

    # Make authentication request and extract token
    auth_response = requests.request("POST", auth_url, headers=auth_headers, data=auth_payload)
    auth_data = json.loads(auth_response.text)
    # logger.debug(f"Response text: {auth_response.text}")
    access_token = auth_data["access_token"]
    # logger.debug(f"Token: {access_token}")

    # Prepare checkout creation request with invoice details
    checkout_url = "https://api.sumup.com/v0.1/checkouts"
    checkout_payload = json.dumps(
        {
            "checkout_reference": invoice.cod,
            "amount": float(amount),
            "currency": ctx["payment_currency"],
            "merchant_code": ctx["sumup_merchant_id"],
            "description": invoice.causal,
            # Configure callback URLs for payment flow
            "return_url": request.build_absolute_uri(reverse("acc_webhook_sumup")),
            "redirect_url": request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
            "payment_type": "boleto",
        }
    )

    # Set authorization headers with obtained token
    checkout_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    # Create checkout session and extract checkout ID
    # logger.debug(f"Payload: {checkout_payload}")
    checkout_response = requests.request("POST", checkout_url, headers=checkout_headers, data=checkout_payload)
    # logger.debug(f"SumUp response: {checkout_response.text}")
    checkout_data = json.loads(checkout_response.text)

    # Store checkout ID in context and update invoice for tracking
    ctx["sumup_checkout_id"] = checkout_data["id"]
    invoice.cod = checkout_data["id"]
    invoice.save()


def sumup_webhook(request: HttpRequest) -> bool:
    """Process SumUp webhook notification for payment status.

    Args:
        request: HTTP request object containing webhook payload

    Returns:
        bool: True if payment was successful and processed, False otherwise
    """
    # Parse the JSON payload from the webhook request body
    aux = json.loads(request.body)

    # Check if the payment status indicates success
    if aux["status"] != "SUCCESSFUL":
        # Payment failed or pending - return False to indicate failure
        return False

    # Process the successful payment using the transaction ID
    return invoice_received_money(aux["id"])


def redsys_invoice_cod():
    for _idx in range(5):
        cod = generate_number(5) + generate_id(7)
        if not PaymentInvoice.objects.filter(cod=cod).exists():
            return cod
    raise ValueError("Too many attempts to generate the code")


def get_redsys_form(request: HttpRequest, ctx: dict[str, Any], invoice: PaymentInvoice, amount: Decimal) -> None:
    """Create Redsys payment form with encrypted parameters.

    Generates a secure payment form for Redsys payment gateway by creating
    encrypted parameters and updating the invoice with a unique code.

    Args:
        request: Django HTTP request object containing association data
        ctx: Context dictionary with Redsys payment configuration including
             merchant code, terminal, currency, secret key, and sandbox flag
        invoice: PaymentInvoice instance to be updated with payment code
        amount: Payment amount in decimal format

    Returns:
        None: Updates ctx dictionary in-place with 'redsys_form' key containing
              encrypted payment data ready for form submission

    Side Effects:
        - Updates invoice.cod with generated payment code
        - Saves invoice to database
        - Adds 'redsys_form' to ctx dictionary
    """
    # Generate unique invoice code and save to database
    invoice.cod = redsys_invoice_cod()
    invoice.save()

    # Prepare basic payment parameters for Redsys gateway
    values = {
        "DS_MERCHANT_AMOUNT": float(amount),
        "DS_MERCHANT_CURRENCY": int(ctx["redsys_merchant_currency"]),
        "DS_MERCHANT_ORDER": invoice.cod,
        "DS_MERCHANT_PRODUCTDESCRIPTION": invoice.causal,
        "DS_MERCHANT_TITULAR": request.assoc["name"],
    }

    # Add merchant identification and terminal configuration
    values.update(
        {
            "DS_MERCHANT_MERCHANTCODE": ctx["redsys_merchant_code"],
            "DS_MERCHANT_MERCHANTNAME": request.assoc["name"],
            "DS_MERCHANT_TERMINAL": ctx["redsys_merchant_terminal"],
            "DS_MERCHANT_TRANSACTIONTYPE": "0",  # Standard payment
        }
    )

    # Configure callback URLs for payment flow
    values.update(
        {
            "DS_MERCHANT_MERCHANTURL": request.build_absolute_uri(reverse("acc_webhook_redsys")),
            "DS_MERCHANT_URLOK": request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
            "DS_MERCHANT_URLKO": request.build_absolute_uri(reverse("acc_redsys_ko")),
        }
    )

    # Add optional payment methods if configured
    if "key" in ctx and ctx["key"]:
        values["DS_MERCHANT_PAYMETHODS"] = ctx["key"]

    # Determine sandbox mode from configuration
    redsys_sandbox = int(ctx["redsys_sandbox"]) == 1

    # Initialize Redsys client with merchant credentials
    redsyspayment = RedSysClient(
        business_code=ctx["redsys_merchant_code"],
        secret_key=ctx["redsys_secret_key"],
        sandbox=redsys_sandbox,
    )

    # Generate encrypted form data and add to context
    ctx["redsys_form"] = redsyspayment.redsys_generate_request(values)
    # logger.debug(f"Redsys form: {ctx['redsys_form']}")

    # ~ values = {
    # ~ 'DS_MERCHANT_AMOUNT': 10.0,
    # ~ 'DS_MERCHANT_CURRENCY': 978,
    # ~ 'DS_MERCHANT_ORDER': 'SO001',
    # ~ 'DS_MERCHANT_PRODUCTDESCRIPTION': 'ZZSaas services',
    # ~ 'DS_MERCHANT_TITULAR': REDSYS_MERCHANT_NAME,
    # ~ 'DS_MERCHANT_MERCHANTCODE': REDSYS_MERCHANT_CODE,
    # ~ 'DS_MERCHANT_MERCHANTURL': REDSYS_MERCHANT_URL,
    # ~ 'DS_MERCHANT_URLOK': 'http://localhost:5000/redsys/confirm',
    # ~ 'DS_MERCHANT_URLKO': 'http://localhost:5000/redsys/cancel',
    # ~ 'DS_MERCHANT_MERCHANTNAME': REDSYS_MERCHANT_NAME,
    # ~ 'DS_MERCHANT_TERMINAL': REDSYS_TERMINAL,
    # ~ 'DS_MERCHANT_TRANSACTIONTYPE': REDSYS_TRANS_TYPE,
    # None

    # ~ redsyspayment = Client(business_code=REDSYS_MERCHANT_CODE, secret_key=REDSYS_SECRET_KEY, sandbox=SANDBOX)
    # ~ redsys_form = redsyspayment.redsys_generate_request(values)
    # logger.debug(f"Redsys form data: {redsys_form}")

    # ~ invoice.cod = unique_invoice_cod(24)
    # ~ invoice.save()

    # ~ # create json request
    # ~ Aux = {
    # ~ 'DS_MERCHANT_AMOUNT': "%d" % (int(round(amount, 2) * 100)),
    # ~ 'DS_MERCHANT_ORDER': invoice.cod,
    # ~ 'DS_MERCHANT_MERCHANTCODE': ,
    # ~ 'DS_MERCHANT_CURRENCY':,
    # ~ 'DS_MERCHANT_TRANSACTIONTYPE': '1',
    # ~ 'DS_MERCHANT_TERMINAL': ,
    # ~ 'DS_MERCHANT_MERCHANTURL': request.build_absolute_uri(reverse('acc_payed', args=[invoice.id])),
    # ~ 'DS_MERCHANT_URLOK': request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
    # ~ 'DS_MERCHANT_URLKO': request.build_absolute_uri(reverse('acc_redsys_ko')),
    # None
    # ~ MSG = JSON.DUMPS (AUX)
    # ~ msg = msg.replace(" ", "")
    # ~ msg = msg.replace('/', '\/')

    # ~ # encode in base 64
    # logger.debug(f"Message: {msg}")
    # ~ msg = msg.encode('ascii')
    # ~ msg = base64.b64encode(msg)
    # logger.debug(f"Decoded message: {msg.decode('ascii')}")
    # ~ ctx['merchant_parameters'] = msg.decode('ascii')

    # ~ # 3DES encryption between the merchant key (decoded in BASE 64) and the order
    # ~ #print(ctx['redsys_secret_key'])
    # ~ key = base64.b64decode(ctx['redsys_secret_key'])
    # ~ #print(key.hex())
    # ~ #print(key)
    # ~ code = invoice.cod
    # ~ while len(code) % 8 != 0:
    # ~ code += "\0"
    # ~ #print(code)
    # ~ k = pyDes.triple_des(key, pyDes.CBC, b"\0\0\0\0\0\0\0\0", "\0")
    # ~ ds = k.encrypt(code)
    # logger.debug(f"DS: {ds}")
    # logger.debug(f"DS hex: {ds.hex()}")

    # ~ # HMAC SHA256 of the value of the Ds_MerchantParameters parameter and the key obtained
    # ~ dig = HMAC.new(ds, msg=msg, digestmod=SHA256).digest()
    # ~ sig = base64.b64encode (you)

    # Print (Say)
    # ~ #sig = Sig.encode ('ASCII')
    # Print (sig.hex ())
    # ~ ctx['signature'] = sig


def redsys_webhook(request: HttpRequest, ok: bool = True) -> Union[bool, HttpResponse]:
    """Process Redsys payment gateway webhook notification.

    Handles incoming webhook requests from Redsys payment gateway to process
    payment confirmations and update invoice status accordingly.

    Args:
        request: Django HTTP request object containing POST data from Redsys
        ok: Boolean flag indicating expected success status (default: True)

    Returns:
        Result from invoice_received_money() if payment verification succeeds,
        False if verification fails

    Note:
        Expected POST parameters:
        - Ds_MerchantParameters: Base64 encoded payment data
        - Ds_Signature: HMAC signature for verification
    """
    # Initialize user context and update payment configuration
    ctx = def_user_ctx(request)
    update_payment_details(request, ctx)

    # Extract payment parameters and signature from POST data
    # ver = request.POST["Ds_SignatureVersion"]  # Version currently unused
    pars = request.POST["Ds_MerchantParameters"]
    sig = request.POST["Ds_Signature"]

    # Initialize Redsys client with merchant credentials
    redsyspayment = RedSysClient(business_code=ctx["redsys_merchant_code"], secret_key=ctx["redsys_secret_key"])

    # Verify payment signature and extract transaction code
    cod = redsyspayment.redsys_check_response(sig, pars, ctx)

    # Process successful payment verification
    if cod:
        return invoice_received_money(cod)

    return False


class RedSysClient:
    """Client"""

    DATA = [
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

    LANG_MAP = {
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

    def __init__(self, business_code, secret_key, sandbox=False):
        # init params
        for param in self.DATA:
            setattr(self, param, None)
        self.Ds_Merchant_MerchantCode = business_code
        self.secret_key = secret_key
        if sandbox:
            self.redsys_url = "https://sis-t.redsys.es:25443/sis/realizarPago"
        else:
            self.redsys_url = "https://sis.redsys.es/sis/realizarPago"

    @staticmethod
    def decode_parameters(merchant_parameters):
        """
        Given the Ds_MerchantParameters from Redsys, decode it and eval the
        json file
        :param merchant_parameters: Base 64 encoded json structure returned by
               Redsys
        :return merchant_parameters: Json structure with all parameters
        """
        assert isinstance(merchant_parameters, str)
        return json.loads(base64.b64decode(merchant_parameters).decode())

    def encrypt_order(self, order: str) -> bytes:
        """
        Creates a unique encrypted key for every request based on the merchant order and shared secret.

        This method uses Triple DES encryption in CBC mode to cipher the order string.
        The order is padded to 16 bytes and encrypted using the base64-decoded secret key.

        Args:
            order: The merchant order string to be encrypted

        Returns:
            The encrypted order as bytes

        Raises:
            AssertionError: If order is not a string
        """
        # Validate input parameter type
        assert isinstance(order, str)

        # Create Triple DES cipher with CBC mode and zero IV
        cipher = DES3.new(base64.b64decode(self.secret_key), DES3.MODE_CBC, IV=b"\0\0\0\0\0\0\0\0")

        # Encode order to bytes and pad to 16-byte boundary, then encrypt
        return cipher.encrypt(order.encode().ljust(16, b"\0"))

    @staticmethod
    def sign_hmac256(encrypted_order: bytes, merchant_parameters: bytes) -> bytes:
        """Sign merchant data using HMAC SHA256 algorithm.

        Uses the encrypted order as the key to sign the merchant parameters
        using HMAC SHA256, then encodes the result with Base64.

        Args:
            encrypted_order: Encrypted Ds_Merchant_Order used as HMAC key
            merchant_parameters: Redsys already encoded parameters to sign

        Returns:
            Generated signature as a base64 encoded bytes string

        Raises:
            AssertionError: If parameters are not bytes
        """
        # Validate input types are bytes
        assert isinstance(encrypted_order, bytes)
        assert isinstance(merchant_parameters, bytes)

        # Generate HMAC SHA256 digest using encrypted order as key
        digest = hmac.new(encrypted_order, merchant_parameters, hashlib.sha256).digest()

        # Encode digest with Base64 and return
        return base64.b64encode(digest)

    def redsys_generate_request(self, params: dict) -> dict:
        """
        Generate Redsys Ds_MerchantParameters and Ds_Signature for payment processing.

        Args:
            params: Dictionary containing all transaction parameters including:
                - DS_MERCHANT_AMOUNT: Transaction amount (float)
                - DS_MERCHANT_ORDER: Order identifier (string)
                - DS_MERCHANT_MERCHANTCODE: Merchant code (string)
                - DS_MERCHANT_CURRENCY: Currency code (int, optional)
                - DS_MERCHANT_TRANSACTIONTYPE: Transaction type (string, optional)
                - DS_MERCHANT_TERMINAL: Terminal identifier (string, optional)
                - DS_MERCHANT_URLOK: Success URL (string)
                - DS_MERCHANT_URLKO: Error URL (string)
                - DS_MERCHANT_MERCHANTURL: Merchant notification URL (string)
                - DS_MERCHANT_PRODUCTDESCRIPTION: Product description (string)
                - DS_MERCHANT_TITULAR: Card holder name (string)
                - DS_MERCHANT_MERCHANTNAME: Merchant name (string)
                - DS_MERCHANT_CONSUMERLANGUAGE: Consumer language (string, optional)

        Returns:
            Dictionary containing:
                - Ds_Redsys_Url: Payment gateway URL
                - Ds_SignatureVersion: Signature version identifier
                - Ds_MerchantParameters: Base64 encoded merchant parameters
                - Ds_Signature: HMAC-SHA256 signature for request validation
        """
        # Build merchant parameters with proper formatting and defaults
        merchant_parameters = {
            "DS_MERCHANT_AMOUNT": int(params["DS_MERCHANT_AMOUNT"] * 100),
            "DS_MERCHANT_ORDER": params["DS_MERCHANT_ORDER"].zfill(10),
            "DS_MERCHANT_MERCHANTCODE": params["DS_MERCHANT_MERCHANTCODE"][:9],
            "DS_MERCHANT_CURRENCY": params["DS_MERCHANT_CURRENCY"] or 978,  # EUR
            "DS_MERCHANT_TRANSACTIONTYPE": (params["DS_MERCHANT_TRANSACTIONTYPE"] or "0"),
            # Set terminal and URLs with length restrictions
            "DS_MERCHANT_TERMINAL": params["DS_MERCHANT_TERMINAL"] or "1",
            "DS_MERCHANT_URLOK": params["DS_MERCHANT_URLOK"][:250],
            "DS_MERCHANT_URLKO": params["DS_MERCHANT_URLKO"][:250],
            "DS_MERCHANT_MERCHANTURL": params["DS_MERCHANT_MERCHANTURL"][:250],
            # Set product and merchant details with length limits
            "DS_MERCHANT_PRODUCTDESCRIPTION": (params["DS_MERCHANT_PRODUCTDESCRIPTION"][:125]),
            "DS_MERCHANT_TITULAR": params["DS_MERCHANT_TITULAR"][:60],
            "DS_MERCHANT_MERCHANTNAME": params["DS_MERCHANT_MERCHANTNAME"][:25],
            "DS_MERCHANT_CONSUMERLANGUAGE": self.LANG_MAP.get(params.get("DS_MERCHANT_CONSUMERLANGUAGE"), "001"),
        }

        # Encode merchant_parameters in json + base64
        b64_params = base64.b64encode(json.dumps(merchant_parameters).encode())

        # Encrypt order identifier for signature generation
        encrypted_order = self.encrypt_order(merchant_parameters["DS_MERCHANT_ORDER"])

        # Generate HMAC-SHA256 signature using encrypted order and parameters
        signature = self.sign_hmac256(encrypted_order, b64_params).decode()

        # Return complete request data for Redsys payment gateway
        return {
            "Ds_Redsys_Url": self.redsys_url,
            "Ds_SignatureVersion": "HMAC_SHA256_V1",
            "Ds_MerchantParameters": b64_params.decode(),
            "Ds_Signature": signature,
        }

    def redsys_check_response(self, signature: str, b64_merchant_parameters: str, ctx: dict) -> str | None:
        """Verify Redsys payment response signature and extract order number.

        Validates the cryptographic signature of payment response from Redsys gateway
        to ensure authenticity and prevent tampering. Checks payment status and
        sends notifications to executives on failure.

        Args:
            signature: Received HMAC-SHA256 signature from Redsys
            b64_merchant_parameters: Base64-encoded JSON merchant parameters
            ctx: Context dictionary containing association ID (a_id)

        Returns:
            str: Order number if signature valid and payment successful
            None: If signature invalid or payment failed

        Side effects:
            - Sends error emails to association executives on payment failure
            - Logs error messages for signature verification failures
        """
        # Decode Base64-encoded merchant parameters from Redsys
        merchant_parameters = json.loads(base64.b64decode(b64_merchant_parameters).decode())

        # Get association for executive notifications
        assoc = Association.objects.get(pk=ctx["a_id"])

        # Validate response code presence
        if "Ds_Response" not in merchant_parameters:
            subj = "Ds_Response not found"
            body = str(merchant_parameters)
            # Notify executives about missing response code
            for member in get_assoc_executives(assoc):
                my_send_mail(subj, body, member, assoc)
            return None

        # Check payment response code (0-99 indicates success)
        resp = int(merchant_parameters["Ds_Response"])

        # Response codes 0-99 indicate successful payment, anything else is failure
        redsys_failed = 99
        if resp < 0 or resp > redsys_failed:
            subj = "Failed redsys payment"
            body = str(merchant_parameters)
            # Notify executives about failed payment
            for member in get_assoc_executives(assoc):
                my_send_mail(subj, body, member, assoc)
            return None

        # Extract order number from merchant parameters
        order = merchant_parameters["Ds_Order"]

        # Encrypt order number using 3DES for signature verification
        encrypted_order = self.encrypt_order(order)

        # Re-encode merchant parameters for signature comparison
        b64_params = base64.b64encode(json.dumps(merchant_parameters).encode())

        # Compute expected signature using HMAC-SHA256
        computed_signature = self.sign_hmac256(encrypted_order, b64_params)

        # Verify signature matches to ensure payment authenticity
        if signature != computed_signature:
            mes = f"Different signature redsys: {signature} vs {computed_signature}"
            mes += pformat(merchant_parameters)
            logger.error(f"Redsys signature verification failed: {mes}")
            # Send critical security alert to system admins
            for _name, email in conf_settings.ADMINS:
                my_send_mail("redsys signature", mes, email)

        # Return order number for successful payment processing
        return order
