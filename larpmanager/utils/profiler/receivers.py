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
def handle_profiler_response(sender, domain, path, method, view_func_name, duration, **kwargs):
    """Handle profiler signal to record individual execution data.

    Saves individual execution data with path and query parameters.

    Args:
        sender: Signal sender
        domain: Request domain
        path: Request path
        method: HTTP method
        view_func_name: Name of the view function
        duration: Response duration in seconds
        **kwargs: Additional keyword arguments
    """
    parsed_url = urlparse(path)
    clean_path = parsed_url.path
    query_string = parsed_url.query

    # Save individual execution data
    LarpManagerProfiler.objects.create(
        domain=domain,
        path=clean_path,
        query=query_string,
        method=method,
        view_func_name=view_func_name,
        duration=duration,
    )
