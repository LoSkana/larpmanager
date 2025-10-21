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
from typing import Any

from django import forms
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.base import BaseRegistrationForm, MyForm
from larpmanager.forms.utils import EventCharacterS2Widget, EventCharacterS2WidgetMulti, WritingTinyMCE
from larpmanager.models.access import get_event_staffers
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import ProgressStep
from larpmanager.models.form import (
    QuestionApplicable,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.miscellanea import PlayerRelationship
from larpmanager.models.writing import (
    Faction,
    Handout,
    HandoutTemplate,
    Plot,
    PlotCharacterRel,
    Prologue,
    PrologueType,
    SpeedLarp,
)
from larpmanager.utils.validators import FileTypeValidator


class WritingForm(MyForm):
    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        """Initialize the form with default show_link configuration.

        Initializes the parent class and configures which form fields should display
        links in the rendered form interface. The show_link attribute determines
        which field IDs will have clickable links rendered in the UI.

        Args:
            *args: Variable length argument list passed to parent class constructor.
            **kwargs: Arbitrary keyword arguments passed to parent class constructor.

        Returns:
            None
        """
        # Initialize parent class with all provided arguments
        super().__init__(*args, **kwargs)

        # Configure which fields should display links in the form interface
        # These field IDs will have clickable links rendered in the UI
        self.show_link = ["id_teaser", "id_text"]

    def _init_special_fields(self):
        """Initialize special form fields based on available question types.

        Configures cover, assigned, and progress fields based on writing question types.
        """
        types = set()
        for que in self.questions:
            types.add(que.typ)

        if WritingQuestionType.COVER not in types:
            if "cover" in self.fields:
                del self.fields["cover"]

        if WritingQuestionType.ASSIGNED in types:
            choices = [(m.id, m.show_nick()) for m in get_event_staffers(self.params["run"].event)]
            self.fields["assigned"].choices = [("", _("--- NOT ASSIGNED ---"))] + choices
        else:
            self.delete_field("assigned")

        if WritingQuestionType.PROGRESS in types:
            self.fields["progress"].choices = [
                (el.id, str(el)) for el in ProgressStep.objects.filter(event=self.params["run"].event).order_by("order")
            ]
        else:
            self.delete_field("progress")


class PlayerRelationshipForm(MyForm):
    page_title = _("Character Relationship")

    class Meta:
        model = PlayerRelationship
        exclude = ["reg"]
        widgets = {
            "target": EventCharacterS2Widget,
        }
        labels = {"target": _("Character")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["target"].widget.set_event(self.params["run"].event)
        self.fields["target"].required = True

    def clean(self) -> dict[str, Any]:
        """Clean and validate form data for player relationships.

        Validates that:
        - A player cannot create a relationship with themselves
        - No duplicate relationships exist for the same registration and target

        Returns:
            The cleaned form data dictionary

        Raises:
            ValidationError: If validation rules are violated
        """
        cleaned_data = super().clean()

        # Prevent self-relationships
        if self.cleaned_data["target"].id == self.params["char"]["id"]:
            self.add_error("target", _("You cannot create a relationship towards yourself") + "!")

        # Check for duplicate relationships (excluding current instance during edits)
        try:
            rel = PlayerRelationship.objects.get(reg=self.params["run"].reg, target=self.cleaned_data["target"])
            # Allow editing existing relationship, but prevent duplicates
            if rel.id != self.instance.id:
                self.add_error("target", _("Already existing relationship") + "!")
        except ObjectDoesNotExist:
            # No existing relationship found - this is expected for new relationships
            pass

        return cleaned_data

    def save(self, commit: bool = True) -> Any:
        """Save the form instance with registration assignment.

        Creates or updates the model instance, automatically assigning
        the registration from the run parameter for new instances.

        Parameters
        ----------
        commit : bool, default True
            Whether to save the instance to the database.

        Returns
        -------
        Any
            The saved model instance.

        Raises
        ------
        KeyError
            If 'run' parameter is not found in self.params.
        AttributeError
            If run object doesn't have 'reg' attribute.
        """
        # Create instance without committing to database yet
        instance = super().save(commit=False)

        # For new instances, assign registration from run parameter
        if not instance.pk:
            # Extract registration from the run parameter and assign to instance
            instance.reg = self.params["run"].reg

        # Only save to database if commit is True
        if commit:
            instance.save()

        return instance


class UploadElementsForm(forms.Form):
    allowed_types = [
        "application/csv",
        "text/csv",
        "text/plain",
        "application/zip",
        "text/html",
    ]
    validator = FileTypeValidator(allowed_types=allowed_types)

    first = forms.FileField(validators=[validator], required=False)
    second = forms.FileField(validators=[validator], required=False)

    def __init__(self, *args, **kwargs):
        only_one = kwargs.pop("only_one", False)
        super().__init__(*args, **kwargs)
        if only_one and "second" in self.fields:
            del self.fields["second"]


class BaseWritingForm(BaseRegistrationForm):
    gift = False
    answer_class = WritingAnswer
    choice_class = WritingChoice
    option_class = WritingOption
    question_class = WritingQuestion
    instance_key = "element_id"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # noinspection PyProtectedMember
        self.applicable = QuestionApplicable.get_applicable(self._meta.model._meta.model_name)

    def _init_questions(self, event):
        super()._init_questions(event)
        # noinspection PyProtectedMember
        self.questions = self.questions.filter(applicable=self.applicable)

    def get_options_query(self, event):
        query = super().get_options_query(event)
        return query.annotate(tickets_map=ArrayAgg("tickets"))

    def get_option_key_count(self, option):
        key = f"option_char_{option.id}"
        return key

    def save(self, commit=True):
        instance = super().save()

        instance.save()
        if hasattr(self, "questions"):
            orga = True
            if hasattr(self, "orga"):
                orga = self.orga
            self.save_reg_questions(instance, orga=orga)

        return instance


class PlotForm(WritingForm, BaseWritingForm):
    load_templates = ["plot"]

    load_js = ["characters-choices", "plot-roles"]

    page_title = _("Plot")

    class Meta:
        model = Plot

        exclude = ("number", "temp", "hide", "order")

        widgets = {
            "characters": EventCharacterS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        """Initialize plot form with character relationships and dynamic fields.

        Sets up plot editing form with character selection, role text fields,
        and character finder functionality for plot management.
        """
        super().__init__(*args, **kwargs)

        self.init_orga_fields()
        self.reorder_field("characters")

        # Cache plot characters data to avoid multiple queries
        if self.instance.pk:
            plot_characters_data = list(
                self.instance.get_plot_characters().values_list(
                    "character__id", "character__number", "character__name", "text"
                )
            )
            self.init_characters = [ch[0] for ch in plot_characters_data]
        else:
            plot_characters_data = []
            self.init_characters = []

        self.initial["characters"] = self.init_characters

        self.role_help_text = _("This text will be added to the sheet of")

        self._init_special_fields()

        # PLOT CHARACTERS REL
        self.add_char_finder = []
        self.field_link = {}
        if self.instance.pk:
            for ch in plot_characters_data:
                char = f"#{ch[1]} {ch[2]}"
                field = f"char_role_{ch[0]}"
                id_field = f"id_{field}"
                self.fields[field] = forms.CharField(
                    widget=WritingTinyMCE(),
                    label=char,
                    help_text=f"{self.role_help_text} {char}",
                    required=False,
                )

                self.initial[field] = ch[3]

                self.show_link.append(id_field)
                self.add_char_finder.append(id_field)
                reverse_args = [self.params["run"].get_slug(), ch[0]]
                self.field_link[id_field] = reverse("orga_characters_edit", args=reverse_args)

    def _save_multi(self, s, instance):
        self.chars_id = set(self.cleaned_data["characters"].values_list("pk", flat=True))

        PlotCharacterRel.objects.filter(plot_id=instance.pk).exclude(character_id__in=self.chars_id).delete()

    def save(self, commit=True):
        instance = super().save()

        instance.save()
        for ch_id in self.chars_id:
            (pr, created) = PlotCharacterRel.objects.get_or_create(plot_id=instance.pk, character_id=ch_id)
            field = f"char_role_{pr.character_id}"
            value = self.cleaned_data.get(field, "")
            if not value:
                value = self.data.get(field, "")
            if not value:
                continue
            pr.text = value
            pr.save()

        return instance


class FactionForm(WritingForm, BaseWritingForm):
    load_templates = ["faction"]

    load_js = ["characters-choices"]

    page_title = _("Faction")

    class Meta:
        model = Faction

        exclude = ("number", "temp", "hide", "order")

        widgets = {
            "characters": EventCharacterS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        """Initialize faction form with field configuration and help text.

        Args:
            *args: Positional arguments passed to parent
            **kwargs: Keyword arguments passed to parent
        """
        super().__init__(*args, **kwargs)
        self.init_orga_fields()

        self.reorder_field("characters")

        if "user_character" not in self.params["features"]:
            self.delete_field("selectable")
        else:
            self.reorder_field("selectable")

        self._init_special_fields()

        # set typ help text
        help_texts = {
            _("Primary"): _("main grouping / affiliation for characters"),
            _("Transversal"): _("secondary grouping across primary factions"),
            _("Secret"): _("hidden faction visible only to assigned characters"),
        }
        self.fields["typ"].help_text = ", ".join([f"<b>{key}</b>: {value}" for key, value in help_texts.items()])


class QuestTypeForm(WritingForm):
    page_title = _("Quest type")

    class Meta:
        model = QuestType
        fields = ["name", "teaser", "event"]

        widgets = {
            "teaser": WritingTinyMCE(),
            "text": WritingTinyMCE(),
        }


class QuestForm(WritingForm, BaseWritingForm):
    page_title = _("Quest")

    class Meta:
        model = Quest
        exclude = ("number", "temp", "hide", "order")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.init_orga_fields()
        self._init_special_fields()

        que = self.params["run"].event.get_elements(QuestType)
        self.fields["typ"].choices = [(m.id, m.name) for m in que]


class TraitForm(WritingForm, BaseWritingForm):
    page_title = _("Trait")

    load_templates = ["trait"]

    class Meta:
        model = Trait
        exclude = ("number", "temp", "hide", "order", "traits")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.init_orga_fields()
        self._init_special_fields()

        que = self.params["run"].event.get_elements(Quest)
        self.fields["quest"].choices = [(m.id, m.name) for m in que]


class HandoutForm(WritingForm):
    page_title = _("Handout")

    class Meta:
        model = Handout
        fields = ["template", "name", "text", "event"]

        widgets = {
            "text": WritingTinyMCE(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        que = self.params["run"].event.get_elements(HandoutTemplate)
        self.fields["template"].choices = [(m.id, m.name) for m in que]


class HandoutTemplateForm(WritingForm):
    load_templates = ["handout-template"]

    class Meta:
        model = HandoutTemplate
        exclude = ["number"]

        widgets = {"template": forms.FileInput(attrs={"accept": "application/vnd.oasis.opendocument.text"})}


class PrologueTypeForm(WritingForm):
    page_title = _("Prologue type")

    class Meta:
        model = PrologueType
        fields = ["name", "event"]


class PrologueForm(WritingForm, BaseWritingForm):
    page_title = _("Prologue")

    load_js = ["characters-choices"]

    class Meta:
        model = Prologue

        exclude = ("number", "teaser", "temp", "hide")

        widgets = {
            "characters": EventCharacterS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        que = self.params["run"].event.get_elements(PrologueType)
        self.fields["typ"].choices = [(m.id, m.name) for m in que]

        self.init_orga_fields()

        self.reorder_field("characters")

        self._init_special_fields()


class SpeedLarpForm(WritingForm):
    page_title = _("Speed larp")

    load_js = ["characters-choices"]

    class Meta:
        model = SpeedLarp
        exclude = ("teaser", "temp", "hide")

        widgets = {
            "characters": EventCharacterS2WidgetMulti,
            "text": WritingTinyMCE(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
