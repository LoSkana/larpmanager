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


def association_translation_key(association_id: int, language_code: str):
    """Generate cache key for association translations"""
    return f"association_translation_{association_id}_{language_code}"


def clear_association_translation_cache(association_id: int, language_code: str):
    cache.delete(association_translation_key(association_id, language_code))


def update_association_translation(association_id: int, language_code: str) -> dict:
    """Update association translation for a language"""
    res = {}

    for el in AssociationTranslation.objects.filter(association_id=association_id, language=language_code, active=True):
        res[el.msgid] = el.msgstr

    return res


def get_association_translation_cache(association_id: int, language_code: str) -> dict:
    """Get cached association translation, updating if needed."""
    key = association_translation_key(association_id, language_code)
    res = cache.get(key)

    # If not in cache, update and get fresh data
    if res is None:
        res = update_association_translation(association_id, language_code)
        # Cache the result with 1-day timeout
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res
