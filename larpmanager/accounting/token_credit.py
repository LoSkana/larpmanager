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

from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, QuerySet, Value, When

from larpmanager.cache.basic import get_run_event_id
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
from larpmanager.models.member import Membership, get_user_membership
from larpmanager.models.registration import Registration
from larpmanager.models.utils import get_sum

if TYPE_CHECKING:
    from decimal import Decimal

    from larpmanager.models.association import Association


def _apply_tokens(
    registration: Registration,
    remaining: Decimal,
    membership: Any,
    event_id: int,
    association_id: int,
) -> Decimal:
    """Apply tokens to registration payment and return remaining balance.

    Args:
        registration: Registration to apply tokens to
        remaining: Outstanding balance
        membership: Member's membership with token balance
        event_id: Event ID for config checks
        association_id: Association ID

    Returns:
        Remaining balance after applying tokens

    """
    disable_tokens = get_event_config(event_id, "tokens_disable")
    if membership.tokens <= 0 or disable_tokens:
        return remaining

    tokens_to_use = min(remaining, membership.tokens)
    registration.tot_payed += tokens_to_use
    membership.tokens -= tokens_to_use
    membership.save()

    _create_balance_payment(registration, PaymentChoices.TOKEN, tokens_to_use, association_id)
    return remaining - tokens_to_use


def _apply_credits(
    registration: Registration,
    remaining: Decimal,
    membership: Any,
    event_id: int,
    association_id: int,
) -> Decimal:
    """Apply credits to registration payment and return remaining balance.

    Args:
        registration: Registration to apply credits to
        remaining: Outstanding balance
        membership: Member's membership with credit balance
        event_id: Event ID for config checks
        association_id: Association ID

    Returns:
        Remaining balance after applying credits

    """
    disable_credits = get_event_config(event_id, "credits_disable")
    if membership.credit <= 0 or disable_credits:
        return remaining

    credits_to_use = min(remaining, membership.credit)
    registration.tot_payed += credits_to_use
    membership.credit -= credits_to_use
    membership.save()

    _create_balance_payment(registration, PaymentChoices.CREDIT, credits_to_use, association_id)
    return remaining - credits_to_use


def _create_balance_payment(
    registration: Registration, pay: PaymentChoices, value: Decimal, association_id: int
) -> None:
    """Create the payment record for a balance already deducted from the membership.

    The item is flagged so its post_save neither re-saves the registration (the caller is already
    recomputing its accounting) nor recalculates the balance (already updated by the caller).
    """
    payment = AccountingItemPayment(
        pay=pay,
        value=value,
        member_id=registration.member_id,
        registration=registration,
        association_id=association_id,
    )
    payment._from_balance = True  # noqa: SLF001
    payment.save()


def registration_tokens_credits_use(
    registration: Registration, remaining: Decimal, association_id: int, features: dict
) -> None:
    """Apply available tokens and credits to a registration payment.

    Applies payment methods in order based on enabled features:
    - If both enabled: tokens first, then credits
    - If only one enabled: only that method is applied

    Args:
        registration: Registration instance to apply payments to
        remaining: Outstanding balance amount
        association_id: Association ID for membership lookup
        features: Dict of enabled features

    Side Effects:
        Creates AccountingItemPayment records and updates membership balances.
        Updates registration.tot_payed in memory (caller must persist changes).

    Note:
        This function updates registration.tot_payed in memory but does NOT save the
        registration to avoid infinite recursion. The caller (typically
        handle_registration_accounting_updates) is responsible for persisting
        changes via bulk update to prevent triggering post_save signals.

    """
    # Early return if no outstanding balance
    if remaining <= 0:
        return

    # Get enabled features and check if any payment method is available
    tokens_enabled = "tokens" in features
    credits_enabled = "credits" in features

    if not tokens_enabled and not credits_enabled:
        return

    with transaction.atomic():
        # Prevent concurrent requests from double-spending the same balance
        membership = get_user_membership(registration.member, association_id)
        membership = Membership.objects.select_for_update().get(pk=membership.pk)
        event_id = get_run_event_id(registration.run_id)

        # Apply tokens first if feature is enabled
        if tokens_enabled:
            remaining = _apply_tokens(registration, remaining, membership, event_id, association_id)

        # Apply credits to remaining balance if feature is enabled
        if credits_enabled and remaining > 0:
            _remaining = _apply_credits(registration, remaining, membership, event_id, association_id)

        # Note: registration.tot_payed is updated in memory but NOT saved here
        # to prevent infinite recursion via post_save signal


def registration_tokens_credits_overpay(
    registration: Registration, overpay: Decimal, association_id: int, features: dict
) -> None:
    """Offsets an overpayment by reducing or deleting AccountingItemPayment rows.

    This function handles overpayments by systematically reducing or removing
    AccountingItemPayment entries with payment types TOKEN or CREDIT. Only processes
    payment types for features that are currently enabled.

    Args:
        registration: Registration instance to adjust payments for.
        overpay: Positive decimal amount representing the overpayment to reverse.
        association_id: Association ID used to filter relevant payment records.
        features: Dict of enabled features

    Note:
        Payments are processed in reverse priority order (CREDIT first, then TOKEN),
        ordered by value (descending) and ID (descending) within each type.
        Only processes payment types for enabled features.
        Rows are locked during processing to prevent race conditions.

    """
    # Early return if no overpayment to process
    if overpay <= 0:
        return

    # Get enabled features and determine which payment types to process
    tokens_enabled = "tokens" in features
    credits_enabled = "credits" in features

    if not tokens_enabled and not credits_enabled:
        return

    # Build list of payment types to process based on enabled features
    payment_types = []
    priority_cases = []
    priority_value = 0

    # Credits have higher priority (processed first when reversing overpayments)
    if credits_enabled:
        payment_types.append(PaymentChoices.CREDIT)
        priority_cases.append(When(pay=PaymentChoices.CREDIT, then=Value(priority_value)))
        priority_value += 1

    # Tokens have lower priority (processed after credits)
    if tokens_enabled:
        payment_types.append(PaymentChoices.TOKEN)
        priority_cases.append(When(pay=PaymentChoices.TOKEN, then=Value(priority_value)))

    with transaction.atomic():
        # Build queryset with payment priority annotation and locking
        payment_items_queryset = (
            AccountingItemPayment.objects.select_for_update()
            .filter(registration=registration, association_id=association_id, pay__in=payment_types)
            .annotate(
                pay_priority=Case(
                    *priority_cases,
                    output_field=IntegerField(),
                ),
            )
            .order_by("pay_priority", "-value", "-id")
        )

        # Initialize tracking variables
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

            # Update tracking counter
            remaining_overpay -= amount_to_cut


def get_regs_paying_incomplete(association: Association | int | None = None) -> QuerySet[Registration]:
    """Get registrations with incomplete payments (excluding small differences)."""
    # Get base registration queryset, optionally filtered by association
    registration_queryset = get_regs(association)

    # Calculate payment difference: total_paid - total_registration_amount
    registration_queryset = registration_queryset.annotate(diff=F("tot_payed") - F("tot_iscr"))

    # Filter for significant payment differences (> 0.05 absolute value)
    # Excludes small differences that might be due to rounding or minor errors
    return registration_queryset.filter(Q(diff__lte=-0.05) | Q(diff__gte=0.05))


def get_regs(association: Association | int | None) -> QuerySet[Registration]:
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


def is_balance_payment(instance: AccountingItemPayment) -> bool:
    """Return True if the payment was created by applying the member's tokens or credits."""
    return getattr(instance, "_from_balance", False)


def _balance_owner(
    item: AccountingItemOther | AccountingItemPayment | AccountingItemExpense,
) -> tuple[int, bool] | None:
    """Return (member_id, is_token) of the balance the item counts towards, or None if it counts towards none."""
    if not item.member_id or not getattr(item, "is_approved", True):
        return None
    if isinstance(item, AccountingItemPayment):
        if item.pay == PaymentChoices.MONEY:
            return None
        return item.member_id, item.pay == PaymentChoices.TOKEN
    if isinstance(item, AccountingItemOther):
        return item.member_id, item.oth == OtherChoices.TOKEN
    return item.member_id, False


def store_previous_balance_owner(
    instance: AccountingItemOther | AccountingItemPayment | AccountingItemExpense,
) -> None:
    """Remember the balance owner before save, so a change of member, type or approval refreshes the old one."""
    if not instance.pk:
        return
    previous = type(instance).objects.filter(pk=instance.pk).first()
    if previous:
        instance._previous_balance_owner = _balance_owner(previous)  # noqa: SLF001


def refresh_balances_on_save(
    instance: AccountingItemOther | AccountingItemPayment | AccountingItemExpense,
) -> None:
    """Recalculate the token/credit balances affected by the saved (or soft deleted) item."""
    if isinstance(instance, AccountingItemPayment) and is_balance_payment(instance):
        return

    owners = {_balance_owner(instance), getattr(instance, "_previous_balance_owner", None)}
    for owner in owners:
        if owner:
            member_id, token = owner
            update_token_credit(instance, member_id=member_id, token=token)


def update_token_credit(
    accounting_item: AccountingItemOther | AccountingItemPayment | AccountingItemExpense,
    *,
    member_id: int,
    token: bool,
) -> None:
    """Update the member's token or credit balance."""
    if token:
        update_tokens(member_id, accounting_item.association_id)
    else:
        update_credits(member_id, accounting_item.association_id)


def update_tokens(member_id: int, association_id: int) -> None:
    """Recalculate and update member's token balance from all token transactions."""
    features = get_association_features(association_id)
    if "tokens" not in features:
        return

    # Get all tokens given to the member
    tokens_given = AccountingItemOther.objects.filter(
        member_id=member_id,
        oth=OtherChoices.TOKEN,
        association_id=association_id,
    )

    # Get all tokens used by the member
    tokens_used = AccountingItemPayment.objects.filter(
        member_id=member_id,
        pay=PaymentChoices.TOKEN,
        association_id=association_id,
    )

    # Calculate and save new token balance
    membership, _created = Membership.objects.get_or_create(member_id=member_id, association_id=association_id)
    membership.tokens = get_sum(tokens_given) - get_sum(tokens_used)
    membership.save()

    _save_all_regs(member_id, association_id)


def _save_all_regs(member_id: int, association_id: int) -> None:
    """Trigger accounting recalculation on member's incomplete registrations."""
    for registration in (
        get_regs_paying_incomplete(association_id)
        .filter(member_id=member_id)
        .select_related("run", "run__event", "ticket", "member")
    ):
        registration.save()


def update_credits(member_id: int, association_id: int) -> None:
    """Recalculate and update member's credit balance from all credit transactions."""
    features = get_association_features(association_id)
    if "credits" not in features:
        return

    # Get all approved expenses for the member
    credit_expenses = AccountingItemExpense.objects.filter(
        member_id=member_id,
        is_approved=True,
        association_id=association_id,
    )

    # Get all credits given to the member
    credits_given = AccountingItemOther.objects.filter(
        member_id=member_id,
        oth=OtherChoices.CREDIT,
        association_id=association_id,
    )

    # Get all credits used by the member
    credits_used = AccountingItemPayment.objects.filter(
        member_id=member_id,
        pay=PaymentChoices.CREDIT,
        association_id=association_id,
    )

    # Get all refunds given to the member
    credits_refunded = AccountingItemOther.objects.filter(
        member_id=member_id,
        oth=OtherChoices.REFUND,
        association_id=association_id,
    )

    # Calculate and save new credit balance (expenses + credits - used - refunds)
    membership, _created = Membership.objects.get_or_create(member_id=member_id, association_id=association_id)
    membership.credit = (
        get_sum(credit_expenses) + get_sum(credits_given) - (get_sum(credits_used) + get_sum(credits_refunded))
    )
    membership.save()

    _save_all_regs(member_id, association_id)


def handle_tokes_credits(
    association_id: int,
    features: dict[str, int],
    registration: Registration,
    remaining_balance: Decimal,
) -> None:
    """Handle token credits for a registration based on remaining balance."""
    # Handle positive balance by using available token and/or credits
    if remaining_balance > 0:
        registration_tokens_credits_use(registration, remaining_balance, association_id, features)
    # Handle negative balance (overpayment) by adding token and/or credits
    else:
        registration_tokens_credits_overpay(registration, -remaining_balance, association_id, features)
