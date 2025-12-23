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

from larpmanager.admin.base import DefModelAdmin, EventFilter, MemberFilter, RunFilter
from larpmanager.models.casting import Casting, CastingAvoid, Quest, QuestType, Trait


class TraitInline(admin.TabularInline):
    """Inline admin for Trait model within Quest admin."""

    model = Trait
    fields = (
        "number",
        "name",
    )


@admin.register(Quest)
class QuestAdmin(DefModelAdmin):
    """Admin interface for Quest model."""

    list_display = ("number", "name", "event")
    inlines: ClassVar[list] = [
        TraitInline,
    ]
    list_filter = (EventFilter,)
    autocomplete_fields: ClassVar[list] = ["typ", "event", "progress", "assigned"]
    search_fields: ClassVar[tuple] = ("id", "name")


@admin.register(QuestType)
class QuestTypeAdmin(DefModelAdmin):
    """Admin interface for QuestType model."""

    list_display: ClassVar[tuple] = ("name", "event")
    list_filter = (EventFilter,)
    autocomplete_fields: ClassVar[list] = ["event", "progress", "assigned"]
    search_fields: ClassVar[tuple] = ("id", "name")


@admin.register(Casting)
class CastingAdmin(DefModelAdmin):
    """Admin interface for Casting model."""

    list_display = ("run", "member", "element", "pref", "typ")
    autocomplete_fields = (
        "run",
        "member",
    )
    list_filter = (RunFilter, MemberFilter, "nope")


@admin.register(CastingAvoid)
class CastingAvoidAdmin(DefModelAdmin):
    """Admin interface for CastingAvoid model."""

    list_display = ("run", "member", "typ", "text")
    autocomplete_fields = (
        "run",
        "member",
    )
    list_filter = (RunFilter, MemberFilter)
