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
"""Confirmation interstitial for state-changing endpoints reached via GET links.

Several action endpoints (approve/confirm/delete/toggle) are linked from
templates as plain GET anchors, which makes them triggerable by CSRF
(``<img src>``, prefetch, link-unfurl). Wrapping the view with
``confirm_post`` turns the GET into a harmless confirmation page whose only
action is a same-origin, CSRF-token-protected POST back to the same URL; the
wrapped view body only runs on that POST.
"""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING

from django.shortcuts import render

from larpmanager.utils.core.base import get_context

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse


def confirm_post(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Require a confirming POST before running a state-changing view.

    On GET, render a confirmation page that POSTs back to the same URL with a
    CSRF token. On POST, run the wrapped view. This closes CSRF for endpoints
    that would otherwise mutate on a bare GET.
    """

    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if request.method == "POST":
            return view_func(request, *args, **kwargs)
        return render(request, "elements/confirm_action.html", get_context(request))

    return _wrapped
