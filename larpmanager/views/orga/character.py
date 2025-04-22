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

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Q, Max
from django.db.models.functions import Length
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.character import (
    OrgaCharacterForm,
    OrgaCharacterOptionForm,
    OrgaCharacterQuestionForm,
)
from larpmanager.forms.writing import (
    UploadElementsForm,
    OrgaRelationshipForm,
)
from larpmanager.models.form import (
    CharacterQuestion,
    CharacterOption,
    CharacterChoice,
    CharacterAnswer,
    QuestionType,
)
from larpmanager.models.writing import (
    TextVersion,
    Plot,
    PlotCharacterRel,
    Faction,
    Prologue,
    SpeedLarp,
    Character,
    Relationship,
)
from larpmanager.cache.character import get_event_cache_all
from larpmanager.utils.common import (
    get_char,
    exchange_order,
    get_element,
    get_relationship,
)
from larpmanager.utils.character import get_chars_relations
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.download import orga_character_form_download
from larpmanager.utils.edit import backend_edit, writing_edit
from larpmanager.utils.upload import upload_elements
from larpmanager.utils.writing import writing_list, writing_view, writing_versions


@login_required
def orga_characters(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_characters")
    get_event_cache_all(ctx)
    ctx["user_character_approval"] = ctx["event"].get_config("user_character_approval", False)

    # default name for fields
    ctx["fields_name"] = {
        QuestionType.NAME.value: _("Name"),
        QuestionType.TEASER.value: _("Presentation"),
        QuestionType.SHEET.value: _("Text"),
    }

    if "character_form" in ctx["features"]:
        que = ctx["event"].get_elements(CharacterQuestion).order_by("order")
        ctx["char_questions"] = {}
        for q in que:
            if q.typ in ctx["fields_name"].keys():
                ctx["fields_name"][q.typ] = q.display
            else:
                ctx["char_questions"][q.id] = q

    return writing_list(request, ctx, Character, "character")


@login_required
def orga_characters_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_characters")
    get_event_cache_all(ctx)
    if num != 0:
        get_element(ctx, num, "character", Character)
    return writing_edit(request, ctx, OrgaCharacterForm, "character", TextVersion.CHARACTER)


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
def orga_characters_relationships(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_characters")
    get_char(ctx, num)
    ctx["direct"] = Relationship.objects.filter(source=ctx["character"]).order_by(
        Length("text").asc(), "target__number"
    )
    ctx["inverse"] = Relationship.objects.filter(target=ctx["character"]).order_by(
        Length("text").asc(), "source__number"
    )
    return render(request, "larpmanager/orga/characters/relationships.html", ctx)


@login_required
def orga_relationship_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_characters")
    if num != 0:
        get_relationship(ctx, num)

    def redr(ctx):
        return redirect(
            "orga_characters_relationships",
            s=ctx["event"].slug,
            n=ctx["run"].number,
            num=ctx["element"].source_id,
        )

    return writing_edit(request, ctx, OrgaRelationshipForm, "relationship", TextVersion.RELATIONSHIP, redr=redr)


@login_required
def orga_characters_view(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_characters")
    get_char(ctx, num)
    get_event_cache_all(ctx)
    return writing_view(request, ctx, "character")


@login_required
def orga_characters_versions(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_characters")
    get_char(ctx, num)
    return writing_versions(request, ctx, "character", TextVersion.CHARACTER)


@login_required
def orga_characters_summary(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_characters")
    get_char(ctx, num)
    ctx["factions"] = []
    for p in ctx["character"].factions_list.all():
        ctx["factions"].append(p.show_complete())
    ctx["plots"] = []
    for p in ctx["character"].plots.all():
        ctx["plots"].append(p.show_complete())
    return render(request, "larpmanager/orga/characters_summary.html", ctx)


@login_required
def orga_character_form_list(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_characters")
    event = ctx["event"]
    if event.parent:
        event = event.parent
    eid = request.POST.get("num")
    q = event.get_elements(CharacterQuestion).get(pk=eid)

    res = {}

    if q.typ in [QuestionType.SINGLE, QuestionType.MULTIPLE]:
        cho = {}
        for opt in event.get_elements(CharacterOption).filter(question=q):
            cho[opt.id] = opt.display

        for el in CharacterChoice.objects.filter(question=q, character__event=event):
            if el.character_id not in res:
                res[el.character_id] = []
            res[el.character_id].append(cho[el.option_id])

    elif q.typ in [QuestionType.TEXT, QuestionType.PARAGRAPH]:
        for el in CharacterAnswer.objects.filter(question=q, character__event=event):
            res[el.character_id] = el.text

    return JsonResponse({q.id: res})


@login_required
def orga_character_form_email(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_characters")
    event = ctx["event"]
    if event.parent:
        event = event.parent
    eid = request.POST.get("num")
    q = event.get_elements(CharacterQuestion).get(pk=eid)

    res = {}

    if q.typ not in [QuestionType.SINGLE, QuestionType.MULTIPLE]:
        return

    cho = {}
    for opt in event.get_elements(CharacterOption).filter(question=q):
        cho[opt.id] = opt.display

    for el in CharacterChoice.objects.filter(question=q, character__event=event).select_related(
        "character", "character__player"
    ):
        if el.option_id not in res:
            res[el.option_id] = {"emails": [], "names": []}
        res[el.option_id]["emails"].append(str(el.character))
        if el.character.player:
            res[el.option_id]["names"].append(el.character.player.email)

    n_res = {}
    for opt_id in res:
        n_res[cho[opt_id]] = res[opt_id]

    return JsonResponse(n_res)


@login_required
def orga_character_form(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_character_form")

    if request.method == "POST":
        if request.POST.get("download") == "1":
            return orga_character_form_download(request, ctx)

        return upload_elements(request, ctx, CharacterQuestion, "character_question", "orga_character_form")

    ctx["form"] = UploadElementsForm()
    ctx["upload"] = (
        _("typ (type: 's' for single choice, 'm' for multiple choice, 't' for short text, 'p' for long text)") + ", "
    )
    ctx["upload"] += _("display (question text)") + ", " + _("description (application description)") + ", "
    ctx["upload"] += (
        _("status of application: 'o' for optional, 'm' mandatory, 'c' creation, 'd' disabled, 'h' hidden") + ", "
    )
    ctx["upload"] += _("visibility (demand visibility: 's' for Searchable, 'c' for Public, 'e' for Private") + ", "
    ctx["upload"] += (
        _("options (number of options)")
        + ", "
        + _(
            "for each option five columns: name, description, available seats (0 for "
            "infinite), prerequisite options, ticket required"
        )
    )

    ctx["download"] = 1

    ctx["list"] = ctx["event"].get_elements(CharacterQuestion).order_by("order").prefetch_related("options")
    for el in ctx["list"]:
        el.options_list = el.options.order_by("order")

    ctx["approval"] = ctx["event"].get_config("user_character_approval", False)

    return render(request, "larpmanager/orga/characters/form.html", ctx)


@login_required
def orga_character_form_edit(request, s, n, num):
    perm = "orga_character_form"
    ctx = check_event_permission(request, s, n, perm)
    if backend_edit(request, ctx, OrgaCharacterQuestionForm, num, assoc=False):
        if str(request.POST.get("new_option", "")) == "1":
            return redirect(orga_character_options_new, s=ctx["event"].slug, n=ctx["run"].number, num=ctx["saved"].id)
        return redirect(perm, s=ctx["event"].slug, n=ctx["run"].number)

    ctx["list"] = CharacterOption.objects.filter(question=ctx["el"]).order_by("order")

    return render(request, "larpmanager/orga/characters/form_edit.html", ctx)


@login_required
def orga_character_form_order(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_character_form")
    exchange_order(ctx, CharacterQuestion, num)
    return redirect("orga_character_form", s=ctx["event"].slug, n=ctx["run"].number)


@login_required
def orga_character_options_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_character_form")
    return character_option_edit(ctx, num, request)


@login_required
def orga_character_options_new(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_character_form")
    ctx["question_id"] = num
    return character_option_edit(ctx, 0, request)


def character_option_edit(ctx, num, request):
    if backend_edit(request, ctx, OrgaCharacterOptionForm, num, assoc=False):
        return redirect(
            "orga_character_form_edit", s=ctx["event"].slug, n=ctx["run"].number, num=ctx["saved"].question_id
        )
    return render(request, "larpmanager/orga/edit.html", ctx)


@login_required
def orga_character_options_order(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_character_form")
    exchange_order(ctx, CharacterOption, num)
    return redirect(
        "orga_character_form_edit", s=ctx["event"].slug, n=ctx["run"].number, num=ctx["current"].question_id
    )


@login_required
def orga_relationships(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_characters")
    ctx["list"] = Relationship.objects.filter(Q(source__event=ctx["event"]) | Q(target__event=ctx["event"])).order_by(
        Length("text").asc()
    )
    return render(request, "larpmanager/orga/writing/relationships.html", ctx)


@login_required
def orga_check(request, s, n):
    ctx = check_event_permission(request, s, n)

    get_event_cache_all(ctx)

    checks = {}

    cache = {}

    chs_numbers = list(ctx["chars"].keys())
    id_number_map = {}
    for el in ctx["event"].get_elements(Character).values_list("number", "text"):
        if el[0] not in ctx["chars"]:
            continue
        ch = ctx["chars"][el[0]]
        ch["text"] = ch["teaser"] + el[1]
        id_number_map[ch["id"]] = ch["number"]

    if "plot" in ctx["features"]:
        que = PlotCharacterRel.objects.filter(character__number__in=chs_numbers)
        que = que.exclude(text__isnull=True).exclude(text__exact="")
        for el in que.values_list("character__number", "text"):
            ctx["chars"][el[0]]["text"] += el[1]

    checks["relat_missing"] = []
    checks["relat_extinct"] = []
    for c in ctx["chars"]:
        ch = ctx["chars"][c]
        (from_text, extinct) = get_chars_relations(ch["text"], chs_numbers)
        name = f"#{ch['number']} {ch['name']}"
        for e in extinct:
            checks["relat_extinct"].append((name, e))
        cache[c] = (name, from_text)

    for c in cache:
        (first, first_rel) = cache[c]
        for oth in first_rel:
            (second, second_rel) = cache[oth]
            if c not in second_rel:
                checks["relat_missing"].append({"f_id": c, "f_name": first, "s_id": oth, "s_name": second})

    # check extinct, missing, interloper
    for el in [Faction, Plot, Prologue, SpeedLarp]:
        nm = str(el.__name__).lower()
        if nm not in ctx["features"]:
            continue
        checks[nm + "_extinct"] = []
        checks[nm + "_missing"] = []
        checks[nm + "_interloper"] = []
        cache[nm] = {}
        # check s: all characters currently listed has
        for f in ctx["event"].get_elements(el).annotate(characters_map=ArrayAgg("characters")):
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

    # check speedlarp, no player has double
    if "speedlarp" in ctx["features"]:
        checks["speed_larps_double"] = []
        checks["speed_larps_missing"] = []
        max_typ = ctx["event"].get_elements(SpeedLarp).aggregate(Max("typ"))["typ__max"]
        if max_typ and max_typ > 0:
            speeds = {}
            for el in ctx["event"].get_elements(SpeedLarp).annotate(characters_map=ArrayAgg("characters")):
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
            for chnum, c in ctx["chars"].items():
                if c["special"] in [Character.PNG, Character.FILLER]:
                    continue
                if chnum not in speeds:
                    continue
                for typ in range(1, max_typ + 1):
                    if typ not in speeds[chnum]:
                        checks["speed_larps_missing"].append((typ, c))
                    if len(speeds[chnum][typ]) > 1:
                        checks["speed_larps_double"].append((typ, c))

    ctx["checks"] = checks
    # print(checks)
    return render(request, "larpmanager/orga/writing/check.html", ctx)
