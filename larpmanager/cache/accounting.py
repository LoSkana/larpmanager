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

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.cache.feature import get_event_features
from larpmanager.models.accounting import (
    AccountingItemPayment,
    PaymentChoices,
)
from larpmanager.models.event import Run
from larpmanager.models.registration import Registration, RegistrationTicket


def round_to_nearest_cent(amount: float) -> float:
    """Round a number to the nearest cent with tolerance for small differences.

    This function rounds the input number to the nearest 0.1 (cent) and returns
    the rounded value only if the difference between the original and rounded
    values is within an acceptable tolerance. Otherwise, it returns the original
    number unchanged.

    Args:
        amount: The number to round to the nearest cent.

    Returns:
        The rounded number if within tolerance, otherwise the original number.

    Example:
        >>> round_to_nearest_cent(1.23456)
        1.2
        >>> round_to_nearest_cent(1.26789)
        1.26789
    """
    # Round to nearest 0.1 (cent) by multiplying by 10, rounding, then dividing
    rounded_amount = round(amount * 10) / 10

    # Set maximum acceptable difference between original and rounded values
    max_allowed_rounding_difference = 0.03

    # Check if the rounding difference is within acceptable tolerance
    if abs(float(amount) - rounded_amount) <= max_allowed_rounding_difference:
        return rounded_amount

    # Return original number if rounding difference exceeds tolerance
    return float(amount)


def get_registration_accounting_cache_key(run_id):
    """Generate cache key for registration accounting data.

    Args:
        run_id: id of Run instance

    Returns:
        str: Cache key for registration accounting data
    """
    return f"registration_accounting_{run_id}"


def clear_registration_accounting_cache(run_id):
    """Reset registration accounting cache for a run.

    Args:
        run_id: id of Run instance to reset cache for
    """
    cache_key = get_registration_accounting_cache_key(run_id)
    cache.delete(cache_key)


def _get_accounting_context(run: Run, member_filter=None) -> tuple[dict, dict, dict]:
    """Get the context data needed for accounting calculations.

    This function retrieves and organizes data required for accounting operations
    including event features, registration tickets, and payment cache information.

    Args:
        run: Run instance representing the event run
        member_filter (int, optional): Member ID to filter payments for specific member.
            If None, includes all members. Defaults to None.

    Returns:
        tuple: A 3-tuple containing:
            - features (dict): Event features configuration
            - registration_tickets_by_id (dict): Registration tickets indexed by ticket ID
            - payment_cache_by_member (dict): Aggregated payment data by member ID
    """
    # Retrieve event features and ensure it's a dictionary
    features = get_event_features(run.event_id)
    if not isinstance(features, dict):
        features = {}

    # Get all registration tickets for this event, ordered by price (highest first)
    registration_tickets_by_id = {}
    for ticket in RegistrationTicket.objects.filter(event_id=run.event_id).order_by("-price"):
        registration_tickets_by_id[ticket.id] = ticket

    # Build cache for token/credit payments if feature is enabled
    payment_cache_by_member = {}

    # Build cache only if token_credit feature is enabled
    if "token_credit" in features:
        # Query accounting item payments for this run
        payments_query = AccountingItemPayment.objects.filter(reg__run=run)

        # Apply member filter if specified
        if member_filter:
            payments_query = payments_query.filter(member_id=member_filter)

        # Filter for token and credit payments only
        payments_query = payments_query.filter(pay__in=[PaymentChoices.TOKEN, PaymentChoices.CREDIT])

        # Aggregate payment data by member and payment type
        for member_id, payment_value, payment_type in payments_query.exclude(hide=True).values_list(
            "member_id", "value", "pay"
        ):
            # Initialize member entry if not exists
            if member_id not in payment_cache_by_member:
                payment_cache_by_member[member_id] = {"total": 0}

            # Add to total and payment type specific amounts
            payment_cache_by_member[member_id]["total"] += payment_value
            if payment_type not in payment_cache_by_member[member_id]:
                payment_cache_by_member[member_id][payment_type] = 0
            payment_cache_by_member[member_id][payment_type] += payment_value

    return features, registration_tickets_by_id, payment_cache_by_member


def refresh_member_accounting_cache(run: Run, member_id: int) -> None:
    """Update accounting cache for a specific member's registrations in a run.

    This function efficiently updates the accounting cache for a single member's
    registrations within a specific run, either by creating the entire cache if
    it doesn't exist or by selectively updating only the affected member's data.

    Args:
        run: Run instance for which to update the accounting cache
        member_id: ID of the member whose accounting data should be updated

    Returns:
        None
    """
    # Get the cache key and retrieve existing cached data
    cache_key = get_registration_accounting_cache_key(run.id)
    cached_accounting_data = cache.get(cache_key)

    # If no cache exists, rebuild the entire cache and return early
    if not cached_accounting_data:
        update_registration_accounting_cache(run)
        return

    # Fetch all active registrations for this member in the current run
    member_registrations = Registration.objects.filter(run=run, member_id=member_id, cancellation_date__isnull=True)

    # Handle case where member has no active registrations
    if not member_registrations.exists():
        # Clean up any stale cache entries for this member's old registrations
        for registration_id in list(cached_accounting_data.keys()):
            try:
                registration = Registration.objects.get(id=registration_id, member_id=member_id)
                # Remove cache entry if it belongs to this run and member
                if registration.run_id == run.id:
                    cached_accounting_data.pop(registration_id, None)
            except ObjectDoesNotExist:
                # Skip if registration no longer exists
                pass
    else:
        # Recalculate accounting data for member's active registrations
        features, registration_tickets, cached_already_invoiced_payments = _get_accounting_context(run, member_id)

        # Update cache with fresh accounting data for each registration
        for registration in member_registrations:
            accounting_data = _calculate_registration_accounting(
                registration, registration_tickets, cached_already_invoiced_payments, features
            )
            # Store calculated values as formatted strings in cache
            cached_accounting_data[registration.id] = {key: f"{value:g}" for key, value in accounting_data.items()}

    # Persist the updated cache data with 1-day timeout
    cache.set(cache_key, cached_accounting_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


def get_registration_accounting_cache(run: Run) -> dict:
    """Get or create registration accounting cache for a run.

    Retrieves cached registration accounting data for the given run. If the cache
    is empty or expired, regenerates the data and stores it in cache with a 1-day timeout.

    Args:
        run (Run): The Run instance to get accounting data for.

    Returns:
        dict: Cached registration accounting data containing payment summaries,
              registration statistics, and financial information.
    """
    # Generate the cache key for this specific run
    key = get_registration_accounting_cache_key(run.id)

    # Attempt to retrieve cached data
    res = cache.get(key)

    # If cache miss, regenerate and store the data
    if res is None:
        res = update_registration_accounting_cache(run)
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def update_registration_accounting_cache(run: Run) -> dict[int, dict[str, str]]:
    """Update registration accounting cache for the given run.

    Processes all active (non-cancelled) registrations for a run and calculates
    their accounting data, formatting monetary values as strings without trailing zeros.

    Args:
        run: Run instance to update accounting cache for

    Returns:
        Dictionary mapping registration IDs to their accounting data, where each
        accounting entry contains string-formatted monetary values
    """
    # Get accounting context data (features, tickets, pricing)
    features, registration_tickets, cached_accounting_info_per_registration = _get_accounting_context(run)

    # Filter for active registrations only (exclude cancelled ones)
    active_registrations = Registration.objects.filter(run=run, cancellation_date__isnull=True)
    accounting_cache = {}

    # Process each registration to calculate accounting data
    for registration in active_registrations:
        # Calculate accounting details for this registration
        accounting_data = _calculate_registration_accounting(
            registration, registration_tickets, cached_accounting_info_per_registration, features
        )

        # Format monetary values as strings without trailing zeros
        accounting_cache[registration.id] = {key: f"{value:g}" for key, value in accounting_data.items()}

    return accounting_cache


def _calculate_registration_accounting(reg, reg_tickets: dict, cache_aip: dict, features: dict) -> dict:
    """Calculate accounting data for a single registration.

    Computes financial totals, payment breakdowns, and remaining balances
    for a registration based on tickets, payments, and enabled features.

    Args:
        reg: Registration instance containing financial data
        reg_tickets: Dictionary mapping ticket ID to RegistrationTicket objects
        cache_aip: Cached accounting payment data by member ID
        features: Dictionary of enabled features for the event

    Returns:
        dict: Registration accounting data containing:
            - Basic financial fields (total_paid, total_registration_cost, quota, etc.)
            - Payment breakdown by type (cash_payment, credit_payment, token_payment)
            - Remaining balance and ticket pricing information
    """
    accounting_data = {}
    max_rounding = 0.05

    # Extract and round basic registration financial fields
    for field_name in ["tot_payed", "tot_iscr", "quota", "deadline", "pay_what", "surcharge"]:
        accounting_data[field_name] = round_to_nearest_cent(getattr(reg, field_name, 0))

    # Process token/credit payments if the feature is enabled
    if isinstance(features, dict) and "token_credit" in features:
        if reg.member_id in cache_aip:
            # Extract credit (b) and token (c) payments from cache
            for payment_type in ["b", "c"]:  # b=CREDIT, c=TOKEN
                payment_value = 0
                if payment_type in cache_aip[reg.member_id]:
                    payment_value = cache_aip[reg.member_id][payment_type]
                accounting_data["pay_" + payment_type] = float(payment_value)
            # Calculate cash payment (a) as remainder
            accounting_data["pay_a"] = accounting_data["tot_payed"] - (
                accounting_data["pay_b"] + accounting_data["pay_c"]
            )
        else:
            # No cached payments, all payment is cash
            accounting_data["pay_a"] = accounting_data["tot_payed"]

    # Calculate remaining balance and apply rounding threshold
    accounting_data["remaining"] = accounting_data["tot_iscr"] - accounting_data["tot_payed"]
    if abs(accounting_data["remaining"]) < max_rounding:
        accounting_data["remaining"] = 0

    # Add ticket pricing breakdown if ticket exists
    if reg.ticket_id in reg_tickets:
        ticket = reg_tickets[reg.ticket_id]
        accounting_data["ticket_price"] = ticket.price
        # Add custom payment amount to base ticket price
        if reg.pay_what:
            accounting_data["ticket_price"] += reg.pay_what
        # Calculate additional options cost
        accounting_data["options_price"] = reg.tot_iscr - accounting_data["ticket_price"]

    return accounting_data
