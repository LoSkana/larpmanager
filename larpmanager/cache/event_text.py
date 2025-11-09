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
import logging

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.utils.translation import get_language

from larpmanager.models.event import EventText

logger = logging.getLogger(__name__)


def event_text_key(event_id, text_type, language) -> str:
    """Generate cache key for event text."""
    return f"event_text_{event_id}_{text_type}_{language}"


def update_event_text(event_id: int, text_type: str, language: str) -> str:
    """Update and cache event text for given event, type and language.

    Args:
        event_id: The event identifier
        text_type: The text type
        language: The language code

    Returns:
        The event text or empty string if not found

    """
    event_text = ""

    # Try to get event text from database
    try:
        event_text = EventText.objects.get(event_id=event_id, typ=text_type, language=language).text
    except Exception as e:
        logger.debug(f"Event text not found for event_id={event_id}, type={text_type}, language={language}: {e}")

    # Cache the result for 1 day
    cache.set(event_text_key(event_id, text_type, language), event_text, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return event_text


def get_event_text_cache(event_id: int, typ: str, lang: str) -> str:
    """Get cached event text or update cache if missing.

    Args:
        event_id: The event identifier
        typ: The text type
        lang: The language code

    Returns:
        The cached or newly updated event text

    """
    # Try to get text from cache
    res = cache.get(event_text_key(event_id, typ, lang))

    # Update cache if not found
    if res is None:
        res = update_event_text(event_id, typ, lang)

    return res


def event_text_key_def(event_id, text_type) -> str:
    """Generate cache key for default event text."""
    return f"event_text_def_{event_id}_{text_type}"


def update_event_text_def(event_id: int, typ: str) -> str:
    """Update and cache default event text for given event and type.

    Args:
        event_id: ID of the event
        typ: Type of event text to retrieve

    Returns:
        Default event text content or empty string if not found

    """
    default_text = ""
    try:
        # Get default event text for the specified event and type
        default_text = EventText.objects.filter(event_id=event_id, typ=typ, default=True).first().text
    except Exception as e:
        # Return empty string if no default text found or any error occurs
        logger.debug(f"Default event text not found for event_id={event_id}, type={typ}: {e}")

    # Cache the result for one day
    cache.set(event_text_key_def(event_id, typ), default_text, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return default_text


def get_event_text_cache_def(event_id: int, typ: str) -> str:
    """Get cached event text or update cache if missing.

    Args:
        event_id: The event identifier
        typ: The text type to retrieve

    Returns:
        The cached or newly generated event text

    """
    # Try to get cached result
    res = cache.get(event_text_key_def(event_id, typ))
    if res is None:
        # Cache miss - update and return new value
        res = update_event_text_def(event_id, typ)
    return res


def get_event_text(event_id: int, text_type: str, language_code: str | None = None) -> str:
    """Get event text for the specified event, type, and language.

    Retrieves event text from cache if available, otherwise falls back to
    default language cache. Uses current language if no language specified.

    Args:
        event_id: The ID of the event to get text for
        text_type: The type of text to retrieve
        language_code: Language code for the text. If None, uses current language

    Returns:
        The event text string for the specified parameters

    """
    # Use current language if no language specified
    if not language_code:
        language_code = get_language()

    # Check if there is an event_text with the requested characteristics
    cached_text = get_event_text_cache(event_id, text_type, language_code)
    if cached_text:
        return cached_text

    # Fall back to default language cache if no text found
    return get_event_text_cache_def(event_id, text_type)


def update_event_text_cache_on_save(instance: EventText) -> None:
    """Update event text cache when EventText instance is saved."""
    # Update cache for specific language
    update_event_text(instance.event_id, instance.typ, instance.language)

    # Update default cache if this is the default language
    if instance.default:
        update_event_text_def(instance.event_id, instance.typ)


def clear_event_text_cache_on_delete(instance: EventText) -> None:
    """Clear event text cache entries when an EventText instance is deleted."""
    # Clear cache for specific language variant
    cache.delete(event_text_key(instance.event_id, instance.typ, instance.language))

    # Clear default cache entry if this was the default text
    if instance.default:
        cache.delete(event_text_key_def(instance.event_id, instance.typ))
