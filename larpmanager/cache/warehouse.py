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
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings as conf_settings
from django.core.cache import cache

from larpmanager.models.miscellanea import WarehouseItem

logger = logging.getLogger(__name__)


def get_association_warehouse_key(association_id: int) -> str:
    """Generate cache key for association warehouse items."""
    return f"association__warehouse__{association_id}"


def clear_association_warehouse_cache(association_id: int) -> None:
    """Reset warehouse cache for given association ID."""
    cache_key = get_association_warehouse_key(association_id)
    cache.delete(cache_key)
    logger.debug("Reset warehouse cache for association %s", association_id)


def build_item_data(item: WarehouseItem) -> dict[str, Any]:
    """Build cached data for a warehouse item."""
    return {
        "id": item.id,
        "name": item.name,
        "tags": [(tag.id, tag.name) for tag in item.tags.all()],
    }


def init_association_warehouse_cache(association_id: int) -> dict[int, dict[str, Any]]:
    """Initialize warehouse cache for an association.

    Builds a complete warehouse cache for all items in the association,
    including prefetched tag relationships.

    Args:
        association_id: The Association ID to initialize cache for

    Returns:
        Dictionary with warehouse item data organized by item ID:
        {
            item_id: {
                'id': item_id,
                'name': item_name,
                'tags': [(tag_id, tag_name), ...]
            }
        }

    """
    warehouse_cache: dict[int, dict[str, Any]] = {}

    try:
        # Get all warehouse items for the association with prefetched tags
        items = WarehouseItem.objects.filter(association_id=association_id).prefetch_related("tags")

        # Build cache data for each item
        for item in items:
            warehouse_cache[item.id] = build_item_data(item)

        # Cache the complete data structure
        cache_key = get_association_warehouse_key(association_id)
        cache.set(cache_key, warehouse_cache, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug("Cached warehouse items for association %s (%s items)", association_id, len(warehouse_cache))

    except Exception:
        logger.exception("Error initializing warehouse cache for association %s", association_id)
        warehouse_cache = {}

    return warehouse_cache


def get_association_warehouse_cache(association_id: int) -> dict[int, dict[str, Any]]:
    """Get warehouse cache for an association, initializing if not present.

    Retrieves cached warehouse data for the specified association. If no cached
    data exists, initializes the cache with fresh data.

    Args:
        association_id: The Association ID to get warehouse cache for

    Returns:
        dict[int, dict[str, Any]]: Dictionary containing cached warehouse data

    """
    cache_key = get_association_warehouse_key(association_id)
    cached_warehouse = cache.get(cache_key)

    if cached_warehouse is None:
        logger.debug("Cache miss for association %s warehouse, initializing", association_id)
        cached_warehouse = init_association_warehouse_cache(association_id)

    return cached_warehouse


def update_warehouse_item_cache(item: WarehouseItem) -> None:
    """Update cache for a specific warehouse item.

    Args:
        item: The WarehouseItem instance to update in cache

    """
    try:
        cache_key = get_association_warehouse_key(item.association_id)
        cached_data = cache.get(cache_key)

        if cached_data is None:
            logger.debug("Cache miss during warehouse item update, reinitializing")
            init_association_warehouse_cache(item.association_id)
            return

        # Update the specific item's data
        cached_data[item.id] = build_item_data(item)
        cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug("Updated warehouse item %s in cache", item.uui)

    except Exception:
        logger.exception("Error updating warehouse item %s cache", item.id)
        clear_association_warehouse_cache(item.association_id)


def remove_warehouse_item_from_cache(item_id: int, association_id: int) -> None:
    """Remove a warehouse item from cache.

    Args:
        item_id: The ID of the item to remove
        association_id: The association ID

    """
    try:
        cache_key = get_association_warehouse_key(association_id)
        cached_data = cache.get(cache_key)
        if cached_data and item_id in cached_data:
            del cached_data[item_id]
            cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
            logger.debug("Removed warehouse item %s from cache", item_id)
    except Exception:
        logger.exception("Error removing warehouse item %s from cache", item_id)
        clear_association_warehouse_cache(association_id)


def on_warehouse_item_tags_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: WarehouseItem,
    action: str,
    pk_set: set[int] | None,  # noqa: ARG001
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle warehouse item-tag relationship changes.

    Updates item cache when tags are added to or removed from items.

    Args:
        sender: The through model class that manages the M2M relationship
        instance: The WarehouseItem instance whose tags are changing
        action: The type of change being performed on the relationship
        pk_set: Set of primary keys of the WarehouseTag objects being affected
        **kwargs: Additional keyword arguments passed by the Django signal system

    Returns:
        None

    """
    if action in ("post_add", "post_remove", "post_clear"):
        update_warehouse_item_cache(instance)
