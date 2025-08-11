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
import io
import zipfile

import pandas as pd
from bs4 import BeautifulSoup
from django.db.models import F
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.registration import round_to_nearest_cent
from larpmanager.cache.character import get_event_cache_all
from larpmanager.models.accounting import AccountingItemPayment
from larpmanager.models.form import (
    QuestionApplicable,
    QuestionStatus,
    QuestionType,
    QuestionVisibility,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
    get_ordered_registration_questions,
)
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket
from larpmanager.models.writing import Character, Plot, PlotCharacterRel, Relationship
from larpmanager.utils.common import check_field
from larpmanager.utils.edit import _get_values_mapping


def _temp_csv_file(keys, vals):
    df = pd.DataFrame(vals, columns=keys)
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return buffer.getvalue()


def zip_exports(ctx, exports, filename):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for name, key, vals in exports:
            if not key or not vals:
                continue
            zip_file.writestr(f"{name}.csv", _temp_csv_file(key, vals))
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = f"attachment; filename={str(ctx['run'])} - {filename}.zip"
    return response


def download(ctx, typ, nm):
    exports = export_data(ctx, typ)
    return zip_exports(ctx, exports, nm.capitalize())


def export_data(ctx, typ, member_cover=False):
    query = typ.objects.all()
    get_event_cache_all(ctx)
    model = typ.__name__.lower()
    query = _download_prepare(ctx, model, query, typ)

    _prepare_export(ctx, model, query)

    key = None
    vals = []
    for el in query:
        if ctx["applicable"] or model == "registration":
            val, key = _get_applicable_row(ctx, el, model, member_cover)
        else:
            val, key = _get_standard_row(ctx, el)
        vals.append(val)

    order_column = 0
    if member_cover:
        order_column = 1
    vals = sorted(vals, key=lambda x: x[order_column])

    exports = [(model, key, vals)]

    # if plots, add rels
    if model == "plot":
        exports.extend(export_plot_rels(ctx))

    # if character, add relationships
    if model == "character":
        if "relationships" in ctx["features"]:
            exports.extend(export_relationships(ctx))

    return exports


def export_plot_rels(ctx):
    keys = ["plot", "character", "text"]
    vals = []

    event_id = ctx["event"].get_class_parent(Plot)

    for rel in PlotCharacterRel.objects.filter(plot__event_id=event_id).prefetch_related("plot", "character"):
        vals.append([rel.plot.name, rel.character.name, rel.text])

    return [("plot_rels", keys, vals)]


def export_relationships(ctx):
    keys = ["source", "target", "text"]
    vals = []

    event_id = ctx["event"].get_class_parent(Character)

    for rel in Relationship.objects.filter(source__event_id=event_id).prefetch_related("source", "target"):
        vals.append([rel.source.name, rel.target.name, rel.text])

    return [("relationships", keys, vals)]


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
            choices[choice.question_id][element_id].append(choice.option.name)

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

    ctx["applicable"] = applicable
    ctx["answers"] = answers
    ctx["choices"] = choices
    ctx["questions"] = questions


def _get_applicable_row(ctx, el, model, member_cover=False):
    val = []
    key = []

    _row_header(ctx, el, key, member_cover, model, val)

    if ctx["applicable"] == QuestionApplicable.QUEST:
        key.append("typ")
        val.append(el.typ.name)
    elif ctx["applicable"] == QuestionApplicable.TRAIT:
        key.append("quest")
        val.append(el.quest.name)

    answers = ctx["answers"]
    choices = ctx["choices"]

    # add question values
    for que in ctx["questions"]:
        key.append(que.name)
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
        key.append(_("Participant"))
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


def _expand_val(val, el, field):
    if hasattr(el, field):
        value = getattr(el, field)
        if value:
            val.append(value)
            return

    val.append("")


def _header_regs(ctx, el, key, val):
    if "character" in ctx["features"]:
        key.append(_("Characters"))
        val.append(", ".join([row.character.name for row in el.rcrs.all()]))

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
        _expand_val(val, el, "pay_a")
        key.append(_("Money"))

        _expand_val(val, el, "pay_b")
        key.append(ctx.get("credit_name", _("Credits")))

        _expand_val(val, el, "pay_c")
        key.append(ctx.get("token_name", _("Credits")))


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

    clean = _clean(new_val)
    val.append(clean)
    key.append(k)


def _clean(new_val):
    soup = BeautifulSoup(str(new_val), features="lxml")
    clean = soup.get_text("\n").replace("\n", " ")
    return clean


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


def orga_registration_form_download(ctx):
    return zip_exports(ctx, export_registration_form(ctx), "Registration form")


def export_registration_form(ctx):
    mappings = {
        "typ": QuestionType.get_mapping(),
        "status": QuestionStatus.get_mapping(),
    }

    ctx["typ"] = "registration_form"
    _get_column_names(ctx)
    key = ctx["columns"][0].keys()
    que = get_ordered_registration_questions(ctx)
    vals = _extract_values(key, que, mappings)

    exports = [("registration_questions", key, vals)]

    key = list(ctx["columns"][1].keys())
    new_key = key.copy()
    new_key[0] = f"{new_key[0]}__name"
    que = ctx["event"].get_elements(RegistrationOption).select_related("question")
    que = que.order_by(F("question__order"), "order")
    vals = _extract_values(new_key, que, mappings)

    exports.append(("registration_options", key, vals))
    return exports


def _extract_values(key, que, mappings):
    all_vals = []
    for row in que.values(*key):
        vals = []
        for field, value in row.items():
            if field in mappings and value in mappings[field]:
                new_value = mappings[field][value]
            else:
                new_value = value
            vals.append(new_value)
        all_vals.append(vals)
    return all_vals


def orga_character_form_download(ctx):
    return zip_exports(ctx, export_character_form(ctx), "Character form")


def export_character_form(ctx):
    mappings = {
        "typ": QuestionType.get_mapping(),
        "status": QuestionStatus.get_mapping(),
        "applicable": QuestionApplicable.get_mapping(),
        "visibility": QuestionVisibility.get_mapping(),
    }
    ctx["typ"] = "character_form"
    _get_column_names(ctx)
    key = ctx["columns"][0].keys()
    que = ctx["event"].get_elements(WritingQuestion).order_by("applicable", "order")
    vals = _extract_values(key, que, mappings)

    exports = [("writing_questions", key, vals)]

    key = list(ctx["columns"][1].keys())
    new_key = key.copy()
    new_key[0] = f"{new_key[0]}__name"
    que = ctx["event"].get_elements(WritingOption).select_related("question")
    que = que.order_by(F("question__order"), "order")
    vals = _extract_values(new_key, que, mappings)

    exports.append(("writing_options", key, vals))
    return exports


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


def _get_column_names(ctx):
    if ctx["typ"] == "registration":
        ctx["columns"] = [
            {
                "player": _("The participant's email"),
                "ticket": _("The name of the ticket")
                + " <i>("
                + (_("if it doesn't exist, it will be created"))
                + ")</i>",
                "character": _("(Optional) The character name to assign to the player"),
                "donation": _("(Optional) The amount of a voluntary donation"),
            }
        ]
        que = get_ordered_registration_questions(ctx).values("name", "typ")
        ctx["fields"] = {el["name"]: el["typ"] for el in que}
        if "pay_what_you_want" not in ctx["features"]:
            del ctx["columns"][0]["donation"]

    elif ctx["typ"] == "registration_form":
        ctx["columns"] = [
            {
                "name": _("The question name"),
                "typ": _("The question type, allowed values are")
                + ": 'single-choice', 'multi-choice', 'short-text', 'long-text', 'advanced'",
                "description": _("Optional - Extended description (displayed in small gray text)"),
                "status": _("The question status, allowed values are")
                + ": 'optional', 'mandatory', 'disabled', 'hidden'",
                "max_length": _(
                    "Optional - For text questions, maximum number of characters; For multiple options, maximum number of options (0 = no limit)"
                ),
            },
            {
                "question": _("The name of the question this option belongs to")
                + " <i>("
                + (_("If not found, the option will be skipped"))
                + ")</i>",
                "name": _("The name of the option"),
                "description": _("Optional – Additional information about the option, displayed below the question"),
                "price": _("Optional – Amount added to the registration fee if selected (0 = no extra cost)"),
                "max_available": _(
                    "Optional – Maximum number of times it can be selected across all registrations (0 = unlimited)"
                ),
            },
        ]
    elif ctx["typ"] == "character_form":
        ctx["columns"] = [
            {
                "name": _("The question name"),
                "typ": _("The question type, allowed values are")
                + ": 'single-choice', 'multi-choice', 'short-text', 'long-text', 'advanced', 'name', 'teaser', 'text'",
                "description": _("Optional - Extended description (displayed in small gray text)"),
                "status": _("The question status, allowed values are")
                + ": 'optional', 'mandatory', 'disabled', 'hidden'",
                "applicable": _("The writing element this question applies to, allowed values are")
                + ": 'character', 'plot', 'faction', 'quest', 'trait'",
                "visibility": _("The question visibility to participants, allowed values are")
                + ": 'searchable', 'public', 'private', 'hidden'",
                "max_length": _(
                    "Optional - For text questions, maximum number of characters; For multiple options, maximum number of options (0 = no limit)"
                ),
            },
            {
                "question": _("The name of the question this option belongs to")
                + " <i>("
                + (_("If not found, the option will be skipped"))
                + ")</i>",
                "name": _("The name of the option"),
                "description": _("Optional – Additional information about the option, displayed below the question"),
                "max_available": _("Optional – Maximum number of times it can be selected (0 = unlimited)"),
            },
        ]

    else:
        _get_writing_names(ctx)


def _get_writing_names(ctx):
    ctx["writing_typ"] = QuestionApplicable.get_applicable(ctx["typ"])
    ctx["fields"] = {}
    que = ctx["event"].get_elements(WritingQuestion).filter(applicable=ctx["writing_typ"])
    for field in que.order_by("order").values("name", "typ"):
        ctx["fields"][field["name"]] = field["typ"]
        if field["typ"] == "name":
            ctx["field_name"] = field["name"]

    ctx["columns"] = [{}]
    if ctx["writing_typ"] == QuestionApplicable.CHARACTER:
        if "relationships" in ctx["features"]:
            ctx["columns"].append(
                {
                    "source": _("First character in the relationship (origin)"),
                    "target": _("Second character in the relationship (destination)"),
                    "text": _("Description of the relationship from source to target"),
                }
            )

    elif ctx["writing_typ"] == QuestionApplicable.PLOT:
        ctx["columns"].append(
            {
                "plot": _("Name of the plot"),
                "character": _("Name of the character"),
                "text": _("Description of the role of the character in the plot"),
            }
        )

    elif ctx["writing_typ"] == QuestionApplicable.QUEST:
        ctx["columns"][0]["typ"] = _("Name of quest type")

    elif ctx["writing_typ"] == QuestionApplicable.TRAIT:
        ctx["columns"][0]["quest"] = _("Name of quest")

    ctx["allowed"] = list(ctx["columns"][0].keys())
    ctx["allowed"].extend(ctx["fields"].keys())
