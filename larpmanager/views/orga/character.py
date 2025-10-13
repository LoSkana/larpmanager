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

from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Max
from django.db.models.functions import Length, Substr
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.cache.character import get_event_cache_all
from larpmanager.forms.character import (
    OrgaCharacterForm,
    OrgaWritingOptionForm,
    OrgaWritingQuestionForm,
)
from larpmanager.forms.utils import EventCharacterS2Widget
from larpmanager.forms.writing import FactionForm, PlotForm, QuestForm, TraitForm
from larpmanager.models.base import Feature
from larpmanager.models.casting import Trait
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
    WritingQuestionType,
    _get_writing_mapping,
)
from larpmanager.models.utils import strip_tags
from larpmanager.models.writing import (
    Character,
    Faction,
    Plot,
    PlotCharacterRel,
    Prologue,
    Relationship,
    SpeedLarp,
    TextVersionChoices,
)
from larpmanager.utils.character import get_chars_relations
from larpmanager.utils.common import (
    exchange_order,
    get_char,
)
from larpmanager.utils.download import orga_character_form_download
from larpmanager.utils.edit import backend_edit, set_suggestion, writing_edit, writing_edit_working_ticket
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.writing import writing_list, writing_versions, writing_view


def get_character_optimized(ctx, num):
    """Get character with optimized queries for editing.

    Args:
        ctx: Template context dictionary
        num: Character ID

    Raises:
        Http404: If character does not exist
    """
    try:
        ev = ctx["event"].get_class_parent(Character)
        features = ctx.get("features", [])

        select_related_fields = ["event"]

        # Add other select_related fields based on features
        if "user_character" in features:
            select_related_fields.append("player")
        if "progress" in features:
            select_related_fields.append("progress")
        if "assigned" in features:
            select_related_fields.append("assigned")
        if "mirror" in features:
            select_related_fields.append("mirror")

        query = Character.objects.select_related(*select_related_fields)

        # Only prefetch factions and plots if their features are enabled
        prefetch_fields = []
        if "faction" in features:
            prefetch_fields.append("factions_list")
        if "plot" in features:
            prefetch_fields.append("plots")

        if prefetch_fields:
            query = query.prefetch_related(*prefetch_fields)

        ctx["character"] = query.get(event=ev, pk=num)
        ctx["class_name"] = "character"
    except ObjectDoesNotExist as err:
        raise Http404("character does not exist") from err


@login_required
def orga_characters(request, s):
    ctx = check_event_permission(request, s, "orga_characters")

    get_event_cache_all(ctx)
    for config_name in ["user_character_approval", "writing_external_access"]:
        ctx[config_name] = ctx["event"].get_config(config_name, False)
    if ctx["event"].get_config("show_export", False):
        ctx["export"] = "character"

    return writing_list(request, ctx, Character, "character")


@login_required
def orga_characters_edit(request, s, num):
    ctx = check_event_permission(request, s, "orga_characters")

    # Only load full event cache if we need relationships or other features that require it
    if "relationships" in ctx["features"] or "character_finder" in ctx.get("features", []):
        get_event_cache_all(ctx)

    if num != 0:
        get_character_optimized(ctx, num)

    _characters_relationships(ctx)

    return writing_edit(request, ctx, OrgaCharacterForm, "character", TextVersionChoices.CHARACTER)


def _characters_relationships(ctx):
    """Setup character relationships data and widgets for editing.

    Args:
        ctx: Context dictionary to populate with relationship data
    """
    ctx["relationships"] = {}
    if "relationships" not in ctx["features"]:
        return

    try:
        ctx["rel_tutorial"] = Feature.objects.get(slug="relationships").tutorial
    except ObjectDoesNotExist:
        pass

    ctx["TINYMCE_DEFAULT_CONFIG"] = conf_settings.TINYMCE_DEFAULT_CONFIG
    widget = EventCharacterS2Widget(attrs={"id": "new_rel_select"})
    widget.set_event(ctx["event"])
    ctx["new_rel"] = widget.render(name="new_rel_select", value="")

    if "character" in ctx:
        rels = {}

        direct_rels = Relationship.objects.filter(source=ctx["character"]).select_related("target")

        for rel in direct_rels:
            if rel.target.id not in rels:
                rels[rel.target.id] = {"char": rel.target}
            rels[rel.target.id]["direct"] = rel.text

        inverse_rels = Relationship.objects.filter(target=ctx["character"]).select_related("source")

        for rel in inverse_rels:
            if rel.source.id not in rels:
                rels[rel.source.id] = {"char": rel.source}
            rels[rel.source.id]["inverse"] = rel.text

        sorted_rels = sorted(
            rels.items(),
            key=lambda item: len(item[1].get("direct", "")) + len(item[1].get("inverse", "")),
            reverse=True,
        )
        ctx["relationships"] = dict(sorted_rels)


def update_relationship(request, ctx, nm, fl):
    for d in ctx[nm]:
        idx = getattr(d, fl).number
        c = request.POST.get(f"{nm}_text_{idx}")
        if c:
            d.text = c
        c = request.POST.get(f"{nm}_text_eng_{idx}")
        if c:
            d.text_eng = c
        d.save()


@login_required
def orga_characters_relationships(request, s, num):
    ctx = check_event_permission(request, s, "orga_characters")
    get_char(ctx, num)
    ctx["direct"] = (
        Relationship.objects.filter(source=ctx["character"])
        .select_related("target")
        .order_by(Length("text").asc(), "target__number")
    )
    ctx["inverse"] = (
        Relationship.objects.filter(target=ctx["character"])
        .select_related("source")
        .order_by(Length("text").asc(), "source__number")
    )
    return render(request, "larpmanager/orga/characters/relationships.html", ctx)


@login_required
def orga_characters_view(request, s, num):
    ctx = check_event_permission(request, s, ["orga_reading", "orga_characters"])
    get_char(ctx, num)
    get_event_cache_all(ctx)
    return writing_view(request, ctx, "character")


@login_required
def orga_characters_versions(request, s, num):
    ctx = check_event_permission(request, s, "orga_characters")
    get_char(ctx, num)
    return writing_versions(request, ctx, "character", TextVersionChoices.CHARACTER)


@login_required
def orga_characters_summary(request, s, num):
    ctx = check_event_permission(request, s, "orga_characters")
    get_char(ctx, num)
    ctx["factions"] = []

    for p in ctx["character"].factions_list.all().prefetch_related("characters"):
        ctx["factions"].append(p.show_complete())
    ctx["plots"] = []

    for p in ctx["character"].plots.all().prefetch_related("characters"):
        ctx["plots"].append(p.show_complete())

    return render(request, "larpmanager/orga/characters_summary.html", ctx)


@login_required
def orga_writing_form_list(request, s, typ):
    """Generate form list data for writing questions in JSON format.

    Processes writing questions and their answers for display in organizer interface,
    handling different question types (single, multiple choice, text, paragraph).
    """
    ctx = check_event_permission(request, s, "orga_characters")
    check_writing_form_type(ctx, typ)
    event = ctx["event"]
    if event.parent:
        event = event.parent
    eid = request.POST.get("num")

    applicable = QuestionApplicable.get_applicable(typ)
    element_typ = QuestionApplicable.get_applicable_inverse(applicable)
    element_ids = element_typ.objects.filter(event=event).values_list("id", flat=True)

    res = {}
    popup = []
    max_length = 100

    question = event.get_elements(WritingQuestion).get(pk=eid, applicable=applicable)
    if question.typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
        cho = {}
        for opt in event.get_elements(WritingOption).filter(question=question):
            cho[opt.id] = opt.name

        for el in WritingChoice.objects.filter(question=question, element_id__in=element_ids).order_by("option__order"):
            if el.element_id not in res:
                res[el.element_id] = []
            res[el.element_id].append(cho[el.option_id])

    elif question.typ in [BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, WritingQuestionType.COMPUTED]:
        que = WritingAnswer.objects.filter(question=question, element_id__in=element_ids)
        que = que.annotate(short_text=Substr("text", 1, max_length))
        que = que.values("element_id", "short_text")
        for el in que:
            answer = el["short_text"]
            if len(answer) == max_length:
                popup.append(el["element_id"])
            res[el["element_id"]] = answer

    return JsonResponse({"res": res, "popup": popup, "num": question.id})


@login_required
def orga_writing_form_email(request, s, typ):
    """Generate email data for writing form options by character choices.

    Args:
        request: HTTP request object
        s: Event/run identifier
        typ: Writing form type

    Returns:
        JsonResponse with email data organized by option choices
    """
    ctx = check_event_permission(request, s, "orga_characters")
    check_writing_form_type(ctx, typ)
    event = ctx["event"]
    if event.parent:
        event = event.parent
    eid = request.POST.get("num")
    q = event.get_elements(WritingQuestion).get(pk=eid)

    if q.typ not in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
        return

    cho = {}
    for opt in event.get_elements(WritingOption).filter(question=q):
        cho[opt.id] = opt.name

    get_event_cache_all(ctx)
    mapping = {}
    for ch_num, ch in ctx["chars"].items():
        mapping[ch["id"]] = ch_num

    res = {}

    character_ids = Character.objects.filter(event=event).values_list("id", flat=True)
    for el in WritingChoice.objects.filter(question=q, element_id__in=character_ids):
        if el.element_id not in mapping:
            continue
        ch_num = mapping[el.element_id]
        char = ctx["chars"][ch_num]
        if el.option_id not in res:
            res[el.option_id] = {"emails": [], "names": []}
        res[el.option_id]["emails"].append(char["name"])
        if char["player_id"]:
            res[el.option_id]["names"].append(char["player"])

    n_res = {}
    for opt_id, value in res.items():
        n_res[cho[opt_id]] = value

    return JsonResponse(n_res)


@login_required
def orga_character_form(request, s):
    return redirect("orga_writing_form", s=s, typ="character")


def check_writing_form_type(ctx, typ):
    typ = typ.lower()
    mapping = _get_writing_mapping()
    available = {v: k for k, v in QuestionApplicable.choices if mapping[v] in ctx["features"]}
    if typ not in available:
        raise Http404(f"unknown writing form type: {typ}")
    ctx["typ"] = typ
    ctx["writing_typ"] = available[typ]
    ctx["label_typ"] = typ.capitalize()
    ctx["available_typ"] = {k.capitalize(): v for k, v in available.items()}


@login_required
def orga_writing_form(request, s, typ):
    """Display and manage writing form questions for character creation.

    Args:
        request: HTTP request object
        s: Event slug
        typ: Writing form type (character, etc.)

    Returns:
        HttpResponse: Rendered form page or download response
    """
    ctx = check_event_permission(request, s, "orga_character_form")
    check_writing_form_type(ctx, typ)

    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_character_form_download(ctx)

    ctx["upload"] = "character_form"
    ctx["download"] = 1

    ctx["list"] = (
        ctx["event"]
        .get_elements(WritingQuestion)
        .filter(applicable=ctx["writing_typ"])
        .order_by("order")
        .prefetch_related("options")
    )
    for el in ctx["list"]:
        el.options_list = el.options.order_by("order")

    ctx["approval"] = ctx["event"].get_config("user_character_approval", False)
    ctx["status"] = "user_character" in ctx["features"] and typ.lower() == "character"

    return render(request, "larpmanager/orga/characters/form.html", ctx)


@login_required
def orga_writing_form_edit(request, s, typ, num):
    """Edit writing form questions with validation and option handling.

    Args:
        request: HTTP request object
        s: Event slug
        typ: Writing form type identifier
        num: Question number/ID

    Returns:
        HttpResponse: Form edit template or redirect to options/form list
    """
    perm = "orga_character_form"
    ctx = check_event_permission(request, s, perm)
    check_writing_form_type(ctx, typ)
    if backend_edit(request, ctx, OrgaWritingQuestionForm, num, assoc=False):
        set_suggestion(ctx, perm)
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, s=ctx["run"].get_slug(), typ=typ, num=0)
        edit_option = False
        if str(request.POST.get("new_option", "")) == "1":
            edit_option = True
        elif ctx["saved"].typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
            if not WritingOption.objects.filter(question_id=ctx["saved"].id).exists():
                edit_option = True
                messages.warning(
                    request,
                    _("You must define at least one option before saving a single-choice or multiple-choice question"),
                )
        if edit_option:
            return redirect(orga_writing_options_new, s=ctx["run"].get_slug(), typ=typ, num=ctx["saved"].id)
        return redirect("orga_writing_form", s=ctx["run"].get_slug(), typ=typ)

    ctx["list"] = WritingOption.objects.filter(question=ctx["el"], question__applicable=ctx["writing_typ"]).order_by(
        "order"
    )

    return render(request, "larpmanager/orga/characters/form_edit.html", ctx)


@login_required
def orga_writing_form_order(request, s, typ, num, order):
    ctx = check_event_permission(request, s, "orga_character_form")
    check_writing_form_type(ctx, typ)
    exchange_order(ctx, WritingQuestion, num, order)
    return redirect("orga_writing_form", s=ctx["run"].get_slug(), typ=typ)


@login_required
def orga_writing_options_edit(request, s, typ, num):
    ctx = check_event_permission(request, s, "orga_character_form")
    check_writing_form_type(ctx, typ)
    return writing_option_edit(ctx, num, request, typ)


@login_required
def orga_writing_options_new(request, s, typ, num):
    ctx = check_event_permission(request, s, "orga_character_form")
    check_writing_form_type(ctx, typ)
    ctx["question_id"] = num
    return writing_option_edit(ctx, 0, request, typ)


def writing_option_edit(ctx, num, request, typ):
    if backend_edit(request, ctx, OrgaWritingOptionForm, num, assoc=False):
        redirect_target = "orga_writing_form_edit"
        if "continue" in request.POST:
            redirect_target = "orga_writing_options_new"
        return redirect(redirect_target, s=ctx["run"].get_slug(), typ=typ, num=ctx["saved"].question_id)
    return render(request, "larpmanager/orga/edit.html", ctx)


@login_required
def orga_writing_options_order(request, s, typ, num, order):
    ctx = check_event_permission(request, s, "orga_character_form")
    check_writing_form_type(ctx, typ)
    exchange_order(ctx, WritingOption, num, order)
    return redirect("orga_writing_form_edit", s=ctx["run"].get_slug(), typ=typ, num=ctx["current"].question_id)


@login_required
def orga_check(request, s):
    """Perform comprehensive character and writing consistency checks.

    Validates character relationships, writing completeness, speedlarp constraints,
    and plot assignments to identify potential issues in the event setup.
    """
    ctx = check_event_permission(request, s)

    get_event_cache_all(ctx)

    checks = {}

    cache = {}

    chs_numbers = list(ctx["chars"].keys())
    id_number_map = {}
    number_map = {}
    for el in ctx["event"].get_elements(Character).values_list("number", "text"):
        if el[0] not in ctx["chars"]:
            continue
        ch = ctx["chars"][el[0]]
        ch["text"] = ch["teaser"] + el[1]
        id_number_map[ch["id"]] = ch["number"]
        number_map[ch["number"]] = ch["id"]

    if "plot" in ctx["features"]:
        event = ctx["event"].get_class_parent(Character)
        que = PlotCharacterRel.objects.filter(character__event=event).select_related("character")
        que = que.exclude(text__isnull=True).exclude(text__exact="")
        for el in que.values_list("character__number", "text"):
            ctx["chars"][el[0]]["text"] += el[1]

    check_relations(cache, checks, chs_numbers, ctx, number_map)

    # check extinct, missing, interloper
    check_writings(cache, checks, chs_numbers, ctx, id_number_map)

    # check speedlarp, no player has double
    check_speedlarp(checks, ctx, id_number_map)

    ctx["checks"] = checks
    # print(checks)
    return render(request, "larpmanager/orga/writing/check.html", ctx)


def check_relations(cache, checks, chs_numbers, ctx, number_map):
    """Check character relationships for missing and extinct references.

    Args:
        cache: Dictionary to store relationship data for each character
        checks: Dictionary to accumulate validation errors
        chs_numbers: Set of valid character numbers in the event
        ctx: Context dictionary containing character data
        number_map: Mapping from character IDs to numbers

    Side effects:
        Updates checks with relat_missing and relat_extinct validation errors
        Populates cache with character relationship data
    """
    checks["relat_missing"] = []
    checks["relat_extinct"] = []
    for c in ctx["chars"]:
        ch = ctx["chars"][c]
        (from_text, extinct) = get_chars_relations(ch["text"], chs_numbers)
        name = f"#{ch['number']} {ch['name']}"
        for e in extinct:
            checks["relat_extinct"].append((name, e))
        cache[c] = (name, from_text)
    for c, content in cache.items():
        (first, first_rel) = content
        for oth in first_rel:
            (second, second_rel) = cache[oth]
            if c not in second_rel:
                checks["relat_missing"].append(
                    {"f_id": number_map[c], "f_name": first, "s_id": number_map[oth], "s_name": second}
                )


def check_writings(cache, checks, chs_numbers, ctx, id_number_map):
    """Validate writing submissions and requirements for different element types.

    Args:
        cache: Dictionary to store validation results
        checks: Dictionary to store validation issues found
        chs_numbers: Set of valid character numbers
        ctx: Context with event and features data
        id_number_map: Mapping from character IDs to numbers

    Side effects:
        Updates checks with extinct, missing, and interloper character issues
    """
    for el in [Faction, Plot, Prologue, SpeedLarp]:
        nm = str(el.__name__).lower()
        if nm not in ctx["features"]:
            continue
        checks[nm + "_extinct"] = []
        checks[nm + "_missing"] = []
        checks[nm + "_interloper"] = []
        cache[nm] = {}
        # check s: all characters currently listed has
        for f in (
            ctx["event"].get_elements(el).annotate(characters_map=ArrayAgg("characters")).prefetch_related("characters")
        ):
            (from_text, extinct) = get_chars_relations(f.text, chs_numbers)
            for e in extinct:
                checks[nm + "_extinct"].append((f, e))

            from_rels = set()
            for ch_id in f.characters_map:
                if ch_id not in id_number_map:
                    continue
                from_rels.add(id_number_map[ch_id])

            for e in list(set(from_text) - set(from_rels)):
                checks[nm + "_missing"].append((f, e))
            for e in list(set(from_rels) - set(from_text)):
                checks[nm + "_interloper"].append((f, e))
                # cache[nm][f.number] = (str(f), from_text)


def check_speedlarp(checks, ctx, id_number_map):
    """Validate speedlarp character configurations.

    Args:
        checks: Dictionary to store validation issues
        ctx: Context with event features and character data
        id_number_map: Mapping from character IDs to numbers

    Side effects:
        Updates checks with speedlarp double assignments and missing configurations
    """
    if "speedlarp" not in ctx["features"]:
        return

    checks["speed_larps_double"] = []
    checks["speed_larps_missing"] = []
    max_typ = ctx["event"].get_elements(SpeedLarp).aggregate(Max("typ"))["typ__max"]
    if not max_typ or max_typ == 0:
        return

    speeds = {}
    for el in ctx["event"].get_elements(SpeedLarp).annotate(characters_map=ArrayAgg("characters")):
        check_speedlarp_prepare(el, id_number_map, speeds)
    for chnum, c in ctx["chars"].items():
        if chnum not in speeds:
            continue
        for typ in range(1, max_typ + 1):
            if typ not in speeds[chnum]:
                checks["speed_larps_missing"].append((typ, c))
            if len(speeds[chnum][typ]) > 1:
                checks["speed_larps_double"].append((typ, c))


def check_speedlarp_prepare(el, id_number_map, speeds):
    from_rels = set()
    for ch_id in el.characters_map:
        if ch_id not in id_number_map:
            continue
        from_rels.add(id_number_map[ch_id])
    for ch in from_rels:
        if ch not in speeds:
            speeds[ch] = {}
        if el.typ not in speeds[ch]:
            speeds[ch][el.typ] = []
        speeds[ch][el.typ].append(str(el))


@require_POST
def orga_character_get_number(request, s):
    ctx = check_event_permission(request, s, "orga_characters")
    idx = request.POST.get("idx")
    type = request.POST.get("type")
    try:
        if type.lower() == "trait":
            el = ctx["event"].get_elements(Trait).get(pk=idx)
        else:
            el = ctx["event"].get_elements(Character).get(pk=idx)
        return JsonResponse({"res": "ok", "number": el.number})
    except ObjectDoesNotExist:
        JsonResponse({"res": "ko"})


@require_POST
def orga_writing_excel_edit(request, s, typ):
    """Handle Excel-based editing of writing elements.

    Manages bulk editing of character stories and writing content through
    spreadsheet interface, providing AJAX form rendering with TinyMCE
    support and character count validation.
    """
    try:
        ctx = _get_excel_form(request, s, typ)
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    tinymce = False
    if ctx["question"].typ in [WritingQuestionType.TEASER, WritingQuestionType.SHEET, BaseQuestionType.EDITOR]:
        tinymce = True

    counter = ""
    if ctx["question"].typ in ["m", "t", "p", "e", "name", "teaser", "text", "title"]:
        if ctx["question"].max_length:
            if ctx["question"].typ == "m":
                name = _("options")
            else:
                name = "text length"
            counter = f'<div class="helptext">{name}: <span class="count"></span> / {ctx["question"].max_length}</div>'

    confirm = _("Confirm")
    field = ctx["form"][ctx["field_key"]]
    value = f"""
        <h2>{ctx["question"].name}: {ctx["element"]}</h2>
        <form id='form-excel'>
            <div id='{field.auto_id}_tr'>
                {field.as_widget()}
                {counter}
            </div>
        </form>
        <br />
        <input type='submit' value='{confirm}'>
        <a href="#" class="close"><i class="fa-solid fa-xmark"></i></a>
    """
    response = {
        "k": 1,
        "v": value,
        "tinymce": tinymce,
        "typ": ctx["question"].typ,
        "max_length": ctx["question"].max_length,
        "key": field.auto_id,
    }
    return JsonResponse(response)


@require_POST
def orga_writing_excel_submit(request, s, typ):
    """Handle Excel submission for writing data with validation.

    Args:
        request: HTTP request with form data
        s: Event slug
        typ: Writing type identifier

    Returns:
        JsonResponse: Success status, element updates, or validation errors
    """
    try:
        ctx = _get_excel_form(request, s, typ, submit=True)
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    ctx["auto"] = int(request.POST.get("auto"))
    if ctx["auto"]:
        if request.user.is_superuser:
            return JsonResponse({"k": 1})
        msg = _check_working_ticket(request, ctx, request.POST["token"])
        if msg:
            return JsonResponse({"warn": msg})

    if ctx["form"].is_valid():
        obj = ctx["form"].save()
        response = {
            "k": 1,
            "qid": ctx["question"].id,
            "eid": ctx["element"].id,
            "update": _get_question_update(ctx, obj),
        }
        return JsonResponse(response)
    else:
        return JsonResponse({"k": 2, "errors": ctx["form"].errors})


def _get_excel_form(request, s, typ, submit=False):
    """Prepare Excel form context for bulk editing operations.

    Sets up form data and validation for spreadsheet-based content editing,
    filtering forms to show only the requested question field and preparing
    the context for character, faction, plot, trait, or quest editing.
    """
    ctx = check_event_permission(request, s, f"orga_{typ}s")
    if not submit:
        get_event_cache_all(ctx)
    check_writing_form_type(ctx, typ)
    question_id = int(request.POST.get("qid"))
    element_id = int(request.POST.get("eid"))

    question = (
        ctx["event"]
        .get_elements(WritingQuestion)
        .select_related("event")
        .filter(applicable=ctx["writing_typ"])
        .get(pk=question_id)
    )
    ctx["applicable"] = QuestionApplicable.get_applicable_inverse(ctx["writing_typ"])
    element = ctx["event"].get_elements(ctx["applicable"]).select_related("event").get(pk=element_id)

    ctx["elementTyp"] = ctx["applicable"]

    form_mapping = {
        "character": OrgaCharacterForm,
        "faction": FactionForm,
        "plot": PlotForm,
        "trait": TraitForm,
        "quest": QuestForm,
    }

    form_class = form_mapping.get(typ, OrgaCharacterForm)
    if submit:
        form = form_class(request.POST, request.FILES, ctx=ctx, instance=element)
    else:
        form = form_class(ctx=ctx, instance=element)

    keep_key = f"q{question_id}"
    if question.typ not in BaseQuestionType.get_basic_types():
        keep_key = question.typ

    if keep_key in form.fields:
        form.fields = {keep_key: form.fields[keep_key]}
    else:
        form.fields = {}

    ctx["form"] = form
    ctx["question"] = question
    ctx["element"] = element
    ctx["field_key"] = keep_key

    return ctx


def _get_question_update(ctx, el):
    """Generate question update HTML for different question types.

    Creates appropriate HTML content for updating questions based on their type,
    handling cover questions and other writing question formats.
    """
    if ctx["question"].typ in [WritingQuestionType.COVER]:
        return f"""
                <a href="{el.thumb.url}">
                    <img src="{el.thumb.url}"
                         class="character-cover"
                         alt="character cover" />
                </a>
            """

    question_key = f"q{ctx['question'].id}"
    question_slug = str(ctx["question"].id)
    if ctx["question"].typ not in BaseQuestionType.get_basic_types():
        question_key = ctx["question"].typ
        question_slug = ctx["question"].typ

    value = ctx["form"].cleaned_data[question_key]

    if ctx["question"].typ in [WritingQuestionType.TEASER, WritingQuestionType.SHEET, BaseQuestionType.EDITOR]:
        value = strip_tags(str(value))

    if ctx["question"].typ in [BaseQuestionType.MULTIPLE, BaseQuestionType.SINGLE]:
        # get option names
        option_ids = [int(val) for val in value]
        query = ctx["event"].get_elements(WritingOption).filter(pk__in=option_ids).order_by("order")
        value = ", ".join([display for display in query.values_list("name", flat=True)])
    else:
        # check if it is over the character limit
        value = str(value)
        limit = conf_settings.FIELD_SNIPPET_LIMIT
        if len(value) > limit:
            value = value[:limit]
            value += f"... <a href='#' class='post_popup' pop='{ctx['element'].id}' fie='{question_slug}'><i class='fas fa-eye'></i></a>"

    return value


def _check_working_ticket(request, ctx, token):
    # perform normal check, if somebody else has opened the character to edit it
    msg = writing_edit_working_ticket(request, ctx["typ"], ctx["element"].id, token)

    # perform check if somebody has opened the same field to edit it
    if not msg:
        msg = writing_edit_working_ticket(request, ctx["typ"], f"{ctx['element'].id}_{ctx['question'].id}", token)

    return msg
