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


def event_button_key(event_id):
    """Generate cache key for event buttons.

    Args:
        event_id (int): Event ID

    Returns:
        str: Cache key for event buttons
    """
    return f"event_button_{event_id}"


def update_event_button(event_id):
    """Update event button cache from database.

    Args:
        event_id (int): Event ID to update buttons for

    Returns:
        list: List of (name, tooltip, link) tuples for event buttons

    Side effects:
        Updates cache with current button data
    """
    res = []
    for el in EventButton.objects.filter(event_id=event_id).order_by("number"):
        res.append((el.name, el.tooltip, el.link))
    cache.set(event_button_key(event_id), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def get_event_button_cache(event_id):
    """Get cached event buttons, updating if needed.

    Args:
        event_id (int): Event ID to get buttons for

    Returns:
        list: List of (name, tooltip, link) tuples for event buttons
    """
    res = cache.get(event_button_key(event_id))
    if res is None:
        res = update_event_button(event_id)
    return res
