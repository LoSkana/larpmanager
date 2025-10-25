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
import ast

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.cache.button import get_event_button_cache
from larpmanager.cache.config import get_event_config
from larpmanager.cache.feature import get_event_features
from larpmanager.models.association import Association
from larpmanager.models.event import Run
from larpmanager.models.form import _get_writing_mapping


def reset_cache_run(association, slug):
    key = cache_run_key(association, slug)
    cache.delete(key)


def cache_run_key(association_id, slug):
    return f"run_{association_id}_{slug}"


def get_cache_run(association: Association, slug: str) -> dict:
    """Get cached run data for association and slug."""
    # Generate cache key for the association and slug
    cache_key = cache_run_key(association, slug)

    # Try to retrieve cached result
    cached_result = cache.get(cache_key)

    # If not cached, initialize and cache the result
    if cached_result is None:
        cached_result = init_cache_run(association, slug)
        cache.set(cache_key, cached_result, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_result


def init_cache_run(a, s):
    try:
        try:
            s, n = s.split("-")
            n = int(n)
        except ValueError:
            n = 1

        run = Run.objects.select_related("event").get(event__assoc_id=a, event__slug=s, number=n)
        return run.id
    except ObjectDoesNotExist:
        return None


def on_run_pre_save_invalidate_cache(instance):
    """Handle run pre-save cache invalidation.

    Args:
        instance: Run instance being saved
    """
    if instance.pk:
        reset_cache_run(instance.event.assoc_id, instance.get_slug())


def on_event_pre_save_invalidate_cache(instance):
    """Handle event pre-save cache invalidation.

    Args:
        instance: Event instance being saved
    """
    if instance.pk:
        for run in instance.runs.all():
            reset_cache_run(instance.assoc_id, run.get_slug())


def reset_cache_config_run(run):
    cache_key = cache_config_run_key(run)
    cache.delete(cache_key)


def cache_config_run_key(run_instance):
    return f"run_config_{run_instance.id}"


def get_cache_config_run(run: Run) -> dict:
    """Retrieve cached run configuration, initializing if not found.

    Args:
        run: The run object to get configuration for.

    Returns:
        Dictionary containing the run configuration data.
    """
    # Generate cache key for this specific run
    key = cache_config_run_key(run)

    # Attempt to retrieve from cache
    res = cache.get(key)

    # Initialize and cache if not found
    if res is None:
        res = init_cache_config_run(run)
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def init_cache_config_run(run) -> dict:
    """
    Initialize and build cache configuration data for a run.

    This function creates a cache configuration context containing UI elements,
    limitations, and display settings for a specific run. It handles event features,
    parent event inheritance, and writing system configurations.

    Args:
        run: Run instance to initialize cache for. Must have an associated event.

    Returns:
        dict: Cache configuration context containing:
            - buttons: Event-specific button cache
            - limitations: Whether to show limitations
            - user_character_max: Maximum characters per user
            - cover_orig: Original cover setting
            - px_user: User experience points setting
            - show_* keys: Display configuration for character, faction, quest, trait
            - show_addit: Additional display configuration
    """
    # Get event features to determine what functionality is available
    ev_features = get_event_features(run.event_id)

    # Initialize base context with buttons and core display settings
    ctx = {
        "buttons": get_event_button_cache(run.event_id),
    }
    ctx["limitations"] = get_event_config(run.event_id, "show_limitations", False, ctx)
    ctx["user_character_max"] = get_event_config(run.event_id, "user_character_max", 0, ctx)
    ctx["cover_orig"] = get_event_config(run.event_id, "cover_orig", False, ctx)
    ctx["px_user"] = get_event_config(run.event_id, "px_user", False, ctx)

    # Handle parent event inheritance for px_user setting
    if run.event.parent:
        ctx["px_user"] = get_event_config(run.event.parent.id, "px_user", False, ctx)

    # Process writing system configurations for enabled features
    mapping = _get_writing_mapping()
    for config_name in ["character", "faction", "quest", "trait"]:
        # Skip if this writing feature is not enabled for the event
        if mapping[config_name] not in ev_features:
            continue

        # Parse and convert list configuration to dictionary lookup
        res = {}
        val = run.get_config("show_" + config_name, "[]")
        for el in ast.literal_eval(val):
            res[el] = 1
        ctx["show_" + config_name] = res

    # Process additional display configurations
    res = {}
    val = run.get_config("show_addit", "[]")
    for el in ast.literal_eval(val):
        res[el] = 1
    ctx["show_addit"] = res

    return ctx


def on_run_post_save_reset_config_cache(instance):
    """Handle run post-save cache reset.

    Args:
        instance: Run instance that was saved
    """
    if instance.pk:
        reset_cache_config_run(instance)


def on_event_post_save_reset_config_cache(instance):
    """Handle event post-save cache reset.

    Args:
        instance: Event instance that was saved
    """
    if instance.pk:
        for run in instance.runs.all():
            reset_cache_config_run(run)
