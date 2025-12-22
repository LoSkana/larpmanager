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

import re
from pathlib import Path
from typing import Any, ClassVar

from django.db import models
from django.db.models import Q
from django.db.models.constraints import UniqueConstraint
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from pilkit.processors import ResizeToFit
from tinymce.models import HTMLField

from larpmanager.cache.config import get_element_config, get_event_config
from larpmanager.models.base import BaseModel, UuidMixin
from larpmanager.models.event import BaseConceptModel, Event, ProgressStep, Run
from larpmanager.models.member import Member
from larpmanager.models.utils import UploadToPathAndRename, download, my_uuid, my_uuid_short, show_thumb


class Writing(UuidMixin, BaseConceptModel):
    """Represents Writing model."""

    progress = models.ForeignKey(
        ProgressStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Progress status"),
    )

    assigned = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Assigned staff member"),
    )

    teaser = HTMLField(
        max_length=100000,
        blank=True,
        verbose_name=_("Presentation"),
        help_text=_("Presentation visible to all participants, when 'show presentation' is checked"),
    )

    text = HTMLField(
        max_length=100000,
        blank=True,
        help_text=_("Text visible only by the assigned participant, when 'show text' is checked"),
    )

    temp = models.BooleanField(default=False)

    hide = models.BooleanField(default=False)

    class Meta:
        abstract = True

    def show_red(self) -> dict[str, Any]:
        """Return a dictionary representation for red display.

        Returns:
            Dictionary containing id, number, and name attributes.

        """
        js = {}
        for s in ["id", "number", "name", "uuid"]:
            self.upd_js_attr(js, s)
        return js

    def show(self, run: Run | None = None) -> dict[str, Any]:  # noqa: ARG002
        """Generate a display dictionary with basic writing information and teaser.

        Builds upon the reduced representation from show_red() by adding the teaser
        field to provide a more complete view of the writing object for display
        purposes.

        Args:
            run: Optional run instance for context-specific display modifications.
                 Defaults to None if no specific run context is needed.

        Returns:
            Dict containing writing object data with id, number, name, and teaser
            fields suitable for JSON serialization and frontend display.

        """
        # Get base dictionary with id, number, and name fields
        js = self.show_red()

        # Add teaser field to the display dictionary
        self.upd_js_attr(js, "teaser")

        return js

    def show_complete(self) -> dict:
        """Get complete JSON representation with updated text attribute."""
        js = self.show()
        self.upd_js_attr(js, "text")
        return js

    @classmethod
    def get_example_csv(cls, enabled_features: dict[str, int]) -> list[list[str]]:
        """Generate example CSV structure for writing element imports.

        Args:
            enabled_features: Dict of enabled feature names to include in the CSV template.

        Returns:
            List of CSV rows: first row contains headers, second row contains example data.

        """
        # Initialize base CSV structure with mandatory columns
        csv_rows = [
            ["number", "name", "presentation", "text"],
            [
                "put a number, from 1 onward",
                "the name",
                "a public presentation",
                "a private text (Please avoid quotes of any kind!)",
            ],
        ]

        # Define optional feature columns with their descriptions
        optional_feature_columns = [
            ("title", "short text, the title of the element"),
            ("mirror", "number, the number of the element mirroring"),
            ("cover", "url of the element cover"),
            ("hide", "single character, t (true), f (false)"),
        ]

        # Add enabled feature columns to the CSV structure
        for feature_column_name, feature_description in optional_feature_columns:
            if feature_column_name in enabled_features:
                # Append feature column to header row
                csv_rows[0].append(feature_column_name)
                # Append description to example data row
                csv_rows[1].append(feature_description)

        return csv_rows


class CharacterStatus(models.TextChoices):
    """Represents CharacterStatus model."""

    CREATION = "c", _("Creation")
    PROPOSED = "s", _("Proposed")
    REVIEW = "r", _("Revision")
    APPROVED = "a", _("Approved")


class Character(Writing):
    """Represents Character model."""

    title = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Indicates the title of the character - it will be shown along with the name"),
    )

    mirror = models.OneToOneField(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mirror_inv",
        help_text=_(
            "Indicate whether the character is a mirror (i.e., whether this pg shows the true "
            "secret face of another character)",
        ),
    )

    characters = models.ManyToManyField(
        "self",
        related_name="characters_inv",
        through="Relationship",
        symmetrical=False,
        blank=True,
    )

    hide = models.BooleanField(default=False)

    cover = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("character/cover/"),
        verbose_name=_("Character cover"),
        help_text=_("Cover photo fo the character"),
        null=True,
        blank=True,
    )

    thumb = ImageSpecField(
        source="cover",
        processors=[ResizeToFit(500, 500)],
        format="JPEG",
        options={"quality": 90},
    )

    player = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text=_("Player"),
        related_name="characters_player",
    )

    status = models.CharField(
        max_length=1,
        choices=CharacterStatus.choices,
        default=CharacterStatus.CREATION,
        verbose_name=_("Status"),
    )

    access_token = models.CharField(
        max_length=12,
        unique=True,
        default=my_uuid_short,
        db_index=True,
        verbose_name=_("External access code"),
        help_text=_(
            "Allows external access to this character through a secret URL "
            "(change the code if it has been shared with the wrong people)",
        ),
    )

    def __str__(self) -> str:
        """Return string representation."""
        return f"#{self.number} {self.name}"

    def get_config(self, name: str, *, default_value: Any = None, bypass_cache: bool = False) -> Any:
        """Get configuration value for this character."""
        return get_element_config(self, name, default_value, bypass_cache=bypass_cache)

    @property
    def is_active(self) -> bool:
        """Check if character is active (not marked as inactive in CharacterConfig).

        Returns:
            True if character is active (no inactive config), False otherwise.

        """
        is_inactive = self.get_config("inactive", default_value=False)
        return not (is_inactive == "True" or is_inactive is True)

    def show(self, run: Run | None = None) -> Any:
        """Generate display dictionary with character information and media URLs.

        Creates a comprehensive dictionary containing character details, player info,
        factions, cover images, mirror characters, and approval status.
        """
        js = super().show(run)

        for s in ["title"]:
            self.upd_js_attr(js, s)

        if self.player:
            # noinspection PyUnresolvedReferences
            js["owner_id"] = self.player_id
            # noinspection PyUnresolvedReferences
            js["owner"] = self.player.display_member()

        js["show"] = js["name"]
        if js.get("title"):
            js["show"] += " - " + js["title"]

        if run:
            self.show_factions(run.event, js)

        if self.cover:
            # noinspection PyUnresolvedReferences
            js["cover"] = self.cover.url
            # noinspection PyUnresolvedReferences
            js["thumb"] = self.thumb.url

        if self.mirror:
            # noinspection PyUnresolvedReferences
            js["mirror"] = self.mirror.show_red()

        js["hide"] = self.hide
        if get_event_config(self.event_id, "user_character_approval", default_value=False) and self.status not in [
            CharacterStatus.APPROVED
        ]:
            js["hide"] = True

        return js

    def show_factions(self, event: Event | None, js: dict) -> None:
        """Add faction information to the JavaScript data structure.

        Populates the 'factions' list in the js dictionary with faction numbers
        from the event. If no primary faction is found, adds 0 as default.
        Also sets thumbnail URL if primary faction has cover image.

        Args:
            event: Event object to get factions from. If None, uses self.event.
            js: Dictionary to populate with faction data.

        """
        js["factions"] = []

        # Determine which event to use for faction lookup
        faction_event = event.get_class_parent("faction") if event else self.event.get_class_parent("faction")

        # Track if we find a primary faction
        has_primary_faction = False

        # Process all factions for this event
        # noinspection PyUnresolvedReferences
        for faction in self.factions_list.filter(event=faction_event):
            # Check if this is a primary faction
            if faction.typ == FactionType.PRIM:
                has_primary_faction = True
                # Set thumbnail if cover image exists
                if faction.cover:
                    js["thumb"] = faction.thumb.url

            # Add faction number to the list
            js["factions"].append(faction.number)

        # Add default faction if no primary found
        if not has_primary_faction:
            js["factions"].append(0)

    @staticmethod
    def get_character_filepath(run: Run) -> str:
        """Get the directory path for storing character files for a given run.

        Args:
            run: The run instance for which to get the character filepath.

        Returns:
            The absolute path to the character files directory.

        """
        # Build the path to the characters directory for this run
        directory_path = str(Path(run.event.get_media_filepath()) / "characters" / f"{run.number}/")
        # Ensure the directory exists
        Path(directory_path).mkdir(parents=True, exist_ok=True)
        return directory_path

    def get_sheet_filepath(self, run: Run) -> str:
        """Get the path to this character's PDF sheet file.

        Args:
            run: The Run instance for which to get the sheet filepath.

        Returns:
            The full filesystem path to the character's PDF sheet file.

        """
        # Build the character's directory path
        character_directory = self.get_character_filepath(run)

        # Create sheet filename using character number
        sheet_filename = f"#{self.number}.pdf"

        return str(Path(character_directory) / sheet_filename)

    def get_sheet_friendly_filepath(self, character_run: Any = None) -> Any:
        """Return filepath for the light PDF version of the character sheet."""
        return str(Path(self.get_character_filepath(character_run)) / f"#{self.number}-light.pdf")

    def get_relationships_filepath(self, run: Any = None) -> Any:
        """Return filepath for the relationships PDF."""
        return str(Path(self.get_character_filepath(run)) / f"#{self.number}-rels.pdf")

    def show_thumb(self) -> Any:
        """Return HTML for displaying character thumbnail image if available."""
        if self.thumb:
            # noinspection PyUnresolvedReferences
            return show_thumb(200, self.thumb.url)
        return None

    def relationships(self) -> Any:
        """Return queryset of relationships where this character is the source."""
        return Relationship.objects.filter(source_id=self.pk)

    def get_plot_characters(self) -> Any:
        """Return queryset of plot-character relations for this character."""
        return PlotCharacterRel.objects.filter(character_id=self.pk).select_related("plot").order_by("order")

    @classmethod
    def get_example_csv(cls, enabled_features: dict[str, int]) -> list[list[str]]:
        """Extend Writing CSV example with player assignment column.

        Args:
            enabled_features: List of enabled features for the organization.

        Returns:
            List of CSV rows with headers and examples including player column.

        """
        # Get base CSV structure from parent Writing class
        csv_rows = Writing.get_example_csv(enabled_features)

        # Add player assignment column header and description
        csv_rows[0].extend(["player"])
        csv_rows[1].extend(["optional - the email of the player to whom you want to assign this character"])

        return csv_rows

    class Meta:
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_character_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_character_without_optional",
            ),
        ]
        indexes: ClassVar[list] = [
            models.Index(fields=["number", "event"]),
            models.Index(fields=["event", "status"], condition=Q(deleted__isnull=True), name="char_evt_stat_act"),
            models.Index(fields=["player", "event"], condition=Q(deleted__isnull=True), name="char_plyr_evt_act"),
            models.Index(fields=["event", "hide"], condition=Q(deleted__isnull=True), name="char_evt_hide_act"),
            models.Index(fields=["mirror"]),
            models.Index(fields=["event"], condition=Q(deleted__isnull=True), name="char_evt_act"),
        ]


class CharacterConfig(BaseModel):
    """Django app configuration for Character."""

    name = models.CharField(max_length=150)

    value = models.CharField(max_length=5000)

    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="configs")

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.character} {self.name}"

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["character", "name"]),
        ]
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["character", "name", "deleted"],
                name="unique_character_config_with_optional",
            ),
            UniqueConstraint(
                fields=["character", "name"],
                condition=Q(deleted=None),
                name="unique_character_config_without_optional",
            ),
        ]


class Plot(Writing):
    """Represents Plot model."""

    characters = models.ManyToManyField(Character, related_name="plots", through="PlotCharacterRel", blank=True)

    order = models.IntegerField(default=0)

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["number", "event"]),
            models.Index(fields=["event"], condition=Q(deleted__isnull=True), name="plot_evt_act"),
        ]
        constraints: ClassVar[list] = [
            UniqueConstraint(fields=["event", "number", "deleted"], name="unique_plot_with_optional"),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_plot_without_optional",
            ),
        ]

    def __str__(self) -> str:
        """Return string representation."""
        return self.name

    def get_plot_characters(self) -> Any:
        """Return queryset of plot-character relations for this plot."""
        return (
            PlotCharacterRel.objects.filter(plot_id=self.pk).select_related("character").order_by("character__number")
        )


class PlotCharacterRel(UuidMixin, BaseModel):
    """Represents PlotCharacterRel model."""

    plot = models.ForeignKey(Plot, on_delete=models.CASCADE)

    order = models.IntegerField(default=0)

    character = models.ForeignKey(Character, on_delete=models.CASCADE)

    text = models.TextField(max_length=5000, null=True)

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.plot} - {self.character}"

    class Meta:
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["plot", "character", "deleted"],
                name="unique_plot_character_rel_with_optional",
            ),
            UniqueConstraint(
                fields=["plot", "character"],
                condition=Q(deleted=None),
                name="unique_plot_character_rel_without_optional",
            ),
        ]


class FactionType(models.TextChoices):
    """Represents FactionType model."""

    PRIM = "s", _("Primary")
    TRASV = "t", _("Transversal")
    SECRET = "g", _("Secret")


class Faction(Writing):
    """Represents Faction model."""

    typ = models.CharField(max_length=1, choices=FactionType.choices, default=FactionType.PRIM, verbose_name=_("Type"))

    order = models.IntegerField(default=0)

    cover = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("faction/cover/"),
        verbose_name=_("Faction cover"),
        help_text=_("Faction logo"),
        null=True,
        blank=True,
    )

    thumb = ImageSpecField(
        source="cover",
        processors=[ResizeToFit(500, 500)],
        format="JPEG",
        options={"quality": 90},
    )

    characters = models.ManyToManyField(Character, related_name="factions_list", blank=True)

    selectable = models.BooleanField(
        default=False,
        help_text=_("Indicates whether it can be selected by participants"),
    )

    @staticmethod
    def get_faction_filepath(run: Run) -> str:
        """Get the directory path for storing faction PDF files for a specific run.

        Creates the faction directory structure within the event's media directory
        if it doesn't already exist. The directory structure follows the pattern:
        {event_media}/factions/{run_number}/

        This static method can be called without a faction instance, useful for
        batch operations or directory initialization.

        Args:
            run: The Run model instance for which to get the faction files directory

        Returns:
            Absolute filesystem path to the faction files directory for this run.
            The directory is guaranteed to exist after this call.

        Side Effects:
            Creates the faction directory structure if it doesn't exist

        """
        # Build directory path: event_media/factions/run_number/
        directory_path = str(Path(run.event.get_media_filepath()) / "factions" / f"{run.number}/")

        # Ensure directory exists, creating parent directories as needed
        Path(directory_path).mkdir(parents=True, exist_ok=True)

        return directory_path

    def get_sheet_filepath(self, run: Run) -> str:
        """Get the complete file path for this faction's PDF sheet.

        Constructs the full filesystem path where the faction sheet PDF should be
        stored or retrieved from. The filename includes the faction number for
        easy identification: #{faction_number}.pdf

        Args:
            run: The Run model instance for which to get the sheet file path

        Returns:
            Absolute filesystem path to the faction sheet PDF file, in the format:
            {event_media}/factions/{run_number}/#{faction_number}.pdf

        Example:
            For faction #5 in run #2:
            /path/to/media/event_123/factions/2/#5.pdf

        """
        # Get the faction directory for this run
        faction_directory = self.get_faction_filepath(run)

        # Construct filename with faction number
        sheet_filename = f"#{self.number}.pdf"

        # Return complete path to faction sheet PDF
        return str(Path(faction_directory) / sheet_filename)

    def show_red(self) -> dict:
        """Update JavaScript response with 'typ' and 'teaser' attributes."""
        js = super().show_red()

        # Update JS attributes for typ and teaser fields
        for s in ["typ", "teaser"]:
            self.upd_js_attr(js, s)

        return js

    def __str__(self) -> str:
        """Return string representation."""
        return self.name

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["number", "event", "order"]),
            models.Index(fields=["event"], condition=Q(deleted__isnull=True), name="fac_evt_act"),
        ]


class PrologueType(Writing):
    """Represents PrologueType model."""

    def __str__(self) -> str:
        """Return string representation."""
        return self.name

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["number", "event"]),
            models.Index(fields=["event"], condition=Q(deleted__isnull=True), name="ptype_evt_act"),
        ]


class Prologue(Writing):
    """Represents Prologue model."""

    typ = models.ForeignKey(PrologueType, on_delete=models.CASCADE, null=True, related_name="prologues")

    characters = models.ManyToManyField(Character, related_name="prologues_list", blank=True)

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["number", "event"]),
            models.Index(fields=["event"], condition=Q(deleted__isnull=True), name="prol_evt_act"),
        ]
        ordering = ("event", "number", "typ")
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["event", "number", "typ", "deleted"],
                name="unique_prologue_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number", "typ"],
                condition=Q(deleted=None),
                name="unique_prologue_without_optional",
            ),
        ]

    def __str__(self) -> str:
        """Return string representation."""
        return f"P{self.number} {self.name} ({self.typ})"


class HandoutTemplate(BaseModel):
    """Represents HandoutTemplate model."""

    number = models.IntegerField()

    name = models.CharField(max_length=150)

    css = models.TextField(blank=True, null=True)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="handout_templates")

    class Meta:
        constraints: ClassVar[list] = [
            UniqueConstraint(fields=["event", "number", "deleted"], name="unique_ht_with_optional"),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_ht_without_optional",
            ),
        ]

    def __str__(self) -> str:
        """Return string representation."""
        return f"HT{self.number} {self.name}"

    def download_template(self) -> str:
        """Download the template file."""
        # noinspection PyUnresolvedReferences
        return download(self.template.path)


class Handout(Writing):
    """Represents Handout model."""

    template = models.ForeignKey(HandoutTemplate, on_delete=models.CASCADE, related_name="handouts", null=True)

    cod = models.SlugField(max_length=32, unique=True, default=my_uuid, db_index=True)

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["number", "event"]),
            models.Index(fields=["event"], condition=Q(deleted__isnull=True), name="hand_evt_act"),
        ]
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_handout_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_handout_without_optional",
            ),
        ]

    def __str__(self) -> str:
        """Return string representation."""
        return f"H{self.number} {self.name}"

    def get_filepath(self, run: Run) -> str:
        """Build the file path for this handout's PDF within the event's media directory.

        Args:
            run: The Run instance to determine the event directory.

        Returns:
            Absolute path to the handout PDF file.

        """
        # Build handouts directory path within event media
        handouts_directory = str(Path(run.event.get_media_filepath()) / "handouts")
        Path(handouts_directory).mkdir(parents=True, exist_ok=True)

        # Generate PDF filename using handout number
        return str(Path(handouts_directory) / f"H{self.number}.pdf")


class TextVersionChoices(models.TextChoices):
    """Choices for TextVersionChoices."""

    PLOT = "p", "Plot"
    CHARACTER = "c", "Character"
    FACTION = "h", "Faction"
    QUEST = "q", "Quest"
    TRAIT = "t", "Trait"
    ARTICLE = "a", "Article"
    HANDOUT = "o", "Handout"
    PROLOGUE = "g", "Prologue"
    QUEST_TYPE = "e", "QuestType"
    SPEEDLARP = "s", "SpeedLarp"
    PLOT_CHARACTER = "r", "PlotCharacter"
    RELATIONSHIP = "l", "Relationship"


class TextVersion(UuidMixin, BaseModel):
    """Represents TextVersion model."""

    tp = models.CharField(max_length=1, choices=TextVersionChoices.choices)

    eid = models.IntegerField()

    version = models.IntegerField()

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="text_versions", null=True)

    text = HTMLField(blank=True)

    dl = models.BooleanField(default=False)

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.tp} {self.eid} {self.version}"


class SpeedLarp(Writing):
    """Represents SpeedLarp model."""

    typ = models.IntegerField()

    station = models.IntegerField()

    characters = models.ManyToManyField(Character, related_name="speedlarps_list", blank=True)

    def show_red(self) -> dict:
        """Override parent method to include additional type and station data."""
        # Call parent method to get base JSON data
        js = super().show_red()

        # Add type-specific fields
        js["typ"] = self.typ
        js["station"] = self.station

        return js

    def __str__(self) -> str:
        """Return string representation."""
        return f"S{self.number} {self.name} ({self.typ} - {self.station})"

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["number", "event"]),
            models.Index(fields=["event"], condition=Q(deleted__isnull=True), name="speed_evt_act"),
        ]


def replace_char_names(text: str, chars: dict[str, str]) -> str:
    """Replace character names in text with formatted references.

    Args:
        text: The input text to process
        chars: Dictionary mapping character names to their replacements

    Returns:
        The processed text with character names replaced, or empty string if input is falsy

    """
    # Return empty string if input is falsy
    if not text:
        return ""

    # First pass: temporarily replace all existing @<number> references with placeholders
    # to protect them from being modified
    placeholder_map = {}
    placeholder_counter = 0

    def create_placeholder(match: re.Match[str]) -> str:
        """Create unique placeholder for character reference and store original match."""
        nonlocal placeholder_counter
        placeholder = f"___CHAR_REF_{placeholder_counter}___"
        placeholder_map[placeholder] = match.group(0)
        placeholder_counter += 1
        return placeholder

    # Protect existing character references (@ followed by digits)
    text = re.sub(r"@\d+", create_placeholder, text)

    # Iterate through each character name in the dictionary
    for character_name, character_id in chars.items():
        minimum_name_length = 2

        # Skip names that are too short (less than 2 characters)
        if len(character_name) < minimum_name_length:
            continue

        # Replace character name with formatted reference if found in text
        if character_name in text:
            character_reference = f"@{character_id}"
            # Escape special regex characters in character_name
            escaped_name = re.escape(character_name)
            # Use word boundaries to match only complete words
            pattern = rf"\b{escaped_name}\b"
            text = re.sub(pattern, character_reference, text)

    # Restore all protected character references
    for placeholder, original in placeholder_map.items():
        text = text.replace(placeholder, original)

    return text


def replace_chars_element(element: Any, character_names: dict[str, str]) -> None:
    """Replace character names in element text and teaser attributes."""
    if hasattr(element, "text"):
        element.text = replace_char_names(element.text, character_names)
    if hasattr(element, "teaser"):
        element.teaser = replace_char_names(element.teaser, character_names)


def replace_character_names(instance: Any) -> None:
    """Replace character names in writing content with character numbers.

    This function substitutes character names with their corresponding numbers
    in writing content when the event has character substitution enabled.
    It processes the main instance and related plot character relationships.

    Args:
        instance: Writing model instance to process for character substitution.
                 Can be Character, Plot, or other writing-related model instances.

    Returns:
        None: Function performs in-place modifications and saves related objects.

    Note:
        Only processes instances that have a primary key, belong to an event,
        and where the event has writing_substitute configuration enabled.

    """
    # Early return if instance hasn't been saved to database yet
    if not instance.pk:
        return

    # Early return if instance doesn't have an associated event
    if not hasattr(instance, "event"):
        return

    # Early return if event doesn't have character substitution enabled
    if not get_event_config(instance.event_id, "writing_substitute", default_value=False):
        return

    # Build character name to number mapping for replacement
    character_name_to_number_mapping = {}
    for character in instance.event.get_elements(Character):
        character_name_to_number_mapping[character.name] = character.number

    # Sort names by length (longest first) to avoid partial replacements
    character_names = list(character_name_to_number_mapping.keys())
    character_names.sort(key=len, reverse=True)

    # Perform character name replacement on the main instance
    replace_chars_element(instance, character_name_to_number_mapping)

    # Handle Character instance: process related plot character relationships
    if isinstance(instance, Character):
        for plot_character_relationship in PlotCharacterRel.objects.filter(character=instance):
            replace_chars_element(plot_character_relationship, character_name_to_number_mapping)
            plot_character_relationship.save()

    # Handle Plot instance: process related plot character relationships
    if isinstance(instance, Plot):
        for plot_character_relationship in PlotCharacterRel.objects.filter(plot=instance):
            replace_chars_element(plot_character_relationship, character_name_to_number_mapping)
            plot_character_relationship.save()


class Relationship(BaseModel):
    """Represents Relationship model."""

    source = models.ForeignKey(Character, related_name="source", on_delete=models.CASCADE)

    target = models.ForeignKey(Character, related_name="target", on_delete=models.CASCADE)

    text = HTMLField()

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.source} {self.target}"

    class Meta:
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["source", "target", "deleted"],
                name="unique_relationship_with_optional",
            ),
            UniqueConstraint(
                fields=["source", "target"],
                condition=Q(deleted=None),
                name="unique_relationship_without_optional",
            ),
        ]
        indexes: ClassVar[list] = [
            models.Index(fields=["source"], condition=Q(deleted__isnull=True), name="rel_src_act"),
            models.Index(fields=["target"], condition=Q(deleted__isnull=True), name="rel_tgt_act"),
            models.Index(fields=["source", "target"], condition=Q(deleted__isnull=True), name="rel_src_tgt_act"),
        ]
