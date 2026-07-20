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

from typing import Any, ClassVar

from colorfield.fields import ColorField
from django.db import models
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill, ResizeToFit
from tinymce.models import HTMLField

from larpmanager.models.association import Association
from larpmanager.models.base import AlphanumericValidator, BaseModel, OrderMixin, UuidMixin
from larpmanager.models.member import Member
from larpmanager.models.utils import UploadToPathAndRename, show_thumb


class LarpManagerTutorial(OrderMixin, BaseModel):
    """Model for managing LARP tutorials and guides.

    Represents educational content for LARP management,
    including tutorials with descriptions and ordering.
    """

    name = models.CharField(max_length=100)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], db_index=True, blank=True)

    descr = HTMLField(blank=True, null=True)


class LarpManagerChatLog(BaseModel):
    """Log of questions asked through the wwyltd and ask-larpmanager chat widgets."""

    member = models.ForeignKey(Member, on_delete=models.CASCADE)

    question = models.TextField()


class LarpManagerReview(BaseModel):
    """Model for storing user reviews and testimonials.

    Contains review text and author information for
    displaying user feedback about the platform.
    """

    text = models.CharField(max_length=1000)

    author = models.CharField(max_length=100)


class LarpManagerFaqType(OrderMixin, BaseModel):
    """Model for categorizing FAQ entries.

    Provides organization structure for frequently
    asked questions with ordering and naming.
    """

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


class LarpManagerHighlight(BaseModel):
    """Model for storing highlight photos used in showcases."""

    info = models.CharField(max_length=1000)

    photo = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("highlight/"),
        verbose_name=_("Photo"),
    )

    reduced = ImageSpecField(
        source="photo",
        processors=[ResizeToFit(1000)],
        format="JPEG",
        options={"quality": 80},
    )

    def show_reduced(self) -> Any:
        """Generate HTML for displaying reduced-size image."""
        if self.reduced:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.reduced.url)
        return ""

    def as_dict(self, *, many_to_many: bool = True) -> dict:
        """Convert model instance to dictionary with image URL."""
        result_dict = super().as_dict(many_to_many=many_to_many)

        # Add reduced image URL if available
        if self.reduced:
            # noinspection PyUnresolvedReferences
            result_dict["reduced_url"] = self.reduced.url

        return result_dict


class LarpManagerScreenshot(OrderMixin, BaseModel):
    """Model for storing interface screenshots shown on the home page."""

    caption = models.CharField(max_length=1000)

    photo = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("screenshot/"),
        verbose_name=_("Photo"),
    )

    reduced = ImageSpecField(
        source="photo",
        processors=[ResizeToFit(1200)],
        format="JPEG",
        options={"quality": 80},
    )

    def show_reduced(self) -> Any:
        """Generate HTML for displaying reduced-size image."""
        if self.reduced:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.reduced.url)
        return ""

    def as_dict(self, *, many_to_many: bool = True) -> dict:
        """Convert model instance to dictionary with image URL."""
        result_dict = super().as_dict(many_to_many=many_to_many)

        # Add reduced image URL if available
        if self.reduced:
            # noinspection PyUnresolvedReferences
            result_dict["reduced_url"] = self.reduced.url

        return result_dict


class LarpManagerShowcase(BaseModel):
    """Model for displaying showcase items with photos."""

    number = models.IntegerField(blank=True, null=True)

    title = models.CharField(max_length=1000)

    text = HTMLField(blank=True, null=True)

    blog = models.ForeignKey(
        "LarpManagerBlog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="showcases",
    )

    def text_red(self) -> Any:
        """Get truncated version of showcase text."""
        return self.text[:100]


class LarpManagerGuide(BaseModel):
    """Model for managing published guides and articles.

    Represents detailed guides with images, text content,
    and publication status for user education.
    """

    number = models.IntegerField(blank=True, null=True)

    title = models.CharField(max_length=1000)

    description = models.CharField(max_length=1000, null=True)

    keywords = models.CharField(max_length=1000, null=True)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], db_index=True)

    text = HTMLField(blank=True, null=True)

    photo = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("albums/"),
        verbose_name=_("Photo"),
        blank=True,
        null=True,
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

    icon = models.CharField(max_length=100, blank=True, null=True)

    published = models.BooleanField(default=False)

    def show_thumb(self) -> Any:
        """Generate HTML for displaying thumbnail image."""
        if self.thumb:
            # noinspection PyUnresolvedReferences
            return show_thumb(thumbnail_size=100, image_url=self.thumb.url)
        return ""

    def text_red(self) -> Any:
        """Get truncated version of text content."""
        return self.text[:100]


class LarpManagerBlog(BaseModel):
    """Model for managing blog posts with published status."""

    number = models.IntegerField(blank=True, null=True)

    title = models.CharField(max_length=1000)

    description = models.CharField(max_length=1000, null=True)

    keywords = models.CharField(max_length=1000, null=True)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], db_index=True)

    text = HTMLField(blank=True, null=True)

    published = models.BooleanField(default=False)

    def text_red(self) -> Any:
        """Get truncated version of showcase text."""
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

    def __str__(self) -> str:
        """Return string representation of the profiler entry."""
        return f"{self.view_func_name} ({self.domain})"

    class Meta:
        indexes: ClassVar[list] = [models.Index(fields=["domain", "view_func_name"])]


class LarpManagerDiscover(OrderMixin, BaseModel):
    """Model for discovery/feature showcase content.

    Represents highlighted features or content for
    user discovery with ordering and visual elements.
    """

    name = models.CharField(max_length=100)

    text = HTMLField()

    profile = models.ImageField(upload_to=UploadToPathAndRename("discover/"), blank=True, null=True)

    profile_thumb = ImageSpecField(
        source="profile",
        processors=[ResizeToFill(500, 500)],
        format="JPEG",
        options={"quality": 90},
    )


class LarpManagerPartner(BaseModel):
    """Model for displaying partner organizations on the home page."""

    name = models.CharField(max_length=200)

    text = models.TextField(blank=True)

    url = models.URLField(max_length=500, blank=True)

    profile = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("partners/"),
        verbose_name=_("Profile Image"),
        blank=True,
        null=True,
    )

    profile_thumb = ImageSpecField(
        source="profile",
        processors=[ResizeToFill(200, 200)],
        format="JPEG",
        options={"quality": 85},
    )

    def show_thumb(self) -> Any:
        """Generate HTML for displaying thumbnail image."""
        if self.profile_thumb:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.profile_thumb.url)
        return ""

    def as_dict(self, *, many_to_many: bool = True) -> dict:
        """Convert model instance to dictionary with image URL."""
        result_dict = super().as_dict(many_to_many=many_to_many)

        if self.profile_thumb:
            # noinspection PyUnresolvedReferences
            result_dict["profile_thumb_url"] = self.profile_thumb.url

        return result_dict


class LarpManagerCollaborator(BaseModel):
    """Model for displaying project collaborators on the about us page."""

    name = models.CharField(max_length=200)

    photo = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("collaborators/"),
        verbose_name=_("Photo"),
    )

    thumb = ImageSpecField(
        source="photo",
        processors=[ResizeToFill(300, 300)],
        format="JPEG",
        options={"quality": 85},
    )

    def show_thumb(self) -> Any:
        """Generate HTML for displaying thumbnail image."""
        if self.thumb:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.thumb.url)
        return ""

    def as_dict(self, *, many_to_many: bool = True) -> dict:
        """Convert model instance to dictionary with image URL."""
        result_dict = super().as_dict(many_to_many=many_to_many)

        if self.thumb:
            # noinspection PyUnresolvedReferences
            result_dict["thumb_url"] = self.thumb.url

        return result_dict


class TicketStatus(models.TextChoices):
    """Status choices for LarpManagerTicket."""

    OPEN = "open", _("Open")
    WORKING = "working", _("Working")
    DONE = "done", _("Done")


class TicketPriority(models.TextChoices):
    """Priority choices for LarpManagerTicket."""

    LOW = "low", _("Low")
    MEDIUM = "medium", _("Medium")
    HIGH = "high", _("High")


class LarpManagerText(BaseModel):
    """Model for managing editable text snippets on the LarpManager home page."""

    name = models.CharField(max_length=200, unique=True, verbose_name=_("Name"), db_index=True)

    value = models.TextField(verbose_name=_("Value"))

    def __str__(self) -> str:
        """Return string representation of the text."""
        return f"{self.name}: {self.value[:50]}..."


class LarpManagerTicket(UuidMixin, BaseModel):
    """Model for managing support tickets and requests.

    Handles user support requests with contact information,
    content, and optional screenshots for issue tracking.
    """

    association = models.ForeignKey(Association, on_delete=models.CASCADE)

    reason = models.CharField(max_length=100, null=True)

    email = models.EmailField(
        null=True,
        help_text=_("How can we contact you"),
    )

    member = models.ForeignKey(Member, on_delete=models.CASCADE, null=True)

    content = models.TextField(max_length=5000, verbose_name=_("Request"), help_text=_("Describe how we can help you"))

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

    status = models.CharField(
        max_length=20,
        choices=TicketStatus.choices,
        default=TicketStatus.OPEN,
        verbose_name=_("Status"),
    )

    priority = models.CharField(
        max_length=20,
        choices=TicketPriority.choices,
        default=TicketPriority.LOW,
        verbose_name=_("Priority"),
    )

    analysis = models.CharField(max_length=10000, verbose_name=_("Analysis"), default="")

    def show_thumb(self) -> Any:
        """Generate HTML for displaying screenshot thumbnail."""
        if self.screenshot_reduced:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.screenshot_reduced.url)
        return ""

    def __str__(self) -> str:
        """Return string representation of the ticket."""
        return f"Ticket #{self.id}: {self.reason or 'No reason'}"


class NewsletterStatus(models.TextChoices):
    """Status choices for LarpManagerNewsletter."""

    ACTIVE = "a", "Active"
    NON_ACTIVE = "n", "Non active"
    UNSUBSCRIBED = "u", "Unsubscribed"


class LarpManagerDemoType(UuidMixin, OrderMixin, BaseModel):
    """Model for demo instance types offered on the get started page.

    Each type points to a template association whose whole data graph
    (events, registrations, characters) is cloned into a new demo instance.
    """

    name = models.CharField(max_length=100)

    slug = models.SlugField(max_length=100, unique=True, validators=[AlphanumericValidator], db_index=True)

    icon = models.CharField(max_length=50, blank=True, help_text="FontAwesome icon class shown on the button")

    color = ColorField(
        verbose_name=_("Color"),
        null=True,
        blank=True,
        help_text="Accent color shown on the demo card in the get started page",
    )

    descr = models.CharField(max_length=500, blank=True)

    template_association = models.ForeignKey(Association, on_delete=models.PROTECT, related_name="demo_types")

    active = models.BooleanField(default=True)

    allowed_sidebar = models.TextField(
        blank=True,
        help_text="Comma separated list of event/association permission slugs allowed in the sidebar, "
        "and feature slugs allowed in the player-facing navigation, for this demo type. "
        "Empty means no restriction.",
    )

    allowed_config = models.TextField(
        blank=True,
        help_text="Comma separated list of config section slugs allowed to be shown (and auto-opened) "
        "in the association/event configuration forms for this demo type. Empty means no restriction.",
    )

    is_campaign = models.BooleanField(
        default=False,
        help_text="Template association has multiple events under one campaign: grant the demo user an "
        "association-wide role and land on the association dashboard, instead of organizer of the first event.",
    )

    def __str__(self) -> str:
        """Return string representation of the demo type."""
        return self.name

    def get_allowed_sidebar_list(self) -> list[str]:
        """Return the list of allowed sidebar permission slugs, or an empty list for no restriction."""
        return [slug.strip() for slug in self.allowed_sidebar.split(",") if slug.strip()]

    def get_allowed_config_list(self) -> list[str]:
        """Return the list of allowed config section slugs, or an empty list for no restriction."""
        return [slug.strip() for slug in self.allowed_config.split(",") if slug.strip()]


class LarpManagerDemoHint(UuidMixin, OrderMixin, BaseModel):
    """Model for contextual hints shown while using a demo instance.

    Each hint is bound to a view name and optionally to a specific demo
    type; a null demo type means the hint applies to every demo instance.
    """

    key = models.SlugField(max_length=100, unique=True, db_index=True)

    demo_type = models.ForeignKey(
        LarpManagerDemoType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="hints",
    )

    view_name = models.CharField(max_length=255)

    title = models.CharField(max_length=200)

    content = HTMLField()

    active = models.BooleanField(default=True)

    class Meta:
        indexes: ClassVar[list] = [models.Index(fields=["view_name", "active"])]

    def __str__(self) -> str:
        """Return string representation of the demo hint."""
        return f"{self.key} ({self.view_name})"


class LarpManagerDemoHintDismissal(BaseModel):
    """Model tracking hints a member chose to no longer auto-open."""

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="demo_hint_dismissals")

    hint = models.ForeignKey(LarpManagerDemoHint, on_delete=models.CASCADE, related_name="dismissals")

    class Meta:
        unique_together = ("member", "hint")

    def __str__(self) -> str:
        """Return string representation of the dismissal."""
        return f"{self.member} - {self.hint_id}"


class LarpManagerNewsletter(BaseModel):
    """Model for managing newsletter recipients."""

    email = models.EmailField(unique=True)

    status = models.CharField(
        max_length=1,
        choices=NewsletterStatus.choices,
        default=NewsletterStatus.NON_ACTIVE,
    )

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.email} ({self.status})"
