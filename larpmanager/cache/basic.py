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
"""Cache the minimal Event/Run attributes callers need without loading the full object."""

from __future__ import annotations

from babel.numbers import get_currency_symbol as babel_get_currency_symbol
from django.conf import settings as conf_settings
from django.core.cache import cache

from larpmanager.models.association import Association, Currency
from larpmanager.models.event import Event, Run


def association_basic_cache_key(association_id: int) -> str:
    """Generate cache key for an association's basic info."""
    return f"association_basic_{association_id}"


def get_association_basic_cache(association_id: int) -> dict:
    """Get an association basic data from cache if available."""
    cache_key = association_basic_cache_key(association_id)
    data = cache.get(cache_key)
    if data is None:
        payment_currency = Association.objects.values_list("payment_currency", flat=True).get(id=association_id)
        currency_symbol = babel_get_currency_symbol(Currency(payment_currency or Currency.EUR).label)
        data = {"currency_symbol": currency_symbol}
        cache.set(cache_key, data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return data


def reset_association_basic_cache(association_id: int) -> None:
    """Invalidate the cached basic info for an association."""
    cache.delete(association_basic_cache_key(association_id))


def event_basic_cache_key(event_id: int) -> str:
    """Generate cache key for an event's basic info."""
    return f"event_basic_{event_id}"


def get_event_basic_cache(event_id: int) -> dict:
    """Get an event basic data from cache if available."""
    cache_key = event_basic_cache_key(event_id)
    data = cache.get(cache_key)
    if data is None:
        association_id, parent_id, slug = Event.objects.values_list("association_id", "parent_id", "slug").get(
            id=event_id
        )
        currency_symbol = get_association_basic_cache(association_id)["currency_symbol"]
        data = {
            "association_id": association_id,
            "parent_id": parent_id,
            "slug": slug,
            "currency_symbol": currency_symbol,
        }
        cache.set(cache_key, data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return data


def reset_event_basic_cache(event_id: int) -> None:
    """Invalidate the cached basic info for an event."""
    cache.delete(event_basic_cache_key(event_id))


def run_basic_cache_key(run_id: int) -> str:
    """Generate cache key for a run's basic info."""
    return f"run_basic_{run_id}"


def get_run_basic_cache(run_id: int) -> dict:
    """Get a run basic data from cache if available."""
    cache_key = run_basic_cache_key(run_id)
    data = cache.get(cache_key)
    if data is None:
        event_id, number, media_token = Run.objects.values_list("event_id", "number", "media_token").get(id=run_id)
        event_cache = get_event_basic_cache(event_id)
        data = {
            "event_id": event_id,
            "association_id": event_cache["association_id"],
            "parent_id": event_cache["parent_id"],
            "slug": event_cache["slug"],
            "currency_symbol": event_cache["currency_symbol"],
            "number": number,
            "media_token": media_token,
        }
        cache.set(cache_key, data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return data


def reset_run_basic_cache(run_id: int) -> None:
    """Invalidate the cached basic info for a run."""
    cache.delete(run_basic_cache_key(run_id))
