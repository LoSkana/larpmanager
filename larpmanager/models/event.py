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

import inspect
import logging
from pathlib import Path
from typing import Any, ClassVar

from colorfield.fields import ColorField
from django.conf import settings as conf_settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, QuerySet
from django.db.models.constraints import UniqueConstraint
from django.utils import formats
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFit
from tinymce.models import HTMLField

from larpmanager.cache.config import get_element_config
from larpmanager.models.association import Association, AssociationPlan
from larpmanager.models.base import AlphanumericValidator, BaseModel, Feature, UuidMixin
from larpmanager.models.member import Member
from larpmanager.models.utils import (
    UploadToPathAndRename,
    download,
    get_attr,
    my_uuid_short,
    show_thumb,
)

logger = logging.getLogger(__name__)


class Event(UuidMixin, BaseModel):
    """Represents Event model."""

    slug = models.CharField(
        max_length=30,
        validators=[AlphanumericValidator],
        db_index=True,
        blank=True,
        null=True,
        verbose_name=_("URL identifier"),
        help_text=_("Unique identifier for the event URL")
        + " ("
        + _("only lowercase letters and numbers allowed, no spaces or special characters")
        + ")",
    )

    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="events")

    name = models.CharField(
        max_length=100,
        verbose_name=_("Event name"),
        help_text=_("The full name of your event as it will be displayed to participants"),
    )

    tagline = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("Tagline"),
        help_text=_("A catchy short phrase or slogan to describe your event"),
    )

    where = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("Location"),
        help_text=_("Where the event will take place"),
    )

    authors = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("Organizers"),
        help_text=_("Names of the people or teams organizing and running this event"),
    )

    description = HTMLField(
        max_length=10000,
        blank=True,
        default="",
        verbose_name=_("Description"),
        help_text=_("Full event description with all important details")
        + " ("
        + _("will be displayed on the main event page")
        + ")",
    )

    genre = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=pgettext_lazy("event", "Genre"),
        help_text=_("The genre or setting of your event"),
    )

    visible = models.BooleanField(default=True)

    cover = models.ImageField(
        max_length=500,
        upload_to="cover/",
        blank=True,
        verbose_name=_("Cover image"),
        help_text=_("Main event image displayed on your organization's homepage")
        + " ("
        + _("use a rectangular image, ideally 4:3 ratio for best results")
        + ")",
    )

    cover_thumb = ImageSpecField(
        source="cover",
        processors=[ResizeToFit(width=600)],
        format="JPEG",
        options={"quality": 70},
    )

    carousel_img = models.ImageField(
        max_length=500,
        upload_to="carousel/",
        blank=True,
        verbose_name=_("Carousel image"),
        help_text=_("Optional image for homepage carousel/slideshow")
        + " ("
        + _("use high-quality wide images for best visual impact")
        + ")",
    )

    carousel_thumb = ImageSpecField(source="carousel_img", format="JPEG", options={"quality": 70})

    carousel_text = HTMLField(
        max_length=2000,
        blank=True,
        verbose_name=_("Carousel description"),
        help_text=_("Text displayed alongside the carousel image") + " (" + _("keep it short and engaging") + ")",
    )

    website = models.URLField(
        max_length=100,
        blank=True,
        verbose_name=_("External website"),
        help_text=_("Link to an external website with additional event information"),
    )

    max_pg = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Maximum participants"),
        help_text=_("Maximum number of participant slots available (set to 0 for unlimited)"),
    )

    max_filler = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Maximum fillers"),
        help_text=_("Maximum number of filler character slots available (set to 0 for unlimited)"),
    )

    max_waiting = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Maximum waiting list"),
        help_text=_("Maximum number of people allowed on the waiting list (set to 0 for unlimited)"),
    )

    features = models.ManyToManyField(Feature, related_name="events", blank=True)

    parent = models.ForeignKey(
        "event",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Parent campaign"),
        help_text=_("Link this event to another event to create a campaign series where characters are shared")
        + " ("
        + _("leave empty to start a new campaign")
        + ")",
    )

    background = models.ImageField(
        max_length=500,
        upload_to="event_background/",
        verbose_name=_("Background image"),
        blank=True,
        help_text=_("Background image displayed across all event pages")
        + " ("
        + _("use a subtle pattern or texture for best results")
        + ")",
    )

    background_red = ImageSpecField(
        source="background",
        processors=[ResizeToFit(width=1000)],
        format="JPEG",
        options={"quality": 80},
    )

    font = models.FileField(
        upload_to=UploadToPathAndRename("event_font/"),
        verbose_name=_("Custom title font"),
        help_text=_(
            "Upload a custom font file for page titles to match your event's theme (TTF, OTF, or WOFF formats)"
        ),
        blank=True,
        null=True,
    )

    css_code = models.CharField(max_length=32, editable=False, default="")

    pri_rgb = ColorField(
        verbose_name=_("Text color"),
        help_text=_("Main color for text content throughout your event's pages"),
        blank=True,
        null=True,
    )

    sec_rgb = ColorField(
        verbose_name=_("Background color"),
        help_text=_("Color used for text backgrounds and content boxes"),
        blank=True,
        null=True,
    )

    ter_rgb = ColorField(
        verbose_name=_("Link color"),
        help_text=_("Color for clickable links and interactive elements"),
        blank=True,
        null=True,
    )

    template = models.BooleanField(default=False)

    class Meta:
        constraints: ClassVar[list] = [
            UniqueConstraint(fields=["association", "slug", "deleted"], name="unique_event_with_optional"),
            UniqueConstraint(
                fields=["association", "slug"],
                condition=Q(deleted=None),
                name="unique_event_without_optional",
            ),
        ]

    def __str__(self) -> str:
        """Return the name of the object as a string."""
        return self.name

    def get_elements(self, element_model_class: type[BaseModel]) -> QuerySet:
        """Get ordered elements of specified type for the parent event."""
        # Get all elements for the parent event
        queryset = element_model_class.objects.filter(event=self.get_class_parent(element_model_class))

        # Order by number if the model has that field
        if hasattr(element_model_class, "number"):
            queryset = queryset.order_by("number")
        return queryset

    def get_class_parent(self, model_class: type[BaseModel] | str) -> Any:
        """Get the parent event for inheriting elements of a specific model class.

        This method determines whether to use the parent event's elements or the current
        event's elements based on inheritance settings and model class type.

        Args:
            model_class: Model class (subclass of BaseModel) or class name string to check
                inheritance for. If a class is provided, it will be converted to
                lowercase string format.

        Returns:
            Event: Parent event if inheritance is enabled for the given model class
                   and a parent exists, otherwise returns self.

        Note:
            Only specific model classes support inheritance. The method checks against
            a predefined list of inheritable elements and respects campaign independence
            configuration settings.

        """
        # Convert class objects to lowercase string representation
        if inspect.isclass(model_class) and issubclass(model_class, BaseModel):
            model_class = model_class.__name__.lower()

        # Define which model elements can be inherited from parent events
        inheritable_elements = [
            "character",
            "faction",
            "abilitypx",
            "deliverypx",
            "abilitytypepx",
            "pooltypeci",
            "writingquestion",
            "writingoption",
        ]

        # Check if inheritance conditions are met
        # Verify that campaign independence is not enabled for this element type
        # If independence is disabled (False), use parent's elements
        if (
            self.parent
            and model_class in inheritable_elements
            and not self.get_config(f"campaign_{model_class}_indep", default_value=False)
        ):
            return self.parent

        # Return self if no parent exists, element not inheritable, or independence enabled
        return self

    def get_cover_thumb_url(self) -> str | None:
        """Get the URL of the cover thumbnail image, or None if unavailable."""
        try:
            # noinspection PyUnresolvedReferences
            return self.cover_thumb.url
        except (ValueError, AttributeError) as e:
            # Log error and return None if cover_thumb is not available
            logger.debug("Cover thumbnail not available for event %s: %s", self.id, e)
            return None

    def get_name(self) -> str:
        """Return the name attribute."""
        return self.name

    def show(self) -> dict[str, str]:
        """Generate display dictionary with event information and media URLs.

        Creates a comprehensive dictionary containing event details, cover images,
        carousel images, fonts, and backgrounds with their respective URLs.

        Returns:
            dict[str, str]: Dictionary containing event attributes and media URLs.
                Keys include: slug, name, tagline, description, website, genre,
                where, authors, cover, cover_thumb, carousel_img, carousel_thumb,
                font, background, background_red (when available).

        """
        dc = {}

        # Extract basic event attributes
        for s in [
            "slug",
            "name",
            "tagline",
            "description",
            "website",
            "genre",
            "where",
            "authors",
        ]:
            dc[s] = get_attr(self, s)

        # Add cover image URLs if available
        if self.cover:
            # noinspection PyUnresolvedReferences
            dc["cover"] = self.cover.url
            # noinspection PyUnresolvedReferences
            dc["cover_thumb"] = self.cover_thumb.url

        # Add carousel image URLs if available
        if self.carousel_img:
            # noinspection PyUnresolvedReferences
            dc["carousel_img"] = self.carousel_img.url
            # noinspection PyUnresolvedReferences
            dc["carousel_thumb"] = self.carousel_thumb.url

        # Add font URL if available
        if self.font:
            # noinspection PyUnresolvedReferences
            dc["font"] = self.font.url

        # Add background image URLs if available
        if self.background:
            # noinspection PyUnresolvedReferences
            dc["background"] = self.background.url
            # noinspection PyUnresolvedReferences
            dc["background_red"] = self.background_red.url

        return dc

    def thumb(self) -> str:
        """Return HTML markup for thumbnail image at 100px width."""
        # noinspection PyUnresolvedReferences
        return show_thumb(100, self.cover_thumb.url)

    def download_sheet_template(self) -> str:
        """Download the sheet template file."""
        # noinspection PyUnresolvedReferences
        return download(self.sheet_template.path)

    def get_media_filepath(self) -> str:
        """Get the media directory path for this object's PDFs, creating it if needed."""
        # Build path to PDF directory using object slug
        pdf_directory_path = str(Path(conf_settings.MEDIA_ROOT) / f"pdf/{self.slug}/")
        # Ensure directory exists
        Path(pdf_directory_path).mkdir(parents=True, exist_ok=True)
        return pdf_directory_path

    def get_config(self, name: str, *, default_value: Any = None, bypass_cache: bool = False) -> Any:
        """Get configuration value for this event."""
        return get_element_config(self, name, default_value, bypass_cache=bypass_cache)


class EventConfig(BaseModel):
    """Django app configuration for Event."""

    name = models.CharField(max_length=150)

    value = models.CharField(max_length=1000)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="configs")

    def __str__(self) -> str:
        """Return string representation combining event and name."""
        return f"{self.event} {self.name}"

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["event", "name"]),
        ]
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["event", "name", "deleted"],
                name="unique_event_config_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "name"],
                condition=Q(deleted=None),
                name="unique_event_config_without_optional",
            ),
        ]


class BaseConceptModel(BaseModel):
    """Represents BaseConceptModel model."""

    number = models.IntegerField()

    name = models.CharField(max_length=150, blank=False)

    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    class Meta:
        abstract = True
        ordering: ClassVar[list] = ["event", "number"]

    def get_name(self) -> str:
        """Get the name attribute."""
        return get_attr(self, "name")

    def __str__(self) -> str:
        """Return the string representation of this instance."""
        return self.name


class EventButton(UuidMixin, BaseConceptModel):
    """Represents EventButton model."""

    tooltip = models.CharField(max_length=200)

    link = models.URLField(max_length=150)

    class Meta:
        indexes: ClassVar[list] = [models.Index(fields=["number", "event"])]
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_event_button_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_event_button_without_optional",
            ),
        ]


class EventTextType(models.TextChoices):
    """Represents EventTextType model."""

    INTRO = "i", _("Character sheet intro")
    TOC = "t", _("Terms and conditions")
    REGISTER = "r", _("Registration form")
    SEARCH = "s", _("Search")
    SIGNUP = "g", _("Registration mail")
    ASSIGNMENT = "a", _("Mail assignment")
    USER_CHARACTER = "c", _("Player's character form")

    CHARACTER_PROPOSED = "cs", _("Proposed character")
    CHARACTER_APPROVED = "ca", _("Approved character")
    CHARACTER_REVIEW = "cr", _("Character review")


class EventText(UuidMixin, BaseModel):
    """Represents EventText model."""

    number = models.IntegerField(null=True, blank=True)

    text = HTMLField(blank=True, null=True)

    typ = models.CharField(max_length=2, choices=EventTextType.choices, verbose_name=_("Type"))

    language = models.CharField(
        max_length=3,
        choices=conf_settings.LANGUAGES,
        default="en",
        null=True,
        verbose_name=_("Language"),
        help_text=_("Text language"),
    )

    default = models.BooleanField(default=True)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="texts")

    def __str__(self) -> str:
        """Return string representation of the event text."""
        return f"{self.get_typ_display()} - {self.get_language_display()}"

    class Meta:
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["event", "typ", "language", "deleted"],
                name="unique_event_text_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "typ", "language"],
                condition=Q(deleted=None),
                name="nique_event_text_without_optional",
            ),
        ]


class ProgressStep(UuidMixin, BaseConceptModel):
    """Represents ProgressStep model."""

    order = models.IntegerField(default=0)

    class Meta:
        indexes: ClassVar[list] = [models.Index(fields=["number", "event"])]
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_ProgressStep_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_ProgressStep_without_optional",
            ),
        ]

    def __str__(self) -> str:
        """Return formatted string with order number and name."""
        return f"{self.order} - {self.name}"


class DevelopStatus(models.TextChoices):
    """Represents DevelopStatus model."""

    START = "0", _("Hidden")
    SHOW = "1", _("Visible")
    CANC = "8", _("Cancelled")
    DONE = "9", _("Concluded")


class RegistrationStatus(models.TextChoices):
    """Registration status for event runs."""

    PRE = "p", _("Pre-registration")
    CLOSED = "c", _("Closed")
    OPEN = "o", _("Open")
    EXTERNAL = "e", _("External site")
    FUTURE = "f", _("Open on date")


class Run(UuidMixin, BaseModel):
    """Represents Run model."""

    search = models.CharField(max_length=150, editable=False)

    start = models.DateField(
        blank=True,
        null=True,
        verbose_name=_("Start date"),
        help_text=_("The date when this event begins"),
    )

    end = models.DateField(
        blank=True,
        null=True,
        verbose_name=_("End date"),
        help_text=_("The date when this event ends"),
        db_index=True,
    )

    development = models.CharField(
        max_length=1,
        choices=DevelopStatus.choices,
        default=DevelopStatus.START,
        verbose_name=_("Status"),
        help_text=_("Current status of this event"),
    )

    registration_status = models.CharField(
        max_length=1,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.CLOSED,
        verbose_name=_("Registrations status"),
        help_text=_("Registrations status for this event"),
    )

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="runs")

    number = models.IntegerField(
        verbose_name=_("Run number"),
        help_text=_("Sequential number for this event"),
    )

    registration_open = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("Registration opening"),
        help_text=_("Date and time when registrations open for participants"),
    )

    register_link = models.URLField(
        max_length=150,
        blank=True,
        verbose_name=_("External registration link"),
        help_text=_("Link to an external registration system")
        + " ("
        + _("non-registered users will be redirected here, while registered users get normal access")
        + ")",
    )

    registration_secret = models.CharField(
        default=my_uuid_short,
        max_length=50,
        unique=True,
        verbose_name=_("Secret registration code"),
        help_text=_("Unique code used to generate the secret registration link")
        + " ("
        + _("keep the auto-generated value or customize it")
        + ")",
        db_index=True,
    )

    balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name=_("Balance"),
        help_text=_("Current financial balance for this event"),
    )

    paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("Amount paid"),
        help_text=_("Total amount paid for platform management"),
    )

    plan = models.CharField(
        max_length=1,
        choices=AssociationPlan.choices,
        blank=True,
        null=True,
        verbose_name=_("Subscription plan"),
        help_text=_("The subscription plan associated with this event"),
    )

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["id", "deleted"]),
            models.Index(fields=["event", "deleted"]),
        ]
        constraints: ClassVar[list] = [
            UniqueConstraint(fields=["event", "number", "deleted"], name="unique_run_with_optional"),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_run_without_optional",
            ),
        ]

    def __str__(self) -> str:
        """Return string representation of the run with event name and optional number."""
        s = self.event.name
        max_length = 50
        if len(s) > max_length:
            s = f"{s[:max_length]}[...]"
        if self.number and self.number != 1:
            s = f"{s} #{self.number}"
        return s

    def get_slug(self) -> str:
        """Return the slug for this run, appending the run number if greater than 1."""
        run_slug = self.event.slug
        if self.number > 1:
            run_slug += f"-{self.number}"
        return run_slug

    def get_where(self) -> str:
        """Return the location of the associated event."""
        # noinspection PyUnresolvedReferences
        return self.event.where

    def get_cover_url(self) -> str:
        """Return the thumbnail URL of the associated event's cover image."""
        # noinspection PyUnresolvedReferences
        return self.event.cover_thumb.url

    def pretty_dates(self) -> str:
        """Format start and end dates into a human-readable string.

        Returns a formatted date string that intelligently handles different
        scenarios: missing dates, same dates, different years/months, etc.

        Returns:
            str: Formatted date string or "TBA" if dates are missing.
                Examples: "15 January 2024", "15 - 20 January 2024",
                "15 January - 20 February 2024", "15 January 2024 - 20 January 2025"

        """
        # Handle missing dates - return "TBA" if either date is None
        if not self.start or not self.end:
            return "TBA"

        # Same date - show single date format
        if self.start == self.end:
            return formats.date_format(self.start, "j E Y")

        # Different years - show full date format for both dates
        # noinspection PyUnresolvedReferences
        if self.start.year != self.end.year:
            return f"{formats.date_format(self.start, 'j E Y')} - {formats.date_format(self.end, 'j E Y')}"

        # Different months (same year) - show month for start, full date for end
        # noinspection PyUnresolvedReferences
        if self.start.month != self.end.month:
            return f"{formats.date_format(self.start, 'j E')} - {formats.date_format(self.end, 'j E Y')}"

        # Same month and year - show day range with single month/year
        # noinspection PyUnresolvedReferences
        return f"{self.start.day} - {formats.date_format(self.end, 'j E Y')}"

    def get_media_filepath(self) -> str:
        """Return the media file path for this run, creating the directory if needed."""
        # Build path by combining event media path with run number
        # noinspection PyUnresolvedReferences
        run_media_path = str(Path(self.event.get_media_filepath()) / f"{self.number}/")

        # Ensure directory exists
        Path(run_media_path).mkdir(parents=True, exist_ok=True)

        return run_media_path

    def get_gallery_filepath(self) -> str:
        """Return the file path for the gallery PDF."""
        return self.get_media_filepath() + "gallery.pdf"

    def get_profiles_filepath(self) -> str:
        """Return the file path for the profiles PDF."""
        return self.get_media_filepath() + "profiles.pdf"

    def get_config(self, name: str, *, default_value: Any = None, bypass_cache: bool = False) -> Any:
        """Get configuration value for this run."""
        return get_element_config(self, name, default_value, bypass_cache=bypass_cache)


class RunConfig(BaseModel):
    """Django app configuration for Run."""

    name = models.CharField(max_length=150)

    value = models.CharField(max_length=1000)

    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="configs")

    def __str__(self) -> str:
        """Return string representation combining run and name."""
        return f"{self.run} {self.name}"

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["run", "name"]),
        ]
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["run", "name", "deleted"],
                name="unique_run_config_with_optional",
            ),
            UniqueConstraint(
                fields=["run", "name"],
                condition=Q(deleted=None),
                name="unique_run_config_without_optional",
            ),
        ]


class PreRegistration(BaseModel):
    """Represents PreRegistration model."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="pre_registrations")

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="pre_registrations")

    pref = models.IntegerField()

    info = models.CharField(max_length=255)

    def __str__(self) -> str:
        """Return string representation combining event and member."""
        return f"{self.event} {self.member}"

    class Meta:
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["event", "member", "deleted"],
                name="unique_prereg_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "member"],
                condition=Q(deleted=None),
                name="unique_prereg_without_optional",
            ),
        ]
