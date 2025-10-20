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

import os

from django.conf import settings as conf_settings
from django.utils import translation


class LocaleAdvMiddleware:
    """Advanced locale middleware with user preference support.

    Determines language based on user preferences, falling back to
    browser detection with validation against supported languages.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        """Activate language for request based on user/browser preferences.

        Args:
            request: Django HTTP request object

        Returns:
            HttpResponse: Response with activated language
        """
        request.LANGUAGE_CODE = self.get_lang(request)
        translation.activate(request.LANGUAGE_CODE)
        response = self.get_response(request)
        return response

    @staticmethod
    def get_lang(request) -> str:
        """Determine appropriate language for the request.

        Selects the most appropriate language based on a priority hierarchy:
        1. Test environment (forces English)
        2. Authenticated user's language preference
        3. Browser's Accept-Language header
        4. Default fallback to English

        Args:
            request: Django HTTP request object containing user and metadata

        Returns:
            str: Activated language code (e.g., 'en', 'it', 'es')

        Note:
            This function has the side effect of activating the selected language
            globally and modifying the request's HTTP_ACCEPT_LANGUAGE header.
        """
        # Force English in test environment to ensure consistent test results
        if os.getenv("PYTEST_CURRENT_TEST"):
            language = "en"
        # Check if user is authenticated and has a language preference
        elif hasattr(request, "user") and hasattr(request.user, "member"):
            if request.user.member.language:
                # Use the user's explicitly set language preference
                language = request.user.member.language
            else:
                # Fall back to browser language detection
                language = translation.get_language_from_request(request)
                found = False
                # Validate that the detected language is supported
                for code, _lang in conf_settings.LANGUAGES:
                    if language == code:
                        found = True
                # Default to English if detected language is not supported
                if not found:
                    language = "en"
        else:
            # For anonymous users, rely on browser language detection
            language = translation.get_language_from_request(request)

        # Activate the selected language globally and update request metadata
        translation.activate(language)
        request.META["HTTP_ACCEPT_LANGUAGE"] = language

        return translation.get_language()
