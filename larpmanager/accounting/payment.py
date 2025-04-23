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
from datetime import datetime

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
    PaymentInvoice,
    RefundRequest,
)
from larpmanager.models.association import Association
from larpmanager.models.base import PaymentMethod
from larpmanager.models.registration import Registration
from larpmanager.models.utils import generate_id, get_payment_details
from larpmanager.utils.base import update_payment_details
from larpmanager.utils.einvoice import process_payment
from larpmanager.utils.member import assign_badge


def get_payment_fee(assoc, slug):
    payment_details = get_payment_details(assoc)
    k = slug + "_fee"
    if k not in payment_details or not payment_details[k]:
        return 0.0

    return float(payment_details[k].replace(",", "."))


def unique_invoice_cod(length=16):
    for _idx in range(5):
        cod = generate_id(length)
        if not PaymentInvoice.objects.filter(cod=cod).exists():
            return cod
    raise ValueError("Too many attempts to generate the code")


def set_data_invoice(request, ctx, invoice, form, assoc):
    real = request.user.member.display_real()
    if invoice.typ == PaymentInvoice.REGISTRATION:
        invoice.idx = ctx["reg"].id
        invoice.reg = ctx["reg"]
        custom_reason = ctx["reg"].run.event.get_config("payment_custom_reason")
        if not custom_reason:
            invoice.causal = _("Registration fee %(number)d of %(user)s per %(event)s") % {
                "user": real,
                "event": str(ctx["reg"].run),
                "number": ctx["reg"].num_payments,
            }
        else:
            custom_reason = custom_reason.replace("{player_name}", real)
            invoice.causal = custom_reason
    elif invoice.typ == PaymentInvoice.MEMBERSHIP:
        invoice.causal = _("Membership fee of %(user)s for %(year)s") % {
            "user": real,
            "year": ctx["year"],
        }
    elif invoice.typ == PaymentInvoice.DONATE:
        descr = form.cleaned_data["descr"]
        invoice.causal = _("Donation of %(user)s, with reason: '%(reason)s'") % {
            "user": real,
            "reason": descr,
        }
    elif invoice.typ == PaymentInvoice.COLLECTION:
        invoice.idx = ctx["coll"].id
        invoice.causal = _("Collected contribution of %(user)s for %(recipient)s") % {
            "user": real,
            "recipient": ctx["coll"].display_member(),
        }

    if assoc.get_config("payment_special_code", False):
        invoice.causal = f"{invoice.cod} - {invoice.causal}"


def round_up_to_two_decimals(number):
    return math.ceil(number * 100) / 100


def update_invoice_gross_fee(request, invoice, amount, assoc, pay_method):
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
    assoc = form.assoc

    amount = form.cleaned_data["amount"]
    ctx["am"] = amount
    method = form.cleaned_data["method"]
    ctx["method"] = method

    pay_method = PaymentMethod.objects.get(slug=method)

    invoice = None
    if key is not None:
        try:
            invoice = PaymentInvoice.objects.get(key=key, status=PaymentInvoice.CREATED)
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

    if method == "wire" or method == "paypal_nf":
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
    assoc = Association.objects.get(pk=invoice.assoc_id)
    features = get_assoc_features(invoice.assoc_id)
    fee = get_payment_fee(assoc, invoice.method.slug)
    if fee > 0 and AccountingItemTransaction.objects.filter(inv=invoice).count() == 0:
        trans = AccountingItemTransaction()
        trans.member = invoice.member
        trans.inv = invoice
        # trans.value = invoice.mc_fee
        trans.value = (float(invoice.mc_gross) * fee) / 100
        trans.assoc = invoice.assoc
        if "payment_fees" in features and invoice.assoc.get_config("payment_fees_user", False):
            trans.user_burden = True
        trans.save()
        if invoice.typ == PaymentInvoice.REGISTRATION:
            reg = Registration.objects.get(pk=invoice.idx)
            trans.reg = reg
            trans.save()

    if invoice.typ == PaymentInvoice.REGISTRATION:
        if AccountingItemPayment.objects.filter(inv=invoice).count() == 0:
            reg = Registration.objects.get(pk=invoice.idx)

            acc = AccountingItemPayment()
            acc.pay = AccountingItemPayment.MONEY
            acc.member = invoice.member
            acc.reg = reg
            acc.inv = invoice
            acc.value = invoice.mc_gross
            acc.assoc = invoice.assoc
            acc.save()

            reg.num_payments += 1
            reg.save()

            # e-invoice emission
            if "e-invoice" in get_assoc_features(invoice.assoc_id):
                process_payment(invoice.id)

    elif invoice.typ == PaymentInvoice.MEMBERSHIP:
        if AccountingItemMembership.objects.filter(inv=invoice).count() == 0:
            acc = AccountingItemMembership()
            acc.year = datetime.now().year
            acc.member = invoice.member
            acc.inv = invoice
            acc.value = invoice.mc_gross
            acc.assoc = invoice.assoc
            acc.save()

    elif invoice.typ == PaymentInvoice.DONATE:
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

    elif invoice.typ == PaymentInvoice.COLLECTION:
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

    return True


@receiver(pre_save, sender=PaymentInvoice)
def update_PaymentInvoice(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        prev = PaymentInvoice.objects.get(pk=instance.pk)
    except Exception:
        return

    if prev.status == PaymentInvoice.CHECKED or prev.status == PaymentInvoice.CONFIRMED:
        return

    if instance.status != PaymentInvoice.CHECKED and instance.status != PaymentInvoice.CONFIRMED:
        return

    payment_received(instance)


@receiver(pre_save, sender=RefundRequest)
def update_RefundRequest(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        prev = RefundRequest.objects.get(pk=instance.pk)
    except Exception:
        return

    if prev.status == RefundRequest.PAYED:
        return

    if instance.status != RefundRequest.PAYED:
        return

    acc = AccountingItemOther()
    acc.member = instance.member
    acc.value = instance.value
    acc.oth = AccountingItemOther.REFUND
    acc.descr = f"Delivered refund of {instance.value:.2f}"
    acc.assoc = instance.assoc
    acc.save()


@receiver(pre_save, sender=Collection)
def update_Collection(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        prev = Collection.objects.get(pk=instance.pk)
    except Exception:
        return

    if prev.status == Collection.PAYED:
        return

    if instance.status != Collection.PAYED:
        return

    acc = AccountingItemOther()
    acc.assoc = instance.assoc
    acc.member = instance.member
    acc.run = instance.run
    acc.value = instance.total
    acc.oth = AccountingItemOther.CREDIT
    acc.descr = f"Collection of {instance.organizer}"
    acc.save()
