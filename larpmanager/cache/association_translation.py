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

from larpmanager.models.association import AssociationTranslation


def association_translation_key(association_id: int, language_code: str) -> str:
    """Generate a unique cache key for association translation dictionary.

    Args:
        association_id: The unique identifier of the association
        language_code: ISO language code (e.g., 'en', 'it', 'de')

    Returns:
        A formatted cache key string for storing/retrieving translations
    """
    return f"association_translation_{association_id}_{language_code}"


def clear_association_translation_cache(association_id: int, language_code: str) -> None:
    """Clear the cached translation dictionary for a specific association and language.

    This should be called when translation entries are modified to ensure
    the cache stays in sync with the database.

    Args:
        association_id: The unique identifier of the association
        language_code: ISO language code for the translation to clear
    """
    cache.delete(association_translation_key(association_id, language_code))


def update_association_translation(association_id: int, language_code: str) -> dict[str, str]:
    """Fetch and build translation dictionary from database for an association.

    Retrieves all active custom translations for the specified association and language,
    constructing a dictionary that maps original text (msgid) to translated text (msgstr).
    This dictionary is used to override default Django translations at runtime.

    Args:
        association_id: The unique identifier of the association
        language_code: ISO language code for the translations to fetch

    Returns:
        Dictionary mapping original text strings to their custom translations.
        Empty dict if no translations exist for this association/language combination.
    """
    res: dict[str, str] = {}

    # Query all active custom translations for this association and language
    for el in AssociationTranslation.objects.filter(association_id=association_id, language=language_code, active=True):
        res[el.msgid] = el.msgstr

    return res


def get_association_translation_cache(association_id: int, language_code: str) -> dict[str, str]:
    """Get cached translation dictionary for an association, fetching from DB if needed.

    This function implements a cache-aside pattern: first checks the cache,
    and if not found, fetches from database and stores in cache for future requests.
    The cache timeout is set to 1 day.

    Args:
        association_id: The unique identifier of the association
        language_code: ISO language code for the translations to retrieve

    Returns:
        Dictionary mapping original text strings to their custom translations.
        Returns empty dict if no translations exist for this combination.
    """
    key = association_translation_key(association_id, language_code)
    res = cache.get(key)

    # Cache miss - fetch from database and populate cache
    if res is None:
        res = update_association_translation(association_id, language_code)
        # Cache for 1 day to balance freshness with performance
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res
