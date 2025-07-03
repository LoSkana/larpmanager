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

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core.cache import cache
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from larpmanager.views.user.member import get_user_backend


class TokenAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = request.GET.get("token")
        if token:
            print(token)
            user_id = cache.get(f"session_token:{token}")
            print(user_id)
            if user_id:
                user = get_user_model().objects.get(pk=user_id)
                print(user)
                if user:
                    messages.success(request, _("Welcome") + ", " + str(user) + "!")
                    login(request, user, backend=get_user_backend())

            # remove token and redirect
            parsed = urlparse(request.get_full_path())
            query = parse_qs(parsed.query)
            query.pop("token", None)
            cleaned_query = urlencode(query, doseq=True)
            clean_url = urlunparse(parsed._replace(query=cleaned_query))

            return redirect(clean_url)

        return self.get_response(request)
