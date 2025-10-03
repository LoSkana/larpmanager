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
from django.db.models import Exists, Model, OuterRef
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_all, get_writing_element_fields
from larpmanager.cache.rels import get_event_rels_cache
from larpmanager.cache.text_fields import get_cache_text_field
from larpmanager.models.access import get_event_staffers
from larpmanager.models.casting import Quest, Trait
from larpmanager.models.event import ProgressStep
from larpmanager.models.experience import AbilityPx
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    WritingAnswer,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import (
    Character,
    CharacterConfig,
    Faction,
    Plot,
    PlotCharacterRel,
    Prologue,
    SpeedLarp,
    TextVersion,
    Writing,
    replace_chars_all,
)
from larpmanager.templatetags.show_tags import show_char, show_trait
from larpmanager.utils.bulk import handle_bulk_characters, handle_bulk_quest, handle_bulk_trait
from larpmanager.utils.character import get_character_relationships, get_character_sheet
from larpmanager.utils.common import check_field, compute_diff
from larpmanager.utils.download import download
from larpmanager.utils.edit import _setup_char_finder
from larpmanager.utils.exceptions import ReturnNowError


def orga_list_progress_assign(ctx, typ: type[Model]):
    """Setup progress and assignment tracking for writing elements.

    Args:
        ctx: Context dictionary to populate with progress/assignment data
        typ: Model type being processed (Character, Plot, etc.)

    Side effects:
        Updates ctx with progress steps, assignments, and mapping counters
    """
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
    """Get writing question data for popup display.

    Args:
        ctx: Context dictionary with event and writing element data
        idx (int): Writing element ID
        question_idx (int): Question index

    Returns:
        dict: Question data for popup rendering
    """
    try:
        char = Character.objects.get(pk=idx, event=ctx["event"].get_class_parent(Character))
        question = WritingQuestion.objects.get(pk=question_idx, event=ctx["event"].get_class_parent(WritingQuestion))
        el = WritingAnswer.objects.get(element_id=char.id, question=question)
        tx = f"<h2>{char} - {question.name}</h2>" + el.text
        return JsonResponse({"k": 1, "v": tx})
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})


def writing_popup(request, ctx, typ):
    """Handle writing element popup requests.

    Args:
        request: Django HTTP request object
        ctx: Context dictionary with event data
        typ: Writing element type (character, plot, etc.)

    Returns:
        JsonResponse: Writing element data for popup display
    """
    get_event_cache_all(ctx)

    try:
        idx = int(request.POST.get("idx", ""))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid idx parameter"}, status=400)
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
    """Generate example writing content for a given type.

    Args:
        ctx: Context dictionary with event information
        typ (str): Type of writing element to generate example for

    Returns:
        dict: Example content and structure for the writing type
    """
    file_rows = typ.get_example_csv(ctx["features"])

    buffer = io.StringIO()
    wr = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    wr.writerows(file_rows)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=example.csv"

    return response


def writing_post(request, ctx, typ, nm):
    """Handle POST requests for writing operations.

    Args:
        request: Django HTTP request object
        ctx: Context dictionary with event data
        typ: Writing element type class
        nm: Template name

    Raises:
        ReturnNowError: When download operation needs to return immediately
    """
    if not request.POST:
        return

    if request.POST.get("download") == "1":
        raise ReturnNowError(download(ctx, typ, nm))

    if request.POST.get("example") == "1":
        raise ReturnNowError(writing_example(ctx, typ))

    if request.POST.get("popup") == "1":
        raise ReturnNowError(writing_popup(request, ctx, typ))


def writing_list(request, ctx, typ, nm):
    """Handle writing list display with POST processing and bulk operations.

    Manages writing element lists with form submission processing,
    bulk operations, and proper context preparation for different writing types.
    """
    writing_post(request, ctx, typ, nm)

    writing_bulk(ctx, request, typ)

    ev = ctx["event"]

    ctx["nm"] = nm

    text_fields, writing = writing_list_query(ctx, ev, typ)

    if issubclass(typ, Character):
        writing_list_char(ctx)

    if issubclass(typ, Plot):
        writing_list_plot(ctx)

    if issubclass(typ, Faction):
        writing_list_faction(ctx)

    if issubclass(typ, SpeedLarp):
        writing_list_speedlarp(ctx)

    if issubclass(typ, Prologue):
        writing_list_prologue(ctx)

    if issubclass(typ, AbilityPx):
        ctx["list"] = ctx["list"].prefetch_related("prerequisites")

    if writing:
        # noinspection PyProtectedMember, PyUnresolvedReferences
        ctx["label_typ"] = typ._meta.model_name
        ctx["writing_typ"] = QuestionApplicable.get_applicable(ctx["label_typ"])
        if ctx["writing_typ"]:
            ctx["upload"] = f"{nm}s"
            ctx["download"] = f"{nm}s"
        orga_list_progress_assign(ctx, typ)  # pyright: ignore[reportArgumentType]
        writing_list_text_fields(ctx, text_fields, typ)
        _prepare_writing_list(ctx, request)
        _setup_char_finder(ctx, typ)
        _get_custom_form(ctx)

    return render(request, "larpmanager/orga/writing/" + nm + "s.html", ctx)


def writing_bulk(ctx, request, typ):
    """Handle bulk operations for different writing element types.

    Args:
        ctx: Context dictionary with event data
        request: Django HTTP request object
        typ: Writing element type class

    Side effects:
        Executes bulk operations through type-specific handlers
    """
    bulks = {Character: handle_bulk_characters, Quest: handle_bulk_quest, Trait: handle_bulk_trait}

    if typ in bulks:
        bulks[typ](request, ctx)


def _get_custom_form(ctx):
    """Setup custom form questions and field names for writing elements.

    Args:
        ctx: Context dictionary to populate with form data

    Side effects:
        Updates ctx with form_questions and fields_name dictionaries
    """
    if not ctx["writing_typ"]:
        return

    # default name for fields
    ctx["fields_name"] = {WritingQuestionType.NAME.value: _("Name")}

    que = ctx["event"].get_elements(WritingQuestion).order_by("order")
    que = que.filter(applicable=ctx["writing_typ"])
    ctx["form_questions"] = {}
    for q in que:
        q.basic_typ = q.typ in BaseQuestionType.get_basic_types()
        if q.typ in ctx["fields_name"].keys():
            ctx["fields_name"][q.typ] = q.name
        else:
            ctx["form_questions"][q.id] = q


def writing_list_query(ctx, ev, typ):
    """
    Build optimized database query for writing element lists.

    Args:
        ctx: Context dictionary to store query results
        ev: Event instance
        typ: Writing element model class

    Returns:
        tuple: (text_fields list, writing boolean flag)
    """
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
    """
    Add editor-type question fields to text fields list and retrieve cached data.

    Args:
        ctx: Context dictionary with event and writing type information
        text_fields: List of text field names to extend
        typ: Writing element model class
    """
    # add editor type questions
    que = ctx["event"].get_elements(WritingQuestion).filter(applicable=ctx["writing_typ"])
    for que_id in que.filter(typ=BaseQuestionType.EDITOR).values_list("pk", flat=True):
        text_fields.append(str(que_id))

    retrieve_cache_text_field(ctx, text_fields, typ)


def retrieve_cache_text_field(ctx, text_fields, typ):
    """
    Retrieve and attach cached text field data to writing elements.

    Args:
        ctx: Context dictionary with list of elements
        text_fields: List of text field names to cache
        typ: Writing element model class
    """
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
    """Prepare context data for writing list display and configuration.

    Args:
        ctx: Template context dictionary to update
        request: HTTP request object with user information
    """
    try:
        name_que = (
            ctx["event"]
            .get_elements(WritingQuestion)
            .filter(applicable=ctx["writing_typ"], typ=WritingQuestionType.NAME)
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

    ctx["writing_unimportant"] = ctx["event"].get_config("writing_unimportant", False)


def writing_list_plot(ctx):
    """Build character associations for plot list display.

    Args:
        ctx: Context dictionary with list of plots and event data

    Side effects:
        Adds chars dictionary to context and attaches character lists to plot objects
    """
    rels = get_event_rels_cache(ctx["event"]).get("plots", {})

    for el in ctx["list"]:
        el.character_rels = rels.get(el.id, {}).get("character_rels", [])


def writing_list_faction(ctx):
    rels = get_event_rels_cache(ctx["event"]).get("factions", {})

    for el in ctx["list"]:
        el.character_rels = rels.get(el.id, {}).get("character_rels", [])


def writing_list_speedlarp(ctx):
    rels = get_event_rels_cache(ctx["event"]).get("speedlarps", {})

    for el in ctx["list"]:
        el.character_rels = rels.get(el.id, {}).get("character_rels", [])


def writing_list_prologue(ctx):
    rels = get_event_rels_cache(ctx["event"]).get("prologues", {})

    for el in ctx["list"]:
        el.character_rels = rels.get(el.id, {}).get("character_rels", [])


def writing_list_char(ctx):
    """Enhance character list with feature-specific data and relationships.

    Args:
        ctx: Context dictionary containing character list, features, and event data
    """
    if "user_character" in ctx["features"]:
        ctx["list"] = ctx["list"].select_related("player")

    if "campaign" in ctx["features"] and ctx["event"].parent:
        # add check if the character is signed up to the event
        ctx["list"] = ctx["list"].annotate(
            has_registration=Exists(
                RegistrationCharacterRel.objects.filter(
                    character=OuterRef("pk"), reg__run_id=ctx["run"].id, reg__cancellation_date__isnull=True
                )
            )
        )

    rels = get_event_rels_cache(ctx["event"]).get("characters", {})

    if "relationships" in ctx["features"]:
        for el in ctx["list"]:
            el.relationships_rels = rels.get(el.id, {}).get("relationships_rels", [])

    if "plot" in ctx["features"]:
        for el in ctx["list"]:
            el.plot_rels = rels.get(el.id, {}).get("plot_rels", [])

    if "faction" in ctx["features"]:
        for el in ctx["list"]:
            el.faction_rels = rels.get(el.id, {}).get("faction_rels", [])

    if "speedlarp" in ctx["features"]:
        for el in ctx["list"]:
            el.speedlarp_rels = rels.get(el.id, {}).get("speedlarp_rels", [])

    if "prologue" in ctx["features"]:
        for el in ctx["list"]:
            el.prologue_rels = rels.get(el.id, {}).get("prologue_rels", [])

    # add character configs
    char_add_addit(ctx)


def char_add_addit(ctx):
    """
    Add additional configuration data to all characters in the context list.

    Args:
        ctx: Context dictionary containing character list and event information
    """
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
    """
    Display writing element view with character data and relationships.

    Args:
        request: HTTP request object
        ctx: Context dictionary with element data
        nm: Name of the writing element type

    Returns:
        HttpResponse: Rendered writing view template
    """
    ctx["el"] = ctx[nm]
    ctx["el"].data = ctx["el"].show_complete()
    ctx["nm"] = nm
    get_event_cache_all(ctx)

    if nm == "character":
        if ctx["el"].number in ctx["chars"]:
            ctx["char"] = ctx["chars"][ctx["el"].number]
        ctx["character"] = ctx["el"]
        get_character_sheet(ctx)
        get_character_relationships(ctx)
    else:
        applicable = QuestionApplicable.get_applicable(nm)
        if applicable:
            ctx["element"] = get_writing_element_fields(ctx, nm, applicable, ctx["el"].id, only_visible=False)
        ctx["sheet_char"] = ctx["el"].show_complete()

    if nm == "plot":
        ctx["sheet_plots"] = (
            PlotCharacterRel.objects.filter(plot=ctx["el"]).order_by("character__number").select_related("character")
        )

    return render(request, "larpmanager/orga/writing/view.html", ctx)


def writing_versions(request, ctx, nm, tp):
    """Display text versions with diff comparison for writing elements.

    Args:
        request: HTTP request object
        ctx: Context dictionary with writing element data
        nm: Name of the writing element
        tp: Type identifier for text versions

    Returns:
        HttpResponse: Rendered versions template with diff data
    """
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
    """Django signal handler to replace character names before saving.

    Args:
        sender: Model class sending the signal
        instance: Character instance being saved
        *args: Additional positional arguments
        **kwargs: Additional keyword arguments
    """
    if not instance.pk:
        return

    replace_chars_all(instance)
