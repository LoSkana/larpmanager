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

        Authenticates users via token from URL query parameters, then redirects
        to a clean URL without the token parameter to maintain security.

        Args:
            request: Django HTTP request object containing potential token parameter

        Returns:
            HttpResponse: Redirect response to clean URL if token found,
                         otherwise normal middleware response

        Note:
            Token is validated against cached user_id. Invalid tokens or users
            are silently ignored for security reasons.
        """
        # Extract authentication token from query parameters
        token = request.GET.get("token")
        if token:
            # Retrieve user_id associated with this token from cache
            user_id = cache.get(f"session_token:{token}")
            if user_id:
                try:
                    # Authenticate user if valid user_id found
                    user = get_user_model().objects.get(pk=user_id)
                    welcome_user(request, user)
                    login(request, user, backend=get_user_backend())
                except get_user_model().DoesNotExist:
                    # Invalid user_id, ignore silently for security
                    pass

            # Parse current URL to remove token parameter
            parsed = urlparse(request.get_full_path())
            query = parse_qs(parsed.query)

            # Remove token from query parameters and rebuild URL
            query.pop("token", None)
            cleaned_query = urlencode(query, doseq=True)
            clean_url = urlunparse(parsed._replace(query=cleaned_query))

            # Redirect to clean URL without token exposure
            return redirect(clean_url)

        # Continue with normal request processing if no token
        return self.get_response(request)
