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
from __future__ import annotations

from typing import TYPE_CHECKING

from larpmanager.utils.auth.sso import extract_after_login_slug, stash_login_slug

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse

SOCIAL_LOGIN_PREFIX = "/accounts/"
SOCIAL_LOGIN_SUFFIX = "/login/"


class SocialLoginTargetMiddleware:
    """Remember the organization subdomain a social login is started for.

    The subdomain only travels in the 'next' parameter of the provider login
    URL, which django-allauth keeps in a per-attempt session state that can be
    garbage collected. Storing the slug separately lets the account adapter
    still send the user back to the right subdomain.
    """

    def __init__(self, get_response: Callable) -> None:
        """Initialize middleware with Django's get_response callable."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Stash the target subdomain slug when a social login starts."""
        path = request.path
        if path.startswith(SOCIAL_LOGIN_PREFIX) and path.endswith(SOCIAL_LOGIN_SUFFIX):
            next_url = request.GET.get("next") or request.POST.get("next")
            slug = extract_after_login_slug(next_url)
            if slug:
                stash_login_slug(request, slug)

        return self.get_response(request)
