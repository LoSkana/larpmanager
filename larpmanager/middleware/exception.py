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

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
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

    def process_exception(self, request, exception):
        """Django middleware exception handler.

        Routes different exception types to appropriate error pages and handles
        permission, not found, and other application-specific errors.
        """
        handlers = [
            (PermissionError, lambda ex: render(request, "exception/permission.html")),
            (NotFoundError, lambda ex: render(request, "exception/notfound.html")),
            (MembershipError, lambda ex: render(request, "exception/membership.html", {"assocs": ex.assocs})),
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
            (FeatureError, lambda ex: self._handle_feature_error(request, ex)),
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
            (
                HiddenError,
                lambda ex: self._redirect_with_message(
                    request,
                    ex.name + " " + _("not visible at this time"),
                    "gallery",
                    [ex.slug],
                    level="warning",
                ),
            ),
            (RedirectError, lambda ex: redirect(ex.view)),
            (MainPageError, lambda ex: redirect("/")),
            (ReturnNowError, lambda ex: ex.value),
            (
                RewokedMembershipError,
                lambda ex: self._redirect_with_message(request, _("You're not allowed to sign up") + "!", "home", []),
            ),
        ]

        for exc_type, handler in handlers:
            if isinstance(exception, exc_type):
                return handler(exception)

        return None

    @staticmethod
    def _redirect_with_message(request, message, viewname, args, level="success"):
        getattr(messages, level)(request, message)
        return redirect(reverse(viewname, args=args))

    @staticmethod
    def _handle_feature_error(request, ex):
        """Handle feature access errors by rendering appropriate error page.

        Args:
            request: HTTP request object
            ex: FeatureError exception containing feature and run information

        Returns:
            Rendered feature error template or raises Http404

        Raises:
            Http404: If association skin is managed or feature/run not found
        """
        # error is association skin is managed
        if request.assoc["skin_managed"]:
            raise Http404("not allowed")

        try:
            feature = Feature.objects.get(slug=ex.feature)
        except ObjectDoesNotExist as err:
            raise Http404("Feature not found") from err

        ctx = {"exe": ex, "feature": feature}

        if feature.overall:
            ctx["permission"] = has_assoc_permission(request, {}, "exe_features")
        else:
            try:
                run = Run.objects.get(pk=ex.run)
            except ObjectDoesNotExist as err:
                raise Http404("Run not found") from err

            ctx["run"] = run
            ctx["permission"] = has_event_permission(request, {}, run.event.slug, "orga_features")

        return render(request, "exception/feature.html", ctx)
