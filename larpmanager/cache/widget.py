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

from typing import Any

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.http import Http404

from larpmanager.accounting.balance import (
    association_accounting_summary,
    get_run_accounting,
)
from larpmanager.models.casting import Casting
from larpmanager.models.event import Event, Run
from larpmanager.models.member import LogOperationType
from larpmanager.models.miscellanea import Log
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.utils.core.common import get_coming_runs
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


def _init_user_character_widget_cache(run: Run) -> dict:
    """Compute character counts by status for widget cache."""
    # Count characters for each status
    counts = {}

    # Get all characters for this run
    characters = run.event.get_elements(Character)

    # Count by status
    counts["creation"] = characters.filter(status=CharacterStatus.CREATION).count()
    counts["proposed"] = characters.filter(status=CharacterStatus.PROPOSED).count()
    counts["review"] = characters.filter(status=CharacterStatus.REVIEW).count()
    counts["approved"] = characters.filter(status=CharacterStatus.APPROVED).count()

    return counts


def _init_casting_widget_cache(run: Run) -> dict:
    """Compute casting statistics for widget cache."""
    counts = {}

    # Get all characters for this run
    characters = run.event.get_elements(Character)
    all_character_ids = set(characters.values_list("id", flat=True))

    # Precompute list of assigned character IDs via RegistrationCharacterRel
    assigned_character_ids = set(
        RegistrationCharacterRel.objects.filter(registration__run=run).values_list("character_id", flat=True)
    )

    # Count assigned and unassigned characters
    counts["assigned"] = len(assigned_character_ids)
    counts["unassigned"] = len(all_character_ids - assigned_character_ids)

    # Get members with active casting preferences but no assigned character
    members_with_casting = set(
        Casting.objects.filter(run=run, active=True).values_list("member_id", flat=True).distinct()
    )

    # Get members who already have a character assigned in this run
    members_with_character = set(
        RegistrationCharacterRel.objects.filter(registration__run=run)
        .values_list("registration__member_id", flat=True)
        .distinct()
    )

    # Players waiting = those with preferences but no assigned character
    waiting_members = members_with_casting - members_with_character
    counts["waiting"] = len(waiting_members)

    return counts


def _init_orga_accounting_widget_cache(run: Run) -> dict:
    """Compute accounting statistics for widget cache."""
    summary, _accounting_data = get_run_accounting(run, {})
    return summary


def _init_exe_accounting_widget_cache(association_id: int) -> dict:
    """Compute association accounting statistics for widget cache (current year)."""
    context = {"association_id": association_id}

    # Get accounting data summary
    association_accounting_summary(context)
    data = {}
    for key in ["global_sum", "bank_sum"]:
        data[key] = context.get(key, 0)
    return data


def _init_exe_deadline_widget_cache(association_id: int) -> dict:
    """Compute association deadline statistics for widget cache (aggregates all upcoming runs)."""
    # Get all upcoming runs for the association
    runs = get_coming_runs(association_id, future=True)

    # Initialize aggregated counts
    total_counts = {}

    # Iterate through all runs and aggregate deadline counts
    for run in runs:
        run_counts = _init_deadline_widget_cache(run)
        for category, count in run_counts.items():
            total_counts[category] = total_counts.get(category, 0) + count

    return total_counts


def _init_orga_log_widget_cache(run: Run) -> dict:
    """Compute log statistics and recent logs for event dashboard."""
    base_query = Log.objects.filter(run_id=run.id)

    # Count logs by operation type
    operation_counts = {}
    for op_type, op_label in LogOperationType.choices:
        count = base_query.filter(operation_type=op_type).count()
        if count > 0:
            operation_counts[op_type] = {"label": op_label, "count": count}

    # Get recent logs (last 5)
    recent_logs = base_query.select_related("member").order_by("-created")[:5]

    return {"operation_counts": operation_counts, "recent_logs": list(recent_logs), "total_count": base_query.count()}


def _init_exe_log_widget_cache(association_id: int) -> dict:
    """Compute log statistics and recent logs for organization dashboard."""
    base_query = Log.objects.filter(association_id=association_id)

    # Count logs by operation type
    operation_counts = {}
    for op_type, op_label in LogOperationType.choices:
        count = base_query.filter(operation_type=op_type).count()
        if count > 0:
            operation_counts[op_type] = {"label": op_label, "count": count}

    # Get recent logs (last 5)
    recent_logs = base_query.select_related("member", "run__event").order_by("-created")[:5]

    return {"operation_counts": operation_counts, "recent_logs": list(recent_logs), "total_count": base_query.count()}


# Widget list for run-level widgets
orga_widget_list = {
    "deadlines": _init_deadline_widget_cache,
    "user_character": _init_user_character_widget_cache,
    "casting": _init_casting_widget_cache,
    "accounting": _init_orga_accounting_widget_cache,
    "logs": _init_orga_log_widget_cache,
}

# Widget list for association-level widgets
exe_widget_list = {
    "accounting": _init_exe_accounting_widget_cache,
    "deadlines": _init_exe_deadline_widget_cache,
    "logs": _init_exe_log_widget_cache,
}


def get_widget_cache_key(entity_type: str, entity_id: int, widget_name: str) -> str:
    """Generate cache key for widget data."""
    return f"widget_cache_{entity_type}_{entity_id}_{widget_name}"


def get_widget_cache(
    entity: Run | int, entity_type: str, entity_id: int, widget_list: dict, widget_name: str = ""
) -> dict:
    """Get widget data from cache or compute if not cached.

    Args:
        entity: Object on which to recover widget (either Run, or
        entity_type: Type of entity ('run' or 'association')
        entity_id: ID of the entity
        widget_list: List of available widgets
        widget_name: Name of the widget to retrieve

    Returns:
        dict: Widget data

    Raises:
        Http404: If widget is not found
    """
    cached_data_function = widget_list.get(widget_name)
    if not cached_data_function:
        msg = f"widget {widget_name} not found in widget list"
        raise Http404(msg)

    cache_key = get_widget_cache_key(entity_type, entity_id, widget_name)
    cached_data = cache.get(cache_key)

    # If not in cache, update and get fresh data
    if cached_data is None:
        cached_data = cached_data_function(entity)
        # Cache the result with 1-day timeout
        cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_data


def get_orga_widget_cache(run: Run, widget_name: str) -> dict:
    """Get deadline widget data from cache or compute if not cached."""
    return get_widget_cache(run, "run", run.id, orga_widget_list, widget_name)


def get_exe_widget_cache(association_id: int, widget_name: str) -> dict:
    """Get deadline widget data from cache or compute if not cached."""
    return get_widget_cache(association_id, "association", association_id, exe_widget_list, widget_name)


def clear_widget_cache(run_id: int) -> None:
    """Clear cached widget data for a run."""
    for widget_name in orga_widget_list:
        cache_key = get_widget_cache_key("run", run_id, widget_name)
        cache.delete(cache_key)


def clear_widget_cache_association(association_id: int) -> None:
    """Clear cached widget data for an association."""
    for widget_name in exe_widget_list:
        cache_key = get_widget_cache_key("association", association_id, widget_name)
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
    """Clear widget cache for all runs in an association and association-level widgets."""
    # Clear run-level widgets
    event_ids = Event.objects.filter(association_id=association_id).values_list("id", flat=True)
    run_ids = Run.objects.filter(event_id__in=event_ids).values_list("id", flat=True)
    clear_widget_cache_for_runs(list(run_ids))

    # Clear association-level widgets
    clear_widget_cache_association(association_id)


def reset_widgets(instance: Any) -> None:
    """Reset widget cache data for related elements."""
    if hasattr(instance, "run") and instance.run:
        clear_widget_cache(instance.run.id)
        clear_widget_cache_association(instance.run.event.association_id)
    elif hasattr(instance, "event") and instance.event:
        clear_widget_cache_for_event(instance.event.id)
        clear_widget_cache_association(instance.event.association_id)
    elif hasattr(instance, "association_id") and instance.association_id:
        clear_widget_cache_association(instance.association_id)
