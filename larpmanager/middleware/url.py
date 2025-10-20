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

from urllib.parse import urlparse, urlunparse

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


class CorrectUrlMiddleware:
    """Middleware to fix common URL formatting issues.

    Handles double slashes, trailing 'undefined' segments from social media
    redirects, and unwanted trailing characters in URLs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process request and fix common URL formatting issues.

        This middleware handles various URL malformation issues that can occur
        from external redirects, social media links, or client-side routing errors.

        Args:
            request: Django HTTP request object containing the incoming request data

        Returns:
            HttpResponse: Either a redirect response to the corrected URL or the
                         normal response from the next middleware/view in the chain

        Note:
            This middleware should be placed early in the middleware stack to
            catch URL issues before they reach view processing.
        """
        path = request.get_full_path()

        # Fix double slashes in URLs, but preserve Google OAuth callback URLs
        # which legitimately contain double slashes in their structure
        if "//" in path and "accounts/google/login/" not in path:
            return redirect(path.replace("//", "/"))

        # Handle "undefined" suffixes commonly added by JavaScript redirects
        # Parse the URL to safely manipulate path components
        parsed_url = urlparse(path)
        path_parts = parsed_url.path.split("/")

        # Remove trailing "undefined" from social media or JS redirects
        if path_parts[-1] == "undefined":
            path_parts = path_parts[:-1]
            cleaned_path = "/".join(path_parts)
            # Reconstruct URL without query params or fragments to avoid issues
            cleaned_url = urlunparse((parsed_url.scheme, parsed_url.netloc, cleaned_path, "", "", ""))
            return redirect(cleaned_url)

        # Strip common trailing characters that break URL parsing
        # These often come from copy-paste errors or malformed links
        for char in ['"', "'", "$"]:
            if path.endswith(char):
                return redirect(path.strip(char))

        # No URL issues found, continue with normal request processing
        response = self.get_response(request)

        return response
