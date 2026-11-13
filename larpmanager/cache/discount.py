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
"""Temporary discount reservations, kept in cache until the registration is saved."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

from django.core.cache import cache
from django.db import transaction

from larpmanager.models.accounting import Discount

if TYPE_CHECKING:
    from collections.abc import Iterator

DISCOUNT_RESERVATION_SECONDS = 15 * 60

# Expired reservations are kept this long, to warn the member that the discount was not applied
DISCOUNT_RESERVATION_RETENTION_SECONDS = 24 * 60 * 60

DISCOUNT_RESERVATION_CACHE_TIMEOUT = DISCOUNT_RESERVATION_SECONDS + DISCOUNT_RESERVATION_RETENTION_SECONDS


def discount_reservations_key(run_id: int, discount_id: int) -> str:
    """Return the cache key holding the reservations of a discount on a run."""
    return f"discount_reservations_{run_id}_{discount_id}"


@contextmanager
def _reservations_lock(discount_id: int) -> Iterator[None]:
    """Serialize read-modify-write of a discount reservations entry by locking the discount row."""
    with transaction.atomic():
        Discount.objects.select_for_update().filter(pk=discount_id).exists()
        yield


def _active_reservations(reservations: dict | None) -> dict[int, float]:
    """Return only the reservations not yet expired, as {member_id: expires_timestamp}."""
    now = time.time()
    return {int(member_id): expires for member_id, expires in (reservations or {}).items() if expires > now}


def _retained_reservations(reservations: dict | None) -> dict[int, float]:
    """Return the reservations not yet expired or expired within the retention window."""
    threshold = time.time() - DISCOUNT_RESERVATION_RETENTION_SECONDS
    return {int(member_id): expires for member_id, expires in (reservations or {}).items() if expires > threshold}


def get_discount_reservations(run_id: int, discount_id: int) -> dict[int, float]:
    """Return active reservations of a discount on a run."""
    return _active_reservations(cache.get(discount_reservations_key(run_id, discount_id)))


def count_discounts_reservations(run_id: int, discount_ids: list[int]) -> dict[int, int]:
    """Return the number of active reservations for each of the given discounts on a run."""
    keys = {discount_reservations_key(run_id, discount_id): discount_id for discount_id in discount_ids}
    return {
        keys[key]: len(_active_reservations(reservations)) for key, reservations in cache.get_many(list(keys)).items()
    }


def reserve_discount(run_id: int, discount_id: int, member_id: int) -> float:
    """Reserve a discount for a member and return the reservation expiration timestamp."""
    key = discount_reservations_key(run_id, discount_id)
    with _reservations_lock(discount_id):
        reservations = _retained_reservations(cache.get(key))
        expires = time.time() + DISCOUNT_RESERVATION_SECONDS
        reservations[member_id] = expires
        cache.set(key, reservations, timeout=DISCOUNT_RESERVATION_CACHE_TIMEOUT)
    return expires


def get_member_reservations(run_id: int, discount_ids: list[int], member_id: int) -> dict[int, float]:
    """Return the member active reservations among the given discounts, as {discount_id: expires_timestamp}."""
    keys = {discount_reservations_key(run_id, discount_id): discount_id for discount_id in discount_ids}
    result = {}
    for key, reservations in cache.get_many(list(keys)).items():
        expires = _active_reservations(reservations).get(member_id)
        if expires:
            result[keys[key]] = expires
    return result


def get_member_expired_reservations(run_id: int, discount_ids: list[int], member_id: int) -> list[int]:
    """Return the ids of the given discounts whose reservation by the member has expired."""
    keys = {discount_reservations_key(run_id, discount_id): discount_id for discount_id in discount_ids}
    now = time.time()
    return [
        keys[key]
        for key, reservations in cache.get_many(list(keys)).items()
        if 0 < _retained_reservations(reservations).get(member_id, 0) <= now
    ]


def clear_member_reservation(run_id: int, discount_id: int, member_id: int) -> None:
    """Remove the reservation of a discount for a member, expired or not."""
    key = discount_reservations_key(run_id, discount_id)
    with _reservations_lock(discount_id):
        reservations = _retained_reservations(cache.get(key))
        if reservations.pop(member_id, None) is None:
            return
        if reservations:
            cache.set(key, reservations, timeout=DISCOUNT_RESERVATION_CACHE_TIMEOUT)
        else:
            cache.delete(key)
