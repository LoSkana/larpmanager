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
import math
import re
from pprint import pformat

import requests
import satispaython
import stripe
from Crypto.Cipher import DES3
from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist
from django.dispatch import receiver
from django.http import Http404
from django.urls import reverse
from paypal.standard.forms import PayPalPaymentsForm
from paypal.standard.ipn.signals import invalid_ipn_received, valid_ipn_received
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


def get_satispay_form(request, ctx, invoice, amount):
    ctx["redirect"] = request.build_absolute_uri(reverse("acc_payed", args=[invoice.id]))
    ctx["callback"] = request.build_absolute_uri(reverse("acc_webhook_satispay")) + "?payment_id={uuid}"

    key_id = ctx["satispay_key_id"]
    rsa_key = load_key("main/satispay/private.pem")

    # body_params = {
    # "expire_date": expiration_date,
    # "external_code": invoice.causal,
    # "redirect_url": ctx["redirect"],
    # "callback_url": ctx["callback"],
    # None

    response = satispaython.create_payment(
        key_id, rsa_key, math.ceil(amount * 100), ctx["payment_currency"], ctx["callback"]
    )

    correct_response_code = 200
    if response.status_code != correct_response_code:
        # print(response)
        # print(response.content)
        raise Http404("something went wrong :( ")

    aux = json.loads(response.content)
    invoice.cod = aux["id"]
    invoice.save()
    ctx["pay_id"] = aux["id"]


def satispay_check(request, ctx):
    update_payment_details(request, ctx)

    if "satispay_key_id" not in ctx:
        return

    que = PaymentInvoice.objects.filter(
        method__slug="satispay",
        status=PaymentStatus.CREATED,
    )
    if que.count() == 0:
        return

    for invoice in que:
        satispay_verify(request, invoice.cod)


def satispay_verify(request, cod):
    ctx = {}
    update_payment_details(request, ctx)

    try:
        invoice = PaymentInvoice.objects.get(cod=cod)
    except ObjectDoesNotExist:
        print(f"Not found - invoice {cod}")
        return

    if invoice.method.slug != "satispay":
        print(f"Wrong slug method - invoice {cod}")
        return

    if invoice.status != PaymentStatus.CREATED:
        print(f"Already confirmed - invoice {cod}")
        return

    key_id = ctx["satispay_key_id"]
    rsa_key = load_key("main/satispay/private.pem")

    response = satispaython.get_payment_details(key_id, rsa_key, invoice.cod)
    # print(response)
    correct_response_code = 200
    if response.status_code != correct_response_code:
        return
    aux = json.loads(response.content)
    mc_gross = int(aux["amount_unit"]) / 100.0
    if aux["status"] == "ACCEPTED":
        invoice_received_money(invoice.cod, mc_gross)


def satispay_webhook(request):
    cod = request.GET.get("payment_id", "")
    satispay_verify(request, cod)


def get_paypal_form(request, ctx, invoice, amount):
    paypal_dict = {
        "business": ctx["paypal_id"],
        "amount": float(amount),
        "currency_code": ctx["payment_currency"],
        "item_name": invoice.causal,
        "invoice": invoice.cod,
        "notify_url": request.build_absolute_uri(reverse("paypal-ipn")),
        "return": request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
        "cancel_return": request.build_absolute_uri(reverse("acc_cancelled")),
    }
    # print(paypal_dict)
    ctx["paypal_form"] = PayPalPaymentsForm(initial=paypal_dict)


@receiver(valid_ipn_received)
def paypal_webhook(sender, **kwargs):
    ipn_obj = sender
    if ipn_obj.payment_status == ST_PP_COMPLETED:
        # WARNING !
        # Check that the receiver email is the same we previously
        # set on the `business` field. (The user could tamper with
        # that fields on the payment form before it goes to PayPal)
        # ~ if ipn_obj.receiver_email != ctx['paypal_id']:
        # ~ # Not a valid payment
        # ~ return

        # print(ipn_obj.receiver_email)
        # print(ipn_obj)
        # ~ Print (ipn_obj)
        # print(ipn_obj.mc_fee)
        # print(ipn_obj.mc_gross)

        return invoice_received_money(ipn_obj.invoice, ipn_obj.mc_gross, ipn_obj.mc_fee, ipn_obj.txn_id)


@receiver(invalid_ipn_received)
def paypal_ko_webhook(sender, **kwargs):
    ipn_obj = sender
    if ipn_obj:
        print(ipn_obj)
    # TODO send mail
    body = pformat(ipn_obj)
    print(body)
    notify_admins("paypal ko", body)


def get_stripe_form(request, ctx, invoice, amount):
    stripe.api_key = ctx["stripe_sk_api"]

    prod = stripe.Product.create(name=invoice.causal)

    # create price
    price = stripe.Price.create(
        unit_amount=str(int(round(amount, 2) * 100)),
        currency=ctx["payment_currency"],
        product=prod.id,
    )

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
    ctx["stripe_ck"] = checkout_session

    invoice.cod = price.id
    invoice.save()


def stripe_webhook(request):
    ctx = def_user_ctx(request)
    update_payment_details(request, ctx)
    stripe.api_key = ctx["stripe_sk_api"]
    payload = request.body
    sig_header = request.META["HTTP_STRIPE_SIGNATURE"]
    endpoint_secret = ctx["stripe_webhook_secret"]

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as e:
        # Invalid payload
        raise e
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        raise e

    # Handle the event
    if event["type"] == "checkout.session.completed" or event["type"] == "checkout.session.async_payment_succeeded":
        session = stripe.checkout.Session.retrieve(
            event["data"]["object"]["id"],
            expand=["line_items"],
        )

        line_items = session.line_items
        # assume only one
        item = line_items["data"][0]
        # print(item)
        cod = item["price"]["id"]
        # print(cod)
        return invoice_received_money(cod)
    # ~ elif event['type'] == 'checkout.session.async_payment_failed':
    # ~ return True
    # ~ elif event['type'] == 'checkout.session.expired':
    # ~ return True
    # ~ elif event['type'] == 'checkout.session.async_payment_succeeded':
    # ~ return True
    else:
        return True
        # raise Exception('Unhandled event type {}'.format(event['type']))


def get_sumup_form(request, ctx, invoice, amount):
    # ## GET AUTH TOKEN

    url = "https://api.sumup.com/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "client_id": ctx["sumup_client_id"],
        "client_secret": ctx["sumup_client_secret"],
        "grant_type": "client_credentials",
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    aux = json.loads(response.text)
    # print(response.text)
    token = aux["access_token"]
    # print(token)

    # ## GET CHECKOUT

    url = "https://api.sumup.com/v0.1/checkouts"
    payload = json.dumps(
        {
            "checkout_reference": invoice.cod,
            "amount": float(amount),
            "currency": ctx["payment_currency"],
            "merchant_code": ctx["sumup_merchant_id"],
            "description": invoice.causal,
            "return_url": request.build_absolute_uri(reverse("acc_webhook_sumup")),
            "redirect_url": request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
            "payment_type": "boleto",
        }
    )
    headers = {"Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {token}"}
    # print(payload)
    response = requests.request("POST", url, headers=headers, data=payload)
    # print(response.text)
    aux = json.loads(response.text)
    ctx["sumup_checkout_id"] = aux["id"]
    invoice.cod = aux["id"]
    invoice.save()


def sumup_webhook(request):
    # Print (Request)
    # pprint(request.body)
    # Print (Request.Meta)
    aux = json.loads(request.body)
    # print (at ['id'])
    # print (at ['status'])

    if aux["status"] != "SUCCESSFUL":
        # Err_Paypal (Print (Request) + Print (Request.Body) + Print (Request.meta))
        return False

    return invoice_received_money(aux["id"])


def redsys_invoice_cod():
    for _idx in range(5):
        cod = generate_number(5) + generate_id(7)
        if not PaymentInvoice.objects.filter(cod=cod).exists():
            return cod
    raise ValueError("Too many attempts to generate the code")


def get_redsys_form(request, ctx, invoice, amount):
    invoice.cod = redsys_invoice_cod()
    invoice.save()

    # print(invoice)
    # print(invoice.cod)

    # ~ client = RedirectClient(ctx['redsys_secret_key'])

    # ~ parameters = {
    # ~ "merchant_code": ctx['redsys_merchant_code'],
    # ~ "terminal": ctx['redsys_merchant_terminal'],
    # ~ "transaction_type": STANDARD_PAYMENT,
    # ~ "currency": int(ctx['redsys_merchant_currency']),
    # ~ "order": invoice.cod,
    # ~ "amount": D(amount).quantize(D(".01"), ROUND_HALF_UP),
    # ~ "merchant_data": "test merchant data",
    # ~ "merchant_name": request.assoc['name'],
    # ~ "titular": "Example Ltd.",
    # ~ "product_description": "Products of Example Commerce",
    # ~ "merchant_url": request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
    # None

    # ~ ctx['redsys_form'] = client.prepare_request(parameters)

    values = {
        "DS_MERCHANT_AMOUNT": float(amount),
        "DS_MERCHANT_CURRENCY": int(ctx["redsys_merchant_currency"]),
        "DS_MERCHANT_ORDER": invoice.cod,
        "DS_MERCHANT_PRODUCTDESCRIPTION": invoice.causal,
        "DS_MERCHANT_TITULAR": request.assoc["name"],
        "DS_MERCHANT_MERCHANTCODE": ctx["redsys_merchant_code"],
        "DS_MERCHANT_MERCHANTURL": request.build_absolute_uri(reverse("acc_webhook_redsys")),
        "DS_MERCHANT_URLOK": request.build_absolute_uri(reverse("acc_payed", args=[invoice.id])),
        "DS_MERCHANT_URLKO": request.build_absolute_uri(reverse("acc_redsys_ko")),
        "DS_MERCHANT_MERCHANTNAME": request.assoc["name"],
        "DS_MERCHANT_TERMINAL": ctx["redsys_merchant_terminal"],
        "DS_MERCHANT_TRANSACTIONTYPE": "0",
    }

    # key = "redsys_merchant_paymethods"
    if "key" in ctx and ctx["key"]:
        values["DS_MERCHANT_PAYMETHODS"] = ctx["key"]

    # print(ctx)
    redsys_sandbox = False
    if int(ctx["redsys_sandbox"]) == 1:
        redsys_sandbox = True
    # print(redsys_sandbox)
    redsyspayment = RedSysClient(
        business_code=ctx["redsys_merchant_code"],
        secret_key=ctx["redsys_secret_key"],
        sandbox=redsys_sandbox,
    )
    ctx["redsys_form"] = redsyspayment.redsys_generate_request(values)
    # print(ctx['redsys_form'])

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
    # print(redsys_form)

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
    # print(msg)
    # ~ msg = msg.encode('ascii')
    # ~ msg = base64.b64encode(msg)
    # print(msg.decode('ascii'))
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
    # print(ds)
    # print(ds.hex())

    # ~ # HMAC SHA256 of the value of the Ds_MerchantParameters parameter and the key obtained
    # ~ dig = HMAC.new(ds, msg=msg, digestmod=SHA256).digest()
    # ~ sig = base64.b64encode (you)

    # Print (Say)
    # ~ #sig = Sig.encode ('ASCII')
    # Print (sig.hex ())
    # ~ ctx['signature'] = sig


def redsys_webhook(request, ok=True):
    ctx = def_user_ctx(request)
    update_payment_details(request, ctx)
    # ver = request.POST["Ds_SignatureVersion"]
    pars = request.POST["Ds_MerchantParameters"]
    sig = request.POST["Ds_Signature"]

    redsyspayment = RedSysClient(business_code=ctx["redsys_merchant_code"], secret_key=ctx["redsys_secret_key"])

    cod = redsyspayment.redsys_check_response(sig, pars, ctx)

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

    def encrypt_order(self, order):
        """
        This method creates a unique key for every request, based on the
        Ds_Merchant_Order and in the shared secret (SERMEPA_SECRET_KEY).
        This unique key is Triple DES ciphered.
        :param Ds_Merchant_Order: Dict with all merchant parameters
        :return  order_encrypted: The encrypted order
        """
        assert isinstance(order, str)
        cipher = DES3.new(base64.b64decode(self.secret_key), DES3.MODE_CBC, IV=b"\0\0\0\0\0\0\0\0")
        return cipher.encrypt(order.encode().ljust(16, b"\0"))

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
        digest = hmac.new(encrypted_order, merchant_parameters, hashlib.sha256).digest()
        return base64.b64encode(digest)

    def redsys_generate_request(self, params):
        """
        Method to generate Redsys Ds_MerchantParameters and Ds_Signature
        :param params: Dict with all transaction parameters
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
        b64_params = base64.b64encode(json.dumps(merchant_parameters).encode())
        # Encrypt order
        encrypted_order = self.encrypt_order(merchant_parameters["DS_MERCHANT_ORDER"])
        # Sign parameters
        signature = self.sign_hmac256(encrypted_order, b64_params).decode()
        return {
            "Ds_Redsys_Url": self.redsys_url,
            "Ds_SignatureVersion": "HMAC_SHA256_V1",
            "Ds_MerchantParameters": b64_params.decode(),
            "Ds_Signature": signature,
        }

    def redsys_check_response(self, signature, b64_merchant_parameters, ctx):
        """
        Method to check received Ds_Signature with the one we extract from
        Ds_MerchantParameters data.
        We remove non alphanumeric characters before doing the comparison
        :param signature: Received signature
        :param b64_merchant_parameters: Received parameters
        :return: True if signature is confirmed, False if not
        """
        merchant_parameters = json.loads(base64.b64decode(b64_merchant_parameters).decode())

        assoc = Association.objects.get(pk=ctx["a_id"])
        # print(merchant_parameters)

        if "Ds_Response" not in merchant_parameters:
            subj = "Ds_Response not found"
            body = str(merchant_parameters)
            for member in get_assoc_executives(assoc):
                my_send_mail(subj, body, member, assoc)
            return None

        resp = int(merchant_parameters["Ds_Response"])

        redsys_failed = 99
        if resp < 0 or resp > redsys_failed:
            subj = "Failed redsys payment"
            body = str(merchant_parameters)
            for member in get_assoc_executives(assoc):
                my_send_mail(subj, body, member, assoc)
            return None

            # print(merchant_parameters)

        # print(base64.b64decode(b64_merchant_parameters))

        # print(base64.b64decode(b64_merchant_parameters).decode())

        order = merchant_parameters["Ds_Order"]

        encrypted_order = self.encrypt_order(order)

        # print(encrypted_order)

        b64_params = base64.b64encode(json.dumps(merchant_parameters).encode())

        # print(b64_params)

        computed_signature = self.sign_hmac256(encrypted_order, b64_params)

        # print(computed_signature)

        # signature = re.sub(ALPHANUMERIC_CHARACTERS, b'', signature)

        # print(signature)

        # computed_signature = re.sub(ALPHANUMERIC_CHARACTERS, b'', computed_signature)

        if signature != computed_signature:
            mes = f"Different signature redsys: {signature} vs {computed_signature}"
            mes += pformat(merchant_parameters)
            print(mes)
            for _name, email in conf_settings.ADMINS:
                my_send_mail("redsys signature", mes, email)

        return order
