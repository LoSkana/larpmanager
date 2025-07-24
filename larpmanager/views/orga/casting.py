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
import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.registration import registration_payments_status
from larpmanager.forms.miscellanea import OrganizerCastingOptionsForm
from larpmanager.models.casting import AssignmentTrait, Casting, CastingAvoid, Quest, QuestType, Trait
from larpmanager.models.member import Member, Membership
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    TicketTier,
)
from larpmanager.models.writing import Character, Faction, FactionType
from larpmanager.utils.common import get_element, get_time_diff_today
from larpmanager.utils.deadlines import get_membership_fee_year
from larpmanager.utils.event import check_event_permission
from larpmanager.views.user.casting import (
    casting_details,
    casting_history_characters,
    casting_history_traits,
    casting_preferences_characters,
    casting_preferences_traits,
)


@login_required
def orga_casting_preferences(request, s, n, typ=0):
    ctx = check_event_permission(request, s, n, "orga_casting_preferences")
    casting_details(ctx, typ)
    if typ == 0:
        casting_preferences_characters(ctx)
    else:
        casting_preferences_traits(ctx, typ)

    return render(request, "larpmanager/event/casting/preferences.html", ctx)


@login_required
def orga_casting_history(request, s, n, typ=0):
    ctx = check_event_permission(request, s, n, "orga_casting_history")
    casting_details(ctx, typ)
    if typ == 0:
        casting_history_characters(ctx)
    else:
        casting_history_traits(ctx)

    return render(request, "larpmanager/event/casting/history.html", ctx)


def assign_casting(request, ctx, typ):
    # TODO Assign member to mirror_inv
    mirror = "mirror" in ctx["features"]
    res = request.POST.get("res")
    if not res:
        messages.error(request, _("Results not present"))
        return
    err = ""
    for sp in res.split():
        aux = sp.split("_")
        try:
            mb = Member.objects.get(pk=aux[0].replace("p", ""))
            reg = Registration.objects.get(member=mb, run=ctx["run"], cancellation_date__isnull=True)
            eid = aux[1].replace("c", "")
            if typ == 0:
                if mirror:
                    char = Character.objects.get(pk=eid)
                    if char.mirror:
                        eid = char.mirror_id

                RegistrationCharacterRel.objects.create(character_id=eid, reg=reg)
            else:
                AssignmentTrait.objects.create(trait_id=eid, run=reg.run, member=mb, typ=typ)
        except Exception as e:
            print(e)
            err += str(e)
    if err:
        messages.error(request, err)


def get_casting_choices_characters(ctx, options):
    choices = {}
    mirrors = {}
    taken = []

    allowed = []
    if "faction" in ctx["features"]:
        que = ctx["event"].get_elements(Faction).filter(typ=FactionType.PRIM)
        for el in que.order_by("number"):
            if str(el.id) not in options["factions"]:
                continue
            allowed.extend(el.characters.values_list("id", flat=True))

    chars = RegistrationCharacterRel.objects.filter(reg__run=ctx["run"]).values_list("character_id", flat=True)

    # remove characters that are mirrors
    que = ctx["event"].get_elements(Character)
    for c in que.exclude(hide=True):
        if allowed and c.id not in allowed:
            continue

        if c.id in chars:
            taken.append(c.id)
        if c.mirror_id:
            if c.mirror_id in chars:
                taken.append(c.id)
            mirrors[c.id] = str(c.mirror_id)
        choices[c.id] = str(c)

    return choices, taken, mirrors, allowed


def get_casting_choices_quests(ctx):
    choices = {}
    taken = []
    for q in Quest.objects.filter(event=ctx["event"], typ=ctx["quest_type"]).order_by("number"):
        # gr = q.show()["name"]
        for t in Trait.objects.filter(quest=q).order_by("number"):
            if AssignmentTrait.objects.filter(trait=t, run=ctx["run"]).count() > 0:
                taken.append(t.id)
            choices[t.id] = f"{q.name} - {t.name}"
    return choices, taken, {}


def check_player_skip_characters(reg, ctx):
    # check it has a number of characters assigned less the allowed amount
    casting_chars = int(ctx["event"].get_config("casting_characters", 1))
    return RegistrationCharacterRel.objects.filter(reg=reg).count() >= casting_chars


def check_player_skip_quests(reg, typ):
    return AssignmentTrait.objects.filter(run=reg.run, member=reg.member, typ=typ).count() > 0


def check_casting_player(ctx, reg, options, typ, cache_membs, cache_aim):
    # check if select the player given the ticket
    if "tickets" in options and str(reg.ticket_id) not in options["tickets"]:
        return True

    # check if select the player given the membership status
    if "membership" in ctx["features"]:
        if reg.member.id not in cache_membs:
            return True

        status = cache_membs[reg.member.id]
        if status == "a" and reg.member.id in cache_aim:
            status = "p"

        if "memberships" in options and status not in options["memberships"]:
            return True

    # check if select the player given the payment status
    registration_payments_status(reg)
    if "pays" in options and reg.payment_status:
        if reg.payment_status not in options["pays"]:
            return True

    # check if we have to skip the player (already assigned)
    if typ == 0:
        check = check_player_skip_characters(reg, ctx)
    else:
        check = check_player_skip_quests(reg, typ)

    if check:
        return True

    return False


def get_casting_data(request, ctx, typ, form):
    options = form.get_data()
    # print(options)

    casting_details(ctx, typ)

    players = {}
    didnt_choose = []
    preferences = {}
    nopes = {}
    chosen = {}

    # get casting choices
    if typ == 0:
        (choices, taken, mirrors, allowed) = get_casting_choices_characters(ctx, options)
    else:
        get_element(ctx, typ, "quest_type", QuestType, by_number=True)
        allowed = None
        (choices, taken, mirrors) = get_casting_choices_quests(ctx)

    cache_aim, cache_membs, castings = _casting_prepare(ctx, request, typ)

    # loop over registered players
    que = Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
    que = que.exclude(ticket__tier__in=[TicketTier.WAITING, TicketTier.STAFF, TicketTier.NPC])
    que = que.order_by("created").select_related("ticket", "member")
    for reg in que:
        if check_casting_player(ctx, reg, options, typ, cache_membs, cache_aim):
            continue

        _get_player_info(players, reg)

        pref = _get_player_preferences(allowed, castings, chosen, nopes, reg)

        if len(pref) == 0:
            didnt_choose.append(reg.member.id)
        else:
            preferences[reg.member.id] = pref

    not_chosen, not_chosen_add = _fill_not_chosen(choices, chosen, ctx, preferences, taken)

    avoids = {}
    for el in CastingAvoid.objects.filter(run=ctx["run"], typ=typ):
        avoids[el.member_id] = el.text

    ctx["num_choices"] = min(ctx["casting_max"] + not_chosen_add, len(choices))
    ctx["choices"] = json.dumps(choices)
    ctx["mirrors"] = json.dumps(mirrors)
    ctx["players"] = json.dumps(players)
    ctx["preferences"] = json.dumps(preferences)
    ctx["taken"] = json.dumps(taken)
    ctx["not_chosen"] = json.dumps(not_chosen)
    ctx["chosen"] = json.dumps(list(chosen.keys()))
    ctx["didnt_choose"] = json.dumps(didnt_choose)
    ctx["nopes"] = json.dumps(nopes)
    ctx["avoids"] = json.dumps(avoids)


def _casting_prepare(ctx, request, typ):
    cache_aim = get_membership_fee_year(request.assoc["id"])
    cache_membs = {}
    memb_que = Membership.objects.filter(assoc_id=request.assoc["id"])
    for el in memb_que.values("member_id", "status"):
        cache_membs[el["member_id"]] = el["status"]
    castings = {}
    for el in Casting.objects.filter(run=ctx["run"], typ=typ).order_by("pref"):
        if el.member_id not in castings:
            castings[el.member_id] = []
        castings[el.member_id].append(el)
    return cache_aim, cache_membs, castings


def _get_player_info(players, reg):
    # player info
    players[reg.member.id] = {
        "name": str(reg.member),
        "prior": 1,
        "email": reg.member.email,
    }
    if reg.ticket:
        players[reg.member.id]["prior"] = reg.ticket.casting_priority
    # set registration days
    players[reg.member.id]["reg_days"] = -get_time_diff_today(reg.created.date())


def _get_player_preferences(allowed, castings, chosen, nopes, reg):
    # get player preferences
    pref = []
    if reg.member_id in castings:
        for c in castings[reg.member_id]:
            if allowed and c.element not in allowed:
                continue
            p = c.element
            pref.append(p)
            chosen[p] = 1
            if c.nope:
                if reg.member.id not in nopes:
                    nopes[reg.member.id] = []
                nopes[reg.member.id].append(p)
    return pref


def _fill_not_chosen(choices, chosen, ctx, preferences, taken):
    # adds 3 non taken characters to each player preferences to resolve unlucky ties
    not_chosen = []
    for cid in choices.keys():
        if cid not in chosen and cid not in taken:
            not_chosen.append(cid)
    not_chosen.sort()
    not_chosen_add = min(ctx["casting_add"], len(not_chosen))
    for _mid, pref in preferences.items():
        random.shuffle(not_chosen)
        for i in range(0, not_chosen_add):
            pref.append(not_chosen[i])
    return not_chosen, not_chosen_add


@login_required
def orga_casting(request, s, n, typ=None, tick=""):
    ctx = check_event_permission(request, s, n, "orga_casting")
    if typ is None:
        return redirect("orga_casting", s=ctx["event"].slug, n=ctx["run"].number, typ=0)
    ctx["typ"] = typ
    ctx["tick"] = tick
    if request.method == "POST":
        form = OrganizerCastingOptionsForm(request.POST, ctx=ctx)
        if not form.is_valid():
            raise Http404("form not valid")
        if request.POST.get("submit"):
            assign_casting(request, ctx, typ)
            return redirect(request.path_info)
    else:
        form = OrganizerCastingOptionsForm(ctx=ctx)
    casting_details(ctx, typ)
    get_casting_data(request, ctx, typ, form)
    ctx["form"] = form
    return render(request, "larpmanager/orga/casting.html", ctx)


@login_required
def orga_casting_toggle(request, s, n, typ):
    ctx = check_event_permission(request, s, n, "orga_casting")
    try:
        pid = request.POST["pid"]
        oid = request.POST["oid"]
        c = Casting.objects.get(run=ctx["run"], typ=typ, member_id=pid, element=oid)
        c.nope = not c.nope
        c.save()
        return JsonResponse({"res": "ok"})
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko"})
