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
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from larpmanager.cache.feature import get_event_features
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemOther,
    AccountingItemPayment,
    PaymentChoices,
)
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


def get_registration_accounting_cache_key(run):
    """Generate cache key for registration accounting data.

    Args:
        run: Run instance

    Returns:
        str: Cache key for registration accounting data
    """
    return f"reg_accounting_{run.id}"


def reset_registration_accounting_cache(run):
    """Reset registration accounting cache for a run.

    Args:
        run: Run instance to reset cache for
    """
    cache.delete(get_registration_accounting_cache_key(run))


def _get_accounting_context(run, member_filter=None):
    """Get the context data needed for accounting calculations.

    Args:
        run: Run instance
        member_filter: Optional member ID to filter payments for

    Returns:
        tuple: (features, reg_tickets, cache_aip)
    """
    features = get_event_features(run.event.id)
    if not isinstance(features, dict):
        features = {}

    # Get all tickets for this event
    reg_tickets = {}
    for t in RegistrationTicket.objects.filter(event=run.event).order_by("-price"):
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


def update_member_accounting_cache(run, member_id):
    """Update accounting cache for a specific member's registrations in a run.

    Args:
        run: Run instance
        member_id: Member ID to update accounting data for
    """
    key = get_registration_accounting_cache_key(run)
    cached_data = cache.get(key)

    if not cached_data:
        # If cache doesn't exist, create it entirely
        cached_data = update_registration_accounting_cache(run)
        return

    # Get registrations for this member in this run
    member_regs = Registration.objects.filter(run=run, member_id=member_id, cancellation_date__isnull=True)

    if not member_regs.exists():
        # Remove any cached data for this member's registrations
        for reg_id in list(cached_data.keys()):
            try:
                reg = Registration.objects.get(id=reg_id, member_id=member_id)
                if reg.run_id == run.id:
                    cached_data.pop(reg_id, None)
            except ObjectDoesNotExist:
                pass
    else:
        # Recalculate accounting data for this member's registrations
        features, reg_tickets, cache_aip = _get_accounting_context(run, member_id)

        # Update cache for each registration of this member
        for reg in member_regs:
            dt = _calculate_registration_accounting(reg, reg_tickets, cache_aip, features)
            cached_data[reg.id] = {key: f"{value:g}" for key, value in dt.items()}

    # Update the cache
    cache.set(key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


def get_registration_accounting_cache(run):
    """Get or create registration accounting cache for a run.

    Args:
        run: Run instance

    Returns:
        dict: Cached registration accounting data
    """
    key = get_registration_accounting_cache_key(run)
    res = cache.get(key)

    if not res:
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


def _calculate_registration_accounting(reg, reg_tickets, cache_aip, features):
    """Calculate accounting data for a single registration.

    Args:
        reg: Registration instance
        reg_tickets: Dictionary of ticket ID to RegistrationTicket mapping
        cache_aip: Cached accounting payment data
        features: Dictionary of enabled features for the event

    Returns:
        dict: Registration accounting data
    """
    dt = {}
    max_rounding = 0.05

    # Basic registration financial fields
    for k in ["tot_payed", "tot_iscr", "quota", "deadline", "pay_what", "surcharge"]:
        dt[k] = round_to_nearest_cent(getattr(reg, k, 0))

    # Handle token/credit payments if feature is enabled
    if isinstance(features, dict) and "token_credit" in features:
        if reg.member_id in cache_aip:
            for pay in ["b", "c"]:  # b=CREDIT, c=TOKEN
                v = 0
                if pay in cache_aip[reg.member_id]:
                    v = cache_aip[reg.member_id][pay]
                dt["pay_" + pay] = float(v)
            dt["pay_a"] = dt["tot_payed"] - (dt["pay_b"] + dt["pay_c"])
        else:
            dt["pay_a"] = dt["tot_payed"]

    # Calculate remaining balance
    dt["remaining"] = dt["tot_iscr"] - dt["tot_payed"]
    if abs(dt["remaining"]) < max_rounding:
        dt["remaining"] = 0

    # Add ticket price information
    if reg.ticket_id in reg_tickets:
        t = reg_tickets[reg.ticket_id]
        dt["ticket_price"] = t.price
        if reg.pay_what:
            dt["ticket_price"] += reg.pay_what
        dt["options_price"] = reg.tot_iscr - dt["ticket_price"]

    return dt


@receiver(post_save, sender=Registration)
def post_save_registration_accounting_cache(sender, instance, created, **kwargs):
    """Reset accounting cache when a registration is saved."""
    reset_registration_accounting_cache(instance.run)


@receiver(post_delete, sender=Registration)
def post_delete_registration_accounting_cache(sender, instance, **kwargs):
    """Reset accounting cache when a registration is deleted."""
    reset_registration_accounting_cache(instance.run)


@receiver(post_save, sender=RegistrationTicket)
def post_save_ticket_accounting_cache(sender, instance, created, **kwargs):
    """Reset accounting cache when a ticket is saved."""
    for run in instance.event.runs.all():
        reset_registration_accounting_cache(run)


@receiver(post_delete, sender=RegistrationTicket)
def post_delete_ticket_accounting_cache(sender, instance, **kwargs):
    """Reset accounting cache when a ticket is deleted."""
    for run in instance.event.runs.all():
        reset_registration_accounting_cache(run)


@receiver(post_save, sender=AccountingItemPayment)
def post_save_payment_accounting_cache(sender, instance, created, **kwargs):
    """Update accounting cache when a payment is saved."""
    if instance.reg and instance.reg.run:
        update_member_accounting_cache(instance.reg.run, instance.member_id)


@receiver(post_delete, sender=AccountingItemPayment)
def post_delete_payment_accounting_cache(sender, instance, **kwargs):
    """Update accounting cache when a payment is deleted."""
    if instance.reg and instance.reg.run:
        update_member_accounting_cache(instance.reg.run, instance.member_id)


@receiver(post_save, sender=AccountingItemDiscount)
def post_save_discount_accounting_cache(sender, instance, created, **kwargs):
    """Update accounting cache when a discount is saved."""
    if instance.run and instance.member_id:
        update_member_accounting_cache(instance.run, instance.member_id)


@receiver(post_delete, sender=AccountingItemDiscount)
def post_delete_discount_accounting_cache(sender, instance, **kwargs):
    """Update accounting cache when a discount is deleted."""
    if instance.run and instance.member_id:
        update_member_accounting_cache(instance.run, instance.member_id)


@receiver(post_save, sender=AccountingItemOther)
def post_save_other_accounting_cache(sender, instance, created, **kwargs):
    """Update accounting cache when an other accounting item is saved."""
    if instance.run and instance.member_id:
        update_member_accounting_cache(instance.run, instance.member_id)


@receiver(post_delete, sender=AccountingItemOther)
def post_delete_other_accounting_cache(sender, instance, **kwargs):
    """Update accounting cache when an other accounting item is deleted."""
    if instance.run and instance.member_id:
        update_member_accounting_cache(instance.run, instance.member_id)
