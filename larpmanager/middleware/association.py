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

import os

from django.conf import settings as conf_settings
from django.shortcuts import redirect, render
from django.utils.translation import get_language

from larpmanager.cache.association import get_cache_assoc
from larpmanager.models.association import AssocTextType
from larpmanager.utils.text import get_assoc_text


class AssociationIdentifyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_assoc_info(request) or self.get_response(request)

    @classmethod
    def get_assoc_info(cls, request):
        # get assoc slug from host
        host = request.get_host().split(":")[0]
        domain = host.split(".")[0]
        base_domain = ".".join(host.split(".")[-2:])

        local = False
        if os.getenv("env") == "prod":
            request.enviro = "prod"
        elif "xyz" in host:
            request.enviro = "staging"
        else:
            # dev environment
            local = True
            if not os.getenv("PYTEST_CURRENT_TEST"):
                request.enviro = "dev"
            else:
                request.enviro = "test"

        assoc_slug = request.session.get("debug_slug", None) or getattr(conf_settings, "SLUG_ASSOC", None) or domain

        assoc = get_cache_assoc(assoc_slug)
        if assoc:
            if "skin_domain" in assoc and assoc["skin_domain"] != base_domain:
                slug = assoc["slug"]
                domain = assoc["skin_domain"]
                return redirect(f"https://{slug}.{domain}{request.get_full_path()}")
            return cls.load_assoc(request, assoc, base_domain)

        if local or domain == "larpmanager":
            assoc = {
                "id": 0,
                "name": "LarpManager",
                "shuttle": [],
                "features": ["assoc_css"],
                "css_code": "main",
                "slug": "lm",
                "logo": "https://larpmanager.com/static/lm_logo.png",
                "main_mail": "info@larpmanager.com",
                "favicon": "https://larpmanager.com/static/lm_fav.png",
            }
            return cls.load_assoc(request, assoc)

        if request.get_host().endswith("larpmanager.com"):
            return redirect(f"https://larpmanager.com{request.get_full_path()}")

        if request.path.startswith("/admin"):
            return

        return render(request, "exception/assoc.html", {})

    @staticmethod
    def load_assoc(request, assoc, base_domain):
        request.assoc = assoc
        lang = get_language()
        request.assoc["footer"] = get_assoc_text(request.assoc["id"], AssocTextType.FOOTER, lang)
