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

import os
from typing import Any, Optional

from django.db import models
from django.db.models import Q
from django.db.models.constraints import UniqueConstraint
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from pilkit.processors import ResizeToFit
from tinymce.models import HTMLField

from larpmanager.cache.config import get_element_config
from larpmanager.models.base import BaseModel
from larpmanager.models.event import BaseConceptModel, Event, ProgressStep
from larpmanager.models.member import Member
from larpmanager.models.utils import UploadToPathAndRename, download, my_uuid, my_uuid_short, show_thumb


class Writing(BaseConceptModel):
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

    def show_red(self):
        # noinspection PyUnresolvedReferences
        js = {"id": self.id, "number": self.number}
        for s in ["name"]:
            self.upd_js_attr(js, s)
        return js

    def show(self, run: Optional[Any] = None) -> dict[str, Any]:
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

    def show_complete(self):
        js = self.show()
        self.upd_js_attr(js, "text")
        return js

    @classmethod
    def get_example_csv(cls, features: set[str]) -> list[list[str]]:
        """
        Generate example CSV structure for writing element imports.

        This method creates a template CSV with headers and example data for importing
        writing elements. The CSV structure includes mandatory fields and optional
        fields based on enabled features.

        Args:
            features: Set of enabled feature names to include in CSV template.
                     Common features include 'title', 'mirror', 'cover', 'hide'.

        Returns:
            List of CSV rows where first row contains headers and second row
            contains example/description data for each column.

        Example:
            >>> features = {'title', 'cover'}
            >>> csv_data = MyClass.get_example_csv(features)
            >>> csv_data[0]  # Headers
            ['number', 'name', 'presentation', 'text', 'title', 'cover']
        """
        # Initialize base CSV structure with mandatory columns
        rows = [
            ["number", "name", "presentation", "text"],
            [
                "put a number, from 1 onward",
                "the name",
                "a public presentation",
                "a private text (Please avoid quotes of any kind!)",
            ],
        ]

        # Define optional features with their descriptions
        # Each tuple contains (feature_name, description_text)
        optional_features = [
            # ('assigned', 'email of the staff members to which to assign this element'),
            ("title", "short text, the title of the element"),
            ("mirror", "number, the number of the element mirroring"),
            ("cover", "url of the element cover"),
            ("hide", "single character, t (true), f (false)"),
        ]

        # Add columns for enabled features only
        for feature_name, description in optional_features:
            if feature_name in features:
                # Append feature column to headers and descriptions
                rows[0].append(feature_name)
                rows[1].append(description)

        return rows


class CharacterStatus(models.TextChoices):
    CREATION = "c", _("Creation")
    PROPOSED = "s", _("Proposed")
    REVIEW = "r", _("Revision")
    APPROVED = "a", _("Approved")


class Character(Writing):
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
            "secret face of another character)"
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
        max_length=1, choices=CharacterStatus.choices, default=CharacterStatus.CREATION, verbose_name=_("Status")
    )

    access_token = models.CharField(
        max_length=12,
        unique=True,
        default=my_uuid_short,
        db_index=True,
        verbose_name=_("External access code"),
        help_text=_(
            "Allows external access to this character through a secret URL "
            "(change the code if it has been shared with the wrong people)"
        ),
    )

    def __str__(self):
        return f"#{self.number} {self.name}"

    def get_config(self, name, def_v=None, bypass_cache=False):
        return get_element_config(self, name, def_v, bypass_cache)

    def show(self, run=None):
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
        if "title" in js and js["title"]:
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
        if self.event.get_config("user_character_approval", False):
            if self.status not in [CharacterStatus.APPROVED]:
                js["hide"] = True

        return js

    def show_factions(self, event: Optional[Event], js: dict[str, Any]) -> None:
        """Display factions for the given event in the JSON response.

        Populates the 'factions' key in the js dictionary with faction numbers
        and sets a thumbnail if a primary faction with cover exists.

        Args:
            event: The event to get factions for. If None, uses self.event.
            js: Dictionary to populate with faction data.
        """
        js["factions"] = []

        # Determine which event to use for faction lookup
        if event:
            fac_event = event.get_class_parent("faction")
        else:
            fac_event = self.event.get_class_parent("faction")

        primary = False

        # Process all factions for the event
        # noinspection PyUnresolvedReferences
        for g in self.factions_list.filter(event=fac_event):
            # Check if this is a primary faction and set thumbnail
            if g.typ == FactionType.PRIM:
                primary = True
                if g.cover:
                    js["thumb"] = g.thumb.url

            # Add faction number to the list
            js["factions"].append(g.number)

        # Add default faction (0) if no primary faction exists
        if not primary:
            js["factions"].append(0)

    @staticmethod
    def get_character_filepath(run):
        fp = os.path.join(run.event.get_media_filepath(), "characters", f"{run.number}/")
        os.makedirs(fp, exist_ok=True)
        return fp

    def get_sheet_filepath(self, run):
        return os.path.join(self.get_character_filepath(run), f"#{self.number}.pdf")

    def get_sheet_friendly_filepath(self, run=None):
        return os.path.join(self.get_character_filepath(run), f"#{self.number}-light.pdf")

    def get_relationships_filepath(self, run=None):
        return os.path.join(self.get_character_filepath(run), f"#{self.number}-rels.pdf")

    def show_thumb(self):
        if self.thumb:
            # noinspection PyUnresolvedReferences
            return show_thumb(200, self.thumb.url)

    def relationships(self):
        return Relationship.objects.filter(source_id=self.pk)

    def get_plot_characters(self):
        return PlotCharacterRel.objects.filter(character_id=self.pk).select_related("plot").order_by("order")

    @classmethod
    def get_example_csv(cls, features):
        rows = Writing.get_example_csv(features)

        rows[0].extend(["player"])
        rows[1].extend(["optional - the email of the player to whom you want to assign this character"])

        return rows

    class Meta:
        constraints = [
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
        indexes = [
            models.Index(fields=["number", "event"]),
            models.Index(fields=["event", "status"]),
            models.Index(fields=["player", "event"]),
            models.Index(fields=["event", "hide"]),
            models.Index(fields=["mirror"]),
        ]


class CharacterConfig(BaseModel):
    name = models.CharField(max_length=150)

    value = models.CharField(max_length=5000)

    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="configs")

    def __str__(self):
        return f"{self.character} {self.name}"

    class Meta:
        indexes = [
            models.Index(fields=["character", "name"]),
        ]
        constraints = [
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
    characters = models.ManyToManyField(Character, related_name="plots", through="PlotCharacterRel", blank=True)

    order = models.IntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]
        constraints = [
            UniqueConstraint(fields=["event", "number", "deleted"], name="unique_plot_with_optional"),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_plot_without_optional",
            ),
        ]

    def __str__(self):
        return self.name

    def get_plot_characters(self):
        return (
            PlotCharacterRel.objects.filter(plot_id=self.pk).select_related("character").order_by("character__number")
        )


class PlotCharacterRel(BaseModel):
    plot = models.ForeignKey(Plot, on_delete=models.CASCADE)

    order = models.IntegerField(default=0)

    character = models.ForeignKey(Character, on_delete=models.CASCADE)

    text = models.TextField(max_length=5000, null=True)

    def __str__(self):
        return f"{self.plot} - {self.character}"

    class Meta:
        constraints = [
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
    PRIM = "s", _("Primary")
    TRASV = "t", _("Transversal")
    SECRET = "g", _("Secret")


class Faction(Writing):
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

    def show_red(self):
        js = super().show_red()
        for s in ["typ", "teaser"]:
            self.upd_js_attr(js, s)
        return js

    def __str__(self):
        return self.name

    class Meta:
        indexes = [models.Index(fields=["number", "event", "order"])]


class PrologueType(Writing):
    def __str__(self):
        return self.name

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]


class Prologue(Writing):
    typ = models.ForeignKey(PrologueType, on_delete=models.CASCADE, null=True, related_name="prologues")

    characters = models.ManyToManyField(Character, related_name="prologues_list", blank=True)

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]
        ordering = ("event", "number", "typ")
        constraints = [
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

    def __str__(self):
        return f"P{self.number} {self.name} ({self.typ})"


class HandoutTemplate(BaseModel):
    number = models.IntegerField()

    name = models.CharField(max_length=150)

    css = models.TextField(blank=True, null=True)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="handout_templates")

    class Meta:
        constraints = [
            UniqueConstraint(fields=["event", "number", "deleted"], name="unique_ht_with_optional"),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_ht_without_optional",
            ),
        ]

    def __str__(self):
        return f"HT{self.number} {self.name}"

    def download_template(self):
        # noinspection PyUnresolvedReferences
        return download(self.template.path)


class Handout(Writing):
    template = models.ForeignKey(HandoutTemplate, on_delete=models.CASCADE, related_name="handouts", null=True)

    cod = models.SlugField(max_length=32, unique=True, default=my_uuid, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]
        constraints = [
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

    def __str__(self):
        return f"H{self.number} {self.name}"

    def get_filepath(self, run):
        fp = os.path.join(run.event.get_media_filepath(), "handouts")
        os.makedirs(fp, exist_ok=True)
        return os.path.join(fp, f"H{self.number}.pdf")


class TextVersionChoices(models.TextChoices):
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


class TextVersion(BaseModel):
    tp = models.CharField(max_length=1, choices=TextVersionChoices.choices)

    eid = models.IntegerField()

    version = models.IntegerField()

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="text_versions", null=True)

    text = HTMLField(blank=True)

    dl = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.tp} {self.eid} {self.version}"


class SpeedLarp(Writing):
    typ = models.IntegerField()

    station = models.IntegerField()

    characters = models.ManyToManyField(Character, related_name="speedlarps_list", blank=True)

    def show_red(self):
        js = super().show_red()
        js["typ"] = self.typ
        js["station"] = self.station
        return js

    def __str__(self):
        return f"S{self.number} {self.name} ({self.typ} - {self.station})"

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]


def replace_char_names(v: str, chars: dict[str, dict]) -> str:
    """Replace character names in text with their corresponding values.

    Args:
        v: The input text to process. If falsy, returns empty string.
        chars: Dictionary mapping character names to their replacement values.

    Returns:
        Text with character names replaced by their values prefixed with '@'.
        Returns empty string if input text is falsy.
    """
    # Return early if input text is falsy (None, empty string, etc.)
    if not v:
        return ""

    # Iterate through each character name in the mapping
    for name, char_value in chars.items():
        name_number = 2

        # Skip names that are too short (less than 2 characters)
        if len(name) < name_number:
            continue

        # Replace character name with '@' prefixed value if found in text
        if name in v:
            c = f"@{char_value}"
            v = v.replace(name, c)

    return v


def replace_chars_el(el, chars):
    if hasattr(el, "text"):
        el.text = replace_char_names(el.text, chars)
    if hasattr(el, "teaser"):
        el.teaser = replace_char_names(el.teaser, chars)


def replace_character_names_in_writing(instance) -> None:
    """
    Replace character names in writing content with character numbers.

    This function processes a writing instance and replaces all character names
    with their corresponding numbers if the event has writing substitution enabled.
    It also handles related plot character relationships for Character and Plot instances.

    Args:
        instance: Writing model instance to process for character substitution.
                 Can be Character, Plot, or other writing-related model instances.

    Returns:
        None

    Note:
        Function returns early if:
        - Instance has no primary key (not saved)
        - Instance has no event attribute
        - Event has writing_substitute config disabled
    """
    # Early return if instance is not saved yet
    if not instance.pk:
        return

    # Early return if instance doesn't have an event
    if not hasattr(instance, "event"):
        return

    # Early return if writing substitution is disabled for this event
    if not instance.event.get_config("writing_substitute", False):
        return

    # Build character name to number mapping for replacement
    chars = {}
    for c in instance.event.get_elements(Character):
        chars[c.name] = c.number

    # Sort names by length (longest first) to avoid partial replacements
    names = list(chars.keys())
    names.sort(key=len, reverse=True)

    # Replace character names in the main instance
    replace_chars_el(instance, chars)

    # Handle Character instances: process related plot character relationships
    if isinstance(instance, Character):
        for el in PlotCharacterRel.objects.filter(character=instance):
            replace_chars_el(el, chars)
            el.save()

    # Handle Plot instances: process related plot character relationships
    if isinstance(instance, Plot):
        for el in PlotCharacterRel.objects.filter(plot=instance):
            replace_chars_el(el, chars)
            el.save()


class Relationship(BaseModel):
    source = models.ForeignKey(Character, related_name="source", on_delete=models.CASCADE)

    target = models.ForeignKey(Character, related_name="target", on_delete=models.CASCADE)

    text = HTMLField()

    def __str__(self):
        return f"{self.source} {self.target}"

    class Meta:
        constraints = [
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
        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["target"]),
            models.Index(fields=["source", "target"]),
        ]
