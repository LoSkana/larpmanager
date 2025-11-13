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
"""Token and credit balance management for member registrations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, QuerySet, Value, When

from larpmanager.cache.config import get_event_config
from larpmanager.cache.feature import get_association_features
from larpmanager.models.accounting import (
    AccountingItemExpense,
    AccountingItemOther,
    AccountingItemPayment,
    OtherChoices,
    PaymentChoices,
)
from larpmanager.models.event import DevelopStatus
from larpmanager.models.member import get_user_membership
from larpmanager.models.registration import Registration
from larpmanager.models.utils import get_sum

if TYPE_CHECKING:
    from decimal import Decimal

    from larpmanager.models.association import Association


def registration_tokens_credits_use(reg: Registration, remaining: float, association_id: int) -> None:
    """Apply available tokens and credits to a registration payment.

    Automatically uses member's available tokens first, then credits
    to pay for outstanding registration balance.

    Args:
        reg: Registration instance to apply payments to
        remaining: Outstanding balance amount
        association_id: Association ID for membership lookup

    Side Effects:
        Creates AccountingItemPayment records and updates membership balances.
        Updates reg.tot_payed with applied amounts.

    """
    # Early return if no outstanding balance
    if remaining < 0:
        return

    with transaction.atomic():
        # Get member and their membership for the association
        member = reg.member
        membership = get_user_membership(member, association_id)

        # Apply tokens first if available
        if membership.tokens > 0:
            tokens_to_use = min(remaining, membership.tokens)
            reg.tot_payed += tokens_to_use
            membership.tokens -= tokens_to_use
            membership.save()

            # Create payment record for token usage
            AccountingItemPayment.objects.create(
                pay=PaymentChoices.TOKEN,
                value=tokens_to_use,
                member_id=reg.member_id,
                reg=reg,
                association_id=association_id,
            )
            remaining -= tokens_to_use

        # Apply credits if still have remaining balance and credits available
        if membership.credit > 0:
            credits_to_use = min(remaining, membership.credit)
            reg.tot_payed += credits_to_use
            membership.credit -= credits_to_use
            membership.save()

            # Create payment record for credit usage
            AccountingItemPayment.objects.create(
                pay=PaymentChoices.CREDIT,
                value=credits_to_use,
                member_id=reg.member_id,
                reg=reg,
                association_id=association_id,
            )


def registration_tokens_credits_overpay(reg: Registration, overpay: Decimal, association_id: int) -> None:
    """Offsets an overpayment by reducing or deleting AccountingItemPayment rows.

    This function handles overpayments by systematically reducing or removing
    AccountingItemPayment entries with payment types TOKEN or CREDIT. The
    operation is performed within an atomic transaction to ensure data consistency.

    Args:
        reg: Registration instance to adjust payments for.
        overpay: Positive decimal amount representing the overpayment to reverse.
        association_id: Association ID used to filter relevant payment records.

    Note:
        Payments are processed in priority order: CREDIT first, then TOKEN,
        ordered by value (descending) and ID (descending) within each type.
        Rows are locked during processing to prevent race conditions.

    """
    # Early return if no overpayment to process
    if overpay <= 0:
        return

    with transaction.atomic():
        # Build queryset with payment priority annotation and locking
        payment_items_queryset = (
            AccountingItemPayment.objects.select_for_update()
            .filter(reg=reg, association_id=association_id, pay__in=[PaymentChoices.TOKEN, PaymentChoices.CREDIT])
            .annotate(
                pay_priority=Case(
                    When(pay=PaymentChoices.CREDIT, then=Value(0)),
                    When(pay=PaymentChoices.TOKEN, then=Value(1)),
                    output_field=IntegerField(),
                ),
            )
            .order_by("pay_priority", "-value", "-id")
        )

        # Initialize tracking variables
        reversed_total = 0
        remaining_overpay = overpay

        # Process each payment item in priority order
        for payment_item in payment_items_queryset:
            if remaining_overpay <= 0:
                break

            # Calculate how much to cut from this payment
            amount_to_cut = min(remaining_overpay, payment_item.value)
            new_payment_value = payment_item.value - amount_to_cut

            # Delete item if value becomes zero or negative, otherwise update
            if new_payment_value <= 0:
                payment_item.delete()
            else:
                payment_item.value = new_payment_value
                payment_item.save(update_fields=["value"])

            # Update tracking counters
            reversed_total += amount_to_cut
            remaining_overpay -= amount_to_cut


def get_regs_paying_incomplete(association: Association = None) -> QuerySet[Registration]:
    """Get registrations with incomplete payments (excluding small differences).

    This function identifies registrations where the total amount paid differs
    from the total registration amount by more than 0.05 (either overpaid or underpaid).
    Small differences within the 0.05 threshold are considered complete payments
    to account for rounding errors or minor discrepancies.

    Args:
        association (Optional[Association]): Association to filter registrations by.
            If None, returns registrations from all associations.

    Returns:
        QuerySet: Django QuerySet of Registration objects with payment
            differences greater than 0.05 in absolute value. Each registration
            includes an annotated 'diff' field showing the payment difference.

    Examples:
        >>> incomplete_regs = get_regs_paying_incomplete()
        >>> association_incomplete = get_regs_paying_incomplete(my_association)

    """
    # Get base registration queryset, optionally filtered by association
    registration_queryset = get_regs(association)

    # Calculate payment difference: total_paid - total_registration_amount
    registration_queryset = registration_queryset.annotate(diff=F("tot_payed") - F("tot_iscr"))

    # Filter for significant payment differences (> 0.05 absolute value)
    # Excludes small differences that might be due to rounding or minor errors
    return registration_queryset.filter(Q(diff__lte=-0.05) | Q(diff__gte=0.05))


def get_regs(association: Association) -> QuerySet[Registration]:
    """Get active registrations (not cancelled, not from completed events).

    Retrieves all registrations that are still active by filtering out cancelled
    registrations and registrations from events that are cancelled or completed.

    Args:
        association: Optional association to filter registrations by. If provided,
            only returns registrations for events belonging to this association.

    Returns:
        QuerySet of Registration objects that are active and not from
        completed/cancelled events.

    Example:
        >>> active_regs = get_regs(my_association)
        >>> all_active_regs = get_regs(None)

    """
    # Start with all non-cancelled registrations
    registrations_queryset = Registration.objects.filter(cancellation_date__isnull=True)

    # Exclude registrations from cancelled or completed events
    registrations_queryset = registrations_queryset.exclude(
        run__development__in=[DevelopStatus.CANC, DevelopStatus.DONE],
    )

    # Filter by association if provided
    if association:
        registrations_queryset = registrations_queryset.filter(run__event__association=association)

    return registrations_queryset


def update_token_credit_on_payment_save(instance: AccountingItemPayment, created: bool) -> None:
    """Handle accounting item payment post-save token/credit updates.

    Args:
        instance: AccountingItemPayment instance that was saved
        created: Boolean indicating if instance was created

    """
    if not created and instance.reg:
        update_token_credit(instance, token=instance.pay == PaymentChoices.TOKEN)


def update_token_credit_on_payment_delete(instance: AccountingItemPayment) -> None:
    """Handle accounting item payment post-delete token/credit updates.

    Args:
        instance: AccountingItemPayment instance that was deleted

    """
    if instance.reg:
        update_token_credit(instance, token=instance.pay == PaymentChoices.TOKEN)


def update_token_credit_on_other_save(accounting_item: AccountingItemOther) -> None:
    """Handle accounting item other save for token/credit updates.

    Args:
        accounting_item: AccountingItemOther instance that was saved

    """
    if not accounting_item.member:
        return

    update_token_credit(accounting_item, token=accounting_item.oth == OtherChoices.TOKEN)


def update_credit_on_expense_save(expense_item: AccountingItemExpense) -> None:
    """Handle accounting item expense save for credit updates.

    Args:
        expense_item: AccountingItemExpense instance that was saved

    """
    if not expense_item.member or not expense_item.is_approved:
        return

    update_token_credit(expense_item, token=False)


def update_token_credit(
    instance: AccountingItemOther | AccountingItemPayment | AccountingItemExpense, *, token: bool = True
) -> None:
    """Update member's token or credit balance based on accounting items.

    Recalculates and updates membership token or credit balance by summing
    all relevant accounting items (given, used, expenses, refunds).

    Args:
        instance: Accounting item instance that triggered the update
        token: If True, update tokens; if False, update credits. Defaults to True.

    Returns:
        None

    Side Effects:
        - Updates membership.tokens or membership.credit
        - Triggers accounting updates on affected registrations

    """
    association_id = instance.association_id

    # Skip processing if token_credit feature is not active for this association
    if "token_credit" not in get_association_features(association_id):
        return

    # Get the user's membership for this association
    membership = get_user_membership(instance.member, association_id)

    # Handle token balance calculation
    if token:
        # Get all tokens given to the member
        tokens_given = AccountingItemOther.objects.filter(
            member_id=instance.member_id,
            oth=OtherChoices.TOKEN,
            association_id=association_id,
        )

        # Get all tokens used by the member
        tokens_used = AccountingItemPayment.objects.filter(
            member_id=instance.member_id,
            pay=PaymentChoices.TOKEN,
            association_id=association_id,
        )

        # Calculate and save new token balance
        membership.tokens = get_sum(tokens_given) - get_sum(tokens_used)
        membership.save()

    # Handle credit balance calculation
    else:
        # Get all approved expenses for the member
        credit_expenses = AccountingItemExpense.objects.filter(
            member_id=instance.member_id,
            is_approved=True,
            association_id=association_id,
        )

        # Get all credits given to the member
        credits_given = AccountingItemOther.objects.filter(
            member_id=instance.member_id,
            oth=OtherChoices.CREDIT,
            association_id=association_id,
        )

        # Get all credits used by the member
        credits_used = AccountingItemPayment.objects.filter(
            member_id=instance.member_id,
            pay=PaymentChoices.CREDIT,
            association_id=association_id,
        )

        # Get all refunds given to the member
        credits_refunded = AccountingItemOther.objects.filter(
            member_id=instance.member_id,
            oth=OtherChoices.REFUND,
            association_id=association_id,
        )

        # Calculate and save new credit balance (expenses + credits - used - refunds)
        membership.credit = (
            get_sum(credit_expenses) + get_sum(credits_given) - (get_sum(credits_used) + get_sum(credits_refunded))
        )
        membership.save()

    # Trigger accounting updates on registrations with incomplete payments
    for registration in get_regs_paying_incomplete(instance.association).filter(member_id=instance.member_id):
        registration.save()


def handle_tokes_credits(
    association_id: int,
    features: list[str],
    registration: Registration,
    remaining_balance: Decimal,
) -> None:
    """Handle token credits for a registration based on remaining balance.

    Args:
        association_id: Association ID for token credit operations
        features: List of enabled feature names
        registration: Registration object to process
        remaining_balance: Remaining balance (positive = use credits, negative = add credits)

    """
    # Skip if token credits are disabled globally or for this event
    if "token_credit" not in features or get_event_config(
        registration.run.event_id, "token_credit_disable_t", default_value=False
    ):
        return

    # Handle positive balance by using available token credits
    if remaining_balance > 0:
        registration_tokens_credits_use(registration, remaining_balance, association_id)
    # Handle negative balance (overpayment) by adding token credits
    else:
        registration_tokens_credits_overpay(registration, -remaining_balance, association_id)
