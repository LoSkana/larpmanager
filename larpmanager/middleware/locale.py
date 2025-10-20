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
from django.http import HttpRequest, HttpResponse
from django.utils import translation


class LocaleAdvMiddleware:
    """Advanced locale middleware with user preference support.

    Determines language based on user preferences, falling back to
    browser detection with validation against supported languages.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Activate language for request based on user/browser preferences.

        This middleware method processes incoming requests to determine and activate
        the appropriate language based on user preferences or browser settings.

        Args:
            request: Django HTTP request object containing user and browser information

        Returns:
            HttpResponse object with the appropriate language activated for the request

        Note:
            The language code is stored in request.LANGUAGE_CODE and activated
            globally for the duration of this request processing.
        """
        # Determine the appropriate language for this request
        request.LANGUAGE_CODE = self.get_lang(request)

        # Activate the determined language globally for this request
        translation.activate(request.LANGUAGE_CODE)

        # Process the request with the activated language
        response = self.get_response(request)

        return response

    @staticmethod
    def get_lang(request: HttpRequest) -> str:
        """Determine appropriate language for the request.

        Determines the most appropriate language code to use for internationalization
        based on a priority system: test environment settings override user preferences,
        which override browser detection, which overrides the default fallback.

        Args:
            request: Django HTTP request object containing user and browser information

        Returns:
            str: Two-letter language code (e.g., 'en', 'it') that was activated

        Note:
            This function has the side effect of activating the determined language
            and modifying the request's HTTP_ACCEPT_LANGUAGE header.
        """
        # Check if running in test environment - force English for consistency
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

                # Validate that the detected language is supported
                found = False
                for code, _lang in conf_settings.LANGUAGES:
                    if language == code:
                        found = True

                # Use English as fallback if detected language isn't supported
                if not found:
                    language = "en"
        else:
            # No authenticated user - rely on browser language detection
            language = translation.get_language_from_request(request)

        # Activate the determined language and update request headers
        translation.activate(language)
        request.META["HTTP_ACCEPT_LANGUAGE"] = language

        return translation.get_language()
