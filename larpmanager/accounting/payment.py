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

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.gateway import (
    get_paypal_form,
    get_redsys_form,
    get_satispay_form,
    get_stripe_form,
    get_sumup_form,
)
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
from larpmanager.models.association import Association
from larpmanager.models.base import PaymentMethod
from larpmanager.models.form import (
    BaseQuestionType,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationQuestion,
)
from larpmanager.models.registration import Registration
from larpmanager.models.utils import generate_id, get_payment_details
from larpmanager.utils.base import update_payment_details
from larpmanager.utils.einvoice import process_payment
from larpmanager.utils.member import assign_badge


def get_payment_fee(assoc, slug):
    """Get payment processing fee for a specific payment method.

    Args:
        assoc: Association instance
        slug (str): Payment method slug

    Returns:
        float: Payment fee amount, 0.0 if not configured
    """
    payment_details = get_payment_details(assoc)
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


def set_data_invoice(request, ctx, invoice, form, assoc):
    """Set invoice data from form submission.

    Args:
        request: Django HTTP request object
        ctx: Context dictionary
        invoice: PaymentInvoice instance to update
        form: Form containing invoice data
        assoc: Association instance
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

    if assoc.get_config("payment_special_code", False):
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


def update_invoice_gross_fee(request, invoice, amount, assoc, pay_method):
    """Update invoice with gross amount including payment processing fees.

    Args:
        request: Django HTTP request object
        invoice: PaymentInvoice instance to update
        amount (Decimal): Base amount before fees
        assoc: Association instance
        pay_method (str): Payment method slug
    """
    # add fee for paymentmethod
    amount = float(amount)
    fee = get_payment_fee(assoc, pay_method.slug)

    if fee is not None:
        if assoc.get_config("payment_fees_user", False):
            amount = (amount * 100) / (100 - fee)
            amount = round_up_to_two_decimals(amount)

        invoice.mc_fee = round_up_to_two_decimals(amount * fee / 100.0)

    invoice.mc_gross = amount
    invoice.save()
    return amount


def get_payment_form(request, form, typ, ctx, key=None):
    """Create or update payment invoice and return payment gateway form.

    Args:
        request: Django HTTP request object
        form: Form containing payment data
        typ: Payment type
        ctx: Context dictionary to update
        key: Optional existing invoice key

    Returns:
        dict: Payment form data for gateway integration
    """
    assoc = form.assoc

    amount = form.cleaned_data["amount"]
    ctx["am"] = amount
    method = form.cleaned_data["method"]
    ctx["method"] = method

    pay_method = PaymentMethod.objects.get(slug=method)

    invoice = None
    if key is not None:
        try:
            invoice = PaymentInvoice.objects.get(key=key, status=PaymentStatus.CREATED)
        except Exception:
            # print(e)
            pass

    if not invoice:
        invoice = PaymentInvoice()
        invoice.key = key
        invoice.cod = unique_invoice_cod()
        invoice.method = pay_method
        invoice.typ = typ
        invoice.member = request.user.member
        invoice.assoc = assoc
    else:
        invoice.method = pay_method
        invoice.typ = typ

    update_payment_details(request, ctx)

    set_data_invoice(request, ctx, invoice, form, assoc)

    amount = update_invoice_gross_fee(request, invoice, amount, assoc, pay_method)

    ctx["invoice"] = invoice

    if method in {"wire", "paypal_nf"}:
        ctx["wire_form"] = WireInvoiceSubmitForm()
        ctx["wire_form"].set_initial("cod", invoice.cod)

    elif method == "any":
        ctx["any_form"] = AnyInvoiceSubmitForm()
        ctx["any_form"].set_initial("cod", invoice.cod)

    elif method == "paypal":
        get_paypal_form(request, ctx, invoice, amount)

    elif method == "stripe":
        get_stripe_form(request, ctx, invoice, amount)

    elif method == "sumup":
        get_sumup_form(request, ctx, invoice, amount)

    elif method == "redsys":
        get_redsys_form(request, ctx, invoice, amount)

    elif method == "satispay":
        get_satispay_form(request, ctx, invoice, amount)


def payment_received(invoice):
    """Process a received payment and update related records.

    Args:
        invoice: PaymentInvoice instance that was paid

    Side effects:
        Creates accounting records, processes collections/donations
    """
    assoc = Association.objects.get(pk=invoice.assoc_id)
    features = get_assoc_features(invoice.assoc_id)
    fee = get_payment_fee(assoc, invoice.method.slug)

    if fee > 0 and AccountingItemTransaction.objects.filter(inv=invoice).count() == 0:
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
    if AccountingItemCollection.objects.filter(inv=invoice).count() == 0:
        acc = AccountingItemCollection()
        acc.member = invoice.member
        acc.inv = invoice
        acc.value = invoice.mc_gross
        acc.assoc = invoice.assoc
        acc.collection_id = invoice.idx
        acc.save()

        if "badge" in features:
            assign_badge(invoice.member, "gifter")


def _process_donate(features, invoice):
    if AccountingItemDonation.objects.filter(inv=invoice).count() == 0:
        acc = AccountingItemDonation()
        acc.member = invoice.member
        acc.inv = invoice
        acc.value = invoice.mc_gross
        acc.assoc = invoice.assoc
        acc.inv = invoice
        acc.descr = invoice.causal
        acc.save()

        if "badge" in features:
            assign_badge(invoice.member, "donor")


def _process_membership(invoice):
    if AccountingItemMembership.objects.filter(inv=invoice).count() == 0:
        acc = AccountingItemMembership()
        acc.year = datetime.now().year
        acc.member = invoice.member
        acc.inv = invoice
        acc.value = invoice.mc_gross
        acc.assoc = invoice.assoc
        acc.save()


def _process_payment(invoice):
    """Process a payment from an invoice and create accounting entries.

    Args:
        invoice: Invoice object to process payment for
    """
    if AccountingItemPayment.objects.filter(inv=invoice).count() == 0:
        reg = Registration.objects.get(pk=invoice.idx)

        acc = AccountingItemPayment()
        acc.pay = PaymentChoices.MONEY
        acc.member = invoice.member
        acc.reg = reg
        acc.inv = invoice
        acc.value = invoice.mc_gross
        acc.assoc = invoice.assoc
        acc.save()

        Registration.objects.filter(pk=reg.pk).update(num_payments=F("num_payments") + 1)
        reg.refresh_from_db()

        # e-invoice emission
        if "e-invoice" in get_assoc_features(invoice.assoc_id):
            process_payment(invoice.id)


def _process_fee(features, fee, invoice):
    trans = AccountingItemTransaction()
    trans.member = invoice.member
    trans.inv = invoice
    # trans.value = invoice.mc_fee
    trans.value = (float(invoice.mc_gross) * fee) / 100
    trans.assoc = invoice.assoc
    if invoice.assoc.get_config("payment_fees_user", False):
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


@receiver(pre_save, sender=PaymentInvoice)
def update_payment_invoice(sender, instance, **kwargs):
    process_payment_invoice_status_change(instance)


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
    acc.member = refund_request.member
    acc.value = refund_request.value
    acc.oth = OtherChoices.REFUND
    acc.descr = f"Delivered refund of {refund_request.value:.2f}"
    acc.assoc = refund_request.assoc
    acc.save()


@receiver(pre_save, sender=RefundRequest)
def update_refund_request(sender, instance, **kwargs):
    process_refund_request_status_change(instance)


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
    acc.assoc = collection.assoc
    acc.member = collection.member
    acc.run = collection.run
    acc.value = collection.total
    acc.oth = OtherChoices.CREDIT
    acc.descr = f"Collection of {collection.organizer}"
    acc.save()


@receiver(pre_save, sender=Collection)
def update_collection(sender, instance, **kwargs):
    process_collection_status_change(instance)
