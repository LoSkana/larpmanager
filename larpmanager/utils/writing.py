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
import json

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Model, Prefetch
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_all, get_writing_element_fields
from larpmanager.cache.text_fields import get_cache_text_field
from larpmanager.models.access import get_event_staffers
from larpmanager.models.casting import Quest, Trait
from larpmanager.models.event import ProgressStep
from larpmanager.models.experience import AbilityPx
from larpmanager.models.form import QuestionApplicable, QuestionType, WritingAnswer, WritingQuestion
from larpmanager.models.writing import (
    Character,
    CharacterConfig,
    Plot,
    PlotCharacterRel,
    Relationship,
    TextVersion,
    Writing,
    replace_chars_all,
)
from larpmanager.templatetags.show_tags import show_char, show_trait
from larpmanager.utils.character import get_character_sheet
from larpmanager.utils.common import check_field, compute_diff
from larpmanager.utils.download import download
from larpmanager.utils.edit import _setup_char_finder


def orga_list_progress_assign(ctx, typ: type[Model]):
    features = ctx["features"]
    event = ctx["event"]

    if "progress" in features:
        ctx["progress_steps"] = {el.id: str(el) for el in ProgressStep.objects.filter(event=event).order_by("order")}
        ctx["progress_steps_map"] = {el_id: 0 for el_id in ctx["progress_steps"]}

    if "assigned" in features:
        ctx["assigned"] = {m.id: m.show_nick() for m in get_event_staffers(event)}
        ctx["assigned_map"] = {m_id: 0 for m_id in ctx["assigned"]}

    if "progress" in features and "assigned" in features:
        ctx["progress_assigned_map"] = {f"{p}_{a}": 0 for p in ctx["progress_steps"] for a in ctx["assigned"]}

    for el in ctx["list"]:
        pid = el.progress_id
        aid = el.assigned_id

        if "progress" in features and pid in ctx.get("progress_steps_map", {}):
            ctx["progress_steps_map"][pid] += 1

        if "assigned" in features and aid in ctx.get("assigned_map", {}):
            ctx["assigned_map"][aid] += 1

        if "progress" in features and "assigned" in features:
            key = f"{pid}_{aid}"
            if key in ctx.get("progress_assigned_map", {}):
                ctx["progress_assigned_map"][key] += 1

    ctx["typ"] = str(typ._meta).replace("larpmanager.", "")  # type: ignore[attr-defined]


def writing_popup_question(ctx, idx, question_idx):
    try:
        char = Character.objects.get(pk=idx, event=ctx["event"].get_class_parent(Character))
        question = WritingQuestion.objects.get(pk=question_idx, event=ctx["event"].get_class_parent(WritingQuestion))
        el = WritingAnswer.objects.get(element_id=char.id, question=question)
        tx = f"<h2>{char} - {question.name}</h2>" + el.text
        return JsonResponse({"k": 1, "v": tx})
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})


def writing_popup(request, ctx, typ):
    get_event_cache_all(ctx)

    idx = int(request.POST.get("idx", ""))
    tp = request.POST.get("tp", "")

    # check if it is a character question
    try:
        question_idx = int(tp)
        return writing_popup_question(ctx, idx, question_idx)
    except ValueError:
        pass

    try:
        el = typ.objects.get(pk=idx, event=ctx["event"].get_class_parent(typ))
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    if not hasattr(el, tp):
        return JsonResponse({"k": 0})

    tx = f"<h2>{el} - {tp}</h2>"
    if typ in [Trait, Quest]:
        tx += show_trait(ctx, getattr(el, tp), ctx["run"], 1)
    else:
        tx += show_char(ctx, getattr(el, tp), ctx["run"], 1)

    return JsonResponse({"k": 1, "v": tx})


def writing_example(ctx, typ):
    file_rows = typ.get_example_csv(ctx["features"])

    buffer = io.StringIO()
    wr = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    wr.writerows(file_rows)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=example.csv"

    return response


def writing_post(request, ctx, typ, nm):
    if request.POST.get("download") == "1":
        return download(ctx, typ, nm)

    if request.POST.get("example") == "1":
        return writing_example(ctx, typ)

    if request.POST.get("popup") == "1":
        return writing_popup(request, ctx, typ)

    return None


def writing_list(request, ctx, typ, nm):
    if request.method == "POST":
        return writing_post(request, ctx, typ, nm)

    ev = ctx["event"]

    ctx["nm"] = nm

    text_fields, writing = writing_list_query(ctx, ev, typ)

    if issubclass(typ, Character):
        writing_list_char(ctx, ev, text_fields)

    if issubclass(typ, Plot):
        writing_list_plot(ctx)

    if issubclass(typ, AbilityPx):
        ctx["list"] = ctx["list"].prefetch_related("prerequisites")

    if writing:
        # noinspection PyProtectedMember, PyUnresolvedReferences
        ctx["label_typ"] = typ._meta.model_name
        ctx["writing_typ"] = QuestionApplicable.get_applicable(ctx["label_typ"])
        if ctx["writing_typ"]:
            ctx["upload"] = f"{nm}s"
        orga_list_progress_assign(ctx, typ)  # pyright: ignore[reportArgumentType]
        writing_list_text_fields(ctx, text_fields, typ)
        _prepare_writing_list(ctx, request)
        _setup_char_finder(ctx)
        _get_custom_form(ctx)

    return render(request, "larpmanager/orga/writing/" + nm + "s.html", ctx)


def _get_custom_form(ctx):
    if not ctx["writing_typ"]:
        return

    # default name for fields
    ctx["fields_name"] = {QuestionType.NAME.value: _("Name")}

    que = ctx["event"].get_elements(WritingQuestion).order_by("order")
    que = que.filter(applicable=ctx["writing_typ"])
    ctx["form_questions"] = {}
    for q in que:
        q.basic_typ = q.typ in QuestionType.get_basic_types()
        if q.typ in ctx["fields_name"].keys():
            ctx["fields_name"][q.typ] = q.name
        else:
            ctx["form_questions"][q.id] = q


def writing_list_query(ctx, ev, typ):
    writing = issubclass(typ, Writing)
    text_fields = ["teaser", "text"]
    ctx["list"] = typ.objects.filter(event=ev.get_class_parent(typ))
    if writing:
        for f in text_fields:
            ctx["list"] = ctx["list"].defer(f)
    # noinspection PyProtectedMember
    typ_fields = [f.name for f in typ._meta.get_fields()]
    for el in [
        ("faction", "factions_list"),
        ("prologue", "prologues_list"),
        ("speedlarp", "speedlarps_list"),
        ("", "characters"),
    ]:
        if el[0] and el[0] not in ctx["features"]:
            continue

        if el[1] not in typ_fields:
            continue

        ctx["list"] = ctx["list"].prefetch_related(el[1])
    if check_field(typ, "order"):
        ctx["list"] = ctx["list"].order_by("order")
    elif check_field(typ, "number"):
        ctx["list"] = ctx["list"].order_by("number")
    else:
        ctx["list"] = ctx["list"].order_by("-updated")
    return text_fields, writing


def writing_list_text_fields(ctx, text_fields, typ):
    # add editor type questions
    que = ctx["event"].get_elements(WritingQuestion).filter(applicable=ctx["writing_typ"])
    for que_id in que.filter(typ=QuestionType.EDITOR).values_list("pk", flat=True):
        text_fields.append(str(que_id))

    retrieve_cache_text_field(ctx, text_fields, typ)


def retrieve_cache_text_field(ctx, text_fields, typ):
    gctf = get_cache_text_field(typ, ctx["event"])
    for el in ctx["list"]:
        if el.id not in gctf:
            continue
        for f in text_fields:
            if f not in gctf[el.id]:
                continue
            (red, ln) = gctf[el.id][f]
            setattr(el, f + "_red", red)
            setattr(el, f + "_ln", ln)


def _prepare_writing_list(ctx, request):
    try:
        name_que = (
            ctx["event"].get_elements(WritingQuestion).filter(applicable=ctx["writing_typ"], typ=QuestionType.NAME)
        )
        ctx["name_que_id"] = name_que.values_list("id", flat=True)[0]
    except Exception:
        pass

    model_name = ctx["label_typ"].lower()
    ctx["default_fields"] = request.user.member.get_config(f"open_{model_name}_{ctx['event'].id}", "[]")
    if ctx["default_fields"] == "[]":
        if model_name in ctx["writing_fields"]:
            lst = [f"q_{el}" for name, el in ctx["writing_fields"][model_name]["ids"].items()]
            ctx["default_fields"] = json.dumps(lst)

    ctx["auto_save"] = not ctx["event"].get_config("writing_disable_auto", False)


def writing_list_plot(ctx):
    ctx["chars"] = {}
    for el in PlotCharacterRel.objects.filter(character__event=ctx["event"]).select_related("plot", "character"):
        if el.plot.number not in ctx["chars"]:
            ctx["chars"][el.plot.number] = []
        ctx["chars"][el.plot.number].append((f"#{el.character.number} {el.character.name}", el.character.id))
    for el in ctx["list"]:
        if el.number in ctx["chars"]:
            el.chars = ctx["chars"][el.number]


def writing_list_char(ctx, ev, text_fields):
    if "user_character" in ctx["features"]:
        ctx["list"] = ctx["list"].select_related("player")

    if "relationships" in ctx["features"]:
        ctx["list"] = ctx["list"].prefetch_related(
            Prefetch("source", queryset=Relationship.objects.filter(deleted=None))
        )

    if "plot" in ctx["features"]:
        ctx["plots"] = {}
        for el in PlotCharacterRel.objects.filter(character__event=ctx["event"]).select_related("plot", "character"):
            if el.character.number not in ctx["plots"]:
                ctx["plots"][el.character.number] = []
            ctx["plots"][el.character.number].append((f"[T{el.plot.number}] {el.plot.name}", el.plot.id))

        for el in ctx["list"]:
            if el.number in ctx["plots"]:
                el.plts = ctx["plots"][el.number]

    if "faction" in ctx["features"]:
        fac_event = ctx["event"].get_class_parent("faction")
        for el in ctx["list"]:
            el.factions = el.factions_list.filter(event=fac_event)

    # add character configs
    char_add_addit(ctx)


def char_add_addit(ctx):
    addits = {}
    event = ctx["event"].get_class_parent(Character)
    for config in CharacterConfig.objects.filter(character__event=event):
        if config.character_id not in addits:
            addits[config.character_id] = {}
        addits[config.character_id][config.name] = config.value

    for el in ctx["list"]:
        if el.id in addits:
            el.addit = addits[el.id]
        else:
            el.addit = {}


def writing_view(request, ctx, nm):
    ctx["el"] = ctx[nm]
    ctx["el"].data = ctx["el"].show_complete()
    ctx["nm"] = nm
    get_event_cache_all(ctx)

    if nm == "character":
        if ctx["el"].number in ctx["chars"]:
            ctx["char"] = ctx["chars"][ctx["el"].number]
        ctx["character"] = ctx["el"]
        get_character_sheet(ctx)
    else:
        applicable = QuestionApplicable.get_applicable(nm)
        if applicable:
            ctx["element"] = get_writing_element_fields(ctx, "faction", applicable, ctx["el"].id, only_visible=False)

    if nm == "plot":
        ctx["sheet_plots"] = (
            PlotCharacterRel.objects.filter(plot=ctx["el"]).order_by("character__number").select_related("character")
        )

    return render(request, "larpmanager/orga/writing/view.html", ctx)


def writing_versions(request, ctx, nm, tp):
    ctx["versions"] = TextVersion.objects.filter(tp=tp, eid=ctx[nm].id).order_by("version").select_related("member")
    last = None
    for v in ctx["versions"]:
        if last is not None:
            compute_diff(v, last)
        else:
            v.diff = v.text.replace("\n", "<br />")
        last = v
    ctx["element"] = ctx[nm]
    ctx["typ"] = nm
    return render(request, "larpmanager/orga/writing/versions.html", ctx)


@receiver(pre_save, sender=Character)
def pre_save_character(sender, instance, *args, **kwargs):
    if not instance.pk:
        return

    replace_chars_all(instance)
