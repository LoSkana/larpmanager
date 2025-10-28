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

from django.utils import translation
from django.utils.functional import lazy

from larpmanager.cache.association_translation import get_association_translation


class AssociationTranslationMiddleware:
    """Middleware to apply association-specific translations.

    This middleware intercepts Django's translation system and overrides
    translations with association-specific ones when available. It works
    transparently with existing {% trans %} tags and _() calls.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Process request and inject association translation override.

        Args:
            request: Django HTTP request object

        Returns:
            HttpResponse: Response with association translations applied
        """
        # Check if association context is available
        if hasattr(request, "assoc") and request.assoc:
            association_id = request.assoc.get("id")
            language = getattr(request, "LANGUAGE_CODE", None)
            if association_id:
                # Store association ID in thread-local storage for translation lookup
                _translation_override.value = get_association_translation(association_id, language)
        else:
            # Clear any previous association ID
            _translation_override.value = None

        response = self.get_response(request)

        # Clean up thread-local storage
        _translation_override.value = None

        return response


# Thread-local storage for current association ID
class ThreadLocalAssociationTranslations:
    """Thread-local storage for association ID during request processing."""

    def __init__(self):
        import threading

        self._local = threading.local()

    @property
    def value(self):
        return getattr(self._local, "association_id", None)

    @value.setter
    def value(self, association_id):
        self._local.association_id = association_id


_translation_override = ThreadLocalAssociationTranslationsco()


# Monkey-patch Django's gettext to support association overrides
_original_gettext = translation.gettext
_original_gettext_lazy = translation.gettext_lazy


def _association_aware_gettext(message):
    """Get translation with association override support.

    Args:
        message: The message to translate

    Returns:
        str: Translated message, using association override if available
    """
    # Get standard translation first
    standard_translation = _original_gettext(message)

    # Check if we have an association context
    association_id = _translation_override.value
    if association_id:
        # Try to get association-specific translation
        custom_translation = get_association_translation(association_id, message)
        if custom_translation:
            return custom_translation

    # Return standard translation if no override found
    return standard_translation


def _association_aware_gettext_lazy(message):
    """Lazy version of association-aware gettext.

    Args:
        message: The message to translate

    Returns:
        Promise: Lazy translation promise
    """
    return lazy(_association_aware_gettext, str)(message)


# Apply the monkey patch
translation.gettext = _association_aware_gettext
translation.gettext_lazy = _association_aware_gettext_lazy

# Also patch ugettext variants (deprecated but still used)
translation.ugettext = _association_aware_gettext
translation.ugettext_lazy = _association_aware_gettext_lazy
