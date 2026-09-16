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

from larpmanager.utils.auth.sso import extract_after_login_slug, stash_login_slug, stash_pending_next_url

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse

SOCIAL_LOGIN_PREFIX = "/accounts/"
SOCIAL_LOGIN_SUFFIX = "/login/"
# Entry points of a login/signup attempt: only these should overwrite the
# stashed 'next' url. Other /accounts/ pages (password reset, logout, email
# management, ...) can carry an unrelated 'next' and must not hijack it.
LOGIN_SIGNUP_ENTRY_SUFFIXES = ("/login/", "/signup/")


class SocialLoginTargetMiddleware:
    """Remember the organization subdomain and destination a login/signup was started for.

    The 'next' parameter only travels with the current request/session-state,
    which django-allauth keeps in a per-attempt session state that can be
    garbage collected or lost entirely (e.g. a user abandons the login page
    to register through a different entry point, then comes back to log in).
    Storing it separately lets the account adapter still send the user back
    to the right subdomain and page once authentication completes.
    """

    def __init__(self, get_response: Callable) -> None:
        """Initialize middleware with Django's get_response callable."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Stash the target subdomain slug / redirect destination when auth starts."""
        path = request.path
        if path.startswith(SOCIAL_LOGIN_PREFIX) and path.endswith(LOGIN_SIGNUP_ENTRY_SUFFIXES):
            next_url = request.GET.get("next") or request.POST.get("next")
            if next_url:
                stash_pending_next_url(request, next_url)
            if path.endswith(SOCIAL_LOGIN_SUFFIX):
                slug = extract_after_login_slug(next_url)
                if slug:
                    stash_login_slug(request, slug)

        return self.get_response(request)
