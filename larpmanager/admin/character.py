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

from larpmanager.admin.base import CharacterFilter, DefModelAdmin, EventFilter, reduced
from larpmanager.models.base import BaseModel
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
    """Admin filter for WritingQuestion autocomplete."""

    title = "WritingQuestion"
    field_name = "question"


@admin.register(Character)
class CharacterAdmin(DefModelAdmin):
    """Admin interface for Character model."""

    list_display = ("id", "number", "name", "teaser", "event", "uuid")
    search_fields: ClassVar[tuple] = ("id", "name", "teaser", "uuid")
    list_filter = (EventFilter,)
    autocomplete_fields: ClassVar[list] = ["event", "characters", "progress", "assigned"]


@admin.register(CharacterConfig)
class CharacterConfigAdmin(DefModelAdmin):
    """Admin interface for CharacterConfig model."""

    list_display = ("character", "name", "value")
    search_fields: ClassVar[tuple] = ("id", "name")
    list_filter = (CharacterFilter,)
    autocomplete_fields: ClassVar[list] = ["character"]


@admin.register(WritingQuestion)
class WritingQuestionAdmin(DefModelAdmin):
    """Admin interface for WritingQuestion model."""

    list_display = (
        "id",
        "event",
        "typ",
        "name",
        "description_red",
        "order",
        "status",
        "visibility",
        "applicable",
        "uuid",
    )
    exclude: ClassVar[tuple] = ("search",)
    search_fields: ClassVar[tuple] = ("id", "search", "name", "uuid")
    autocomplete_fields: ClassVar[list] = ["event"]
    list_filter = (EventFilter, "applicable")

    @staticmethod
    def description_red(instance: BaseModel) -> str:
        """Return reduced description for admin display."""
        return reduced(instance.description)


@admin.register(WritingOption)
class WritingOptionAdmin(DefModelAdmin):
    """Admin interface for WritingOption model."""

    list_display = ("id", "question", "name", "event", "details_red", "max_available", "order", "uuid")
    exclude: ClassVar[tuple] = ("search",)
    search_fields: ClassVar[tuple] = ("id", "search", "name", "uuid")
    autocomplete_fields: ClassVar[list] = ["question", "event"]
    list_filter = (WritingQuestionFilter, EventFilter)

    @staticmethod
    def details_red(instance: BaseModel) -> str:
        """Return reduced details for admin display."""
        return reduced(instance.description)


@admin.register(WritingChoice)
class WritingChoiceAdmin(DefModelAdmin):
    """Admin interface for WritingChoice model."""

    list_display = ("id", "question", "option", "element_id")
    autocomplete_fields: ClassVar[list] = ["question", "option"]
    list_filter = (WritingQuestionFilter,)


@admin.register(WritingAnswer)
class WritingAnswerAdmin(DefModelAdmin):
    """Admin interface for WritingAnswer model."""

    list_display = ("id", "question", "text_red", "element_id")
    autocomplete_fields: ClassVar[list] = ["question"]
    list_filter = (WritingQuestionFilter,)

    @staticmethod
    def text_red(instance: BaseModel) -> str:
        """Return reduced text for admin display."""
        return reduced(instance.text)


class SourceFilter(AutocompleteFilter):
    """Admin filter for source Character autocomplete."""

    title = "Member"
    field_name = "source"


class TargetFilter(AutocompleteFilter):
    """Admin filter for target Character autocomplete."""

    title = "Member"
    field_name = "target"


@admin.register(Relationship)
class RelationshipAdmin(DefModelAdmin):
    """Admin interface for Relationship model."""

    list_display: ClassVar[tuple] = ("source", "target", "text")
    list_filter = (SourceFilter, TargetFilter)
    autocomplete_fields: ClassVar[list] = ["source", "target"]


@admin.register(AbilityTypePx)
class AbilityTypePxAdmin(DefModelAdmin):
    """Admin interface for AbilityTypePx model."""

    list_display: ClassVar[tuple] = ("id", "event", "name", "uuid")
    list_filter: ClassVar[tuple] = (EventFilter,)
    autocomplete_fields: ClassVar[list] = ["event"]
    search_fields: ClassVar[list] = ["id", "name", "uuid"]


@admin.register(AbilityPx)
class AbilityPxAdmin(DefModelAdmin):
    """Admin interface for AbilityPx model."""

    list_display: ClassVar[tuple] = ("id", "name", "typ", "cost", "event", "uuid")
    list_filter: ClassVar[tuple] = (EventFilter,)
    autocomplete_fields: ClassVar[list] = ["event", "characters", "typ", "prerequisites", "requirements"]
    search_fields: ClassVar[list] = ["id", "name", "uuid"]


@admin.register(DeliveryPx)
class DeliveryPxAdmin(DefModelAdmin):
    """Admin interface for DeliveryPx model."""

    list_display: ClassVar[tuple] = ("id", "event", "name", "amount", "uuid")
    list_filter = (EventFilter,)
    search_fields: ClassVar[list] = ["id", "uuid"]
    autocomplete_fields: ClassVar[list] = ["characters"]


class PlotFilter(AutocompleteFilter):
    """Admin filter for Plot autocomplete."""

    title = "Plot"
    field_name = "plot"
