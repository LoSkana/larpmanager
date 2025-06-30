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

import csv

from bs4 import BeautifulSoup
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.registration import round_to_nearest_cent
from larpmanager.cache.character import get_event_cache_all
from larpmanager.models.accounting import AccountingItemPayment
from larpmanager.models.form import (
    QuestionApplicable,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationQuestion,
    WritingAnswer,
    WritingChoice,
    WritingQuestion,
    get_ordered_registration_questions,
)
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket
from larpmanager.utils.common import check_field
from larpmanager.utils.edit import _get_values_mapping


def download(ctx, typ, model):
    response, writer = get_writer(ctx, model)

    key, vals = _export_data(ctx, model, typ)

    writer.writerow(key)
    for val in vals:
        writer.writerow(val)

    return response


def _export_data(ctx, model, typ, member_cover=False):
    query = typ.objects.all()
    get_event_cache_all(ctx)
    query = _download_prepare(ctx, model, query, typ)

    answers, applicable, choices, questions = _prepare_export(ctx, model, query)

    key = None
    vals = []
    for el in query:
        if applicable or model == "registration":
            val, key = _get_applicable_row(ctx, el, choices, answers, questions, model, member_cover)
        else:
            val, key = _get_standard_row(ctx, el)
        vals.append(val)

    order_column = 0
    if member_cover:
        order_column = 1
    vals = sorted(vals, key=lambda x: x[order_column])

    return key, vals


def _prepare_export(ctx, model, query):
    # noinspection PyProtectedMember
    applicable = QuestionApplicable.get_applicable(model)
    choices = {}
    answers = {}
    questions = []
    if applicable or model == "registration":
        is_reg = model == "registration"
        question_cls = RegistrationQuestion if is_reg else WritingQuestion
        choices_cls = RegistrationChoice if is_reg else WritingChoice
        answers_cls = RegistrationAnswer if is_reg else WritingAnswer
        ref_field = "reg_id" if is_reg else "element_id"

        el_ids = {el.id for el in query}

        questions = question_cls.get_instance_questions(ctx["event"], ctx["features"])
        if model != "registration":
            questions = questions.filter(applicable=applicable)

        que_ids = {que.id for que in questions}

        filter_kwargs = {"question_id__in": que_ids, f"{ref_field}__in": el_ids}

        que_choice = choices_cls.objects.filter(**filter_kwargs)
        for choice in que_choice.select_related("option"):
            element_id = getattr(choice, ref_field)
            if choice.question_id not in choices:
                choices[choice.question_id] = {}
            if element_id not in choices[choice.question_id]:
                choices[choice.question_id][element_id] = []
            choices[choice.question_id][element_id].append(choice.option.display)

        que_answer = answers_cls.objects.filter(**filter_kwargs)
        for answer in que_answer:
            element_id = getattr(answer, ref_field)
            if answer.question_id not in answers:
                answers[answer.question_id] = {}
            answers[answer.question_id][element_id] = answer.text

    if model == "character":
        ctx["assignments"] = {}
        for rcr in RegistrationCharacterRel.objects.filter(reg__run=ctx["run"]).select_related("reg", "reg__member"):
            ctx["assignments"][rcr.character.id] = rcr.reg.member

    return answers, applicable, choices, questions


def _get_applicable_row(ctx, el, choices, answers, questions, model, member_cover=False):
    val = []
    key = []

    _row_header(ctx, el, key, member_cover, model, val)

    # add question values
    for que in questions:
        key.append(que.display)
        mapping = _get_values_mapping(el)
        value = ""
        if que.typ in mapping:
            value = mapping[que.typ]()
        elif que.typ in {"p", "t", "e"}:
            if que.id in answers and el.id in answers[que.id]:
                value = answers[que.id][el.id]
        elif que.typ in {"s", "m"}:
            if que.id in choices and el.id in choices[que.id]:
                value = ", ".join(choices[que.id][el.id])
        value = value.replace("\t", "").replace("\n", "<br />")
        val.append(value)

    return val, key


def _row_header(ctx, el, key, member_cover, model, val):
    member = None
    if model == "registration":
        member = el.member
    elif model == "character":
        if el.id in ctx["assignments"]:
            member = ctx["assignments"][el.id]

    if member_cover:
        key.append("")
        profile = ""
        if member and member.profile:
            profile = member.profile_thumb.url
        val.append(profile)

    if model in ["registration", "character"]:
        key.append(_("Player"))
        display = ""
        if member:
            display = member.display_real()
        val.append(display)

        key.append(_("Email"))
        email = ""
        if member:
            email = member.email
        val.append(email)

    if model == "registration":
        val.append(el.ticket.name)
        key.append(_("Ticket"))

        _header_regs(ctx, el, key, val)

    else:
        val.append(el.number)
        key.append("number")


def _expand_val(val, field):
    if hasattr(val, field):
        value = getattr(val, field)
        if value:
            val.append(value)
            return

    val.append("")


def _header_regs(ctx, el, key, val):
    if "pay_what_you_want" in ctx["features"]:
        val.append(el.pay_what)
        key.append("PWYW")

    if "surcharge" in ctx["features"]:
        val.append(el.surcharge)
        key.append(_("Surcharge"))

    if "reg_quotas" in ctx["features"] or "reg_installments" in ctx["features"]:
        val.append(el.quota)
        key.append(_("Next quota"))

    val.append(el.deadline)
    key.append(_("Deadline"))

    val.append(el.remaining)
    key.append(_("Owing"))

    val.append(el.tot_payed)
    key.append(_("Payed"))

    val.append(el.tot_iscr)
    key.append(_("Total"))

    if "vat" in ctx["features"]:
        val.append(el.ticket_price)
        key.append(_("Ticket"))

        val.append(el.options_price)
        key.append(_("Options"))

    if "token_credit" in ctx["features"]:
        _expand_val(val, "pay_a")
        key.append(_("Money"))

        _expand_val(val, "pay_b")
        key.append(ctx["credit_name"])

        _expand_val(val, "pay_c")
        key.append(ctx["token_name"])


def _get_standard_row(ctx, el):
    val = []
    key = []
    for k, v in el.show_complete().items():
        _writing_field(ctx, k, key, v, val)

    return val, key


def _writing_field(ctx, k, key, v, val):
    new_val = v
    skip_fields = [
        "id",
        "show",
        "owner_id",
        "owner",
        "player",
        "player_full",
        "player_id",
        "first_aid",
        "player_prof",
        "profile",
        "cover",
        "thumb",
    ]
    if k in skip_fields:
        return

    if k.startswith("custom_"):
        return

    if k in ["title"]:
        if k not in ctx["features"]:
            return

    if k == "factions":
        if "faction" not in ctx["features"]:
            return

        aux = [ctx["factions"][int(el)]["name"] for el in v]
        new_val = ", ".join(aux)

    soup = BeautifulSoup(str(new_val), features="lxml")
    val.append(soup.get_text("\n").replace("\n", " "))
    key.append(k)


def _download_prepare(ctx, nm, query, typ):
    if check_field(typ, "event"):
        query = query.filter(event=ctx["event"])

    elif check_field(typ, "run"):
        query = query.filter(run=ctx["run"])

    if check_field(typ, "number"):
        query = query.order_by("number")

    if nm == "character":
        query = query.prefetch_related("factions_list").select_related("player")

    if nm == "registration":
        query = query.filter(cancellation_date__isnull=True).select_related("ticket")
        resp = _orga_registrations_acc(ctx, query)
        for el in query:
            if el.id not in resp:
                continue
            for key, value in resp[el.id].items():
                setattr(el, key, value)

    return query


def get_writer(ctx, nm):
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="{}-{}.csv"'.format(ctx["event"], nm)},
    )
    writer = csv.writer(response, delimiter="\t")
    return response, writer


def orga_registration_form_download(request, ctx):
    response, writer = get_writer(ctx, "Registration form")
    writer.writerow(["typ", "display", "description", "status", "options"])

    que = get_ordered_registration_questions(ctx)
    for el in que:
        options = el.options.all()
        row = [el.typ, el.display, el.description, el.status, len(options)]
        for opt in options:
            row.extend([opt.display, opt.details, opt.price, opt.max_available])
        writer.writerow(row)

    return response


def orga_character_form_download(request, ctx):
    response, writer = get_writer(ctx, "Registration form")
    writer.writerow(["typ", "display", "description", "status", "visibility", "options"])

    que = ctx["event"].get_elements(WritingQuestion).order_by("order")
    que = que.filter(applicable=QuestionApplicable.CHARACTER)
    for el in que.prefetch_related("options"):
        options = el.options.order_by("order")
        row = [el.typ, el.display, el.description, el.status, el.visibility, len(options)]
        for opt in options:
            dependents = ",".join(opt.dependents.values_list("display", flat=True))
            tickets = ",".join(opt.tickets.values_list("name", flat=True))
            row.extend([opt.display, opt.details, opt.max_available, dependents, tickets])
        writer.writerow(row)

    return response


def _orga_registrations_acc(ctx, regs=None):
    ctx["reg_tickets"] = {}
    for t in RegistrationTicket.objects.filter(event=ctx["event"]).order_by("-price"):
        t.emails = []
        ctx["reg_tickets"][t.id] = t

    cache_aip = {}
    if "token_credit" in ctx["features"]:
        que = AccountingItemPayment.objects.filter(reg__run=ctx["run"])
        que = que.filter(pay__in=[AccountingItemPayment.TOKEN, AccountingItemPayment.CREDIT])
        for el in que.exclude(hide=True).values_list("member_id", "value", "pay"):
            if el[0] not in cache_aip:
                cache_aip[el[0]] = {"total": 0}
            cache_aip[el[0]]["total"] += el[1]
            if el[2] not in cache_aip[el[0]]:
                cache_aip[el[0]][el[2]] = 0
            cache_aip[el[0]][el[2]] += el[1]

    if not regs:
        regs = Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
    res = {}
    for r in regs:
        dt = _orga_registrations_acc_reg(r, ctx, cache_aip)
        res[r.id] = {key: f"{value:g}" for key, value in dt.items()}

    return res


def _orga_registrations_acc_reg(reg, ctx, cache_aip):
    dt = {}

    max_rounding = 0.05

    for k in ["tot_payed", "tot_iscr", "quota", "deadline", "pay_what", "surcharge"]:
        dt[k] = round_to_nearest_cent(getattr(reg, k, 0))

    if "token_credit" in ctx["features"]:
        if reg.member_id in cache_aip:
            for pay in ["b", "c"]:
                v = 0
                if pay in cache_aip[reg.member_id]:
                    v = cache_aip[reg.member_id][pay]
                dt["pay_" + pay] = float(v)
            dt["pay_a"] = dt["tot_payed"] - (dt["pay_b"] + dt["pay_c"])
        else:
            dt["pay_a"] = dt["tot_payed"]

    dt["remaining"] = dt["tot_iscr"] - dt["tot_payed"]
    if abs(dt["remaining"]) < max_rounding:
        dt["remaining"] = 0

    if reg.ticket_id in ctx["reg_tickets"]:
        t = ctx["reg_tickets"][reg.ticket_id]
        dt["ticket_price"] = t.price
        if reg.pay_what:
            dt["ticket_price"] += reg.pay_what
        dt["options_price"] = reg.tot_iscr - dt["ticket_price"]

    return dt
