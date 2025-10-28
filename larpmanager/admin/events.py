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

from larpmanager.admin.base import AssociationFilter, DefModelAdmin, EventFilter, RunFilter
from larpmanager.models.event import Event, EventConfig, EventText, PreRegistration, ProgressStep, Run, RunConfig


@admin.register(ProgressStep)
class ProgressStepAdmin(DefModelAdmin):
    search_fields = ("name",)
    autocomplete_fields = ["event"]


@admin.register(Event)
class EventAdmin(DefModelAdmin):
    list_display = ("name", "thumb", "slug", "association")
    search_fields = ("name",)
    list_filter = (AssociationFilter,)
    autocomplete_fields = ["association", "parent", "features"]


@admin.register(EventConfig)
class EventConfigAdmin(DefModelAdmin):
    list_display = ("event", "name", "value")
    search_fields = ("name",)
    list_filter = (EventFilter,)
    autocomplete_fields = ["event"]


@admin.register(Run)
class RunAdmin(DefModelAdmin):
    exclude = ("search",)
    search_fields = ("search",)
    list_display = ("id", "event", "number", "start", "end")
    autocomplete_fields = ["event"]
    list_filter = (EventFilter, "development")


@admin.register(RunConfig)
class RunConfigAdmin(DefModelAdmin):
    list_display = ("run", "name", "value")
    search_fields = ("name",)
    list_filter = (RunFilter,)
    autocomplete_fields = ["run"]


@admin.register(EventText)
class EventTextAdmin(DefModelAdmin):
    list_display = ("event", "typ", "language", "default")
    list_filter = (EventFilter, "typ", "language")
    autocomplete_fields = ["event"]


@admin.register(PreRegistration)
class PreRegistrationAdmin(DefModelAdmin):
    list_display = ("event", "member", "pref")
    list_filter = (EventFilter,)
    autocomplete_fields = ["event", "member"]
