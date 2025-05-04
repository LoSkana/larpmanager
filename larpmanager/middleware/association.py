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
from django.shortcuts import redirect
from django.utils.translation import get_language

from larpmanager.cache.association import get_cache_assoc
from larpmanager.models.association import AssocTextType
from larpmanager.utils.text import get_assoc_text


class AssociationIdentifyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.assoc = self.get_assoc_info(request)
        if not request.assoc:
            return redirect("https://larpmanager.com")

        lang = get_language()
        request.assoc["footer"] = get_assoc_text(request.assoc["id"], AssocTextType.FOOTER, lang)

        response = self.get_response(request)

        return response

    @staticmethod
    def get_assoc_info(request):
        # get assoc slug from host
        hst = request.get_host()

        def_assocs = {
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

        host_part = hst.split(":")[0]
        if host_part in ["127.0.0.1", "localhost"]:  # dev environment
            if not os.getenv("PYTEST_CURRENT_TEST"):
                request.enviro = "dev"
            else:
                request.enviro = "test"
        else:
            assoc_slug = request.get_host().split(".")[0]
            if "xyz" in hst:
                request.enviro = "staging"
            else:
                request.enviro = "prod"

        assoc_slug = (
            request.session.get("debug_slug", None)
            or getattr(conf_settings, "SLUG_ASSOC", None)
            or request.get_host().split(".")[0]
        )

        assoc = get_cache_assoc(assoc_slug)
        if assoc:
            return assoc

        return def_assocs
