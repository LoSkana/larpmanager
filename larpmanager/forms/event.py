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

import logging
from typing import Any, ClassVar

from django import forms
from django.conf import settings as conf_settings
from django.core.exceptions import ValidationError
from django.forms import Textarea
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_event_config
from larpmanager.cache.feature import clear_event_features_cache, get_event_features
from larpmanager.forms.association import ExePreferencesForm
from larpmanager.forms.base import BaseModelCssForm, BaseModelForm
from larpmanager.forms.config import ConfigForm, ConfigType
from larpmanager.forms.feature import FeatureForm, QuickSetupForm
from larpmanager.forms.utils import (
    AssociationMemberS2WidgetMulti,
    CampaignS2Widget,
    DatePickerInput,
    DateTimePickerInput,
    EventS2Widget,
    SlugInput,
    TemplateS2Widget,
    WritingTinyMCE,
    prepare_permissions_role,
    remove_choice,
    save_permissions_role,
)
from larpmanager.models.access import EventPermission, EventRole
from larpmanager.models.event import (
    DevelopStatus,
    Event,
    EventButton,
    EventConfig,
    EventText,
    EventTextType,
    ProgressStep,
    Run,
)
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    WritingQuestion,
    WritingQuestionType,
    _get_writing_elements,
    _get_writing_mapping,
)
from larpmanager.models.utils import generate_id
from larpmanager.utils.auth.permission import has_event_permission
from larpmanager.utils.core.common import copy_class
from larpmanager.views.orga.registration import _get_registration_fields

logger = logging.getLogger(__name__)


class EventCharactersPdfForm(ConfigForm):
    """Form for configuring PDF export settings for event characters."""

    class Meta:
        model = Event
        fields = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the instance with cancellation prevention.

        Initializes the parent class with all provided arguments and sets up
        the instance to prevent cancellation operations.

        Args:
            *args: Variable length argument list passed to parent class.
            **kwargs: Arbitrary keyword arguments passed to parent class.

        Returns:
            None

        """
        # Initialize parent class with all provided arguments
        super().__init__(*args, **kwargs)

        # Set flag to prevent cancellation operations on this instance
        self.prevent_canc: bool = True

    def set_configs(self) -> None:
        """Configure PDF-related settings for the application.

        Sets up the PDF configuration section and adds various configuration
        options including CSS styling, header content, and footer content
        for PDF generation and customization.

        This method creates a dedicated PDF configuration section and populates
        it with three main configuration options:
        - CSS styling for PDF appearance customization
        - Header HTML content for PDF documents
        - Footer HTML content for PDF documents
        """
        # Set up the main PDF configuration section
        self.set_section("pdf", "PDF")

        # Add CSS configuration for PDF styling
        # This allows users to customize the visual appearance of generated PDFs
        self.add_configs("page_css", ConfigType.TEXTAREA, "CSS", _("Insert the css code to customize the pdf printing"))

        # Add header content configuration
        # Users can define custom HTML content to appear at the top of each PDF page
        self.add_configs("header_content", ConfigType.TEXTAREA, _("Header"), _("Insert the html code for the header"))

        # Add footer content configuration
        # Users can define custom HTML content to appear at the bottom of each PDF page
        self.add_configs("footer_content", ConfigType.TEXTAREA, _("Footer"), _("Insert the html code for the footer"))


class OrgaEventForm(BaseModelForm):
    """Form for managing general event settings and basic configuration."""

    page_title = _("Event")

    page_info = _("Manage event settings")

    load_templates: ClassVar[list] = ["event"]

    class Meta:
        model = Event
        fields = (
            "name",
            "slug",
            "tagline",
            "where",
            "authors",
            "description",
            "genre",
            "visible",
            "max_pg",
            "max_waiting",
            "max_filler",
            "website",
            "register_link",
            "parent",
            "association",
        )

        widgets: ClassVar[dict] = {"slug": SlugInput, "parent": CampaignS2Widget, "description": WritingTinyMCE}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize event form with field configuration based on context.

        Configures form fields dynamically based on activated features and
        whether the event is being created or edited. Removes unnecessary
        fields from the form when corresponding features are disabled.

        Args:
            *args: Positional arguments passed to parent form class
            **kwargs: Keyword arguments passed to parent form class, including
                     'params' with feature configuration and context data

        Side effects:
            - Modifies form fields by deleting disabled feature fields
            - Sets prevent_canc flag to prevent cancellation
            - Configures campaign parent field widget

        """
        super().__init__(*args, **kwargs)

        # Prevent cancellation for non-executive users
        if "exe" not in self.params:
            self.prevent_canc = True

        # Configure slug field based on whether this is a new or existing event
        if self.instance.pk:
            # Slug cannot be changed after event creation
            self.delete_field("slug")
        else:
            # Slug is required for new events
            self.fields["slug"].required = True

        # Build list of fields to delete based on disabled features
        # Check each display-related feature and mark fields for removal if disabled
        dl = [
            s
            for s in ["visible", "website", "tagline", "where", "authors", "genre", "register_link"]
            if s not in self.params["features"]
        ]

        # Initialize campaign parent selection and add to deletion list if disabled
        self.init_campaign(dl)

        # Add waiting list configuration field if feature is disabled
        if "waiting" not in self.params["features"]:
            dl.append("max_waiting")

        # Add filler list configuration field if feature is disabled
        if "filler" not in self.params["features"]:
            dl.append("max_filler")

        # Remove all marked fields from the form
        for m in dl:
            self.delete_field(m)

    def init_campaign(self, disabled_fields: list) -> None:
        """Initialize campaign field by setting association and exclusions."""
        # Set association for parent widget and exclude current instance if editing
        self.configure_field_association("parent", self.params["association_id"])
        if self.instance and self.instance.pk:
            self.fields["parent"].widget.set_exclude(self.instance.pk)

        # Remove parent field if campaign feature disabled or no parent options available
        if "campaign" not in self.params["features"] or not self.fields["parent"].widget.get_queryset().count():
            disabled_fields.append("parent")
            return

    def clean_slug(self) -> str:
        """Validate event slug for uniqueness and reserved word conflicts.

        Ensures that the slug is unique among all events within the association
        (excluding current instance during updates) and is not a reserved static prefix.

        Returns:
            str: The validated slug value.

        Raises:
            ValidationError: If slug is already used by another event or is a reserved word.

        """
        data = self.cleaned_data["slug"]
        logger.debug("Validating event slug: %s", data)

        # Check if slug is already used by another event in this association
        lst = Event.objects.filter(association_id=self.params["association_id"], slug=data)
        if self.instance is not None and self.instance.pk is not None:
            lst = lst.exclude(pk=self.instance.pk)
        if lst.count() > 0:
            msg = "Slug already used!"
            raise ValidationError(msg)

        # Check if slug conflicts with reserved static prefixes
        if data and hasattr(conf_settings, "STATIC_PREFIXES") and data in conf_settings.STATIC_PREFIXES:
            msg = "Reserved word, please choose another!"
            raise ValidationError(msg)

        return data


class OrgaFeatureForm(FeatureForm):
    """Form for selecting and managing event features."""

    page_title = _("Event features")

    page_info = _(
        "Manage features activated for this event and all its runs (click on a feature to show its description)",
    )

    load_js: ClassVar[list] = ["feature-search"]

    class Meta:
        model = Event
        fields: ClassVar[list] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and features."""
        super().__init__(*args, **kwargs)
        self._init_features(is_association=False)

    def save(self, commit: bool = True) -> Event:  # noqa: FBT001, FBT002, ARG002
        """Save the form instance and update event features cache.

        Args:
            commit: Whether to save the instance to database.

        Returns:
            The saved EventConfig instance.

        """
        # Save form without committing to database yet
        instance: Event = super().save(commit=False)

        # Update associated features for this event
        self._save_features(instance)

        # Invalidate cached event features
        clear_event_features_cache(instance.id)

        return instance


class OrgaConfigForm(ConfigForm):
    """Form for configuring event-specific settings and feature options."""

    page_title = _("Event Configuration")

    page_info = _("Manage configuration of activated features")

    section_replace = True

    load_js: ClassVar[list] = ["config-search"]

    class Meta:
        model = Event
        fields = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and prevent registration cancellation."""
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def set_configs(self) -> None:
        """Configure form fields for event settings and features.

        Sets up various configuration sections including email notifications,
        visualization options, and event-specific settings.
        """
        self.set_section("email", _("Email notifications"))
        disable_assignment_label = _("Disable assignment")
        disable_assignment_help_text = _(
            "If checked: Does not send communication to the participant when the character is assigned",
        )
        self.add_configs("mail_character", ConfigType.BOOL, disable_assignment_label, disable_assignment_help_text)

        self.set_section("visualisation", _("Visualisation"))

        show_shortcuts_label = _("Show shortcuts")
        show_shortcuts_help_text = _(
            "If checked: when first accessing the manage page, automatically show shortcuts on mobile",
        )
        self.add_configs("show_shortcuts_mobile", ConfigType.BOOL, show_shortcuts_label, show_shortcuts_help_text)

        export_label = _("Export")
        export_help_text = _("If checked: allow to export characters and registration in a easily readable page")
        self.add_configs("show_export", ConfigType.BOOL, export_label, export_help_text)

        limitations_label = _("Limitations")
        limitations_help_text = _("If checked: Show summary page with number of tickets/options used")
        self.add_configs("show_limitations", ConfigType.BOOL, limitations_label, limitations_help_text)

        self.set_config_reg_form()

        self.set_config_gallery()

        self.set_config_structure()

        self.set_config_writing()

        self.set_config_character()

        self.set_config_char_form()

        self.set_config_custom()

        self.set_config_accounting()

        self.set_config_casting()

        self.set_config_registration()

    def set_config_gallery(self) -> None:
        """Configure gallery settings for event forms."""
        if "character" not in self.params["features"]:
            return

        self.set_section("gallery", _("Gallery"))

        label = _("Require login")
        help_text = _("If checked, the characters will not be displayed to those not logged in to the system")
        self.add_configs("gallery_hide_login", ConfigType.BOOL, label, help_text)

        label = _("Require registration")
        help_text = _(
            "If checked, the characters will not be displayed to those who are not registered to the event",
        )
        self.add_configs("gallery_hide_signup", ConfigType.BOOL, label, help_text)

        if "character" in self.params["features"]:
            label = _("Hide unassigned characters")
            help_text = _(
                "If checked, does not show characters in the gallery who have not been assigned a participant",
            )
            self.add_configs("gallery_hide_uncasted_characters", ConfigType.BOOL, label, help_text)

            label = _("Hide participants without a character")
            help_text = _(
                "If checked, does not show participants in the gallery who have not been assigned a character",
            )
            self.add_configs("gallery_hide_uncasted_players", ConfigType.BOOL, label, help_text)

    def set_config_reg_form(self) -> None:
        """Configure registration form settings and display options.

        Sets up configuration fields for registration form display,
        grouping options, and participant visibility settings.

        This method creates a configuration section for registration-related
        settings and adds various boolean configuration options that control
        how registration forms are displayed and processed.
        """
        # Create the registration configuration section
        self.set_section("reg_form", _("Registrations"))

        # Configure table grouping behavior
        grouping_label = _("Disable grouping")
        grouping_help_text = _(
            "If checked, all registrations are displayed in a single table rather than being separated by type",
        )
        self.add_configs("registration_no_grouping", ConfigType.BOOL, grouping_label, grouping_help_text)

        # Configure staff visibility permissions for registration questions
        allowed_label = _("Allowed")
        allowed_help_text = _(
            "If checked, enables to set for each registration question the list of staff members allowed to see it's answers from the participants",
        )
        self.add_configs("registration_reg_que_allowed", ConfigType.BOOL, allowed_label, allowed_help_text)

        # Control visibility of unavailable registration options
        hide_unavailable_label = _("Hide not available")
        hide_unavailable_help_text = _(
            "If checked, options no longer available in the registration form are hidden, "
            "instead of being displayed disabled",
        )
        self.add_configs(
            "registration_hide_unavailable",
            ConfigType.BOOL,
            hide_unavailable_label,
            hide_unavailable_help_text,
        )

        # Enable faction-based question visibility
        faction_selection_label = _("Faction selection")
        faction_selection_help_text = _(
            "If checked, allows a registration form question to be visible only if the participant is "
            "assigned to certain factions.",
        )
        self.add_configs(
            "registration_reg_que_faction",
            ConfigType.BOOL,
            faction_selection_label,
            faction_selection_help_text,
        )

        # Enable ticket-based question visibility
        ticket_selection_label = _("Ticket selection")
        ticket_selection_help_text = _(
            "If checked, allows a registration form question to be visible based on the selected registration ticket.",
        )
        self.add_configs(
            "registration_reg_que_tickets",
            ConfigType.BOOL,
            ticket_selection_label,
            ticket_selection_help_text,
        )

        # Enable age-based question visibility
        age_selection_label = _("Age selection")
        age_selection_help_text = _(
            "If checked, allows a registration form question to be visible based on the participant's age",
        )
        self.add_configs("registration_reg_que_age", ConfigType.BOOL, age_selection_label, age_selection_help_text)

    def set_config_char_form(self) -> None:
        """Configure character form options for events with character feature enabled.

        Sets up configuration fields for character form behavior including
        visibility options, maximum selections, ticket requirements, and dependencies.
        """
        if "character" in self.params["features"]:
            self.set_section("char_form", _("Character form"))

            label = _("Hide not available")
            help_text = _(
                "If checked, options no longer available in the form are hidden, instead of being displayed disabled",
            )
            self.add_configs("character_form_hide_unavailable", ConfigType.BOOL, label, help_text)

            label = _("Maximum available")
            help_text = _("If checked, an option can be chosen a maximum number of times")
            self.add_configs("character_form_wri_que_max", ConfigType.BOOL, label, help_text)

            label = _("Ticket selection")
            help_text = _("If checked, allows a option to be visible only to participants with selected ticket")
            self.add_configs("character_form_wri_que_tickets", ConfigType.BOOL, label, help_text)

            label = _("Requirements")
            help_text = _("If checked, allows a option to be visible only if other options are selected")
            self.add_configs("character_form_wri_que_requirements", ConfigType.BOOL, label, help_text)

    def set_config_structure(self) -> None:
        """Configure structural event settings including pre-registration, mail server, and cover options."""
        if "pre_register" in self.params["features"]:
            self.set_section("pre_reg", _("Pre-registration"))
            field_label = _("Active")
            field_help_text = _("If checked, makes pre-registration for this event available")
            self.add_configs("pre_register_active", ConfigType.BOOL, field_label, field_help_text)

        if "custom_mail" in self.params["features"]:
            self.set_section("custom_mail_server", _("Customised mail server"))
            field_help_text = ""

            field_label = _("Use TLD")
            self.add_configs("mail_server_use_tls", ConfigType.BOOL, field_label, field_help_text)

            field_label = _("Host Address")
            self.add_configs("mail_server_host", ConfigType.CHAR, field_label, field_help_text)

            field_label = _("Port")
            self.add_configs("mail_server_port", ConfigType.INT, field_label, field_help_text)

            field_label = _("Username of account")
            self.add_configs("mail_server_host_user", ConfigType.CHAR, field_label, field_help_text)

            field_label = _("Password of account")
            self.add_configs("mail_server_host_password", ConfigType.CHAR, field_label, field_help_text)

        if "cover" in self.params["features"]:
            self.set_section("cover", _("Character cover"))
            field_label = _("Desalt thumbnail")
            field_help_text = _("If checked, shows the original image in the cover, not the thumbnail version")
            self.add_configs("cover_orig", ConfigType.BOOL, field_label, field_help_text)

    def set_config_writing(self) -> None:
        """Configure writing system settings for events.

        Sets up background writing features, character story elements,
        and writing deadline configurations for character development.
        """
        if "character" in self.params["features"]:
            self.set_section("writing", _("Writing"))

            config_label = _("Title")
            config_help_text = _("Enables field 'title', a short (2-3 words) text added to the character's name")
            self.add_configs("writing_title", ConfigType.BOOL, config_label, config_help_text)

            config_label = _("Cover")
            config_help_text = _(
                "Enables field 'cover', to shown a specific image in the gallery - until assigned to a participant",
            )
            self.add_configs("writing_cover", ConfigType.BOOL, config_label, config_help_text)

            config_label = _("Hide")
            config_help_text = _("Enables field 'hide', to be able to hide writing element from participants")
            self.add_configs("writing_hide", ConfigType.BOOL, config_label, config_help_text)

            config_label = _("Assigned")
            config_help_text = _(
                "Enables field 'assigned', to track which staff member is responsible for each writing element",
            )
            self.add_configs("writing_assigned", ConfigType.BOOL, config_label, config_help_text)

            config_label = _("Field visibility")
            config_help_text = _(
                "Normally all character fields (public or private) are shown; with this configuration you can select which ones to display at any given time",
            )
            self.add_configs("writing_field_visibility", ConfigType.BOOL, config_label, config_help_text)

            if "relationships" in self.params["features"]:
                config_label = _("Relationships max length")
                config_help_text = _("Set maximum length on character relationships (default 10000 characters)")
                self.add_configs("writing_relationship_length", ConfigType.INT, config_label, config_help_text)

            config_label = _("Disable character finder")
            config_help_text = (
                _("Disable the system that finds the character number when a special reference symbol is written")
                + " (#, @, ^)"
            )
            self.add_configs("writing_disable_char_finder", ConfigType.BOOL, config_label, config_help_text)

            config_label = _("Replacing names")
            config_help_text = _("If checked, character names will be automatically replaced by a reference")
            self.add_configs("writing_substitute", ConfigType.BOOL, config_label, config_help_text)

            config_label = _("Paste as text")
            config_help_text = _(
                "If checked, automatically removes formatting when pasting text into the WYSIWYG editor",
            )
            self.add_configs("writing_paste_text", ConfigType.BOOL, config_label, config_help_text)

            config_label = _("Disable Auto save")
            config_help_text = _("If checked, automatic saving during editing will be disable for writing elements")
            self.add_configs("writing_disable_auto", ConfigType.BOOL, config_label, config_help_text)

            config_label = _("External access")
            config_help_text = _(
                "If checked, generates secret urls to share the full character sheet with a not signed up user",
            )
            self.add_configs("writing_external_access", ConfigType.BOOL, config_label, config_help_text)

            config_label = _("Unimportant")
            config_help_text = _(
                "If checked, allows to track the plots or relationships not really important for the character",
            )
            self.add_configs("writing_unimportant", ConfigType.BOOL, config_label, config_help_text)

    def set_config_character(self) -> None:
        """Configure character-related settings including campaign and faction options.

        This method sets up configuration fields for various character-related features
        including campaign management, faction independence, experience points system,
        and player-managed character creation settings.

        The configuration sections are conditionally created based on available features
        in self.params["features"]. Each section contains relevant boolean, integer,
        and other configuration options with appropriate labels and help text.

        Note:
            Requires self.params["features"] to contain feature flags and access to
            self.set_section() and self.add_configs() methods.

        """
        # Configure campaign-related settings if campaign feature is enabled
        if "campaign" in self.params["features"]:
            self.set_section("campaign", _("Campaign"))
            independent_factions_label = _("Independent factions")
            independent_factions_help_text = _("If checked, do not use the parent event's factions")
            self.add_configs(
                "campaign_faction_indep",
                ConfigType.BOOL,
                independent_factions_label,
                independent_factions_help_text,
            )

        # Configure experience points system if px feature is enabled
        if "px" in self.params["features"]:
            self.set_section("px", _("Experience points"))

            # Player selection configuration - allows participants to choose abilities
            player_selection_label = _("Player selection")
            player_selection_help_text = _(
                "If checked, participants may add abilities themselves, by selecting from those that "
                "are visible, and whose pre-requisites they meet.",
            )
            self.add_configs("px_user", ConfigType.BOOL, player_selection_label, player_selection_help_text)

            # Undo period configuration - time window for skill revocation
            undo_period_label = _("Undo period")
            undo_period_help_text = _(
                "Time window (in hours) during which the user can revoke a chosen skill and recover spent XP (default is 0)",
            )
            self.add_configs("px_undo", ConfigType.INT, undo_period_label, undo_period_help_text)

            # Initial experience points configuration
            initial_experience_points_label = _("Initial experience points")
            initial_experience_points_help_text = _("Initial value of experience points for all characters")
            self.add_configs(
                "px_start",
                ConfigType.INT,
                initial_experience_points_label,
                initial_experience_points_help_text,
            )

            # Ability templates configuration
            ability_templates_label = _("Ability templates")
            ability_templates_help_text = _(
                "If checked, enables ability templates that can be reused across multiple abilities",
            )
            self.add_configs("px_templates", ConfigType.BOOL, ability_templates_label, ability_templates_help_text)

            # Rules configuration
            rules_label = _("Rules")
            rules_help_text = _(
                "If checked, enables rules for computed character fields based on abilities",
            )
            self.add_configs("px_rules", ConfigType.BOOL, rules_label, rules_help_text)

            # Modifiers configuration
            modifiers_label = _("Modifiers")
            modifiers_help_text = _(
                "If checked, enables modifiers that can adjust ability costs based on prerequisites and requirements",
            )
            self.add_configs("px_modifiers", ConfigType.BOOL, modifiers_label, modifiers_help_text)

        # Configure player character editor if user_character feature is enabled
        if "user_character" in self.params["features"]:
            self.set_section("user_character", _("Player editor"))

            # Maximum character limit configuration
            max_characters_label = _("Maximum number")
            max_characters_help_text = _(
                "Maximum number of characters the player can create (default=0, no creation allowed)"
            )
            self.add_configs("user_character_max", ConfigType.INT, max_characters_label, max_characters_help_text)

            # Character approval process configuration
            character_approval_label = _("Approval")
            character_approval_help_text = _("If checked, activates a staff-managed approval process for characters")
            self.add_configs(
                "user_character_approval",
                ConfigType.BOOL,
                character_approval_label,
                character_approval_help_text,
            )

            # Player relationships configuration
            player_relationships_label = _("Relationships")
            player_relationships_help_text = _(
                "If checked, enables participants to write their own list of character relationships",
            )
            self.add_configs(
                "user_character_player_relationships",
                ConfigType.BOOL,
                player_relationships_label,
                player_relationships_help_text,
            )

    def set_config_custom(self) -> None:
        """Configure character customization form fields for event settings."""
        if "custom_character" in self.params["features"]:
            self.set_section("custom_character", _("Character customisation"))

            character_name_label = _("Name")
            character_name_help_text = _(
                "If checked, it allows participants to customise the names of their characters",
            )
            self.add_configs("custom_character_name", ConfigType.BOOL, character_name_label, character_name_help_text)

            character_profile_label = _("Profile")
            character_profile_help_text = _(
                "If checked, allows participants to customise their characters' profile picture",
            )
            self.add_configs(
                "custom_character_profile",
                ConfigType.BOOL,
                character_profile_label,
                character_profile_help_text,
            )

            character_pronoun_label = _("Pronoun")
            character_pronoun_help_text = _(
                "If checked, it allows participants to customise their characters' pronouns",
            )
            self.add_configs(
                "custom_character_pronoun",
                ConfigType.BOOL,
                character_pronoun_label,
                character_pronoun_help_text,
            )

            character_song_label = _("Song")
            character_song_help_text = _("If checked, it allows participants to indicate the song of their characters")
            self.add_configs("custom_character_song", ConfigType.BOOL, character_song_label, character_song_help_text)

            character_private_label = _("Private")
            character_private_help_text = _(
                "If checked, it allows participants to enter private information on their characters, "
                "visible only to them and the staff",
            )
            self.add_configs(
                "custom_character_private",
                ConfigType.BOOL,
                character_private_label,
                character_private_help_text,
            )

            character_public_label = _("Public")
            character_public_help_text = _(
                "If checked, it allows participants to enter public information on their characters, visible to all",
            )
            self.add_configs(
                "custom_character_public",
                ConfigType.BOOL,
                character_public_label,
                character_public_help_text,
            )

    def set_config_casting(self) -> None:
        """Configure casting-related form fields for event settings.

        Sets up casting preferences, assignments, and display options
        when the casting feature is enabled.
        """
        if "casting" in self.params["features"]:
            self.set_section("casting", _("Casting"))

            label = _("Minimum preferences")
            help_text = _("Minimum number of preferences")
            self.add_configs("casting_min", ConfigType.INT, label, help_text)

            label = _("Maximum preferences")
            help_text = _("Maximum number of preferences")
            self.add_configs("casting_max", ConfigType.INT, label, help_text)

            label = _("Additional Preferences")
            help_text = _("Additional preferences, for random assignment when no solution is found (default 0)")
            self.add_configs("casting_add", ConfigType.INT, label, help_text)

            label = _("Field for exclusions")
            help_text = _(
                "If checked, it adds a field in which the participant can indicate which elements they "
                "wish to avoid altogether",
            )
            self.add_configs("casting_avoid", ConfigType.BOOL, label, help_text)

            label = _("Assignments")
            help_text = _("Number of characters to be assigned (default 1)")
            self.add_configs("casting_characters", ConfigType.INT, label, help_text)

            label = _("Mirror")
            help_text = _("Enables to set a character as a 'mirror' for another, to hide it's true nature")
            self.add_configs("casting_mirror", ConfigType.BOOL, label, help_text)

            label = _("Show statistics")
            help_text = _("If checked, participants will be able to view for each character the preference statistics")
            self.add_configs("casting_show_pref", ConfigType.BOOL, label, help_text)

            label = _("Show history")
            help_text = _("If checked, shows participants the histories of preferences entered")
            self.add_configs("casting_history", ConfigType.BOOL, label, help_text)

            label = _("Registration priority")
            help_text = _(
                "A measure of how much to favor earlier registrants (0=default disabled, 1=normal, 10=strong)",
            )
            self.add_configs("casting_reg_priority", ConfigType.INT, label, help_text)

            label = _("Payment priority")
            help_text = _(
                "A measure of how much to favor participants who completed full payment earlier (0=default disabled, 1=normal, 10=strong)",
            )
            self.add_configs("casting_pay_priority", ConfigType.INT, label, help_text)

    def set_config_accounting(self) -> None:
        """Configure event-specific accounting settings.

        Sets up payment alerts, financial notifications, and event-level
        payment configurations for event management. This method configures
        three main feature areas: payment settings, token/credit controls,
        and bring-a-friend discount system.

        The method checks for specific features in self.params["features"]
        and adds corresponding configuration sections with their respective
        settings.
        """
        # Configure payment-related settings if payment feature is enabled
        if "payment" in self.params["features"]:
            self.set_section("payment", _("Payments"))

            # Payment alert configuration - days before deadline to notify users
            payment_alert_label = _("Alert")
            payment_alert_help_text = _(
                "Given a payment deadline, indicates the number of days under which it notifies "
                "the participant to proceed with the payment. Default 30.",
            )
            self.add_configs("payment_alert", ConfigType.INT, payment_alert_label, payment_alert_help_text)

            # Custom payment reason configuration with dynamic field substitution
            payment_reason_label = _("Causal")
            payment_reason_help_text = _(
                "If present, it indicates the reason for the payment that the participant must put on the payments they make.",
            )
            payment_reason_help_text += (
                " "
                + _("You can use the following fields, they will be filled in automatically")
                + ":"
                + "{player_name}, {question_name}"
            )
            self.add_configs("payment_custom_reason", ConfigType.CHAR, payment_reason_label, payment_reason_help_text)

            # Option to disable provisional registrations - auto-confirm all registrations
            disable_provisional_label = _("Disable provisional")
            disable_provisional_help_text = _(
                "If checked, all registrations are confirmed even if no payment has been received",
            )
            self.add_configs(
                "payment_no_provisional",
                ConfigType.BOOL,
                disable_provisional_label,
                disable_provisional_help_text,
            )

        if "tokens" in self.params["features"]:
            self.set_section("tokens", _("Tokens"))

            # Token disabling option for this specific event
            disable_tokens_label = _("Disable Tokens")
            disable_tokens_help_text = _("If checked, no tokens will be used in the entries of this event")
            self.add_configs("tokens_disable", ConfigType.BOOL, disable_tokens_label, disable_tokens_help_text)

        if "credits" in self.params["features"]:
            self.set_section("credits", _("Credits"))

            # Credit disabling option for this specific event
            disable_credits_label = _("Disable credits")
            disable_credits_help_text = _("If checked, no credits will be used in the entries for this event")
            self.add_configs(
                "credits_disable",
                ConfigType.BOOL,
                disable_credits_label,
                disable_credits_help_text,
            )

        # Configure bring-a-friend referral discount system
        if "bring_friend" in self.params["features"]:
            self.set_section("bring_friend", _("Bring a friend"))

            # Discount amount for the referring participant
            referrer_discount_label = _("Forward discount")
            referrer_discount_help_text = _(
                "Value of the discount for the registered participant who gives the code to a friend who signs up",
            )
            self.add_configs(
                "bring_friend_discount_to",
                ConfigType.INT,
                referrer_discount_label,
                referrer_discount_help_text,
            )

            # Discount amount for the referred friend
            referred_discount_label = _("Discount back")
            referred_discount_help_text = _(
                "Value of the discount for the friend who signs up using the code of a registered participant",
            )
            self.add_configs(
                "bring_friend_discount_from",
                ConfigType.INT,
                referred_discount_label,
                referred_discount_help_text,
            )

    def set_config_registration(self) -> None:
        """Configure event registration settings.

        Sets up ticket tiers, registration options, and staff ticket availability
        including special ticket types like NPC, collaborator, and seller tiers
        based on available features.

        This method configures various registration-related settings by adding
        configuration options to different sections. It handles basic ticket types
        and conditional features like reduced tickets, filler tickets, and lottery
        systems.
        """
        # Set up main tickets section
        self.set_section("tickets", _("Tickets"))

        # Configure staff ticket tier
        staff_ticket_label = "Staff"
        staff_ticket_help_text = _("If checked, allow ticket tier: Staff")
        self.add_configs("ticket_staff", ConfigType.BOOL, staff_ticket_label, staff_ticket_help_text)

        # Configure NPC ticket tier
        npc_ticket_label = "NPC"
        npc_ticket_help_text = _("If checked, allow ticket tier: NPC")
        self.add_configs("ticket_npc", ConfigType.BOOL, npc_ticket_label, npc_ticket_help_text)

        # Configure collaborator ticket tier
        collaborator_ticket_label = "Collaborator"
        collaborator_ticket_help_text = _("If checked, allow ticket tier: Collaborator")
        self.add_configs(
            "ticket_collaborator",
            ConfigType.BOOL,
            collaborator_ticket_label,
            collaborator_ticket_help_text,
        )

        # Configure seller ticket tier
        seller_ticket_label = "Seller"
        seller_ticket_help_text = _("If checked, allow ticket tier: Seller")
        self.add_configs("ticket_seller", ConfigType.BOOL, seller_ticket_label, seller_ticket_help_text)

        # Configure reduced/patron tickets if feature is enabled
        if "reduced" in self.params["features"]:
            self.set_section("reduced", _("Patron / Reduced"))
            reduced_ratio_label = "Ratio"
            reduced_ratio_help_text = _(
                "Indicates the ratio between reduced and patron tickets, multiplied by 10. "
                "Example: 10 -> 1 reduced ticket for 1 patron ticket. 20 -> 2 reduced tickets for "
                "1 patron ticket. 5 -> 1 reduced ticket for 2 patron tickets",
            )
            self.add_configs("reduced_ratio", ConfigType.INT, reduced_ratio_label, reduced_ratio_help_text)

        # Configure filler ticket options if feature is enabled
        if "filler" in self.params["features"]:
            self.set_section("filler", _("Ticket Filler"))
            filler_free_registration_label = _("Free registration")
            filler_free_registration_help_text = _(
                "If checked, participants may sign up as fillers at any time; otherwise, they may only "
                "do so if the stipulated number of characters has been reached",
            )
            self.add_configs(
                "filler_always",
                ConfigType.BOOL,
                filler_free_registration_label,
                filler_free_registration_help_text,
            )

        # Configure lottery system if feature is enabled
        if "lottery" in self.params["features"]:
            self.set_section("lottery", _("Lottery"))

            # Set number of lottery draws
            lottery_num_draws_label = _("Number of extractions")
            lottery_num_draws_help_text = _("Number of tickets to be drawn")
            self.add_configs("lottery_num_draws", ConfigType.INT, lottery_num_draws_label, lottery_num_draws_help_text)

            # Set conversion ticket type for lottery winners
            lottery_conversion_ticket_label = _("Conversion ticket")
            lottery_conversion_ticket_help_text = _("Name of the ticket into which to convert")
            self.add_configs(
                "lottery_ticket",
                ConfigType.CHAR,
                lottery_conversion_ticket_label,
                lottery_conversion_ticket_help_text,
            )


class OrgaAppearanceForm(BaseModelCssForm):
    """Form for customizing event appearance and styling."""

    page_title = _("Event Appearance")

    page_info = _("Manage appearance and presentation of the event")

    load_js: ClassVar[list] = ["appearance-colors"]

    class Meta:
        model = Event
        fields = (
            "cover",
            "carousel_img",
            "carousel_text",
            "background",
            "font",
            "pri_rgb",
            "sec_rgb",
            "ter_rgb",
        )

    event_css = forms.CharField(
        widget=Textarea(attrs={"rows": 15}),
        required=False,
        help_text=_("These CSS commands will be carried over to all pages in your Association space"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with conditional field handling based on carousel feature."""
        super().__init__(*args, **kwargs)

        self.prevent_canc = True

        # Configure visible links for event CSS
        self.show_link = ["id_event_css"]

        # Remove carousel fields if feature is disabled
        dl = []
        if "carousel" not in self.params["features"]:
            dl.append("carousel_text")
            dl.append("carousel_img")
        else:
            self.show_link.append("id_carousel_text")

        # Delete unused fields from form
        for m in dl:
            self.delete_field(m)

    def save(self, commit: bool = True) -> Event:  # noqa: FBT001, FBT002, ARG002
        """Save the form and generate a unique CSS code for the skin."""
        # Generate unique 32-character identifier for CSS code
        self.instance.css_code = generate_id(32)
        instance = super().save()

        # Save associated CSS file
        self.save_css(instance)
        return instance

    @staticmethod
    def get_input_css() -> str:
        """Get the CSS input field name.

        Returns:
            str: CSS input field identifier

        """
        return "event_css"

    @staticmethod
    def get_css_path(event_instance: Event) -> str:
        """Generate CSS file path for event styling.

        Args:
            event_instance: Event instance

        Returns:
            str: Path to CSS file

        """
        return f"css/{event_instance.association.slug}_{event_instance.slug}_{event_instance.css_code}.css"


class OrgaEventTextForm(BaseModelForm):
    """Form for managing event-specific text content and messages."""

    page_title = _("Event Texts")

    page_info = _("Manage event texts")

    class Meta:
        abstract = True
        model = EventText
        exclude = ("number",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize event text form with feature-based field filtering.

        Filters available text types based on activated features and
        event configuration, setting appropriate choices and help texts.

        Args:
            *args: Variable positional arguments
            **kwargs: Variable keyword arguments including event and features

        """
        super().__init__(*args, **kwargs)
        ch = EventTextType.choices
        delete_choice = []

        if "character" not in self.params["features"]:
            delete_choice.append(EventTextType.INTRO)

        if not get_event_config(
            self.params["event"].id, "user_character_approval", default_value=False, context=self.params
        ):
            delete_choice.extend(
                [EventTextType.CHARACTER_PROPOSED, EventTextType.CHARACTER_APPROVED, EventTextType.CHARACTER_REVIEW],
            )

        for tp in delete_choice:
            ch = remove_choice(ch, tp)
        self.fields["typ"].choices = ch

        help_texts = {
            EventTextType.INTRO: _("Text show at the start of all character sheets"),
            EventTextType.TOC: _("Terms and conditions of signup, shown in a page linked in the registration form"),
            EventTextType.REGISTER: _("Added to the registration page, before the form"),
            EventTextType.SEARCH: _("Added at the top of the search page of characters"),
            EventTextType.SIGNUP: _("Added at the bottom of mail confirming signup to participants"),
            EventTextType.ASSIGNMENT: _("Added at the bottom of mail notifying participants of character assignment"),
            EventTextType.CHARACTER_PROPOSED: _(
                "Content of mail notifying participants of their character in proposed status",
            ),
            EventTextType.CHARACTER_APPROVED: _(
                "Content of mail notifying participants of their character in approved status",
            ),
            EventTextType.CHARACTER_REVIEW: _(
                "Content of mail notifying participants of their character in review status",
            ),
        }
        help_text = []
        for choice_typ, text in help_texts.items():
            if choice_typ in delete_choice:
                continue
            help_text.append(f"<b>{choice_typ.label}</b>: {text}")
        self.fields["typ"].help_text = " - ".join(help_text)

    def clean(self) -> dict:
        """Validate event text uniqueness by type and language.

        Ensures only one default text exists per type and prevents duplicate
        language-type combinations for the same event.

        Returns:
            Cleaned form data after validation.

        Raises:
            ValidationError: If default or language-type combination already exists.

        """
        cleaned_data = super().clean()

        # Extract form field values
        default = cleaned_data.get("default")
        typ = cleaned_data.get("typ")
        language = cleaned_data.get("language")

        # Validate default text uniqueness per type
        if default:
            res = EventText.objects.filter(event_id=self.params["event"].id, default=True, typ=typ)
            # Ensure the existing default is not the current instance being edited
            if res.count() > 0 and res.first().pk != self.instance.pk:
                self.add_error("default", "There is already a language set as default!")

        # Validate language-type combination uniqueness
        res = EventText.objects.filter(event_id=self.params["event"].id, language=language, typ=typ)
        # Ensure the existing combination is not the current instance being edited
        if res.count() > 0 and res.first().pk != self.instance.pk:
            self.add_error("language", "There is already a language of this type!")

        return cleaned_data


class OrgaEventRoleForm(BaseModelForm):
    """Form for managing event access roles and permissions."""

    page_title = _("Roles")

    page_info = _("Manage event access roles")

    load_templates: ClassVar[list] = ["share"]

    class Meta:
        model = EventRole
        fields = ("name", "members", "event")
        widgets: ClassVar[dict] = {"members": AssociationMemberS2WidgetMulti}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure members widget with association context."""
        super().__init__(*args, **kwargs)
        # Configure members widget with association ID from params
        self.configure_field_association("members", self.params["association_id"])
        # Prepare permission-based role selection for event permissions
        prepare_permissions_role(self, EventPermission)

    def save(self, commit: bool = True) -> EventRole:  # noqa: FBT001, FBT002, ARG002
        """Save form instance and update role permissions."""
        instance: EventRole = super().save()
        save_permissions_role(instance, self)
        return instance


class OrgaEventButtonForm(BaseModelForm):
    """Form for editing event navigation buttons."""

    page_title = _("Event Navigation")

    page_info = _("Manage event navigation buttons")

    class Meta:
        model = EventButton
        exclude = ("number",)


class OrgaRunForm(ConfigForm):
    """Form for managing event sessions/runs with dates and configuration."""

    page_title = _("Session")

    class Meta:
        model = Run
        exclude = ("balance", "number", "plan", "paid")

        widgets: ClassVar[dict] = {
            "start": DatePickerInput,
            "end": DatePickerInput,
            "registration_open": DateTimePickerInput,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize RunForm with event-specific configuration and field setup.

        Args:
            *args: Variable length argument list passed to parent form
            **kwargs: Arbitrary keyword arguments passed to parent form

        """
        super().__init__(*args, **kwargs)

        self.main_class = ""

        if "exe" not in self.params:
            self.prevent_canc = True

        dl = []

        if not self.params.get("is_creation", False) and (not self.instance.pk or not self.instance.event):
            event_field = forms.ChoiceField(
                required=True,
                choices=[
                    (el.id, el.name)
                    for el in Event.objects.filter(association_id=self.params["association_id"], template=False)
                ],
            )
            self.fields = {"event": event_field} | self.fields
            self.fields["event"].widget = EventS2Widget()
            self.configure_field_association("event", self.params["association_id"])
            self.fields["event"].help_text = _("Select the event of this new session")
            self.choose_event = True
            self.page_info = _("Manage new session for an existing event")
        else:
            self.page_info = _("Manage date settings for this event")
            self.delete_field("event")

        # do not show cancelled or done options for development if date are not set
        if not self.instance.pk or not self.instance.start or not self.instance.end:
            self.fields["development"].choices = [
                (choice.value, choice.label)
                for choice in DevelopStatus
                if choice not in [DevelopStatus.CANC, DevelopStatus.DONE]
            ]
        status_text = {
            DevelopStatus.START: _("Not visible to users"),
            DevelopStatus.SHOW: _("Visible in the homepage"),
            DevelopStatus.DONE: _("Concluded and archived"),
            DevelopStatus.CANC: _("Not active anymore"),
        }
        self.fields["development"].help_text = ", ".join(
            f"<b>{label}</b>: {status_text[DevelopStatus(value)]}"
            for value, label in self.fields["development"].choices
        )

        dl.extend(
            [
                s
                for s in ["registration_open", "registration_secret"]
                if not self.instance.pk or not self.instance.event or s not in self.params["features"]
            ]
        )

        for s in dl:
            self.delete_field(s)

        self.show_sections = True

    def set_configs(self) -> None:  # noqa: C901 - Complex form configuration with feature-dependent field setup
        """Configure event-specific form fields and sections.

        Sets up various event features and their configuration options
        based on enabled features for character management.
        """
        if "character" not in self.params["features"]:
            return

        if not get_event_config(
            self.params["event"].id, "writing_field_visibility", default_value=False, context=self.params
        ):
            return

        help_text = _(
            "Selected fields will be displayed as follows: public fields visible to all participants, "
            "private fields visible only to assigned participants",
        )

        writing_elements = _get_writing_elements()

        basic_types = BaseQuestionType.get_basic_types()
        basic_types.add(WritingQuestionType.COMPUTED)
        self.set_section("visibility", _("Visibility"))
        for writing_element_key, writing_element_label, _writing_element_type in writing_elements:
            if "writing_fields" not in self.params or writing_element_key not in self.params["writing_fields"]:
                continue
            if writing_element_key in ["plot", "prologue"]:
                continue
            questions = self.params["writing_fields"][writing_element_key]["questions"]
            field_choices = []
            for question_field in questions.values():
                question_type = question_field["typ"]
                if question_type in basic_types:
                    question_type = str(question_field["uuid"])

                field_choices.append((question_type, question_field["name"]))

            self.add_configs(
                f"show_{writing_element_key}",
                ConfigType.MULTI_BOOL,
                writing_element_label,
                help_text,
                extra_data=field_choices,
            )

        writing_elements = []

        additional_elements_display = {
            "plot": _("Plots"),
            "relationships": _("Relationships"),
            "speedlarp": _("Speedlarp"),
            "prologue": _("Prologues"),
            "workshop": _("Workshop"),
            "print_pdf": _("PDF"),
        }

        additional_choices = []
        for element_key, element_display_name in additional_elements_display.items():
            if self.instance.pk and element_key in self.params["features"]:
                additional_choices.append((element_key, element_display_name))
        if additional_choices:
            help_text = _("Selected elements will be shown to participants")
            self.add_configs(
                "show_addit",
                ConfigType.MULTI_BOOL,
                _("Elements"),
                help_text,
                extra_data=additional_choices,
            )

        self.set_section("visibility", _("Visibility"))
        for writing_element_key, writing_element_label in writing_elements:
            self.add_configs(
                f"show_{writing_element_key}",
                ConfigType.BOOL,
                writing_element_label,
                writing_element_label,
            )

    def clean(self) -> dict[str, Any]:
        """Validate that end date is defined and not before start date.

        Returns:
            Cleaned form data.

        Raises:
            ValidationError: If end/start dates are missing or end is before start.

        """
        cleaned_data = super().clean()

        # Validate end date is present
        if "end" not in cleaned_data or not cleaned_data["end"]:
            raise ValidationError({"end": _("You need to define the end date!")})

        # Validate start date is present
        if "start" not in cleaned_data or not cleaned_data["start"]:
            raise ValidationError({"start": _("You need to define the start date!")})

        # Ensure end date is not before start date
        if cleaned_data["end"] < cleaned_data["start"]:
            raise ValidationError({"end": _("End date cannot be before start date!")})

        return cleaned_data


class OrgaProgressStepForm(BaseModelForm):
    """Form for managing event progression steps."""

    page_title = _("Progression")

    class Meta:
        model = ProgressStep
        exclude = ("number", "order")


class ExeEventForm(OrgaEventForm):
    """Extended event form for executors with template support."""

    page_title = _("Events")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize ExeEventForm with template event selection."""
        super().__init__(*args, **kwargs)

        if "template" in self.params["features"] and not self.instance.pk:
            qs = Event.objects.filter(association_id=self.params["association_id"], template=True)
            self.fields["template_event"] = forms.ModelChoiceField(
                required=False,
                queryset=qs,
                label=_("Template"),
                help_text=_(
                    "You can indicate a template event from which functionality and configurations will be copied",
                ),
                widget=TemplateS2Widget(),
            )

            self.configure_field_association("template_event", self.params["association_id"])

            if qs.count() == 1:
                self.initial["template_event"] = qs.first()

    def save(self, commit: bool = True) -> Event:  # noqa: FBT001, FBT002, ARG002
        """Save event with optional template copying.

        Args:
            commit: Whether to commit changes to database.

        Returns:
            Saved event instance.

        """
        instance: Event = super().save(commit=False)

        # Copy template event data if template feature enabled and event is new
        if "template" in self.params["features"] and not self.instance.pk and self.cleaned_data.get("template_event"):
            event_id = self.cleaned_data["template_event"].id
            event = Event.objects.get(pk=event_id)

            # Save instance first to get pk for M2M and FK relations
            instance.save()

            # Copy features and configurations from template
            instance.features.add(*event.features.all())
            copy_class(instance.id, event_id, EventConfig)
            copy_class(instance.id, event_id, EventRole)

        instance.save()

        return instance


class ExeTemplateForm(FeatureForm):
    """Form for creating and managing event templates."""

    page_title = _("Event Template")

    page_info = _("Manage template features (click on a feature to show its description)")

    class Meta:
        model = Event
        fields: ClassVar[list] = ["name"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the instance and configure the feature system."""
        # Initialize parent class and feature system
        super().__init__(*args, **kwargs)
        self._init_features(is_association=False)

    def save(self, commit: bool = True) -> Event:  # noqa: FBT001, FBT002, ARG002
        """Save the form instance, setting template and association defaults.

        Args:
            commit: Whether to save the instance to the database.

        Returns:
            The saved Event instance.

        """
        instance: Event = super().save(commit=False)

        # Ensure template flag is set
        if not instance.template:
            instance.template = True

        # Set association from params if not already set
        if not instance.association_id:
            instance.association_id = self.params["association_id"]

        # Save instance before processing features
        if not instance.pk:
            instance.save()

        self._save_features(instance)

        return instance


class ExeTemplateRolesForm(OrgaEventRoleForm):
    """Form for managing template event roles with optional members."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize template roles form with optional member requirement.

        Args:
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments

        """
        super().__init__(*args, **kwargs)
        self.fields["members"].required = False


class OrgaQuickSetupForm(QuickSetupForm):
    """Form for quick setup of essential event settings."""

    page_title = _("Quick Setup")

    page_info = _("You are choosing the most common features to activate for your event")

    class Meta:
        model = Event
        fields: ClassVar[list] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize OrgaQuickSetupForm with event feature configuration.

        Args:
            *args: Variable length argument list passed to parent
            **kwargs: Arbitrary keyword arguments passed to parent

        """
        super().__init__(*args, **kwargs)

        self.setup = {}

        if self.instance.association.skin_id == 1:
            self.setup.update(
                {
                    "character": (
                        True,
                        _("Characters"),
                        _("Do you want to manage characters assigned to registered participants"),
                    ),
                    "casting": (
                        True,
                        _("Casting algorithm"),
                        _("Do you want to assign characters using a casting algorithm"),
                    ),
                    "user_character": (
                        True,
                        _("Player editor"),
                        _("Do you want to allow participants to create their own characters"),
                    ),
                    "px": (
                        True,
                        _("Experience points"),
                        _("Do you want to manage character progression through abilities"),
                    ),
                },
            )

        self.setup.update(
            {
                "registration_open": (
                    True,
                    _("Registration opening date"),
                    _("Do you want to open registrations at a specific date and time instead of immediately"),
                ),
                "registration_secret": (
                    True,
                    _("Early registration link"),
                    _("Do you want to enable a secret registration link to allow early sign-ups"),
                ),
                "player_cancellation": (
                    True,
                    _("Signup cancellation"),
                    _("Do you want to allow users to cancel their registrations on their own"),
                ),
                "reg_installments": (
                    True,
                    _("Payment installments"),
                    _("Do you want to split the registration fee into fixed payment installments"),
                ),
                "reg_quotas": (
                    True,
                    _("Payment quotas"),
                    _("Do you want to split the registration fee into dynamic payment quotas"),
                ),
                "pay_what_you_want": (
                    True,
                    _("Voluntary donation"),
                    _("Do you want to allow users to add a voluntary donation to their registration fee"),
                ),
            },
        )

        self.init_fields(get_event_features(self.instance.pk))


class OrgaPreferencesForm(ExePreferencesForm):
    """Form for setting event organizer preferences and field visibility."""

    def set_configs(self) -> None:
        """Configure organizer preference settings and field display options.

        Sets up default field visibility options for registration and character forms.
        """
        super().set_configs()

        basic_question_types = BaseQuestionType.get_basic_types()
        event_id = self.params["event"].id

        self.set_section("open", _("Default fields"))

        help_text = _("Select which fields should open automatically when the list is displayed")

        self._add_reg_configs(event_id, help_text)

        # Add writings fields
        writing_elements = _get_writing_elements()
        for writing_element in writing_elements:
            self.add_writing_configs(basic_question_types, event_id, help_text, writing_element)

    def _add_reg_configs(self, event_id: int, help_text: str) -> None:
        """Add registration-related configuration fields to the form.

        Configures form fields for registration management including accounting,
        email settings, chronology, and various registration feature options.
        Also adds dynamic fields based on user permissions and available registration
        fields for the specific event.

        Args:
            event_id: The ID of the event to configure registration for
            help_text: Help text to display for the configuration section

        Returns:
            None

        """
        # Check if user has permission to manage registrations for this event
        if not has_event_permission(
            self.params["request"],
            self.params,
            self.params["event"].slug,
            "orga_registrations",
        ):
            return

        # Initialize list for additional configuration fields
        extra_config_fields = []

        # Define standard registration feature fields with their identifiers and labels
        feature_fields = [
            ("", "#load_accounting", _("Accounting")),
            ("", "email", _("Email")),
            ("", "date", _("Chronology")),
            ("additional_tickets", "additionals", _("Additional")),
            ("gift", "gift", _("Gift")),
            ("membership", "membership", _("Member")),
            ("faction", "factions", _("Factions")),
            ("custom_character", "custom", _("Customisations")),
            ("reg_surcharges", "sur", _("Surcharge")),
            ("discount", "disc", _("Discounts")),
        ]

        # Add feature-based fields to the extra configuration options
        self.add_feature_extra(extra_config_fields, feature_fields)

        # Retrieve dynamic registration fields for current user and event
        registration_fields = _get_registration_fields(self.params, self.params["member"])
        field_name_max_length = 20

        # Add dynamic fields with truncated names if they exist
        if registration_fields:
            extra_config_fields.extend(
                [
                    (
                        f".lq_{field_uuid}",
                        registration_field.name
                        if len(registration_field.name) <= field_name_max_length
                        else registration_field.name[: field_name_max_length - 5] + " [...]",
                    )
                    for field_uuid, registration_field in registration_fields.items()
                ],
            )

        # Create the final configuration with all collected fields
        self.add_configs(
            f"open_registration_{event_id}",
            ConfigType.MULTI_BOOL,
            _("Registrations"),
            help_text,
            extra_data=extra_config_fields,
        )

    def add_writing_configs(self, basics: set, event_id: int, help_text: str, writing_section: tuple) -> None:
        """Add writing-related configuration fields to the event form.

        This method adds configuration fields for writing elements (characters, factions,
        plots, etc.) to the event configuration form based on available features and
        permissions.

        Args:
            basics: Basic configuration settings dictionary
            event_id: Unique identifier for the event
            help_text: Descriptive text to help users understand the configuration
            writing_section: Writing section configuration tuple containing (section_name, display_name)

        Returns:
            None: Method modifies the form in place

        """
        # Get the writing feature mapping and check if feature is available
        feature_mapping = _get_writing_mapping()
        if feature_mapping.get(writing_section[0]) not in self.params["features"]:
            return

        # Verify writing fields exist for this section
        if "writing_fields" not in self.params or writing_section[0] not in self.params["writing_fields"]:
            return

        # Check user permissions for this writing section
        if not has_event_permission(
            self.params["request"],
            self.params,
            self.params["event"].slug,
            f"orga_{writing_section[0]}s",
        ):
            return

        # Extract field configurations and prepare extra options
        section_fields = self.params["writing_fields"][writing_section[0]]["questions"]
        extra_config_options = []

        # Compile basic field configurations
        self._compile_configs(basics, extra_config_options, section_fields)

        # Add character-specific configuration options
        if writing_section[0] == "character":
            # Add player field if character limit is set
            if get_event_config(self.params["event"].id, "user_character_max", default_value=0, context=self.params):
                extra_config_options.append(("player", _("Player")))

            # Add status field if character approval is enabled
            if get_event_config(
                self.params["event"].id, "user_character_approval", default_value=False, context=self.params
            ):
                extra_config_options.append(("status", _("Status")))

            # Define character feature fields with their config keys and labels
            feature_fields = [
                ("px", "px", _("XP")),
                ("plot", "plots", _("Plots")),
                ("relationships", "relationships", _("Relationships")),
                ("speedlarp", "speedlarp", _("Speedlarp")),
                ("prologue", "prologues", _("Prologue")),
            ]

            # Add faction field if faction feature is enabled
            if "faction" in self.params["features"]:
                available_questions = self.params["event"].get_elements(WritingQuestion)
                faction_question = available_questions.get(
                    applicable=QuestionApplicable.CHARACTER,
                    typ=WritingQuestionType.FACTIONS,
                )
                feature_fields.insert(0, ("faction", f"q_{faction_question.uuid}", _("Factions")))

            self.add_feature_extra(extra_config_options, feature_fields)

        # Add characters field for faction and plot sections
        elif writing_section[0] in ["faction", "plot"]:
            extra_config_options.append(("characters", _("Characters")))

        # Add traits field for quest and trait sections
        elif writing_section[0] in ["quest", "trait"]:
            extra_config_options.append(("traits", _("Traits")))

        # Add stats field for all writing sections
        extra_config_options.append(("stats", "Stats"))

        # Add the compiled configuration to the form
        self.add_configs(
            f"open_{writing_section[0]}_{event_id}",
            ConfigType.MULTI_BOOL,
            writing_section[1],
            help_text,
            extra_data=extra_config_options,
        )

    @staticmethod
    def _compile_configs(basic_question_types: set, compiled_options: list, field_definitions: dict) -> None:
        """Compile configuration options from field definitions.

        Args:
            basic_question_types: Set of basic question types
            compiled_options: List to append compiled configurations
            field_definitions: Dictionary of field definitions

        """
        for field in field_definitions.values():
            if field["typ"] == "name":
                continue

            toggle_key = f".lq_{field['uuid']}" if field["typ"] in basic_question_types else f"q_{field['uuid']}"

            compiled_options.append((toggle_key, field["name"]))

    def add_feature_extra(self, extra_fields: list, feature_field_definitions: list) -> None:
        """Add feature-specific extra fields to configuration.

        Args:
            extra_fields: List to append extra field configurations
            feature_field_definitions: List of feature field tuples (feature, field_id, label)

        """
        for feature_field_definition in feature_field_definitions:
            feature = feature_field_definition[0]
            field_id = feature_field_definition[1]
            field_label = feature_field_definition[2]

            if feature and feature not in self.params["features"]:
                continue
            extra_fields.append((field_id, field_label))
