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

import re
from collections.abc import Callable

from django.conf import settings as conf_settings
from django.core.mail import mail_managers
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect


class BrokenLinkEmailsMiddleware:
    def __init__(self, get_response: Callable) -> None:
        """Initialize middleware with the response handler."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Send broken link emails for relevant 404 NOT FOUND responses.

        Args:
            request: The HTTP request object being processed.

        Returns:
            The HTTP response object, potentially modified if a broken link
            was detected and processed.

        """
        # Get the initial response from the next middleware or view
        response = self.get_response(request)

        # Define the status code we're interested in monitoring
        broken_link_status = 404

        # Only process 404 errors when not in debug mode
        if response.status_code == broken_link_status and not conf_settings.DEBUG:
            # Check if this broken link should trigger an email notification
            res = self.check(request, response)
            if res:
                return res

        return response

    @staticmethod
    def is_ignorable_404(request_uri):
        """Return True if a 404 at the given URL *shouldn't* notify the site managers."""
        return any(url_pattern.search(request_uri) for url_pattern in conf_settings.IGNORABLE_404_URLS)

    def check(self, request, response) -> HttpResponseRedirect | None:
        """Middleware for detecting and logging broken links.

        Monitors for 404 errors and tracks problematic URLs for debugging,
        filtering out bot traffic and ignorable URLs, and sending detailed
        error reports to administrators.

        Args:
            request: The HTTP request object containing metadata and user info
            response: The HTTP response object with content and status code

        Returns:
            HttpResponseRedirect if a domain redirect is needed, None otherwise

        """
        # Extract basic request information
        domain = request.get_host()
        path = request.get_full_path()

        # Skip processing if referer contains query parameters
        referer = request.META.get("HTTP_REFERER", "None")
        if "?" in referer:
            return None

        # Filter out bot traffic to reduce noise
        user_agent = request.META.get("HTTP_USER_AGENT", "<none>")
        for bot_identifier in ["bot", "facebookexternalhit"]:
            if bot_identifier in str(user_agent):
                return None

        # Handle domain redirection for larpmanager.com with $ separator
        # print(domain)
        # print(path)
        if domain == "larpmanager.com" and "$" in path:
            path_parts = path.split("$")
            # print (at)
            url = "https://" + path_parts[1] + ".larpmanager.com/" + path_parts[0]
            return HttpResponseRedirect(url)

        # Skip ignorable 404 paths (common crawlers, assets, etc.)
        if self.is_ignorable_404(path):
            return None

        # Only process authenticated users or webhook paths
        if "webhook" not in path and not request.user.is_authenticated:
            return None

        # Extract exception information from response HTML
        html_content = response.content.decode("utf-8")
        exception = re.search('<span class="exception-404">(.*)</span>', html_content, re.IGNORECASE)
        if exception:
            exception = exception.group(1)

        # Send detailed error report to administrators
        ip_address = request.META.get("REMOTE_ADDR", "<none>")
        mail_managers(
            f"Broken link on {domain}",
            f"Requested URL: {path}\n"
            f"Exception: {exception}\n"
            f"User: {str(request.user)}\n"
            f"Referrer: {referer}\n"
            f"User agent: {user_agent}\n"
            f"IP address: {ip_address}\n\n"
            f"{vars(request)}",
            fail_silently=True,
        )
        return None
