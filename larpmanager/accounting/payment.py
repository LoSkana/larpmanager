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

"""Payment processing and management utilities."""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.gateway import (
    get_paypal_form,
    get_redsys_form,
    get_satispay_form,
    get_stripe_form,
    get_sumup_form,
)
from larpmanager.cache.config import get_association_config, get_event_config
from larpmanager.cache.feature import get_association_features
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

if TYPE_CHECKING:
    from decimal import Decimal

    from django.forms import Form
    from django.http import HttpRequest

    from larpmanager.models.member import Member

logger = logging.getLogger(__name__)


def get_payment_fee(association_id: int, slug: str) -> float:
    """Get payment processing fee for a specific payment method.

    Args:
        association_id: Association instance ID
        slug (str): Payment method slug

    Returns:
        float: Payment fee amount, 0.0 if not configured

    """
    payment_details = fetch_payment_details(association_id)
    fee_key = slug + "_fee"
    if fee_key not in payment_details or not payment_details[fee_key]:
        return 0.0

    return float(payment_details[fee_key].replace(",", "."))


def unique_invoice_cod(length: int = 16) -> str:
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
    msg = "Too many attempts to generate the code"
    raise ValueError(msg)


def set_data_invoice(
    context: dict,
    invoice: PaymentInvoice,
    form: Form,
    association_id: int,
) -> None:
    """Set invoice data from form submission.

    Updates the invoice object with appropriate causal text based on payment type
    and applies special formatting if configured for the association.

    Args:
        context: Context dictionary with registration, year, or collection data
        invoice: PaymentInvoice instance to update with causal information
        form: Form containing cleaned invoice data (used for donations)
        association_id: Association instance ID for configuration lookup

    Returns:
        None: Function modifies the invoice object in place

    """
    # Get the real display name of the current user
    member_real_display_name = context["member"].display_real()

    # Handle registration payment type
    if invoice.typ == PaymentType.REGISTRATION:
        invoice.causal = _("Registration fee %(number)d of %(user)s per %(event)s") % {
            "user": member_real_display_name,
            "event": str(context["reg"].run),
            "number": context["reg"].num_payments,
        }
        # Apply custom registration reason if applicable
        _custom_reason_reg(context, invoice, member_real_display_name)

    # Handle membership payment type
    elif invoice.typ == PaymentType.MEMBERSHIP:
        invoice.causal = _("Membership fee of %(user)s for %(year)s") % {
            "user": member_real_display_name,
            "year": context["year"],
        }

    # Handle donation payment type
    elif invoice.typ == PaymentType.DONATE:
        donation_description = form.cleaned_data["descr"]
        invoice.causal = _("Donation of %(user)s, with reason: '%(reason)s'") % {
            "user": member_real_display_name,
            "reason": donation_description,
        }

    # Handle collection payment type
    elif invoice.typ == PaymentType.COLLECTION:
        invoice.idx = context["coll"].id
        invoice.causal = _("Collected contribution of %(user)s for %(recipient)s") % {
            "user": member_real_display_name,
            "recipient": context["coll"].display_member(),
        }

    # Apply special code prefix if configured for this association
    if get_association_config(association_id, "payment_special_code", default_value=False):
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
                event=context["reg"].run.event,
                name__iexact=question_name,
            )

            # Handle single/multiple choice questions
            if registration_question.typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
                user_choices = RegistrationChoice.objects.filter(
                    question=registration_question,
                    reg_id=context["reg"].id,
                )

                # Collect all selected option names
                selected_option_names = [choice.option.name for choice in user_choices.select_related("option")]
                answer_value = ",".join(selected_option_names)
            else:
                # Handle text-based questions
                answer_value = RegistrationAnswer.objects.get(
                    question=registration_question,
                    reg_id=context["reg"].id,
                ).text
            placeholder_values[question_name] = answer_value
        except ObjectDoesNotExist:  # noqa: PERF203 - Need per-item error handling to skip missing questions
            # Skip missing questions/answers
            pass

    # Define replacement function for regex substitution
    def replace_placeholder(pattern_match: re.Match) -> str:
        """Replace placeholder with value from dict or keep original."""
        placeholder_key = pattern_match.group(1)
        return placeholder_values.get(placeholder_key, pattern_match.group(0))

    # Apply template substitution and set invoice causal field
    invoice.causal = re.sub(placeholder_pattern, replace_placeholder, custom_reason_template)


def round_up_to_two_decimals(value_to_round: float) -> float:
    """Round number up to two decimal places.

    Args:
        value_to_round (float): Number to round

    Returns:
        float: Number rounded up to 2 decimal places

    """
    return math.ceil(value_to_round * 100) / 100


def update_invoice_gross_fee(
    invoice: PaymentInvoice, amount: Decimal, association_id: int, payment_method: PaymentMethod
) -> float:
    """Update invoice with gross amount including payment processing fees.

    Args:
        invoice: PaymentInvoice instance to update
        amount (Decimal): Base amount before fees
        association_id: Association instance ID
        payment_method (str): Payment method slug

    """
    # add fee for paymentmethod
    amount = float(amount)
    payment_fee_percentage = get_payment_fee(association_id, payment_method.slug)

    if payment_fee_percentage is not None:
        if get_association_config(association_id, "payment_fees_user", default_value=False):
            amount = (amount * 100) / (100 - payment_fee_percentage)
            amount = round_up_to_two_decimals(amount)

        invoice.mc_fee = round_up_to_two_decimals(amount * payment_fee_percentage / 100.0)

    invoice.mc_gross = amount
    invoice.save()
    return amount


def _prepare_gateway_form(
    request: HttpRequest,
    context: dict[str, Any],
    invoice: PaymentInvoice,
    payment_amount: Decimal,
    payment_method_slug: str,
    *,
    require_receipt: bool,
) -> None:
    """Prepare gateway-specific payment forms based on payment method.

    Args:
        request: HTTP request object
        context: Context dictionary to be updated with payment forms
        invoice: Payment invoice object
        payment_amount: Payment amount
        payment_method_slug: Payment method identifier
        require_receipt: Whether receipt upload is required
    """
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


def get_payment_form(
    request: HttpRequest,
    form: Any,
    payment_type: str,
    context: dict[str, Any],
    invoice_key: str | None = None,
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
    initial_amount: Decimal = form.cleaned_data["amount"]
    context["am"] = initial_amount
    payment_method_slug: str = form.cleaned_data["method"]
    context["method"] = payment_method_slug

    # Retrieve payment method configuration
    payment_method: PaymentMethod = PaymentMethod.objects.get(slug=payment_method_slug)

    # Attempt to retrieve existing invoice by key if provided
    invoice: PaymentInvoice | None = None
    if invoice_key is not None:
        try:
            invoice = PaymentInvoice.objects.get(key=invoice_key, status=PaymentStatus.CREATED)
        except PaymentInvoice.DoesNotExist as e:
            # Invoice not found or invalid, will create new one
            logger.debug("Invoice %s not found or invalid: %s", invoice_key, e)

    # Create new invoice if existing one not found or invalid
    if not invoice:
        invoice = PaymentInvoice()
        invoice.key = invoice_key
        invoice.cod = unique_invoice_cod()
        invoice.method = payment_method
        invoice.typ = payment_type
        invoice.member = context["member"]
        invoice.association_id = association_id
    else:
        # Update existing invoice with current payment method and type
        invoice.method = payment_method
        invoice.typ = payment_type

    # Update payment context and invoice data with current details
    update_payment_details(context)
    set_data_invoice(context, invoice, form, association_id)

    # Calculate final amount including fees and update invoice
    payment_amount = update_invoice_gross_fee(invoice, initial_amount, association_id, payment_method)
    context["invoice"] = invoice

    # Check if receipt is required for manual payments (applies to all payment types)
    require_receipt: bool = get_association_config(association_id, "payment_require_receipt", default_value=False)
    context["require_receipt"] = require_receipt

    # Prepare gateway-specific forms based on selected payment method
    _prepare_gateway_form(
        request, context, invoice, payment_amount, payment_method_slug, require_receipt=require_receipt
    )


def payment_received(invoice: PaymentInvoice) -> bool:
    """Process a received payment and update related records.

    Args:
        invoice: PaymentInvoice instance that was paid

    Side effects:
        Creates accounting records, processes collections/donations

    """
    association_features = get_association_features(invoice.association_id)
    payment_fee = get_payment_fee(invoice.association_id, invoice.method.slug)

    if payment_fee > 0 and not AccountingItemTransaction.objects.filter(inv=invoice).exists():
        _process_fee(payment_fee, invoice)

    if invoice.typ == PaymentType.REGISTRATION:
        _process_payment(invoice)

    elif invoice.typ == PaymentType.MEMBERSHIP:
        _process_membership(invoice)

    elif invoice.typ == PaymentType.DONATE:
        _process_donate(association_features, invoice)

    elif invoice.typ == PaymentType.COLLECTION:
        _process_collection(association_features, invoice)

    return True


def _process_collection(features: dict, invoice: PaymentInvoice) -> None:
    """Process collection item creation for an invoice if it doesn't exist."""
    # Check if collection item already exists for this invoice
    if not AccountingItemCollection.objects.filter(inv=invoice).exists():
        # Create new collection item from invoice data
        collection_item = AccountingItemCollection()
        collection_item.member_id = invoice.member_id
        collection_item.inv = invoice
        collection_item.value = invoice.mc_gross
        collection_item.association_id = invoice.association_id
        collection_item.collection_id = invoice.idx
        collection_item.save()

        # Assign gifter badge if badge feature is enabled
        if "badge" in features:
            assign_badge(invoice.member, "gifter")


def _process_donate(features: dict, invoice: PaymentInvoice) -> None:
    """Create donation accounting item and assign badge if enabled."""
    # Check if donation accounting item already exists for this invoice
    if not AccountingItemDonation.objects.filter(inv=invoice).exists():
        # Create and populate new donation accounting item
        accounting_item = AccountingItemDonation()
        accounting_item.member_id = invoice.member_id
        accounting_item.inv = invoice
        accounting_item.value = invoice.mc_gross
        accounting_item.association_id = invoice.association_id
        accounting_item.inv = invoice
        accounting_item.descr = invoice.causal
        accounting_item.save()

        # Assign donor badge if feature is enabled
        if "badge" in features:
            assign_badge(invoice.member, "donor")


def _process_membership(invoice: PaymentInvoice) -> None:
    """Create membership accounting item if not already exists for the invoice."""
    # Check if membership item already exists for this invoice
    if not AccountingItemMembership.objects.filter(inv=invoice).exists():
        # Create and populate new membership accounting item
        accounting_item = AccountingItemMembership()
        accounting_item.year = timezone.now().year
        accounting_item.member_id = invoice.member_id
        accounting_item.inv = invoice
        accounting_item.value = invoice.mc_gross
        accounting_item.association_id = invoice.association_id
        accounting_item.save()


def _process_payment(invoice: PaymentInvoice) -> None:
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
        accounting_item.association_id = invoice.association_id
        accounting_item.save()

        Registration.objects.filter(pk=registration.pk).update(num_payments=F("num_payments") + 1)
        registration.refresh_from_db()

        # e-invoice emission
        if "e-invoice" in get_association_features(invoice.association_id):
            process_payment(invoice.id)


def _process_fee(fee_percentage: float, invoice: PaymentInvoice) -> None:
    """Process payment processing fee for an invoice.

    Creates an accounting transaction to track payment processing fees
    associated with an invoice. The fee can be either charged to the
    organization or passed through to the user based on configuration.

    Args:
        fee_percentage: Fee percentage to apply to the invoice gross amount
        invoice: Invoice object containing payment details

    """
    # Create new accounting transaction for the processing fee
    accounting_transaction = AccountingItemTransaction()
    accounting_transaction.member_id = invoice.member_id
    accounting_transaction.inv = invoice

    # Calculate fee amount as percentage of gross invoice value
    accounting_transaction.value = (float(invoice.mc_gross) * fee_percentage) / 100
    accounting_transaction.association_id = invoice.association_id

    # Check if payment fees should be charged to user instead of organization
    if get_association_config(invoice.association_id, "payment_fees_user", default_value=False):
        accounting_transaction.user_burden = True
    accounting_transaction.save()

    # For registration payments, link the transaction to the registration
    if invoice.typ == PaymentType.REGISTRATION:
        registration = Registration.objects.get(pk=invoice.idx)
        accounting_transaction.reg = registration
        accounting_transaction.save()


def process_payment_invoice_status_change(invoice: PaymentInvoice) -> None:
    """Process payment invoice status changes and trigger payment received.

    Args:
        invoice: PaymentInvoice instance being saved

    """
    if not invoice.pk:
        return

    try:
        previous_invoice = PaymentInvoice.objects.get(pk=invoice.pk)
    except PaymentInvoice.DoesNotExist:
        return

    if previous_invoice.status in (PaymentStatus.CHECKED, PaymentStatus.CONFIRMED):
        return

    if invoice.status not in (PaymentStatus.CHECKED, PaymentStatus.CONFIRMED):
        return

    payment_received(invoice)


def process_refund_request_status_change(refund_request: HttpRequest) -> None:
    """Process refund request status changes.

    Args:
        refund_request: RefundRequest instance being updated

    Side effects:
        Creates accounting item when refund status changes to PAYED

    """
    if not refund_request.pk:
        return

    try:
        previous_refund_request = RefundRequest.objects.get(pk=refund_request.pk)
    except RefundRequest.DoesNotExist:
        return

    if previous_refund_request.status == RefundStatus.PAYED:
        return

    if refund_request.status != RefundStatus.PAYED:
        return

    accounting_item = AccountingItemOther()
    accounting_item.member_id = refund_request.member_id
    accounting_item.value = refund_request.value
    accounting_item.oth = OtherChoices.REFUND
    accounting_item.descr = f"Delivered refund of {refund_request.value:.2f}"
    accounting_item.association_id = refund_request.association_id
    accounting_item.save()


def process_collection_status_change(collection: Collection) -> None:
    """Update payment collection status and metadata.

    Creates an accounting item credit when a collection's status changes from
    any status to PAYED. This function is idempotent and safe to call multiple
    times on the same collection.

    Args:
        collection (Collection): Collection instance being updated. Must have
            pk, status, association_id, member_id, run_id, total, and organizer attributes.

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
        previous_collection = Collection.objects.get(pk=collection.pk)
    except Collection.DoesNotExist:
        # If we can't fetch previous state, safely return to avoid errors
        return

    # Skip processing if collection was already marked as PAYED
    if previous_collection.status == CollectionStatus.PAYED:
        return

    # Only proceed if current status is PAYED (status change occurred)
    if collection.status != CollectionStatus.PAYED:
        return

    # Create accounting credit item for the newly paid collection
    accounting_item = AccountingItemOther()
    accounting_item.association_id = collection.association_id
    accounting_item.member_id = collection.member_id
    accounting_item.run_id = collection.run_id
    accounting_item.value = collection.total

    # Set the accounting item type to credit and add descriptive text
    accounting_item.oth = OtherChoices.CREDIT
    accounting_item.descr = f"Collection of {collection.organizer}"
    accounting_item.save()
