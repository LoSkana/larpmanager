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

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_all
from larpmanager.mail.base import mail_confirm_casting
from larpmanager.models.casting import AssignmentTrait, Casting, CastingAvoid, Quest, QuestType, Trait
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.models.writing import Character, Faction, FactionType
from larpmanager.utils.common import get_element
from larpmanager.utils.event import get_event_filter_characters, get_event_run
from larpmanager.utils.exceptions import check_event_feature
from larpmanager.utils.registration import registration_status


def casting_characters(ctx, reg):
    filter_filler = hasattr(reg, "ticket") and reg.ticket and reg.ticket.tier != TicketTier.FILLER
    filters = {"png": True, "free": True, "mirror": True, "filler": filter_filler, "nonfiller": not filter_filler}
    get_event_filter_characters(ctx, filters)
    choices = {}
    facts = []
    num = 0
    for fac in ctx["factions"]:
        k = fac.data["name"]
        choices[k] = {}
        facts.append(k)
        for char in fac.chars:
            choices[k][char.id] = char.show(ctx["run"])
            num += 1

    ctx["factions"] = json.dumps(facts)
    ctx["choices"] = json.dumps(choices)

    ctx["faction_filter"] = ctx["event"].get_elements(Faction).filter(typ=FactionType.TRASV)


def casting_quest_traits(ctx, typ):
    choices = {}
    factions = []
    num = 0
    for quest in Quest.objects.filter(event=ctx["event"], typ=typ, hide=False).order_by("number"):
        gr = quest.show()["name"]
        dc = {}
        for trait in Trait.objects.filter(quest=quest, hide=False).order_by("number"):
            if AssignmentTrait.objects.filter(trait=trait, run=ctx["run"]).count() > 0:
                continue
            dc[trait.id] = trait.show()
            num += 1
        if len(dc.keys()) == 0:
            continue
        choices[gr] = dc
        factions.append(gr)

    ctx["factions"] = json.dumps(list(factions))
    ctx["choices"] = json.dumps(choices)


def casting_details(ctx, typ):
    get_event_cache_all(ctx)

    if typ > 0:
        data = ctx["quest_types"][typ]
        ctx["gl_name"] = data["name"]
        ctx["cl_name"] = _("Quest")
        ctx["el_name"] = _("Trait")
    else:
        ctx["gl_name"] = _("Characters")
        ctx["cl_name"] = _("Faction")
        ctx["el_name"] = _("Character")

    ctx["typ"] = typ
    ctx["casting_add"] = int(ctx["event"].get_config("casting_add", 0))
    ctx["casting_min"] = int(ctx["event"].get_config("casting_min", 5))
    ctx["casting_max"] = int(ctx["event"].get_config("casting_max", 5))
    for s in ["show_pref", "history", "avoid"]:
        ctx["casting_" + s] = ctx["event"].get_config("casting_" + s, False)
    return ctx


@login_required
def casting(request, s, n, typ=0):
    ctx = get_event_run(request, s, n, signup=True, status=True)
    check_event_feature(request, ctx, "casting")

    if ctx["run"].reg is None:
        messages.success(request, _("You must signed up in order to select your preferences") + "!")
        return redirect("gallery", s=ctx["event"].slug, n=ctx["run"].number)

    if ctx["run"].reg and ctx["run"].reg.ticket and ctx["run"].reg.ticket.tier == TicketTier.WAITING:
        messages.success(
            request,
            _(
                "You are on the waiting list, you must be registered with a regular ticket to be "
                "able to select your preferences!"
            ),
        )
        return redirect("gallery", s=ctx["event"].slug, n=ctx["run"].number)

    casting_details(ctx, typ)
    # print(ctx)

    red = "larpmanager/event/casting/casting.html"

    _check_already_done(ctx, request, typ)

    if "assigned" in ctx:
        return render(request, red, ctx)

    _get_previous(ctx, request, typ)

    if request.method == "POST":
        prefs = {}
        for i in range(0, ctx["casting_max"]):
            k = f"choice{i}"
            if k not in request.POST:
                continue
            pref = int(request.POST[k])
            if pref in prefs.values():
                messages.warning(request, _("You have indicated several preferences towards the same element!"))
                return redirect("casting", s=ctx["event"].slug, n=ctx["run"].number, typ=typ)
            prefs[i] = pref

        _casting_update(ctx, prefs, request, typ)
        return redirect(request.path_info)

    return render(request, red, ctx)


def _get_previous(ctx, request, typ):
    # compila already
    already = [
        c.element for c in Casting.objects.filter(run=ctx["run"], member=request.user.member, typ=typ).order_by("pref")
    ]
    ctx["already"] = json.dumps(already)
    if typ == 0:
        casting_characters(ctx, ctx["run"].reg)
    else:
        check_event_feature(request, ctx, "questbuilder")
        get_element(ctx, typ, "quest_type", QuestType, by_number=True)
        casting_quest_traits(ctx, ctx["quest_type"])
    try:
        ca = CastingAvoid.objects.get(run=ctx["run"], member=request.user.member, typ=typ)
        ctx["avoid"] = ca.text
    except ObjectDoesNotExist:
        pass


def _check_already_done(ctx, request, typ):
    # check already done
    if typ == 0:
        casting_chars = int(ctx["run"].event.get_config("casting_characters", 1))
        if ctx["run"].reg.rcrs.count() >= casting_chars:
            chars = []
            for el in ctx["run"].reg.rcrs.values_list("character__number", flat=True):
                chars.append(ctx["chars"][el]["name"])
            ctx["assigned"] = ", ".join(chars)
    else:
        try:
            at = AssignmentTrait.objects.get(run=ctx["run"], member=request.user.member, typ=typ)
            ctx["assigned"] = f"{at.trait.quest.show()['name']} - {at.trait.show()['name']}"
        except ObjectDoesNotExist:
            pass


def _casting_update(ctx, prefs, request, typ):
    # delete all castings
    Casting.objects.filter(run=ctx["run"], member=request.user.member, typ=typ).delete()
    for i, pref in prefs.items():
        Casting.objects.create(run=ctx["run"], member=request.user.member, typ=typ, element=pref, pref=i)
    avoid = None
    if "casting_avoid" in ctx and ctx["casting_avoid"]:
        CastingAvoid.objects.filter(run=ctx["run"], member=request.user.member, typ=typ).delete()
        avoid = ""
        if "avoid" in request.POST:
            avoid = request.POST["avoid"]
        if avoid and len(avoid) > 0:
            CastingAvoid.objects.create(run=ctx["run"], member=request.user.member, typ=typ, text=avoid)
    messages.success(request, _("Preferences saved!"))
    lst = []
    for c in Casting.objects.filter(run=ctx["run"], member=request.user.member, typ=typ).order_by("pref"):
        if typ == 0:
            lst.append(Character.objects.get(pk=c.element).show(ctx["run"])["name"])
        else:
            trait = Trait.objects.get(pk=c.element)
            lst.append(f"{trait.quest.show()['name']} - {trait.show()['name']}")
            # mail_confirm_casting_bkg(request.user.member.id, ctx['run'].id, ctx['gl_name'], lst)
    mail_confirm_casting(request.user.member, ctx["run"], ctx["gl_name"], lst, avoid)


def get_casting_preferences(number, ctx, typ=0, casts=None):
    tot_pref = 0
    sum_pref = 0
    distr = {}
    if casts is None:
        casts = Casting.objects.filter(element=number, run=ctx["run"], typ=typ)
        if "staff" not in ctx:
            casts = casts.filter(active=True)

    for v in range(0, ctx["casting_max"] + 1):
        distr[v] = 0
    for cs in casts:
        v = int(cs.pref + 1)
        tot_pref += 1
        sum_pref += v
        if v in distr:
            distr[v] += 1
    if tot_pref == 0:
        avg_pref = "-"
    else:
        avg_pref = "%.2f" % (sum_pref * 1.0 / tot_pref)
    return tot_pref, avg_pref, distr


def casting_preferences_characters(ctx):
    filters = {"png": True}
    if not "staff" not in ctx:
        filters["free"] = True
        filters["mirror"] = True
    get_event_filter_characters(ctx, filters)
    ctx["list"] = []

    casts = {}
    for c in Casting.objects.filter(run=ctx["run"], typ=0, active=True):
        if c.element not in casts:
            casts[c.element] = []
        casts[c.element].append(c)

    for fac in ctx["factions"]:
        for ch in fac.chars:
            cc = []
            if ch.id in casts:
                cc = casts[ch.id]
            # print(cc)
            el = {
                "group_dis": fac.data["name"],
                "name_dis": ch.data["name"],
                "pref": get_casting_preferences(ch.id, ctx, 0, cc),
            }
            ctx["list"].append(el)


def casting_preferences_traits(ctx, typ):
    try:
        qtyp = QuestType.objects.get(event=ctx["event"], number=typ)
    except ObjectDoesNotExist as err:
        raise Http404() from err

    ctx["list"] = []
    for quest in Quest.objects.filter(event=ctx["event"], typ=qtyp, hide=False).order_by("number"):
        gr = quest.show()["name"]
        for trait in Trait.objects.filter(quest=quest, hide=False).order_by("number"):
            if "staff" not in ctx and AssignmentTrait.objects.filter(trait=trait, run=ctx["run"]).count() > 0:
                continue
            el = {
                "group_dis": gr,
                "name_dis": trait.show()["name"],
                "pref": get_casting_preferences(trait.id, ctx, qtyp.number),
            }
            ctx["list"].append(el)


@login_required
def casting_preferences(request, s, n, typ=0):
    ctx = get_event_run(request, s, n, signup=True, status=True)
    casting_details(ctx, typ)

    if not ctx["casting_show_pref"]:
        raise Http404("Not cool, bro!")

    features_map = {ctx["event"].slug: ctx["features"]}
    registration_status(ctx["run"], request.user, features_map=features_map)

    if ctx["run"].reg is None:
        raise Http404("not registered")

    if typ == 0:
        casting_preferences_characters(ctx)
    else:
        check_event_feature(request, ctx, "questbuilder")
        casting_preferences_traits(ctx, typ)

    return render(request, "larpmanager/event/casting/preferences.html", ctx)


def casting_history_characters(ctx):
    ctx["list"] = []
    ctx["cache"] = {}
    for ch in ctx["event"].get_elements(Character).filter(hide=False).select_related("mirror"):
        ctx["cache"][ch.id] = ch

    casts = {}
    for c in Casting.objects.filter(run=ctx["run"], typ=0).order_by("pref"):
        if c.member_id not in casts:
            casts[c.member_id] = []
        casts[c.member_id].append(c)

    query = (
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.STAFF, TicketTier.NPC])
        .select_related("member")
    )

    for reg in query:
        reg.prefs = {}
        if reg.member_id not in casts:
            continue
        for c in casts[reg.member_id]:
            if c.element not in ctx["cache"]:
                continue
            ch = ctx["cache"][c.element]
            if ch.mirror:
                # TODO see how to manage it
                continue

            if ch:
                v = f"#{ch.number} {ch.name}"
            else:
                v = "-----"

            reg.prefs[c.pref + 1] = v
        ctx["list"].append(reg)


def casting_history_traits(ctx):
    ctx["list"] = []
    ctx["cache"] = {}

    casts = {}
    for c in Casting.objects.filter(run=ctx["run"], typ=ctx["typ"]).order_by("pref"):
        if c.member_id not in casts:
            casts[c.member_id] = []
        casts[c.member_id].append(c)

    que = Trait.objects.filter(event=ctx["event"], hide=False)
    for el in que.select_related("quest"):
        nm = f"#{el.number} {el.name}"
        if el.quest:
            nm = f"{nm} ({el.quest.name})"
        ctx["cache"][el.id] = nm

    for reg in (
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.STAFF, TicketTier.NPC])
        .select_related("member")
    ):
        reg.prefs = {}
        if reg.member_id not in casts:
            continue
        for c in casts[reg.member_id]:
            if c.element not in ctx["cache"]:
                continue
            reg.prefs[c.pref + 1] = ctx["cache"][c.element]
        ctx["list"].append(reg)

    # print(ctx)


@login_required
def casting_history(request, s, n, typ=0):
    ctx = get_event_run(request, s, n, signup=True, status=True)
    casting_details(ctx, typ)

    if not ctx["casting_history"]:
        raise Http404("Not cool, bro!")

    if ctx["run"].reg is None and "staff" not in ctx:
        raise Http404("not registered")

    casting_details(ctx, typ)

    if typ == 0:
        casting_history_characters(ctx)
    else:
        check_event_feature(request, ctx, "questbuilder")
        casting_history_traits(ctx)

    return render(request, "larpmanager/event/casting/history.html", ctx)
