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
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration
from larpmanager.models.utils import generate_id
from larpmanager.utils.base import fetch_payment_details, update_payment_details
from larpmanager.utils.einvoice import process_payment
from larpmanager.utils.member import assign_badge


def get_payment_fee(assoc_id: int, slug: str) -> float:
    """Get payment processing fee for a specific payment method.

    Args:
        assoc_id: Association instance ID.
        slug: Payment method slug identifier.

    Returns:
        Payment fee amount as float. Returns 0.0 if fee is not configured
        or payment method is not found.
    """
    # Fetch payment configuration details for the association
    payment_details = fetch_payment_details(assoc_id)

    # Construct the fee key using the payment method slug
    k = slug + "_fee"

    # Check if fee configuration exists and has a value
    if k not in payment_details or not payment_details[k]:
        return 0.0

    # Convert fee string to float, handling comma decimal separators
    return float(payment_details[k].replace(",", "."))


def unique_invoice_cod(length: int = 16) -> str:
    """Generate a unique invoice code.

    This function attempts to generate a unique invoice code by creating
    random IDs and checking for uniqueness in the database. It will retry
    up to 5 times before raising an exception.

    Args:
        length: Length of the generated code. Defaults to 16.

    Returns:
        A unique invoice code string.

    Raises:
        ValueError: If unable to generate a unique code after 5 attempts.
    """
    # Attempt to generate a unique code up to 5 times
    for _idx in range(5):
        # Generate a random code of specified length
        cod = generate_id(length)

        # Check if this code already exists in the database
        if not PaymentInvoice.objects.filter(cod=cod).exists():
            return cod

    # If all attempts failed, raise an exception
    raise ValueError("Too many attempts to generate the code")


def set_data_invoice(request, ctx: dict, invoice, form, assoc_id: int) -> None:
    """Set invoice data from form submission.

    Sets the causal (description) field of a PaymentInvoice based on the payment type
    and form data. Handles different payment types: registration, membership, donation,
    and collection fees.

    Args:
        request: Django HTTP request object containing user information
        ctx: Context dictionary with payment-specific data (reg, year, coll)
        invoice: PaymentInvoice instance to update with causal information
        form: Form containing cleaned invoice data
        assoc_id: Association instance ID for configuration lookup

    Returns:
        None: Modifies the invoice object in place
    """
    # Get the display name of the current user
    member_real = request.user.member.display_real()

    # Handle registration payment type
    if invoice.typ == PaymentType.REGISTRATION:
        invoice.causal = _("Registration fee %(number)d of %(user)s per %(event)s") % {
            "user": member_real,
            "event": str(ctx["reg"].run),
            "number": ctx["reg"].num_payments,
        }
        # Apply custom registration reasoning if needed
        _custom_reason_reg(ctx, invoice, member_real)

    # Handle membership payment type
    elif invoice.typ == PaymentType.MEMBERSHIP:
        invoice.causal = _("Membership fee of %(user)s for %(year)s") % {
            "user": member_real,
            "year": ctx["year"],
        }

    # Handle donation payment type
    elif invoice.typ == PaymentType.DONATE:
        descr = form.cleaned_data["descr"]
        invoice.causal = _("Donation of %(user)s, with reason: '%(reason)s'") % {
            "user": member_real,
            "reason": descr,
        }

    # Handle collection payment type
    elif invoice.typ == PaymentType.COLLECTION:
        invoice.idx = ctx["coll"].id
        invoice.causal = _("Collected contribution of %(user)s for %(recipient)s") % {
            "user": member_real,
            "recipient": ctx["coll"].display_member(),
        }

    # Prepend invoice code to causal if special code configuration is enabled
    if get_assoc_config(assoc_id, "payment_special_code", False):
        invoice.causal = f"{invoice.cod} - {invoice.causal}"


def _custom_reason_reg(ctx: dict, invoice: PaymentInvoice, member_real: Member) -> None:
    """Generate custom invoice reason text for registrations.

    This function processes a custom reason template from event configuration,
    replacing placeholder variables with actual registration data including
    player names and registration question answers.

    Args:
        ctx: Context dictionary containing registration data with 'reg' key
        invoice: PaymentInvoice instance to update with custom reason text
        member_real: Real member instance for the registration

    Returns:
        None: Function modifies the invoice object in place
    """
    # Set invoice registration references
    invoice.idx = ctx["reg"].id
    invoice.reg = ctx["reg"]

    # Get custom reason template from event configuration
    custom_reason = ctx["reg"].run.event.get_config("payment_custom_reason")
    if not custom_reason:
        return

    # Extract all placeholder variables from template using regex
    pattern = r"\{([^}]+)\}"
    keys = re.findall(pattern, custom_reason)

    # Initialize values dictionary for template replacement
    values = {}

    # Handle special case for player_name placeholder
    name = "player_name"
    if name in keys:
        values[name] = member_real
        keys.remove(name)

    # Process each remaining placeholder key
    for key in keys:
        # Look for a registration question with matching name
        try:
            question = RegistrationQuestion.objects.get(event=ctx["reg"].run.event, name__iexact=key)

            # Handle single/multiple choice questions
            if question.typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
                aux = []
                que = RegistrationChoice.objects.filter(question=question, reg_id=ctx["reg"].id)

                # Collect all selected option names
                for choice in que.select_related("option"):
                    aux.append(choice.option.name)
                value = ",".join(aux)
            else:
                # Handle text-based questions
                value = RegistrationAnswer.objects.get(question=question, reg_id=ctx["reg"].id).text
            values[key] = value
        except ObjectDoesNotExist:
            # Skip missing questions/answers
            pass

    # Define replacement function for regex substitution
    def replace(match):
        key = match.group(1)
        return values.get(key, match.group(0))

    # Apply template substitution and set invoice causal field
    invoice.causal = re.sub(pattern, replace, custom_reason)


def round_up_to_two_decimals(number):
    """Round number up to two decimal places.

    Args:
        number (float): Number to round

    Returns:
        float: Number rounded up to 2 decimal places
    """
    return math.ceil(number * 100) / 100


def update_invoice_gross_fee(request, invoice, amount: float, assoc_id: int, pay_method) -> float:
    """Update invoice with gross amount including payment processing fees.

    Calculates and applies payment processing fees to the invoice based on the
    payment method configuration. If user fee configuration is enabled, adjusts
    the amount to account for fees being passed to the user.

    Args:
        request: Django HTTP request object for context
        invoice: PaymentInvoice instance to update with calculated amounts
        amount: Base amount before fees are applied
        assoc_id: Association instance ID for fee configuration lookup
        pay_method: Payment method object containing slug for fee calculation

    Returns:
        Final calculated amount after fee adjustments
    """
    # Convert amount to float for fee calculations
    amount = float(amount)

    # Retrieve payment processing fee percentage for this method
    fee = get_payment_fee(assoc_id, pay_method.slug)

    # Apply fee calculations if a fee is configured
    if fee is not None:
        # Check if fees should be passed to the user
        if get_assoc_config(assoc_id, "payment_fees_user", False):
            # Adjust amount so user pays the fee (reverse calculation)
            amount = (amount * 100) / (100 - fee)
            amount = round_up_to_two_decimals(amount)

        # Calculate and store the monetary fee amount
        invoice.mc_fee = round_up_to_two_decimals(amount * fee / 100.0)

    # Set the final gross amount and persist changes
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


def payment_received(invoice: PaymentInvoice) -> bool:
    """Process a received payment and update related records.

    Args:
        invoice (PaymentInvoice): The payment invoice instance that was paid.

    Returns:
        bool: Always returns True to indicate successful processing.

    Side Effects:
        - Creates accounting records for payment fees
        - Processes registration payments
        - Handles membership payments
        - Processes donations
        - Handles collection payments
    """
    # Get association features and calculate payment fee
    features = get_assoc_features(invoice.assoc_id)
    fee = get_payment_fee(invoice.assoc_id, invoice.method.slug)

    # Process payment fee if applicable and not already processed
    if fee > 0 and not AccountingItemTransaction.objects.filter(inv=invoice).exists():
        _process_fee(features, fee, invoice)

    # Route payment processing based on payment type
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


def _process_fee(features, fee: float, invoice) -> None:
    """Process payment fee for an invoice by creating an accounting transaction.

    Creates an AccountingItemTransaction to track payment processing fees.
    The fee can be assigned to either the user or the organization based on
    configuration settings.

    Args:
        features: Feature configuration object
        fee: Fee percentage to apply to the invoice gross amount
        invoice: Invoice object containing payment details

    Returns:
        None
    """
    # Create new accounting transaction for the fee
    trans = AccountingItemTransaction()
    trans.member_id = invoice.member_id
    trans.inv = invoice

    # Calculate fee amount as percentage of gross payment
    # trans.value = invoice.mc_fee
    trans.value = (float(invoice.mc_gross) * fee) / 100
    trans.assoc_id = invoice.assoc_id

    # Check if payment fees should be user's burden based on config
    if get_assoc_config(invoice.assoc_id, "payment_fees_user", False):
        trans.user_burden = True
    trans.save()

    # Link transaction to registration if this is a registration payment
    if invoice.typ == PaymentType.REGISTRATION:
        reg = Registration.objects.get(pk=invoice.idx)
        trans.reg = reg
        trans.save()


def process_payment_invoice_status_change(invoice: PaymentInvoice) -> None:
    """Process payment invoice status changes and trigger payment received.

    This function monitors invoice status transitions and triggers payment
    processing when an invoice moves from an unpaid state to a paid state
    (CHECKED or CONFIRMED).

    Args:
        invoice (PaymentInvoice): The PaymentInvoice instance being saved.
            Must have a primary key to process status changes.

    Returns:
        None

    Note:
        Only processes invoices that transition FROM non-paid status
        TO CHECKED or CONFIRMED status. Ignores new invoices without pk.
    """
    # Skip processing for new invoices without primary key
    if not invoice.pk:
        return

    # Attempt to fetch previous invoice state from database
    try:
        prev = PaymentInvoice.objects.get(pk=invoice.pk)
    except Exception:
        return

    # Skip if previous status was already paid (CHECKED or CONFIRMED)
    if prev.status in (PaymentStatus.CHECKED, PaymentStatus.CONFIRMED):
        return

    # Skip if current status is not a paid status
    if invoice.status not in (PaymentStatus.CHECKED, PaymentStatus.CONFIRMED):
        return

    # Trigger payment received processing for status transition to paid
    payment_received(invoice)


def process_refund_request_status_change(refund_request: "RefundRequest") -> None:
    """Process refund request status changes.

    Creates an accounting item when a refund request status changes to PAYED.
    Only processes existing refund requests and ignores if previous status was
    already PAYED to prevent duplicate accounting entries.

    Args:
        refund_request: RefundRequest instance being updated with new status

    Returns:
        None

    Side Effects:
        Creates AccountingItemOther record when refund status changes to PAYED
    """
    # Skip processing for new refund requests (not yet saved)
    if not refund_request.pk:
        return

    # Retrieve previous state to detect status changes
    try:
        prev = RefundRequest.objects.get(pk=refund_request.pk)
    except Exception:
        return

    # Skip if previous status was already PAYED (avoid duplicates)
    if prev.status == RefundStatus.PAYED:
        return

    # Only proceed if current status is PAYED
    if refund_request.status != RefundStatus.PAYED:
        return

    # Create accounting item for the delivered refund
    acc = AccountingItemOther()
    acc.member_id = refund_request.member_id
    acc.value = refund_request.value
    acc.oth = OtherChoices.REFUND
    acc.descr = f"Delivered refund of {refund_request.value:.2f}"
    acc.assoc_id = refund_request.assoc_id
    acc.save()


def process_collection_status_change(collection: Collection) -> None:
    """Update payment collection status and metadata.

    This function handles the business logic when a collection's status changes
    to PAYED, automatically creating an accounting credit item for the payment.

    Args:
        collection (Collection): Collection instance being updated. Must have
            pk, status, assoc_id, member_id, run_id, total, and organizer attributes.

    Returns:
        None

    Side Effects:
        Creates an AccountingItemOther credit entry when collection status
        changes from any status to PAYED.

    Note:
        Function returns early if collection has no primary key or if the
        previous status was already PAYED to prevent duplicate credits.
    """
    # Early return if collection hasn't been saved yet
    if not collection.pk:
        return

    # Attempt to fetch the previous state of the collection
    try:
        prev = Collection.objects.get(pk=collection.pk)
    except Exception:
        # If we can't get previous state, skip processing
        return

    # Skip if collection was already marked as paid
    if prev.status == CollectionStatus.PAYED:
        return

    # Only process if current status is PAYED
    if collection.status != CollectionStatus.PAYED:
        return

    # Create accounting credit item for the paid collection
    acc = AccountingItemOther()
    acc.assoc_id = collection.assoc_id
    acc.member_id = collection.member_id
    acc.run_id = collection.run_id

    # Set credit value and type
    acc.value = collection.total
    acc.oth = OtherChoices.CREDIT
    acc.descr = f"Collection of {collection.organizer}"

    # Save the accounting item to database
    acc.save()
