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
from typing import Optional

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.role import has_assoc_permission, has_event_permission
from larpmanager.models.base import Feature
from larpmanager.models.event import DevelopStatus, Run
from larpmanager.utils.exceptions import (
    FeatureError,
    HiddenError,
    MainPageError,
    MembershipError,
    NotFoundError,
    PermissionError,
    RedirectError,
    ReturnNowError,
    RewokedMembershipError,
    SignupError,
    UnknowRunError,
    WaitingError,
)


class ExceptionHandlingMiddleware:
    """Handle permission / missing feature instead of raising a 404."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request: HttpRequest, exception: Exception) -> Optional[HttpResponse]:
        """Process Django middleware exceptions and route to appropriate handlers.

        Args:
            request: The HTTP request object that triggered the exception
            exception: The exception instance that was raised

        Returns:
            HttpResponse object for handled exceptions, None for unhandled exceptions

        Note:
            This method handles application-specific exceptions by routing them to
            appropriate error pages or redirect responses. Unhandled exceptions
            return None to allow Django's default exception handling.
        """
        # Define exception type to handler mappings for clean separation of concerns
        handlers = [
            # Permission-related errors - show appropriate error pages
            (PermissionError, lambda ex: render(request, "exception/permission.html")),
            (NotFoundError, lambda ex: render(request, "exception/notfound.html")),
            (MembershipError, lambda ex: render(request, "exception/membership.html", {"assocs": ex.assocs})),
            # Run-related errors - show available runs for the current association
            (
                UnknowRunError,
                lambda ex: render(
                    request,
                    "exception/runs.html",
                    {
                        "runs": Run.objects.filter(development=DevelopStatus.SHOW)
                        .exclude(event__visible=False)
                        .select_related("event")
                        .filter(event__assoc_id=request.assoc["id"])
                        .order_by("-end")
                    },
                ),
            ),
            # Feature and access control errors - delegate to specialized handlers
            (FeatureError, lambda ex: self._handle_feature_error(request, ex)),
            # Registration and signup flow errors - redirect with informative messages
            (
                SignupError,
                lambda ex: self._redirect_with_message(
                    request, _("To access this feature, you must first register") + "!", "register", [ex.slug]
                ),
            ),
            (
                WaitingError,
                lambda ex: self._redirect_with_message(
                    request, _("This feature is available for non-waiting tickets") + "!", "register", [ex.slug]
                ),
            ),
            # Content visibility and access errors
            (
                HiddenError,
                lambda ex: self._redirect_with_message(
                    request, ex.name + " " + _("not visible at this time"), "gallery", [ex.slug]
                ),
            ),
            # Flow control exceptions - handle redirects and early returns
            (RedirectError, lambda ex: redirect(ex.view)),
            (ReturnNowError, lambda ex: ex.value),
            # Domain and membership management errors
            (
                MainPageError,
                lambda ex: redirect(f"https://{ex.base_domain}/{ex.path or request.path}"),
            ),
            (
                RewokedMembershipError,
                lambda ex: self._redirect_with_message(request, _("You're not allowed to sign up") + "!", "home", []),
            ),
        ]

        # Iterate through handlers and process the first matching exception type
        for exc_type, handler in handlers:
            if isinstance(exception, exc_type):
                return handler(exception)

        # Return None for unhandled exceptions to use Django's default handling
        return None

    @staticmethod
    def _redirect_with_message(request, message, viewname, args, level="success"):
        getattr(messages, level)(request, message)
        return redirect(reverse(viewname, args=args))

    @staticmethod
    def _handle_feature_error(request: HttpRequest, ex: FeatureError) -> HttpResponse:
        """Handle feature access errors by rendering appropriate error page.

        This function processes FeatureError exceptions by determining the appropriate
        error response based on association settings and feature permissions.

        Args:
            request: The HTTP request object containing user and association context
            ex: FeatureError exception containing feature slug and run ID information

        Returns:
            HttpResponse: Rendered feature error template with context data

        Raises:
            Http404: If association skin is managed, or if feature/run objects are not found
        """
        # Check if association skin is managed - if so, deny access completely
        if request.assoc["skin_managed"]:
            raise Http404("not allowed")

        # Retrieve the feature object or raise 404 if not found
        try:
            feature = Feature.objects.get(slug=ex.feature)
        except ObjectDoesNotExist as err:
            raise Http404("Feature not found") from err

        # Build base context with exception and feature data
        ctx = {"exe": ex, "feature": feature}

        # Handle permission checking based on feature scope
        if feature.overall:
            # For organization-wide features, check association permissions
            ctx["permission"] = has_assoc_permission(request, {}, "exe_features")
        else:
            # For event-specific features, retrieve run and check event permissions
            try:
                run = Run.objects.get(pk=ex.run)
            except ObjectDoesNotExist as err:
                raise Http404("Run not found") from err

            # Add run context and check event-level permissions
            ctx["run"] = run
            ctx["permission"] = has_event_permission(request, {}, run.event.slug, "orga_features")

        # Render the feature error template with assembled context
        return render(request, "exception/feature.html", ctx)
