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

from larpmanager.admin.base import DefModelAdmin, EventFilter, MemberFilter, RunFilter
from larpmanager.models.casting import Casting, CastingAvoid, Quest, QuestType, Trait


class TraitInline(admin.TabularInline):
    model = Trait
    fields = (
        "number",
        "name",
    )


@admin.register(Quest)
class QuestAdmin(DefModelAdmin):
    list_display = ("number", "name", "event")
    inlines = [
        TraitInline,
    ]
    list_filter = (EventFilter,)
    autocomplete_fields = ["typ", "event", "progress", "assigned"]
    search_fields = ("name",)


@admin.register(QuestType)
class QuestTypeAdmin(DefModelAdmin):
    list_display = ("name", "event")
    list_filter = (EventFilter,)
    autocomplete_fields = ["event", "progress", "assigned"]
    search_fields = ("name",)


@admin.register(Casting)
class CastingAdmin(DefModelAdmin):
    list_display = ("run", "member", "element", "pref", "typ", "created", "updated")
    autocomplete_fields = (
        "run",
        "member",
    )
    list_filter = (RunFilter, MemberFilter, "nope")


@admin.register(CastingAvoid)
class CastingAvoidAdmin(DefModelAdmin):
    list_display = ("run", "member", "typ", "text")
    autocomplete_fields = (
        "run",
        "member",
    )
    list_filter = (RunFilter, MemberFilter)
