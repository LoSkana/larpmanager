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
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        request.LANGUAGE_CODE = self.get_lang(request)
        translation.activate(request.LANGUAGE_CODE)
        response = self.get_response(request)
        return response

    @staticmethod
    def get_lang(request):
        if os.getenv("PYTEST_CURRENT_TEST"):
            language = "en"
        elif hasattr(request, "user") and hasattr(request.user, "member"):
            if request.user.member.language:
                language = request.user.member.language
            else:
                language = translation.get_language_from_request(request)
                found = False
                for code, lang in conf_settings.LANGUAGES:
                    if language == code:
                        found = True
                if not found:
                    language = "en"
        else:
            language = translation.get_language_from_request(request)

        translation.activate(language)
        request.META["HTTP_ACCEPT_LANGUAGE"] = language

        return translation.get_language()
