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
from django.utils.translation import get_language

from larpmanager.models.association import AssocText
from larpmanager.models.event import EventText


def event_text_key(event_id, text_type, language):
    return f"event_text_{event_id}_{text_type}_{language}"


def update_event_text(event_id: int, typ: str, lang: str) -> str:
    """Updates and caches event text for given event, type and language.

    Args:
        event_id: The event identifier
        typ: The text type
        lang: The language code

    Returns:
        The event text or empty string if not found
    """
    res = ""

    # Try to get event text from database
    try:
        res = EventText.objects.get(event_id=event_id, typ=typ, language=lang).text
    except Exception:
        pass

    # Cache the result for 1 day
    cache.set(event_text_key(event_id, typ, lang), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


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


def event_text_key_def(event_id, text_type):
    return f"event_text_def_{event_id}_{text_type}"


def update_event_text_def(event_id: int, typ: str) -> str:
    """Update and cache default event text for given event and type.

    Args:
        event_id: ID of the event
        typ: Type of event text to retrieve

    Returns:
        Default event text content or empty string if not found
    """
    res = ""
    try:
        # Get default event text for the specified event and type
        res = EventText.objects.filter(event_id=event_id, typ=typ, default=True).first().text
    except Exception:
        # Return empty string if no default text found or any error occurs
        pass

    # Cache the result for one day
    cache.set(event_text_key_def(event_id, typ), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


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


def get_event_text(event_id: int, text_type: str, language_code: str = None) -> str:
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


# # ASSOC TEXT


def update_association_text_cache_on_save(instance: AssocText) -> None:
    """Update association text cache and default cache if needed."""
    update_assoc_text(instance.assoc_id, instance.typ, instance.language)
    if instance.default:
        update_assoc_text_def(instance.assoc_id, instance.typ)


def clear_association_text_cache_on_delete(instance: AssocText) -> None:
    """Clear association text cache entries when an instance is deleted."""
    # Clear language-specific cache entry
    cache.delete(assoc_text_key(instance.assoc_id, instance.typ, instance.language))

    # Clear default language cache if this was the default text
    if instance.default:
        cache.delete(assoc_text_key_def(instance.assoc_id, instance.typ))


# ## EVENT TEXT


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


# Text cache


def assoc_text_key(association_id, text_type, language):
    return f"assoc_text_{association_id}_{text_type}_{language}"


def update_assoc_text(assoc_id: int, typ: str, lang: str) -> str:
    """Updates and caches association text for given ID, type and language.

    Args:
        assoc_id: Association ID
        typ: Text type
        lang: Language code

    Returns:
        Text content or empty string if not found
    """
    res = ""
    try:
        # Retrieve association text from database
        res = AssocText.objects.get(assoc_id=assoc_id, typ=typ, language=lang).text
    except Exception:
        # Return empty string if text not found
        pass

    # Cache the result for one day
    cache.set(assoc_text_key(assoc_id, typ, lang), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def get_assoc_text_cache(assoc_id: int, typ: str, lang: str) -> str:
    """Get cached association text or update cache if missing.

    Args:
        assoc_id: Association ID
        typ: Text type identifier
        lang: Language code

    Returns:
        Cached or freshly updated association text
    """
    # Try to get cached text
    res = cache.get(assoc_text_key(assoc_id, typ, lang))

    # Update cache if not found
    if res is None:
        res = update_assoc_text(assoc_id, typ, lang)

    return res


# default it


def assoc_text_key_def(association_id, text_type):
    return f"assoc_text_def_{association_id}_{text_type}"


def update_assoc_text_def(assoc_id: int, typ: str) -> str:
    """Updates and caches the default association text for given type.

    Args:
        assoc_id: The association ID
        typ: The text type to retrieve

    Returns:
        The default text content or empty string if not found
    """
    res = ""
    try:
        # Get the default association text for the specified type
        res = AssocText.objects.filter(assoc_id=assoc_id, typ=typ, default=True).first().text
    except Exception:
        pass

    # Cache the result for one day
    cache.set(assoc_text_key_def(assoc_id, typ), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def get_assoc_text_cache_def(assoc_id: int, typ: str) -> str:
    """Get association text from cache or update if not found.

    Args:
        assoc_id: Association ID
        typ: Text type identifier

    Returns:
        Association text content
    """
    # Try to retrieve from cache first
    res = cache.get(assoc_text_key_def(assoc_id, typ))

    # Update cache if not found
    if res is None:
        res = update_assoc_text_def(assoc_id, typ)

    return res


def get_assoc_text(association_id: int, text_type: str, language_code: str = None) -> str:
    """Get association text for the specified type and language.

    Retrieves localized text for an association. Falls back to default
    language if the requested language is not available.

    Args:
        association_id: The association ID to get text for.
        text_type: The type of text to retrieve.
        language_code: The language code. If None, uses current language.

    Returns:
        The localized text string, or default language text if not found.
    """
    # Use current language if none specified
    if not language_code:
        language_code = get_language()

    # Check if there is an assoc_text with the requested characteristics
    cached_text = get_assoc_text_cache(association_id, text_type, language_code)
    if cached_text:
        return cached_text

    # Fall back to default language text if requested language not found
    return get_assoc_text_cache_def(association_id, text_type)
