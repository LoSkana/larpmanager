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

from django.contrib import admin

from larpmanager.admin.base import CharacterFilter, DefModelAdmin, EventFilter, MemberFilter, RunFilter, TraitFilter
from larpmanager.admin.character import PlotFilter
from larpmanager.models.casting import AssignmentTrait, Trait
from larpmanager.models.writing import (
    Faction,
    Handout,
    HandoutTemplate,
    Plot,
    PlotCharacterRel,
    Prologue,
    PrologueType,
    SpeedLarp,
    TextVersion,
)


@admin.register(TextVersion)
class TextVersionAdmin(DefModelAdmin):
    list_display = ("id", "tp", "eid", "version", "dl")
    list_filter = ("tp",)
    search_fields = ("eid",)
    autocomplete_fields = ["member"]


@admin.register(Plot)
class PlotAdmin(DefModelAdmin):
    list_display = ("id", "name", "event")
    list_filter = (EventFilter,)
    autocomplete_fields = ["characters", "event", "progress", "assigned"]
    search_fields = ["name"]


@admin.register(PlotCharacterRel)
class PlotCharacterRelAdmin(DefModelAdmin):
    list_display = ("plot", "character")
    list_filter = (CharacterFilter, PlotFilter)
    autocomplete_fields = ["plot", "character"]


@admin.register(Faction)
class FactionAdmin(DefModelAdmin):
    list_display = ("name", "event", "number")
    list_filter = (EventFilter,)
    autocomplete_fields = ["characters", "event", "progress", "assigned"]
    search_fields = ["name"]


@admin.register(Trait)
class TraitAdmin(DefModelAdmin):
    list_display = ("number", "name", "event", "quest")
    list_filter = (EventFilter,)
    search_fields = ("name",)
    autocomplete_fields = ["quest", "traits", "event", "progress", "assigned"]


@admin.register(Handout)
class HandoutAdmin(DefModelAdmin):
    list_display = ("event", "name", "number")
    list_filter = (EventFilter,)
    autocomplete_fields = ["event", "progress", "assigned"]


@admin.register(HandoutTemplate)
class HandoutTemplateAdmin(DefModelAdmin):
    list_display = ("event", "name", "number")
    list_filter = (EventFilter,)
    autocomplete_fields = ["event"]


@admin.register(Prologue)
class PrologueAdmin(DefModelAdmin):
    list_display = ("number", "typ", "event")
    list_filter = (EventFilter,)
    autocomplete_fields = ["typ", "characters", "event", "progress", "assigned"]


@admin.register(PrologueType)
class PrologueTypeAdmin(DefModelAdmin):
    list_display = ("name", "event")
    list_filter = (EventFilter,)
    autocomplete_fields = ["event", "progress", "assigned"]
    search_fields = ["name"]


@admin.register(AssignmentTrait)
class AssignmentTraitAdmin(DefModelAdmin):
    list_display = ("run", "member", "trait", "typ")
    list_filter = (RunFilter, MemberFilter, TraitFilter)
    autocomplete_fields = ("run", "member", "trait")


@admin.register(SpeedLarp)
class SpeedLarpAdmin(DefModelAdmin):
    list_display = ("name", "event", "typ", "station")
    autocomplete_fields = ["characters", "event", "progress", "assigned"]
