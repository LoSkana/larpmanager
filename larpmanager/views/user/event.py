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
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.cache.character import (
    get_event_cache_all,
    get_writing_element_fields,
)
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.fields import visible_writing_fields
from larpmanager.cache.registration import get_reg_counts
from larpmanager.models.association import AssocTextType
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import (
    DevelopStatus,
    EventTextType,
    Run,
)
from larpmanager.models.form import (
    QuestionApplicable,
    RegistrationOption,
    _get_writing_mapping,
)
from larpmanager.models.member import MembershipStatus, get_user_membership
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.writing import (
    Character,
    CharacterStatus,
    Faction,
    FactionType,
)
from larpmanager.utils.auth import is_lm_admin
from larpmanager.utils.base import def_user_ctx
from larpmanager.utils.common import get_element
from larpmanager.utils.event import get_event, get_event_run
from larpmanager.utils.exceptions import (
    HiddenError,
)
from larpmanager.utils.registration import registration_status
from larpmanager.utils.text import get_assoc_text, get_event_text


def calendar(request, lang):
    aid = request.assoc["id"]
    my_regs = None
    my_runs_list = []
    if request.user.is_authenticated:
        ref = datetime.now() - timedelta(days=3)
        my_regs = Registration.objects.filter(
            run__event__assoc_id=aid,
            cancellation_date__isnull=True,
            redeem_code__isnull=True,
            member=request.user.member,
            run__end__gte=ref.date(),
        )
        my_regs = my_regs.select_related("ticket")
        my_runs_list = [reg.run_id for reg in my_regs]

    ctx = def_user_ctx(request)
    ctx.update({"open": [], "future": [], "langs": [], "page": "calendar"})
    if lang:
        ctx["lang"] = lang
    for run in get_coming_runs(aid, my_runs_list=my_runs_list):
        registration_status(run, request.user, my_regs=my_regs)
        if run.status["open"]:
            ctx["open"].append(run)
        elif "already" not in run.status:
            ctx["future"].append(run)

    ctx["custom_text"] = get_assoc_text(request.assoc["id"], AssocTextType.HOME)

    return render(request, "larpmanager/general/calendar.html", ctx)


def get_coming_runs(assoc_id, my_runs_list=None, future=True):
    runs = Run.objects.exclude(development=DevelopStatus.CANC).exclude(event__visible=False).select_related("event")
    if my_runs_list:
        runs = runs.exclude(Q(development=DevelopStatus.START) & ~Q(id__in=my_runs_list))
    else:
        runs = runs.exclude(development=DevelopStatus.START)
    if future:
        ref = datetime.now() - timedelta(days=3)
        runs = runs.filter(end__gte=ref.date()).order_by("end")
    else:
        ref = datetime.now() + timedelta(days=3)
        runs = runs.filter(end__lte=ref.date()).order_by("-end")
    if assoc_id:
        runs = runs.filter(event__assoc_id=assoc_id)
    return runs


def home_json(request, lang="it"):
    aid = request.assoc["id"]
    if lang:
        request.LANGUAGE_CODE = lang

    res = []
    runs = get_coming_runs(aid)
    already = []
    for run in runs:
        if run.event.id not in already:
            res.append(run.event.show())
        already.append(run.event.id)
    return JsonResponse({"res": res})


def carousel(request):
    ctx = def_user_ctx(request)
    ctx.update({"list": []})
    cache = {}
    ref = (datetime.now() - timedelta(days=3)).date()
    # for run in get_coming_runs(request, ctx, aid):
    # ref = datetime.now() - timedelta(days=3)
    for run in (
        Run.objects.filter(event__assoc_id=request.assoc["id"])
        .exclude(development=DevelopStatus.START)
        .exclude(development=DevelopStatus.CANC)
        .order_by("-end")
        .select_related("event")
    ):
        if run.event_id in cache:
            continue
        if not run.end:
            continue
        cache[run.event_id] = 1
        el = run.event.show()
        el["coming"] = run.end > ref
        ctx["list"].append(el)

    ctx["json"] = json.dumps(ctx["list"])

    return render(request, "larpmanager/general/carousel.html", ctx)


@login_required
def share(request):
    ctx = def_user_ctx(request)

    el = get_user_membership(request.user.member, request.assoc["id"])
    if el.status != MembershipStatus.EMPTY:
        messages.success(request, _("You have already granted data sharing with this organisation") + "!")
        return redirect("home")

    if request.method == "POST":
        el.status = MembershipStatus.JOINED
        el.save()
        messages.success(request, _("You have granted data sharing with this organisation!"))
        return redirect("home")

    ctx["disable_join"] = True

    return render(request, "larpmanager/member/share.html", ctx)


@login_required
def legal_notice(request):
    ctx = def_user_ctx(request)
    ctx.update({"text": get_assoc_text(request.assoc["id"], AssocTextType.LEGAL)})
    return render(request, "larpmanager/general/legal.html", ctx)


@login_required
def event_register(request, s):
    ctx = get_event(request, s)
    # check future runs
    runs = (
        Run.objects.filter(event=ctx["event"], end__gte=datetime.now())
        .exclude(development=DevelopStatus.START)
        .exclude(event__visible=False)
        .order_by("end")
    )
    if len(runs) == 0 and "pre_register" in request.assoc["features"]:
        return redirect("pre_register", s=s)
    elif len(runs) == 1:
        run = runs.first()
        return redirect("register", s=s, n=run.number)
    ctx["list"] = []
    features_map = {ctx["event"].slug: ctx["features"]}
    for r in runs:
        registration_status(r, request.user, features_map=features_map)
        ctx["list"].append(r)
    return render(request, "larpmanager/general/event_register.html", ctx)


def calendar_past(request):
    aid = request.assoc["id"]
    ctx = def_user_ctx(request)
    my_regs = None
    if request.user.is_authenticated:
        my_regs = Registration.objects.filter(
            run__event__assoc_id=aid,
            cancellation_date__isnull=True,
            redeem_code__isnull=True,
            member=request.user.member,
        )
        my_regs = my_regs.select_related("ticket")
    ctx["list"] = []
    for run in get_coming_runs(aid, future=False):
        registration_status(run, request.user, my_regs=my_regs)
        ctx["list"].append(run)
    ctx["page"] = "calendar_past"
    return render(request, "larpmanager/general/past.html", ctx)


def check_gallery_visibility(request, ctx):
    if is_lm_admin(request):
        return True

    if "manage" in ctx:
        return True

    hide_signup = ctx["event"].get_config("gallery_hide_signup", False)
    hide_login = ctx["event"].get_config("gallery_hide_login", False)

    if hide_login and not request.user.is_authenticated:
        ctx["hide_login"] = True
        return False

    if hide_signup and not ctx["run"].reg:
        ctx["hide_signup"] = True
        return False

    return True


def gallery(request, s, n):
    ctx = get_event_run(request, s, n, status=True)

    ctx["reg_list"] = []

    features = get_event_features(ctx["event"].id)

    if check_gallery_visibility(request, ctx):
        if not ctx["event"].get_config("writing_field_visibility", False) or ctx.get("show_character"):
            get_event_cache_all(ctx)

        hide_uncasted_players = ctx["event"].get_config("gallery_hide_uncasted_players", False)
        if not hide_uncasted_players:
            que = RegistrationCharacterRel.objects.filter(reg__run_id=ctx["run"].id)
            if ctx["event"].get_config("user_character_approval", False):
                que = que.filter(character__status__in=[CharacterStatus.APPROVED])
            assigned = que.values_list("reg_id", flat=True)

            que_reg = Registration.objects.filter(run_id=ctx["run"].id, cancellation_date__isnull=True)
            que_reg = que_reg.exclude(pk__in=assigned).exclude(ticket__tier=TicketTier.WAITING)
            for reg in que_reg.select_related("member", "ticket").order_by("search"):
                if not is_reg_provisional(reg, features):
                    ctx["reg_list"].append(reg.member)

    return render(request, "larpmanager/event/gallery.html", ctx)


def event(request, s, n):
    ctx = get_event_run(request, s, n, status=True)
    ctx["coming"] = []
    ctx["past"] = []
    my_regs = None
    if request.user.is_authenticated:
        my_regs = Registration.objects.filter(
            run__event=ctx["event"],
            redeem_code__isnull=True,
            cancellation_date__isnull=True,
            member=request.user.member,
        )
    runs = Run.objects.filter(event=ctx["event"])
    ref = datetime.now() - timedelta(days=3)

    features_map = {ctx["event"].slug: ctx["features"]}
    for r in runs:
        if not r.end:
            continue

        registration_status(r, request.user, my_regs=my_regs, features_map=features_map)

        if r.end > ref.date():
            ctx["coming"].append(r)
        else:
            ctx["past"].append(r)

    ctx["data"] = ctx["event"].show()

    # ~ if 'fullscreen' in ctx['features']:
    # ~ ctx['event'].background = ctx['event'].fullscreen
    # ~ return render(request, 'larpmanager/general/event_full.html', ctx)

    return render(request, "larpmanager/event/event.html", ctx)


def event_redirect(request, s):
    ctx = get_event(request, s)
    n = Run.objects.filter(event=ctx["event"]).order_by("-end").first().number
    return redirect("event", s=s, n=n)


def search(request, s, n):
    ctx = get_event_run(request, s, n, status=True)

    if check_gallery_visibility(request, ctx) and ctx["show_character"]:
        get_event_cache_all(ctx)
        ctx["search_text"] = get_event_text(ctx["event"].id, EventTextType.SEARCH)
        visible_writing_fields(ctx, QuestionApplicable.CHARACTER)
        for _num, char in ctx["chars"].items():
            fields = char.get("fields")
            if not fields:
                continue
            to_delete = [
                qid for qid in list(fields) if str(qid) not in ctx.get("show_character", []) and "show_all" not in ctx
            ]
            for qid in to_delete:
                del fields[qid]

    for slug in ["chars", "factions", "questions", "options", "searchable"]:
        if slug not in ctx:
            ctx[slug] = {}
        ctx[f"{slug}_json"] = json.dumps(ctx[slug])

    return render(request, "larpmanager/event/search.html", ctx)


def get_fact(qs):
    ls = []
    for f in qs:
        fac = f.show_complete()
        # print(fac)
        if len(fac["characters"]) == 0:
            continue
        ls.append(fac)
    return ls


def get_factions(ctx):
    fcs = ctx["event"].get_elements(Faction)
    ctx["sec"] = get_fact(fcs.filter(typ=FactionType.PRIM).order_by("number"))
    ctx["trasv"] = get_fact(fcs.filter(typ=FactionType.TRASV).order_by("number"))


def check_visibility(ctx, typ, name):
    mapping = _get_writing_mapping()
    if mapping.get(typ) not in ctx["features"]:
        raise Http404(typ + " not active")

    if "staff" not in ctx and not ctx[f"show_{typ}"]:
        raise HiddenError(ctx["event"].slug, ctx["run"].number, name)


def factions(request, s, n):
    ctx = get_event_run(request, s, n, status=True)
    check_visibility(ctx, "faction", _("Factions"))
    get_event_cache_all(ctx)
    return render(request, "larpmanager/event/factions.html", ctx)


def faction(request, s, n, g):
    ctx = get_event_run(request, s, n, status=True)
    check_visibility(ctx, "faction", _("Factions"))

    get_event_cache_all(ctx)

    typ = None
    if g in ctx["factions"]:
        ctx["faction"] = ctx["factions"][g]
        typ = ctx["faction"]["typ"]

    if "faction" not in ctx or typ == "secret" or "id" not in ctx["faction"]:
        raise Http404("Faction does not exist")

    ctx["fact"] = get_writing_element_fields(
        ctx, "faction", QuestionApplicable.FACTION, ctx["faction"]["id"], only_visible=True
    )

    return render(request, "larpmanager/event/faction.html", ctx)


def quests(request, s, n, g=None):
    ctx = get_event_run(request, s, n, status=True)
    check_visibility(ctx, "quest", _("Quest"))

    if not g:
        ctx["list"] = QuestType.objects.filter(event=ctx["event"]).order_by("number").prefetch_related("quests")
        return render(request, "larpmanager/event/quest_types.html", ctx)

    get_element(ctx, g, "quest_type", QuestType, by_number=True)
    ctx["list"] = []
    for el in Quest.objects.filter(event=ctx["event"], hide=False, typ=ctx["quest_type"]).order_by("number"):
        ctx["list"].append(el.show_complete())
    return render(request, "larpmanager/event/quests.html", ctx)


def quest(request, s, n, g):
    ctx = get_event_run(request, s, n, status=True)
    check_visibility(ctx, "quest", _("Quest"))

    get_element(ctx, g, "quest", Quest, by_number=True)
    ctx["quest_fields"] = get_writing_element_fields(
        ctx, "quest", QuestionApplicable.QUEST, ctx["quest"].id, only_visible=True
    )

    traits = []
    for el in ctx["quest"].traits.all():
        res = get_writing_element_fields(ctx, "trait", QuestionApplicable.TRAIT, el.id, only_visible=True)
        res.update(el.show())
        traits.append(res)
    ctx["traits"] = traits

    return render(request, "larpmanager/event/quest.html", ctx)


def limitations(request, s, n):
    ctx = get_event_run(request, s, n, status=True)

    counts = get_reg_counts(ctx["run"])

    ctx["disc"] = []
    for discount in ctx["run"].discounts.exclude(visible=False):
        ctx["disc"].append(discount.show(ctx["run"]))

    ctx["tickets"] = []
    for ticket in RegistrationTicket.objects.filter(event=ctx["event"], max_available__gt=0, visible=True):
        dt = ticket.show(ctx["run"])
        key = f"tk_{ticket.id}"
        if key in counts:
            dt["used"] = counts[key]
        ctx["tickets"].append(dt)

    ctx["opts"] = []
    que = RegistrationOption.objects.filter(question__event=ctx["event"], max_available__gt=0)
    for option in que:
        dt = option.show(ctx["run"])
        key = f"option_{option.id}"
        if key in counts:
            dt["used"] = counts[key]
        ctx["opts"].append(dt)

    return render(request, "larpmanager/event/limitations.html", ctx)


def export(request, s, t):
    ctx = get_event(request, s)
    if t == "char":
        lst = ctx["event"].get_elements(Character).order_by("number")
    elif t == "faction":
        lst = ctx["event"].get_elements(Faction).order_by("number")
    elif t == "quest":
        lst = Quest.objects.filter(event=ctx["event"]).order_by("number")
    elif t == "trait":
        lst = Trait.objects.filter(quest__event=ctx["event"]).order_by("number")
    else:
        raise Http404("wrong type")
    # r = Run(event=ctx["event"])
    aux = {}
    for el in lst:
        aux[el.number] = el.show(ctx["run"])
    return JsonResponse(aux)
