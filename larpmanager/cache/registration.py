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

from django.core.cache import cache
from django.db.models import Count

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.cache.config import get_event_config
from larpmanager.cache.feature import get_event_features
from larpmanager.models.event import Run
from larpmanager.models.form import RegistrationChoice, WritingChoice
from larpmanager.models.registration import Registration, RegistrationCharacterRel, TicketTier
from larpmanager.models.writing import Character
from larpmanager.utils.common import _search_char_reg


def clear_registration_counts_cache(run_id):
    cache.delete(cache_registration_counts_key(run_id))


def cache_registration_counts_key(run_id):
    return f"registration_counts_{run_id}"


def get_reg_counts(run: Run, reset_cache: bool = False) -> dict:
    """Get registration counts for a run, with caching support.

    Args:
        run: The run instance to get counts for
        reset_cache: If True, force cache refresh

    Returns:
        Dictionary containing registration count data
    """
    # Generate cache key for this run
    cache_key = cache_registration_counts_key(run.id)

    # Check if we should bypass cache
    if reset_cache:
        cached_counts = None
    else:
        cached_counts = cache.get(cache_key)

    # Update and cache if not found
    if cached_counts is None:
        cached_counts = update_reg_counts(run)
        cache.set(cache_key, cached_counts, timeout=60 * 5)

    return cached_counts


def add_count(counter_dict: dict, parameter_name: str, increment_value: int = 1) -> None:
    """Add or increment a counter value in a dictionary.

    Args:
        counter_dict: Dictionary to modify
        parameter_name: Key to add or increment
        increment_value: Value to add (default: 1)
    """
    # Initialize parameter if not present
    if parameter_name not in counter_dict:
        counter_dict[parameter_name] = increment_value
        return

    # Increment existing value
    counter_dict[parameter_name] += increment_value


def update_reg_counts(run) -> dict[str, int]:
    """Update registration counts cache for the given run.

    Calculates and returns registration statistics including counts by ticket tier,
    provisional registrations, registration choices, and character writing choices.

    Args:
        run: Run instance to update registration counts for

    Returns:
        Dictionary containing registration counts data by ticket tier and choices.
        Keys include count_reg, count_wait, count_staff, count_fill, tk_{ticket_id},
        option_{option_id}, and option_char_{option_id}.
    """
    # Initialize base counters
    s = {"count_reg": 0, "count_wait": 0, "count_staff": 0, "count_fill": 0}

    # Get all non-cancelled registrations for this run
    que = Registration.objects.filter(run=run, cancellation_date__isnull=True)

    # Get event features
    features = get_event_features(run.event_id)

    # Process each registration to count by ticket tier
    for reg in que.select_related("ticket"):
        num_tickets = 1 + reg.additionals

        # Handle registrations without ticket assignment
        if not reg.ticket:
            add_count(s, "count_unknown", num_tickets)
        else:
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
            key = tier_map.get(reg.ticket.tier)
            if key:
                add_count(s, f"count_{key}", num_tickets)
            else:
                add_count(s, "count_player", num_tickets)

            # Track provisional registrations separately
            if is_reg_provisional(reg, event=run.event, features=features):
                add_count(s, "count_provisional", num_tickets)

        # Add to total registration count
        add_count(s, "count_reg", num_tickets)

        # Track count by specific ticket ID
        add_count(s, f"tk_{reg.ticket_id}", num_tickets)

    # Count registration choices (form options selected)
    que = RegistrationChoice.objects.filter(reg__run=run, reg__cancellation_date__isnull=True)
    for el in que.values("option_id").annotate(total=Count("option_id")):
        s[f"option_{el['option_id']}"] = el["total"]

    # Count character writing choices for this event
    character_ids = Character.objects.filter(event_id=run.event_id).values_list("id", flat=True)

    que = WritingChoice.objects.filter(element_id__in=character_ids)
    for el in que.values("option_id").annotate(total=Count("option_id")):
        s[f"option_char_{el['option_id']}"] = el["total"]

    return s


def on_character_update_registration_cache(instance: Character) -> None:
    """Clear registration caches and update related registrations when character changes."""
    # Clear registration count caches for all event runs
    for run_id in instance.event.runs.values_list("id", flat=True):
        clear_registration_counts_cache(run_id)

    # Trigger registration updates if character approval is enabled
    if get_event_config(instance.event_id, "user_character_approval", False):
        for rcr in RegistrationCharacterRel.objects.filter(character=instance):
            rcr.reg.save()


def search_player(character, json_output: dict, context: dict) -> None:
    """
    Search for players in registration cache and populate results.

    This function attempts to find player registration data for a given character,
    either from a pre-loaded assignments cache or by querying the database directly.
    It populates the character object with registration and member information.

    Args:
        character: Character instance with player data to be populated
        json_output (dict): JSON object to populate with search results
        context (dict): Context dictionary containing search parameters, assignments cache,
                   and run information

    Returns:
        None: Function modifies character and json_output objects in place
    """
    # Check if assignments are pre-loaded in context (cache hit)
    if "assignments" in context:
        if character.number in context["assignments"]:
            # Populate character with cached registration data
            character.rcr = context["assignments"][character.number]
            character.reg = character.rcr.reg
            character.member = character.reg.member
        else:
            # Character not found in assignments cache
            character.rcr = None
            character.reg = None
            character.member = None
    else:
        # No cache available, query database directly
        try:
            # Fetch registration character relationship with related objects
            character.rcr = RegistrationCharacterRel.objects.select_related("reg", "reg__member").get(
                reg__run_id=context["run"].id, character=character
            )
            character.reg = character.rcr.reg
            character.member = character.reg.member
        except Exception:
            # Registration not found or database error
            character.rcr = None
            character.reg = None
            character.member = None

    # Process character registration data if available
    if character.reg:
        _search_char_reg(context, character, json_output)
    else:
        # No registration found, set default player ID
        json_output["player_id"] = 0
