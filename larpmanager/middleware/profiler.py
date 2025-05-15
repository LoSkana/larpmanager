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

from django.utils.timezone import now

from larpmanager.utils.profiler.signals import profiler_response_signal


class ProfilerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request._profiler_start_ts = now()
        response = self.get_response(request)

        if hasattr(request, "_profiler_func_name"):
            duration = (now() - request._profiler_start_ts).total_seconds()
            if duration >= 1:
                try:
                    profiler_response_signal.send(
                        sender=None,
                        domain=request.get_host(),
                        path=request.get_full_path(),
                        method=request.method,
                        view_func_name=request._profiler_func_name,
                        duration=duration,
                    )
                except Exception:
                    pass  # fail silently
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        request._profiler_func_name = self._extract_view_func_name(view_func)

    @staticmethod
    def _extract_view_func_name(view_func):
        if hasattr(view_func, "view_class"):
            return view_func.view_class.__name__
        return getattr(view_func, "__name__", view_func.__class__.__name__)
