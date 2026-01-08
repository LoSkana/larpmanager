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

from typing import ClassVar

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
    """Admin interface for TextVersion model."""

    list_display = ("id", "tp", "eid", "version", "dl", "uuid")
    list_filter: ClassVar[tuple] = ("tp",)
    search_fields: ClassVar[tuple] = ("id", "eid", "uuid")
    autocomplete_fields: ClassVar[list] = ["member"]


@admin.register(Plot)
class PlotAdmin(DefModelAdmin):
    """Admin interface for Plot model."""

    list_display: ClassVar[tuple] = ("id", "name", "event", "uuid")
    list_filter: ClassVar[tuple] = (EventFilter,)
    autocomplete_fields: ClassVar[list] = ["characters", "event", "progress", "assigned"]
    search_fields: ClassVar[list] = ["id", "name", "uuid"]


@admin.register(PlotCharacterRel)
class PlotCharacterRelAdmin(DefModelAdmin):
    """Admin interface for PlotCharacterRel model."""

    list_display: ClassVar[tuple] = ("id", "plot", "character", "order")
    list_filter = (CharacterFilter, PlotFilter)
    search_fields: ClassVar[list] = ["id", "plot__name", "character__name"]
    autocomplete_fields: ClassVar[list] = ["plot", "character"]


@admin.register(Faction)
class FactionAdmin(DefModelAdmin):
    """Admin interface for Faction model."""

    list_display: ClassVar[tuple] = ("id", "name", "event", "number", "uuid")
    list_filter: ClassVar[tuple] = (EventFilter,)
    autocomplete_fields: ClassVar[list] = ["characters", "event", "progress", "assigned"]
    search_fields: ClassVar[list] = ["id", "name", "uuid"]


@admin.register(Trait)
class TraitAdmin(DefModelAdmin):
    """Admin interface for Trait model."""

    list_display = ("id", "number", "name", "event", "quest", "uuid")
    list_filter: ClassVar[tuple] = (EventFilter,)
    search_fields: ClassVar[tuple] = ("id", "name", "uuid")
    autocomplete_fields: ClassVar[list] = ["quest", "traits", "event", "progress", "assigned"]


@admin.register(Handout)
class HandoutAdmin(DefModelAdmin):
    """Admin interface for Handout model."""

    list_display: ClassVar[tuple] = ("id", "event", "name", "number", "uuid")
    list_filter = (EventFilter,)
    search_fields: ClassVar[list] = ["id", "uuid"]
    autocomplete_fields: ClassVar[list] = ["event", "progress", "assigned"]


@admin.register(HandoutTemplate)
class HandoutTemplateAdmin(DefModelAdmin):
    """Admin interface for HandoutTemplate model."""

    list_display: ClassVar[tuple] = ("event", "name", "number")
    list_filter = (EventFilter,)
    autocomplete_fields: ClassVar[list] = ["event"]


@admin.register(Prologue)
class PrologueAdmin(DefModelAdmin):
    """Admin interface for Prologue model."""

    list_display: ClassVar[tuple] = ("id", "number", "typ", "event", "uuid")
    list_filter = (EventFilter,)
    search_fields: ClassVar[list] = ["id", "uuid"]
    autocomplete_fields: ClassVar[list] = ["typ", "characters", "event", "progress", "assigned"]


@admin.register(PrologueType)
class PrologueTypeAdmin(DefModelAdmin):
    """Admin interface for PrologueType model."""

    list_display: ClassVar[tuple] = ("id", "name", "event", "uuid")
    list_filter: ClassVar[tuple] = (EventFilter,)
    autocomplete_fields: ClassVar[list] = ["event", "progress", "assigned"]
    search_fields: ClassVar[list] = ["id", "name", "uuid"]


@admin.register(AssignmentTrait)
class AssignmentTraitAdmin(DefModelAdmin):
    """Admin interface for AssignmentTrait model."""

    list_display = ("run", "member", "trait", "typ")
    list_filter = (RunFilter, MemberFilter, TraitFilter)
    autocomplete_fields = ("run", "member", "trait")


@admin.register(SpeedLarp)
class SpeedLarpAdmin(DefModelAdmin):
    """Admin interface for SpeedLarp model."""

    list_display = ("id", "name", "event", "typ", "station", "uuid")
    search_fields: ClassVar[list] = ["id", "uuid"]
    autocomplete_fields: ClassVar[list] = ["characters", "event", "progress", "assigned"]
