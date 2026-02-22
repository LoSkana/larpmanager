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

import ast
from typing import TYPE_CHECKING

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count

from larpmanager.cache.button import get_event_button_cache
from larpmanager.cache.config import get_event_config, save_single_config
from larpmanager.cache.feature import get_event_features
from larpmanager.models.event import Event, Run
from larpmanager.models.form import _get_writing_mapping
from larpmanager.models.writing import Faction

if TYPE_CHECKING:
    from larpmanager.models.association import Association


def reset_cache_run(association: Association, slug: str) -> None:
    """Invalidate the cached run data for a specific event."""
    key = cache_run_key(association, slug)
    cache.delete(key)


def cache_run_key(association_id: int, slug: str) -> str:
    """Generate cache key for run data."""
    return f"run_{association_id}_{slug}"


def get_cache_run(association_id: int, slug: str) -> str:
    """Get cached run data for association and slug."""
    # Generate cache key for the association and slug
    cache_key = cache_run_key(association_id, slug)

    # Try to retrieve cached result
    cached_result = cache.get(cache_key)

    # If not cached, initialize and cache the result
    if cached_result is None:
        cached_result = init_cache_run(association_id, slug)
        cache.set(cache_key, cached_result, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_result


def init_cache_run(association_id: int, event_slug: str) -> int | None:
    """Get the run ID from association ID and event slug.

    Args:
        association_id: The association ID
        event_slug: Event slug, optionally with run number (e.g., "event-2")

    Returns:
        Run ID if found, None otherwise

    """
    try:
        # Extract run number from event slug if present (e.g., "event-2" -> "event", 2)
        try:
            event_slug, run_number = event_slug.split("-")
            run_number = int(run_number)
        except ValueError:
            run_number = 1

        # Fetch the run with related event data
        run = Run.objects.select_related("event").get(
            event__association_id=association_id,
            event__slug=event_slug,
            number=run_number,
        )
    except ObjectDoesNotExist:
        return None
    else:
        return run.uuid


def on_run_pre_save_invalidate_cache(instance: Run) -> None:
    """Handle run pre-save cache invalidation."""
    if instance.pk:
        reset_cache_run(instance.event.association_id, instance.get_slug())


def on_event_pre_save_invalidate_cache(instance: Event) -> None:
    """Handle event pre-save cache invalidation."""
    if instance.pk:
        for run in instance.runs.all():
            reset_cache_run(instance.association_id, run.get_slug())


def reset_cache_config_run(run: Run) -> None:
    """Delete cached configuration for a run."""
    cache_key = cache_config_run_key(run)
    cache.delete(cache_key)


def cache_config_run_key(run_instance: Run) -> str:
    """Return cache key for a run's config."""
    return f"run_config_{run_instance.id}"


def get_cache_config_run(run: Run) -> dict:
    """Retrieve cached run configuration, initializing if not found.

    Args:
        run: The run object to get configuration for.

    Returns:
        Dictionary containing the run configuration data.

    """
    # Generate cache key for this specific run
    cache_key = cache_config_run_key(run)

    # Attempt to retrieve from cache
    cached_config = cache.get(cache_key)

    # Initialize and cache if not found
    if cached_config is None:
        cached_config = init_cache_config_run(run)
        cache.set(cache_key, cached_config, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_config


def init_cache_config_run(run: Run) -> dict:
    """Initialize and build cache configuration data for a run.

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
    event_id = run.event_id
    parent_id = run.event.parent.id if run.event.parent else run.event_id

    # Get event features to determine what functionality is available
    event_features = get_event_features(event_id)

    # Initialize base context with buttons and core display settings
    context = {
        "buttons": get_event_button_cache(event_id),
    }
    configs = [
        ("limitations", "show_limitations", event_id, False),
        ("user_character_max", "user_character_max", event_id, 0),
        ("cover_orig", "cover_orig", event_id, False),
        ("px_user", "px_user", parent_id, False),
    ]
    for context_key, config_key, event_id, default in configs:
        context[context_key] = get_event_config(event_id, config_key, default_value=default, context=context)

    # Process writing system configurations for enabled features
    mapping = _get_writing_mapping()
    for config_name in ["character", "faction", "quest", "trait"]:
        # Skip if this writing feature is not enabled for the event
        if mapping[config_name] not in event_features:
            continue

        # Parse and convert list configuration to dictionary lookup
        config_display_dict = {}
        config_value = run.get_config("show_" + config_name, default_value="[]")
        for element in ast.literal_eval(config_value):
            config_display_dict[element] = 1
        context["show_" + config_name] = config_display_dict

    # Process additional display configurations
    additional_display_dict = {}
    additional_config_value = run.get_config("show_addit", default_value="[]")
    for element in ast.literal_eval(additional_config_value):
        additional_display_dict[element] = 1
    context["show_addit"] = additional_display_dict

    return context


def on_run_post_save_reset_config_cache(instance: Run) -> None:
    """Handle run post-save cache reset."""
    if instance.pk:
        reset_cache_config_run(instance)


def on_event_post_save_reset_config_cache(instance: Event) -> None:
    """Handle event post-save cache reset."""
    if instance.pk:
        for run in instance.runs.all():
            reset_cache_config_run(run)


def update_visible_factions(event: Event) -> None:
    """Check if there are visible factions with characters for nav display."""
    has_visible_factions = (
        "faction" in get_event_features(event.id)
        and event.get_elements(Faction)
        .prefetch_related("characters")
        .exclude(name="")
        .annotate(char_count=Count("characters"))
        .filter(char_count__gt=0)
        .exists()
    )
    save_single_config(event, "has_visible_factions", has_visible_factions)
