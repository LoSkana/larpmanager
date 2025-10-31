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
import random
import secrets
from typing import Any

from django.db import models
from django.db.models import Q, UniqueConstraint
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from pilkit.processors import ResizeToFit
from tinymce.models import HTMLField

from larpmanager.models.association import Association
from larpmanager.models.base import BaseModel
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration
from larpmanager.models.utils import UploadToPathAndRename, download, my_uuid, my_uuid_miny, show_thumb
from larpmanager.models.writing import Character
from larpmanager.utils.validators import FileTypeValidator


class HelpQuestion(BaseModel):
    """Model for storing user help questions and support requests."""

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="questions")

    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Event"),
        help_text=_(
            "If your question is about a specific event, please select it! If  is a general "
            "question instead, please leave it blank."
        ),
    )

    is_user = models.BooleanField(default=True)

    text = models.TextField(
        max_length=5000,
        verbose_name=_("Text"),
        help_text=_("Write your question, request or concern here. We will be happy to answer you!"),
    )

    closed = models.BooleanField(default=False)

    attachment = models.FileField(
        upload_to=UploadToPathAndRename("attachment/"),
        blank=True,
        null=True,
        verbose_name=_("Attachment"),
        help_text=_("If you need to attach a file, indicate it here, otherwise leave blank"),
        validators=[
            FileTypeValidator(
                [
                    "application/pdf",
                    "application/msword",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "text/plain",
                    "image/jpeg",
                    "image/png",
                    "image/gif",
                ]
            )
        ],
    )

    association = models.ForeignKey(Association, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return f"{self.member} {self.text}"


class Contact(BaseModel):
    """Model for managing private messaging contacts between members."""

    channel = models.IntegerField(default=0)

    me = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="FIRST_CONTACT")

    you = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="SECOND_CONTACT")

    last_message = models.DateTimeField(auto_now_add=True)

    num_unread = models.IntegerField(default=0)

    association = models.ForeignKey(Association, on_delete=models.CASCADE)

    class Meta:
        ordering = ["me", "you"]
        constraints = [
            UniqueConstraint(fields=["me", "you", "deleted"], name="unique_contact_with_optional"),
            UniqueConstraint(
                fields=["me", "you"],
                condition=Q(deleted=None),
                name="unique_contact_without_optional",
            ),
        ]

    def __str__(self):
        return f"C - {self.me} {self.you}"


class ChatMessage(BaseModel):
    message = models.TextField(max_length=1000)

    channel = models.IntegerField(db_index=True)

    sender = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="SENDER_MSG")

    receiver = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="RECEIVER_MSG")

    association = models.ForeignKey(Association, on_delete=models.CASCADE)

    def __str__(self):
        return f"CM - {self.sender} {self.message[:20]}"


class Util(BaseModel):
    number = models.IntegerField()

    name = models.CharField(max_length=150)

    cod = models.CharField(max_length=16, null=True)

    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    util = models.FileField(upload_to=UploadToPathAndRename("../utils/"))

    def __str__(self):
        return f"U{self.number} {self.name}"

    def download(self) -> HttpResponse:
        """Download the utility file."""
        # noinspection PyUnresolvedReferences
        s = self.util.url
        # s = s.replace("media/", "", 1)
        return download(s)

    def file_name(self) -> str:
        """Return the base filename from the util URL or empty string if no util."""
        if not self.util:
            return ""
        # noinspection PyUnresolvedReferences
        return os.path.basename(self.util.url)


class UrlShortner(BaseModel):
    number = models.IntegerField()

    name = models.CharField(max_length=150)

    cod = models.CharField(max_length=5, unique=True, default=my_uuid_miny, db_index=True)

    url = models.URLField(max_length=300)

    association = models.ForeignKey(Association, on_delete=models.CASCADE)

    def __str__(self):
        return f"U{self.number} {self.name}"


class Album(BaseModel):
    name = models.CharField(max_length=70)

    cover = models.ImageField(max_length=500, upload_to=UploadToPathAndRename("albums/cover/"), blank=True)

    thumb = ImageSpecField(
        source="cover",
        processors=[ResizeToFit(300)],
        format="JPEG",
        options={"quality": 80},
    )

    is_visible = models.BooleanField(default=True)

    cod = models.SlugField(max_length=32, unique=True, default=my_uuid, db_index=True)

    parent = models.ForeignKey(
        "album",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="sub_albums",
    )

    run = models.ForeignKey(Run, on_delete=models.PROTECT, blank=True, null=True, related_name="albums")

    association = models.ForeignKey(Association, on_delete=models.CASCADE)

    def __unicode__(self):
        # noinspection PyUnresolvedReferences
        return self.title

    def show_thumb(self):
        if self.thumb:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.thumb.url)


class AlbumUpload(BaseModel):
    """Model for tracking uploaded content to albums."""

    name = models.CharField(max_length=70)

    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name="uploads")

    PHOTO = "p"
    TYPE_CHOICES = [
        (PHOTO, _("Photo")),
    ]
    typ = models.CharField(max_length=1, choices=TYPE_CHOICES)


class AlbumImage(BaseModel):
    """Model for storing and processing album images with thumbnails."""

    upload = models.OneToOneField(AlbumUpload, on_delete=models.CASCADE, related_name="image")

    original = models.ImageField(upload_to=UploadToPathAndRename("albums/"))

    thumb = ImageSpecField(
        source="original",
        processors=[ResizeToFit(300)],
        format="JPEG",
        options={"quality": 80},
    )

    show = ImageSpecField(
        source="original",
        processors=[ResizeToFit(1280)],
        format="JPEG",
        options={"quality": 70},
    )

    width = models.IntegerField(default=0)

    height = models.IntegerField(default=0)

    def __str__(self):
        return self.upload.name

    def show_thumb(self):
        if self.thumb:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.thumb.url)

    def original_url(self) -> str:
        """Extract the original media URL path from the full URL."""
        # noinspection PyUnresolvedReferences
        s = self.original.url
        # Split by /media/ and take the third part (after two splits)
        return "/media/" + s.split("/media/")[2]


class Competence(BaseModel):
    """Model for managing member competences and skills within associations."""

    name = models.CharField(max_length=100, help_text=_("The name of the competence"))

    descr = models.CharField(max_length=5000, help_text=_("A description of the skills / abilities involved"))

    association = models.ForeignKey(Association, on_delete=models.CASCADE)

    members = models.ManyToManyField(Member, related_name="competences", through="CompetenceMemberRel")


class CompetenceMemberRel(BaseModel):
    """Through model linking members to competences with experience levels."""

    competence = models.ForeignKey(Competence, on_delete=models.CASCADE)

    member = models.ForeignKey(Member, on_delete=models.CASCADE)

    exp = models.IntegerField(default=0)

    info = models.TextField(max_length=5000)

    def __str__(self):
        return f"{self.member} - {self.competence} ({self.exp})"

    class Meta:
        unique_together = ["competence", "member", "deleted"]


class WorkshopModule(BaseModel):
    """Model for managing workshop modules and member participation."""

    search = models.CharField(max_length=150, editable=False)

    is_generic = models.BooleanField(default=False)

    name = models.CharField(max_length=50)

    number = models.IntegerField(blank=True)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="workshops")

    members = models.ManyToManyField(Member, related_name="workshops", through="WorkshopMemberRel")

    def __str__(self):
        return self.name

    def show(self) -> dict[str, Any]:
        """Return dictionary representation of instance for display."""
        # noinspection PyUnresolvedReferences
        js = {"id": self.id, "number": self.number}
        self.upd_js_attr(js, "name")
        return js


class WorkshopMemberRel(BaseModel):
    workshop = models.ForeignKey(WorkshopModule, on_delete=models.CASCADE)

    member = models.ForeignKey(Member, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.workshop} - {self.member}"


class WorkshopQuestion(BaseModel):
    search = models.CharField(max_length=200, editable=False)

    name = models.CharField(max_length=200)

    module = models.ForeignKey(WorkshopModule, on_delete=models.CASCADE, related_name="questions")

    number = models.IntegerField(blank=True)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="workshop_questions")

    def __str__(self):
        return self.name

    def show(self) -> dict[str, any]:
        """Return dictionary representation for display purposes.

        Returns:
            Dictionary containing id, number and name attributes.
        """
        # noinspection PyUnresolvedReferences
        js = {"id": self.id, "opt": [], "number": self.number}
        self.upd_js_attr(js, "name")
        # noinspection PyUnresolvedReferences
        for op in self.options.all():
            js["opt"].append(op.show())
        random.shuffle(js["opt"])
        return js

    class Meta:
        constraints = [models.UniqueConstraint(fields=["module", "number", "deleted"], name="unique workshop question")]


class WorkshopOption(BaseModel):
    search = models.CharField(max_length=500, editable=False)

    question = models.ForeignKey(WorkshopQuestion, on_delete=models.CASCADE, related_name="options")

    name = models.CharField(max_length=500)

    is_correct = models.BooleanField(default=False)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="workshop_options")

    number = models.IntegerField(blank=True)

    def __str__(self):
        return f"{self.question} {self.name} ({self.is_correct})"

    def show(self) -> dict[str, Any]:
        """Return JSON-serializable dict with answer option data.

        Returns:
            Dictionary with id, correctness flag, and name if present.
        """
        # noinspection PyUnresolvedReferences
        # Build base dict with id and correctness status
        js = {"id": self.id, "is_correct": self.is_correct}

        # Add name attribute if available
        self.upd_js_attr(js, "name")

        return js


class WarehouseContainer(BaseModel):
    name = models.CharField(max_length=100, help_text=_("Code of the box or shelf"))

    position = models.CharField(max_length=100, help_text=_("Where it is located"), blank=True, default="")

    description = models.CharField(max_length=1000, blank=True, default="")

    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="containers")


class WarehouseTag(BaseModel):
    name = models.CharField(max_length=100)

    description = models.CharField(max_length=1000, blank=True, default="")

    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="tags")


class WarehouseItem(BaseModel):
    name = models.CharField(max_length=100)

    quantity = models.IntegerField(blank=True, null=True)

    description = models.CharField(max_length=1000, blank=True, default="")

    container = models.ForeignKey(WarehouseContainer, on_delete=models.CASCADE, related_name="items")

    tags = models.ManyToManyField(WarehouseTag, related_name="items", blank=True)

    photo = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("warehouse/"),
        verbose_name=_("Photo"),
        help_text=_("Photo of the object"),
        null=True,
        blank=True,
    )

    thumb = ImageSpecField(
        source="photo",
        processors=[ResizeToFit(300)],
        format="JPEG",
        options={"quality": 80},
    )

    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="items")

    @classmethod
    def get_optional_fields(cls):
        return ["quantity"]


class WarehouseMovement(BaseModel):
    quantity = models.IntegerField(blank=True, null=True)

    item = models.ForeignKey(WarehouseItem, on_delete=models.CASCADE, related_name="movements")

    notes = models.CharField(
        max_length=1000,
        blank=True,
        null=True,
        help_text=_("Where it has been placed? When it is expected to come back?"),
    )

    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="movements")

    completed = models.BooleanField(default=False)


class WarehouseArea(BaseModel):
    name = models.CharField(max_length=100, help_text=_("Name of event area"))

    position = models.CharField(max_length=100, help_text=_("Where it is"), blank=True, default="")

    description = models.CharField(max_length=1000, blank=True, default="")

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="area")


class WarehouseItemAssignment(BaseModel):
    quantity = models.IntegerField(blank=True, null=True)

    item = models.ForeignKey(WarehouseItem, on_delete=models.CASCADE, related_name="assignments")

    area = models.ForeignKey(WarehouseArea, on_delete=models.CASCADE)

    notes = models.CharField(max_length=1000, blank=True, default="")

    loaded = models.BooleanField(default=False)

    deployed = models.BooleanField(default=False)

    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["area", "item", "deleted"],
                name="unique_warehouse_item_assignment_with_optional",
            ),
            UniqueConstraint(
                fields=["area", "item"],
                condition=Q(deleted=None),
                name="unique_warehouse_item_assignment_without_optional",
            ),
        ]


class ShuttleStatus(models.TextChoices):
    OPEN = "0", _("Waiting list")
    COMING = "1", _("We're coming")
    DONE = "2", _("Arrived safe and sound")


class ShuttleService(BaseModel):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="shuttle_services_requests")

    passengers = models.IntegerField(
        verbose_name=_("Number of passengers"),
        help_text=_("Indicates how many passengers require transportation"),
    )

    address = models.TextField(
        verbose_name=_("Address"),
        help_text=_("Indicate as precisely as possible where to pick you up"),
    )

    info = models.TextField(
        verbose_name=_("Informations"),
        help_text=_(
            "Indicates how you can be recognized, if you will be found near some point "
            "specific, if you have a lot of luggage: any information that might help us help "
            "you"
        ),
    )

    date = models.DateField(
        verbose_name=_("Request date"),
        help_text=_("For which day you will need transportation"),
    )

    time = models.TimeField(
        verbose_name=_("Request time"),
        help_text=_("For what time you will need transportation (time zone of the larp location)"),
    )

    working = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="shuttle_services_worked",
        blank=True,
        null=True,
    )

    notes = models.TextField(
        verbose_name=_("Note"),
        help_text=_(
            "Indicates useful information to passengers, such as color of your car, time estimated time of your arrival"
        ),
        null=True,
    )

    status = models.CharField(max_length=1, choices=ShuttleStatus.choices, default=ShuttleStatus.OPEN, db_index=True)

    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="shuttles")

    def __str__(self):
        return f"{self.member} ({self.date} {self.time}) {self.status}"


class ProblemStatus(models.TextChoices):
    OPEN = "o", "1 - OPEN"
    WORKING = "w", "2 - WORKING"
    CLOSED = "c", "3 - CLOSED"


class ProblemSeverity(models.TextChoices):
    RED = "r", "1 - RED"
    ORANGE = "o", "2 - ORANGE"
    YELLOW = "y", "3 - YELLOW"
    GREEN = "g", "4 - GREEN"


class Problem(BaseModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    number = models.IntegerField()

    severity = models.CharField(
        max_length=1,
        choices=ProblemSeverity.choices,
        default=ProblemSeverity.GREEN,
        verbose_name=_("Severity"),
        help_text=_(
            "Indicate severity: RED (risks ruining the event for more than half of the "
            "participants), ORANGE (risks ruining the event for more than ten participants),  YELLOW "
            "(risks ruining the event for a few participants), GREEN (more than  problems, finesses "
            "to be fixed)"
        ),
    )

    status = models.CharField(
        max_length=1,
        choices=ProblemStatus.choices,
        default=ProblemStatus.OPEN,
        verbose_name=_("Status"),
        help_text=_(
            "When putting in WORKING, indicate in the comments the specific actions that  are "
            "being performed; when putting in CLOSED, indicate showd in the  comments."
        ),
        db_index=True,
    )

    where = models.TextField(
        verbose_name=_("Where"),
        help_text=_("Describe exactly at which point it occurs"),
    )

    when = models.TextField(
        verbose_name=_("When"),
        help_text=_("Describe exactly what condition it is in"),
    )

    what = models.TextField(
        verbose_name=_("What"),
        help_text=_("Describe exactly what risks it poses to the event"),
    )

    who = models.TextField(
        verbose_name=_("Who"),
        help_text=_("Describe exactly which participants are involved"),
    )

    assigned = models.CharField(max_length=100, help_text=_("Who takes it upon themselves to solve it"))

    comments = models.TextField(blank=True)

    def get_small_text(self, attribute_name: str) -> str:
        """Get truncated text value from object attribute.

        Args:
            attribute_name: Attribute name to retrieve and truncate.

        Returns:
            Truncated string (max 100 chars) or original string if attribute doesn't exist.
        """
        # Check if attribute exists on object
        if not hasattr(self, attribute_name):
            return attribute_name

        # Get attribute value
        attribute_value = getattr(self, attribute_name)
        if not attribute_value:
            return attribute_name

        # Return truncated value (max 100 characters)
        return attribute_value[:100]

    def where_l(self):
        return self.get_small_text("where")

    def when_l(self):
        return self.get_small_text("when")

    def who_l(self):
        return self.get_small_text("who")

    def what_l(self):
        return self.get_small_text("what")


class PlayerRelationship(BaseModel):
    reg = models.ForeignKey(Registration, on_delete=models.CASCADE)

    target = models.ForeignKey(Character, related_name="target_players", on_delete=models.CASCADE)

    text = HTMLField(max_length=5000)

    def __str__(self):
        # noinspection PyUnresolvedReferences
        return f"{self.reg} - {self.target} ({self.reg.run.number})"

    class Meta:
        indexes = [
            models.Index(fields=["reg"], condition=Q(deleted__isnull=True), name="prel_reg_act"),
            models.Index(fields=["target"], condition=Q(deleted__isnull=True), name="prel_target_act"),
        ]
        constraints = [
            UniqueConstraint(
                fields=["reg", "target", "deleted"],
                name="unique_player_relationship_with_optional",
            ),
            UniqueConstraint(
                fields=["reg", "target"],
                condition=Q(deleted=None),
                name="unique_player_relationship_without_optional",
            ),
        ]


class Email(BaseModel):
    association = models.ForeignKey(Association, on_delete=models.CASCADE, blank=True, null=True)

    run = models.ForeignKey(Run, on_delete=models.CASCADE, blank=True, null=True)

    recipient = models.CharField(max_length=170)

    subj = models.CharField(max_length=500)

    body = models.TextField()

    reply_to = models.CharField(max_length=170, blank=True, null=True)

    sent = models.DateTimeField(blank=True, null=True)

    search = models.CharField(max_length=500, blank=True)

    def __str__(self):
        return f"{self.recipient} - {self.subj}"


class OneTimeContent(BaseModel):
    """
    Model to store multimedia content for one-time access via tokens.
    Organizers can upload video/audio files and generate access tokens.
    """

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="onetime_contents",
        verbose_name=_("Event"),
        help_text=_("The event this content belongs to"),
    )

    name = models.CharField(
        max_length=200,
        verbose_name=_("Content name"),
        help_text=_("Descriptive name for this content"),
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Optional description of the content"),
    )

    file = models.FileField(
        upload_to=UploadToPathAndRename("onetime_content/"),
        verbose_name=_("Media file"),
        help_text=_("Video or audio file to be streamed (recommended: MP4, WebM, MP3)"),
    )

    content_type = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Content type"),
        help_text=_("MIME type of the file (e.g., video/mp4)"),
    )

    file_size = models.BigIntegerField(
        default=0,
        verbose_name=_("File size"),
        help_text=_("Size of the file in bytes"),
    )

    duration = models.IntegerField(
        blank=True,
        null=True,
        verbose_name=_("Duration"),
        help_text=_("Duration in seconds (optional)"),
    )

    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Whether this content is currently available for access"),
    )

    class Meta:
        ordering = ["-created"]
        verbose_name = _("One-Time Content")
        verbose_name_plural = _("One-Time Contents")

    def __str__(self):
        return f"{self.name} ({self.event.name})"

    def save(self, *args, **kwargs):
        """Override save to capture file metadata."""
        if self.file:
            self.file_size = self.file.size
            # Try to determine content type
            if not self.content_type:
                file_name = self.file.name.lower()
                if file_name.endswith(".mp4"):
                    self.content_type = "video/mp4"
                elif file_name.endswith(".webm"):
                    self.content_type = "video/webm"
                elif file_name.endswith(".mp3"):
                    self.content_type = "audio/mpeg"
                elif file_name.endswith(".ogg"):
                    self.content_type = "audio/ogg"
                else:
                    self.content_type = "application/octet-stream"
        super().save(*args, **kwargs)

    def generate_token(self, note=""):
        """
        Generate a new access token for this content.

        Args:
            note (str): Optional note describing the purpose of this token

        Returns:
            OneTimeAccessToken: The newly created token
        """
        token = OneTimeAccessToken.objects.create(content=self, note=note)
        return token

    def get_token_stats(self):
        """
        Get statistics about tokens for this content.

        Returns:
            dict: Dictionary with token statistics
        """
        access_tokens = self.access_tokens.all()
        return {
            "total": access_tokens.count(),
            "used": access_tokens.filter(used=True).count(),
            "unused": access_tokens.filter(used=False).count(),
        }


class OneTimeAccessToken(BaseModel):
    """
    Access token for one-time viewing of content.
    Each token can only be used once.
    """

    content = models.ForeignKey(
        OneTimeContent,
        on_delete=models.CASCADE,
        related_name="access_tokens",
        verbose_name=_("Content"),
    )

    token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        editable=False,
        verbose_name=_("Token"),
    )

    note = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("Note"),
        help_text=_("Optional note about this token (e.g., recipient name, purpose)"),
    )

    used = models.BooleanField(
        default=False,
        verbose_name=_("Used"),
        help_text=_("Whether this token has been used"),
    )

    used_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("Used at"),
        help_text=_("When this token was used"),
    )

    used_by = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="used_onetime_tokens",
        verbose_name=_("Used by"),
        help_text=_("Member who used this token (if authenticated)"),
    )

    ip_address = models.GenericIPAddressField(
        blank=True,
        null=True,
        verbose_name=_("IP address"),
        help_text=_("IP address from which the token was used"),
    )

    user_agent = models.TextField(
        blank=True,
        verbose_name=_("User agent"),
        help_text=_("Browser user agent string from the access"),
    )

    class Meta:
        ordering = ["-created"]
        verbose_name = _("One-Time Access Token")
        verbose_name_plural = _("One-Time Access Tokens")

    def __str__(self):
        status = _("Used") if self.used else _("Unused")
        return f"{self.token[:8]}... - {status}"

    def save(self, *args, **kwargs):
        """Generate token on creation."""
        if not self.token:
            # Generate a cryptographically secure token
            self.token = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    def mark_as_used(self, http_request=None, authenticated_member=None):
        """
        Mark this token as used and record access information.

        Args:
            http_request: Django HttpRequest object to extract metadata
            authenticated_member: Member object if user is authenticated
        """
        self.used = True
        self.used_at = timezone.now()
        self.used_by = authenticated_member

        if http_request:
            # Extract IP address
            forwarded_for_header = http_request.META.get("HTTP_X_FORWARDED_FOR")
            if forwarded_for_header:
                self.ip_address = forwarded_for_header.split(",")[0].strip()
            else:
                self.ip_address = http_request.META.get("REMOTE_ADDR")

            # Extract user agent
            self.user_agent = http_request.META.get("HTTP_USER_AGENT", "")[:500]

        self.save()
