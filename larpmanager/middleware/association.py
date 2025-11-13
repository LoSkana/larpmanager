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
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from django.conf import settings as conf_settings
from django.contrib.auth import logout
from django.shortcuts import redirect, render
from django.utils.translation import get_language

from larpmanager.cache.association import get_cache_association
from larpmanager.cache.association_text import get_association_text
from larpmanager.cache.skin import get_cache_skin
from larpmanager.models.association import AssociationTextType
from typing import Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse


class AssociationIdentifyMiddleware:
    """Middleware to identify and load association data from request domain.

    Handles subdomain routing, environment detection, and association
    context loading for multi-tenant functionality.
    """

    def __init__(self, get_response: Callable) -> None:
        """Initialize middleware with Django response handler."""
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        """Process request through association middleware.

        Args:
            request: Django HTTP request object

        Returns:
            HttpResponse: Either a redirect or the normal response

        """
        return self.get_association_info(request) or self.get_response(request)

    @classmethod
    def get_association_info(cls, request: HttpRequest) -> HttpResponse | None:
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
        request_host = request.get_host().split(":")[0]
        subdomain = request_host.split(".")[0]
        base_domain = ".".join(request_host.split(".")[-2:])

        # Determine environment based on host characteristics
        if os.getenv("ENV") == "prod":
            request.enviro = "prod"
        elif "xyz" in request_host:
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
        configured_slug = getattr(conf_settings, "SLUG_ASSOC", None)
        association_slug = (
            request.session.get("debug_slug") if "debug_slug" in request.session else configured_slug or subdomain
        )

        # Attempt to load association data from cache
        association_data = get_cache_association(association_slug)
        if association_data:
            # Check for domain mismatch requiring redirect
            if "main_domain" in association_data and association_data["main_domain"] != base_domain:
                if request.enviro == "prod" and not configured_slug:
                    association_slug = association_data["slug"]
                    association_domain = association_data["main_domain"]
                    return redirect(f"https://{association_slug}.{association_domain}{request.get_full_path()}")
            return cls.load_association(request, association_data)

        # Fallback to main domain handling
        return cls.get_main_info(request, base_domain)

    @classmethod
    def get_main_info(cls, request: HttpRequest, base_domain: str) -> HttpResponse | None:
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
        current_user = request.user
        if not request.path.startswith("/after_login/"):
            # Demo users should be logged out when visiting main domain
            if current_user.is_authenticated and current_user.email.lower().endswith("demo.it"):
                logout(request)
                return redirect(request.path)

        # Attempt to load association skin for the base domain
        association_skin = get_cache_skin(base_domain)
        if association_skin:
            # Skin found - load the associated organization
            return cls.load_association(request, association_skin)

        # Handle larpmanager.com domain redirects to ensure HTTPS
        if request.get_host().endswith("larpmanager.com"):
            return redirect(f"https://larpmanager.com{request.get_full_path()}")

        # Allow admin panel access without association
        if request.path.startswith("/admin"):
            return None

        # No valid association found - render error page
        return render(request, "exception/association.html", {})

    @staticmethod
    def load_association(request: HttpRequest, association_data: dict) -> None:
        """Load association data into request context.

        This function enriches the request object with association data and
        localized footer text for the current language.

        Args:
            request: Django HTTP request object to be modified
            association_data: Association data dictionary containing at minimum an 'id' key

        Returns:
            None

        Side Effects:
            - Sets request.association with the provided association data
            - Adds localized footer text to request.association["footer"]

        """
        # Attach association data to request for template access
        request.association = association_data

        # Get current language for localization
        current_language = get_language()

        # Load and attach localized footer text for the association
        request.association["footer"] = get_association_text(
            request.association["id"],
            AssociationTextType.FOOTER,
            current_language,
        )
