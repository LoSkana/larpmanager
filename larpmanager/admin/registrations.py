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

from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin

from larpmanager.admin.base import (
    CharacterFilter,
    DefModelAdmin,
    EventFilter,
    MemberFilter,
    RegistrationFilter,
    RunFilter,
)
from larpmanager.models.form import RegistrationAnswer, RegistrationChoice, RegistrationOption, RegistrationQuestion
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationSection,
    RegistrationTicket,
)


class RegistrationQuestionInline(admin.TabularInline):
    """Inline admin for RegistrationQuestion model within parent admin."""

    model = RegistrationQuestion
    fields = ("name", "description")
    show_change_link = True


class RegistrationOptionInline(admin.TabularInline):
    """Inline admin for RegistrationOption model within parent admin."""

    model = RegistrationOption
    exclude = ("search",)


class RegistrationQuestionFilter(AutocompleteFilter):
    """Admin filter for RegistrationQuestion autocomplete."""

    title = "RegistrationQuestion"
    field_name = "question"


@admin.register(Registration)
class RegistrationAdmin(DefModelAdmin):
    """Admin interface for Registration model."""

    exclude = ("search",)
    list_display: ClassVar[tuple] = ("id", "run", "member", "ticket", "quotas", "cancellation_date", "uuid")
    search_fields: ClassVar[tuple] = ("id", "search", "uuid")
    autocomplete_fields: ClassVar[list] = ["run", "member", "ticket"]
    list_filter = (RunFilter, MemberFilter, "cancellation_date")


@admin.register(RegistrationTicket)
class RegistrationTicketAdmin(DefModelAdmin):
    """Admin interface for RegistrationTicket model."""

    exclude: ClassVar[tuple] = ("name",)
    list_display: ClassVar[tuple] = ("id", "uuid")
    search_fields: ClassVar[tuple] = ("id", "search", "uuid")
    autocomplete_fields: ClassVar[list] = ["event"]
    list_filter = (EventFilter,)


@admin.register(RegistrationSection)
class RegistrationSectionAdmin(DefModelAdmin):
    """Admin interface for RegistrationSection model."""

    exclude: ClassVar[tuple] = ("search",)
    list_display: ClassVar[tuple] = ("id", "uuid")
    search_fields: ClassVar[tuple] = ("id", "search", "uuid")
    autocomplete_fields: ClassVar[list] = ["event"]
    list_filter = (EventFilter,)
    inlines: ClassVar[list] = [
        RegistrationQuestionInline,
    ]


@admin.register(RegistrationQuestion)
class RegistrationQuestionAdmin(DefModelAdmin):
    """Admin interface for RegistrationQuestion model."""

    exclude = ("search",)
    search_fields: ClassVar[tuple] = ("id", "search", "uuid")
    list_display = ("id", "typ", "event", "name", "status", "description", "uuid")
    autocomplete_fields: ClassVar[list] = ["event", "section", "factions", "tickets", "allowed"]
    list_filter: ClassVar[tuple] = (EventFilter,)

    inlines: ClassVar[list] = [
        RegistrationOptionInline,
    ]


@admin.register(RegistrationOption)
class RegistrationOptionAdmin(DefModelAdmin):
    """Admin interface for RegistrationOption model."""

    exclude: ClassVar[tuple] = ("search",)
    list_display: ClassVar[tuple] = ("id", "uuid")
    search_fields: ClassVar[tuple] = ("id", "search", "uuid")
    autocomplete_fields: ClassVar[list] = ["question", "event"]
    list_filter = (RegistrationQuestionFilter,)


@admin.register(RegistrationChoice)
class RegistrationChoiceAdmin(DefModelAdmin):
    """Admin interface for RegistrationChoice model."""

    autocomplete_fields: ClassVar[list] = ["question", "option", "reg"]
    list_filter = (
        RegistrationFilter,
        RegistrationQuestionFilter,
    )


@admin.register(RegistrationAnswer)
class RegistrationAnswerAdmin(DefModelAdmin):
    """Admin interface for RegistrationAnswer model."""

    autocomplete_fields: ClassVar[list] = ["question", "reg"]
    list_filter = (
        RegistrationFilter,
        RegistrationQuestionFilter,
    )


@admin.register(RegistrationCharacterRel)
class RegistrationCharacterRelAdmin(DefModelAdmin):
    """Admin interface for RegistrationCharacterRel model."""

    list_display: ClassVar[tuple] = ("id", "character", "reg")
    search_fields: ClassVar[list] = ["id", "character", "reg"]
    autocomplete_fields: ClassVar[list] = ["character", "reg"]
    list_filter = (CharacterFilter, RegistrationFilter)
