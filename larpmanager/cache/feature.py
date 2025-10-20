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

from larpmanager.models.association import Association
from larpmanager.models.event import Event


def reset_assoc_features(assoc_id):
    """Clear cached association features.

    Args:
        assoc_id (int): Association ID to clear cache for
    """
    cache.delete(cache_assoc_features(assoc_id))


def cache_assoc_features(assoc_id):
    """Generate cache key for association features.

    Args:
        assoc_id (int): Association ID

    Returns:
        str: Cache key for association features
    """
    return f"assoc_features_{assoc_id}"


def get_assoc_features(assoc_id: int) -> dict[str, int]:
    """Get cached association features, updating cache if needed.

    Retrieves the enabled features for a specific association from cache.
    If the data is not cached, fetches it from the database and caches it
    for future requests.

    Args:
        assoc_id: The unique identifier for the association.

    Returns:
        A dictionary mapping feature slugs to their enabled status.
        Keys are feature slug strings, values are 1 for enabled features.

    Example:
        >>> get_assoc_features(123)
        {'registration': 1, 'accounting': 1, 'character_creation': 1}
    """
    # Generate the cache key for this association's features
    key = cache_assoc_features(assoc_id)

    # Attempt to retrieve features from cache
    res = cache.get(key)

    # If not cached, fetch from database and cache the result
    if res is None:
        res = update_assoc_features(assoc_id)
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def update_assoc_features(assoc_id: int) -> dict[str, int]:
    """Update association feature cache from database.

    Retrieves enabled features for an association and builds a cache dictionary
    containing both database-stored features and configuration-based features.

    Args:
        assoc_id: Association ID to update cache for

    Returns:
        Dictionary mapping feature slugs to enabled status (1 for enabled)

    Raises:
        None: Catches ObjectDoesNotExist and returns empty dict on failure
    """
    res = {}
    try:
        # Get association object and retrieve enabled features
        assoc = Association.objects.get(pk=assoc_id)
        for s in assoc.features.values_list("slug", flat=True):
            res[s] = 1

        # Add calendar-based configuration features
        for sl in [
            "genre",
            "show_event",
            "website",
            "past_events",
            "description",
            "where",
            "authors",
            "visible",
            "tagline",
        ]:
            if assoc.get_config("calendar_" + sl, False):
                res[sl] = 1

        # Add field-based features (safety and diet)
        for slug in ["safety", "diet"]:
            if slug in assoc.mandatory_fields or slug in assoc.optional_fields:
                res[slug] = 1

    except ObjectDoesNotExist:
        # Return empty dict if association not found
        pass
    return res


def clear_event_features_cache(ev_id):
    cache.delete(cache_event_features_key(ev_id))


def cache_event_features_key(ev_id):
    return f"event_features_{ev_id}"


def get_event_features(ev_id: int) -> dict[str, int]:
    """Get cached event features, updating cache if needed.

    Retrieves event features from cache. If not found in cache, updates
    the cache by fetching fresh data and stores it for future requests.

    Args:
        ev_id: Event ID to fetch features for.

    Returns:
        Dictionary mapping feature slugs to enabled status (1 for enabled).
        Example: {'registration': 1, 'accounting': 1}

    Note:
        Cache timeout is set to 1 day as defined in conf_settings.
    """
    # Generate cache key for this specific event
    key = cache_event_features_key(ev_id)

    # Attempt to retrieve cached features
    res = cache.get(key)

    # If not in cache, fetch fresh data and cache it
    if res is None:
        res = update_event_features(ev_id)
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def update_event_features(ev_id):
    """Update event feature cache with dependencies.

    Args:
        ev_id: Event ID to update features for

    Returns:
        dict: Feature dictionary with enabled features marked as 1
    """
    try:
        ev = Event.objects.get(pk=ev_id)
        res = get_assoc_features(ev.assoc_id)
        for slug in ev.features.values_list("slug", flat=True):
            res[slug] = 1
        ex_features = {
            "writing": ["paste_text", "title", "cover", "hide", "assigned"],
            "registration": ["reg_que_age", "reg_que_faction", "reg_que_tickets", "unique_code", "reg_que_allowed"],
            "character_form": ["wri_que_max", "wri_que_tickets", "wri_que_requirements"],
            "casting": ["mirror"],
            "user_character": ["player_relationships"],
        }
        for config_type, config_names in ex_features.items():
            for slug in config_names:
                if ev.get_config(f"{config_type}_{slug}", False):
                    res[slug] = 1
        return res
    except ObjectDoesNotExist:
        return {}


def on_association_post_save_reset_features_cache(instance):
    """Handle association post-save feature cache reset.

    Args:
        instance: Association instance that was saved
    """
    reset_assoc_features(instance.id)
    for ev_id in instance.events.values_list("pk", flat=True):
        clear_event_features_cache(ev_id)
