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
from django.db.models.signals import post_save
from django.dispatch import receiver

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.models.event import Event, Run
from larpmanager.models.form import RegistrationChoice, WritingChoice
from larpmanager.models.registration import Registration, RegistrationCharacterRel, TicketTier
from larpmanager.models.writing import Character
from larpmanager.utils.common import _search_char_reg


def reset_cache_reg_counts(r):
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
        cache.set(key, res)
    return res


def add_count(s, param, v=1):
    if param not in s:
        s[param] = v
        return

    s[param] += v


def update_reg_counts(r):
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


@receiver(post_save, sender=Registration)
def post_save_registration_cache(sender, instance, created, **kwargs):
    reset_cache_reg_counts(instance.run)


@receiver(post_save, sender=Character)
def post_save_registration_character_rel_cache(sender, instance, created, **kwargs):
    for run in instance.event.runs.all():
        reset_cache_reg_counts(run)

    if instance.event.get_config("user_character_approval", False):
        for rcr in RegistrationCharacterRel.objects.filter(character=instance):
            rcr.reg.save()


@receiver(post_save, sender=Run)
def post_save_run_cache(sender, instance, created, **kwargs):
    reset_cache_reg_counts(instance)


@receiver(post_save, sender=Event)
def post_save_event_cache(sender, instance, created, **kwargs):
    for r in instance.runs.all():
        reset_cache_reg_counts(r)


def search_player(char, js, ctx):
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
