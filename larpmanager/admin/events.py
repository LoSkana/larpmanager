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

from larpmanager.admin.base import AssociationFilter, DefModelAdmin, EventFilter, RunFilter
from larpmanager.models.event import Event, EventConfig, EventText, PreRegistration, ProgressStep, Run, RunConfig


@admin.register(ProgressStep)
class ProgressStepAdmin(DefModelAdmin):
    """Admin interface for ProgressStep model."""

    list_display: ClassVar[tuple] = ("id", "uuid")
    search_fields: ClassVar[tuple] = ("id", "name", "uuid")
    autocomplete_fields: ClassVar[list] = ["event"]


@admin.register(Event)
class EventAdmin(DefModelAdmin):
    """Admin interface for Event model."""

    list_display = ("name", "thumb", "slug", "association")
    search_fields: ClassVar[tuple] = ("id", "name")
    list_filter = (AssociationFilter,)
    autocomplete_fields: ClassVar[list] = ["association", "parent", "features"]


@admin.register(EventConfig)
class EventConfigAdmin(DefModelAdmin):
    """Admin interface for EventConfig model."""

    list_display = ("event", "name", "value")
    search_fields: ClassVar[tuple] = ("id", "name")
    list_filter = (EventFilter,)
    autocomplete_fields: ClassVar[list] = ["event"]


@admin.register(Run)
class RunAdmin(DefModelAdmin):
    """Admin interface for Run model."""

    exclude = ("search",)
    search_fields: ClassVar[tuple] = ("id", "search")
    list_display = ("id", "event", "number", "start", "end")
    autocomplete_fields: ClassVar[list] = ["event"]
    list_filter = (EventFilter, "development")


@admin.register(RunConfig)
class RunConfigAdmin(DefModelAdmin):
    """Admin interface for RunConfig model."""

    list_display = ("run", "name", "value")
    search_fields: ClassVar[tuple] = ("id", "name")
    list_filter = (RunFilter,)
    autocomplete_fields: ClassVar[list] = ["run"]


@admin.register(EventText)
class EventTextAdmin(DefModelAdmin):
    """Admin interface for EventText model."""

    list_display: ClassVar[tuple] = ("event", "typ", "language", "default")
    list_filter = (EventFilter, "typ", "language")
    autocomplete_fields: ClassVar[list] = ["event"]


@admin.register(PreRegistration)
class PreRegistrationAdmin(DefModelAdmin):
    """Admin interface for PreRegistration model."""

    list_display: ClassVar[tuple] = ("event", "member", "pref")
    list_filter = (EventFilter,)
    autocomplete_fields: ClassVar[list] = ["event", "member"]
