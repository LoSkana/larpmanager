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
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from larpmanager.cache.character import get_event_cache_all
from larpmanager.forms.event import OrgaProgressStepForm
from larpmanager.forms.writing import (
    FactionForm,
    HandoutForm,
    HandoutTemplateForm,
    PlotForm,
    PrologueForm,
    PrologueTypeForm,
    QuestForm,
    QuestTypeForm,
    SpeedLarpForm,
    TraitForm,
)
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import ProgressStep
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import (
    Character,
    Faction,
    Handout,
    HandoutTemplate,
    Plot,
    Prologue,
    PrologueType,
    SpeedLarp,
    TextVersion,
)
from larpmanager.utils.common import (
    exchange_order,
    get_element,
    get_handout,
    get_handout_template,
    get_plot,
    get_prologue,
    get_prologue_type,
    get_quest,
    get_quest_type,
    get_speedlarp,
    get_trait,
)
from larpmanager.utils.edit import orga_edit, writing_edit
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.pdf import (
    print_handout,
    return_pdf,
)
from larpmanager.utils.writing import writing_list, writing_versions, writing_view


@login_required
def orga_plots(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_plots")
    return writing_list(request, ctx, Plot, "plot")


@login_required
def orga_plots_view(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_plots")
    get_plot(ctx, num)
    return writing_view(request, ctx, "plot")


@login_required
def orga_plots_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_plots")
    if num != 0:
        get_element(ctx, num, "plot", Plot)
    return writing_edit(request, ctx, PlotForm, "plot", TextVersion.PLOT)


@login_required
def orga_plots_versions(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_plots")
    get_plot(ctx, num)
    return writing_versions(request, ctx, "plot", TextVersion.PLOT)


@login_required
def orga_factions(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_factions")
    return writing_list(request, ctx, Faction, "faction")


@login_required
def orga_factions_view(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_factions")
    get_element(ctx, num, "faction", Faction)
    return writing_view(request, ctx, "faction")


@login_required
def orga_factions_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_factions")
    if num != 0:
        get_element(ctx, num, "faction", Faction)
    return writing_edit(request, ctx, FactionForm, "faction", TextVersion.FACTION)


@login_required
def orga_factions_order(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_factions")
    exchange_order(ctx, Faction, num)
    return redirect("orga_factions", s=ctx["event"].slug, n=ctx["run"].number)


@login_required
def orga_factions_versions(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_factions")
    get_element(ctx, num, "faction", Faction)
    return writing_versions(request, ctx, "faction", TextVersion.FACTION)


@login_required
def orga_quest_types(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_quest_types")
    return writing_list(request, ctx, QuestType, "quest_type")


@login_required
def orga_quest_types_view(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_quest_types")
    get_quest_type(ctx, num)
    return writing_view(request, ctx, "quest_type")


@login_required
def orga_quest_types_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_quest_types")
    if num != 0:
        get_quest_type(ctx, num)
    return writing_edit(request, ctx, QuestTypeForm, "quest_type", TextVersion.QUEST_TYPE)


@login_required
def orga_quest_types_versions(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_quest_types")
    get_quest_type(ctx, num)
    return writing_versions(request, ctx, "quest_type", TextVersion.QUEST_TYPE)


@login_required
def orga_quests(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_quests")
    return writing_list(request, ctx, Quest, "quest")


@login_required
def orga_quests_view(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_quests")
    get_quest(ctx, num)
    return writing_view(request, ctx, "quest")


@login_required
def orga_quests_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_quests")
    if num != 0:
        get_element(ctx, num, "quest", Quest)
    return writing_edit(request, ctx, QuestForm, "quest", TextVersion.QUEST)


@login_required
def orga_quests_versions(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_quests")
    get_quest(ctx, num)
    return writing_versions(request, ctx, "quest", TextVersion.QUEST)


@login_required
def orga_traits(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_traits")
    return writing_list(request, ctx, Trait, "trait")


@login_required
def orga_traits_view(request, s, n, num):
    ctx = check_event_permission(request, s, n, "questbuilder")
    get_trait(ctx, num)
    return writing_view(request, ctx, "trait")


@login_required
def orga_traits_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_traits")
    if num != 0:
        get_trait(ctx, num)
    return writing_edit(request, ctx, TraitForm, "trait", TextVersion.TRAIT)


@login_required
def orga_traits_versions(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_traits")
    get_trait(ctx, num)
    return writing_versions(request, ctx, "trait", TextVersion.TRAIT)


@login_required
def orga_handouts(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_handouts")
    return writing_list(request, ctx, Handout, "handout")


@login_required
def orga_handouts_test(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_handouts")
    get_handout(ctx, num)
    return render(request, "pdf/sheets/handout.html", ctx)


@login_required
def orga_handouts_print(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_handouts")
    get_handout(ctx, num)
    fp = print_handout(ctx)
    return return_pdf(fp, str(ctx["handout"]))


@login_required
def orga_handouts_view(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_handouts")
    get_handout(ctx, num)
    return print_handout(ctx)


@login_required
def orga_handouts_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_handouts")
    if num != 0:
        get_handout(ctx, num)
    return writing_edit(request, ctx, HandoutForm, "handout", TextVersion.HANDOUT)


@login_required
def orga_handouts_versions(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_handouts")
    get_handout(ctx, num)
    return writing_versions(request, ctx, "handout", TextVersion.HANDOUT)


@login_required
def orga_handout_templates(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_handout_templates")
    return writing_list(request, ctx, HandoutTemplate, "handout_template")


@login_required
def orga_handout_templates_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_handout_templates")
    if num != 0:
        get_handout_template(ctx, num)
    return writing_edit(request, ctx, HandoutTemplateForm, "handout_template", None)


@login_required
def orga_prologue_types(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_prologue_types")
    return writing_list(request, ctx, PrologueType, "prologue_type")


@login_required
def orga_prologue_types_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_prologue_types")
    if num != 0:
        get_prologue_type(ctx, num)
    return writing_edit(request, ctx, PrologueTypeForm, "prologue_type", None)


@login_required
def orga_prologues(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_prologues")
    return writing_list(request, ctx, Prologue, "prologue")


@login_required
def orga_prologues_view(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_prologues")
    get_prologue(ctx, num)
    return writing_view(request, ctx, "prologue")


@login_required
def orga_prologues_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "prologue")
    if num != 0:
        get_prologue(ctx, num)
    return writing_edit(request, ctx, PrologueForm, "prologue", TextVersion.PROLOGUE)


@login_required
def orga_prologues_versions(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_prologues")
    get_prologue(ctx, num)
    return writing_versions(request, ctx, "prologue", TextVersion.PROLOGUE)


@login_required
def orga_speedlarps(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_speedlarps")
    return writing_list(request, ctx, SpeedLarp, "speedlarp")


@login_required
def orga_speedlarps_view(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_speedlarps")
    get_speedlarp(ctx, num)
    return writing_view(request, ctx, "speedlarp")


@login_required
def orga_speedlarps_edit(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_speedlarps")
    if num != 0:
        get_speedlarp(ctx, num)
    return writing_edit(request, ctx, SpeedLarpForm, "speedlarp", TextVersion.SPEEDLARP)


@login_required
def orga_speedlarps_versions(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_speedlarps")
    get_speedlarp(ctx, num)
    return writing_versions(request, ctx, "speedlarp", TextVersion.SPEEDLARP)


@login_required
def orga_assignments(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_assignments")
    get_event_cache_all(ctx)
    return render(request, "larpmanager/orga/writing/assignments.html", ctx)


@login_required
def orga_props(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_props")
    get_event_cache_all(ctx)
    que = ctx["event"].get_elements(Character).exclude(props__isnull=True)
    ctx["list"] = que.exclude(props__exact="").values_list("number", "props")
    return render(request, "larpmanager/orga/writing/props.html", ctx)


@login_required
def orga_progress_steps(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_progress_steps")
    return writing_list(request, ctx, ProgressStep, "progress_step")


@login_required
def orga_progress_steps_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_progress_steps", OrgaProgressStepForm, num)


@login_required
def orga_progress_steps_order(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_progress_steps")
    exchange_order(ctx, ProgressStep, num)
    return redirect("orga_progress_steps", s=ctx["event"].slug, n=ctx["run"].number)


@login_required
def orga_multichoice_available(request, s, n):
    if not request.method == "POST":
        return Http404()

    type = request.POST.get("type", "")
    class_name = None
    for v, nm in TextVersion.TEXT_CHOICES:
        if v == type:
            class_name = nm

    if not class_name:
        ctx = check_event_permission(request, s, n, "orga_registrations")
        taken_characters = RegistrationCharacterRel.objects.filter(reg__run_id=ctx["run"].id).values_list(
            "character_id", flat=True
        )
    else:
        ctx = check_event_permission(request, s, n, "orga_" + class_name.lower() + "s")
        main_class = globals()[class_name]
        eid = int(request.POST.get("eid", ""))
        taken_characters = main_class.objects.get(pk=eid).characters.values_list("id", flat=True)

    ctx["list"] = ctx["event"].get_elements(Character).order_by("number")
    ctx["list"] = ctx["list"].exclude(pk__in=taken_characters)
    res = [(el.id, str(el)) for el in ctx["list"]]
    return JsonResponse({"res": res})
