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

import inspect
import os

from colorfield.fields import ColorField
from django.conf import settings as conf_settings
from django.db import models
from django.db.models import Q
from django.db.models.constraints import UniqueConstraint
from django.utils import formats
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFit
from tinymce.models import HTMLField

from larpmanager.cache.config import get_element_config
from larpmanager.models.association import Association, AssociationPlan
from larpmanager.models.base import AlphanumericValidator, BaseModel, Feature
from larpmanager.models.member import Member
from larpmanager.models.utils import (
    UploadToPathAndRename,
    download,
    get_attr,
    my_uuid_short,
    show_thumb,
)


class Event(BaseModel):
    slug = models.CharField(
        max_length=30,
        validators=[AlphanumericValidator],
        db_index=True,
        blank=True,
        null=True,
        verbose_name=_("URL identifier"),
        help_text=_("Only lowercase characters and numbers are allowed, no spaces or symbols"),
    )

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="events")

    name = models.CharField(max_length=100)

    tagline = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("Tagline"),
        help_text=_("A short tagline, slogan"),
    )

    where = models.CharField(max_length=500, blank=True, null=True, help_text=_("Where it is held"))

    authors = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("Authors"),
        help_text=_("Names of the collaborators who are organizing it"),
    )

    description = HTMLField(
        max_length=10000,
        blank=True,
        default="",
        verbose_name=_("Description"),
        help_text=_("Event description displayed on the event page"),
    )

    genre = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=pgettext_lazy("event", "Genre"),
        help_text=_("The setting / genre of the event"),
    )

    visible = models.BooleanField(default=True)

    cover = models.ImageField(
        max_length=500,
        upload_to="cover/",
        blank=True,
        help_text=_("Cover image shown on the organization's homepage — rectangular, ideally 4:3 ratio"),
    )

    cover_thumb = ImageSpecField(
        source="cover",
        processors=[ResizeToFit(width=600)],
        format="JPEG",
        options={"quality": 70},
    )

    carousel_img = models.ImageField(max_length=500, upload_to="carousel/", blank=True, help_text=_("Carousel image"))

    carousel_thumb = ImageSpecField(source="carousel_img", format="JPEG", options={"quality": 70})

    carousel_text = HTMLField(
        max_length=2000,
        blank=True,
        verbose_name=_("Carousel description"),
    )

    website = models.URLField(
        max_length=100,
        blank=True,
        verbose_name=_("Website"),
    )

    register_link = models.URLField(
        max_length=150,
        blank=True,
        verbose_name=_("External register link"),
        help_text=_("Insert the link to an external tool where users will be redirected if they are not yet registered")
        + ". "
        + _("Registered users will be granted normal access"),
    )

    max_pg = models.IntegerField(
        default=0,
        verbose_name=_("Max participants"),
        help_text=_("Maximum number of participants spots (0 = unlimited)"),
    )

    max_filler = models.IntegerField(
        default=0,
        verbose_name=_("Max fillers"),
        help_text=_("Maximum number of filler spots (0 = unlimited)"),
    )

    max_waiting = models.IntegerField(
        default=0,
        verbose_name=_("Max waitings"),
        help_text=_("Maximum number of waiting spots (0 = unlimited)"),
    )

    features = models.ManyToManyField(Feature, related_name="events", blank=True)

    parent = models.ForeignKey(
        "event",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Campaign"),
        help_text=_(
            "If you select another event, it will be considered in the same campaign, and they will share the characters"
        )
        + " - "
        + _("if you leave this empty, this can be the starting event of a new campaign"),
    )

    background = models.ImageField(
        max_length=500,
        upload_to="event_background/",
        verbose_name=_("Background image"),
        blank=True,
        help_text=_("Background image used across all event pages"),
    )

    background_red = ImageSpecField(
        source="background",
        processors=[ResizeToFit(width=1000)],
        format="JPEG",
        options={"quality": 80},
    )

    font = models.FileField(
        upload_to=UploadToPathAndRename("event_font/"),
        verbose_name=_("Title font"),
        help_text=_("Font used for title texts across all event pages"),
        blank=True,
        null=True,
    )

    css_code = models.CharField(max_length=32, editable=False, default="")

    pri_rgb = ColorField(
        verbose_name=_("Color texts"),
        help_text=_("Indicate the color that will be used for the texts"),
        blank=True,
        null=True,
    )

    sec_rgb = ColorField(
        verbose_name=_("Color background"),
        help_text=_("Indicate the color that will be used for the background of texts"),
        blank=True,
        null=True,
    )

    ter_rgb = ColorField(
        verbose_name=_("Color links"),
        help_text=_("Indicate the color that will be used for the links"),
        blank=True,
        null=True,
    )

    template = models.BooleanField(default=False)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["slug", "deleted"], name="unique_event_with_optional"),
            UniqueConstraint(
                fields=["slug"],
                condition=Q(deleted=None),
                name="unique_event_without_optional",
            ),
        ]

    def __str__(self):
        return self.name

    def get_elements(self, typ):
        queryset = typ.objects.filter(event=self.get_class_parent(typ))
        if hasattr(typ, "number"):
            queryset = queryset.order_by("number")
        return queryset

    def get_class_parent(self, nm):
        if inspect.isclass(nm) and issubclass(nm, BaseModel):
            nm = nm.__name__.lower()

        elements = [
            "character",
            "faction",
            "abilitypx",
            "deliverypx",
            "abilitytypepx",
            "pooltypeci",
            "writingquestion",
            "writingoption",
        ]

        if self.parent and nm in elements:
            # check if we don't want to actually use that event's elements
            if not self.get_config(f"campaign_{nm}_indep", False):
                return self.parent

        return self

    def get_cover_thumb_url(self):
        try:
            # noinspection PyUnresolvedReferences
            return self.cover_thumb.url
        except Exception as e:
            print(e)
            return None

    def get_name(self):
        return self.name

    def show(self):
        dc = {}

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
        if self.cover:
            # noinspection PyUnresolvedReferences
            dc["cover"] = self.cover.url
            # noinspection PyUnresolvedReferences
            dc["cover_thumb"] = self.cover_thumb.url

        if self.carousel_img:
            # noinspection PyUnresolvedReferences
            dc["carousel_img"] = self.carousel_img.url
            # noinspection PyUnresolvedReferences
            dc["carousel_thumb"] = self.carousel_thumb.url

        if self.font:
            # noinspection PyUnresolvedReferences
            dc["font"] = self.font.url

        if self.background:
            # noinspection PyUnresolvedReferences
            dc["background"] = self.background.url
            # noinspection PyUnresolvedReferences
            dc["background_red"] = self.background_red.url

        return dc

    def thumb(self):
        # noinspection PyUnresolvedReferences
        return show_thumb(100, self.cover_thumb.url)

    def download_sheet_template(self):
        # noinspection PyUnresolvedReferences
        return download(self.sheet_template.path)

    def get_media_filepath(self):
        fp = os.path.join(conf_settings.MEDIA_ROOT, f"pdf/{self.slug}/")
        os.makedirs(fp, exist_ok=True)
        return fp

    def get_config(self, name, def_v=None):
        return get_element_config(self, name, def_v)


class EventConfig(BaseModel):
    name = models.CharField(max_length=150)

    value = models.CharField(max_length=1000)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="configs")

    def __str__(self):
        return f"{self.event} {self.name}"

    class Meta:
        indexes = [
            models.Index(fields=["event", "name"]),
        ]
        constraints = [
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
    number = models.IntegerField()

    name = models.CharField(max_length=150, blank=False)

    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    class Meta:
        abstract = True
        ordering = ["event", "number"]

    def get_name(self):
        return get_attr(self, "name")

    def __str__(self):
        return self.name


class EventButton(BaseConceptModel):
    tooltip = models.CharField(max_length=200)

    link = models.URLField(max_length=150)

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]
        constraints = [
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
    INTRO = "i", _("Character sheet intro")
    TOC = "t", _("Terms and conditions")
    REGISTER = "r", _("Registration form")
    SEARCH = "s", _("Search")
    SIGNUP = "g", _("Registration mail")
    ASSIGNMENT = "a", _("Mail assignment")

    CHARACTER_PROPOSED = "cs", _("Proposed character")
    CHARACTER_APPROVED = "ca", _("Approved character")
    CHARACTER_REVIEW = "cr", _("Character review")


class EventText(BaseModel):
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

    class Meta:
        constraints = [
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


class ProgressStep(BaseConceptModel):
    order = models.IntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]
        constraints = [
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

    def __str__(self):
        return f"{self.order} - {self.name}"


class DevelopStatus(models.TextChoices):
    START = "0", _("Hidden")
    SHOW = "1", _("Visible")
    CANC = "8", _("Cancelled")
    DONE = "9", _("Concluded")


class Run(BaseModel):
    search = models.CharField(max_length=150, editable=False)

    development = models.CharField(
        max_length=1,
        choices=DevelopStatus.choices,
        default=DevelopStatus.START,
        verbose_name=_("Status"),
    )

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="runs")

    number = models.IntegerField()

    start = models.DateField(blank=True, null=True, verbose_name=_("Start date"))

    end = models.DateField(blank=True, null=True, verbose_name=_("End date"))

    registration_open = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("Registration opening date"),
        help_text=_("Enter the date and time when registrations open - leave blank to keep registrations closed"),
    )

    registration_secret = models.CharField(
        default=my_uuid_short,
        max_length=12,
        unique=True,
        verbose_name=_("Secret code"),
        help_text=_(
            "This code is used to generate the secret registration link, you may keep the default or customize it"
        ),
        db_index=True,
    )

    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    paid = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    plan = models.CharField(max_length=1, choices=AssociationPlan.choices, blank=True, null=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["event", "number", "deleted"], name="unique_run_with_optional"),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_run_without_optional",
            ),
        ]

    def __str__(self):
        s = self.event.name
        if self.number and self.number != 1:
            s = f"{s} #{self.number}"
        return s

    def get_where(self):
        # noinspection PyUnresolvedReferences
        return self.event.where

    def get_cover_url(self):
        # noinspection PyUnresolvedReferences
        return self.event.cover_thumb.url

    def pretty_dates(self):
        if not self.start or not self.end:
            return "TBA"
        if self.start == self.end:
            return formats.date_format(self.start, "j E Y")
        # noinspection PyUnresolvedReferences
        if self.start.year != self.end.year:
            return f"{formats.date_format(self.start, 'j E Y')} - {formats.date_format(self.end, 'j E Y')}"
        # noinspection PyUnresolvedReferences
        if self.start.month != self.end.month:
            return f"{formats.date_format(self.start, 'j E')} - {formats.date_format(self.end, 'j E Y')}"
        # noinspection PyUnresolvedReferences
        return f"{self.start.day} - {formats.date_format(self.end, 'j E Y')}"

    def get_media_filepath(self):
        # noinspection PyUnresolvedReferences
        fp = os.path.join(self.event.get_media_filepath(), f"{self.number}/")
        os.makedirs(fp, exist_ok=True)
        return fp

    def get_gallery_filepath(self):
        return self.get_media_filepath() + "gallery.pdf"

    def get_profiles_filepath(self):
        return self.get_media_filepath() + "profiles.pdf"

    def get_config(self, name, def_v=None):
        return get_element_config(self, name, def_v)


class RunConfig(BaseModel):
    name = models.CharField(max_length=150)

    value = models.CharField(max_length=1000)

    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="configs")

    def __str__(self):
        return f"{self.run} {self.name}"

    class Meta:
        indexes = [
            models.Index(fields=["run", "name"]),
        ]
        constraints = [
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
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="pre_registrations")

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="pre_registrations")

    pref = models.IntegerField()

    info = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.event} {self.member}"

    class Meta:
        constraints = [
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
