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
from django.forms import Form
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.gateway import (
    get_paypal_form,
    get_redsys_form,
    get_satispay_form,
    get_stripe_form,
    get_sumup_form,
)
from larpmanager.cache.config import get_assoc_config, get_event_config
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


def get_payment_fee(assoc_id, slug):
    """Get payment processing fee for a specific payment method.

    Args:
        assoc_id: Association instance ID
        slug (str): Payment method slug

    Returns:
        float: Payment fee amount, 0.0 if not configured
    """
    payment_details = fetch_payment_details(assoc_id)
    fee_key = slug + "_fee"
    if fee_key not in payment_details or not payment_details[fee_key]:
        return 0.0

    return float(payment_details[fee_key].replace(",", "."))


def unique_invoice_cod(length=16):
    """Generate a unique invoice code.

    Args:
        length (int): Length of the generated code, defaults to 16

    Returns:
        str: Unique invoice code

    Raises:
        Exception: If unable to generate unique code after 5 attempts
    """
    max_attempts = 5
    for _attempt_number in range(max_attempts):
        invoice_code = generate_id(length)
        if not PaymentInvoice.objects.filter(cod=invoice_code).exists():
            return invoice_code
    raise ValueError("Too many attempts to generate the code")


def set_data_invoice(request: HttpRequest, context: dict, invoice: PaymentInvoice, form: Form, assoc_id: int) -> None:
    """Set invoice data from form submission.

    Updates the invoice object with appropriate causal text based on payment type
    and applies special formatting if configured for the association.

    Args:
        request: Django HTTP request object containing user information
        context: Context dictionary with registration, year, or collection data
        invoice: PaymentInvoice instance to update with causal information
        form: Form containing cleaned invoice data (used for donations)
        assoc_id: Association instance ID for configuration lookup

    Returns:
        None: Function modifies the invoice object in place
    """
    # Get the real display name of the current user
    member_real = request.user.member.display_real()

    # Handle registration payment type
    if invoice.typ == PaymentType.REGISTRATION:
        invoice.causal = _("Registration fee %(number)d of %(user)s per %(event)s") % {
            "user": member_real,
            "event": str(context["reg"].run),
            "number": context["reg"].num_payments,
        }
        # Apply custom registration reason if applicable
        _custom_reason_reg(context, invoice, member_real)

    # Handle membership payment type
    elif invoice.typ == PaymentType.MEMBERSHIP:
        invoice.causal = _("Membership fee of %(user)s for %(year)s") % {
            "user": member_real,
            "year": context["year"],
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
        invoice.idx = context["coll"].id
        invoice.causal = _("Collected contribution of %(user)s for %(recipient)s") % {
            "user": member_real,
            "recipient": context["coll"].display_member(),
        }

    # Apply special code prefix if configured for this association
    if get_assoc_config(assoc_id, "payment_special_code", False):
        invoice.causal = f"{invoice.cod} - {invoice.causal}"


def _custom_reason_reg(context: dict, invoice: PaymentInvoice, member_real: Member) -> None:
    """Generate custom invoice reason text for registrations.

    This function processes a custom reason template from event configuration,
    replacing placeholder variables with actual registration data including
    player names and registration question answers.

    Args:
        context: Context dictionary containing registration data with 'reg' key
        invoice: PaymentInvoice instance to update with custom reason text
        member_real: Real member instance for the registration

    Returns:
        None: Function modifies the invoice object in place
    """
    # Set invoice registration references
    invoice.idx = context["reg"].id
    invoice.reg = context["reg"]

    # Get custom reason template from event configuration
    custom_reason_template = get_event_config(context["reg"].run.event_id, "payment_custom_reason")
    if not custom_reason_template:
        return

    # Extract all placeholder variables from template using regex
    placeholder_pattern = r"\{([^}]+)\}"
    placeholder_keys = re.findall(placeholder_pattern, custom_reason_template)

    # Initialize values dictionary for template replacement
    placeholder_values = {}

    # Handle special case for player_name placeholder
    player_name_key = "player_name"
    if player_name_key in placeholder_keys:
        placeholder_values[player_name_key] = member_real
        placeholder_keys.remove(player_name_key)

    # Process each remaining placeholder key
    for question_name in placeholder_keys:
        # Look for a registration question with matching name
        try:
            registration_question = RegistrationQuestion.objects.get(
                event=context["reg"].run.event, name__iexact=question_name
            )

            # Handle single/multiple choice questions
            if registration_question.typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
                selected_option_names = []
                user_choices = RegistrationChoice.objects.filter(
                    question=registration_question, reg_id=context["reg"].id
                )

                # Collect all selected option names
                for choice in user_choices.select_related("option"):
                    selected_option_names.append(choice.option.name)
                answer_value = ",".join(selected_option_names)
            else:
                # Handle text-based questions
                answer_value = RegistrationAnswer.objects.get(
                    question=registration_question, reg_id=context["reg"].id
                ).text
            placeholder_values[question_name] = answer_value
        except ObjectDoesNotExist:
            # Skip missing questions/answers
            pass

    # Define replacement function for regex substitution
    def replace_placeholder(pattern_match):
        placeholder_key = pattern_match.group(1)
        return placeholder_values.get(placeholder_key, pattern_match.group(0))

    # Apply template substitution and set invoice causal field
    invoice.causal = re.sub(placeholder_pattern, replace_placeholder, custom_reason_template)


def round_up_to_two_decimals(value_to_round):
    """Round number up to two decimal places.

    Args:
        value_to_round (float): Number to round

    Returns:
        float: Number rounded up to 2 decimal places
    """
    return math.ceil(value_to_round * 100) / 100


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


def get_payment_form(
    request: HttpRequest, form: Any, payment_type: str, context: dict[str, Any], invoice_key: str | None = None
) -> None:
    """Create or update payment invoice and prepare gateway-specific form.

    This function handles the complete payment form preparation workflow:
    extracting payment details from the form, creating or updating payment
    invoices, and preparing the appropriate gateway forms based on the
    selected payment method.

    Args:
        request: HTTP request object containing user and association data
        form: Form instance with cleaned payment data (amount, method)
        payment_type: Payment type identifier string
        context: Context dictionary to be updated with payment data and forms
        invoice_key: Optional existing invoice key for invoice retrieval

    Returns:
        None: Function modifies context dict in place

    Side Effects:
        - Updates context with invoice, payment forms, and method details
        - May create new PaymentInvoice object in database
        - Modifies invoice gross fee calculations
    """
    association_id: int = context["association_id"]

    # Extract and store payment details from form data
    payment_amount: Decimal = form.cleaned_data["amount"]
    context["am"] = payment_amount
    payment_method_slug: str = form.cleaned_data["method"]
    context["method"] = payment_method_slug

    # Retrieve payment method configuration
    payment_method: PaymentMethod = PaymentMethod.objects.get(slug=payment_method_slug)

    # Attempt to retrieve existing invoice by key if provided
    invoice: PaymentInvoice | None = None
    if invoice_key is not None:
        try:
            invoice = PaymentInvoice.objects.get(key=invoice_key, status=PaymentStatus.CREATED)
        except Exception:
            # Invoice not found or invalid, will create new one
            pass

    # Create new invoice if existing one not found or invalid
    if not invoice:
        invoice = PaymentInvoice()
        invoice.key = invoice_key
        invoice.cod = unique_invoice_cod()
        invoice.method = payment_method
        invoice.typ = payment_type
        invoice.member = request.user.member
        invoice.assoc_id = association_id
    else:
        # Update existing invoice with current payment method and type
        invoice.method = payment_method
        invoice.typ = payment_type

    # Update payment context and invoice data with current details
    update_payment_details(request, context)
    set_data_invoice(request, context, invoice, form, association_id)

    # Calculate final amount including fees and update invoice
    payment_amount = update_invoice_gross_fee(request, invoice, payment_amount, association_id, payment_method)
    context["invoice"] = invoice

    # Check if receipt is required for manual payments (applies to all payment types)
    require_receipt = get_assoc_config(association_id, "payment_require_receipt", False)
    context["require_receipt"] = require_receipt

    # Prepare gateway-specific forms based on selected payment method
    if payment_method_slug in {"wire", "paypal_nf"}:
        # Wire transfer or non-financial PayPal forms
        context["wire_form"] = WireInvoiceSubmitForm(require_receipt=require_receipt)
        context["wire_form"].set_initial("cod", invoice.cod)
    elif payment_method_slug == "any":
        # Generic payment method form
        context["any_form"] = AnyInvoiceSubmitForm()
        context["any_form"].set_initial("cod", invoice.cod)
    elif payment_method_slug == "paypal":
        # PayPal gateway integration
        get_paypal_form(request, context, invoice, payment_amount)
    elif payment_method_slug == "stripe":
        # Stripe payment gateway
        get_stripe_form(request, context, invoice, payment_amount)
    elif payment_method_slug == "sumup":
        # SumUp payment gateway
        get_sumup_form(request, context, invoice, payment_amount)
    elif payment_method_slug == "redsys":
        # Redsys payment gateway (Spanish banks)
        get_redsys_form(request, context, invoice, payment_amount)
    elif payment_method_slug == "satispay":
        # Satispay mobile payment gateway
        get_satispay_form(request, context, invoice, payment_amount)


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
        collection_item = AccountingItemCollection()
        collection_item.member_id = invoice.member_id
        collection_item.inv = invoice
        collection_item.value = invoice.mc_gross
        collection_item.assoc_id = invoice.assoc_id
        collection_item.collection_id = invoice.idx
        collection_item.save()

        if "badge" in features:
            assign_badge(invoice.member, "gifter")


def _process_donate(features, invoice):
    if not AccountingItemDonation.objects.filter(inv=invoice).exists():
        accounting_item = AccountingItemDonation()
        accounting_item.member_id = invoice.member_id
        accounting_item.inv = invoice
        accounting_item.value = invoice.mc_gross
        accounting_item.assoc_id = invoice.assoc_id
        accounting_item.inv = invoice
        accounting_item.descr = invoice.causal
        accounting_item.save()

        if "badge" in features:
            assign_badge(invoice.member, "donor")


def _process_membership(invoice):
    if not AccountingItemMembership.objects.filter(inv=invoice).exists():
        accounting_item = AccountingItemMembership()
        accounting_item.year = datetime.now().year
        accounting_item.member_id = invoice.member_id
        accounting_item.inv = invoice
        accounting_item.value = invoice.mc_gross
        accounting_item.assoc_id = invoice.assoc_id
        accounting_item.save()


def _process_payment(invoice):
    """Process a payment from an invoice and create accounting entries.

    Args:
        invoice: Invoice object to process payment for
    """
    if not AccountingItemPayment.objects.filter(inv=invoice).exists():
        registration = Registration.objects.get(pk=invoice.idx)

        accounting_item = AccountingItemPayment()
        accounting_item.pay = PaymentChoices.MONEY
        accounting_item.member_id = invoice.member_id
        accounting_item.reg = registration
        accounting_item.inv = invoice
        accounting_item.value = invoice.mc_gross
        accounting_item.assoc_id = invoice.assoc_id
        accounting_item.save()

        Registration.objects.filter(pk=registration.pk).update(num_payments=F("num_payments") + 1)
        registration.refresh_from_db()

        # e-invoice emission
        if "e-invoice" in get_assoc_features(invoice.assoc_id):
            process_payment(invoice.id)


def _process_fee(features, fee_percentage: float, invoice) -> None:
    """Process payment processing fee for an invoice.

    Creates an accounting transaction to track payment processing fees
    associated with an invoice. The fee can be either charged to the
    organization or passed through to the user based on configuration.

    Args:
        features: Feature configuration object
        fee_percentage: Fee percentage to apply to the invoice gross amount
        invoice: Invoice object containing payment details
    """
    # Create new accounting transaction for the processing fee
    accounting_transaction = AccountingItemTransaction()
    accounting_transaction.member_id = invoice.member_id
    accounting_transaction.inv = invoice
    # accounting_transaction.value = invoice.mc_fee

    # Calculate fee amount as percentage of gross invoice value
    accounting_transaction.value = (float(invoice.mc_gross) * fee_percentage) / 100
    accounting_transaction.assoc_id = invoice.assoc_id

    # Check if payment fees should be charged to user instead of organization
    if get_assoc_config(invoice.assoc_id, "payment_fees_user", False):
        accounting_transaction.user_burden = True
    accounting_transaction.save()

    # For registration payments, link the transaction to the registration
    if invoice.typ == PaymentType.REGISTRATION:
        registration = Registration.objects.get(pk=invoice.idx)
        accounting_transaction.reg = registration
        accounting_transaction.save()


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


def process_collection_status_change(collection: Collection) -> None:
    """Update payment collection status and metadata.

    Creates an accounting item credit when a collection's status changes from
    any status to PAYED. This function is idempotent and safe to call multiple
    times on the same collection.

    Args:
        collection (Collection): Collection instance being updated. Must have
            pk, status, assoc_id, member_id, run_id, total, and organizer attributes.

    Returns:
        None

    Side Effects:
        Creates an AccountingItemOther credit entry when collection status
        changes to PAYED for the first time.

    Note:
        Function returns early if collection has no primary key or if the
        previous status was already PAYED to prevent duplicate credits.
    """
    # Early return if collection hasn't been saved to database yet
    if not collection.pk:
        return

    # Attempt to fetch the previous state of the collection
    try:
        prev = Collection.objects.get(pk=collection.pk)
    except Exception:
        # If we can't fetch previous state, safely return to avoid errors
        return

    # Skip processing if collection was already marked as PAYED
    if prev.status == CollectionStatus.PAYED:
        return

    # Only proceed if current status is PAYED (status change occurred)
    if collection.status != CollectionStatus.PAYED:
        return

    # Create accounting credit item for the newly paid collection
    acc = AccountingItemOther()
    acc.assoc_id = collection.assoc_id
    acc.member_id = collection.member_id
    acc.run_id = collection.run_id
    acc.value = collection.total

    # Set the accounting item type to credit and add descriptive text
    acc.oth = OtherChoices.CREDIT
    acc.descr = f"Collection of {collection.organizer}"
    acc.save()
