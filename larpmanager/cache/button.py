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

from larpmanager.models.event import EventButton


def event_button_key(event_id: int) -> str:
    """Generate cache key for event buttons.

    Args:
        event_id (int): Event ID

    Returns:
        str: Cache key for event buttons

    """
    return f"event_button_{event_id}"


def update_event_button(event_id: int) -> list[tuple[str, str, str]]:
    """Update event button cache from database.

    Retrieves all event buttons for the specified event, orders them by number,
    and caches the result for performance optimization.

    Args:
        event_id: Event ID to update buttons for.

    Returns:
        List of tuples containing (name, tooltip, link) for each event button,
        ordered by the button's number field.

    Side effects:
        Updates the cache with current button data using a 1-day timeout.

    """
    # Query event buttons ordered by number field and extract button data as tuples
    return [
        (button.name, button.tooltip, button.link)
        for button in EventButton.objects.filter(event_id=event_id).order_by("number")
    ]


def get_event_button_cache(event_id: int) -> list[tuple[str, str, str]]:
    """Get cached event buttons, updating if needed.

    Retrieves event buttons from cache. If not found in cache,
    triggers an update and returns the fresh data.

    Args:
        event_id: Event ID to get buttons for.

    Returns:
        List of (name, tooltip, link) tuples for event buttons.

    """
    # Check if buttons are already cached for this event
    cache_key = event_button_key(event_id)
    cached_buttons = cache.get(cache_key)

    # If not in cache, update and get fresh data
    if cached_buttons is None:
        cached_buttons = update_event_button(event_id)
        # Cache the result with 1-day timeout
        cache.set(cache_key, cached_buttons, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_buttons


def clear_event_button_cache(event_id: int) -> None:
    """Clear cached event button data for given event ID."""
    cache.delete(event_button_key(event_id))
