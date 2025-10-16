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


def round_to_nearest_cent(number):
    """Round a number to the nearest cent with tolerance for small differences.

    Args:
        number: Number to round

    Returns:
        float: Rounded number, original if difference exceeds tolerance
    """
    rounded = round(number * 10) / 10
    max_rounding = 0.03
    if abs(float(number) - rounded) <= max_rounding:
        return rounded
    return float(number)


def get_registration_accounting_cache_key(run_id):
    """Generate cache key for registration accounting data.

    Args:
        run_id: id of Run instance

    Returns:
        str: Cache key for registration accounting data
    """
    return f"reg_accounting_{run_id}"


def clear_registration_accounting_cache(run_id):
    """Reset registration accounting cache for a run.

    Args:
        run_id: id of Run instance to reset cache for
    """
    cache.delete(get_registration_accounting_cache_key(run_id))


def _get_accounting_context(run, member_filter=None):
    """Get the context data needed for accounting calculations.

    Args:
        run: Run instance
        member_filter: Optional member ID to filter payments for

    Returns:
        tuple: (features, reg_tickets, cache_aip)
    """
    features = get_event_features(run.event_id)
    if not isinstance(features, dict):
        features = {}

    # Get all tickets for this event
    reg_tickets = {}
    for t in RegistrationTicket.objects.filter(event_id=run.event_id).order_by("-price"):
        reg_tickets[t.id] = t

    # Build cache for token/credit payments
    cache_aip = {}
    if "token_credit" in features:
        que = AccountingItemPayment.objects.filter(reg__run=run)
        if member_filter:
            que = que.filter(member_id=member_filter)
        que = que.filter(pay__in=[PaymentChoices.TOKEN, PaymentChoices.CREDIT])
        for el in que.exclude(hide=True).values_list("member_id", "value", "pay"):
            if el[0] not in cache_aip:
                cache_aip[el[0]] = {"total": 0}
            cache_aip[el[0]]["total"] += el[1]
            if el[2] not in cache_aip[el[0]]:
                cache_aip[el[0]][el[2]] = 0
            cache_aip[el[0]][el[2]] += el[1]

    return features, reg_tickets, cache_aip


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
    key = get_registration_accounting_cache_key(run.id)
    cached_data = cache.get(key)

    # If no cache exists, rebuild the entire cache and return early
    if not cached_data:
        update_registration_accounting_cache(run)
        return

    # Fetch all active registrations for this member in the current run
    member_regs = Registration.objects.filter(run=run, member_id=member_id, cancellation_date__isnull=True)

    # Handle case where member has no active registrations
    if not member_regs.exists():
        # Clean up any stale cache entries for this member's old registrations
        for reg_id in list(cached_data.keys()):
            try:
                reg = Registration.objects.get(id=reg_id, member_id=member_id)
                # Remove cache entry if it belongs to this run and member
                if reg.run_id == run.id:
                    cached_data.pop(reg_id, None)
            except ObjectDoesNotExist:
                # Skip if registration no longer exists
                pass
    else:
        # Recalculate accounting data for member's active registrations
        features, reg_tickets, cache_aip = _get_accounting_context(run, member_id)

        # Update cache with fresh accounting data for each registration
        for reg in member_regs:
            dt = _calculate_registration_accounting(reg, reg_tickets, cache_aip, features)
            # Store calculated values as formatted strings in cache
            cached_data[reg.id] = {key: f"{value:g}" for key, value in dt.items()}

    # Persist the updated cache data with 1-day timeout
    cache.set(key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


def get_registration_accounting_cache(run):
    """Get or create registration accounting cache for a run.

    Args:
        run: Run instance

    Returns:
        dict: Cached registration accounting data
    """
    key = get_registration_accounting_cache_key(run.id)
    res = cache.get(key)

    if res is None:
        res = update_registration_accounting_cache(run)
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def update_registration_accounting_cache(run):
    """Update registration accounting cache for the given run.

    Args:
        run: Run instance to update accounting cache for

    Returns:
        dict: Updated registration accounting data keyed by registration ID
    """
    features, reg_tickets, cache_aip = _get_accounting_context(run)

    # Process all active registrations
    regs = Registration.objects.filter(run=run, cancellation_date__isnull=True)
    res = {}

    for reg in regs:
        dt = _calculate_registration_accounting(reg, reg_tickets, cache_aip, features)
        res[reg.id] = {key: f"{value:g}" for key, value in dt.items()}

    return res


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
            - Basic financial fields (tot_payed, tot_iscr, quota, etc.)
            - Payment breakdown by type (pay_a, pay_b, pay_c)
            - Remaining balance and ticket pricing information
    """
    dt = {}
    max_rounding = 0.05

    # Extract and round basic registration financial fields
    for k in ["tot_payed", "tot_iscr", "quota", "deadline", "pay_what", "surcharge"]:
        dt[k] = round_to_nearest_cent(getattr(reg, k, 0))

    # Process token/credit payments if the feature is enabled
    if isinstance(features, dict) and "token_credit" in features:
        if reg.member_id in cache_aip:
            # Extract credit (b) and token (c) payments from cache
            for pay in ["b", "c"]:  # b=CREDIT, c=TOKEN
                v = 0
                if pay in cache_aip[reg.member_id]:
                    v = cache_aip[reg.member_id][pay]
                dt["pay_" + pay] = float(v)
            # Calculate cash payment (a) as remainder
            dt["pay_a"] = dt["tot_payed"] - (dt["pay_b"] + dt["pay_c"])
        else:
            # No cached payments, all payment is cash
            dt["pay_a"] = dt["tot_payed"]

    # Calculate remaining balance and apply rounding threshold
    dt["remaining"] = dt["tot_iscr"] - dt["tot_payed"]
    if abs(dt["remaining"]) < max_rounding:
        dt["remaining"] = 0

    # Add ticket pricing breakdown if ticket exists
    if reg.ticket_id in reg_tickets:
        t = reg_tickets[reg.ticket_id]
        dt["ticket_price"] = t.price
        # Add custom payment amount to base ticket price
        if reg.pay_what:
            dt["ticket_price"] += reg.pay_what
        # Calculate additional options cost
        dt["options_price"] = reg.tot_iscr - dt["ticket_price"]

    return dt
