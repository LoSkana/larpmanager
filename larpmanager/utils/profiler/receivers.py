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

from urllib.parse import urlparse

from django.dispatch import receiver

from larpmanager.models.larpmanager import LarpManagerProfiler
from larpmanager.utils.profiler.signals import profiler_response_signal


@receiver(profiler_response_signal)
def handle_profiler_response(
    sender: object, domain: str, path: str, method: str, view_func_name: str, duration: float, **kwargs: object
) -> None:
    """Handle profiler signal to record individual execution data.

    This function processes profiler signals and saves execution metrics
    to the database for performance monitoring and analysis.

    Args:
        sender: The signal sender object that triggered this handler
        domain: The domain name of the request being profiled
        path: The full request path including query parameters
        method: The HTTP method used for the request (GET, POST, etc.)
        view_func_name: The name of the Django view function that handled the request
        duration: The total response time in seconds as a float
        **kwargs: Additional keyword arguments passed by the signal

    Returns:
        None: This function doesn't return any value
    """
    # Parse the URL to separate path from query parameters
    parsed_url = urlparse(path)

    # Extract clean path without query string
    clean_path = parsed_url.path

    # Extract query parameters for separate storage
    query_string = parsed_url.query

    # Save individual execution data to the profiler model
    LarpManagerProfiler.objects.create(
        domain=domain,
        path=clean_path,
        query=query_string,
        method=method,
        view_func_name=view_func_name,
        duration=duration,
    )
