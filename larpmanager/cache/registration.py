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
from larpmanager.models.form import RegistrationChoice, WritingChoice
from larpmanager.models.registration import Registration, RegistrationCharacterRel, TicketTier
from larpmanager.models.writing import Character
from larpmanager.utils.common import _search_char_reg
from larpmanager.cache.feature import get_event_features


def clear_registration_counts_cache(run_id):
    cache.delete(cache_reg_counts_key(run_id))


def cache_reg_counts_key(run_id):
    return f"reg_counts{run_id}"


def get_reg_counts(run, reset=False):
    key = cache_reg_counts_key(run.id)
    if reset:
        res = None
    else:
        res = cache.get(key)
    if not res:
        res = update_reg_counts(run)
        cache.set(key, res, timeout=60 * 5)
    return res


def add_count(s, param, v=1):
    if param not in s:
        s[param] = v
        return

    s[param] += v


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


def on_character_update_registration_cache(instance):
    for run_id in instance.event.runs.values_list("id", flat=True):
        clear_registration_counts_cache(run_id)
    if instance.event.get_config("user_character_approval", False):
        for rcr in RegistrationCharacterRel.objects.filter(character=instance):
            rcr.reg.save()


def search_player(char, js, ctx):
    """
    Search for players in registration cache and populate results.

    Args:
        char: Character instance with player data
        js: JSON object to populate with search results
        ctx: Context dictionary with search parameters and assignments
    """
    if "assignments" in ctx:
        if char.number in ctx["assignments"]:
            char.rcr = ctx["assignments"][char.number]
            char.reg = char.rcr.reg
            char.member = char.reg.member
        else:
            char.rcr = None
            char.reg = None
            char.member = None
    else:
        try:
            char.rcr = RegistrationCharacterRel.objects.select_related("reg", "reg__member").get(
                reg__run_id=ctx["run"].id, character=char
            )
            char.reg = char.rcr.reg
            char.member = char.reg.member
        except Exception:
            char.rcr = None
            char.reg = None
            char.member = None

    if char.reg:
        _search_char_reg(ctx, char, js)
    else:
        js["player_id"] = 0
