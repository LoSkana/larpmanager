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
from django.contrib.auth import logout
from django.shortcuts import redirect, render
from django.utils.translation import get_language

from larpmanager.cache.association import get_cache_assoc
from larpmanager.cache.skin import get_cache_skin
from larpmanager.models.association import AssocTextType
from larpmanager.utils.text import get_assoc_text


class AssociationIdentifyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_assoc_info(request) or self.get_response(request)

    @classmethod
    def get_assoc_info(cls, request):
        print("larpmanager/middleware/association.py: request",request)
        # get assoc slug from host
        host = request.get_host().split(":")[0]
        domain = host.split(".")[0]
        #base_domain = ".".join(host.split(".")[-2:])
        base_domain = ".".join(host.split(".")[1:])
        print("larpmanager/middleware/association.py: initial base_domain:",base_domain)

        if os.getenv("env") == "prod":
            request.enviro = "prod"
        elif "xyz" in host:
            request.enviro = "staging"
        else:
            # dev environment
            if not os.getenv("PYTEST_CURRENT_TEST"):
                request.enviro = "dev"
            else:
                request.enviro = "test"

            # base_domain = "ludomanager.it"
            # base_domain = "larpmanager.com"
            # base_domain = "cpularp.com"
            base_domain = "larpmanager.cpularp.com"

        assoc_slug = (
            request.session.get("debug_slug")
            if "debug_slug" in request.session
            else getattr(conf_settings, "SLUG_ASSOC", None) or domain
        )

        print("larpmanager/middleware/association.py: assoc_slug = ",assoc_slug)
        assoc = get_cache_assoc(assoc_slug)
        print("larpmanager/middleware/association.py: assoc = ",assoc)
        if assoc:
            # Jeff Stewart: The below commented out if block and sub-block causes an infinite redirect loop
            # because of the following:
            #   - For some reason the "domain" attribute in "larpmanager_associationskin" for entity "1" is set to "larpmanager.com".
            #       If you modify that value in the database and then shut down the database then the value reverts to "larpmanager.com".
            #   - Because the "base_domain" above is set to "cpularp.com" this causes the original code to redirect you to the value of
            #       '$slug$.larpmanager.com' which is not where I want to go because I am self-hosting this application.
            #   - Changing "domain", below, to "cpularp.com" causes the rewrite to take you to "larpmanager.cpularp.com". This results in
            #       an infinite redirect loop because everytime you go to larpmanager.cpularp.com it ends up trapped in this code section.
            #   - So I commented out the below. Doing so allows me to get to the actual administration page.
            #if "main_domain" in assoc and assoc["main_domain"] != base_domain:
            #    print("larpmanager/middleware/association.py: base_domain:",base_domain)
            #    if request.enviro == "prod":
            #        slug = assoc["slug"]
            #        domain = assoc["main_domain"] # original code. I replaced with domain = "cpularp.com" to try to fix larpmanager.com redirects.
            #        # domain = "cpularp.com"
            #        print("larpmanager/middleware/association.py: slug:", assoc["slug"]," | main_domain:", assoc["main_domain"])
            #        print(f"larpmanager/middleware/association.py: redirecting to https://{slug}.{domain}{request.get_full_path()}")
            #        return redirect(f"https://{slug}.{domain}{request.get_full_path()}")
            print("larpmanager/middleware/association.py: attempting to load request:",request," | assoc:", assoc)
            return cls.load_assoc(request, assoc)

        return cls.get_main_info(request, base_domain)

    @classmethod
    def get_main_info(cls, request, base_domain):
        # if logged in with demo user visiting main page, logout
        user = request.user
        if not request.path.startswith("/after_login/"):
            if user.is_authenticated and user.email.lower().endswith("demo.it"):
                logout(request)
                return redirect(request.path)

        skin = get_cache_skin(base_domain)
        if skin:
            return cls.load_assoc(request, skin)

        #if request.get_host().endswith("larpmanager.com"):
            #return redirect(f"https://larpmanager.com{request.get_full_path()}")

        if request.get_host().endswith("larpmanager.cpularp.com"):
            return redirect(f"https://larpmanager.cpularp.com{request.get_full_path()}")

        if request.path.startswith("/admin"):
            return

        return render(request, "exception/assoc.html", {})

    @staticmethod
    def load_assoc(request, assoc):
        print("larpmanager/middleware/association.py: inside load_assoc(request:",request," | assoc: ",assoc)
        request.assoc = assoc
        lang = get_language()
        request.assoc["footer"] = get_assoc_text(request.assoc["id"], AssocTextType.FOOTER, lang)
