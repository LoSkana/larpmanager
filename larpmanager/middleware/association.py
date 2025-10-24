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
from typing import Optional

from django.conf import settings as conf_settings
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import get_language

from larpmanager.cache.association import get_cache_assoc
from larpmanager.cache.skin import get_cache_skin
from larpmanager.models.association import AssocTextType
from larpmanager.utils.text import get_assoc_text


class AssociationIdentifyMiddleware:
    """Middleware to identify and load association data from request domain.

    Handles subdomain routing, environment detection, and association
    context loading for multi-tenant functionality.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Process request through association middleware.

        Args:
            request: Django HTTP request object

        Returns:
            HttpResponse: Either a redirect or the normal response
        """
        return self.get_assoc_info(request) or self.get_response(request)

    @classmethod
    def get_assoc_info(cls, request) -> Optional[HttpResponse]:
        """Extract association information from request domain.

        Determines the environment based on host domain, extracts subdomain to identify
        the target association, loads association data from cache, and handles domain
        redirects for proper multi-tenant routing.

        Args:
            request: Django HTTP request object containing host and session data

        Returns:
            HttpResponse: Redirect response if domain mismatch requires redirect
            None: Continue processing if association found and domain is correct

        Raises:
            No exceptions are raised directly by this method
        """
        # Extract host components for domain analysis
        host = request.get_host().split(":")[0]
        domain = host.split(".")[0]
        base_domain = ".".join(host.split(".")[-2:])

        # Determine environment based on host characteristics
        if os.getenv("env") == "prod":
            request.enviro = "prod"
        elif "xyz" in host:
            request.enviro = "staging"
        else:
            # Handle dev/test environment detection
            if not os.getenv("PYTEST_CURRENT_TEST"):
                request.enviro = "dev"
            else:
                request.enviro = "test"

            # Override base domain for development environments
            base_domain = "larpmanager.com"

        # Resolve association slug from multiple sources
        conf_slug = getattr(conf_settings, "SLUG_ASSOC", None)
        assoc_slug = request.session.get("debug_slug") if "debug_slug" in request.session else conf_slug or domain

        # Attempt to load association data from cache
        assoc = get_cache_assoc(assoc_slug)
        if assoc:
            # Check for domain mismatch requiring redirect
            if "main_domain" in assoc and assoc["main_domain"] != base_domain:
                if request.enviro == "prod" and not conf_slug:
                    slug = assoc["slug"]
                    domain = assoc["main_domain"]
                    return redirect(f"https://{slug}.{domain}{request.get_full_path()}")
            return cls.load_assoc(request, assoc)

        # Fallback to main domain handling
        return cls.get_main_info(request, base_domain)

    @classmethod
    def get_main_info(cls, request: HttpRequest, base_domain: str) -> Optional[HttpResponse]:
        """Handle requests to main domain without specific association.

        Handles demo user logout, skin loading, and default redirects
        for the main application domain.

        Args:
            request: Django HTTP request object containing user session and path info
            base_domain: Base domain name used for skin lookup and routing decisions

        Returns:
            HttpResponse for redirects/renders, or None to continue normal processing

        Note:
            Demo users (ending with 'demo.it') are automatically logged out when
            visiting the main page, except for post-login flows.
        """
        # Check for demo user logout requirement - skip if already in post-login flow
        user = request.user
        if not request.path.startswith("/after_login/"):
            # Demo users should be logged out when visiting main domain
            if user.is_authenticated and user.email.lower().endswith("demo.it"):
                logout(request)
                return redirect(request.path)

        # Attempt to load association skin for the base domain
        skin = get_cache_skin(base_domain)
        if skin:
            # Skin found - load the associated organization
            return cls.load_assoc(request, skin)

        # Handle larpmanager.com domain redirects to ensure HTTPS
        if request.get_host().endswith("larpmanager.com"):
            return redirect(f"https://larpmanager.com{request.get_full_path()}")

        # Allow admin panel access without association
        if request.path.startswith("/admin"):
            return

        # No valid association found - render error page
        return render(request, "exception/assoc.html", {})

    @staticmethod
    def load_assoc(request: HttpRequest, association_data: dict) -> None:
        """Load association data into request context.

        This function enriches the request object with association data and
        localized footer text for the current language.

        Args:
            request: Django HTTP request object to be modified
            association_data: Association data dictionary containing at minimum an 'id' key

        Returns:
            None

        Side Effects:
            - Sets request.assoc with the provided association data
            - Adds localized footer text to request.assoc["footer"]
        """
        # Attach association data to request for template access
        request.assoc = association_data

        # Get current language for localization
        current_language = get_language()

        # Load and attach localized footer text for the association
        request.assoc["footer"] = get_assoc_text(request.assoc["id"], AssocTextType.FOOTER, current_language)
