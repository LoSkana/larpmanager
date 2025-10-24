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
from larpmanager.models.event import Event, ProgressStep
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

        Args:
            *args: Variable length argument list passed to parent class.
            **kwargs: Arbitrary keyword arguments passed to parent class.
        """
        # Initialize parent class with all provided arguments
        super().__init__(*args, **kwargs)

        # Configure which fields should display links in the form
        self.show_link = ["id_teaser", "id_text"]

    def _init_special_fields(self):
        """Initialize special form fields based on available question types.

        Configures cover, assigned, and progress fields based on writing question types.
        """
        question_types = set()
        for question in self.questions:
            question_types.add(question.typ)

        if WritingQuestionType.COVER not in question_types:
            if "cover" in self.fields:
                del self.fields["cover"]

        if WritingQuestionType.ASSIGNED in question_types:
            staffer_choices = [
                (member.id, member.show_nick()) for member in get_event_staffers(self.params["run"].event)
            ]
            self.fields["assigned"].choices = [("", _("--- NOT ASSIGNED ---"))] + staffer_choices
        else:
            self.delete_field("assigned")

        if WritingQuestionType.PROGRESS in question_types:
            self.fields["progress"].choices = [
                (step.id, str(step))
                for step in ProgressStep.objects.filter(event=self.params["run"].event).order_by("order")
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure target field for the event."""
        super().__init__(*args, **kwargs)
        # Configure target field widget with event from run params
        self.fields["target"].widget.set_event(self.params["run"].event)
        self.fields["target"].required = True

    def clean(self) -> dict:
        """Clean and validate form data for player relationships.

        Validates that:
        - User cannot create relationship with themselves
        - No duplicate relationships exist for the same registration and target

        Returns:
            dict: Cleaned form data

        Raises:
            ValidationError: When validation rules are violated
        """
        cleaned_data = super().clean()

        # Check if user is trying to create relationship with themselves
        if self.cleaned_data["target"].id == self.params["char"]["id"]:
            self.add_error("target", _("You cannot create a relationship towards yourself") + "!")

        # Check for existing relationships with same target and registration
        try:
            rel = PlayerRelationship.objects.get(reg=self.params["run"].reg, target=self.cleaned_data["target"])
            # Allow editing existing relationship, but prevent duplicates
            if rel.id != self.instance.id:
                self.add_error("target", _("Already existing relationship") + "!")
        except ObjectDoesNotExist:
            # No existing relationship found - this is valid
            pass

        return cleaned_data

    def save(self, commit: bool = True) -> Any:
        """Save the form instance, setting registration if new.

        Args:
            commit: Whether to save the instance to the database.

        Returns:
            The saved instance.
        """
        instance = super().save(commit=False)

        # Set registration for new instances
        if not instance.pk:
            instance.reg = self.params["run"].reg

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

    def __init__(self, *args: Any, only_one: bool = False, **kwargs: Any) -> None:
        """Initialize form, optionally removing the 'second' field.

        Args:
            *args: Positional arguments passed to parent class.
            only_one: If True, removes 'second' field if present.
            **kwargs: Keyword arguments passed to parent class.
        """
        only_one = kwargs.pop("only_one", False)
        super().__init__(*args, **kwargs)

        # Remove 'second' field when only_one is True
        if only_one and "second" in self.fields:
            del self.fields["second"]


class BaseWritingForm(BaseRegistrationForm):
    gift = False
    answer_class = WritingAnswer
    choice_class = WritingChoice
    option_class = WritingOption
    question_class = WritingQuestion
    instance_key = "element_id"

    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        """Initialize form with applicable questions configuration.

        Args:
            *args: Variable length argument list passed to parent class.
            **kwargs: Arbitrary keyword arguments passed to parent class.
        """
        # Initialize parent class with all provided arguments
        super().__init__(*args, **kwargs)

        # Get applicable questions for this model type
        # noinspection PyProtectedMember
        self.applicable = QuestionApplicable.get_applicable(self._meta.model._meta.model_name)

    def _init_questions(self, event: Event) -> None:
        """Initialize questions filtered by applicable type."""
        super()._init_questions(event)
        # Filter questions to only include those matching this form's applicable type
        # noinspection PyProtectedMember
        self.questions = self.questions.filter(applicable=self.applicable)

    def get_options_query(self, event: Event) -> Any:
        """Get annotated queryset of options with ticket mappings."""
        # Get base options query from parent class
        query = super().get_options_query(event)
        # Annotate with array-aggregated tickets for each option
        return query.annotate(tickets_map=ArrayAgg("tickets"))

    def get_option_key_count(self, option) -> str:
        """Return cache key for tracking option character count."""
        key = f"option_char_{option.id}"
        return key

    def save(self, commit: bool = True) -> Any:
        """Save the form and handle registration questions if present.

        Args:
            commit: Whether to save the instance to database

        Returns:
            The saved instance
        """
        # Save parent form and persist instance
        instance = super().save()
        instance.save()

        # Save registration questions if form has them
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

        self.chars_id = []

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

    def _save_multi(self, s: str, instance: Plot) -> None:
        """Delete plot-character relations for unselected characters."""
        # Extract character IDs from cleaned form data
        self.chars_id = set(self.cleaned_data["characters"].values_list("pk", flat=True))

        # Remove relations for characters not in the current selection
        PlotCharacterRel.objects.filter(plot_id=instance.pk).exclude(character_id__in=self.chars_id).delete()

    def save(self, commit: bool = True) -> PlotCharacterRel:
        """
        Save the form instance and update plot-character relationships.

        Args:
            commit: Whether to save the instance to the database.

        Returns:
            The saved instance with updated plot-character relationships.
        """
        instance = super().save()

        # Persist the instance to ensure it has a primary key
        instance.save()

        # Create or update plot-character relationships for each character
        for ch_id in self.chars_id:
            (pr, created) = PlotCharacterRel.objects.get_or_create(plot_id=instance.pk, character_id=ch_id)

            # Extract role text from cleaned_data or raw data
            field = f"char_role_{pr.character_id}"
            value = self.cleaned_data.get(field, "")
            if not value:
                value = self.data.get(field, "")
            if not value:
                continue

            # Update and save the relationship with role text
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize faction form with field configuration and help text."""
        super().__init__(*args, **kwargs)

        # Configure organization-specific fields and reorder characters field
        self.init_orga_fields()
        self.reorder_field("characters")

        # Handle selectable field based on user_character feature
        if "user_character" not in self.params["features"]:
            self.delete_field("selectable")
        else:
            self.reorder_field("selectable")

        self._init_special_fields()

        # Configure faction type help text with descriptions
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the form with organization fields and quest type choices."""
        super().__init__(*args, **kwargs)

        # Initialize organization-specific and special fields
        self.init_orga_fields()
        self._init_special_fields()

        # Populate quest type choices from event elements
        que = self.params["run"].event.get_elements(QuestType)
        self.fields["typ"].choices = [(m.id, m.name) for m in que]


class TraitForm(WritingForm, BaseWritingForm):
    page_title = _("Trait")

    load_templates = ["trait"]

    class Meta:
        model = Trait
        exclude = ("number", "temp", "hide", "order", "traits")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure quest field choices."""
        super().__init__(*args, **kwargs)

        # Initialize organization-specific and special fields
        self.init_orga_fields()
        self._init_special_fields()

        # Populate quest choices from event elements
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and populate template choices from run's handout templates."""
        super().__init__(*args, **kwargs)
        # Retrieve handout templates for the associated run's event
        que = self.params["run"].event.get_elements(HandoutTemplate)
        # Populate template field choices with template IDs and names
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with prologue choices and field configuration."""
        super().__init__(*args, **kwargs)

        # Populate prologue type choices from event elements
        que = self.params["run"].event.get_elements(PrologueType)
        self.fields["typ"].choices = [(m.id, m.name) for m in que]

        # Initialize organization-specific fields and reorder characters
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
