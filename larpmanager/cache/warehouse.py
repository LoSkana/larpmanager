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

from larpmanager.models.association import Association
from larpmanager.models.miscellanea import WarehouseItem

logger = logging.getLogger(__name__)


def get_association_warehouse_key(association_id: int) -> str:
    """Generate cache key for association warehouse items.

    Args:
        association_id: The ID of the association

    Returns:
        str: Cache key in format 'association__warehouse__{association_id}'

    """
    return f"association__warehouse__{association_id}"


def clear_association_warehouse_cache(association_id: int) -> None:
    """Reset association warehouse cache for given association ID.

    This function clears the cache for the specified association to ensure
    data consistency when warehouse item relationships change.

    Args:
        association_id: The ID of the association whose cache should be cleared.

    Returns:
        None

    """
    cache_key = get_association_warehouse_key(association_id)
    cache.delete(cache_key)
    logger.debug("Reset warehouse cache for association %s", association_id)


def build_warehouse_dict(items: list) -> dict[str, Any]:
    """Build warehouse dictionary with list and count.

    Args:
        items: List of (id, name) tuples

    Returns:
        Dict with "list" and "count" keys

    """
    return {"list": items, "count": len(items)}


def get_warehouse_item_rels(item: WarehouseItem) -> dict[str, Any]:
    """Get warehouse item relationships.

    Retrieves all tags and assignments associated with the given warehouse item
    and formats them into a relationship dictionary structure.

    Args:
        item (WarehouseItem): The WarehouseItem instance to get relationships for.

    Returns:
        dict[str, Any]: Dictionary containing relationship data with the structure:
            {
                'tag_rels': {
                    'list': [(tag_id, tag_name), ...],
                    'count': int
                },
                'assignment_rels': {
                    'list': [(assignment_id, area_name), ...],
                    'count': int
                }
            }
            Returns empty dict if an error occurs.

    Raises:
        Exception: Logs any database or processing errors and returns empty dict.

    """
    item_relations = {}

    try:
        # Get all tags associated with this item
        item_tags = item.tags.all()
        tag_id_name_tuples = [(tag.id, tag.name) for tag in item_tags]
        item_relations["tag_rels"] = build_warehouse_dict(tag_id_name_tuples)

        # Get all assignments associated with this item
        item_assignments = item.assignments.all()
        assignment_id_area_tuples = [(assignment.id, assignment.area.name) for assignment in item_assignments]
        item_relations["assignment_rels"] = build_warehouse_dict(assignment_id_area_tuples)

    except Exception:
        # Log error with full traceback for debugging
        logger.exception("Error getting relationships for warehouse item %s", item.id)

        # Return empty dict on error to prevent downstream issues
        item_relations = {}

    return item_relations


def get_association_warehouse_cache(association: Association) -> dict[str, Any]:
    """Get association warehouse relationships from cache, initializing if not present.

    Retrieves cached relationship data for the specified association. If no cached
    data exists, initializes the cache with fresh relationship data.

    Args:
        association (Association): The Association instance to get warehouse relationships for.

    Returns:
        dict[str, Any]: Dictionary containing cached relationship data for warehouse items.

    Note:
        Cache miss will trigger full relationship initialization via
        init_association_warehouse_all().

    """
    # Generate cache key for this specific association
    cache_key = get_association_warehouse_key(association.id)

    # Attempt to retrieve cached relationships
    cached_relationships = cache.get(cache_key)

    # Initialize cache if no data found
    if cached_relationships is None:
        logger.debug("Cache miss for warehouse association %s, initializing", association.id)
        cached_relationships = init_association_warehouse_all(association)

    return cached_relationships


def init_association_warehouse_all(association: Association) -> dict[str, dict[int, dict[str, Any]]]:
    """Initialize all warehouse item relationships for an association and cache the result.

    Builds a complete relationship cache for all warehouse items in the association,
    including tag and assignment relationships.

    Args:
        association: The Association instance to initialize warehouse relationships for

    Returns:
        Dictionary with relationship data structure:
        {
            'warehouse_items': {
                item_id: {
                    'tag_rels': [(tag_id, tag_name), ...],
                    'assignment_rels': [(assignment_id, area_name), ...]
                }
            }
        }

    Raises:
        Exception: Any error during relationship initialization is logged
                  and an empty dict is returned

    """
    relationship_cache: dict[str, dict[int, dict[str, Any]]] = {}

    try:
        # Initialize the cache section for warehouse items
        relationship_cache["warehouse_items"] = {}

        # Get all warehouse items associated with the association
        warehouse_items = WarehouseItem.objects.filter(association_id=association.id, deleted=None)

        # Build relationships for each warehouse item
        for item in warehouse_items:
            relationship_cache["warehouse_items"][item.id] = get_warehouse_item_rels(item)

        # Cache the complete relationship data structure
        cache_key = get_association_warehouse_key(association.id)
        cache.set(cache_key, relationship_cache, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug("Cached warehouse relationships for association %s", association.id)

    except Exception:
        # Log the error with full traceback and return empty result
        logger.exception("Error initializing warehouse relationships for association %s", association.id)
        relationship_cache = {}

    return relationship_cache


def update_warehouse_cache_section(association_id: int, item_id: int, data: dict[str, Any]) -> None:
    """Update a specific warehouse item in the association cache.

    Args:
        association_id: The association ID
        item_id: ID of the warehouse item to update
        data: Data to store for this item

    """
    try:
        cache_key = get_association_warehouse_key(association_id)
        cached_association_data = cache.get(cache_key)

        if cached_association_data is None:
            logger.debug("Cache miss during warehouse item update for association %s, reinitializing", association_id)
            # We need to get the association to reinitialize
            association = Association.objects.get(id=association_id)
            init_association_warehouse_all(association)
            return

        if "warehouse_items" not in cached_association_data:
            cached_association_data["warehouse_items"] = {}

        cached_association_data["warehouse_items"][item_id] = data
        cache.set(cache_key, cached_association_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug("Updated warehouse item %s relationships in cache", item_id)

    except Exception:
        logger.exception("Error updating warehouse item %s relationships", item_id)
        clear_association_warehouse_cache(association_id)


def remove_warehouse_item_from_cache(association_id: int, item_id: int) -> None:
    """Remove a warehouse item from the association cache.

    Args:
        association_id: The association ID
        item_id: ID of the warehouse item to remove

    """
    try:
        cache_key = get_association_warehouse_key(association_id)
        cached_data = cache.get(cache_key)
        if cached_data and "warehouse_items" in cached_data and item_id in cached_data["warehouse_items"]:
            del cached_data["warehouse_items"][item_id]
            cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
            logger.debug("Removed warehouse item %s from cache", item_id)
    except Exception:
        logger.exception("Error removing warehouse item %s from cache", item_id)
        clear_association_warehouse_cache(association_id)


def refresh_warehouse_item_relationships(item: WarehouseItem) -> None:
    """Update warehouse item relationships in cache.

    Updates the cached relationship data for a specific warehouse item.
    If the cache doesn't exist, it will be initialized for the entire association.

    Args:
        item (WarehouseItem): The WarehouseItem instance to update relationships for

    Returns:
        None

    """
    # Get the current warehouse item relationship data
    item_relationship_data = get_warehouse_item_rels(item)

    # Update the cache with the item's relationship data
    update_warehouse_cache_section(item.association_id, item.id, item_relationship_data)


def on_warehouse_item_tags_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: WarehouseItem,
    action: str,
    pk_set: set[int] | None,  # noqa: ARG001
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle warehouse item tag relationship changes.

    Updates warehouse item cache when tag relationships change.
    This signal handler is triggered when tags are added to or removed
    from a warehouse item's tags many-to-many relationship.

    Args:
        sender: The through model class that manages the M2M relationship
        instance: The WarehouseItem instance whose relationships are changing
        action: The type of change being performed on the relationship.
            Common values include 'post_add', 'post_remove', 'post_clear'
        pk_set: Set of primary keys of the WarehouseTag objects being affected.
            May be None for certain actions like 'post_clear'
        **kwargs: Additional keyword arguments passed by the Django signal system

    Returns:
        None

    """
    if action in ("post_add", "post_remove", "post_clear"):
        # Update the warehouse item cache
        refresh_warehouse_item_relationships(instance)
