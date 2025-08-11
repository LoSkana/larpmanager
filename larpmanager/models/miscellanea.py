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

from django.db import models
from django.db.models import Q, UniqueConstraint
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


class HelpQuestion(BaseModel):
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
    )

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return f"{self.member} {self.text}"


class Contact(BaseModel):
    channel = models.IntegerField(default=0)

    me = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="FIRST_CONTACT")

    you = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="SECOND_CONTACT")

    last_message = models.DateTimeField(auto_now_add=True)

    num_unread = models.IntegerField(default=0)

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE)

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

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE)

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

    def download(self):
        # noinspection PyUnresolvedReferences
        s = self.util.url
        # s = s.replace("media/", "", 1)
        return download(s)

    def file_name(self):
        if not self.util:
            return ""
        # noinspection PyUnresolvedReferences
        return os.path.basename(self.util.url)


class UrlShortner(BaseModel):
    number = models.IntegerField()

    name = models.CharField(max_length=150)

    cod = models.CharField(max_length=5, unique=True, default=my_uuid_miny, db_index=True)

    url = models.URLField(max_length=300)

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE)

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

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE)

    def __unicode__(self):
        # noinspection PyUnresolvedReferences
        return self.title

    def show_thumb(self):
        if self.thumb:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.thumb.url)


class AlbumUpload(BaseModel):
    name = models.CharField(max_length=70)

    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name="uploads")

    PHOTO = "p"
    TYPE_CHOICES = [
        (PHOTO, _("Photo")),
    ]
    typ = models.CharField(max_length=1, choices=TYPE_CHOICES)


class AlbumImage(BaseModel):
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

    def original_url(self):
        # noinspection PyUnresolvedReferences
        s = self.original.url
        return "/media/" + s.split("/media/")[2]


class Competence(BaseModel):
    name = models.CharField(max_length=100, help_text=_("The name of the competence"))

    descr = models.CharField(max_length=5000, help_text=_("A description of the skills / abilities involved"))

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE)

    members = models.ManyToManyField(Member, related_name="competences", through="CompetenceMemberRel")


class CompetenceMemberRel(BaseModel):
    competence = models.ForeignKey(Competence, on_delete=models.CASCADE)

    member = models.ForeignKey(Member, on_delete=models.CASCADE)

    exp = models.IntegerField(default=0)

    info = models.TextField(max_length=5000)

    def __str__(self):
        return f"{self.member} - {self.competence} ({self.exp})"

    class Meta:
        unique_together = ["competence", "member", "deleted"]


class WorkshopModule(BaseModel):
    search = models.CharField(max_length=150, editable=False)

    is_generic = models.BooleanField(default=False)

    name = models.CharField(max_length=50)

    number = models.IntegerField(blank=True)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="workshops")

    members = models.ManyToManyField(Member, related_name="workshops", through="WorkshopMemberRel")

    def __str__(self):
        return self.name

    def show(self):
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

    def show(self):
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

    def show(self):
        # noinspection PyUnresolvedReferences
        js = {"id": self.id, "is_correct": self.is_correct}
        self.upd_js_attr(js, "name")
        return js


class Inventory(BaseModel):
    cod = models.CharField(max_length=5)

    name = models.CharField(max_length=500, help_text=_("Briefly describe what the box contains"))

    shelf = models.CharField(max_length=5)

    rack = models.CharField(max_length=5)

    description = models.TextField(
        help_text=_(
            "Fully describe what the box contains, especially number of items, main features, state of preservation."
        )
    )

    tag = models.CharField(max_length=100, help_text=_("List of content-related tags"))

    photo = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("inventory/"),
        verbose_name=_("Photo"),
        help_text=_("Photo (clear and understandable) of the object"),
        null=True,
        blank=True,
    )

    thumb = ImageSpecField(
        source="photo",
        processors=[ResizeToFit(300)],
        format="JPEG",
        options={"quality": 80},
    )

    class Meta:
        abstract = True


class InventoryBox(Inventory):
    assoc = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="boxes")


class InventoryBoxHistory(Inventory):
    box = models.ForeignKey(InventoryBox, on_delete=models.CASCADE, related_name="histories")

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="box_histories")


class InventoryBoxPhoto(BaseModel):
    box = models.ForeignKey(InventoryBox, on_delete=models.CASCADE, related_name="photos")

    photo = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("albums/"),
        verbose_name=_("Photo"),
        help_text=_("Photo (clear and understandable) of the object"),
    )

    thumb = ImageSpecField(
        source="photo",
        processors=[ResizeToFit(300)],
        format="JPEG",
        options={"quality": 80},
    )


class ShuttleService(BaseModel):
    OPEN = "0"
    COMING = "1"
    DONE = "2"
    STATUS_CHOICES = [
        (OPEN, _("Waiting list")),
        (COMING, _("We're coming")),
        (DONE, _("Arrived safe and sound")),
    ]

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

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=OPEN, db_index=True)

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="shuttles")

    def __str__(self):
        return f"{self.member} ({self.date} {self.time}) {self.status}"


class Problem(BaseModel):
    RED = "r"
    ORANGE = "o"
    YELLOW = "y"
    GREEN = "g"
    SEVERITY_CHOICES = [
        (RED, "1 - RED"),
        (ORANGE, "2 - ORANGE"),
        (YELLOW, "3 - YELLOW"),
        (GREEN, "4 - GREEN"),
    ]

    OPEN = "o"
    WORKING = "w"
    CLOSED = "c"
    STATUS_CHOICES = [
        (OPEN, "1 - OPEN"),
        (WORKING, "2 - WORKING"),
        (CLOSED, "3 - CLOSED"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    number = models.IntegerField()

    severity = models.CharField(
        max_length=1,
        choices=SEVERITY_CHOICES,
        default=GREEN,
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
        choices=STATUS_CHOICES,
        default=OPEN,
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

    def get_small_text(self, s):
        if not hasattr(self, s):
            return s
        v = getattr(self, s)
        if not v:
            return s
        return v[:100]

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
    assoc = models.ForeignKey(Association, on_delete=models.CASCADE, blank=True, null=True)

    run = models.ForeignKey(Run, on_delete=models.CASCADE, blank=True, null=True)

    recipient = models.CharField(max_length=170)

    subj = models.CharField(max_length=500)

    body = models.TextField()

    reply_to = models.CharField(max_length=170, blank=True, null=True)

    sent = models.DateTimeField(blank=True, null=True)

    search = models.CharField(max_length=500, blank=True)

    def __str__(self):
        return f"{self.recipient} - {self.subj}"
