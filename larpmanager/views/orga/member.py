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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.models.registration import Registration
from larpmanager.utils.event import check_event_permission

from datetime import date

from django.db.models import Count

from larpmanager.forms.miscellanea import OrgaHelpQuestionForm, SendMailForm
from larpmanager.models.access import get_event_staffers
from larpmanager.models.event import PreRegistration
from larpmanager.models.member import Membership, Member
from larpmanager.models.miscellanea import HelpQuestion, Email
from larpmanager.models.registration import (
    RegistrationTicket,
)
from larpmanager.cache.character import get_event_cache_all
from larpmanager.utils.paginate import orga_paginate
from larpmanager.utils.tasks import send_mail_exec


@login_required
def orga_newsletter(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_newsletter")
    que = Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
    que = que.exclude(ticket__tier=RegistrationTicket.WAITING).select_related("member")
    ctx["list"] = que.values_list("member__id", "member__email", "member__name", "member__surname")
    return render(request, "larpmanager/orga/users/newsletter.html", ctx)


@login_required
def orga_safety(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_safety")
    get_event_cache_all(ctx)

    member_chars = {}
    for _num, el in ctx["chars"].items():
        if "player_id" not in el:
            continue
        if el["player_id"] not in member_chars:
            member_chars[el["player_id"]] = []
        member_chars[el["player_id"]].append(f"#{el['number']} {el['name']}")

    ctx["list"] = []
    for el in (
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
        .exclude(member__safety__isnull=True)
        .select_related("member")
    ):
        if len(el.member.safety) > 3:
            if el.member_id in member_chars:
                el.member.chars = member_chars[el.member_id]
            ctx["list"].append(el.member)
    return render(request, "larpmanager/orga/users/safety.html", ctx)


@login_required
def orga_diet(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_diet")
    get_event_cache_all(ctx)

    member_chars = {}
    for _num, el in ctx["chars"].items():
        if "player_id" not in el:
            continue
        if el["player_id"] not in member_chars:
            member_chars[el["player_id"]] = []
        member_chars[el["player_id"]].append(f"#{el['number']} {el['name']}")

    ctx["list"] = []
    for el in (
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
        .exclude(member__diet__isnull=True)
        .select_related("member")
    ):
        if len(el.member.diet) > 3:
            if el.member_id in member_chars:
                el.member.chars = member_chars[el.member_id]
            ctx["list"].append(el.member)
    return render(request, "larpmanager/orga/users/diet.html", ctx)


@login_required
def orga_spam(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_spam")

    already = list(
        Registration.objects.filter(run__event=ctx["event"], run__end__gte=date.today()).values_list(
            "member_id", flat=True
        )
    )

    already.extend([mb.id for mb in get_event_staffers(ctx["event"])])

    members = Membership.objects.filter(assoc_id=ctx["a_id"])
    members = members.exclude(status=Membership.EMPTY).values_list("member_id", flat=True)

    lst = {}
    que = Member.objects.filter(newsletter=Member.ALL)
    que = que.filter(id__in=members)
    que = que.exclude(id__in=already)
    for m in que.values_list("language", "email"):
        language = m[0]
        if language not in lst:
            lst[language] = []
        lst[language].append(m[1])
    ctx["lst"] = lst
    return render(request, "larpmanager/orga/users/spam.html", ctx)


@login_required
def orga_persuade(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_persuade")

    already = list(
        Registration.objects.filter(run__event=ctx["event"], run__end__gte=date.today()).values_list(
            "member_id", flat=True
        )
    )

    already.extend([mb.id for mb in get_event_staffers(ctx["event"])])

    members = Membership.objects.filter(assoc_id=ctx["a_id"])
    members = members.exclude(status=Membership.EMPTY).values_list("member_id", flat=True)

    que = Member.objects.filter(id__in=members)
    que = que.exclude(id__in=already)

    pre_regs = set(PreRegistration.objects.filter(event=ctx["event"]).values_list("member_id", flat=True))

    reg_counts = {}
    for el in (
        Registration.objects.filter(member_id__in=members, cancellation_date__isnull=True)
        .exclude(member_id__in=already)
        .values("member_id")
        .annotate(Count("member_id"))
    ):
        reg_counts[el["member_id"]] = el["member_id__count"]

    ctx["lst"] = []
    for m in que.values_list("id", "name", "surname", "nickname"):
        pre_reg = m[0] in pre_regs
        reg_count = 0
        if m[0] in reg_counts:
            reg_count = reg_counts[m[0]]
        ctx["lst"].append((m[0], m[1], m[2], m[3], pre_reg, reg_count))

    return render(request, "larpmanager/orga/users/persuade.html", ctx)


@login_required
def orga_questions(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_questions")

    last_q = {}
    for cq in HelpQuestion.objects.filter(assoc_id=ctx["a_id"], run=ctx["run"]).order_by("created"):
        last_q[cq.member.id] = (cq, cq.is_user, cq.closed)
    ctx["open"] = []
    ctx["closed"] = []
    for cid in last_q:
        (cq, is_user, closed) = last_q[cid]
        if is_user and not closed:
            ctx["open"].append(cq)
        else:
            ctx["closed"].append(cq)

    ctx["open"].sort(key=lambda x: x.created)
    ctx["closed"].sort(key=lambda x: x.created, reverse=True)

    return render(request, "larpmanager/orga/users/questions.html", ctx)


@login_required
def orga_questions_answer(request, s, n, r):
    ctx = check_event_permission(request, s, n, "orga_questions")

    member = Member.objects.get(pk=r)
    if request.method == "POST":
        form = OrgaHelpQuestionForm(request.POST, request.FILES)
        if form.is_valid():
            hp = form.save(commit=False)
            hp.member = member
            hp.is_user = False
            hp.assoc_id = ctx["a_id"]
            hp.run = ctx["run"]
            hp.save()
            messages.success(request, _("Answer submitted!"))
            return redirect("orga_questions", s=s, n=n)
    else:
        form = OrgaHelpQuestionForm()

    ctx["form"] = form
    ctx["member"] = member

    get_event_cache_all(ctx)
    ctx["reg_characters"] = []
    ctx["reg_factions"] = []
    for _num, char in ctx["chars"].items():
        if "player_id" not in char:
            continue
        if char["player_id"] == member.id:
            ctx["reg_characters"].append(char)
            for fnum in char["factions"]:
                ctx["reg_factions"].append(ctx["factions"][fnum])

    ctx["list"] = HelpQuestion.objects.filter(member_id=r, assoc_id=ctx["a_id"], run_id=ctx["run"]).order_by("-created")
    return render(request, "larpmanager/orga/users/questions_answer.html", ctx)


@login_required
def orga_questions_close(request, s, n, r):
    ctx = check_event_permission(request, s, n, "orga_questions")

    h = HelpQuestion.objects.filter(member_id=r, assoc_id=ctx["a_id"], run_id=ctx["run"]).order_by("-created").first()
    h.closed = True
    h.save()
    return redirect("orga_questions", s=s, n=n)


def send_mail_batch(request, assoc_id=None, run_id=None):
    players = request.POST["players"]
    subj = request.POST["subject"]
    body = request.POST["body"]
    raw = request.POST["raw"]
    reply_to = request.POST["reply_to"]
    if raw:
        body = raw

    send_mail_exec(players, subj, body, assoc_id, run_id, reply_to)


@login_required
def orga_send_mail(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_send_mail")
    if request.method == "POST":
        form = SendMailForm(request.POST)
        if form.is_valid():
            send_mail_batch(request, run_id=ctx["run"].id)
            messages.success(request, _("Mail added to queue!"))
            return redirect(request.path_info)
    else:
        form = SendMailForm()
    ctx["form"] = form
    return render(request, "larpmanager/exe/users/send_mail.html", ctx)


@login_required
def orga_archive_email(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_archive_email")
    orga_paginate(request, ctx, Email)
    return render(request, "larpmanager/exe/users/archive_mail.html", ctx)


@login_required
def orga_sensitive(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_sensitive")

    get_event_cache_all(ctx)

    member_chars = {}
    for _num, el in ctx["chars"].items():
        if "player_id" not in el:
            continue
        if el["player_id"] not in member_chars:
            member_chars[el["player_id"]] = []
        member_chars[el["player_id"]].append(f"#{el['number']} {el['name']}")

    member_list = list(
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True).values_list("member_id", flat=True)
    )
    member_list.extend([mb.id for mb in get_event_staffers(ctx["run"].event)])

    ctx["list"] = Member.objects.filter(id__in=member_list).order_by("created")
    for el in ctx["list"]:
        if el.id in member_chars:
            el.chars = member_chars[el.id]

    ctx["fields"] = []
    for f in request.assoc["members_fields"]:
        if f in ["diet", "safety", "profile", "newsletter", "language"]:
            continue
        ctx["fields"].append(f)

    return render(request, "larpmanager/orga/users/sensitive.html", ctx)
