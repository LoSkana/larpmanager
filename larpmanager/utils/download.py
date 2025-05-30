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

from larpmanager.cache.character import get_event_cache_all
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
from larpmanager.models.registration import RegistrationCharacterRel
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

    return key, vals


def _prepare_export(ctx, model, query):
    # noinspection PyProtectedMember
    applicable = QuestionApplicable.get_applicable(model)
    choices = {}
    answers = {}
    questions = []
    if applicable or model == "registration":
        question_cls = RegistrationQuestion
        choices_cls = RegistrationChoice
        answers_cls = RegistrationAnswer
        ref_field = "reg_id"
        if model != "registration":
            question_cls = WritingQuestion
            choices_cls = WritingChoice
            answers_cls = WritingAnswer
            ref_field = "element_id"

        el_ids = {el.id for el in query}

        questions = question_cls.objects.filter(event=ctx["event"]).order_by("order")
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
            display = member.display_member()
        val.append(display)
    if model == "registration":
        val.extend([el.member.email, el.ticket.name])
        key.extend([_("Email"), _("Ticket")])
    else:
        val.extend([el.number])
        key.extend(["number"])


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
        query = query.select_related("ticket")

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
