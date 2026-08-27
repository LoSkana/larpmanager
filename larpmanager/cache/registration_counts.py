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
"""Registration counts cache key/invalidation.

Split out of larpmanager.cache.registration: larpmanager.utils.registrations.signals
needs to invalidate this cache, while larpmanager.cache.registration itself needs a
function from signals.py, so keeping both in one module would create an import cycle.
"""

from __future__ import annotations

from django.core.cache import cache
from django.db.models import Count

from larpmanager.accounting.base import is_registration_provisional
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.registration_lookup import get_active_registrations
from larpmanager.models.form import BaseQuestionType, RegistrationChoice, WritingChoice
from larpmanager.models.registration import TicketTier
from larpmanager.models.writing import Character


def cache_registration_counts_key(run_id: int) -> str:
    """Generate cache key for registration counts."""
    return f"registration_counts_{run_id}"


def clear_registration_counts_cache(run_id: int) -> None:
    """Clear cached registration counts for a run."""
    cache.delete(cache_registration_counts_key(run_id))


def get_registration_counts(run_id: int, event_id: int, *, reset_cache: bool = False) -> dict:
    """Get registration counts for a run, with caching support.

    Args:
        run_id: The run id to get counts for
        event_id: The event id the run belongs to
        reset_cache: If True, force cache refresh

    Returns:
        Dictionary containing registration count data

    """
    # Generate cache key for this run
    cache_key = cache_registration_counts_key(run_id)

    # Check if we should bypass cache
    cached_counts = None if reset_cache else cache.get(cache_key)

    # Update and cache if not found
    if cached_counts is None:
        cached_counts = update_registration_counts(run_id, event_id)
        cache.set(cache_key, cached_counts, timeout=60 * 5)

    return cached_counts


def add_count(counter_dict: dict, parameter_name: str, increment_value: int = 1) -> None:
    """Add or increment a counter value in a dictionary."""
    # Initialize parameter if not present
    if parameter_name not in counter_dict:
        counter_dict[parameter_name] = increment_value
        return

    # Increment existing value
    counter_dict[parameter_name] += increment_value


def update_registration_counts(run_id: int, event_id: int) -> dict[str, int]:
    """Update registration counts cache for the given run.

    Calculates and returns registration statistics including counts by ticket tier,
    provisional registrations, registration choices, and character writing choices.

    Args:
        run_id: Run id to update registration counts for
        event_id: Event id the run belongs to

    Returns:
        Dictionary containing registration counts data by ticket tier and choices.
        Keys include count_reg, count_wait, count_staff, count_fill, tk_{ticket_id},
        option_{option_id}, option_char_{option_id}, tickets_map, and tickets_order.

    """
    # Initialize base counters
    counts = {
        "count_reg": 0,
        "count_wait": 0,
        "count_staff": 0,
        "count_fill": 0,
        "tickets_map": {},
        "tickets_order": {},
    }

    # Get all non-cancelled registrations for this run
    registrations = get_active_registrations(run_id)

    # Get event features
    features = get_event_features(event_id)

    context = {}

    # Process each registration to count by ticket tier
    for registration in registrations.select_related("ticket"):
        num_tickets = 1 + registration.additionals

        # Handle registrations without ticket assignment
        if not registration.ticket:
            add_count(counts, "count_unknown", num_tickets)
        else:
            # Count by ticket name
            add_count(counts, f"count_ticket_{registration.ticket_id}", num_tickets)
            if registration.ticket_id not in counts["tickets_map"]:
                counts["tickets_map"][registration.ticket_id] = registration.ticket.name
            if registration.ticket_id not in counts["tickets_order"]:
                counts["tickets_order"][registration.ticket_id] = registration.ticket.order

            # Map ticket tiers to counter keys
            tier_map = {
                TicketTier.STAFF: "staff",
                TicketTier.WAITING: "wait",
                TicketTier.FILLER: "fill",
                TicketTier.SELLER: "seller",
                TicketTier.LOTTERY: "lottery",
                TicketTier.NPC: "npc",
                TicketTier.COLLABORATOR: "collaborator",
            }

            # Count by specific tier or default to player
            tier_key = tier_map.get(registration.ticket.tier)
            if tier_key:
                add_count(counts, f"count_{tier_key}", num_tickets)
            else:
                add_count(counts, "count_player", num_tickets)

            # Track provisional registrations separately
            if is_registration_provisional(registration, event_id=event_id, features=features, context=context):
                add_count(counts, "count_provisional", num_tickets)

        # Add to total registration count
        add_count(counts, "count_reg", num_tickets)

        # Track count by specific ticket ID
        add_count(counts, f"tk_{registration.ticket_id}", num_tickets)

    # Count registration choices (form options selected)
    registration_choices = RegistrationChoice.objects.filter(
        registration__run_id=run_id,
        registration__cancellation_date__isnull=True,
        registration__pending=False,
        question__typ__in=[BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE],
    )
    for choice_data in registration_choices.values("option_id").annotate(total=Count("option_id")):
        counts[f"option_{choice_data['option_id']}"] = choice_data["total"]

    # Count character writing choices for this event
    character_ids = Character.objects.filter(event_id=event_id).values_list("id", flat=True)

    writing_choices = WritingChoice.objects.filter(element_id__in=character_ids)
    for choice_data in writing_choices.values("option_id").annotate(total=Count("option_id")):
        counts[f"option_char_{choice_data['option_id']}"] = choice_data["total"]

    return counts
