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

import math
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.gateway import (
    get_paypal_form,
    get_redsys_form,
    get_satispay_form,
    get_stripe_form,
    get_sumup_form,
)
from larpmanager.cache.config import get_assoc_config
from larpmanager.cache.feature import get_assoc_features
from larpmanager.forms.accounting import AnyInvoiceSubmitForm, WireInvoiceSubmitForm
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemDonation,
    AccountingItemMembership,
    AccountingItemOther,
    AccountingItemPayment,
    AccountingItemTransaction,
    Collection,
    CollectionStatus,
    OtherChoices,
    PaymentChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
    RefundRequest,
    RefundStatus,
)
from larpmanager.models.base import PaymentMethod
from larpmanager.models.form import (
    BaseQuestionType,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationQuestion,
)
from larpmanager.models.registration import Registration
from larpmanager.models.utils import generate_id
from larpmanager.utils.base import fetch_payment_details, update_payment_details
from larpmanager.utils.einvoice import process_payment
from larpmanager.utils.member import assign_badge


def get_payment_fee(assoc_id, slug):
    """Get payment processing fee for a specific payment method.

    Args:
        assoc_id: Association instance ID
        slug (str): Payment method slug

    Returns:
        float: Payment fee amount, 0.0 if not configured
    """
    payment_details = fetch_payment_details(assoc_id)
    k = slug + "_fee"
    if k not in payment_details or not payment_details[k]:
        return 0.0

    return float(payment_details[k].replace(",", "."))


def unique_invoice_cod(length=16):
    """Generate a unique invoice code.

    Args:
        length (int): Length of the generated code, defaults to 16

    Returns:
        str: Unique invoice code

    Raises:
        Exception: If unable to generate unique code after 5 attempts
    """
    for _idx in range(5):
        cod = generate_id(length)
        if not PaymentInvoice.objects.filter(cod=cod).exists():
            return cod
    raise ValueError("Too many attempts to generate the code")


def set_data_invoice(request, ctx, invoice, form, assoc_id):
    """Set invoice data from form submission.

    Args:
        request: Django HTTP request object
        ctx: Context dictionary
        invoice: PaymentInvoice instance to update
        form: Form containing invoice data
        assoc_id: Association instance ID
    """
    member_real = request.user.member.display_real()
    if invoice.typ == PaymentType.REGISTRATION:
        invoice.causal = _("Registration fee %(number)d of %(user)s per %(event)s") % {
            "user": member_real,
            "event": str(ctx["reg"].run),
            "number": ctx["reg"].num_payments,
        }
        _custom_reason_reg(ctx, invoice, member_real)

    elif invoice.typ == PaymentType.MEMBERSHIP:
        invoice.causal = _("Membership fee of %(user)s for %(year)s") % {
            "user": member_real,
            "year": ctx["year"],
        }
    elif invoice.typ == PaymentType.DONATE:
        descr = form.cleaned_data["descr"]
        invoice.causal = _("Donation of %(user)s, with reason: '%(reason)s'") % {
            "user": member_real,
            "reason": descr,
        }
    elif invoice.typ == PaymentType.COLLECTION:
        invoice.idx = ctx["coll"].id
        invoice.causal = _("Collected contribution of %(user)s for %(recipient)s") % {
            "user": member_real,
            "recipient": ctx["coll"].display_member(),
        }

    if get_assoc_config(assoc_id, "payment_special_code", False):
        invoice.causal = f"{invoice.cod} - {invoice.causal}"


def _custom_reason_reg(ctx, invoice, member_real):
    """Generate custom invoice reason text for registrations.

    Args:
        ctx: Context dictionary with registration data
        invoice: PaymentInvoice instance to update
        member_real: Real member instance for the registration
    """
    invoice.idx = ctx["reg"].id
    invoice.reg = ctx["reg"]
    custom_reason = ctx["reg"].run.event.get_config("payment_custom_reason")
    if not custom_reason:
        return

    # find all matches
    pattern = r"\{([^}]+)\}"
    keys = re.findall(pattern, custom_reason)

    values = {}
    name = "player_name"
    if name in keys:
        values[name] = member_real
        keys.remove(name)
    for key in keys:
        # Look for a registration question with that name
        try:
            question = RegistrationQuestion.objects.get(event=ctx["reg"].run.event, name__iexact=key)
            if question.typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
                aux = []
                que = RegistrationChoice.objects.filter(question=question, reg_id=ctx["reg"].id)
                for choice in que.select_related("option"):
                    aux.append(choice.option.name)
                value = ",".join(aux)
            else:
                value = RegistrationAnswer.objects.get(question=question, reg_id=ctx["reg"].id).text
            values[key] = value
        except ObjectDoesNotExist:
            pass

    def replace(match):
        key = match.group(1)
        return values.get(key, match.group(0))

    invoice.causal = re.sub(pattern, replace, custom_reason)


def round_up_to_two_decimals(number):
    """Round number up to two decimal places.

    Args:
        number (float): Number to round

    Returns:
        float: Number rounded up to 2 decimal places
    """
    return math.ceil(number * 100) / 100


def update_invoice_gross_fee(request, invoice, amount, assoc_id, pay_method):
    """Update invoice with gross amount including payment processing fees.

    Args:
        request: Django HTTP request object
        invoice: PaymentInvoice instance to update
        amount (Decimal): Base amount before fees
        assoc_id: Association instance ID
        pay_method (str): Payment method slug
    """
    # add fee for paymentmethod
    amount = float(amount)
    fee = get_payment_fee(assoc_id, pay_method.slug)

    if fee is not None:
        if get_assoc_config(assoc_id, "payment_fees_user", False):
            amount = (amount * 100) / (100 - fee)
            amount = round_up_to_two_decimals(amount)

        invoice.mc_fee = round_up_to_two_decimals(amount * fee / 100.0)

    invoice.mc_gross = amount
    invoice.save()
    return amount


def get_payment_form(request: HttpRequest, form: Any, typ: str, ctx: dict[str, Any], key: str | None = None) -> None:
    """Create or update payment invoice and prepare gateway-specific form.

    This function handles the complete payment form preparation workflow:
    extracting payment details from the form, creating or updating payment
    invoices, and preparing the appropriate gateway forms based on the
    selected payment method.

    Args:
        request: HTTP request object containing user and association data
        form: Form instance with cleaned payment data (amount, method)
        typ: Payment type identifier string
        ctx: Context dictionary to be updated with payment data and forms
        key: Optional existing invoice key for invoice retrieval

    Returns:
        None: Function modifies ctx dict in place

    Side Effects:
        - Updates ctx with invoice, payment forms, and method details
        - May create new PaymentInvoice object in database
        - Modifies invoice gross fee calculations
    """
    assoc_id: int = request.assoc["id"]

    # Extract and store payment details from form data
    amount: Decimal = form.cleaned_data["amount"]
    ctx["am"] = amount
    method: str = form.cleaned_data["method"]
    ctx["method"] = method

    # Retrieve payment method configuration
    pay_method: PaymentMethod = PaymentMethod.objects.get(slug=method)

    # Attempt to retrieve existing invoice by key if provided
    invoice: PaymentInvoice | None = None
    if key is not None:
        try:
            invoice = PaymentInvoice.objects.get(key=key, status=PaymentStatus.CREATED)
        except Exception:
            # Invoice not found or invalid, will create new one
            pass

    # Create new invoice if existing one not found or invalid
    if not invoice:
        invoice = PaymentInvoice()
        invoice.key = key
        invoice.cod = unique_invoice_cod()
        invoice.method = pay_method
        invoice.typ = typ
        invoice.member = request.user.member
        invoice.assoc_id = assoc_id
    else:
        # Update existing invoice with current payment method and type
        invoice.method = pay_method
        invoice.typ = typ

    # Update payment context and invoice data with current details
    update_payment_details(request, ctx)
    set_data_invoice(request, ctx, invoice, form, assoc_id)

    # Calculate final amount including fees and update invoice
    amount = update_invoice_gross_fee(request, invoice, amount, assoc_id, pay_method)
    ctx["invoice"] = invoice

    # Prepare gateway-specific forms based on selected payment method
    if method in {"wire", "paypal_nf"}:
        # Wire transfer or non-financial PayPal forms
        ctx["wire_form"] = WireInvoiceSubmitForm()
        ctx["wire_form"].set_initial("cod", invoice.cod)
    elif method == "any":
        # Generic payment method form
        ctx["any_form"] = AnyInvoiceSubmitForm()
        ctx["any_form"].set_initial("cod", invoice.cod)
    elif method == "paypal":
        # PayPal gateway integration
        get_paypal_form(request, ctx, invoice, amount)
    elif method == "stripe":
        # Stripe payment gateway
        get_stripe_form(request, ctx, invoice, amount)
    elif method == "sumup":
        # SumUp payment gateway
        get_sumup_form(request, ctx, invoice, amount)
    elif method == "redsys":
        # Redsys payment gateway (Spanish banks)
        get_redsys_form(request, ctx, invoice, amount)
    elif method == "satispay":
        # Satispay mobile payment gateway
        get_satispay_form(request, ctx, invoice, amount)


def payment_received(invoice):
    """Process a received payment and update related records.

    Args:
        invoice: PaymentInvoice instance that was paid

    Side effects:
        Creates accounting records, processes collections/donations
    """
    features = get_assoc_features(invoice.assoc_id)
    fee = get_payment_fee(invoice.assoc_id, invoice.method.slug)

    if fee > 0 and not AccountingItemTransaction.objects.filter(inv=invoice).exists():
        _process_fee(features, fee, invoice)

    if invoice.typ == PaymentType.REGISTRATION:
        _process_payment(invoice)

    elif invoice.typ == PaymentType.MEMBERSHIP:
        _process_membership(invoice)

    elif invoice.typ == PaymentType.DONATE:
        _process_donate(features, invoice)

    elif invoice.typ == PaymentType.COLLECTION:
        _process_collection(features, invoice)

    return True


def _process_collection(features, invoice):
    if not AccountingItemCollection.objects.filter(inv=invoice).exists():
        acc = AccountingItemCollection()
        acc.member_id = invoice.member_id
        acc.inv = invoice
        acc.value = invoice.mc_gross
        acc.assoc_id = invoice.assoc_id
        acc.collection_id = invoice.idx
        acc.save()

        if "badge" in features:
            assign_badge(invoice.member, "gifter")


def _process_donate(features, invoice):
    if not AccountingItemDonation.objects.filter(inv=invoice).exists():
        acc = AccountingItemDonation()
        acc.member_id = invoice.member_id
        acc.inv = invoice
        acc.value = invoice.mc_gross
        acc.assoc_id = invoice.assoc_id
        acc.inv = invoice
        acc.descr = invoice.causal
        acc.save()

        if "badge" in features:
            assign_badge(invoice.member, "donor")


def _process_membership(invoice):
    if not AccountingItemMembership.objects.filter(inv=invoice).exists():
        acc = AccountingItemMembership()
        acc.year = datetime.now().year
        acc.member_id = invoice.member_id
        acc.inv = invoice
        acc.value = invoice.mc_gross
        acc.assoc_id = invoice.assoc_id
        acc.save()


def _process_payment(invoice):
    """Process a payment from an invoice and create accounting entries.

    Args:
        invoice: Invoice object to process payment for
    """
    if not AccountingItemPayment.objects.filter(inv=invoice).exists():
        reg = Registration.objects.get(pk=invoice.idx)

        acc = AccountingItemPayment()
        acc.pay = PaymentChoices.MONEY
        acc.member_id = invoice.member_id
        acc.reg = reg
        acc.inv = invoice
        acc.value = invoice.mc_gross
        acc.assoc_id = invoice.assoc_id
        acc.save()

        Registration.objects.filter(pk=reg.pk).update(num_payments=F("num_payments") + 1)
        reg.refresh_from_db()

        # e-invoice emission
        if "e-invoice" in get_assoc_features(invoice.assoc_id):
            process_payment(invoice.id)


def _process_fee(features, fee, invoice):
    trans = AccountingItemTransaction()
    trans.member_id = invoice.member_id
    trans.inv = invoice
    # trans.value = invoice.mc_fee
    trans.value = (float(invoice.mc_gross) * fee) / 100
    trans.assoc_id = invoice.assoc_id
    if get_assoc_config(invoice.assoc_id, "payment_fees_user", False):
        trans.user_burden = True
    trans.save()
    if invoice.typ == PaymentType.REGISTRATION:
        reg = Registration.objects.get(pk=invoice.idx)
        trans.reg = reg
        trans.save()


def process_payment_invoice_status_change(invoice):
    """Process payment invoice status changes and trigger payment received.

    Args:
        invoice: PaymentInvoice instance being saved
    """
    if not invoice.pk:
        return

    try:
        prev = PaymentInvoice.objects.get(pk=invoice.pk)
    except Exception:
        return

    if prev.status in (PaymentStatus.CHECKED, PaymentStatus.CONFIRMED):
        return

    if invoice.status not in (PaymentStatus.CHECKED, PaymentStatus.CONFIRMED):
        return

    payment_received(invoice)


def process_refund_request_status_change(refund_request):
    """Process refund request status changes.

    Args:
        refund_request: RefundRequest instance being updated

    Side effects:
        Creates accounting item when refund status changes to PAYED
    """
    if not refund_request.pk:
        return

    try:
        prev = RefundRequest.objects.get(pk=refund_request.pk)
    except Exception:
        return

    if prev.status == RefundStatus.PAYED:
        return

    if refund_request.status != RefundStatus.PAYED:
        return

    acc = AccountingItemOther()
    acc.member_id = refund_request.member_id
    acc.value = refund_request.value
    acc.oth = OtherChoices.REFUND
    acc.descr = f"Delivered refund of {refund_request.value:.2f}"
    acc.assoc_id = refund_request.assoc_id
    acc.save()


def process_collection_status_change(collection):
    """Update payment collection status and metadata.

    Args:
        collection: Collection instance being updated

    Side effects:
        Creates accounting item credit when collection status changes to PAYED
    """
    if not collection.pk:
        return

    try:
        prev = Collection.objects.get(pk=collection.pk)
    except Exception:
        return

    if prev.status == CollectionStatus.PAYED:
        return

    if collection.status != CollectionStatus.PAYED:
        return

    acc = AccountingItemOther()
    acc.assoc_id = collection.assoc_id
    acc.member_id = collection.member_id
    acc.run_id = collection.run_id
    acc.value = collection.total
    acc.oth = OtherChoices.CREDIT
    acc.descr = f"Collection of {collection.organizer}"
    acc.save()
