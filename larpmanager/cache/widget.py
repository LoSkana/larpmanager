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

from __future__ import annotations

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.http import Http404

from larpmanager.models.event import Event, Run
from larpmanager.utils.users.deadlines import check_run_deadlines


def _init_deadline_widget_cache(run: Run) -> dict:
    """Compute deadline data for widget cache."""
    deadline_results = check_run_deadlines([run])
    if not deadline_results:
        return {}

    deadline_data = deadline_results[0]

    # Extract the counts
    counts = {}
    for category in ["pay", "pay_del", "casting", "memb", "memb_del", "fee", "fee_del", "profile", "profile_del"]:
        if category in deadline_data:
            counts[category] = len(deadline_data[category])

    return counts


widget_list = {"deadline": _init_deadline_widget_cache}


def get_widget_cache_key(run_id: int, widget_name: str) -> str:
    """Generate cache key for deadline widget data."""
    return f"deadline_widget_{run_id}_{widget_name}"


def get_widget_cache(run: Run, widget_name: str) -> dict:
    """Get deadline widget data from cache or compute if not cached."""
    cached_data_function = widget_list.get(widget_name)
    if not cached_data_function:
        msg = f"widget {widget_name} not found"
        raise Http404(msg)

    cache_key = get_widget_cache_key(run.id, widget_name)
    cached_data = cache.get(cache_key)

    # If not in cache, update and get fresh data
    if cached_data is None:
        cached_data = cached_data_function(run)
        # Cache the result with 1-day timeout
        cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_data


def clear_widget_cache(run_id: int) -> None:
    """Clear cached deadline widget data for a run."""
    for widget_name in widget_list:
        cache_key = get_widget_cache_key(run_id, widget_name)
        cache.delete(cache_key)


def clear_widget_cache_for_runs(run_ids: list[int]) -> None:
    """Clear widget cache for multiple runs."""
    for run_id in run_ids:
        clear_widget_cache(run_id)


def clear_widget_cache_for_event(event_id: int) -> None:
    """Clear widget cache for all runs in an event."""
    run_ids = Run.objects.filter(event_id=event_id).values_list("id", flat=True)
    clear_widget_cache_for_runs(list(run_ids))


def clear_widget_cache_for_association(association_id: int) -> None:
    """Clear widget cache for all runs in an association."""
    event_ids = Event.objects.filter(association_id=association_id).values_list("id", flat=True)
    run_ids = Run.objects.filter(event_id__in=event_ids).values_list("id", flat=True)
    clear_widget_cache_for_runs(list(run_ids))
