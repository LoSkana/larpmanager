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
"""VAT calculation utilities for payment accounting."""

from decimal import Decimal

from django.db.models import Sum

from larpmanager.cache.config import get_association_config
from larpmanager.cache.feature import get_association_features
from larpmanager.models.accounting import AccountingItemPayment, AccountingItemTransaction, PaymentChoices


def calculate_payment_vat(instance: AccountingItemPayment) -> None:
    """Compute VAT for a payment based on ticket and options VAT rates.

    Calculates VAT for an accounting item payment by splitting the payment
    between ticket amount and options, applying different VAT rates to each.

    The function performs the following steps:
    1. Validates that VAT feature is enabled and payment is in money
    2. Calculates previous payments to determine remaining amounts
    3. Retrieves VAT configuration for tickets and options
    4. Splits current payment between ticket and options portions
    5. Updates the payment record with calculated VAT amounts

    Args:
        instance: AccountingItemPayment instance to compute VAT for.
                 Must have valid association_id, pay type, reg, and inv attributes.

    Returns:
        None: Function modifies the instance's VAT fields in the database as a side effect.

    Side Effects:
        Updates the instance's vat_ticket and vat_options fields in the database.

    """
    # Early return if VAT feature is not enabled for this association
    if "vat" not in get_association_features(instance.association_id):
        return

    # Early return if payment is not in money (no VAT calculation needed)
    if instance.pay != PaymentChoices.MONEY:
        return

    # Calculate total amount already paid by this member for this run
    # This includes previous payments minus any refund transactions
    previous_payments_sum = get_previous_sum(instance, AccountingItemPayment)
    previous_transactions_sum = get_previous_sum(instance, AccountingItemTransaction)
    total_previously_paid = previous_payments_sum - previous_transactions_sum

    # Retrieve VAT rates from association configuration
    # Convert percentage values (e.g., 22) to decimal rates (e.g., 0.22)
    config_context = {}
    _vat_rate_ticket = (
        int(get_association_config(instance.association_id, "vat_ticket", default_value=0, context=config_context))
        / 100.0
    )
    _vat_rate_options = (
        int(get_association_config(instance.association_id, "vat_options", default_value=0, context=config_context))
        / 100.0
    )

    # Calculate total ticket cost including both base price and custom amounts
    ticket_total_cost = Decimal(0)
    if instance.registration.pay_what is not None:
        ticket_total_cost += Decimal(str(instance.registration.pay_what))
    if instance.registration.ticket:
        ticket_total_cost += Decimal(str(instance.registration.ticket.price))

    # Determine net payment amount after accounting for refund transactions
    # Ensure we're working with Decimal for monetary calculations
    current_payment_amount = Decimal(str(instance.value))
    transactions_query = AccountingItemTransaction.objects.filter(inv=instance.inv)
    for transaction in transactions_query:
        current_payment_amount -= Decimal(str(transaction.value))

    # Calculate how much of the ticket portion remains unpaid
    # This determines how to split the current payment
    remaining_ticket_amount = max(Decimal(0), ticket_total_cost - Decimal(str(total_previously_paid)))

    # Split current payment between ticket portion and options portion
    # Ticket portion is paid first, remainder goes to options
    payment_allocated_to_ticket = min(current_payment_amount, remaining_ticket_amount)
    payment_allocated_to_options = current_payment_amount - payment_allocated_to_ticket

    # Update database with calculated VAT amounts for each portion
    updates = {"vat_ticket": payment_allocated_to_ticket, "vat_options": payment_allocated_to_options}
    AccountingItemPayment.objects.filter(pk=instance.pk).update(**updates)


def get_previous_sum(aip: AccountingItemPayment, typ: type) -> Decimal:
    """Calculate sum of previous accounting items for the same member and run.

    Computes the total value of all accounting items of the specified type
    that were created before the given reference item, for the same member
    and run combination.

    Args:
        aip: AccountingItemPayment instance used as reference point for
            filtering by member, run, and creation timestamp
        typ: Model class to query (AccountingItemPayment or AccountingItemTransaction)

    Returns:
        Sum of values from previous items matching the criteria, or Decimal(0) if none found

    Example:
        >>> previous_total = get_previous_sum(payment_item, AccountingItemPayment)
        >>> print(f"Previous payments total: {previous_total}")

    """
    # Filter items by same member and run, created before reference item
    previous_items = typ.objects.filter(
        registration__member=aip.registration.member, registration__run=aip.registration.run, created__lt=aip.created
    )

    # Aggregate the sum of values and return Decimal(0) if no items found
    return previous_items.aggregate(total=Sum("value"))["total"] or Decimal(0)
