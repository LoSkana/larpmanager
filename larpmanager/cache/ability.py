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

from larpmanager.cache.feature import get_event_features
from larpmanager.models.event import Event
from larpmanager.models.experience import AbilityPx

logger = logging.getLogger(__name__)


def get_event_ability_key(event_id: int) -> str:
    """Generate cache key for event abilities.

    Args:
        event_id: The ID of the event

    Returns:
        str: Cache key in format 'event__ability__{event_id}'

    """
    return f"event__ability__{event_id}"


def clear_event_ability_cache(event_id: int) -> None:
    """Reset event ability cache for given event ID.

    This function clears the cache for the specified event to ensure
    data consistency when ability relationships change.

    Args:
        event_id: The ID of the event whose cache should be cleared.

    Returns:
        None

    """
    cache_key = get_event_ability_key(event_id)
    cache.delete(cache_key)
    logger.debug("Reset ability cache for event %s", event_id)


def build_ability_dict(character_items: list) -> dict[str, Any]:
    """Build ability dictionary with list and count.

    Args:
        character_items: List of (id, name) tuples

    Returns:
        Dict with "list" and "count" keys

    """
    return {"list": character_items, "count": len(character_items)}


def get_event_ability_rels(ability: AbilityPx) -> dict[str, Any]:
    """Get ability relationships for a specific ability.

    Retrieves all characters associated with the given ability and formats
    them into a relationship dictionary structure.

    Args:
        ability (AbilityPx): The AbilityPx instance to get relationships for.

    Returns:
        dict[str, Any]: Dictionary containing relationship data with the structure:
            {
                'character_rels': {
                    'list': [(char_id, char_name), ...],
                    'count': int
                }
            }
            Returns empty dict if an error occurs.

    Raises:
        Exception: Logs any database or processing errors and returns empty dict.

    """
    ability_relations = {}

    try:
        # Get all characters associated with this ability
        ability_characters = ability.characters.all()

        # Build list of character ID and name tuples
        character_id_name_tuples = [(character.id, character.name) for character in ability_characters]

        # Structure the relationship data using helper function
        ability_relations["character_rels"] = build_ability_dict(character_id_name_tuples)

    except Exception:
        # Log error with full traceback for debugging
        logger.exception("Error getting relationships for ability %s", ability.id)

        # Return empty dict on error to prevent downstream issues
        ability_relations = {}

    return ability_relations


def get_event_ability_cache(event: Event) -> dict[str, Any]:
    """Get event ability relationships from cache, initializing if not present.

    Retrieves cached relationship data for the specified event. If no cached
    data exists, initializes the cache with fresh relationship data.

    Args:
        event (Event): The Event instance to get ability relationships for.

    Returns:
        dict[str, Any]: Dictionary containing cached relationship data for abilities.

    Note:
        Cache miss will trigger full relationship initialization via
        init_event_ability_all().

    """
    # Generate cache key for this specific event
    cache_key = get_event_ability_key(event.id)

    # Attempt to retrieve cached relationships
    cached_relationships = cache.get(cache_key)

    # Initialize cache if no data found
    if cached_relationships is None:
        logger.debug("Cache miss for ability event %s, initializing", event.id)
        cached_relationships = init_event_ability_all(event)

    return cached_relationships


def init_event_ability_all(event: Event) -> dict[str, dict[int, dict[str, Any]]]:
    """Initialize all ability relationships for an event and cache the result.

    Builds a complete relationship cache for all abilities in the event,
    including character relationships if the px feature is enabled.

    Args:
        event: The Event instance to initialize ability relationships for

    Returns:
        Dictionary with relationship data structure:
        {
            'abilities': {
                ability_id: {
                    'character_rels': [(char_id, char_name), ...]
                }
            }
        }

    Raises:
        Exception: Any error during relationship initialization is logged
                  and an empty dict is returned

    """
    relationship_cache: dict[str, dict[int, dict[str, Any]]] = {}

    try:
        # Get enabled features for this event to determine which relationships to build
        features = get_event_features(event.id)

        # Only process if px feature is enabled
        if "px" not in features:
            return relationship_cache

        # Initialize the cache section for abilities
        relationship_cache["abilities"] = {}

        # Get all abilities associated with the event
        abilities = event.get_elements(AbilityPx)

        # Build relationships for each ability
        for ability in abilities:
            relationship_cache["abilities"][ability.id] = get_event_ability_rels(ability)

        # Cache the complete relationship data structure
        cache_key = get_event_ability_key(event.id)
        cache.set(cache_key, relationship_cache, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug("Cached ability relationships for event %s", event.id)

    except Exception:
        # Log the error with full traceback and return empty result
        logger.exception("Error initializing ability relationships for event %s", event.id)
        relationship_cache = {}

    return relationship_cache


def update_ability_cache_section(event_id: int, ability_id: int, data: dict[str, Any]) -> None:
    """Update a specific ability in the event cache.

    Args:
        event_id: The event ID
        ability_id: ID of the ability to update
        data: Data to store for this ability

    """
    try:
        cache_key = get_event_ability_key(event_id)
        cached_event_data = cache.get(cache_key)

        if cached_event_data is None:
            logger.debug("Cache miss during ability update for event %s, reinitializing", event_id)
            # We need to get the event to reinitialize
            event = Event.objects.get(id=event_id)
            init_event_ability_all(event)
            return

        if "abilities" not in cached_event_data:
            cached_event_data["abilities"] = {}

        cached_event_data["abilities"][ability_id] = data
        cache.set(cache_key, cached_event_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug("Updated ability %s relationships in cache", ability_id)

    except Exception:
        logger.exception("Error updating ability %s relationships", ability_id)
        clear_event_ability_cache(event_id)


def remove_ability_from_cache(event_id: int, ability_id: int) -> None:
    """Remove an ability from the event cache.

    Args:
        event_id: The event ID
        ability_id: ID of the ability to remove

    """
    try:
        cache_key = get_event_ability_key(event_id)
        cached_data = cache.get(cache_key)
        if cached_data and "abilities" in cached_data and ability_id in cached_data["abilities"]:
            del cached_data["abilities"][ability_id]
            cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
            logger.debug("Removed ability %s from cache", ability_id)
    except Exception:
        logger.exception("Error removing ability %s from cache", ability_id)
        clear_event_ability_cache(event_id)


def refresh_event_ability_relationships(ability: AbilityPx) -> None:
    """Update ability relationships in cache.

    Updates the cached relationship data for a specific ability.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        ability (AbilityPx): The AbilityPx instance to update relationships for

    Returns:
        None

    """
    # Get the current ability relationship data from the event
    ability_relationship_data = get_event_ability_rels(ability)

    # Update the cache with the ability's relationship data
    update_ability_cache_section(ability.event_id, ability.id, ability_relationship_data)


def on_ability_characters_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: AbilityPx,
    action: str,
    pk_set: set[int] | None,  # noqa: ARG001
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle ability-character relationship changes.

    Updates ability cache when relationships change.
    This signal handler is triggered when characters are added to or removed
    from an ability's characters many-to-many relationship.

    Args:
        sender: The through model class that manages the M2M relationship
        instance: The AbilityPx instance whose relationships are changing
        action: The type of change being performed on the relationship.
            Common values include 'post_add', 'post_remove', 'post_clear'
        pk_set: Set of primary keys of the Character objects being affected.
            May be None for certain actions like 'post_clear'
        **kwargs: Additional keyword arguments passed by the Django signal system

    Returns:
        None

    """
    if action in ("post_add", "post_remove", "post_clear"):
        # Update the ability cache
        refresh_event_ability_relationships(instance)
