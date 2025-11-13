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
from collections.abc import Callable
from typing import Any

from django.conf import settings as conf_settings
from django.http import HttpRequest
from django.utils import translation


class LocaleAdvMiddleware:
    """Advanced locale middleware with user preference support.

    Determines language based on user preferences, falling back to
    browser detection with validation against supported languages.
    """

    def __init__(self, get_response: Callable) -> None:
        """Initialize middleware with Django response handler."""
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request: Any) -> Any:
        """Activate language for request based on user/browser preferences.

        Args:
            request: Django HTTP request object

        Returns:
            HttpResponse: Response with activated language

        """
        request.LANGUAGE_CODE = self.get_lang(request)
        translation.activate(request.LANGUAGE_CODE)
        return self.get_response(request)

    @staticmethod
    def get_lang(request: HttpRequest) -> str:
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
            selected_language = "en"
        # Check if user is authenticated and has a language preference
        elif hasattr(request, "user") and hasattr(request.user, "member"):
            if request.user.member.language:
                # Use the user's explicitly set language preference
                selected_language = request.user.member.language
            else:
                # Fall back to browser language detection
                browser_language = translation.get_language_from_request(request)
                is_language_supported = False
                # Validate that the detected language is supported
                for language_code, _language_name in conf_settings.LANGUAGES:
                    if browser_language == language_code:
                        is_language_supported = True
                # Default to English if detected language is not supported
                selected_language = "en" if not is_language_supported else browser_language
        else:
            # For anonymous users, rely on browser language detection
            selected_language = translation.get_language_from_request(request)

        # Activate the selected language globally and update request metadata
        translation.activate(selected_language)
        request.META["HTTP_ACCEPT_LANGUAGE"] = selected_language

        return translation.get_language()
