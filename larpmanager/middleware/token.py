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
import logging
from collections.abc import Callable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from django.contrib.auth import get_user_model, login
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from larpmanager.utils.auth.sso import session_token_key
from larpmanager.utils.core.common import welcome_user
from larpmanager.views.user.member import get_user_backend

logger = logging.getLogger(__name__)


class TokenAuthMiddleware:
    """Middleware to handle token-based authentication.

    Processes 'token' query parameters for automatic user login,
    then redirects to clean URL without the token.
    """

    def __init__(self, get_response: Callable) -> None:
        """Initialize middleware with Django's get_response callable."""
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
            Token is validated against cached user_id. Invalid, expired or already
            used tokens do not authenticate the user; they are only logged, as the
            token value itself must never reach the response.

        """
        # Extract authentication token from query parameters
        token = request.GET.get("token")
        if token:
            # Retrieve user_id associated with this token from cache
            user_id = cache.get(session_token_key(token))
            if user_id:
                try:
                    # Authenticate user if valid user_id found
                    user = get_user_model().objects.get(pk=user_id)
                    welcome_user(request, user)
                    login(request, user, backend=get_user_backend())
                    # Delete token after use to prevent replay attacks
                    cache.delete(session_token_key(token))
                except get_user_model().DoesNotExist:
                    # Token pointed at a user that no longer exists
                    logger.warning("Cross-subdomain login token referenced missing user %s", user_id)
            else:
                # Expired, already used or forged token: the user stays anonymous
                logger.info(
                    "Cross-subdomain login token not found in cache for host %s path %s",
                    request.get_host(),
                    request.path,
                )

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
