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
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.role import has_assoc_permission, has_event_permission
from larpmanager.models.base import Feature
from larpmanager.models.event import Run
from larpmanager.utils.exceptions import (
    PermissionException,
    NotFoundException,
    MembershipException,
    UnknowRunException,
    FeatureException,
    SignupException,
    WaitingException,
    HiddenException,
    RedirectException,
)


class ExceptionHandlingMiddleware:
    """Handle permission / missing feature instead of raising a 404."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    @staticmethod
    def process_exception(request, exception):
        if isinstance(exception, PermissionException):
            return render(request, "exception/permission.html")

        if isinstance(exception, NotFoundException):
            return render(request, "exception/notfound.html")

        if isinstance(exception, MembershipException):
            ctx = {"assocs": exception.assocs}
            return render(request, "exception/membership.html", ctx)

        if isinstance(exception, UnknowRunException):
            runs = (
                Run.objects.filter(development=Run.SHOW)
                .exclude(event__visible=False)
                .select_related("event")
                .filter(event__assoc_id=request.assoc["id"])
                .order_by("-end")
            )
            return render(request, "exception/runs.html", {"runs": runs})

        if isinstance(exception, FeatureException):
            feature = Feature.objects.get(slug=exception.feature)
            ctx = {"exe": exception, "feature": feature}

            # check if the user has the permission to add features
            if feature.overall:
                ctx["permission"] = has_assoc_permission(request, "exe_features")
            else:
                ctx["run"] = Run.objects.get(pk=exception.run)
                ctx["permission"] = has_event_permission({}, request, ctx["run"].event.slug, "orga_features")

            return render(request, "exception/feature.html", ctx)

        if isinstance(exception, SignupException):
            mes = _("To access this feature, you must first register!")
            messages.success(request, mes)
            args = [exception.slug, exception.number]
            return HttpResponseRedirect(reverse("register", args=args))

        if isinstance(exception, WaitingException):
            mes = _("This feature is available for non-waiting tickets!")
            messages.success(request, mes)
            args = [exception.slug, exception.number]
            return HttpResponseRedirect(reverse("register", args=args))

        if isinstance(exception, HiddenException):
            messages.warning(request, exception.name + " " + _("not visible at this time"))
            args = [exception.slug, exception.number]
            return HttpResponseRedirect(reverse("gallery", args=args))

        if isinstance(exception, RedirectException):
            return redirect(exception.view)

        return None  # Middlewares should return None when not applied
