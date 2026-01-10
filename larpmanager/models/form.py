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
from __future__ import annotations

from typing import Any, ClassVar

from django.apps import apps
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import models
from django.db.models import F, Q, QuerySet
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from pilkit.processors import ResizeToFit

from larpmanager.models.base import BaseModel, UuidMixin
from larpmanager.models.event import Event
from larpmanager.models.member import Member
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationSection,
    RegistrationTicket,
)
from larpmanager.models.utils import UploadToPathAndRename, decimal_to_str
from larpmanager.models.writing import CharacterStatus, Faction


class BaseQuestionType(models.TextChoices):
    """Base question types for forms with static utility methods."""

    SINGLE = "s", _("Single choice")
    MULTIPLE = "m", _("Multiple choice")
    TEXT = "t", _("Single-line text")
    PARAGRAPH = "p", _("Multi-line text")
    EDITOR = "e", _("Advanced text editor")

    @staticmethod
    def get_answer_types() -> Any:
        """Get question types that use text answers.

        Returns:
            set: Question types requiring text input

        """
        return {BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, BaseQuestionType.EDITOR}

    @staticmethod
    def get_choice_types() -> Any:
        """Get question types that use choice options.

        Returns:
            set: Question types with predefined choices

        """
        return {BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE}

    @staticmethod
    def get_basic_types() -> Any:
        """Get all basic question types.

        Returns:
            set: All basic question type values

        """
        return BaseQuestionType.get_answer_types() | BaseQuestionType.get_choice_types()

    @classmethod
    def get_mapping(cls) -> Any:
        """Return mapping of question types to string identifiers."""
        return {
            BaseQuestionType.SINGLE: "single-choice",
            BaseQuestionType.MULTIPLE: "multi-choice",
            BaseQuestionType.TEXT: "short-text",
            BaseQuestionType.PARAGRAPH: "long-text",
            BaseQuestionType.EDITOR: "advanced",
        }


def extend_textchoices(name: str, base: models.TextChoices, extra: list[tuple[str, str, str]]) -> Any:
    """Extend Django TextChoices with additional options.

    Args:
        name: Name for the new TextChoices class
        base: Base TextChoices to extend
        extra: List of (name, value, label) tuples to add

    Returns:
        models.TextChoices: Extended choices class

    """
    members = [(m.name, (m.value, m.label)) for m in base] + [(n, (v, lbl)) for (n, v, lbl) in extra]
    return models.TextChoices(name, members)


WritingQuestionType = extend_textchoices(
    "WritingQuestionType",
    BaseQuestionType,
    [
        ("NAME", "name", _("Name")),
        ("TEASER", "teaser", _("Presentation")),
        ("SHEET", "text", _("Sheet")),
        ("COVER", "cover", _("Cover")),
        ("FACTIONS", "faction", _("Factions")),
        ("TITLE", "title", _("Title")),
        ("MIRROR", "mirror", _("Mirror")),
        ("HIDE", "hide", _("Hide")),
        ("PROGRESS", "progress", _("Progress")),
        ("ASSIGNED", "assigned", _("Assigned")),
        ("COMPUTED", "c", _("Computed")),
    ],
)


def get_def_writing_types() -> Any:
    """Get default writing question types.

    Returns:
        set: Set of default WritingQuestionType values

    """
    return {WritingQuestionType.NAME, WritingQuestionType.TEASER, WritingQuestionType.SHEET, WritingQuestionType.TITLE}


def get_writing_max_length() -> Any:
    """Get maximum length for writing content.

    Returns:
        int: Maximum character length for writing fields

    """
    return {
        WritingQuestionType.NAME,
        WritingQuestionType.SHEET,
        WritingQuestionType.TEASER,
        WritingQuestionType.TEXT,
        WritingQuestionType.PARAGRAPH,
        WritingQuestionType.MULTIPLE,
        WritingQuestionType.EDITOR,
    }


RegistrationQuestionType = extend_textchoices(
    "RegistrationQuestionType",
    BaseQuestionType,
    [
        ("TICKET", "ticket", _("Ticket")),
        ("ADDITIONAL", "additional_tickets", _("Additional")),
        ("PWYW", "pay_what_you_want", _("Pay what you want")),
        ("QUOTA", "reg_quotas", _("Rate")),
        ("SURCHARGE", "reg_surcharges", _("Surcharge")),
    ],
)


class QuestionStatus(models.TextChoices):
    """Status choices for form questions determining requirement level."""

    OPTIONAL = "o", _("Optional")
    MANDATORY = "m", _("Mandatory")
    DISABLED = "d", _("Disabled")
    HIDDEN = "h", _("Hidden")

    @classmethod
    def get_mapping(cls) -> Any:
        """Return mapping of question status values to string identifiers."""
        return {
            QuestionStatus.OPTIONAL: "optional",
            QuestionStatus.MANDATORY: "mandatory",
            QuestionStatus.DISABLED: "disabled",
            QuestionStatus.HIDDEN: "hidden",
        }


class QuestionVisibility(models.TextChoices):
    """Visibility choices for form questions controlling access level."""

    SEARCHABLE = "s", _("Searchable")
    PUBLIC = "c", _("Public")
    PRIVATE = "e", _("Private")
    HIDDEN = "h", _("Hidden")

    @classmethod
    def get_mapping(cls) -> Any:
        """Return mapping of visibility values to string identifiers."""
        return {
            QuestionVisibility.SEARCHABLE: "searchable",
            QuestionVisibility.PUBLIC: "public",
            QuestionVisibility.PRIVATE: "private",
            QuestionVisibility.HIDDEN: "hidden",
        }


class QuestionApplicable(models.TextChoices):
    """Defines which models questions can be applied to."""

    CHARACTER = "c", "character"
    PLOT = "p", "plot"
    FACTION = "f", "faction"
    QUEST = "q", "quest"
    TRAIT = "t", "trait"
    PROLOGUE = "r", "prologue"

    @classmethod
    def get_applicable(cls, model_name: str) -> str | None:
        """Get the applicable value for a given model name."""
        # Iterate through choices to find matching model name
        for choice_value, choice_label in cls.choices:
            if model_name.lower() == choice_label.lower():
                return choice_value
        return None

    @staticmethod
    def get_applicable_inverse(question_applicable_type: str) -> type:
        """Get the Django model class for a QuestionApplicable type."""
        # noinspection PyUnresolvedReferences
        # Get the lowercase label from QuestionApplicable enum
        model_name = QuestionApplicable(question_applicable_type).label.lower()
        # Retrieve and return the corresponding Django model
        return apps.get_model("larpmanager", model_name)

    @classmethod
    def get_mapping(cls) -> Any:
        """Return mapping of type values to labels."""
        return dict(cls.choices)


class WritingQuestion(UuidMixin, BaseModel):
    """Form questions for character writing and story elements."""

    typ = models.CharField(
        max_length=10,
        choices=WritingQuestionType.choices,
        default=BaseQuestionType.SINGLE,
        help_text=_("Question type"),
        verbose_name=_("Type"),
    )

    search = models.CharField(max_length=1000, editable=False)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="form_questions")

    name = models.CharField(max_length=100, verbose_name=_("Name"), help_text=_("Question name (keep it short)"))

    description = models.CharField(
        max_length=1000,
        blank=True,
        default="",
        verbose_name=_("Description"),
        help_text=_("Optional - Extended description (displayed in small gray text)"),
    )

    order = models.IntegerField(default=0)

    status = models.CharField(
        max_length=1,
        choices=QuestionStatus.choices,
        default=QuestionStatus.OPTIONAL,
        verbose_name=_("Status"),
    )

    visibility = models.CharField(
        max_length=1,
        choices=QuestionVisibility.choices,
        default=QuestionVisibility.PRIVATE,
        verbose_name=_("Visibility"),
    )

    editable = models.CharField(
        default="",
        max_length=20,
        null=True,
        blank=True,
        verbose_name=_("Editable"),
        help_text=_(
            "This field can be edited by the participant only when the character is in one of the selected statuses",
        ),
    )

    max_length = models.IntegerField(
        default=0,
        verbose_name=_("Maximum length"),
        help_text=_(
            "For text questions, maximum number of characters; For multiple options, maximum "
            "number of options (0 = no limit)",
        ),
    )

    printable = models.BooleanField(
        default=True,
        verbose_name=_("Printable"),
        help_text=_("Indicate whether the field is printed in PDF generations"),
    )

    applicable = models.CharField(
        max_length=1,
        choices=QuestionApplicable.choices,
        default=QuestionApplicable.CHARACTER,
        verbose_name=_("Applicable"),
        help_text=_("Select the types of writing elements that this question applies to"),
    )

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.event} - {self.name[:30]}"

    def show(self) -> dict[str, Any]:
        """Return JSON-serializable dictionary of object attributes.

        Returns:
            Dictionary containing description, name, and order fields.

        """
        js = {}
        # Update JSON dict with description, name, and order attributes
        for s in ["description", "name", "order"]:
            self.upd_js_attr(js, s)
        return js

    @staticmethod
    def get_instance_questions(event_instance: Any, enabled_features: Any) -> Any:  # noqa: ARG004
        """Get all writing questions for the event instance ordered by order field."""
        return event_instance.get_elements(WritingQuestion).order_by("order")

    @staticmethod
    def skip(registration: Any, features: Any, params: Any = None, *, is_organizer: Any = False) -> bool:  # noqa: ARG004
        """Default behavior: never skip processing."""
        return False

    def get_editable(self) -> Any:
        """Return list of editable character statuses."""
        return self.editable.split(",") if self.editable else []

    def set_editable(self, editable_list: Any) -> None:
        """Set editable character statuses from list."""
        self.editable = ",".join(editable_list)

    def get_editable_display(self) -> Any:
        """Return comma-separated display of editable character statuses."""
        return ", ".join([str(label) for value, label in CharacterStatus.choices if value in self.get_editable()])

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(
                fields=["event", "applicable", "status"],
                condition=Q(deleted__isnull=True),
                name="wq_evt_app_stat_act",
            ),
            models.Index(fields=["event", "applicable"], condition=Q(deleted__isnull=True), name="wq_evt_app_act"),
        ]


class WritingOption(UuidMixin, BaseModel):
    """Represents WritingOption model."""

    search = models.CharField(max_length=1000, editable=False)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="char_options")

    question = models.ForeignKey(WritingQuestion, on_delete=models.CASCADE, related_name="options")

    name = models.CharField(
        max_length=50,
        verbose_name=_("Name"),
        help_text=_("Option name, displayed within the question (keep it short)"),
    )

    description = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name=_("Description"),
        help_text=_("Optional - Additional information about the option, displayed below the question"),
    )

    max_available = models.IntegerField(
        default=0,
        help_text=_("Optional - Maximum number of times it can be selected across all characters (0 = unlimited)"),
    )

    order = models.IntegerField(default=0)

    requirements = models.ManyToManyField(
        "self",
        related_name="dependents_inv",
        symmetrical=False,
        blank=True,
        verbose_name=_("Prerequisites"),
        help_text=_("Indicates other options that must be selected for this option to be selectable"),
    )

    tickets = models.ManyToManyField(
        RegistrationTicket,
        related_name="character_options",
        blank=True,
        help_text=_(
            "If you select one (or more) tickets, the option will only be available to "
            "participants who have selected that ticket",
        ),
    )

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.question} {self.name}"

    def get_form_text(self, currency_symbol: str | None = None) -> str:  # noqa: ARG002
        """Return the display name for this ticket tier."""
        show_data = self.show()
        return show_data["name"]

    def show(self) -> dict[str, Any]:
        """Return JSON representation with available fields and attributes."""
        # Initialize response with max available count
        js = {"max_available": self.max_available}

        # Update with name, description, and order attributes
        for s in ["name", "description", "order"]:
            self.upd_js_attr(js, s)

        return js


class WritingChoice(BaseModel):
    """Choices for WritingChoice."""

    question = models.ForeignKey(WritingQuestion, on_delete=models.CASCADE, related_name="choices")

    option = models.ForeignKey(WritingOption, on_delete=models.CASCADE, related_name="choices")

    element_id = models.IntegerField(blank=True, null=True)

    def __str__(self) -> str:
        """Return string representation."""
        # Return string representation showing element ID, question name, and option name
        # noinspection PyUnresolvedReferences
        return f"{self.element_id} ({self.question.name}) {self.option.name}"

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["element_id", "question"], condition=Q(deleted__isnull=True), name="wch_elem_q_act"),
            models.Index(fields=["element_id"], condition=Q(deleted__isnull=True), name="wch_elem_act"),
        ]


class WritingAnswer(BaseModel):
    """Represents WritingAnswer model."""

    question = models.ForeignKey(WritingQuestion, on_delete=models.CASCADE, related_name="answers")

    text = models.TextField(max_length=100000)

    element_id = models.IntegerField(blank=True, null=True)

    def __str__(self) -> str:
        """Return string representation with element ID, question name, and text preview."""
        # noinspection PyUnresolvedReferences
        return f"{self.element_id} ({self.question.name}) {self.text[:100]}"

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["element_id", "question"], condition=Q(deleted__isnull=True), name="wan_elem_q_act"),
            models.Index(fields=["element_id"], condition=Q(deleted__isnull=True), name="wan_elem_act"),
        ]


class RegistrationQuestion(UuidMixin, BaseModel):
    """Represents RegistrationQuestion model."""

    typ = models.CharField(
        max_length=50,
        choices=RegistrationQuestionType.choices,
        default=BaseQuestionType.SINGLE,
        help_text=_("Question type"),
        verbose_name=_("Type"),
    )

    search = models.CharField(max_length=1000, editable=False)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="questions")

    name = models.CharField(max_length=100, verbose_name=_("Name"), help_text=_("Question name (keep it short)"))

    description = models.CharField(
        max_length=1000,
        blank=True,
        default="",
        verbose_name=_("Description"),
        help_text=_("Optional - Extended description (displayed in small gray text)"),
    )

    order = models.IntegerField(default=0)

    status = models.CharField(
        max_length=1,
        choices=QuestionStatus.choices,
        default=QuestionStatus.OPTIONAL,
        verbose_name=_("Status"),
    )

    max_length = models.IntegerField(
        default=0,
        verbose_name=_("Maximum length"),
        help_text=_(
            "Optional - For text questions, maximum number of characters; For multiple options, maximum "
            "number of options (0 = no limit)",
        ),
    )

    factions = models.ManyToManyField(
        Faction,
        related_name="registration_questions",
        blank=True,
        verbose_name=_("Faction list"),
        help_text=_(
            "Optional - If you select one (or more) factions, the question will only be shown to participants "
            "with characters in all chosen factions",
        ),
    )

    profile = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("reg_questions/"),
        blank=True,
        null=True,
        verbose_name=_("Image"),
        help_text=_("Optional - Image displayed within the question"),
    )

    profile_thumb = ImageSpecField(
        source="profile",
        processors=[ResizeToFit(width=600)],
        format="JPEG",
        options={"quality": 90},
    )

    tickets = models.ManyToManyField(
        RegistrationTicket,
        related_name="registration_tickets",
        blank=True,
        verbose_name=_("Ticket list"),
        help_text=_(
            "If you select one (or more) tickets, the question will only be shown to participants "
            "who have selected one of those tickets",
        ),
    )

    section = models.ForeignKey(
        RegistrationSection,
        on_delete=models.CASCADE,
        related_name="questions",
        null=True,
        blank=True,
        verbose_name=_("Section"),
        help_text=_(
            "The question will be shown in the selected section (if left empty it will shown at the start of the form)",
        ),
    )

    allowed = models.ManyToManyField(
        Member,
        related_name="questions_allowed",
        blank=True,
        verbose_name=_("Allowed"),
        help_text=_(
            "Staff members who are allowed to be able to see the responses of participants (leave blank to let everyone see)",
        ),
    )

    giftable = models.BooleanField(
        default=False,
        verbose_name=_("Giftable"),
        help_text=_("Indicates whether the option can be included in the gifted signups"),
    )

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.event} - {self.name[:30]}"

    def show(self) -> dict[str, Any]:
        """Return JSON-serializable dict with description and name attributes."""
        js = {}
        for s in ["description", "name"]:
            self.upd_js_attr(js, s)
        return js

    @staticmethod
    def get_instance_questions(event: Event, features: list[str]) -> QuerySet:
        """Get registration questions for an event with optional feature-specific annotations.

        Args:
            event: Event instance to filter questions for
            features: List of feature flag strings to determine which annotations to add

        Returns:
            QuerySet of RegistrationQuestion objects ordered by section and question order

        """
        # Get all questions for the event, ordered by section first, then by question order
        questions = RegistrationQuestion.objects.filter(event=event).order_by(
            F("section__order").asc(nulls_first=True),
            "order",
        )

        # Conditionally add annotations based on enabled features
        if "reg_que_tickets" in features:
            questions = questions.annotate(tickets_map=ArrayAgg("tickets"))
        if "reg_que_faction" in features:
            questions = questions.annotate(factions_map=ArrayAgg("factions"))
        if "reg_que_allowed" in features:
            questions = questions.annotate(allowed_map=ArrayAgg("allowed"))

        return questions

    def skip(self, registration: Any, features: Any, params: Any = None, *, is_organizer: Any = False) -> bool:  # noqa: C901 - Complex question skip logic with feature checks
        """Determine if a question should be skipped based on context and features.

        Evaluates question visibility rules including hidden status, ticket restrictions,
        faction filtering, and organizer permissions to decide if question should be shown.
        """
        if self.status == QuestionStatus.HIDDEN and not is_organizer:
            return True

        if "reg_que_tickets" in features and registration and registration.pk:
            # noinspection PyUnresolvedReferences
            allowed_ticket_ids = [ticket_id for ticket_id in self.tickets_map if ticket_id is not None]
            if len(allowed_ticket_ids) > 0:
                if not registration or not registration.ticket:
                    return True

                if registration.ticket_id not in allowed_ticket_ids:
                    return True

        if "reg_que_faction" in features and registration and registration.pk:
            # noinspection PyUnresolvedReferences
            allowed_faction_ids = [faction_id for faction_id in self.factions_map if faction_id is not None]
            if len(allowed_faction_ids) > 0:
                registration_faction_ids = []
                for character_relation in RegistrationCharacterRel.objects.filter(registration=registration):
                    character_factions = character_relation.character.factions_list.values_list("id", flat=True)
                    registration_faction_ids.extend(character_factions)

                if len(set(allowed_faction_ids).intersection(set(registration_faction_ids))) == 0:
                    return True

        if "reg_que_allowed" in features and registration and registration.pk and is_organizer and params:
            run_id = params["run"].id
            is_run_organizer = run_id in params["all_runs"] and 1 in params["all_runs"][run_id]
            # noinspection PyUnresolvedReferences
            if not is_run_organizer and self.allowed_map[0] and params["member"].id not in self.allowed_map:
                return True

        return False

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["event"], condition=Q(deleted__isnull=True), name="rq_evt_act"),
            models.Index(fields=["event", "status"], condition=Q(deleted__isnull=True), name="rq_evt_stat_act"),
        ]


class RegistrationOption(UuidMixin, BaseModel):
    """Represents RegistrationOption model."""

    search = models.CharField(max_length=1000, editable=False)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="options")

    question = models.ForeignKey(RegistrationQuestion, on_delete=models.CASCADE, related_name="options")

    name = models.CharField(
        max_length=170,
        verbose_name=_("Name"),
        help_text=_("Option name, displayed within the question (keep it short)"),
    )

    description = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name=_("Description"),
        help_text=_("Optional - Additional information about the option, displayed below the question"),
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name=_("Price"),
        help_text=_("Optional - Amount added to the registration fee if selected (0 = no extra cost)"),
    )

    max_available = models.IntegerField(
        default=0,
        verbose_name=_("Maximum number"),
        help_text=_("Optional - Maximum number of times it can be selected across all registrations (0 = unlimited)"),
    )

    order = models.IntegerField(default=0)

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.question} {self.name[:30]} ({self.price}€)"

    def get_price(self) -> Any:
        """Return the option price."""
        return self.price

    def get_form_text(self, currency_symbol: str | None = None) -> str:
        """Return formatted text with name and optional price."""
        # Get display data for the current instance
        display_data = self.show()
        formatted_text = display_data["name"]

        # Append formatted price with currency symbol if applicable
        if display_data["price"] and int(display_data["price"]) > 0:
            if not currency_symbol:
                # noinspection PyUnresolvedReferences
                currency_symbol = self.event.association.get_currency_symbol()
            formatted_text += f" ({decimal_to_str(display_data['price'])}{currency_symbol})"

        return formatted_text

    def show(self) -> dict[str, Any]:
        """Return ticket tier display data as dictionary.

        Returns:
            Dictionary with tier name, price, description, question, and max availability.

        """
        # Build base dictionary with max availability
        js = {"max_available": self.max_available}

        # Add name, price, and description attributes
        for s in ["name", "price", "description"]:
            self.upd_js_attr(js, s)

        # Add associated question name
        # noinspection PyUnresolvedReferences
        js["question"] = self.question.name

        return js

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["event"], condition=Q(deleted__isnull=True), name="ro_evt_act"),
            models.Index(fields=["question"], condition=Q(deleted__isnull=True), name="ro_quest_act"),
        ]


class RegistrationChoice(BaseModel):
    """Choices for RegistrationChoice."""

    question = models.ForeignKey(RegistrationQuestion, on_delete=models.CASCADE, related_name="choices")

    option = models.ForeignKey(RegistrationOption, on_delete=models.CASCADE, related_name="choices")

    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name="choices")

    def __str__(self) -> str:
        """Return string representation showing registration, question and option."""
        # noinspection PyUnresolvedReferences
        return f"{self.registration} ({self.question.name}) {self.option.name}"

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["registration", "question"], condition=Q(deleted__isnull=True), name="rc_reg_q_act"),
            models.Index(fields=["registration"], condition=Q(deleted__isnull=True), name="rc_reg_act"),
        ]


class RegistrationAnswer(BaseModel):
    """Represents RegistrationAnswer model."""

    question = models.ForeignKey(RegistrationQuestion, on_delete=models.CASCADE, related_name="answers")

    text = models.TextField(max_length=5000)

    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name="answers")

    def __str__(self) -> str:
        """Return string representation with registration, question name, and truncated text."""
        # noinspection PyUnresolvedReferences
        return f"{self.registration} ({self.question.name}) {self.text[:100]}"

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["registration", "question"], condition=Q(deleted__isnull=True), name="ra_reg_q_act"),
            models.Index(fields=["registration"], condition=Q(deleted__isnull=True), name="ra_reg_act"),
        ]


def get_ordered_registration_questions(context: dict) -> QuerySet[RegistrationQuestion]:
    """Get registration questions ordered by section and question order."""
    questions = context["event"].get_elements(RegistrationQuestion)
    return questions.order_by(F("section__order").asc(nulls_first=True), "order")


def _get_writing_elements() -> list[tuple[str, str, QuestionApplicable]]:
    """Return list of writing elements with their display names and applicable types."""
    # Define available writing elements with their identifiers, translated names, and applicable types
    return [
        ("character", _("Characters"), QuestionApplicable.CHARACTER),
        ("faction", _("Factions"), QuestionApplicable.FACTION),
        ("plot", _("Plots"), QuestionApplicable.PLOT),
        ("quest", _("Quests"), QuestionApplicable.QUEST),
        ("trait", _("Traits"), QuestionApplicable.TRAIT),
        ("prologue", _("Prologues"), QuestionApplicable.PROLOGUE),
    ]


def _get_writing_mapping() -> dict[str, str]:
    """Return mapping of writing types to their corresponding modules.

    Returns:
        Dictionary mapping writing types to module names.

    """
    # Core writing type mappings
    return {
        "character": "character",
        "faction": "faction",
        "plot": "plot",
        "quest": "questbuilder",
        "trait": "questbuilder",
        "prologue": "prologue",
    }
