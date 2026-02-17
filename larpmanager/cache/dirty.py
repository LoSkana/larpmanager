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
"""Shared dirty-flag helpers for PX and rels cache namespaces.

Each namespace (``"px"``, ``"rels"``) gets its own per-item and event-level hint
keys so the two systems never collide.  Callers create thin :func:`functools.partial`
aliases so existing code keeps the original private-looking names.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.core.cache import cache

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def get_dirty_key(cache_ns: str, section: str, item_id: int) -> str:
    """Per-item dirty flag cache key."""
    return f"{cache_ns}_dirty__{section}__{item_id}"


def get_has_dirty_key(cache_ns: str, event_id: int) -> str:
    """Event-level hint: True when at least one item in this event is dirty."""
    return f"{cache_ns}_has_dirty__{event_id}"


def resolve_dirty_section(
    cache_ns: str,
    event_id: int,
    cached_data: dict[str, Any],
    section: str,
    model_class: type,
    get_rels_func: Callable,
) -> bool:
    """Recompute dirty items for one cache section in-place.

    Args:
        cache_ns: Namespace prefix.
        event_id: Event whose cache is being resolved (used for logging).
        cached_data: The in-memory cache dict (modified in-place).
        section: Cache section name.
        model_class: Django model class for the section.
        get_rels_func: Function ``(item) -> dict`` that builds relationship data.

    Returns:
        ``True`` if at least one dirty item was resolved, ``False`` otherwise.
    """
    item_ids = list(cached_data.get(section, {}).keys())
    if not item_ids:
        return False

    dirty_key_to_id = {get_dirty_key(cache_ns, section, iid): iid for iid in item_ids}
    dirty_found = cache.get_many(list(dirty_key_to_id.keys()))
    if not dirty_found:
        return False

    dirty_ids = [dirty_key_to_id[k] for k in dirty_found]
    for item in model_class.objects.filter(id__in=dirty_ids):
        cached_data[section][item.id] = get_rels_func(item)
        logger.debug("Resolved dirty %s %s on-demand for event %s", section, item.id, event_id)

    cache.delete_many([get_dirty_key(cache_ns, section, iid) for iid in dirty_ids])
    return True


def mark_dirty(cache_ns: str, section: str, item_ids: list[int], event_id: int | None) -> None:
    """Mark items as dirty and set the event-level hint.

    Args:
        cache_ns: Namespace prefix.
        section: Cache section name.
        item_ids: IDs of items to mark dirty.
        event_id: Event the items belong to; ``None`` skips the hint.
    """
    for item_id in item_ids:
        cache.set(get_dirty_key(cache_ns, section, item_id), "1")
    if event_id is not None:
        cache.set(get_has_dirty_key(cache_ns, event_id), "1")


def refresh_if_dirty(cache_ns: str, section: str, items: list, refresh_func: Callable) -> None:
    """Refresh items in background, skipping those already resolved on-demand.

    Args:
        cache_ns: Namespace prefix.
        section: Cache section name.
        items: Model instances to (conditionally) refresh.
        refresh_func: Function that rebuilds and stores one item's cache entry.
    """
    for item in items:
        dirty_key = get_dirty_key(cache_ns, section, item.id)
        if not cache.get(dirty_key):
            logger.debug("%s %s already resolved on-demand, skipping background refresh", section, item.id)
            continue
        refresh_func(item)
        cache.delete(dirty_key)
