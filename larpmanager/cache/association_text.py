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

from larpmanager.models.association import AssociationText


def association_text_key(association_id: int, text_type: str, language: str) -> str:
    """Generate cache key for association text content."""
    return f"association_text_{association_id}_{text_type}_{language}"


def update_association_text(association_id: int, typ: str, lang: str) -> str:
    """Update and cache association text for given ID, type and language.

    Args:
        association_id: Association ID
        typ: Text type
        lang: Language code

    Returns:
        Text content or empty string if not found

    """
    text_content = ""
    try:
        # Retrieve association text from database
        text_content = AssociationText.objects.get(association_id=association_id, typ=typ, language=lang).text
    except Exception:
        # Return empty string if text not found
        pass

    # Cache the result for one day
    cache.set(association_text_key(association_id, typ, lang), text_content, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return text_content


def get_association_text_cache(association_id: int, typ: str, lang: str) -> str:
    """Get cached association text or update cache if missing.

    Args:
        association_id: Association ID
        typ: Text type identifier
        lang: Language code

    Returns:
        Cached or freshly updated association text

    """
    # Try to get cached text
    cached_text = cache.get(association_text_key(association_id, typ, lang))

    # Update cache if not found
    if cached_text is None:
        cached_text = update_association_text(association_id, typ, lang)

    return cached_text


def association_text_key_def(association_id: int, text_type: str) -> str:
    """Generate cache key for association text definitions."""
    return f"association_text_def_{association_id}_{text_type}"


def update_association_text_def(association_id: int, text_type: str) -> str:
    """Update and cache the default association text for given type.

    Args:
        association_id: The association ID
        text_type: The text type to retrieve

    Returns:
        The default text content or empty string if not found

    """
    default_text = ""
    try:
        # Get the default association text for the specified type
        default_text = (
            AssociationText.objects.filter(association_id=association_id, typ=text_type, default=True).first().text
        )
    except Exception:
        pass

    # Cache the result for one day
    cache.set(
        association_text_key_def(association_id, text_type), default_text, timeout=conf_settings.CACHE_TIMEOUT_1_DAY
    )
    return default_text


def get_association_text_cache_def(association_id: int, typ: str) -> str:
    """Get association text from cache or update if not found.

    Args:
        association_id: Association ID
        typ: Text type identifier

    Returns:
        Association text content

    """
    # Try to retrieve from cache first
    cached_text = cache.get(association_text_key_def(association_id, typ))

    # Update cache if not found
    if cached_text is None:
        cached_text = update_association_text_def(association_id, typ)

    return cached_text


def get_association_text(association_id: int, text_type: str, language_code: str = None) -> str:
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

    # Check if there is an association_text with the requested characteristics
    cached_text = get_association_text_cache(association_id, text_type, language_code)
    if cached_text:
        return cached_text

    # Fall back to default language text if requested language not found
    return get_association_text_cache_def(association_id, text_type)


def update_association_text_cache_on_save(instance: AssociationText) -> None:
    """Update association text cache and default cache if needed."""
    update_association_text(instance.association_id, instance.typ, instance.language)
    if instance.default:
        update_association_text_def(instance.association_id, instance.typ)


def clear_association_text_cache_on_delete(instance: AssociationText) -> None:
    """Clear association text cache entries when an instance is deleted."""
    # Clear language-specific cache entry
    cache.delete(association_text_key(instance.association_id, instance.typ, instance.language))

    # Clear default language cache if this was the default text
    if instance.default:
        cache.delete(association_text_key_def(instance.association_id, instance.typ))
