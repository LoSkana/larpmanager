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
    model = RegistrationQuestion
    fields = ("name", "description")
    show_change_link = True


class RegistrationOptionInline(admin.TabularInline):
    model = RegistrationOption
    exclude = ("search",)


class RegistrationQuestionFilter(AutocompleteFilter):
    title = "RegistrationQuestion"
    field_name = "question"


@admin.register(Registration)
class RegistrationAdmin(DefModelAdmin):
    exclude = ("search",)
    list_display = ("id", "run", "member", "ticket", "quotas", "cancellation_date")
    search_fields = ("search",)
    autocomplete_fields = ["run", "member", "ticket"]
    list_filter = (RunFilter, MemberFilter, "cancellation_date")


@admin.register(RegistrationTicket)
class RegistrationTicketAdmin(DefModelAdmin):
    exclude = ("name",)
    search_fields = ("search",)
    autocomplete_fields = ["event"]
    list_filter = (EventFilter,)


@admin.register(RegistrationSection)
class RegistrationSectionAdmin(DefModelAdmin):
    exclude = ("search",)
    search_fields = ("search",)
    autocomplete_fields = ["event"]
    list_filter = (EventFilter,)
    inlines = [
        RegistrationQuestionInline,
    ]


@admin.register(RegistrationQuestion)
class RegistrationQuestionAdmin(DefModelAdmin):
    exclude = ("search",)
    search_fields = ("search",)
    list_display = ("typ", "event", "name", "status", "description")
    autocomplete_fields = ["event", "section", "factions", "tickets", "allowed"]
    list_filter = (EventFilter,)

    inlines = [
        RegistrationOptionInline,
    ]


@admin.register(RegistrationOption)
class RegistrationOptionAdmin(DefModelAdmin):
    exclude = ("search",)
    search_fields = ("search",)
    autocomplete_fields = ["question", "event"]
    list_filter = (RegistrationQuestionFilter,)


@admin.register(RegistrationChoice)
class RegistrationChoiceAdmin(DefModelAdmin):
    autocomplete_fields = ["question", "option", "reg"]
    list_filter = (
        RegistrationFilter,
        RegistrationQuestionFilter,
    )


@admin.register(RegistrationAnswer)
class RegistrationAnswerAdmin(DefModelAdmin):
    autocomplete_fields = ["question", "reg"]
    list_filter = (
        RegistrationFilter,
        RegistrationQuestionFilter,
    )


@admin.register(RegistrationCharacterRel)
class RegistrationCharacterRelAdmin(DefModelAdmin):
    list_display = ("character", "reg")
    search_fields = ["character", "reg"]
    autocomplete_fields = ["character", "reg"]
    list_filter = (CharacterFilter, RegistrationFilter)
