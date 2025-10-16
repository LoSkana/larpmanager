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
from typing import Optional

from django.conf import settings as conf_settings
from django.core.mail import mail_managers
from django.http import HttpResponseRedirect


class BrokenLinkEmailsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        Send broken link emails for relevant 404 NOT FOUND responses.
        """
        response = self.get_response(request)
        broken_link_status = 404
        if response.status_code == broken_link_status and not conf_settings.DEBUG:
            res = self.check(request, response)
            if res:
                return res
        return response

    @staticmethod
    def is_ignorable_404(uri):
        """
        Returns True if a 404 at the given URL *shouldn't* notify the site managers.
        """
        return any(pattern.search(uri) for pattern in conf_settings.IGNORABLE_404_URLS)

    def check(self, request, response) -> Optional[HttpResponseRedirect]:
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
            return

        # Filter out bot traffic to reduce noise
        ua = request.META.get("HTTP_USER_AGENT", "<none>")
        for s in ["bot", "facebookexternalhit"]:
            if s in str(ua):
                return

        # Handle domain redirection for larpmanager.com with $ separator
        # print(domain)
        # print(path)
        if domain == "larpmanager.com" and "$" in path:
            aux = path.split("$")
            # print (at)
            url = "https://" + aux[1] + ".larpmanager.com/" + aux[0]
            return HttpResponseRedirect(url)

        # Skip ignorable 404 paths (common crawlers, assets, etc.)
        if self.is_ignorable_404(path):
            return

        # Only process authenticated users or webhook paths
        if "webhook" not in path and not request.user.is_authenticated:
            return

        # Extract exception information from response HTML
        html = response.content.decode("utf-8")
        exception = re.search('<span class="exception-404">(.*)</span>', html, re.IGNORECASE)
        if exception:
            exception = exception.group(1)

        # Send detailed error report to administrators
        ip = request.META.get("REMOTE_ADDR", "<none>")
        mail_managers(
            f"Broken link on {domain}",
            f"Requested URL: {path}\n"
            f"Exception: {exception}\n"
            f"User: {str(request.user)}\n"
            f"Referrer: {referer}\n"
            f"User agent: {ua}\n"
            f"IP address: {ip}\n\n"
            f"{vars(request)}",
            fail_silently=True,
        )
