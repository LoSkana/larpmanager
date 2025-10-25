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


def reset_assoc_features(association_id):
    """Clear cached association features.

    Args:
        association_id (int): Association ID to clear cache for
    """
    cache.delete(cache_assoc_features(association_id))


def cache_assoc_features(association_id):
    """Generate cache key for association features.

    Args:
        association_id (int): Association ID

    Returns:
        str: Cache key for association features
    """
    return f"assoc_features_{association_id}"


def get_assoc_features(association_id):
    """Get cached association features, updating cache if needed.

    Args:
        association_id (int): Association ID

    Returns:
        dict: Dictionary of enabled features {feature_slug: 1}
    """
    cache_key = cache_assoc_features(association_id)
    cached_features = cache.get(cache_key)
    if cached_features is None:
        cached_features = update_assoc_features(association_id)
        cache.set(cache_key, cached_features, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return cached_features


def update_assoc_features(assoc_id: int) -> dict[str, int]:
    """Update association feature cache from database.

    Retrieves enabled features for an association and builds a cache dictionary
    containing both database-stored features and configuration-based features.

    Args:
        assoc_id: Association ID to update cache for

    Returns:
        Dictionary mapping feature slugs to enabled status (1 if enabled)

    Raises:
        No exceptions raised - ObjectDoesNotExist is handled gracefully
    """
    res = {}
    try:
        # Get association object from database
        assoc = Association.objects.get(pk=assoc_id)

        # Add all database-stored features to result
        for s in assoc.features.values_list("slug", flat=True):
            res[s] = 1

        # Check calendar-related configuration features
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
            # Add calendar features based on configuration
            if assoc.get_config("calendar_" + sl, False):
                res[sl] = 1

        # Check field-based features (safety and diet)
        for slug in ["safety", "diet"]:
            # Enable if field is either mandatory or optional
            if slug in assoc.mandatory_fields or slug in assoc.optional_fields:
                res[slug] = 1

    except ObjectDoesNotExist:
        # Return empty dict if association doesn't exist
        pass
    return res


def clear_event_features_cache(event_id):
    cache.delete(cache_event_features_key(event_id))


def cache_event_features_key(event_id):
    return f"event_features_{event_id}"


def get_event_features(event_id):
    """Get cached event features, updating cache if needed.

    Args:
        event_id (int): Event ID

    Returns:
        dict: Dictionary of enabled event features {feature_slug: 1}
    """
    cache_key = cache_event_features_key(event_id)
    cached_features = cache.get(cache_key)
    if cached_features is None:
        cached_features = update_event_features(event_id)
        cache.set(cache_key, cached_features, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return cached_features


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
