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
        if response.status_code == 404 and not conf_settings.DEBUG:
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

    def check(self, request, response):
        domain = request.get_host()
        path = request.get_full_path()

        referer = request.META.get("HTTP_REFERER", "None")
        if "?" in referer:
            return

        ua = request.META.get("HTTP_USER_AGENT", "<none>")
        for s in ["bot", "facebookexternalhit"]:
            if s in str(ua):
                return

        # print(domain)
        # print(path)
        if domain == "larpmanager.com" and "$" in path:
            aux = path.split("$")
            # print (at)
            url = "https://" + aux[1] + ".larpmanager.com/" + aux[0]
            return HttpResponseRedirect(url)

        if self.is_ignorable_404(path):
            return

        if "webhook" not in path and not request.user.is_authenticated:
            return

        html = response.content.decode("utf-8")
        exception = re.search('<span class="exception-404">(.*)</span>', html, re.IGNORECASE)
        if exception:
            exception = exception.group(1)

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
