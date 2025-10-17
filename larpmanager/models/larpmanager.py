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

from larpmanager.models.association import Association
from larpmanager.models.base import AlphanumericValidator, BaseModel
from larpmanager.models.member import Member
from larpmanager.models.utils import UploadToPathAndRename, show_thumb


class LarpManagerTutorial(BaseModel):
    """Model for managing LARP tutorials and guides.

    Represents educational content for LARP management,
    including tutorials with descriptions and ordering.
    """

    name = models.CharField(max_length=100)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], db_index=True, blank=True)

    descr = HTMLField(blank=True, null=True)

    order = models.IntegerField()


class LarpManagerReview(BaseModel):
    """Model for storing user reviews and testimonials.

    Contains review text and author information for
    displaying user feedback about the platform.
    """

    text = models.CharField(max_length=1000)

    author = models.CharField(max_length=100)


class LarpManagerFaqType(BaseModel):
    """Model for categorizing FAQ entries.

    Provides organization structure for frequently
    asked questions with ordering and naming.
    """

    order = models.IntegerField()

    name = models.CharField(max_length=100)


class LarpManagerFaq(BaseModel):
    """Model for storing frequently asked questions.

    Contains question-answer pairs with optional
    categorization through FaqType relationship.
    """

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
    """Model for displaying showcase items with photos.

    Represents featured content with images, text,
    and metadata for promotional displays.
    """

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
        """Generate HTML for displaying reduced-size image.

        Returns:
            str: HTML string for reduced image display or empty string if no image
        """
        if self.reduced:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.reduced.url)
        return ""

    def text_red(self):
        """Get truncated version of showcase text.

        Returns:
            str: First 100 characters of the showcase text
        """
        return self.text[:100]

    def as_dict(self, many_to_many=True):
        """Convert model instance to dictionary with image URL.

        Args:
            many_to_many (bool): Whether to include many-to-many relationships

        Returns:
            dict: Model data as dictionary with reduced image URL if available
        """
        res = super().as_dict(many_to_many)
        if self.reduced:
            # noinspection PyUnresolvedReferences
            res["reduced_url"] = self.reduced.url
        return res


class LarpManagerGuide(BaseModel):
    """Model for managing published guides and articles.

    Represents detailed guides with images, text content,
    and publication status for user education.
    """

    number = models.IntegerField(blank=True, null=True)

    title = models.CharField(max_length=1000)

    description = models.CharField(max_length=1000, null=True)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], db_index=True)

    text = HTMLField(blank=True, null=True)

    photo = models.ImageField(
        max_length=500, upload_to=UploadToPathAndRename("albums/"), verbose_name=_("Photo"), blank=True, null=True
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
        """Generate HTML for displaying thumbnail image.

        Returns:
            str: HTML string for thumbnail display or empty string if no image
        """
        if self.thumb:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.thumb.url)
        return ""

    def text_red(self):
        """Get truncated version of text content.

        Returns:
            str: First 100 characters of the guide text
        """
        return self.text[:100]


class LarpManagerProfiler(BaseModel):
    """Model for storing performance profiling data.

    Tracks individual execution times with request path and query
    """

    num_calls = models.IntegerField(default=0)

    mean_duration = models.FloatField(default=0)

    domain = models.CharField(max_length=100)

    path = models.CharField(max_length=500, blank=True)

    query = models.TextField(blank=True)

    method = models.CharField(max_length=10, blank=True)

    view_func_name = models.CharField(max_length=100, verbose_name="View function")

    duration = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["domain", "view_func_name"])]


class LarpManagerDiscover(BaseModel):
    """Model for discovery/feature showcase content.

    Represents highlighted features or content for
    user discovery with ordering and visual elements.
    """

    order = models.IntegerField()

    name = models.CharField(max_length=100)

    text = HTMLField()

    profile = models.ImageField(upload_to=UploadToPathAndRename("discover/"), blank=True, null=True)

    profile_thumb = ImageSpecField(
        source="profile", processors=[ResizeToFill(500, 500)], format="JPEG", options={"quality": 90}
    )


class LarpManagerTicket(BaseModel):
    """Model for managing support tickets and requests.

    Handles user support requests with contact information,
    content, and optional screenshots for issue tracking.
    """

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE)

    reason = models.CharField(max_length=100, null=True)

    email = models.EmailField(
        null=True,
        help_text=_("How can we contact you"),
    )

    member = models.ForeignKey(Member, on_delete=models.CASCADE, null=True)

    content = models.CharField(max_length=1000, verbose_name=_("Request"), help_text=_("Describe how we can help you"))

    screenshot = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("tickets/"),
        verbose_name=_("Screenshot"),
        help_text=_("Optional - A screenshot of the error / bug / problem"),
        null=True,
        blank=True,
    )

    screenshot_reduced = ImageSpecField(
        source="screenshot",
        processors=[ResizeToFit(1000)],
        format="JPEG",
        options={"quality": 80},
    )

    def show_thumb(self):
        """Generate HTML for displaying screenshot thumbnail.

        Returns:
            str: HTML string for screenshot thumbnail or empty string if no image
        """
        if self.screenshot_reduced:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.screenshot_reduced.url)
        return ""
