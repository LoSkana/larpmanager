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

import time
from random import shuffle

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.functions import Substr
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from slugify import slugify

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.accounting.registration import (
    cancel_reg,
    check_reg_bkg,
    get_accounting_refund,
    get_reg_payments,
)
from larpmanager.cache.character import get_event_cache_all, reset_run
from larpmanager.cache.feature import reset_event_features
from larpmanager.cache.links import reset_run_event_links
from larpmanager.cache.registration import reset_cache_reg_counts
from larpmanager.cache.role import has_event_permission
from larpmanager.cache.run import reset_cache_run
from larpmanager.cache.text_fields import get_cache_reg_field
from larpmanager.forms.registration import (
    OrgaRegistrationForm,
    RegistrationCharacterRelForm,
)
from larpmanager.forms.writing import (
    UploadElementsForm,
)
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemOther,
    AccountingItemPayment,
)
from larpmanager.models.casting import AssignmentTrait, QuestType
from larpmanager.models.event import (
    PreRegistration,
)
from larpmanager.models.form import (
    QuestionType,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
)
from larpmanager.models.member import Member, Membership, get_user_membership
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.utils.common import (
    get_char,
    get_discount,
    get_registration,
    get_time_diff,
)
from larpmanager.utils.download import _orga_registrations_acc, download
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.upload import upload_elements
from larpmanager.views.orga.member import member_field_correct


def check_time(times, step, start=None):
    if step not in times:
        times[step] = []
    now = time.time()
    times[step].append(now - start)
    return now


def _orga_registrations_traits(r, ctx):
    if "questbuilder" not in ctx["features"]:
        return

    r.traits = {}
    if not hasattr(r, "chars"):
        return
    for char in r.chars:
        if "traits" not in char:
            continue
        for tr_num in char["traits"]:
            trait = ctx["traits"][tr_num]
            quest = ctx["quests"][trait["quest"]]
            typ = ctx["quest_types"][quest["typ"]]
            typ_num = typ["number"]
            if typ_num not in r.traits:
                r.traits[typ_num] = []
            r.traits[typ_num].append(f"{quest['name']} - {trait['name']}")

    for typ in r.traits:
        r.traits[typ] = ",".join(r.traits[typ])


def _orga_registrations_tickets(r, ctx):
    typ = ("1", _("Standard"))

    ticket_types = {
        TicketTier.FILLER: ("2", _("Filler")),
        TicketTier.WAITING: ("3", _("Waiting")),
        TicketTier.LOTTERY: ("4", _("Lottery")),
        TicketTier.NPC: ("5", _("NPC")),
        TicketTier.COLLABORATOR: ("6", _("Collaborator")),
        TicketTier.STAFF: ("7", _("Staff")),
        TicketTier.SELLER: ("8", _("Seller")),
    }

    if not r.ticket_id or r.ticket_id not in ctx["reg_tickets"]:
        regs_list_add(ctx, "list_tickets", "e", r.member)
    else:
        t = ctx["reg_tickets"][r.ticket_id]
        regs_list_add(ctx, "list_tickets", t.name, r.member)
        r.ticket_show = t.name

        if is_reg_provisional(r, ctx["features"]):
            typ = ("0", _("Provisional"))
        elif t.tier in ticket_types:
            typ = ticket_types[t.tier]

    if typ[0] not in ctx["reg_all"]:
        ctx["reg_all"][typ[0]] = {"count": 0, "type": typ[1], "list": []}

    ctx["reg_all"][typ[0]]["list"].append(r)
    ctx["reg_all"][typ[0]]["count"] += 1


def orga_registrations_membership(r, ctx):
    member = r.member
    if member.id in ctx["memberships"]:
        member.membership = ctx["memberships"][member.id]
    else:
        get_user_membership(member, ctx["a_id"])
    nm = member.membership.get_status_display()
    regs_list_add(ctx, "list_membership", nm, r.member)
    r.membership = member.membership.get_status_display


def regs_list_add(ctx, list, name, member):
    key = slugify(name)
    if list not in ctx:
        ctx[list] = {}
    if key not in ctx[list]:
        ctx[list][key] = {"name": name, "emails": [], "players": []}
    if member.email not in ctx[list][key]["emails"]:
        ctx[list][key]["emails"].append(member.email)
        ctx[list][key]["players"].append(member.display_member())


def _orga_registrations_standard(r, ctx, cache):
    regs_list_add(ctx, "list_all", "all", r.member)
    if r.member_id in ctx["reg_chars"]:
        r.factions = []
        r.chars = ctx["reg_chars"][r.member_id]
        for char in r.chars:
            if "factions" in char:
                r.factions.extend(char["factions"])
                for fnum in char["factions"]:
                    if fnum in ctx["factions"]:
                        regs_list_add(ctx, "list_factions", ctx["factions"][fnum]["name"], r.member)

            if "custom_character" in ctx["features"]:
                orga_registrations_custom(r, ctx, char)

        if "custom_character" in ctx["features"] and r.custom:
            for s in ctx["custom_info"]:
                if not r.custom[s]:
                    continue
                r.custom[s] = ", ".join(r.custom[s])

    # membership status
    if "membership" in ctx["features"]:
        orga_registrations_membership(r, ctx)

    # age at run
    if ctx["registration_reg_que_age"]:
        if r.member.birth_date and ctx["run"].start:
            r.age = calculate_age(r.member.birth_date, ctx["run"].start)


def orga_registrations_custom(r, ctx, char):
    if not hasattr(r, "custom"):
        r.custom = {}

    for s in ctx["custom_info"]:
        if s not in r.custom:
            r.custom[s] = []
        v = ""
        if s in char:
            v = char[s]
        if s == "profile" and v:
            v = f"<img src='{v}' class='reg_profile' />"
        if v:
            r.custom[s].append(v)


def registrations_popup(request, ctx):
    idx = int(request.POST.get("idx", ""))
    tp = request.POST.get("tp", "")

    try:
        reg = Registration.objects.get(pk=idx, run=ctx["run"])
        question = RegistrationQuestion.objects.get(pk=tp, event=ctx["event"].get_class_parent(RegistrationQuestion))
        el = RegistrationAnswer.objects.get(reg=reg, question=question)
        tx = f"<h2>{reg} - {question.display}</h2>" + el.text
        return JsonResponse({"k": 1, "v": tx})
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})


def _orga_registrations_custom_character(ctx):
    if "custom_character" not in ctx["features"]:
        return
    ctx["custom_info"] = []
    for field in ["pronoun", "song", "public", "private", "profile"]:
        if not ctx["event"].get_config("custom_character_" + field, False):
            continue
        ctx["custom_info"].append(field)


def _orga_registrations_prepare(ctx, request):
    ctx["reg_chars"] = {}
    for _chnum, char in ctx["chars"].items():
        if "player_id" not in char:
            continue
        if char["player_id"] not in ctx["reg_chars"]:
            ctx["reg_chars"][char["player_id"]] = []
        ctx["reg_chars"][char["player_id"]].append(char)
    ctx["reg_tickets"] = {}
    for t in RegistrationTicket.objects.filter(event=ctx["event"]).order_by("-price"):
        t.emails = []
        ctx["reg_tickets"][t.id] = t
    ctx["reg_questions"] = _get_registration_fields(ctx, request.user.member)


def _get_registration_fields(ctx, member):
    reg_questions = {}
    que = RegistrationQuestion.get_instance_questions(ctx["event"], ctx["features"])
    for q in que:
        if "reg_que_allowed" in ctx["features"] and q.allowed_map[0]:
            run_id = ctx["run"].id
            organizer = run_id in ctx["all_runs"] and 1 in ctx["all_runs"][run_id]
            if not organizer and member.id not in q.allowed_map:
                continue
        reg_questions[q.id] = q
    return reg_questions


def _orga_registrations_discount(ctx):
    if "discount" not in ctx["features"]:
        return
    ctx["reg_discounts"] = {}
    que = AccountingItemDiscount.objects.filter(run=ctx["run"])
    for aid in que.select_related("member", "disc").exclude(hide=True):
        regs_list_add(ctx, "list_discount", aid.disc.name, aid.member)
        if aid.member_id not in ctx["reg_discounts"]:
            ctx["reg_discounts"][aid.member_id] = []
        ctx["reg_discounts"][aid.member_id].append(aid.disc.name)


def _orga_registrations_text_fields(ctx):
    # add editor type questions
    text_fields = []
    que = RegistrationQuestion.objects.filter(event=ctx["event"])
    for que_id in que.filter(typ=QuestionType.EDITOR).values_list("pk", flat=True):
        text_fields.append(str(que_id))

    gctf = get_cache_reg_field(ctx["run"])
    for el in ctx["reg_list"]:
        if el.id not in gctf:
            continue
        for f in text_fields:
            if f not in gctf[el.id]:
                continue
            (red, ln) = gctf[el.id][f]
            setattr(el, f + "_red", red)
            setattr(el, f + "_ln", ln)


@login_required
def orga_registrations(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_registrations")

    if request.method == "POST":
        if request.POST.get("popup") == "1":
            return registrations_popup(request, ctx)

        if request.POST.get("download") == "1":
            return download(ctx, Registration, "registration")

        return upload_elements(request, ctx, Registration, "registration", "orga_registrations")

    cache = {}

    get_event_cache_all(ctx)

    _orga_registrations_prepare(ctx, request)

    _orga_registrations_discount(ctx)

    _orga_registrations_custom_character(ctx)

    ctx["registration_reg_que_age"] = ctx["event"].get_config("registration_reg_que_age", False)

    ctx["reg_all"] = {}

    que = Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True).order_by("-updated")
    ctx["reg_list"] = que.select_related("member")

    ctx["memberships"] = {}
    if "membership" in ctx["features"]:
        members_id = []
        for r in ctx["reg_list"]:
            members_id.append(r.member_id)
        for el in Membership.objects.filter(assoc_id=ctx["a_id"], member_id__in=members_id):
            ctx["memberships"][el.member_id] = el

    for r in ctx["reg_list"]:
        _orga_registrations_standard(r, ctx, cache)

        if "discount" in ctx["features"]:
            if r.member_id in ctx["reg_discounts"]:
                r.discounts = ctx["reg_discounts"][r.member_id]

        _orga_registrations_traits(r, ctx)

        _orga_registrations_tickets(r, ctx)

    ctx["reg_all"] = sorted(ctx["reg_all"].items())

    _orga_registrations_text_fields(ctx)

    ctx["typ"] = "registration"
    ctx["form"] = UploadElementsForm()

    ctx["upload"] = ",".join(
        [
            str(_("'player' (player's email)")),
            str(_("'ticket' (ticket name or number)")),
            str(_("'character' (character name or number to be assigned)")),
            str(_("'pwyw' (donation)")),
        ]
    )

    ctx["download"] = 1
    if ctx["event"].get_config("show_export", False):
        ctx["export"] = "registration"

    ctx["default_fields"] = request.user.member.get_config(f"open_registration_{ctx['event'].id}", "[]")

    return render(request, "larpmanager/orga/registration/registrations.html", ctx)


@login_required
def orga_registrations_accounting(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_registrations")

    res = _orga_registrations_acc(ctx)

    return JsonResponse(res)


@login_required
def orga_registration_form_list(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_registrations")

    eid = request.POST.get("num")

    q = RegistrationQuestion.objects
    if "reg_que_allowed" in ctx["features"]:
        q = q.annotate(allowed_map=ArrayAgg("allowed"))
    q = q.get(event=ctx["event"], pk=eid)

    if "reg_que_allowed" in ctx["features"] and q.allowed_map[0]:
        run_id = ctx["run"].id
        organizer = run_id in ctx["all_runs"] and 1 in ctx["all_runs"][run_id]
        if not organizer and request.user.member.id not in q.allowed_map:
            return

    res = {}
    popup = []

    max_length = 100

    if q.typ in [QuestionType.SINGLE, QuestionType.MULTIPLE]:
        cho = {}
        for opt in RegistrationOption.objects.filter(question=q):
            cho[opt.id] = opt.get_form_text()

        for el in RegistrationChoice.objects.filter(question=q, reg__run=ctx["run"]):
            if el.reg_id not in res:
                res[el.reg_id] = []
            res[el.reg_id].append(cho[el.option_id])

    elif q.typ in [QuestionType.TEXT, QuestionType.PARAGRAPH]:
        que = RegistrationAnswer.objects.filter(question=q, reg__run=ctx["run"])
        que = que.annotate(short_text=Substr("text", 1, max_length))
        que = que.values("reg_id", "short_text")
        for el in que:
            answer = el["short_text"]
            if len(answer) == max_length:
                popup.append(el["reg_id"])
            res[el["reg_id"]] = answer

    return JsonResponse({"res": res, "popup": popup, "num": q.id})


@login_required
def orga_registration_form_email(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_registrations")

    eid = request.POST.get("num")

    q = RegistrationQuestion.objects
    if "reg_que_allowed" in ctx["features"]:
        q = q.annotate(allowed_map=ArrayAgg("allowed"))
    q = q.get(event=ctx["event"], pk=eid)

    if "reg_que_allowed" in ctx["features"] and q.allowed_map[0]:
        run_id = ctx["run"].id
        organizer = run_id in ctx["all_runs"] and 1 in ctx["all_runs"][run_id]
        if not organizer and request.user.member.id not in q.allowed_map:
            return

    res = {}

    if q.typ not in [QuestionType.SINGLE, QuestionType.MULTIPLE]:
        return

    cho = {}
    for opt in RegistrationOption.objects.filter(question=q):
        cho[opt.id] = opt.display

    que = RegistrationChoice.objects.filter(question=q, reg__run=ctx["run"], reg__cancellation_date__isnull=True)
    for el in que.select_related("reg", "reg__member"):
        if el.option_id not in res:
            res[el.option_id] = {"emails": [], "names": []}
        res[el.option_id]["emails"].append(el.reg.member.email)
        res[el.option_id]["names"].append(el.reg.member.display_member())

    n_res = {}
    for opt_id, value in res.items():
        n_res[cho[opt_id]] = value

    return JsonResponse(n_res)


@login_required
def orga_registrations_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_registrations")
    get_event_cache_all(ctx)
    ctx["orga_characters"] = has_event_permission(ctx, request, ctx["event"].slug, "orga_characters")
    ctx["continue_add"] = "continue" in request.POST
    if num != 0:
        get_registration(ctx, num)
    if request.method == "POST":
        if num != 0:
            form = OrgaRegistrationForm(request.POST, instance=ctx["registration"], ctx=ctx, request=request)
        else:
            form = OrgaRegistrationForm(request.POST, ctx=ctx)
        if form.is_valid():
            reg = form.save()

            if "delete" in request.POST and request.POST["delete"] == "1":
                cancel_reg(reg)
                messages.success(request, _("Registration cancelled"))
                return redirect("orga_registrations", s=ctx["event"].slug, n=ctx["run"].number)

            # Registration questions
            form.save_reg_questions(reg)

            if "questbuilder" in ctx["features"]:
                _save_questbuilder(ctx, form, reg)

            if ctx["continue_add"]:
                return redirect("orga_registrations_edit", s=ctx["event"].slug, n=ctx["run"].number, num=0)

            return redirect("orga_registrations", s=ctx["event"].slug, n=ctx["run"].number)
    elif num != 0:
        form = OrgaRegistrationForm(instance=ctx["registration"], ctx=ctx)
    else:
        form = OrgaRegistrationForm(ctx=ctx)

    ctx["form"] = form
    ctx["add_another"] = 1

    return render(request, "larpmanager/orga/edit.html", ctx)


def _save_questbuilder(ctx, form, reg):
    for qt in QuestType.objects.filter(event=ctx["event"]):
        qt_id = f"qt_{qt.number}"
        tid = int(form.cleaned_data[qt_id])
        base_kwargs = {"run": ctx["run"], "member": reg.member, "typ": qt.number}

        if tid:
            ait = AssignmentTrait.objects.filter(**base_kwargs).first()

            if ait and ait.trait_id != tid:
                ait.delete()
                ait = None

            if not ait:
                AssignmentTrait.objects.create(**base_kwargs, trait_id=tid)
        else:
            AssignmentTrait.objects.filter(**base_kwargs).delete()


@login_required
def orga_registrations_customization(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_registrations")
    get_event_cache_all(ctx)
    get_char(ctx, num)
    rcr = RegistrationCharacterRel.objects.get(
        character_id=ctx["character"].id, reg__run_id=ctx["run"].id, reg__cancellation_date__isnull=True
    )

    if request.method == "POST":
        form = RegistrationCharacterRelForm(request.POST, ctx=ctx, instance=rcr)
        if form.is_valid():
            form.save()
            messages.success(request, _("Player customisation updated") + "!")
            return redirect("orga_registrations", s=ctx["event"].slug, n=ctx["run"].number)
    else:
        form = RegistrationCharacterRelForm(instance=rcr, ctx=ctx)

    ctx["form"] = form
    return render(request, "larpmanager/orga/edit.html", ctx)


@login_required
def orga_registrations_reload(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_registrations")
    reg_ids = []
    for reg in Registration.objects.filter(run=ctx["run"]):
        reg_ids.append(str(reg.id))
    check_reg_bkg(reg_ids)
    # print(f"@@@@ orga_registrations_reload {request} {datetime.now()}")
    return redirect("orga_registrations", s=ctx["event"].slug, n=ctx["run"].number)


@login_required
def orga_registration_discounts(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_registrations")
    get_registration(ctx, num)
    # get active discounts
    ctx["active"] = AccountingItemDiscount.objects.filter(run=ctx["run"], member=ctx["registration"].member)
    # get available discounts
    ctx["available"] = ctx["run"].discounts.all()
    return render(request, "larpmanager/orga/registration/discounts.html", ctx)


@login_required
def orga_registration_discount_add(request, s, n, num, dis):
    ctx = check_event_permission(request, s, n, "orga_registrations")
    get_registration(ctx, num)
    get_discount(ctx, dis)
    AccountingItemDiscount.objects.create(
        value=ctx["discount"].value,
        member=ctx["registration"].member,
        disc=ctx["discount"],
        run=ctx["run"],
        assoc_id=ctx["a_id"],
    )
    ctx["registration"].save()
    return redirect(
        "orga_registration_discounts",
        s=ctx["event"].slug,
        n=ctx["run"].number,
        num=ctx["registration"].id,
    )


@login_required
def orga_registration_discount_del(request, s, n, num, dis):
    ctx = check_event_permission(request, s, n, "orga_registrations")
    get_registration(ctx, num)
    AccountingItemDiscount.objects.get(pk=dis).delete()
    ctx["registration"].save()
    return redirect(
        "orga_registration_discounts",
        s=ctx["event"].slug,
        n=ctx["run"].number,
        num=ctx["registration"].id,
    )


@login_required
def orga_cancellations(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_cancellations")
    ctx["list"] = (
        Registration.objects.filter(run=ctx["run"])
        .exclude(cancellation_date__isnull=True)
        .order_by("-cancellation_date")
        .select_related("member")
    )
    regs_id = []
    members_map = {}
    for r in ctx["list"]:
        regs_id.append(r.id)
        members_map[r.member_id] = r.id

    payments = {}
    for el in AccountingItemPayment.objects.filter(member_id__in=members_map.keys(), reg__run=ctx["run"]):
        reg_id = members_map[el.member_id]
        if reg_id not in payments:
            payments[reg_id] = []
        payments[reg_id].append(el)

    refunds = {}
    for el in AccountingItemOther.objects.filter(run_id=ctx["run"].id, cancellation=True):
        reg_id = members_map[el.member_id]
        if reg_id not in refunds:
            refunds[reg_id] = []
        refunds[reg_id].append(el)

    # Check if payed, check if already approved reimburse
    for r in ctx["list"]:
        acc_payments = None
        if r.id in payments:
            acc_payments = payments[r.id]
        get_reg_payments(r, acc_payments)

        r.acc_refunds = None
        if r.id in refunds:
            r.acc_refunds = refunds[r.id]
        get_accounting_refund(r)

        r.days = get_time_diff(ctx["run"].end, r.cancellation_date.date())
    return render(request, "larpmanager/orga/accounting/cancellations.html", ctx)


@login_required
def orga_cancellation_refund(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_cancellations")
    get_registration(ctx, num)
    if request.method == "POST":
        ref_token = int(request.POST["inp_token"])
        ref_credit = int(request.POST["inp_credit"])

        if ref_token > 0:
            AccountingItemOther.objects.create(
                oth=AccountingItemOther.TOKEN,
                run=ctx["run"],
                descr="Refund",
                member=ctx["registration"].member,
                assoc_id=ctx["a_id"],
                value=ref_token,
                cancellation=True,
            )
        if ref_credit > 0:
            AccountingItemOther.objects.create(
                oth=AccountingItemOther.CREDIT,
                run=ctx["run"],
                descr="Refund",
                member=ctx["registration"].member,
                assoc_id=ctx["a_id"],
                value=ref_credit,
                cancellation=True,
            )

        ctx["registration"].refunded = True
        ctx["registration"].save()

        return redirect("orga_cancellations", s=ctx["event"].slug, n=ctx["run"].number)

    get_reg_payments(ctx["registration"])

    return render(request, "larpmanager/orga/accounting/cancellation_refund.html", ctx)


def get_pre_registration(event):
    dc = {"list": [], "pred": []}
    signed = set(Registration.objects.filter(run__event=event).values_list("member_id", flat=True))
    que = PreRegistration.objects.filter(event=event).order_by("pref", "created")
    for p in que.select_related("member"):
        if p.member_id not in signed:
            dc["pred"].append(p)
        else:
            p.signed = True

        dc["list"].append(p)
        if p.pref not in dc:
            dc[p.pref] = 0
        dc[p.pref] += 1
    return dc


@login_required
def orga_pre_registrations(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_pre_registrations")
    ctx["dc"] = get_pre_registration(ctx["event"])
    return render(request, "larpmanager/orga/registration/pre_registrations.html", ctx)


@login_required
def orga_reload_cache(request, s, n):
    ctx = check_event_permission(request, s, n)
    reset_run(ctx["run"])
    reset_cache_run(ctx["event"].assoc_id, ctx["event"].slug, ctx["run"].number)
    reset_event_features(ctx["event"].id)
    reset_run_event_links(ctx["event"])
    reset_cache_reg_counts(ctx["run"])
    messages.success(request, _("Cache reset!"))
    return redirect("manage", s=ctx["event"].slug, n=ctx["run"].number)


def lottery_info(request, ctx):
    ctx["num_draws"] = int(ctx["event"].get_config("lottery_num_draws", 0))
    ctx["ticket"] = ctx["event"].get_config("lottery_ticket", "")
    ctx["num_lottery"] = Registration.objects.filter(
        run=ctx["run"],
        ticket__tier=TicketTier.LOTTERY,
        cancellation_date__isnull=True,
    ).count()
    ctx["num_def"] = (
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.LOTTERY, TicketTier.STAFF, TicketTier.NPC, TicketTier.WAITING])
        .count()
    )


@login_required
def orga_lottery(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_lottery")

    if request.method == "POST" and request.POST.get("submit"):
        lottery_info(request, ctx)
        to_upgrade = ctx["num_draws"] - ctx["num_def"]
        if to_upgrade <= 0:
            raise Http404("already filled!")
        # do assignment
        regs = Registration.objects.filter(run=ctx["run"], ticket__tier=TicketTier.LOTTERY)
        regs = list(regs)
        shuffle(regs)
        chosen = regs[0:to_upgrade]
        ticket = get_object_or_404(RegistrationTicket, event=ctx["run"].event, display=ctx["ticket"])
        for el in chosen:
            el.ticket = ticket
            el.save()
            # send mail?
        ctx["chosen"] = chosen

    lottery_info(request, ctx)
    return render(request, "larpmanager/orga/registration/lottery.html", ctx)


def calculate_age(born, today):
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


@require_POST
def orga_registration_member(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_registrations")
    member_id = request.POST.get("mid")

    # check it's a member
    try:
        member = Member.objects.get(pk=member_id)
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    # check they have a registration it this event
    try:
        Registration.objects.filter(member=member, run=ctx["run"]).first()
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    text = f"<h2>{member.display_real()}</h2>"

    if member.profile:
        text += f"<img src='{member.profile_thumb.url}' style='width: 15em; margin: 1em; border-radius: 5%;' />"

    text += f"<p><b>Email</b>: {member.email}</p>"

    # check if the user can see sensitive data
    exclude = ["profile", "newsletter", "language", "presentation"]
    if not has_event_permission(ctx, request, s, "orga_sensitive"):
        exclude.extend(
            [
                "diet",
                "safety",
                "legal_name",
                "birth_date",
                "birth_place",
                "fiscal_code",
                "document_type",
                "document",
                "document_issued",
                "document_expiration",
                "accessibility",
                "residence_address",
            ]
        )

    member_cls: type[Member] = Member
    member_fields = sorted(request.assoc["members_fields"])
    member_field_correct(member, member_fields)
    for field_name in member_fields:
        if not field_name:
            continue

        if field_name in exclude:
            continue
        # noinspection PyUnresolvedReferences, PyProtectedMember
        field_label = member_cls._meta.get_field(field_name).verbose_name
        value = getattr(member, field_name)
        if not value:
            continue
        text += f"<p><b>{field_label}</b>: {value}</p>"

    return JsonResponse({"k": 1, "v": text})
