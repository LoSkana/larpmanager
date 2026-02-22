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
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.utils import translation as dj_translation
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import trans_real

from larpmanager.cache.association_translation import get_association_translation_cache


class AssociationTranslationMiddleware(MiddlewareMixin):
    """Django middleware that enables per-association custom translation overrides.

    This middleware intercepts each request and injects association-specific
    translations that override the default Django i18n translations. It allows
    each organization to customize specific translation strings without modifying
    the global .po files.

    The middleware:
    1. Checks if the request is associated with a specific organization
    2. Loads custom translations for that organization from cache
    3. Wraps the standard Django translation with custom overrides
    4. Cleans up after the response is sent

    This enables multi-tenant translation customization where different
    organizations can see different text for the same UI elements.
    """

    def process_request(self, request: HttpRequest) -> None:
        """Inject association-specific translations into the request context.

        Args:
            request: The incoming HTTP request object

        """
        # Extract association ID from request context (set by earlier middleware)
        association_id = getattr(request, "association", {}).get("id", None)
        if not association_id:
            # No association context, use default translations
            return

        # Determine the active language for this request
        language = getattr(request, "LANGUAGE_CODE", dj_translation.get_language())

        # Get the base Django translation object for this language
        base_translation = trans_real.translation(language)

        # Load custom translation overrides for this association from cache
        overrides = get_association_translation_cache(association_id, language) or {}

        # Create a custom translation wrapper that applies overrides
        assoc_trans = AssociationTranslations(base_translation, overrides, language)

        # Replace the thread-local active translation with our custom one
        trans_real._active.value = assoc_trans  # noqa: SLF001  # Django translation internal

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:  # noqa: ARG002
        """Clean up translation overrides after processing the request."""
        # Restore default translation behavior for the next request
        trans_real._active.value = None  # noqa: SLF001  # Django translation internal
        dj_translation.deactivate_all()
        return response


class AssociationTranslations(GNUTranslations):
    """Custom translation class that wraps Django translations with per-association overrides.

    This class extends the standard gettext GNUTranslations to support custom
    translation overrides. It checks the overrides dictionary first, and falls
    back to the base Django translation if no custom translation is found.

    This implements the Decorator pattern, wrapping the base translation object
    and selectively overriding specific strings.

    Attributes:
        _base: The underlying Django translation object
        _overrides: Dictionary mapping msgid strings to custom translations
        _language: The language code for this translation (e.g., 'en', 'it')

    """

    def __init__(self, base_translation: Any, overrides: dict[str, str], language: str) -> None:
        """Initialize the translation wrapper with base translations and overrides."""
        self._base = base_translation
        self._overrides = overrides or {}
        self._language = language

    def to_language(self) -> str:
        """Return the language code for this translation."""
        return self._language

    def gettext(self, message: str) -> str:
        """Translate a message, using custom override if available."""
        if message in self._overrides:
            return self._overrides[message]
        return self._base.gettext(message)

    def ngettext(self, singular: str, plural: str, n: int) -> str:
        """Translate a message with plural forms, using custom override if available."""
        # Determine which form to check for override based on count
        key = singular if n == 1 else plural
        if key in self._overrides:
            return self._overrides[key]
        return self._base.ngettext(singular, plural, n)
