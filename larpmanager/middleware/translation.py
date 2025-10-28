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

from gettext import GNUTranslations

from django.utils import translation as dj_translation
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import trans_real

from larpmanager.cache.association_translation import get_association_translation_cache


class AssociationTranslationMiddleware(MiddlewareMixin):
    """Middleware that injects association-specific translation overrides."""

    def process_request(self, request):
        association_id = getattr(request, "association", {}).get("id", None)
        if not association_id:
            return

        language = getattr(request, "LANGUAGE_CODE", dj_translation.get_language())
        base_translation = trans_real.translation(language)

        overrides = get_association_translation_cache(association_id, language) or {}
        assoc_trans = AssociationTranslations(base_translation, overrides)

        # Replace only thread-local active translation
        trans_real._active.value = assoc_trans

    def process_response(self, request, response):
        # Restore normal translation object
        trans_real._active.value = None
        dj_translation.deactivate_all()
        return response


class AssociationTranslations(GNUTranslations):
    """Custom Translations object that supports per-association overrides."""

    def __init__(self, base_translation, overrides):
        self._base = base_translation
        self._overrides = overrides or {}

    def gettext(self, message):
        if message in self._overrides:
            return self._overrides[message]
        return self._base.gettext(message)

    def ngettext(self, singular, plural, n):
        key = singular if n == 1 else plural
        if key in self._overrides:
            return self._overrides[key]
        return self._base.ngettext(singular, plural, n)
