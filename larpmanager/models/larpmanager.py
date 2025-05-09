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

from django.db import models
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill, ResizeToFit
from tinymce.models import HTMLField

from larpmanager.models.base import AlphanumericValidator, BaseModel
from larpmanager.models.utils import UploadToPathAndRename, show_thumb


class LarpManagerPlan(models.TextChoices):
    FREE = "f", _("Free")
    SUPPORT = "p", _("Support")


class LarpManagerTutorial(BaseModel):
    name = models.CharField(max_length=100)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], db_index=True, blank=True)

    descr = HTMLField(blank=True, null=True)

    order = models.IntegerField()


class LarpManagerHowto(BaseModel):
    order = models.IntegerField()

    name = models.CharField(max_length=100)

    descr = models.TextField(max_length=500)

    link = models.CharField(max_length=500, blank=True)


class LarpManagerReview(BaseModel):
    text = models.CharField(max_length=1000)

    author = models.CharField(max_length=100)


class LarpManagerFaqType(BaseModel):
    order = models.IntegerField()

    name = models.CharField(max_length=100)


class LarpManagerFaq(BaseModel):
    number = models.IntegerField(blank=True, null=True)

    question = models.CharField(max_length=1000)

    answer = HTMLField(blank=True, null=True)

    typ = models.ForeignKey(
        LarpManagerFaqType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="faqs",
    )


class LarpManagerShowcase(BaseModel):
    number = models.IntegerField(blank=True, null=True)

    title = models.CharField(max_length=1000)

    text = HTMLField(blank=True, null=True)

    info = models.CharField(max_length=1000)

    photo = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("showcase/"),
        verbose_name=_("Photo"),
    )

    reduced = ImageSpecField(
        source="photo",
        processors=[ResizeToFit(1000)],
        format="JPEG",
        options={"quality": 80},
    )

    def show_reduced(self):
        if self.reduced:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.reduced.url)
        return ""

    def text_red(self):
        return self.text[:100]


class LarpManagerBlog(BaseModel):
    number = models.IntegerField(blank=True, null=True)

    title = models.CharField(max_length=1000)

    description = models.CharField(max_length=1000, null=True)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], db_index=True)

    text = HTMLField(blank=True, null=True)

    photo = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("albums/"),
        verbose_name=_("Photo"),
    )

    reduced = ImageSpecField(
        source="photo",
        processors=[ResizeToFit(1000)],
        format="JPEG",
        options={"quality": 80},
    )

    thumb = ImageSpecField(
        source="photo",
        processors=[ResizeToFit(300)],
        format="JPEG",
        options={"quality": 80},
    )

    published = models.BooleanField(default=False)

    def show_thumb(self):
        if self.thumb:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.thumb.url)
        return ""

    def text_red(self):
        return self.text[:100]


class LarpManagerProfiler(BaseModel):
    num_calls = models.IntegerField(default=0)

    mean_duration = models.FloatField(default=0)

    domain = models.CharField(max_length=100)

    view_func_name = models.CharField(max_length=100, verbose_name="View function")

    date = models.DateField()

    class Meta:
        unique_together = ("domain", "view_func_name", "date")


class LarpManagerDiscover(BaseModel):
    order = models.IntegerField()

    name = models.CharField(max_length=100)

    text = HTMLField()

    profile = models.ImageField(upload_to=UploadToPathAndRename("discover/"), blank=True, null=True)

    profile_thumb = ImageSpecField(
        source="profile", processors=[ResizeToFill(500, 500)], format="JPEG", options={"quality": 90}
    )
