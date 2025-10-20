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

import re
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_select2 import forms as s2forms

from larpmanager.cache.registration import get_reg_counts
from larpmanager.forms.base import MyForm
from larpmanager.forms.utils import (
    AssocMemberS2Widget,
    EventCharacterS2WidgetMulti,
    EventPlotS2WidgetMulti,
    EventWritingOptionS2WidgetMulti,
    FactionS2WidgetMulti,
    TicketS2WidgetMulti,
    WritingTinyMCE,
)
from larpmanager.forms.writing import BaseWritingForm, WritingForm
from larpmanager.models.experience import AbilityPx, DeliveryPx
from larpmanager.models.form import (
    QuestionApplicable,
    QuestionStatus,
    QuestionVisibility,
    WritingOption,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.utils import strip_tags
from larpmanager.models.writing import (
    Character,
    CharacterStatus,
    Faction,
    FactionType,
    Plot,
    PlotCharacterRel,
    Relationship,
    TextVersionChoices,
)
from larpmanager.utils.edit import save_version


class CharacterForm(WritingForm, BaseWritingForm):
    orga = False

    page_title = _("Character")

    class Meta:
        model = Character
        fields = [
            "progress",
            "name",
            "assigned",
            "title",
            "teaser",
            "text",
            "mirror",
            "hide",
            "cover",
            "player",
            "event",
            "status",
            "access_token",
        ]

        widgets = {
            "teaser": WritingTinyMCE(),
            "text": WritingTinyMCE(),
            "player": AssocMemberS2Widget,
            "characters": EventCharacterS2WidgetMulti,
        }

    def __init__(self, *args: Any, **kwargs: dict[str, Any]) -> None:
        """Initialize character form with custom fields and configuration.

        Sets up the character creation/editing form including faction selection,
        dynamic custom fields based on event configuration, and optional
        character completion workflow for approval processes.

        Args:
            *args: Positional arguments passed to parent form class.
            **kwargs: Keyword arguments passed to parent form class. Must include
                     'params' dict with event, run, and features configuration.

        Raises:
            KeyError: If required 'params' key is missing from kwargs.

        Note:
            The 'params' dict should contain:
            - event: Event instance for context
            - run: Run instance for current event run
            - features: Available features configuration
        """
        # Initialize parent form class with all provided arguments
        super().__init__(*args, **kwargs)

        # Initialize storage for field details and metadata
        # This dict will store additional information about dynamic fields
        # such as validation rules, display options, and field dependencies
        self.details: dict[str, Any] = {}

        # Set up character-specific fields including factions and custom questions
        # This method handles dynamic field creation based on event configuration
        # and applies feature-based field visibility and validation rules
        self._init_character()

    def check_editable(self, question) -> bool:
        """Check if a question is editable based on event configuration and character status.

        Args:
            question: The question object to check editability for.

        Returns:
            bool: True if the question is editable, False otherwise.

        Notes:
            Returns True if user character approval is disabled or if no editable
            statuses are defined for the question. Otherwise, checks if the current
            instance status matches any of the question's editable statuses.
        """
        # If user character approval is disabled, all questions are editable
        if not self.params["event"].get_config("user_character_approval", False):
            return True

        # Get the list of statuses for which this question is editable
        statuses = question.get_editable()

        # If no specific editable statuses are defined, question is editable
        if not statuses:
            return True

        # Check if current instance status is in the editable statuses list
        return self.instance.status in question.get_editable()

    def _init_custom_fields(self) -> None:
        """Initialize custom form fields for character creation.

        Sets up dynamic form fields based on event configuration and custom field definitions,
        organizing fields into default and custom categories, and handling organizer-specific
        fields and character completion proposals.

        The method performs the following operations:
        1. Determines the parent event if applicable
        2. Initializes registration questions and fields
        3. Categorizes fields into default and custom sets
        4. Adds organizer-specific fields when appropriate
        5. Removes unused fields from the form
        6. Adds character proposal field for user approval workflow

        Returns:
            None
        """
        # Get the parent event if this is a child event
        event = self.params["event"]
        if event.parent:
            event = event.parent

        # Initialize field categories
        fields_default = {"event"}
        fields_custom = set()

        # Set up registration questions and get registration counts
        self._init_reg_question(self.instance, event)
        reg_counts = get_reg_counts(self.params["run"])

        # Process each question to create form fields
        for question in self.questions:
            key = self._init_field(question, reg_counts=reg_counts, orga=self.orga)
            if not key:
                continue

            # Categorize field based on question type
            if len(question.typ) == 1:
                fields_custom.add(key)
            else:
                fields_default.add(key)

        # Add organizer-specific fields and reorder them
        if self.orga:
            for key in ["player", "status"]:
                fields_default.add(key)
                self.reorder_field(key)

            # Add access token field for external writing access
            if event.get_config("writing_external_access", False) and self.instance.pk:
                fields_default.add("access_token")
                self.reorder_field("access_token")

        # Remove unused fields that aren't in our defined categories
        all_fields = set(self.fields.keys()) - fields_default
        for lbl in all_fields - fields_custom:
            del self.fields[lbl]

        # Add character completion proposal field for user approval workflow
        if not self.orga and event.get_config("user_character_approval", False):
            if not self.instance.pk or self.instance.status in [CharacterStatus.CREATION, CharacterStatus.REVIEW]:
                self.fields["propose"] = forms.BooleanField(
                    required=False,
                    label=_("Complete"),
                    help_text=_(
                        "Click here to confirm that you have completed the character and are ready to "
                        "propose it to the staff. Be careful: some fields may no longer be editable. "
                        "Leave the field blank to save your changes and to be able to continue them in "
                        "the future."
                    ),
                    widget=forms.CheckboxInput(attrs={"class": "checkbox_single"}),
                )

    def _init_character(self) -> None:
        """Initialize character with factions and custom fields.

        This method sets up a new character by initializing their faction
        associations and any custom field values that have been configured
        for the character creation process.

        Returns:
            None
        """
        # Initialize character faction associations
        self._init_factions()

        # Initialize custom field values for character
        self._init_custom_fields()

    def _init_factions(self) -> None:
        """Initialize faction selection field for character form.

        Sets up a multiple choice field for selectable factions if the faction
        feature is enabled for the event. Creates a ModelMultipleChoiceField
        with Select2 widget for enhanced user experience.

        The field is populated with existing faction selections for character
        instances that already exist in the database.

        Returns:
            None
        """
        # Early return if faction feature is not enabled for the event
        if "faction" not in self.params["features"]:
            return

        # Get queryset of selectable factions for the current event
        queryset = self.params["run"].event.get_elements(Faction).filter(selectable=True)

        # Create the multiple choice field with Select2 widget for enhanced search functionality
        self.fields["factions_list"] = forms.ModelMultipleChoiceField(
            queryset=queryset,
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains"]),
            required=False,
            label=_("Factions"),
        )

        # Set up the label for showing available factions
        self.show_available_factions = _("Show available factions")

        # Initialize the field with empty list as default value
        self.initial["factions_list"] = []

        # Return early if this is a new character instance (no existing factions to populate)
        if not self.instance.pk:
            return

        # Populate initial values with existing faction IDs for existing character instances
        # Retrieve faction data ordered by number and extract only the ID for field initialization
        for fc in self.instance.factions_list.order_by("number").values_list("id", "number", "name", "text"):
            self.initial["factions_list"].append(fc[0])

    def _save_multi(self, s: str, instance) -> None:
        """Save many-to-many relationships for the given field.

        Handles special processing for 'factions_list' field by comparing
        current and new faction assignments and updating only the differences.
        For other fields, delegates to the parent class implementation.

        Args:
            s: The field name being processed
            instance: The model instance being saved

        Returns:
            None
        """
        # Delegate non-faction fields to parent implementation
        if s != "factions_list":
            return super()._save_multi(s, instance)

        # Skip processing if factions_list field is not in form data
        if "factions_list" not in self.cleaned_data:
            return

        # Extract primary keys from new faction selections
        new = set(self.cleaned_data["factions_list"].values_list("pk", flat=True))

        # Get the faction event context for filtering existing factions
        faction_event = self.params["run"].event.get_class_parent(Faction)

        # Extract primary keys from current faction assignments
        old = set(instance.factions_list.filter(event=faction_event).values_list("id", flat=True))

        # Remove factions that are no longer selected
        for ch in old - new:
            instance.factions_list.remove(ch)

        # Add newly selected factions
        for ch in new - old:
            instance.factions_list.add(ch)

    def clean(self) -> dict[str, Any]:
        """Validate the form data, ensuring only one primary faction is selected.

        Performs validation on the factions_list field to ensure that at most
        one faction with type PRIM (primary) is selected.

        Returns:
            dict[str, Any]: The cleaned form data.

        Raises:
            ValidationError: If more than one primary faction is selected.
        """
        cleaned_data = super().clean()

        # Check if factions_list field exists in cleaned data
        if "factions_list" in self.cleaned_data:
            # Count primary factions to ensure only one is selected
            prim = 0
            for el in self.cleaned_data["factions_list"]:
                if el.typ == FactionType.PRIM:
                    prim += 1

            # Validate that no more than one primary faction is selected
            if prim > 1:
                raise ValidationError({"factions_list": _("Select only one primary faction")})

        return cleaned_data


class OrgaCharacterForm(CharacterForm):
    page_info = _("Manage characters")

    page_title = _("Character")

    load_templates = ["char"]

    load_js = ["characters-choices", "characters-relationships", "factions-choices"]

    load_form = ["characters-relationships"]

    orga = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.relationship_max_length = int(self.params["event"].get_config("writing_relationship_length", 10000))

        if not self.instance.pk:
            return

        self._init_px()

        self._init_plots()

    def _init_character(self):
        """Initialize character form fields based on features and event configuration.

        Sets up factions, custom fields, player assignment, approval status,
        mirror character choices, and special character fields.
        """
        self._init_factions()

        self._init_custom_fields()

        if "user_character" in self.params["features"]:
            self.fields["player"].widget.set_assoc(aid=self.params["a_id"])
        else:
            self.delete_field("player")

        if not self.params["event"].get_config("user_character_approval", False):
            self.delete_field("status")

        if "mirror" in self.fields:
            que = self.params["run"].event.get_elements(Character).all()
            choices = [(m.id, m.name) for m in que]
            self.fields["mirror"].choices = [("", _("--- NOT ASSIGNED ---"))] + choices

        self._init_special_fields()

    def _init_plots(self) -> None:
        """Initialize plot assignment fields in character forms.

        Sets up plot selection options and plot-related character
        attributes for story-driven character development. Creates
        dynamic form fields for each plot the character is assigned to,
        including text editing capabilities and ordering controls.

        Returns:
            None
        """
        # Early return if plot feature is not enabled
        if "plot" not in self.params["features"]:
            return

        # Initialize the main plots selection field
        self.fields["plots"] = forms.ModelMultipleChoiceField(
            label="Plots",
            queryset=self.params["event"].get_elements(Plot),
            required=False,
            widget=EventPlotS2WidgetMulti,
        )
        self.fields["plots"].widget.set_event(self.params["event"])

        # Get character's plot assignments and set initial values
        self.plots = self.instance.get_plot_characters()
        self.initial["plots"] = [el.plot_id for el in self.plots]

        # Initialize control structures for dynamic fields
        self.add_char_finder = []
        self.ordering_up = {}
        self.ordering_down = {}
        self.field_link = {}

        # Process each plot assignment to create dynamic fields
        count = len(self.plots)
        for i, el in enumerate(self.plots):
            plot = el.plot.name
            field = f"pl_{el.plot.id}"
            id_field = f"id_{field}"

            # Create text field for plot-specific character content
            self.fields[field] = forms.CharField(
                widget=WritingTinyMCE(),
                label=plot,
                help_text=_("This text will be added to the sheet, in the plot paragraph %(name)s") % {"name": plot},
                required=False,
            )

            # Set initial text content if available
            if el.text:
                self.initial[field] = el.text

            # Setup plot details and navigation links
            if el.plot.text:
                self.details[id_field] = el.plot.text
            self.show_link.append(id_field)
            self.add_char_finder.append(id_field)

            # Create edit link for the plot
            reverse_args = [self.params["run"].get_slug(), el.plot.id]
            self.field_link[id_field] = reverse("orga_plots_edit", args=reverse_args)

            # Add ordering up link (not for first element)
            if not i == 0:
                reverse_args = [self.params["run"].get_slug(), el.id, "0"]
                self.ordering_up[id_field] = reverse("orga_plots_rels_order", args=reverse_args)

            # Add ordering down link (not for last element)
            if not i == count - 1:
                reverse_args = [self.params["run"].get_slug(), el.id, "1"]
                self.ordering_down[id_field] = reverse("orga_plots_rels_order", args=reverse_args)

    def _save_plot(self, instance: Character) -> None:
        """Save plot associations for a character.

        This method manages the many-to-many relationship between characters and plots,
        adding new associations, removing old ones, and updating associated text content.

        Args:
            instance: Character instance to save plots for

        Returns:
            None
        """
        # Early return if plot feature is not enabled
        if "plot" not in self.params["features"]:
            return

        # Only process plots if the plots field is present in the form
        if "plots" not in self.cleaned_data:
            return

        # Determine which plots need to be added or removed
        selected = set(self.cleaned_data.get("plots", []))
        current = set(Plot.objects.filter(plotcharacterrel__character=instance))

        # Calculate the difference between current and selected plots
        to_add = selected - current
        to_remove = current - selected

        # Remove plot associations that are no longer selected
        if to_remove:
            PlotCharacterRel.objects.filter(character=instance, plot__in=[p.pk for p in to_remove]).delete()

        # Create new plot associations for newly selected plots
        for plot in to_add:
            PlotCharacterRel.objects.create(character=instance, plot=plot)

        # Update text content for existing plot-character relationships
        for pr in instance.get_plot_characters():
            field = f"pl_{pr.plot_id}"

            # Skip if field is not in form data
            if field not in self.cleaned_data:
                continue

            # Skip if text hasn't changed to avoid unnecessary saves
            if self.cleaned_data[field] == pr.text:
                continue

            # Update and save the changed text
            pr.text = self.cleaned_data[field]
            pr.save()

    def _init_px(self) -> None:
        """Initialize PX (ability/delivery) form fields if PX feature is enabled.

        This method adds ability and delivery selection fields to the form when the PX
        feature is available for the current run. It sets up ModelMultipleChoiceField
        widgets with search functionality and initializes them with existing values.

        The method configures:
        - px_ability_list: Multiple selection field for abilities
        - px_delivery_list: Multiple selection field for deliveries

        Both fields use Select2 widgets for enhanced user experience with search
        capabilities and are linked to show_link for UI display purposes.
        """
        # Early return if PX feature is not enabled
        if "px" not in self.params["features"]:
            return

        # Configure ability selection field with search widget
        self.fields["px_ability_list"] = forms.ModelMultipleChoiceField(
            label=_("Abilities"),
            queryset=self.params["run"].event.get_elements(AbilityPx),
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains"]),
            required=False,
        )

        # Initialize ability field with existing values and add to show_link
        self.initial["px_ability_list"] = list(self.instance.px_ability_list.values_list("pk", flat=True))
        self.show_link.append("id_px_ability_list")

        # Configure delivery selection field with search widget
        self.fields["px_delivery_list"] = forms.ModelMultipleChoiceField(
            label=_("Delivery"),
            queryset=self.params["run"].event.get_elements(DeliveryPx),
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains"]),
            required=False,
        )

        # Initialize delivery field with existing values and add to show_link
        self.initial["px_delivery_list"] = list(self.instance.px_delivery_list.values_list("pk", flat=True))
        self.show_link.append("id_px_delivery_list")

    def _save_px(self, instance):
        if "px" not in self.params["features"]:
            return

        if "px_ability_list" in self.cleaned_data:
            instance.px_ability_list.set(self.cleaned_data["px_ability_list"])
        if "px_delivery_list" in self.cleaned_data:
            instance.px_delivery_list.set(self.cleaned_data["px_delivery_list"])

    def _init_factions(self):
        """Initialize faction selection fields for character forms.

        Sets up faction choice fields with proper widget configuration
        when faction feature is enabled.
        """
        if "faction" not in self.params["features"]:
            return

        queryset = self.params["run"].event.get_elements(Faction)

        self.fields["factions_list"] = forms.ModelMultipleChoiceField(
            queryset=queryset, widget=FactionS2WidgetMulti(), required=False, label=_("Factions")
        )
        self.fields["factions_list"].widget.set_event(self.params["event"])

        self.show_available_factions = _("Show available factions")

        if not self.instance.pk:
            return

        # Initial factions values
        self.initial["factions_list"] = []
        for fc in self.instance.factions_list.order_by("number").values_list("id", "number", "name", "text"):
            self.initial["factions_list"].append(fc[0])

    def _save_relationships(self, instance: Character) -> None:
        """Save character relationships from form data.

        This method processes relationship form data to create, update, or delete
        character relationships. It validates that target characters exist in the
        current event and enforces text length limits.

        Args:
            instance: Character instance being saved

        Raises:
            Http404: If a referenced character ID is not found in the event
            ValidationError: If relationship text exceeds maximum length
        """
        # Early return if relationships feature is not enabled
        if "relationships" not in self.params["features"]:
            return

        # Get all character IDs for the current event
        chars_ids = self.params["event"].get_elements(Character).values_list("pk", flat=True)

        # Extract only relationship-related form data
        rel_data = {k: v for k, v in self.data.items() if k.startswith("rel")}

        # Skip processing if no relationship fields are present
        if not rel_data:
            return

        # Process each relationship field in the form data
        for key, value in rel_data.items():
            # Parse the relationship field name to extract character ID
            match = re.match(r"rel_(\d+)", key)
            if not match:
                continue

            # Extract character ID and set relationship type
            ch_id = int(match.group(1))
            rel_type = "direct"

            # Validate that the target character exists in this event
            if ch_id not in chars_ids:
                raise Http404(f"char {ch_id} not recognized")

            # Handle empty relationship value (deletion case)
            if not value:
                # Skip if relationship never existed
                if ch_id not in self.params["relationships"] or rel_type not in self.params["relationships"][ch_id]:
                    continue

                # Delete existing relationship and save version history
                else:
                    rel = self._get_rel(ch_id, instance, rel_type)
                    save_version(rel, TextVersionChoices.RELATIONSHIP, self.params["member"], True)
                    rel.delete()
                    continue

            # Skip if relationship value hasn't changed
            if ch_id in self.params["relationships"] and rel_type in self.params["relationships"][ch_id]:
                if value == self.params["relationships"][ch_id][rel_type]:
                    continue

            # Validate relationship text length using plain text (no HTML tags)
            plain_text = strip_tags(value)
            if len(plain_text) > self.relationship_max_length:
                raise ValidationError(
                    f"Relationship text for character #{ch_id} exceeds maximum length of {self.relationship_max_length} characters. Current length: {len(plain_text)}"
                )

            # Create or update the relationship with new text
            rel = self._get_rel(ch_id, instance, rel_type)
            rel.text = value
            rel.save()

    def _get_rel(self, ch_id, instance, rel_type):
        if rel_type == "direct":
            (rel, cr) = Relationship.objects.get_or_create(source_id=instance.pk, target_id=ch_id)
        else:
            (rel, cr) = Relationship.objects.get_or_create(target_id=instance.pk, source_id=ch_id)
        return rel

    def save(self, commit=True):
        instance = super().save()

        if instance.pk:
            self._save_plot(instance)
            self._save_px(instance)
            self._save_relationships(instance)

        return instance


class OrgaWritingQuestionForm(MyForm):
    page_info = _("Manage form questions for writing elements")

    page_title = _("Writing Question")

    class Meta:
        model = WritingQuestion
        exclude = ["order"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "cols": 40}),
        }

    def __init__(self, *args, **kwargs):
        """Initialize WritingQuestionForm with dynamic field configuration.

        Args:
            *args: Variable length argument list passed to parent
            **kwargs: Arbitrary keyword arguments passed to parent
        """
        super().__init__(*args, **kwargs)

        self._init_type()

        if (
            "user_character" not in self.params["features"]
            or self.params["writing_typ"] != QuestionApplicable.CHARACTER
        ):
            self.delete_field("status")
        else:
            visible_choices = {v for v, _ in self.fields["status"].choices}

            help_texts = {
                QuestionStatus.OPTIONAL: "The question is shown, and can be filled by the player",
                QuestionStatus.MANDATORY: "The question needs to be filled by the player",
                QuestionStatus.DISABLED: "The question is shown, but cannot be changed by the player",
                QuestionStatus.HIDDEN: "The question is not shown to the player",
            }

            self.fields["status"].help_text = ", ".join(
                f"<b>{choice.label}</b>: {text}"
                for choice, text in help_texts.items()
                if choice.value in visible_choices
            )

        if "print_pdf" not in self.params["features"] or self.params["writing_typ"] == QuestionApplicable.PLOT:
            self.delete_field("printable")

        self._init_editable()

        self._init_applicable()

        # remove visibility from plot
        if self.params["writing_typ"] == QuestionApplicable.PLOT:
            self.delete_field("visibility")
        else:
            # set only private and public visibility if different from character
            if self.params["writing_typ"] != QuestionApplicable.CHARACTER:
                self.fields["visibility"].choices = [
                    (choice.value, choice.label)
                    for choice in QuestionVisibility
                    if choice != QuestionVisibility.SEARCHABLE
                ]

            visible_choices = {v for v, _ in self.fields["visibility"].choices}

            help_texts = {
                QuestionVisibility.SEARCHABLE: "Characters can be filtered according to this question",
                QuestionVisibility.PUBLIC: "The answer to this question is publicly visible",
                QuestionVisibility.PRIVATE: "The answer to this question is only visible to the participant",
                QuestionVisibility.HIDDEN: "The answer is hidden to all participants",
            }

            self.fields["visibility"].help_text = ", ".join(
                f"<b>{choice.label}</b>: {text}"
                for choice, text in help_texts.items()
                if choice.value in visible_choices
            )

        self.check_applicable = self.params["writing_typ"]

    def _init_type(self) -> None:
        """Initialize character type field choices based on available writing question types.

        Filters question types based on event features and existing usage to determine
        which writing question types are available for selection. Removes already used
        types and enforces feature-based restrictions.

        The method:
        1. Gets writing questions applicable to the current writing type
        2. Identifies already used question types
        3. Filters choices based on feature availability
        4. Updates the form field choices accordingly
        """
        # Get writing questions for the current event and writing type
        que = self.params["event"].get_elements(WritingQuestion)
        que = que.filter(applicable=self.params["writing_typ"])

        # Extract already used question types to avoid duplicates
        already = list(que.values_list("typ", flat=True).distinct())

        # Handle existing instance - allow editing current type and check cancellation rules
        if self.instance.pk and self.instance.typ:
            already.remove(self.instance.typ)
            # prevent cancellation if one of the default types
            self.prevent_canc = len(self.instance.typ) > 1

        # Build filtered choices based on feature availability and usage
        choices = []
        for choice in WritingQuestionType.choices:
            # Handle feature-dependent question types (multi-character types)
            if len(choice[0]) > 1:
                # Skip if type is already in use
                if choice[0] in already:
                    continue

                # Check feature availability for non-default types
                elif choice[0] not in ["name", "teaser", "text"]:
                    if choice[0] not in self.params["features"]:
                        continue

            # Handle single character types - check 'px' feature for 'c' type
            elif choice[0] == "c" and "px" not in self.params["features"]:
                continue

            # Add valid choice to available options
            choices.append(choice)

        # Update form field with filtered choices
        self.fields["typ"].choices = choices

    def _init_editable(self):
        if not self.params["event"].get_config("user_character_approval", False):
            self.delete_field("editable")
        else:
            self.fields["editable"] = forms.MultipleChoiceField(
                choices=CharacterStatus.choices,
                widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"}),
                required=False,
            )
            if self.instance and self.instance.pk:
                self.initial["editable"] = self.instance.get_editable()

    def _init_applicable(self):
        if self.instance.pk:
            del self.fields["applicable"]
            return

        self.fields["applicable"].widget = forms.HiddenInput()
        self.initial["applicable"] = self.params["writing_typ"]

    def clean_editable(self):
        return ",".join(self.cleaned_data["editable"])


class OrgaWritingOptionForm(MyForm):
    page_info = _("Manage options in form questions for writing elements")

    page_title = _("Writing option")

    class Meta:
        model = WritingOption
        exclude = ["order"]
        widgets = {
            "requirements": EventWritingOptionS2WidgetMulti,
            "question": forms.HiddenInput(),
            "tickets": TicketS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        """Initialize form with feature-based field customization.

        Args:
            *args: Variable positional arguments passed to parent class
            **kwargs: Variable keyword arguments passed to parent class

        Side effects:
            Modifies form fields based on available features and event configuration
        """
        super().__init__(*args, **kwargs)

        if "question_id" in self.params:
            self.initial["question"] = self.params["question_id"]

        if "wri_que_max" not in self.params["features"]:
            self.delete_field("max_available")

        if "wri_que_tickets" not in self.params["features"]:
            self.delete_field("tickets")
        else:
            self.fields["tickets"].widget.set_event(self.params["event"])

        if "wri_que_requirements" not in self.params["features"]:
            self.delete_field("requirements")
        else:
            self.fields["requirements"].widget.set_event(self.params["event"])
