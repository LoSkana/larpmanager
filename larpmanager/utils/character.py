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

from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404

from larpmanager.cache.character import get_character_element_fields, get_event_cache_all, get_writing_element_fields
from larpmanager.models.casting import Trait
from larpmanager.models.form import QuestionApplicable
from larpmanager.models.miscellanea import PlayerRelationship
from larpmanager.models.utils import strip_tags
from larpmanager.models.writing import Character, FactionType, PlotCharacterRel, Relationship
from larpmanager.utils.common import add_char_addit, get_char
from larpmanager.utils.event import has_access_character
from larpmanager.utils.exceptions import NotFoundError


def get_character_relationships(ctx, restrict=True):
    cache = {}
    data = {}
    for tg_num, text in Relationship.objects.values_list("target__number", "text").filter(source=ctx["character"]):
        if "chars" in ctx and tg_num in ctx["chars"]:
            show = ctx["chars"][tg_num]
        else:
            try:
                ch = Character.objects.get(event=ctx["event"], number=tg_num)
                show = ch.show(ctx["run"])
            except ObjectDoesNotExist:
                continue

        show["factions_list"] = []
        for fac_num in show["factions"]:
            if not fac_num or fac_num not in ctx["factions"]:
                continue
            fac = ctx["factions"][fac_num]
            if not fac["name"] or fac["typ"] == FactionType.SECRET:
                continue
            show["factions_list"].append(fac["name"])
        show["factions_list"] = ", ".join(show["factions_list"])
        data[show["id"]] = show
        cache[show["id"]] = text

    pr = {}
    # update with data inputted by players
    if "player_id" in ctx["char"]:
        for el in PlayerRelationship.objects.filter(reg__member_id=ctx["char"]["player_id"], reg__run=ctx["run"]):
            pr[el.target_id] = el
            cache[el.target_id] = el.text

    ctx["rel"] = []
    for idx in sorted(cache, key=lambda k: len(cache[k]), reverse=True):
        if idx not in data:
            # print(idx)
            # print(data)
            # print(cache)
            continue
        el = data[idx]
        if restrict and len(cache[idx]) == 0:
            continue
        el["text"] = cache[idx]
        el["font_size"] = int(100 - ((len(el["text"]) / 50) * 4))
        ctx["rel"].append(el)

    ctx["pr"] = pr


def get_character_sheet(ctx):
    ctx["sheet_char"] = ctx["character"].show_complete()

    get_character_sheet_fields(ctx)

    get_character_sheet_factions(ctx)

    get_character_sheet_plots(ctx)

    get_character_sheet_questbuilder(ctx)

    get_character_sheet_speedlarp(ctx)

    get_character_sheet_prologue(ctx)

    get_character_sheet_px(ctx)


def get_character_sheet_px(ctx):
    if "px" not in ctx["features"]:
        return

    ctx["sheet_abilities"] = {}
    for el in ctx["character"].px_ability_list.all():
        if el.typ.name not in ctx["sheet_abilities"]:
            ctx["sheet_abilities"][el.typ.name] = []
        ctx["sheet_abilities"][el.typ.name].append(el)

    add_char_addit(ctx["character"])


def get_character_sheet_prologue(ctx):
    if "prologue" not in ctx["features"]:
        return

    ctx["sheet_prologues"] = []
    for s in ctx["character"].prologues_list.order_by("typ__number"):
        s.data = s.show_complete()
        ctx["sheet_prologues"].append(s)


def get_character_sheet_speedlarp(ctx):
    if "speedlarp" not in ctx["features"]:
        return

    ctx["sheet_speedlarps"] = []
    for s in ctx["character"].speedlarps_list.order_by("typ"):
        s.data = s.show_complete()
        ctx["sheet_speedlarps"].append(s)


def get_character_sheet_questbuilder(ctx):
    if "questbuilder" not in ctx["features"]:
        return

    if "char" not in ctx:
        return

    if "player_id" not in ctx["char"] or "traits" not in ctx["char"]:
        return

    ctx["sheet_traits"] = []
    for tnum in ctx["char"]["traits"]:
        el = ctx["traits"][tnum]
        t = Trait.objects.get(event=ctx["event"], number=el["number"])
        data = t.show_complete()
        data["quest"] = t.quest.show_complete()

        data["rels"] = []
        for snum in el["traits"]:
            if snum not in ctx["traits"]:
                continue
            num = ctx["traits"][snum]["char"]
            data["rels"].append(ctx["chars"][num])

        ctx["sheet_traits"].append(data)


def get_character_sheet_plots(ctx):
    if "plot" not in ctx["features"]:
        return

    ctx["sheet_plots"] = []
    que = PlotCharacterRel.objects.filter(character=ctx["character"])
    for el in que.order_by("plot__number"):
        tx = el.plot.text
        if tx and el.text:
            tx += "<hr />"
        if el.text:
            tx += el.text
        ctx["sheet_plots"].append({"name": el.plot.name, "text": tx})


def get_character_sheet_factions(ctx):
    if "faction" not in ctx["features"]:
        return

    fac_event = ctx["event"].get_class_parent("faction")
    ctx["sheet_factions"] = []
    for g in ctx["character"].factions_list.filter(event=fac_event):
        data = g.show_complete()
        data.update(get_writing_element_fields(ctx, "faction", QuestionApplicable.FACTION, g.id, only_visible=False))
        ctx["sheet_factions"].append(data)


def get_character_sheet_fields(ctx):
    if "character" not in ctx["features"]:
        return

    ctx["sheet_char"].update(get_character_element_fields(ctx, ctx["character"].id, only_visible=False))


def get_char_check(request, ctx, num, restrict=False, bypass=False):
    get_event_cache_all(ctx)
    if num not in ctx["chars"]:
        raise NotFoundError()

    ctx["char"] = ctx["chars"][num]

    if bypass or (request.user.is_authenticated and has_access_character(request, ctx)):
        get_char(ctx, num, True)
        ctx["check"] = 1
        return

    if ctx["char"].get("hide", False):
        raise NotFoundError()

    if restrict:
        raise Http404("Not your character")


def get_chars_relations(text, chs_numbers):
    chs = []
    extinct = []

    if not chs_numbers:
        return chs, extinct

    tx = strip_tags(text)

    max_number = chs_numbers[0]
    for number in range(max_number + 100, 0, -1):
        k = f"#{number}"
        if k not in tx:
            continue

        tx = tx.replace(k, "")

        if number in chs_numbers:
            chs.append(number)
        else:
            extinct.append(number)

    return chs, extinct
