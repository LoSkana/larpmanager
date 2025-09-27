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

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.dispatch import receiver

from larpmanager.models.larpmanager import LarpManagerProfiler
from larpmanager.utils.profiler.signals import profiler_response_signal


@receiver(profiler_response_signal)
def handle_profiler_response(sender, domain, path, method, view_func_name, duration, **kwargs):
    """Handle profiler signal to record view function performance metrics.

    Args:
        sender: Signal sender
        domain: Request domain
        path: Request path
        method: HTTP method
        view_func_name: Name of the view function
        duration: Response duration in seconds
        **kwargs: Additional keyword arguments
    """
    if duration < 1:
        return

    with transaction.atomic():
        key = {
            "date": datetime.today().date(),
            "domain": domain,
            "view_func_name": view_func_name,
        }

        try:
            profiler = LarpManagerProfiler.objects.select_for_update().get(**key)
        except ObjectDoesNotExist:
            try:
                profiler = LarpManagerProfiler.objects.create(**key)
            except IntegrityError:
                profiler = LarpManagerProfiler.objects.select_for_update().get(**key)

        profiler.num_calls += 1
        profiler.mean_duration = ((profiler.mean_duration * (profiler.num_calls - 1)) + duration) / profiler.num_calls
        profiler.save(update_fields=["mean_duration", "num_calls"])
