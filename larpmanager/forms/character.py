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
import contextlib
import re
from typing import Any, ClassVar

from django import forms
from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_select2 import forms as s2forms

from larpmanager.cache.character import get_event_cache_all
from larpmanager.cache.config import get_event_config
from larpmanager.cache.registration import get_registration_counts
from larpmanager.forms.base import BaseModelForm
from larpmanager.forms.utils import (
    AssociationMemberS2Widget,
    EventCharacterS2WidgetMulti,
    EventCharacterS2WidgetUuid,
    EventPlotS2WidgetMulti,
    EventWritingOptionS2WidgetMulti,
    FactionS2WidgetMulti,
    RunStaffS2Widget,
    TicketS2WidgetMulti,
    WritingTinyMCE,
)
from larpmanager.forms.writing import BaseWritingForm, WritingForm
from larpmanager.models.base import Feature
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
    CharacterConfig,
    CharacterStatus,
    Faction,
    FactionType,
    Plot,
    PlotCharacterRel,
    Relationship,
    TextVersionChoices,
)
from larpmanager.utils.edit.backend import save_version


class CharacterForm(WritingForm, BaseWritingForm):
    """Form for Character."""

    orga = False

    page_title = _("Character")

    class Meta:
        model = Character
        fields: ClassVar[list] = [
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

        widgets: ClassVar[dict] = {
            "teaser": WritingTinyMCE(),
            "text": WritingTinyMCE(),
            "player": AssociationMemberS2Widget,
            "characters": EventCharacterS2WidgetMulti,
            "assigned": RunStaffS2Widget,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize character form with custom fields and configuration.

        Args:
            *args: Positional arguments passed to parent form class.
            **kwargs: Keyword arguments including 'params' dict with event, run,
                and features configuration.

        Raises:
            KeyError: If required 'params' key is missing from kwargs.

        """
        # Initialize parent form class with all provided arguments
        super().__init__(*args, **kwargs)

        # Initialize storage for field details and metadata
        self.details: dict[str, Any] = {}

        # Set up character-specific fields including factions and custom questions
        self._init_character()

    def check_editable(self, question: WritingQuestion) -> bool:
        """Check if a question is editable based on event config and instance status.

        Args:
            question: Question object to check editability for

        Returns:
            True if question is editable, False otherwise

        """
        # If character approval is disabled, all questions are editable
        character_approval_enabled = get_event_config(
            self.params.get("event").id,
            "user_character_approval",
            default_value=False,
            context=self.params,
        )
        if not character_approval_enabled:
            return True

        # Get allowed statuses for editing this question
        allowed_editable_statuses = question.get_editable()

        # If no status restrictions, question is always editable
        if not allowed_editable_statuses:
            return True

        # Check if current instance status allows editing
        return self.instance.status in allowed_editable_statuses

    def _init_custom_fields(self) -> None:
        """Initialize custom form fields for character creation.

        Sets up dynamic form fields based on event configuration and custom field definitions,
        organizing fields into default and custom categories, and handling organizer-specific
        fields and character completion proposals.

        Args:
            self: The form instance containing event parameters and organizer status.

        Returns:
            None: This method modifies the form instance in place.

        Note:
            - Uses parent event if current event has a parent
            - Handles different field types based on question configuration
            - Adds organizer-specific fields when applicable
            - Conditionally adds character proposal field for user approval workflow

        """
        # Get event, preferring parent event if available
        event = self.params.get("event")
        if event.parent:
            event = event.parent

        # Initialize field categorization sets
        fields_default = {"event"}
        fields_custom = set()

        # Initialize registration questions and get counts
        self._init_registration_question(self.instance, event)
        registration_counts = get_registration_counts(self.params.get("run"))

        # Process each question to create form fields
        for question in self.questions:
            field_key = self._init_field(question, registration_counts=registration_counts, is_organizer=self.orga)
            if not field_key:
                continue

            # Categorize fields based on question type length
            if len(question.typ) == 1:
                fields_custom.add(field_key)
            else:
                fields_default.add(field_key)

        # Add organizer-specific fields and configurations
        if self.orga:
            for field_key in ["player", "status"]:
                fields_default.add(field_key)
                self.reorder_field(field_key)

            # Add access token field for external writing access
            if (
                get_event_config(event.id, "writing_external_access", default_value=False, context=self.params)
                and self.instance.pk
            ):
                fields_default.add("access_token")
                self.reorder_field("access_token")

        # Remove unused fields from form
        all_fields = set(self.fields.keys()) - fields_default
        for field_label in all_fields - fields_custom:
            self.delete_field(field_label)

        # Add character completion proposal field for user approval workflow
        if (
            not self.orga
            and get_event_config(event.id, "user_character_approval", default_value=False, context=self.params)
            and (not self.instance.pk or self.instance.status in [CharacterStatus.CREATION, CharacterStatus.REVIEW])
        ):
            self.fields["propose"] = forms.BooleanField(
                required=False,
                label=_("Complete"),
                help_text=_(
                    "Click here to confirm that you have completed the character and are ready to "
                    "propose it to the staff. Be careful: some fields may no longer be editable. "
                    "Leave the field blank to save your changes and to be able to continue them in "
                    "the future.",
                ),
                widget=forms.CheckboxInput(attrs={"class": "checkbox_single"}),
            )

    def _init_character(self) -> None:
        """Initialize character-specific form data."""
        self._init_factions()
        self._init_custom_fields()

    def _init_factions(self) -> None:
        """Initialize faction selection field for character form.

        Sets up a multiple choice field for selectable factions if the faction
        feature is enabled for the event.
        """
        if "faction" not in self.params.get("features"):
            return

        queryset = self.params.get("run").event.get_elements(Faction).filter(selectable=True)

        self.fields["factions_list"] = forms.ModelMultipleChoiceField(
            queryset=queryset,
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains"]),
            required=False,
            label=_("Factions"),
        )

        self.show_available_factions = _("Show available factions")

        self.initial["factions_list"] = []
        if not self.instance.pk:
            return

        self.initial["factions_list"] = list(
            self.instance.factions_list.order_by("number").values_list("id", flat=True)
        )

    def _save_multi(self, field: str, instance: Any) -> None:
        """Save multi-select field data for the given instance.

        Handles special processing for factions_list field by managing
        faction relationships through set operations to efficiently
        add/remove faction associations.

        Args:
            field: The field name being processed
            instance: The model instance being saved

        Returns:
            None

        """
        # Skip plots field - it's handled separately in _save_plot()
        if field == "plots":
            return None

        # Handle non-faction fields using parent implementation
        if field != "factions_list":
            return super()._save_multi(field, instance)

        # Only process factions if the factions_list field is present in the form
        if "factions_list" not in self.cleaned_data:
            return None

        # Get new faction IDs from cleaned form data
        new = set(self.cleaned_data["factions_list"].values_list("pk", flat=True))

        # Get the faction event context for filtering existing factions
        faction_event = self.params.get("run").event.get_class_parent(Faction)

        # Get current faction IDs associated with the instance
        # For non-orga users, only consider selectable factions to preserve staff-assigned non-selectable factions
        old_query = instance.factions_list.filter(event=faction_event)
        if not self.orga:
            old_query = old_query.filter(selectable=True)
        old = set(old_query.values_list("id", flat=True))

        # Remove factions that are no longer selected
        for ch in old - new:
            instance.factions_list.remove(ch)

        # Add newly selected factions
        for ch in new - old:
            instance.factions_list.add(ch)
        return None

    def clean(self) -> dict:
        """Clean and validate form data.

        Validates that only one primary faction is selected from the factions list.
        Inherits base validation from parent class and adds custom faction validation.

        Returns:
            dict: Cleaned form data after validation

        Raises:
            ValidationError: If more than one primary faction is selected

        """
        cleaned_data = super().clean()

        # Check if factions_list field exists in cleaned data
        if "factions_list" in self.cleaned_data:
            # Count primary factions to ensure only one is selected
            prim = 0
            for el in self.cleaned_data["factions_list"]:
                # Increment counter for each primary faction found
                if el.typ == FactionType.PRIM:
                    prim += 1

            # Validate that no more than one primary faction is selected
            if prim > 1:
                raise ValidationError({"factions_list": _("Select only one primary faction")})

        return cleaned_data


class OrgaCharacterForm(CharacterForm):
    """Form for OrgaCharacter."""

    page_info = _("Manage characters")

    page_title = _("Characters")

    load_templates: ClassVar[list] = ["char"]

    load_js: ClassVar[list] = ["characters-choices", "characters-relationships", "factions-choices"]

    load_form: ClassVar[list] = ["characters-relationships"]

    orga = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with event-specific writing configuration and conditional setup."""
        super().__init__(*args, **kwargs)

        # Init relationships
        self._init_relationships()

        # Skip additional initialization for new instances
        if not self.instance.pk:
            return

        # Initialize experience points configuration
        self._init_px()

        # Initialize plot-related fields
        self._init_plots()

    def _init_relationships(self) -> None:
        """Init relationships data."""
        if "relationships" not in self.params.get("features"):
            return

        # Skip if AJAX auto-save
        if self.params.get("request") and self.params["request"].POST.get("ajax") == "1":
            return

        if "character_finder" in self.params.get("features", []):
            get_event_cache_all(self.params)

        # Process character relationships for display and validation
        self._characters_relationships()

        # Load relationship field max length from event configuration
        self.relationship_max_length = int(
            get_event_config(
                self.params["event"].id, "writing_relationship_length", default_value=10000, context=self.params
            ),
        )

    def _characters_relationships(self) -> None:
        """Set up character relationships data and widgets for editing."""
        context = self.params

        context["relationships"] = {}

        with contextlib.suppress(ObjectDoesNotExist):
            context["rel_tutorial"] = Feature.objects.get(slug="relationships").tutorial

        context["TINYMCE_DEFAULT_CONFIG"] = conf_settings.TINYMCE_DEFAULT_CONFIG
        widget = EventCharacterS2WidgetUuid(attrs={"id": "new_rel_select"})
        widget.set_event(context["event"])
        context["new_rel"] = widget.render(name="new_rel_select", value="")

        if not self.instance.pk:
            return

        relationships_by_character_uuid = {}

        direct_relationships = Relationship.objects.filter(source=self.instance).select_related("target")

        for relationship in direct_relationships:
            if relationship.target.uuid not in relationships_by_character_uuid:
                relationships_by_character_uuid[relationship.target.uuid] = {"char": relationship.target}
            relationships_by_character_uuid[relationship.target.uuid]["direct"] = relationship.text

        inverse_relationships = Relationship.objects.filter(target=self.instance).select_related("source")

        for relationship in inverse_relationships:
            if relationship.source.uuid not in relationships_by_character_uuid:
                relationships_by_character_uuid[relationship.source.uuid] = {"char": relationship.source}
            relationships_by_character_uuid[relationship.source.uuid]["inverse"] = relationship.text

        sorted_relationships = sorted(
            relationships_by_character_uuid.items(),
            key=lambda character_entry: len(character_entry[1].get("direct", ""))
            + len(character_entry[1].get("inverse", "")),
            reverse=True,
        )
        context["relationships"] = dict(sorted_relationships)

    def _init_character(self) -> None:
        """Initialize character form fields based on features and event configuration.

        Sets up factions, custom fields, player assignment, approval status,
        mirror character choices, and special character fields.
        """
        self._init_factions()

        self._init_custom_fields()

        if "user_character" in self.params["features"]:
            self.configure_field_association("player", self.params["association_id"])
        else:
            self.delete_field("player")

        if not get_event_config(
            self.params["event"].id, "user_character_approval", default_value=False, context=self.params
        ):
            self.delete_field("status")

        if get_event_config(self.params["event"].id, "casting_mirror", default_value=False, context=self.params):
            if "mirror" in self.fields:
                characters_query = self.params["run"].event.get_elements(Character).all()
                character_choices = [(character.uuid, character.name) for character in characters_query]
                self.fields["mirror"].choices = [("", _("--- NOT ASSIGNED ---")), *character_choices]
        else:
            self.delete_field("mirror")

        # Add active field for campaign feature
        if "campaign" in self.params["features"]:
            self.fields["active"] = forms.BooleanField(
                required=False,
                label=_("Active"),
                help_text=_("Inactive characters can't be assigned to players"),
                widget=forms.CheckboxInput(attrs={"class": "checkbox_single"}),
            )
            # Set initial value - default to True unless character has inactive config
            if self.instance.pk:
                is_inactive = self.instance.get_config("inactive", default_value=False)
                self.initial["active"] = not (is_inactive == "True" or is_inactive is True)
            else:
                self.initial["active"] = True

        self._init_special_fields()

    def _init_plots(self) -> None:
        """Initialize plot assignment fields in character forms.

        Sets up plot selection options and plot-related character
        attributes for story-driven character development.
        """
        if "plot" not in self.params["features"]:
            return

        self.fields["plots"] = forms.ModelMultipleChoiceField(
            label="Plots",
            queryset=self.params["event"].get_elements(Plot),
            required=False,
            widget=EventPlotS2WidgetMulti,
        )
        self.configure_field_event("plots", self.params["event"])

        self.plots = self.instance.get_plot_characters()
        self.initial["plots"] = [plot_character.plot_id for plot_character in self.plots]

        self.add_char_finder = []
        self.ordering_up = {}
        self.ordering_down = {}
        self.field_link = {}

        total_plots = len(self.plots)
        for index, plot_character in enumerate(self.plots):
            plot_name = plot_character.plot.name
            plot_field_name = f"pl_{plot_character.plot_id}"
            plot_field_id = f"id_{plot_field_name}"
            self.fields[plot_field_name] = forms.CharField(
                widget=WritingTinyMCE(),
                label=plot_name,
                help_text=_("This text will be added to the sheet, in the plot paragraph %(name)s")
                % {"name": plot_name},
                required=False,
            )
            if plot_character.text:
                self.initial[plot_field_name] = plot_character.text

            if plot_character.plot.text:
                self.details[plot_field_id] = plot_character.plot.text
            self.show_link.append(plot_field_id)
            self.add_char_finder.append(plot_field_id)

            reverse_args = [self.params["run"].get_slug(), plot_character.plot_id]
            self.field_link[plot_field_id] = reverse("orga_plots_edit", args=reverse_args)

            # if not first, add to ordering up
            if index != 0:
                reverse_args = [self.params["run"].get_slug(), plot_character.id, "0"]
                self.ordering_up[plot_field_id] = reverse("orga_plots_rels_order", args=reverse_args)

            # if not last, add to ordering down
            if index != total_plots - 1:
                reverse_args = [self.params["run"].get_slug(), plot_character.id, "1"]
                self.ordering_down[plot_field_id] = reverse("orga_plots_rels_order", args=reverse_args)

    def _save_plot(self, instance: Any) -> None:
        """Save plot associations for a character.

        Args:
            instance: Character instance to save plots for

        """
        if "plot" not in self.params["features"]:
            return

        # Only process plots if the plots field is present in the form
        if "plots" not in self.cleaned_data:
            return

        # Add / remove plots
        selected = set(self.cleaned_data.get("plots", []))
        current = set(Plot.objects.filter(plotcharacterrel__character=instance))

        to_add = selected - current
        to_remove = current - selected

        if to_remove:
            PlotCharacterRel.objects.filter(character=instance, plot__in=[p.pk for p in to_remove]).delete()

        for plot in to_add:
            PlotCharacterRel.objects.create(character=instance, plot=plot)

        # update texts
        for pr in instance.get_plot_characters():
            field = f"pl_{pr.plot_id}"
            if field not in self.cleaned_data:
                continue
            if self.cleaned_data[field] == pr.text:
                continue
            pr.text = self.cleaned_data[field]
            pr.save()

    def _init_px(self) -> None:
        """Initialize PX (ability/delivery) form fields if PX feature is enabled."""
        if "px" not in self.params["features"]:
            return

        # px ability
        self.fields["px_ability_list"] = forms.ModelMultipleChoiceField(
            label=_("Abilities"),
            queryset=self.params["run"].event.get_elements(AbilityPx),
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains"]),
            required=False,
        )

        self.initial["px_ability_list"] = list(self.instance.px_ability_list.values_list("id", flat=True))
        self.show_link.append("id_px_ability_list")

        # delivery list
        self.fields["px_delivery_list"] = forms.ModelMultipleChoiceField(
            label=_("Delivery"),
            queryset=self.params["run"].event.get_elements(DeliveryPx),
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains"]),
            required=False,
        )

        self.initial["px_delivery_list"] = list(self.instance.px_delivery_list.values_list("id", flat=True))
        self.show_link.append("id_px_delivery_list")

    def _save_px(self, instance: Any) -> None:
        """Save PX-related data to the instance if PX feature is enabled."""
        # Check if PX feature is available
        if "px" not in self.params["features"]:
            return

        # Set ability list if present in cleaned data
        if "px_ability_list" in self.cleaned_data:
            instance.px_ability_list.set(self.cleaned_data["px_ability_list"])

        # Set delivery list if present in cleaned data
        if "px_delivery_list" in self.cleaned_data:
            instance.px_delivery_list.set(self.cleaned_data["px_delivery_list"])

    def _init_factions(self) -> None:
        """Initialize faction selection fields for character forms.

        Sets up faction choice fields with proper widget configuration
        when faction feature is enabled.
        """
        if "faction" not in self.params["features"]:
            return

        queryset = self.params["run"].event.get_elements(Faction)

        self.fields["factions_list"] = forms.ModelMultipleChoiceField(
            queryset=queryset,
            widget=FactionS2WidgetMulti(),
            required=False,
            label=_("Factions"),
        )
        self.configure_field_event("factions_list", self.params["event"])

        self.show_available_factions = _("Show available factions")

        if not self.instance.pk:
            return

        # Initial factions values
        self.initial["factions_list"] = list(
            self.instance.factions_list.order_by("number").values_list("id", flat=True)
        )

    def _save_relationships(self, instance: Any) -> None:
        """Save character relationships from form data.

        Args:
            instance: Character instance being saved

        """
        if "relationships" not in self.params["features"]:
            return

        uuid_to_id = dict(self.params["event"].get_elements(Character).values_list("uuid", "id"))

        rel_data = {k: v for k, v in self.data.items() if k.startswith("rel")}
        # Only process relationships if relationship fields are present in the form
        if not rel_data:
            return
        for key, value in rel_data.items():
            match = re.match(r"rel_([a-zA-Z0-9]+)", key)
            if not match:
                continue
            ch_uuid = match.group(1)
            rel_type = "direct"

            # check character uuid is in chars of the event
            if ch_uuid not in uuid_to_id:
                msg = f"char {ch_uuid} not recognized"
                raise Http404(msg)

            character_id = uuid_to_id[ch_uuid]

            # if value is empty
            if not value:
                # if wasn't present, do nothing
                if ch_uuid not in self.params["relationships"] or rel_type not in self.params["relationships"][ch_uuid]:
                    continue
                # else delete
                rel = self._get_rel(character_id, instance, rel_type)
                save_version(rel, TextVersionChoices.RELATIONSHIP, self.params["member"], to_delete=True)
                rel.delete()
                continue

            # if the value is present, and is the same as before, do nothing
            if (
                ch_uuid in self.params["relationships"]
                and rel_type in self.params["relationships"][ch_uuid]
                and value == self.params["relationships"][ch_uuid][rel_type]
            ):
                continue

            # Check text length against configuration using centralized value
            # Use strip_tags to get plain text length from HTML content
            plain_text = strip_tags(value)
            if len(plain_text) > self.relationship_max_length:
                msg = f"Relationship text for character {ch_uuid} exceeds maximum length of {self.relationship_max_length} characters. Current length: {len(plain_text)}"
                raise ValidationError(
                    msg,
                )

            rel = self._get_rel(character_id, instance, rel_type)
            rel.text = value
            rel.save()

    @staticmethod
    def _get_rel(character_id: int, instance: Any, relationship_type: str) -> Relationship:
        """Get or create a relationship between characters based on type.

        Args:
            character_id: Character ID for the relationship
            instance: Source or target instance depending on relationship_type
            relationship_type: Either "direct" or reverse relationship type

        Returns:
            The relationship object

        """
        # Create direct relationship (instance -> character)
        if relationship_type == "direct":
            (relationship, _created) = Relationship.objects.get_or_create(source_id=instance.pk, target_id=character_id)
        # Create reverse relationship (character -> instance)
        else:
            (relationship, _created) = Relationship.objects.get_or_create(target_id=instance.pk, source_id=character_id)
        return relationship

    def save(self, commit: bool = True) -> object:  # noqa: FBT001, FBT002, ARG002
        """Save the form instance and handle related data.

        Args:
            commit: Whether to save to database.

        Returns:
            The saved instance.

        """
        # Save the main instance using parent's save method
        instance = super().save()

        # Only process related data if instance has been persisted
        if instance.pk:
            self._save_plot(instance)
            self._save_px(instance)
            self._save_relationships(instance)
            self._save_active(instance)

        return instance

    def _save_active(self, instance: Any) -> None:
        """Save active status to CharacterConfig if campaign feature is enabled."""
        # Check if campaign feature is available
        if "campaign" not in self.params["features"]:
            return

        # Only process if active field is present in cleaned data
        if "active" not in self.cleaned_data:
            return

        # Get the active field value
        is_active = self.cleaned_data["active"]

        # Handle inactive status - create/update CharacterConfig if inactive
        if not is_active:
            # Character is inactive - ensure CharacterConfig exists with inactive=True
            CharacterConfig.objects.update_or_create(
                character=instance,
                name="inactive",
                defaults={"value": "True"},
            )
        else:
            # Character is active - remove CharacterConfig if it exists
            CharacterConfig.objects.filter(character=instance, name="inactive").delete()


class OrgaWritingQuestionForm(BaseModelForm):
    """Form for OrgaWritingQuestion."""

    page_info = _("Manage form questions for writing elements")

    page_title = _("Writing Questions")

    class Meta:
        model = WritingQuestion
        exclude: ClassVar[list] = ["order", "applicable"]
        widgets: ClassVar[dict] = {
            "description": forms.Textarea(attrs={"rows": 3, "cols": 40}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
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

        Filters question types based on event features and existing usage to populate
        the 'typ' field choices. Removes already used types (except for current instance)
        and filters based on active features.

        Side Effects:
            - Modifies self.fields["typ"].choices
            - Sets self.prevent_canc based on instance type length
        """
        # Get writing questions applicable to current writing type
        writing_questions = self.params["event"].get_elements(WritingQuestion)
        writing_questions = writing_questions.filter(applicable=self.params["writing_typ"])

        # Extract already used question types to avoid duplicates
        already_used_types = list(writing_questions.values_list("typ", flat=True).distinct())

        # Handle existing instance - allow editing current type
        if self.instance.pk and self.instance.typ:
            already_used_types.remove(self.instance.typ)
            # Prevent cancellation for multi-character default types
            self.prevent_canc = len(self.instance.typ) > 1

        # Build filtered choices list based on features and usage
        filtered_choices = []
        for choice in WritingQuestionType.choices:
            # Handle feature-related types (length > 1)
            if len(choice[0]) > 1:
                # Skip if type already exists
                if choice[0] in already_used_types:
                    continue

                # Check feature activation for non-default types
                if choice[0] not in ["name", "teaser", "text"] and choice[0] not in self.params["features"]:
                    continue

            # Handle character type 'c' - requires 'px_rules' config
            elif choice[0] == "c":
                if not get_event_config(self.params["event"].id, "px_rules", default_value=False):
                    continue

            # Add valid choice to final list
            filtered_choices.append(choice)

        # Apply filtered choices to form field
        self.fields["typ"].choices = filtered_choices

    def _init_editable(self) -> None:
        """Initialize the editable field based on character approval configuration."""
        # Check if character approval feature is enabled for this event
        if not get_event_config(
            self.params["event"].id, "user_character_approval", default_value=False, context=self.params
        ):
            self.delete_field("editable")
        else:
            # Create multiple choice field for character status selection
            self.fields["editable"] = forms.MultipleChoiceField(
                choices=CharacterStatus.choices,
                widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"}),
                required=False,
            )

            # Set initial values from existing instance if available
            if self.instance and self.instance.pk:
                self.initial["editable"] = self.instance.get_editable()

    def clean_editable(self) -> str:
        """Join editable field values into comma-separated string."""
        return ",".join(self.cleaned_data["editable"])

    def save(self, commit: bool = True) -> WritingQuestion:  # noqa: FBT001, FBT002
        """Save form with applicable type from context for new instances."""
        instance = super().save(commit=False)
        # Only set applicable for new instances
        if not instance.pk:
            instance.applicable = self.params["writing_typ"]
        if commit:
            instance.save()
        return instance


class OrgaWritingOptionForm(BaseModelForm):
    """Form for OrgaWritingOption."""

    page_info = _("Manage options in form questions for writing elements")

    page_title = _("Writing options")

    class Meta:
        model = WritingOption
        exclude: ClassVar[list] = ["order", "question"]
        widgets: ClassVar[dict] = {
            "requirements": EventWritingOptionS2WidgetMulti,
            "tickets": TicketS2WidgetMulti,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with feature-based field customization.

        Args:
            *args: Variable positional arguments passed to parent class
            **kwargs: Variable keyword arguments passed to parent class

        Side effects:
            Modifies form fields based on available features and event configuration

        """
        super().__init__(*args, **kwargs)

        if "wri_que_max" not in self.params["features"]:
            self.delete_field("max_available")

        if "wri_que_tickets" not in self.params["features"]:
            self.delete_field("tickets")
        else:
            self.configure_field_event("tickets", self.params["event"])

        if "wri_que_requirements" not in self.params["features"]:
            self.delete_field("requirements")
        else:
            self.configure_field_event("requirements", self.params["event"])

    def save(self, commit: bool = True) -> WritingOption:  # noqa: FBT001, FBT002
        """Save the form instance, setting question for new instances."""
        if not self.instance.pk and "question" in self.params:
            self.instance.question = self.params["question"]

        return super().save(commit=commit)
