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

from django.shortcuts import redirect


class CorrectUrlMiddleware:
    """
    If the url is incorrect, redirect to a fixed url.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.get_full_path()

        if "//" in path and "accounts/google/login/" not in path:
            return redirect(path.replace("//", "/"))

        # check if there is an "undefined" at the end (social media redirects)
        parsed_url = urlparse(path)
        path_parts = parsed_url.path.split("/")
        if path_parts[-1] == "undefined":
            path_parts = path_parts[:-1]
            cleaned_path = "/".join(path_parts)
            cleaned_url = urlunparse((parsed_url.scheme, parsed_url.netloc, cleaned_path, "", "", ""))
            return redirect(cleaned_url)

        for char in ['"', "'", "$"]:
            if path.endswith(char):
                return redirect(path.strip(char))

        response = self.get_response(request)

        return response
