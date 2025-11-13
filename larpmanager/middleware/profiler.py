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

import logging
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.utils.timezone import now

from larpmanager.utils.profiler.signals import profiler_response_signal

logger = logging.getLogger(__name__)


class ProfilerMiddleware:
    threshold = 0.5

    def __init__(self, get_response: Callable) -> None:
        """Initialize middleware with Django response handler."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process request and measure view function execution time.

        This middleware measures the execution time of Django view functions
        and sends a signal when the duration exceeds the configured threshold.
        It silently handles any errors to avoid disrupting the request flow.

        Args:
            request: The incoming HTTP request object containing request data
                    and metadata.

        Returns:
            The HTTP response object returned by the view function.

        Note:
            The profiling data is only collected if the request has a
            _profiler_func_name attribute set by the view decorator.

        """
        # Record the start timestamp for duration calculation
        request._profiler_start_ts = now()

        # Process the request through the view function
        response = self.get_response(request)

        # Check if profiling is enabled for this request
        if hasattr(request, "_profiler_func_name"):
            # Calculate the total execution duration
            duration = (now() - request._profiler_start_ts).total_seconds()

            # Only emit signal if duration exceeds the threshold
            if duration >= self.threshold:
                try:
                    # Send profiling data via Django signal
                    # noinspection PyProtectedMember
                    profiler_response_signal.send(
                        sender=None,
                        domain=request.get_host(),
                        path=request.get_full_path(),
                        method=request.method,
                        view_func_name=request._profiler_func_name,
                        duration=duration,
                    )
                except Exception as err:
                    # Fail silently in production, but log for debugging
                    logger.warning("ProfilerMiddleware fail: %s", err)

        return response

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable,
        view_args: tuple,  # noqa: ARG002
        view_kwargs: dict,  # noqa: ARG002
    ) -> None:
        """Store the view function name in the request for profiling."""
        request._profiler_func_name = self._extract_view_func_name(view_func)

    @staticmethod
    def _extract_view_func_name(view_function: Callable[..., HttpResponse]) -> str:
        """Extract the name from a Django view function or class-based view.

        Args:
            view_function: Django view function or class-based view

        Returns:
            Name of the view class or function

        """
        # Check if it's a class-based view with view_class attribute
        if hasattr(view_function, "view_class"):
            return view_function.view_class.__name__

        # Fallback to __name__ attribute or class name
        return getattr(view_function, "__name__", view_function.__class__.__name__)
