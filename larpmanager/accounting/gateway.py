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
from django.http import Http404, HttpRequest
from django.urls import reverse
from paypal.standard.forms import PayPalPaymentsForm
from paypal.standard.models import ST_PP_COMPLETED
from satispaython.utils import load_key

from larpmanager.accounting.invoice import invoice_received_money
from larpmanager.models.access import get_association_executives
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.models.association import Association
from larpmanager.models.utils import generate_id
from larpmanager.utils.base import get_context, update_payment_details
from larpmanager.utils.common import generate_number
from larpmanager.utils.tasks import my_send_mail, notify_admins

logger = logging.getLogger(__name__)


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
    # expiration_date = datetime.now(timezone.utc) + timedelta(hours=1)
    # expiration_date = format_datetime(expiration_date)

    # Prepare body parameters with callback URL
    body_params = {
        "callback_url": context["callback"],
        "redirect_url": context["redirect"],
        "external_code": invoice.causal
    }
    # Optional
    # body_params["expire_date"] = expiration_date

    # Create payment request with Satispay API (amount in cents)
    satispay_response = satispaython.create_payment(
        satispay_key_id, satispay_rsa_key, math.ceil(amount * 100), context["payment_currency"], body_params
    )

    # Validate API response and handle errors
    expected_success_status_code = 200
    if satispay_response.status_code != expected_success_status_code:
        notify_admins("satispay ko", str(satispay_response.content))
        raise Http404("something went wrong :( ")

    # Parse response and update invoice with payment ID
    response_data = json.loads(satispay_response.content)
    with transaction.atomic():
        invoice.cod = response_data["id"]
        invoice.save()

    # Add payment ID to context for form rendering
    context["pay_id"] = response_data["id"]


def satispay_check(request, context):
    """Check status of pending Satispay payments.

    Args:
        request: Django HTTP request object
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
        logger.warning(f"Not found - invoice {payment_code}")
        return

    # Validate that invoice uses Satispay payment method
    if invoice.method.slug != "satispay":
        logger.warning(f"Wrong slug method - invoice {payment_code}")
        return

    # Check if payment is still in created status (not already processed)
    if invoice.status != PaymentStatus.CREATED:
        logger.warning(f"Already confirmed - invoice {payment_code}")
        return

    # Load Satispay API credentials and private key for authentication
    key_id = context["satispay_key_id"]
    rsa_key = load_key("main/satispay/private.pem")

    # Make API call to Satispay to get current payment status
    response = satispaython.get_payment_details(key_id, rsa_key, invoice.cod)
    # logger.debug(f"Response: {response}")

    # Validate API response status code
    expected_success_code = 200
    if response.status_code != expected_success_code:
        return

    # Parse response and extract payment details
    payment_data = json.loads(response.content)
    payment_amount = int(payment_data["amount_unit"]) / 100.0

    # Process payment if Satispay marked it as accepted
    if payment_data["status"] == "ACCEPTED":
        invoice_received_money(invoice.cod, payment_amount)


def satispay_webhook(request):
    """Handle Satispay webhook notifications.

    Args:
        request: Django HTTP request with payment_id parameter
    """
    payment_id = request.GET.get("payment_id", "")
    context = get_context(request)
    satispay_verify(context, payment_id)


def get_paypal_form(request, context, invoice, amount):
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
    # logger.debug(f"PayPal dict: {paypal_payment_data}")
    context["paypal_form"] = PayPalPaymentsForm(initial=paypal_payment_data)


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
        # ~ if ipn_obj.receiver_email != context['paypal_id']:
        # ~ # Not a valid payment
        # ~ return

        # logger.debug(f"IPN receiver email: {ipn_obj.receiver_email}")
        # logger.debug(f"IPN object: {ipn_obj}")
        # ~ Print (ipn_obj)
        # logger.debug(f"IPN fee: {ipn_obj.mc_fee}")
        # logger.debug(f"IPN gross: {ipn_obj.mc_gross}")

        return invoice_received_money(ipn_obj.invoice, ipn_obj.mc_gross, ipn_obj.mc_fee, ipn_obj.txn_id)


def handle_invalid_paypal_ipn(invalid_ipn_object):
    """Handle invalid PayPal IPN notifications.

    Args:
        invalid_ipn_object: Invalid IPN object from PayPal
    """
    if invalid_ipn_object:
        logger.info(f"PayPal IPN object: {invalid_ipn_object}")
    # TODO send mail
    formatted_ipn_body = pformat(invalid_ipn_object)
    logger.info(f"PayPal IPN body: {formatted_ipn_body}")
    notify_admins("paypal ko", formatted_ipn_body)


def get_stripe_form(request, context: dict, invoice, amount: float) -> None:
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
        unit_amount=str(int(round(amount, 2) * 100)),
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


def stripe_webhook(request):
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

    try:
        event = stripe.Webhook.construct_event(payload, signature_header, endpoint_secret)
    except ValueError as error:
        # Invalid payload
        raise error
    except stripe.error.SignatureVerificationError as error:
        # Invalid signature
        raise error

    # Handle the event
    if event["type"] == "checkout.session.completed" or event["type"] == "checkout.session.async_payment_succeeded":
        session = stripe.checkout.Session.retrieve(
            event["data"]["object"]["id"],
            expand=["line_items"],
        )

        line_items = session.line_items
        # assume only one
        first_line_item = line_items["data"][0]
        # logger.debug(f"Processing item: {first_line_item}")
        price_id = first_line_item["price"]["id"]
        # logger.debug(f"Code: {price_id}")
        return invoice_received_money(price_id)
    # ~ elif event['type'] == 'checkout.session.async_payment_failed':
    # ~ return True
    # ~ elif event['type'] == 'checkout.session.expired':
    # ~ return True
    # ~ elif event['type'] == 'checkout.session.async_payment_succeeded':
    # ~ return True
    else:
        return True
        # raise Exception('Unhandled event type {}'.format(event['type']))


def get_sumup_form(
    request: HttpRequest, context: dict[str, Any], invoice: PaymentInvoice, amount: Union[int, float, Decimal]
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
        "POST", authentication_url, headers=authentication_headers, data=authentication_payload
    )
    authentication_response_data = json.loads(authentication_response.text)
    # logger.debug(f"Response text: {authentication_response.text}")
    access_token = authentication_response_data["access_token"]
    # logger.debug(f"Token: {access_token}")

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
    checkout_response_data = json.loads(checkout_response.text)

    # Store checkout ID in context and update invoice for tracking
    context["sumup_checkout_id"] = checkout_response_data["id"]
    invoice.cod = checkout_response_data["id"]
    invoice.save()


def sumup_webhook(request: HttpRequest) -> bool:
    """Handle SumUp webhook notifications for payment processing.

    Processes incoming webhook requests from SumUp payment gateway,
    validates the payment status, and triggers invoice payment processing
    for successful transactions.

    Args:
        request: HTTP request object containing webhook payload from SumUp

    Returns:
        bool: True if payment was processed successfully, False if payment
              failed or was not successful
    """
    # Print (Request)
    # pprint(request.body)
    # Print (Request.Meta)

    # Parse the JSON payload from the webhook request body
    webhook_payload = json.loads(request.body)
    # print (at ['id'])
    # print (at ['status'])

    # Check if the payment status indicates failure or non-success
    if webhook_payload["status"] != "SUCCESSFUL":
        # Err_Paypal (Print (Request) + Print (Request.Body) + Print (Request.meta))
        return False

    # Process the successful payment using the transaction ID
    return invoice_received_money(webhook_payload["id"])


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
    raise ValueError("Too many attempts to generate the code")


def get_redsys_form(request: HttpRequest, context: dict[str, Any], invoice: PaymentInvoice, amount: Decimal) -> None:
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
        }
    )

    # Configure callback URLs for payment flow
    payment_parameters.update(
        {
            "DS_MERCHANT_MERCHANTURL": request.build_absolute_uri(reverse("acc_webhook_redsys")),
            "DS_MERCHANT_URLOK": request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
            "DS_MERCHANT_URLKO": request.build_absolute_uri(reverse("acc_redsys_ko")),
        }
    )

    # Add optional payment methods if configured
    if "key" in context and context["key"]:
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
    # logger.debug(f"Redsys form: {context['redsys_form']}")

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
    # ~ context['merchant_parameters'] = msg.decode('ascii')

    # ~ # 3DES encryption between the merchant key (decoded in BASE 64) and the order
    # ~ #print(context['redsys_secret_key'])
    # ~ key = base64.b64decode(context['redsys_secret_key'])
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
    # ~ context['signature'] = sig


def redsys_webhook(request, ok: bool = True) -> bool:
    """Handle RedSys payment webhook notifications.

    Processes incoming webhook requests from RedSys payment gateway,
    validates the signature, and updates payment status accordingly.

    Args:
        request: Django HTTP request object containing webhook data
        ok: Boolean flag indicating expected success state (default: True)

    Returns:
        bool: True if payment was successfully processed, False otherwise
    """
    # Initialize user context and update payment details
    context = get_context(request)
    update_payment_details(context)

    # Extract RedSys parameters and signature from POST data
    # signature_version = request.POST["Ds_SignatureVersion"]  # Version not currently used
    merchant_parameters = request.POST["Ds_MerchantParameters"]
    signature = request.POST["Ds_Signature"]

    # Initialize RedSys client with merchant credentials
    redsys_payment_client = RedSysClient(
        business_code=context["redsys_merchant_code"], secret_key=context["redsys_secret_key"]
    )

    # Validate the webhook signature and extract order code
    order_code = redsys_payment_client.redsys_check_response(signature, merchant_parameters, context)

    # Process successful payment if signature validation passed
    if order_code:
        return invoice_received_money(order_code)

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

    def __init__(self, business_code: str, secret_key: str, sandbox: bool = False) -> None:
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

    def encrypt_order(self, order):
        """
        This method creates a unique key for every request, based on the
        Ds_Merchant_Order and in the shared secret (SERMEPA_SECRET_KEY).
        This unique key is Triple DES ciphered.
        :param Ds_Merchant_Order: dict with all merchant parameters
        :return  order_encrypted: The encrypted order
        """
        assert isinstance(order, str)
        initialization_vector = b"\0\0\0\0\0\0\0\0"
        decoded_secret_key = base64.b64decode(self.secret_key)
        triple_des_cipher = DES3.new(decoded_secret_key, DES3.MODE_CBC, IV=initialization_vector)
        padded_order = order.encode().ljust(16, b"\0")
        return triple_des_cipher.encrypt(padded_order)

    @staticmethod
    def sign_hmac256(encrypted_order, merchant_parameters):
        """
        Use the encrypted_order we have to sign the merchant data using
        a HMAC SHA256 algorithm and encode the result using Base64.
        :param encrypted_order: Encrypted Ds_Merchant_Order
        :param merchant_parameters: Redsys already encoded parameters
        :return Generated signature as a base64 encoded string
        """
        assert isinstance(encrypted_order, bytes)
        assert isinstance(merchant_parameters, bytes)
        hmac_signature = hmac.new(encrypted_order, merchant_parameters, hashlib.sha256).digest()
        return base64.b64encode(hmac_signature)

    def redsys_generate_request(self, params):
        """
        Method to generate Redsys Ds_MerchantParameters and Ds_Signature
        :param params: dict with all transaction parameters
        :return dict url, signature, parameters and type signature
        """
        merchant_parameters = {
            "DS_MERCHANT_AMOUNT": int(params["DS_MERCHANT_AMOUNT"] * 100),
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
        merchant_parameters = json.loads(base64.b64decode(b64_merchant_parameters).decode())

        # Get association for executive notifications
        association = Association.objects.get(pk=context["association_id"])

        # Validate response code presence
        if "Ds_Response" not in merchant_parameters:
            email_subject = "Ds_Response not found"
            email_body = str(merchant_parameters)
            # Notify executives about missing response code
            for member in get_association_executives(association):
                my_send_mail(email_subject, email_body, member, association)
            return None

        # Check payment response code (0-99 indicates success)
        response_code = int(merchant_parameters["Ds_Response"])

        # Response codes 0-99 indicate successful payment, anything else is failure
        max_successful_response_code = 99
        if response_code < 0 or response_code > max_successful_response_code:
            email_subject = "Failed redsys payment"
            email_body = str(merchant_parameters)
            # Notify executives about failed payment
            for member in get_association_executives(association):
                my_send_mail(email_subject, email_body, member, association)
            return None

        # Extract order number from merchant parameters
        order_number = merchant_parameters["Ds_Order"]

        # Encrypt order number using 3DES for signature verification
        encrypted_order = self.encrypt_order(order_number)

        # Re-encode merchant parameters for signature comparison
        reencoded_parameters = base64.b64encode(json.dumps(merchant_parameters).encode())

        # Compute expected signature using HMAC-SHA256
        computed_signature = self.sign_hmac256(encrypted_order, reencoded_parameters)

        # Verify signature matches to ensure payment authenticity
        if signature != computed_signature:
            error_message = f"Different signature redsys: {signature} vs {computed_signature}"
            error_message += pformat(merchant_parameters)
            logger.error(f"Redsys signature verification failed: {error_message}")
            # Send critical security alert to system admins
            for _admin_name, admin_email in conf_settings.ADMINS:
                my_send_mail("redsys signature", error_message, admin_email)

        # Return order number for successful payment processing
        return order_number
