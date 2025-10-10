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


def clear_registration_counts_cache(r):
    cache.delete(cache_reg_counts_key(r))


def cache_reg_counts_key(r):
    return f"reg_counts{r.id}"


def get_reg_counts(r, reset=False):
    key = cache_reg_counts_key(r)
    if reset:
        res = None
    else:
        res = cache.get(key)
    if not res:
        res = update_reg_counts(r)
        cache.set(key, res, timeout=60 * 5)
    return res


def add_count(s, param, v=1):
    if param not in s:
        s[param] = v
        return

    s[param] += v


def update_reg_counts(r):
    """Update registration counts cache for the given run.

    Args:
        r: Run instance to update registration counts for

    Returns:
        dict: Updated registration counts data by ticket tier
    """
    s = {"count_reg": 0, "count_wait": 0, "count_staff": 0, "count_fill": 0}
    que = Registration.objects.filter(run=r, cancellation_date__isnull=True)
    for reg in que.select_related("ticket"):
        num_tickets = 1 + reg.additionals
        if not reg.ticket:
            add_count(s, "count_unknown", num_tickets)
        else:
            tier_map = {
                TicketTier.STAFF: "staff",
                TicketTier.WAITING: "wait",
                TicketTier.FILLER: "fill",
                TicketTier.SELLER: "seller",
                TicketTier.LOTTERY: "lottery",
                TicketTier.NPC: "npc",
                TicketTier.COLLABORATOR: "collaborator",
            }
            key = tier_map.get(reg.ticket.tier)
            if key:
                add_count(s, f"count_{key}", num_tickets)
            else:
                add_count(s, "count_player", num_tickets)

            if is_reg_provisional(reg):
                add_count(s, "count_provisional", num_tickets)

        add_count(s, "count_reg", num_tickets)

        add_count(s, f"tk_{reg.ticket_id}", num_tickets)

    que = RegistrationChoice.objects.filter(reg__run=r, reg__cancellation_date__isnull=True)
    for el in que.values("option_id").annotate(total=Count("option_id")):
        s[f"option_{el['option_id']}"] = el["total"]

    character_ids = Character.objects.filter(event=r.event).values_list("id", flat=True)

    que = WritingChoice.objects.filter(element_id__in=character_ids)
    for el in que.values("option_id").annotate(total=Count("option_id")):
        s[f"option_char_{el['option_id']}"] = el["total"]

    return s


def on_character_update_registration_cache(instance):
    for run in instance.event.runs.all():
        clear_registration_counts_cache(run)
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
