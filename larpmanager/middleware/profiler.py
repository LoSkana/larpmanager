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

from datetime import datetime
from typing import Callable

from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.http import HttpRequest

from larpmanager.models.larpmanager import LarpManagerProfiler


class ProfilerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def process_request(request: HttpRequest):
        """Extract values from HttpRequest"""
        return request.get_host(), request.get_full_path(), request.method

    def process_view(self, request, view_func, view_args, view_kwargs):
        self.func_name = self._extract_view_func_name(view_func)
        request.func_name = self.func_name

    @staticmethod
    def _extract_view_func_name(view_func: Callable) -> str:
        # the View.as_view() method sets this
        if hasattr(view_func, "view_class"):
            return view_func.view_class.__name__
        return view_func.__name__ if hasattr(view_func, "__name__") else view_func.__class__.__name__

    def __call__(self, request):
        start_ts = None
        if not self.is_ignorable_profiler(request):
            # Start counting
            start_ts = datetime.now()

        # Get response
        response = self.get_response(request)

        if not start_ts or not hasattr(self, "func_name"):
            return response

        # end counting
        duration = (datetime.now() - start_ts).total_seconds()
        if duration < 1:
            return response

        (domain, path, http_method) = self.process_request(request)

        # put lock to avoid race condition
        with transaction.atomic():
            kwargs = {
                "date": datetime.today(),
                "domain": domain,
                "view_func_name": self.func_name,
            }
            try:
                # Tries to recover the application with a lock
                profiler = LarpManagerProfiler.objects.select_for_update().get(**kwargs)
            except ObjectDoesNotExist:
                try:
                    # If it does not exist, it creates a new application
                    profiler = LarpManagerProfiler.objects.create(**kwargs)
                except IntegrityError:
                    # If there is a Race Condition, recover the application again with the Lock
                    profiler = LarpManagerProfiler.objects.select_for_update().get(**kwargs)

            # compute new values
            new_num_calls = profiler.num_calls + 1
            new_mean_duration = ((profiler.mean_duration * profiler.num_calls) + duration) / new_num_calls

            # save only updated fields
            profiler.num_calls = new_num_calls
            profiler.mean_duration = new_mean_duration
            profiler.save(update_fields=["mean_duration", "num_calls"])

        return response

    @staticmethod
    def is_ignorable_profiler(request):
        if conf_settings.SKIP_PROFILER:
            return True
        return any(pattern.search(request.get_full_path()) for pattern in conf_settings.IGNORABLE_PROFILER_URLS)
