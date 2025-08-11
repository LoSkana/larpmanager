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

from django.apps import apps
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import models
from django.db.models import F
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from pilkit.processors import ResizeToFit

from larpmanager.models.base import BaseModel
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


class QuestionType(models.TextChoices):
    SINGLE = "s", _("Single choice")
    MULTIPLE = "m", _("Multiple choice")
    TEXT = "t", _("Single-line text")
    PARAGRAPH = "p", _("Multi-line text")
    EDITOR = "e", _("Advanced text editor")
    NAME = "name", _("Name")
    TEASER = "teaser", _("Presentation")
    SHEET = "text", _("Sheet")
    COVER = "cover", _("Cover")
    FACTIONS = "faction", _("Factions")
    TITLE = "title", _("Title")
    MIRROR = "mirror", _("Mirror")
    HIDE = "hide", _("Hide")
    PROGRESS = "progress", _("Progress")
    ASSIGNED = "assigned", _("Assigned")

    @staticmethod
    def get_basic_types():
        return {
            QuestionType.SINGLE,
            QuestionType.MULTIPLE,
            QuestionType.TEXT,
            QuestionType.PARAGRAPH,
            QuestionType.EDITOR,
        }

    @staticmethod
    def get_def_types():
        return {QuestionType.NAME, QuestionType.TEASER, QuestionType.SHEET, QuestionType.TITLE}

    @classmethod
    def get_max_length(cls):
        return {
            QuestionType.NAME,
            QuestionType.SHEET,
            QuestionType.TEASER,
            QuestionType.TEXT,
            QuestionType.PARAGRAPH,
            QuestionType.MULTIPLE,
            QuestionType.EDITOR,
        }

    @classmethod
    def get_mapping(cls):
        return {
            QuestionType.SINGLE: "single-choice",
            QuestionType.MULTIPLE: "multi-choice",
            QuestionType.TEXT: "short-text",
            QuestionType.PARAGRAPH: "long-text",
            QuestionType.EDITOR: "advanced",
        }


class QuestionStatus(models.TextChoices):
    OPTIONAL = "o", _("Optional")
    MANDATORY = "m", _("Mandatory")
    DISABLED = "d", _("Disabled")
    HIDDEN = "h", _("Hidden")

    @classmethod
    def get_mapping(cls):
        return {
            QuestionStatus.OPTIONAL: "optional",
            QuestionStatus.MANDATORY: "mandatory",
            QuestionStatus.DISABLED: "disabled",
            QuestionStatus.HIDDEN: "hidden",
        }


class QuestionVisibility(models.TextChoices):
    SEARCHABLE = "s", _("Searchable")
    PUBLIC = "c", _("Public")
    PRIVATE = "e", _("Private")
    HIDDEN = "h", _("Hidden")

    @classmethod
    def get_mapping(cls):
        return {
            QuestionVisibility.SEARCHABLE: "searchable",
            QuestionVisibility.PUBLIC: "public",
            QuestionVisibility.PRIVATE: "private",
            QuestionVisibility.HIDDEN: "hidden",
        }


class QuestionApplicable(models.TextChoices):
    CHARACTER = "c", "character"
    PLOT = "p", "plot"
    FACTION = "f", "faction"
    QUEST = "q", "quest"
    TRAIT = "t", "trait"

    @classmethod
    def get_applicable(cls, model_name):
        for value, label in cls.choices:
            if model_name.lower() == label.lower():
                return value
        return None

    @staticmethod
    def get_applicable_inverse(typ):
        # noinspection PyUnresolvedReferences
        model_name = QuestionApplicable(typ).label.lower()
        return apps.get_model("larpmanager", model_name)

    @classmethod
    def get_mapping(cls):
        return {value: label for value, label in cls.choices}


class WritingQuestion(BaseModel):
    typ = models.CharField(
        max_length=10,
        choices=QuestionType.choices,
        default=QuestionType.SINGLE,
        help_text=_("Question type"),
        verbose_name=_("Type"),
    )

    search = models.CharField(max_length=1000, editable=False)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="form_questions")

    name = models.CharField(max_length=100, verbose_name=_("Name"), help_text=_("Question name (keep it short)"))

    description = models.CharField(
        max_length=1000,
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Optional - Extended description (displayed in small gray text)"),
    )

    order = models.IntegerField(default=0)

    status = models.CharField(
        max_length=1, choices=QuestionStatus.choices, default=QuestionStatus.OPTIONAL, verbose_name=_("Status")
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
            "This field can be edited by the participant only when the character is in one of the selected statuses"
        ),
    )

    max_length = models.IntegerField(
        default=0,
        verbose_name=_("Maximum length"),
        help_text=_(
            "For text questions, maximum number of characters; For multiple options, maximum "
            "number of options (0 = no limit)"
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

    def __str__(self):
        return f"{self.event} - {self.name[:30]}"

    def show(self):
        js = {}
        for s in ["description", "name"]:
            self.upd_js_attr(js, s)
        return js

    @staticmethod
    def get_instance_questions(event, features):
        return event.get_elements(WritingQuestion).order_by("order")

    @staticmethod
    def skip(instance, features, params, orga):
        return False

    def get_editable(self):
        return self.editable.split(",") if self.editable else []

    def set_editable(self, editable_list):
        self.editable = ",".join(editable_list)

    def get_editable_display(self):
        return ", ".join([str(label) for value, label in CharacterStatus.choices if value in self.get_editable()])


class WritingOption(BaseModel):
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
        null=True,
        verbose_name=_("Description"),
        help_text=_("Optional – Additional information about the option, displayed below the question"),
    )

    max_available = models.IntegerField(
        default=0,
        help_text=_("Optional – Maximum number of times it can be selected across all characters (0 = unlimited)"),
    )

    order = models.IntegerField(default=0)

    dependents = models.ManyToManyField(
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
            "participants who have selected that ticket"
        ),
    )

    def __str__(self):
        return f"{self.question} {self.name}"

    def get_form_text(self, run=None, cs=None):
        s = self.show(run)
        return s["name"]

    def show(self, run=None):
        js = {"max_available": self.max_available}
        for s in ["name", "description"]:
            self.upd_js_attr(js, s)
        return js


class WritingChoice(BaseModel):
    question = models.ForeignKey(WritingQuestion, on_delete=models.CASCADE, related_name="choices")

    option = models.ForeignKey(WritingOption, on_delete=models.CASCADE, related_name="choices")

    element_id = models.IntegerField(blank=True, null=True)

    def __str__(self):
        # noinspection PyUnresolvedReferences
        return f"{self.element_id} ({self.question.name}) {self.option.name}"


class WritingAnswer(BaseModel):
    question = models.ForeignKey(WritingQuestion, on_delete=models.CASCADE, related_name="answers")

    text = models.TextField(max_length=100000)

    element_id = models.IntegerField(blank=True, null=True)

    def __str__(self):
        # noinspection PyUnresolvedReferences
        return f"{self.element_id} ({self.question.name}) {self.text[:100]}"


class RegistrationQuestion(BaseModel):
    typ = models.CharField(
        max_length=10,
        choices=QuestionType.choices,
        default=QuestionType.SINGLE,
        help_text=_("Question type"),
        verbose_name=_("Type"),
    )

    search = models.CharField(max_length=1000, editable=False)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="questions")

    name = models.CharField(max_length=100, verbose_name=_("Name"), help_text=_("Question name (keep it short)"))

    description = models.CharField(
        max_length=1000,
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Optional - Extended description (displayed in small gray text)"),
    )

    order = models.IntegerField(default=0)

    status = models.CharField(
        max_length=1, choices=QuestionStatus.choices, default=QuestionStatus.OPTIONAL, verbose_name=_("Status")
    )

    max_length = models.IntegerField(
        default=0,
        verbose_name=_("Maximum length"),
        help_text=_(
            "Optional - For text questions, maximum number of characters; For multiple options, maximum "
            "number of options (0 = no limit)"
        ),
    )

    factions = models.ManyToManyField(
        Faction,
        related_name="registration_questions",
        blank=True,
        verbose_name=_("Faction list"),
        help_text=_(
            "Optional - If you select one (or more) factions, the question will only be shown to participants "
            "with characters in all chosen factions"
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
            "who have selected one of those tickets"
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
            "The question will be shown in the selected section (if left empty it will shown at the start of the form)"
        ),
    )

    allowed = models.ManyToManyField(
        Member,
        related_name="questions_allowed",
        blank=True,
        verbose_name=_("Allowed"),
        help_text=_(
            "Staff members who are allowed to be able to see the responses of participants (leave blank to let everyone see)"
        ),
    )

    giftable = models.BooleanField(
        default=False,
        verbose_name=_("Giftable"),
        help_text=_("Indicates whether the option can be included in the gifted signups"),
    )

    def __str__(self):
        return f"{self.event} - {self.name[:30]}"

    def show(self):
        js = {}
        for s in ["description", "name"]:
            self.upd_js_attr(js, s)
        return js

    @staticmethod
    def get_instance_questions(event, features):
        que = RegistrationQuestion.objects.filter(event=event).order_by(
            F("section__order").asc(nulls_first=True), "order"
        )
        if "reg_que_tickets" in features:
            que = que.annotate(tickets_map=ArrayAgg("tickets"))
        if "reg_que_faction" in features:
            que = que.annotate(factions_map=ArrayAgg("factions"))
        if "reg_que_allowed" in features:
            que = que.annotate(allowed_map=ArrayAgg("allowed"))
        return que

    def skip(self, reg, features, params=None, orga=False):
        if self.status == QuestionStatus.HIDDEN and not orga:
            return True

        if "reg_que_tickets" in features and reg and reg.pk:
            # noinspection PyUnresolvedReferences
            tickets_id = [i for i in self.tickets_map if i is not None]
            if len(tickets_id) > 0:
                if not reg or not reg.ticket:
                    return True

                if reg.ticket_id not in tickets_id:
                    return True

        if "reg_que_faction" in features and reg and reg.pk:
            # noinspection PyUnresolvedReferences
            factions_id = [i for i in self.factions_map if i is not None]
            if len(factions_id) > 0:
                reg_factions = []
                for el in RegistrationCharacterRel.objects.filter(reg=reg):
                    factions = el.character.factions_list.values_list("id", flat=True)
                    reg_factions.extend(factions)

                if len(set(factions_id).intersection(set(reg_factions))) == 0:
                    return True

        if "reg_que_allowed" in features and reg and reg.pk and orga and params:
            run_id = params["run"].id
            organizer = run_id in params["all_runs"] and 1 in params["all_runs"][run_id]
            # noinspection PyUnresolvedReferences
            if not organizer and self.allowed_map[0]:
                # noinspection PyUnresolvedReferences
                if params["member"].id not in self.allowed_map:
                    return True

        return False


class RegistrationOption(BaseModel):
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
        null=True,
        verbose_name=_("Description"),
        help_text=_("Optional – Additional information about the option, displayed below the question"),
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name=_("Price"),
        help_text=_("Optional – Amount added to the registration fee if selected (0 = no extra cost)"),
    )

    max_available = models.IntegerField(
        default=0,
        verbose_name=_("Maximum number"),
        help_text=_("Optional – Maximum number of times it can be selected across all registrations (0 = unlimited)"),
    )

    order = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.question} {self.name[:30]} ({self.price}€)"

    def get_price(self):
        return self.price

    def get_form_text(self, run=None, cs=None):
        s = self.show(run)
        tx = s["name"]
        if s["price"] and int(s["price"]) > 0:
            if not cs:
                # noinspection PyUnresolvedReferences
                cs = self.event.assoc.get_currency_symbol()
            tx += f" ({decimal_to_str(s['price'])}{cs})"

        return tx

    def show(self, run=None):
        js = {"max_available": self.max_available}
        for s in ["name", "price", "description"]:
            self.upd_js_attr(js, s)
        # noinspection PyUnresolvedReferences
        js["question"] = self.question.name
        return js


class RegistrationChoice(BaseModel):
    question = models.ForeignKey(RegistrationQuestion, on_delete=models.CASCADE, related_name="choices")

    option = models.ForeignKey(RegistrationOption, on_delete=models.CASCADE, related_name="choices")

    reg = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name="choices")

    def __str__(self):
        # noinspection PyUnresolvedReferences
        return f"{self.reg} ({self.question.name}) {self.option.name}"


class RegistrationAnswer(BaseModel):
    question = models.ForeignKey(RegistrationQuestion, on_delete=models.CASCADE, related_name="answers")

    text = models.TextField(max_length=5000)

    reg = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name="answers")

    def __str__(self):
        # noinspection PyUnresolvedReferences
        return f"{self.reg} ({self.question.name}) {self.text[:100]}"


def get_ordered_registration_questions(ctx):
    que = ctx["event"].get_elements(RegistrationQuestion)
    return que.order_by(F("section__order").asc(nulls_first=True), "order")


def _get_writing_elements():
    shows = [
        ("character", _("Characters"), QuestionApplicable.CHARACTER),
        ("faction", _("Factions"), QuestionApplicable.FACTION),
        ("plot", _("Plots"), QuestionApplicable.PLOT),
        ("quest", _("Quests"), QuestionApplicable.QUEST),
        ("trait", _("Traits"), QuestionApplicable.TRAIT),
    ]
    return shows


def _get_writing_mapping():
    mapping = {
        "character": "character",
        "faction": "faction",
        "plot": "plot",
        "quest": "questbuilder",
        "trait": "questbuilder",
    }
    return mapping
