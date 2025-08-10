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

from larpmanager.admin.base import CharacterFilter, DefModelAdmin, EventFilter, reduced
from larpmanager.models.experience import AbilityPx, AbilityTypePx, DeliveryPx
from larpmanager.models.form import (
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.writing import (
    Character,
    CharacterConfig,
    Relationship,
)


class WritingQuestionFilter(AutocompleteFilter):
    title = "WritingQuestion"
    field_name = "question"


@admin.register(Character)
class CharacterAdmin(DefModelAdmin):
    list_display = ("number", "name", "teaser", "event")
    search_fields = ("name", "teaser")
    list_filter = (EventFilter,)
    autocomplete_fields = ["event", "characters", "progress", "assigned"]


@admin.register(CharacterConfig)
class CharacterConfigAdmin(DefModelAdmin):
    list_display = ("character", "name", "value")
    search_fields = ("name",)
    list_filter = (CharacterFilter,)
    autocomplete_fields = ["character"]


@admin.register(WritingQuestion)
class WritingQuestionAdmin(DefModelAdmin):
    list_display = ("event", "typ", "name", "description_red", "order", "status", "visibility", "applicable")
    exclude = ("search",)
    search_fields = ("search", "name")
    autocomplete_fields = ["event"]
    list_filter = (EventFilter, "applicable")

    @staticmethod
    def description_red(instance):
        return reduced(instance.description)


@admin.register(WritingOption)
class WritingOptionAdmin(DefModelAdmin):
    list_display = ("question", "name", "event", "details_red", "max_available", "order")
    exclude = ("search",)
    search_fields = ("search", "name")
    autocomplete_fields = ["question", "event"]
    list_filter = (WritingQuestionFilter, EventFilter)

    @staticmethod
    def details_red(instance):
        return reduced(instance.description)


@admin.register(WritingChoice)
class WritingChoiceAdmin(DefModelAdmin):
    list_display = ("id", "question", "option", "element_id")
    autocomplete_fields = ["question", "option"]
    list_filter = (WritingQuestionFilter,)


@admin.register(WritingAnswer)
class WritingAnswerAdmin(DefModelAdmin):
    list_display = ("id", "question", "text_red", "element_id")
    autocomplete_fields = ["question"]
    list_filter = (WritingQuestionFilter,)

    @staticmethod
    def text_red(instance):
        return reduced(instance.text)


class SourceFilter(AutocompleteFilter):
    title = "Member"
    field_name = "source"


class TargetFilter(AutocompleteFilter):
    title = "Member"
    field_name = "target"


@admin.register(Relationship)
class RelationshipAdmin(DefModelAdmin):
    list_display = ("source", "target", "text")
    list_filter = (SourceFilter, TargetFilter)
    autocomplete_fields = ["source", "target"]


@admin.register(AbilityTypePx)
class AbilityTypePxAdmin(DefModelAdmin):
    list_display = ("event", "name")
    list_filter = (EventFilter,)
    autocomplete_fields = ["event"]
    search_fields = ["name"]


@admin.register(AbilityPx)
class AbilityPxAdmin(DefModelAdmin):
    list_display = ("event", "name", "typ", "cost")
    list_filter = (EventFilter,)
    autocomplete_fields = ["event", "characters", "typ", "prerequisites"]
    search_fields = ["name"]


@admin.register(DeliveryPx)
class DeliveryPxAdmin(DefModelAdmin):
    list_display = ("event", "name", "amount")
    list_filter = (EventFilter,)
    autocomplete_fields = ["characters"]


class PlotFilter(AutocompleteFilter):
    title = "Plot"
    field_name = "plot"
