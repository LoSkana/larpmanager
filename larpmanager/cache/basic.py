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

from typing import TypedDict

from django.conf import settings as conf_settings
from django.core.cache import cache

from larpmanager.models.association import Association, Currency
from larpmanager.models.event import Event, Run


class RunBasicCache(TypedDict):
    """Shape of the dict returned by get_run_basic_cache."""

    event_id: int
    association_id: int
    association_slug: str
    parent_id: int | None
    slug: str
    currency_symbol: str
    number: int
    media_token: str


def association_basic_cache_key(association_id: int) -> str:
    """Generate cache key for an association's basic info."""
    return f"association_basic_{association_id}"


def get_association_basic_cache(association_id: int) -> dict:
    """Get an association basic data from cache if available."""
    cache_key = association_basic_cache_key(association_id)
    data = cache.get(cache_key)
    if data is not None and "domain" not in data:
        data = None
    if data is None:
        association = (
            Association.objects.select_related("skin")
            .only("payment_currency", "slug", "name", "skin__domain")
            .get(id=association_id)
        )
        if not association.payment_currency:
            association.payment_currency = Currency.EUR
        data = {
            "currency_symbol": association.get_currency_symbol(),
            "slug": association.slug,
            "name": association.name,
            "domain": association.skin.domain,
        }
        cache.set(cache_key, data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return data


def reset_association_basic_cache(association_id: int) -> None:
    """Invalidate the cached basic info for an association."""
    cache.delete(association_basic_cache_key(association_id))
    reset_association_events_runs_basic_cache(association_id)


def reset_association_events_runs_basic_cache(association_id: int) -> None:
    """Invalidate the cached basic info for all events and runs of an association."""
    event_ids = list(Event.all_objects.filter(association_id=association_id).values_list("id", flat=True))
    if event_ids:
        cache.delete_many([event_basic_cache_key(event_id) for event_id in event_ids])
        run_ids = Run.all_objects.filter(event_id__in=event_ids).values_list("id", flat=True)
        cache.delete_many([run_basic_cache_key(run_id) for run_id in run_ids])


def event_basic_cache_key(event_id: int) -> str:
    """Generate cache key for an event's basic info."""
    return f"event_basic_{event_id}"


def get_event_basic_cache(event_id: int) -> dict:
    """Get an event basic data from cache if available."""
    cache_key = event_basic_cache_key(event_id)
    data = cache.get(cache_key)
    if data is None:
        association_id, parent_id, slug, name = Event.all_objects.values_list(
            "association_id", "parent_id", "slug", "name"
        ).get(id=event_id)
        association_cache = get_association_basic_cache(association_id)
        data = {
            "association_id": association_id,
            "association_slug": association_cache["slug"],
            "parent_id": parent_id,
            "slug": slug,
            "name": name,
            "currency_symbol": association_cache["currency_symbol"],
        }
        cache.set(cache_key, data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return data


def reset_event_basic_cache(event_id: int) -> None:
    """Invalidate the cached basic info for an event."""
    cache.delete(event_basic_cache_key(event_id))


def run_basic_cache_key(run_id: int) -> str:
    """Generate cache key for a run's basic info."""
    return f"run_basic_{run_id}"


def get_run_basic_cache(run_id: int) -> RunBasicCache:
    """Get a run basic data from cache if available."""
    cache_key = run_basic_cache_key(run_id)
    data = cache.get(cache_key)
    if data is None:
        event_id, number, media_token = Run.all_objects.values_list("event_id", "number", "media_token").get(id=run_id)
        event_cache = get_event_basic_cache(event_id)
        data = {
            "event_id": event_id,
            "association_id": event_cache["association_id"],
            "association_slug": event_cache["association_slug"],
            "parent_id": event_cache["parent_id"],
            "slug": event_cache["slug"],
            "currency_symbol": event_cache["currency_symbol"],
            "number": number,
            "media_token": media_token,
        }
        cache.set(cache_key, data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return data


def get_run_event_id(run_id: int) -> int:
    """Get the event id for a run from cache."""
    return get_run_basic_cache(run_id)["event_id"]


def get_run_association_id(run_id: int) -> int:
    """Get the association id for a run from cache."""
    return get_run_basic_cache(run_id)["association_id"]


def get_event_association_id(event_id: int) -> int:
    """Get the association id for an event from cache."""
    return get_event_basic_cache(event_id)["association_id"]


def reset_run_basic_cache(run_id: int) -> None:
    """Invalidate the cached basic info for a run."""
    cache.delete(run_basic_cache_key(run_id))
