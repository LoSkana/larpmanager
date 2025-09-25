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

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_all
from larpmanager.forms.miscellanea import OrgaHelpQuestionForm, SendMailForm
from larpmanager.models.access import get_event_staffers
from larpmanager.models.event import PreRegistration
from larpmanager.models.member import FirstAidChoices, Member, Membership, MembershipStatus, NewsletterChoices
from larpmanager.models.miscellanea import Email, HelpQuestion
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.utils.common import _get_help_questions
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.member import get_mail
from larpmanager.utils.paginate import orga_paginate
from larpmanager.utils.tasks import send_mail_exec


@login_required
def orga_newsletter(request, s):
    ctx = check_event_permission(request, s, "orga_newsletter")
    que = Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
    que = que.exclude(ticket__tier=TicketTier.WAITING).select_related("member")
    ctx["list"] = que.values_list("member__id", "member__email", "member__name", "member__surname")
    return render(request, "larpmanager/orga/users/newsletter.html", ctx)


@login_required
def orga_safety(request, s):
    ctx = check_event_permission(request, s, "orga_safety")
    get_event_cache_all(ctx)
    min_length = 3

    member_chars = {}
    for _num, el in ctx["chars"].items():
        if "player_id" not in el:
            continue
        if el["player_id"] not in member_chars:
            member_chars[el["player_id"]] = []
        member_chars[el["player_id"]].append(f"#{el['number']} {el['name']}")

    ctx["list"] = []
    que = Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
    que = que.exclude(member__safety__isnull=True).select_related("member")
    for el in que:
        if len(el.member.safety) > min_length:
            if el.member_id in member_chars:
                el.member.chars = member_chars[el.member_id]
            ctx["list"].append(el.member)

    ctx["list"] = sorted(ctx["list"], key=lambda x: x.display_member())

    return render(request, "larpmanager/orga/users/safety.html", ctx)


@login_required
def orga_diet(request, s):
    ctx = check_event_permission(request, s, "orga_diet")
    get_event_cache_all(ctx)
    min_length = 3

    member_chars = {}
    for _num, el in ctx["chars"].items():
        if "player_id" not in el:
            continue
        if el["player_id"] not in member_chars:
            member_chars[el["player_id"]] = []
        member_chars[el["player_id"]].append(f"#{el['number']} {el['name']}")

    ctx["list"] = []
    que = Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
    que = que.exclude(member__diet__isnull=True).select_related("member")
    for el in que:
        if len(el.member.diet) > min_length:
            if el.member_id in member_chars:
                el.member.chars = member_chars[el.member_id]
            ctx["list"].append(el.member)

    ctx["list"] = sorted(ctx["list"], key=lambda x: x.display_member())

    return render(request, "larpmanager/orga/users/diet.html", ctx)


@login_required
def orga_spam(request, s):
    ctx = check_event_permission(request, s, "orga_spam")

    already = list(
        Registration.objects.filter(run__event=ctx["event"], run__end__gte=date.today()).values_list(
            "member_id", flat=True
        )
    )

    already.extend([mb.id for mb in get_event_staffers(ctx["event"])])

    members = Membership.objects.filter(assoc_id=ctx["a_id"])
    members = members.exclude(status=MembershipStatus.EMPTY).values_list("member_id", flat=True)

    lst = {}
    que = Member.objects.filter(newsletter=NewsletterChoices.ALL)
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
def orga_persuade(request, s):
    """Display members who can be persuaded to register for the event.

    Shows association members who haven't registered yet, excluding current
    registrants and staff, with pre-registration status and event history.
    """
    ctx = check_event_permission(request, s, "orga_persuade")

    already = list(
        Registration.objects.filter(run__event=ctx["event"], run__end__gte=date.today()).values_list(
            "member_id", flat=True
        )
    )

    already.extend([mb.id for mb in get_event_staffers(ctx["event"])])

    members = Membership.objects.filter(assoc_id=ctx["a_id"])
    members = members.exclude(status=MembershipStatus.EMPTY).values_list("member_id", flat=True)

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
def orga_questions(request, s):
    ctx = check_event_permission(request, s, "orga_questions")

    ctx["closed"], ctx["open"] = _get_help_questions(ctx, request)

    ctx["open"].sort(key=lambda x: x.created)
    ctx["closed"].sort(key=lambda x: x.created, reverse=True)

    return render(request, "larpmanager/orga/users/questions.html", ctx)


@login_required
def orga_questions_answer(request, s, r):
    """Handle organizer responses to member help questions.

    Args:
        request: HTTP request object
        s: Event/run identifier
        r: Member ID who submitted the question

    Returns:
        Rendered template for answering help questions
    """
    ctx = check_event_permission(request, s, "orga_questions")

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
            return redirect("orga_questions", s=s)
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
def orga_questions_close(request, s, r):
    ctx = check_event_permission(request, s, "orga_questions")

    h = HelpQuestion.objects.filter(member_id=r, assoc_id=ctx["a_id"], run_id=ctx["run"]).order_by("-created").first()
    h.closed = True
    h.save()
    return redirect("orga_questions", s=s)


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
def orga_send_mail(request, s):
    ctx = check_event_permission(request, s, "orga_send_mail")
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
def orga_archive_email(request, s):
    ctx = check_event_permission(request, s, "orga_archive_email")
    orga_paginate(request, ctx, Email)
    return render(request, "larpmanager/exe/users/archive_mail.html", ctx)


# TODO
@login_required
def orga_read_mail(request, s, nm):
    ctx = check_event_permission(request, s, "orga_archive_email")
    ctx["email"] = get_mail(request, ctx, nm)
    return render(request, "larpmanager/exe/users/read_mail.html", ctx)


@login_required
def orga_sensitive(request, s):
    """Display sensitive member information for event organizers.

    Args:
        request: HTTP request object with user and association data
        s: Event/run identifier

    Returns:
        Rendered template with member sensitive data and character assignments
    """
    ctx = check_event_permission(request, s, "orga_sensitive")

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

    member_cls: type[Member] = Member
    member_fields = ["name", "surname"] + sorted(request.assoc["members_fields"])

    ctx["list"] = Member.objects.filter(id__in=member_list).order_by("created")
    for el in ctx["list"]:
        if el.id in member_chars:
            el.chars = member_chars[el.id]

        member_field_correct(el, member_fields)

    ctx["fields"] = {}
    for field_name in member_fields:
        if not field_name:
            continue
        if field_name in ["diet", "safety", "profile", "newsletter", "language"]:
            continue
        # noinspection PyUnresolvedReferences, PyProtectedMember
        ctx["fields"][field_name] = member_cls._meta.get_field(field_name).verbose_name

    ctx["list"] = sorted(ctx["list"], key=lambda x: x.display_member())

    return render(request, "larpmanager/orga/users/sensitive.html", ctx)


def member_field_correct(el, member_fields):
    if "residence_address" in member_fields:
        el.residence_address = el.get_residence()
    if "first_aid" in member_fields:
        if el.first_aid == FirstAidChoices.YES:
            el.first_aid = mark_safe('<i class="fa-solid fa-check"></i>')
        else:
            el.first_aid = ""
    if "document_type" in member_fields:
        el.document_type = el.get_document_type_display()
    if "gender" in member_fields:
        el.gender = el.get_gender_display()
