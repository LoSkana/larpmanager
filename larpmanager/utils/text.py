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


def event_text_key(event_id, typ, lang):
    return f"event_text_{event_id}_{typ}_{lang}"


def update_event_text(event_id: int, typ: str, lang: str) -> str:
    """Update and cache event text for the specified event, type, and language.

    Args:
        event_id: The ID of the event to retrieve text for
        typ: The type of event text to retrieve
        lang: The language code for the text

    Returns:
        The event text string, or empty string if not found

    Note:
        Sets cache with 1-day timeout regardless of whether text is found
    """
    res = ""

    # Attempt to retrieve event text from database
    try:
        res = EventText.objects.get(event_id=event_id, typ=typ, language=lang).text
    except Exception:
        # Return empty string if EventText not found or any other error occurs
        pass

    # Cache the result (empty string or actual text) with 1-day timeout
    cache.set(event_text_key(event_id, typ, lang), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def get_event_text_cache(event_id, typ, lang):
    res = cache.get(event_text_key(event_id, typ, lang))
    if res is None:
        res = update_event_text(event_id, typ, lang)
    return res


def event_text_key_def(event_id, typ):
    return f"event_text_def_{event_id}_{typ}"


def update_event_text_def(event_id: int, typ: str) -> str:
    """Update and cache the default event text for a specific event and type.

    Args:
        event_id: The ID of the event to retrieve text for
        typ: The type of event text to retrieve

    Returns:
        The text content of the default EventText, or empty string if not found

    Note:
        Results are cached for 1 day using the event_text_key_def cache key.
    """
    res = ""

    try:
        # Query for the default EventText of the specified type for this event
        event_text = EventText.objects.filter(event_id=event_id, typ=typ, default=True).first()
        if event_text:
            res = event_text.text
    except Exception:
        # Silently handle any database or attribute errors
        pass

    # Cache the result for 1 day to improve performance on subsequent requests
    cache.set(event_text_key_def(event_id, typ), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def get_event_text_cache_def(event_id, typ):
    res = cache.get(event_text_key_def(event_id, typ))
    if res is None:
        res = update_event_text_def(event_id, typ)
    return res


def get_event_text(event_id: int, typ: str, lang: str = None) -> str:
    """Get event text for the specified event, type, and language.

    Retrieves event text from cache if available, otherwise falls back to
    default language cache. Uses current language if no language specified.

    Args:
        event_id: The ID of the event to get text for
        typ: The type of text to retrieve
        lang: Language code for the text. If None, uses current language

    Returns:
        The event text string for the specified parameters
    """
    # Use current language if no language specified
    if not lang:
        lang = get_language()

    # Check if there is an event_text with the requested characteristics
    res = get_event_text_cache(event_id, typ, lang)
    if res:
        return res

    # Fall back to default language cache if no text found
    return get_event_text_cache_def(event_id, typ)


# # ASSOC TEXT


def update_association_text_cache_on_save(instance):
    update_assoc_text(instance.assoc_id, instance.typ, instance.language)
    if instance.default:
        update_assoc_text_def(instance.assoc_id, instance.typ)


def clear_association_text_cache_on_delete(instance):
    cache.delete(assoc_text_key(instance.assoc_id, instance.typ, instance.language))
    if instance.default:
        cache.delete(assoc_text_key_def(instance.assoc_id, instance.typ))


# ## EVENT TEXT


def update_event_text_cache_on_save(instance):
    update_event_text(instance.event_id, instance.typ, instance.language)
    if instance.default:
        update_event_text_def(instance.event_id, instance.typ)


def clear_event_text_cache_on_delete(instance):
    cache.delete(event_text_key(instance.event_id, instance.typ, instance.language))
    if instance.default:
        cache.delete(event_text_key_def(instance.event_id, instance.typ))


# Text cache


def assoc_text_key(assoc_id, typ, lang):
    return f"assoc_text_{assoc_id}_{typ}_{lang}"


def update_assoc_text(assoc_id: int, typ: str, lang: str) -> str:
    """Update and cache association text for given parameters.

    Args:
        assoc_id: The association ID to retrieve text for
        typ: The type of text to retrieve
        lang: The language code for the text

    Returns:
        The association text string, or empty string if not found
    """
    res = ""

    # Attempt to retrieve association text from database
    try:
        res = AssocText.objects.get(assoc_id=assoc_id, typ=typ, language=lang).text
    except Exception:
        # If text not found, res remains empty string
        pass

    # Cache the result for one day to improve performance
    cache.set(assoc_text_key(assoc_id, typ, lang), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def get_assoc_text_cache(assoc_id, typ, lang):
    res = cache.get(assoc_text_key(assoc_id, typ, lang))
    if res is None:
        res = update_assoc_text(assoc_id, typ, lang)
    return res


# default it


def assoc_text_key_def(assoc_id, typ):
    return f"assoc_text_def_{assoc_id}_{typ}"


def update_assoc_text_def(assoc_id: int, typ: str) -> str:
    """Update and cache default association text for given type.

    Args:
        assoc_id: The association ID to fetch text for
        typ: The text type to retrieve

    Returns:
        The default text content for the association and type, or empty string if not found
    """
    res = ""
    try:
        # Query for default association text of specified type
        assoc_text = AssocText.objects.filter(assoc_id=assoc_id, typ=typ, default=True).first()
        if assoc_text:
            res = assoc_text.text
    except Exception:
        # Silently handle any database or model errors
        pass

    # Cache the result for one day to improve performance
    cache.set(assoc_text_key_def(assoc_id, typ), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def get_assoc_text_cache_def(assoc_id, typ):
    res = cache.get(assoc_text_key_def(assoc_id, typ))
    if res is None:
        res = update_assoc_text_def(assoc_id, typ)
    return res


def get_assoc_text(assoc_id: int, typ: str, lang: str = None) -> str:
    """Get association text for the specified type and language.

    Retrieves localized text for an association. Falls back to default
    language if the requested language is not available.

    Args:
        assoc_id: The association ID to get text for.
        typ: The type of text to retrieve.
        lang: The language code. If None, uses current language.

    Returns:
        The localized text string, or default language text if not found.
    """
    # Use current language if none specified
    if not lang:
        lang = get_language()

    # Check if there is an assoc_text with the requested characteristics
    res = get_assoc_text_cache(assoc_id, typ, lang)
    if res:
        return res

    # Fall back to default language text if requested language not found
    return get_assoc_text_cache_def(assoc_id, typ)
