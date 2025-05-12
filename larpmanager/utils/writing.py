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

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Model
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from larpmanager.cache.character import get_event_cache_all
from larpmanager.cache.writing import get_cache_cocreation, get_cache_text_field
from larpmanager.forms.writing import UploadElementsForm
from larpmanager.models.access import get_event_staffers
from larpmanager.models.casting import Trait
from larpmanager.models.event import ProgressStep, RunText
from larpmanager.models.experience import AbilityPx
from larpmanager.models.form import WritingAnswer, WritingQuestion
from larpmanager.models.writing import (
    Character,
    CharacterConfig,
    Plot,
    PlotCharacterRel,
    TextVersion,
    Writing,
    replace_chars_all,
)
from larpmanager.templatetags.show_tags import show_char, show_trait
from larpmanager.utils.common import check_field, compute_diff
from larpmanager.utils.download import writing_download
from larpmanager.utils.upload import upload_elements


def orga_list_progress_assign(ctx, typ: type[Model]):
    if "progress" in ctx["features"]:
        ctx["progress_steps"] = {}
        ctx["progress_steps_map"] = {}
        for el in ProgressStep.objects.filter(event=ctx["event"]).order_by("order"):
            ctx["progress_steps"][el.id] = str(el)
            ctx["progress_steps_map"][el.id] = 0

    if "assigned" in ctx["features"]:
        ctx["assigned"] = {}
        ctx["assigned_map"] = {}
        for m in get_event_staffers(ctx["event"]):
            ctx["assigned"][m.id] = m.show_nick()
            ctx["assigned_map"][m.id] = 0

    if "progress" in ctx["features"] and "assigned" in ctx["features"]:
        ctx["progress_assigned_map"] = {}
        for el in ctx["progress_steps"]:
            for el2 in ctx["assigned"]:
                ctx["progress_assigned_map"][f"{el}_{el2}"] = 0

    for el in ctx["list"]:
        # count progress
        if "progress" in ctx["features"] and el.progress_id:
            ctx["progress_steps_map"][el.progress_id] += 1

        if "assigned" in ctx["features"] and el.assigned_id and el.assigned_id in ctx["assigned_map"]:
            ctx["assigned_map"][el.assigned_id] += 1

        if "progress" in ctx["features"] and "assigned" in ctx["features"] and el.progress_id and el.assigned_id:
            ctx["progress_assigned_map"][f"{el.progress_id}_{el.assigned_id}"] += 1

    # noinspection PyProtectedMember
    ctx["typ"] = str(typ._meta).replace("larpmanager.", "")  # type: ignore[attr-defined]


def writing_popup_question(ctx, idx, question_idx):
    try:
        char = Character.objects.get(pk=idx, event=ctx["event"].get_class_parent(Character))
        question = WritingQuestion.objects.get(pk=question_idx, event=ctx["event"].get_class_parent(WritingQuestion))
        el = WritingAnswer.objects.get(element_id=char.id, question=question)
        tx = f"<h2>{char} - {question.display}</h2>" + el.text
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

    if "co_creation" in ctx["features"]:
        cc = {"co_creation_question": "first", "co_creation_answer": "second"}
        if tp in cc:
            (el, creat) = RunText.objects.get_or_create(run=ctx["run"], eid=idx, typ=RunText.COCREATION)
            v = getattr(el, cc[tp])
            setattr(el, tp, v)

    if not hasattr(el, tp):
        return JsonResponse({"k": 0})

    tx = f"<h2>{el} - {tp}</h2>"
    if typ == Trait:
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
        return writing_download(request, ctx, typ, nm)

    if request.POST.get("example") == "1":
        return writing_example(ctx, typ)

    if request.POST.get("popup") == "1":
        return writing_popup(request, ctx, typ)

    return upload_elements(request, ctx, typ, nm, "orga_" + nm + "s")


def writing_list(request, ctx, typ, nm):
    if request.method == "POST":
        return writing_post(request, ctx, typ, nm)

    ctx["form"] = UploadElementsForm()
    ev = ctx["event"]

    ctx["nm"] = nm

    text_fields, writing = writing_list_query(ctx, ev, typ)

    if issubclass(typ, Character):
        writing_list_char(ctx, ev, text_fields)
        writing_list_cocreation(ctx, typ)

    if issubclass(typ, Plot):
        writing_list_plot(ctx)

    if issubclass(typ, AbilityPx):
        ctx["list"] = ctx["list"].prefetch_related("prerequisites")

    if writing:
        orga_list_progress_assign(ctx, typ)  # pyright: ignore[reportArgumentType]
        writing_list_text_fields(ctx, text_fields, typ)

    return render(request, "larpmanager/orga/writing/" + nm + "s.html", ctx)


def writing_list_query(ctx, ev, typ):
    writing = issubclass(typ, Writing)
    text_fields = ["teaser", "text", "preview"]
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
    gctf = get_cache_text_field(typ, ctx["event"])
    for el in ctx["list"]:
        if el.number not in gctf:
            continue
        for f in text_fields:
            if f not in gctf[el.number]:
                continue
            (red, ln) = gctf[el.number][f]
            setattr(el, f + "_red", red)
            setattr(el, f + "_ln", ln)


def writing_list_cocreation(ctx, typ):
    if "co_creation" not in ctx["features"] or not issubclass(typ, Character):
        return

    gcc = get_cache_cocreation(ctx["run"])
    for el in ctx["list"]:
        if el.number not in gcc:
            continue
        for f in ["co_creation_question", "co_creation_answer"]:
            if f not in gcc[el.number]:
                continue
            (red, ln) = gcc[el.number][f]
            setattr(el, f + "_red", red)
            setattr(el, f + "_ln", ln)


def writing_list_plot(ctx):
    ctx["chars"] = {}
    for el in PlotCharacterRel.objects.filter(character__event=ctx["event"]).select_related("plot", "character"):
        if el.plot.number not in ctx["chars"]:
            ctx["chars"][el.plot.number] = []
        ctx["chars"][el.plot.number].append((f"#{el.character.number} {el.character.name}", el.character.number))
    for el in ctx["list"]:
        if el.number in ctx["chars"]:
            el.chars = ctx["chars"][el.number]


def writing_list_char(ctx, ev, text_fields):
    if "co_creation" in ctx["features"]:
        text_fields.extend(["co_creation_question", "co_creation_answer"])
    if "user_character" in ctx["features"]:
        ctx["list"] = ctx["list"].select_related("player")
    if "relationships" in ctx["features"]:
        cache = {}
        res = Character.objects.filter(event=ev.get_class_parent("relationships")).annotate(dc=Count("characters"))
        for el in res:
            cache[el.number] = el.dc

        for el in ctx["list"]:
            el.cache_relationship_count = cache[el.number]
    if "plot" in ctx["features"]:
        ctx["plots"] = {}
        for el in PlotCharacterRel.objects.filter(character__event=ctx["event"]).select_related("plot", "character"):
            if el.character.number not in ctx["plots"]:
                ctx["plots"][el.character.number] = []
            ctx["plots"][el.character.number].append((f"[T{el.plot.number}] {el.plot.name}", el.plot.number))

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
    return render(request, "larpmanager/orga/view.html", ctx)


def writing_versions(request, ctx, nm, tp):
    ctx["versions"] = TextVersion.objects.filter(tp=tp, eid=ctx[nm].id).order_by("version").select_related("member")
    last = None
    for v in ctx["versions"]:
        if last is not None:
            compute_diff(v, last)
        last = v
    return render(request, "larpmanager/orga/writing/versions.html", ctx)


@receiver(pre_save, sender=Character)
def pre_save_character(sender, instance, *args, **kwargs):
    if not instance.pk:
        return

    replace_chars_all(instance)
