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

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from django.contrib.auth import get_user_model, login
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from larpmanager.utils.common import welcome_user
from larpmanager.views.user.member import get_user_backend


class TokenAuthMiddleware:
    """Middleware to handle token-based authentication.

    Processes 'token' query parameters for automatic user login,
    then redirects to clean URL without the token.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process token authentication from query parameters.

        Authenticates users via token in query parameters, then redirects to clean URL
        without the token parameter to prevent token exposure in browser history.

        Args:
            request: Django HTTP request object containing potential token parameter

        Returns:
            HttpResponse: Redirect to clean URL (without token) if token was present,
                         otherwise continues to next middleware/view
        """
        # Extract token from query parameters
        token = request.GET.get("token")
        if token:
            # Attempt to retrieve user ID from cache using token
            user_id = cache.get(f"session_token:{token}")
            if user_id:
                try:
                    # Get user object and authenticate them
                    user = get_user_model().objects.get(pk=user_id)
                    welcome_user(request, user)
                    login(request, user, backend=get_user_backend())
                except get_user_model().DoesNotExist:
                    # Invalid user_id, ignore and continue with redirect
                    pass

            # Parse current URL to remove token parameter
            parsed = urlparse(request.get_full_path())
            query = parse_qs(parsed.query)

            # Remove token from query parameters
            query.pop("token", None)
            cleaned_query = urlencode(query, doseq=True)

            # Reconstruct URL without token and redirect
            clean_url = urlunparse(parsed._replace(query=cleaned_query))
            return redirect(clean_url)

        # No token present, continue to next middleware/view
        return self.get_response(request)
