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

import logging
import os
from pathlib import Path
from typing import Any

from django.conf import settings as conf_settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django.db.models.constraints import UniqueConstraint
from django.http import Http404
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from phonenumber_field.modelfields import PhoneNumberField
from pilkit.processors import ResizeToFill

from larpmanager.cache.config import get_element_config
from larpmanager.models.association import Association
from larpmanager.models.base import BaseModel
from larpmanager.models.utils import UploadToPathAndRename, download_d, show_thumb
from larpmanager.utils.codes import countries

logger = logging.getLogger(__name__)


class GenderChoices(models.TextChoices):
    MALE = "m", _("Male")
    FEMALE = "f", _("Female")
    OTHER = "o", _("Other")


class FirstAidChoices(models.TextChoices):
    YES = "y", "Yes"
    NO = "n", "No"


class NewsletterChoices(models.TextChoices):
    ALL = "a", _("Yes, keep me posted!")
    ONLY = "o", _("Only really important communications")
    NO = "n", _("No, I don't want updates")


class DocumentChoices(models.TextChoices):
    IDENT = "i", _("ID Card")
    PATEN = "p", _("Driver's License")
    PASS = "s", _("Passport")


class Member(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="member")

    email = models.CharField(max_length=200, editable=False)

    search = models.CharField(max_length=200, editable=False)

    language = models.CharField(
        max_length=3,
        choices=conf_settings.LANGUAGES,
        default="en",
        null=True,
        verbose_name=_("Navigation language"),
        help_text=_("Preferred navigation language"),
    )

    name = models.CharField(max_length=100, verbose_name=_("Name"))

    surname = models.CharField(max_length=100, verbose_name=_("Surname"))

    nickname = models.CharField(
        max_length=100,
        verbose_name=_("Alias"),
        help_text=_(
            "If you prefer that your real name and surname not be publicly visible, please "
            "indicate an alias that will be displayed instead. Note: If you register for an "
            "event, your real first and last name will be shown to other participants, and to the "
            "organisers.",
        ),
        blank=True,
    )

    legal_name = models.CharField(
        max_length=100,
        verbose_name=_("Legal name"),
        blank=True,
        null=True,
        help_text=_(
            "If for whatever reason the first and last name shown on your documents is "
            "different from the one you prefer to use, then write it here. It will only be "
            "used for internal bureaucratic purposes, and will NEVER be displayed to other "
            "participants.",
        ),
    )

    pronoun = models.CharField(
        max_length=20,
        verbose_name=_("Pronouns"),
        help_text=_("Indicate the pronouns you wish to be used to refer to you"),
        blank=True,
        null=True,
    )

    nationality = models.CharField(
        max_length=2,
        choices=countries,
        blank=True,
        null=True,
        verbose_name=_("Nationality"),
        help_text=_("Indicate the country of which you are a citizen"),
    )

    gender = models.CharField(
        max_length=1,
        choices=GenderChoices.choices,
        default=GenderChoices.OTHER,
        verbose_name=_("Gender"),
        help_text=_("Indicates what gender you identify yourself as"),
        null=True,
    )

    phone_contact = PhoneNumberField(
        unique=True,
        verbose_name=_("Phone contact"),
        help_text=_("Remember to put the prefix at the beginning!"),
        blank=True,
        null=True,
    )

    social_contact = models.CharField(
        max_length=150,
        verbose_name=_("Contact"),
        help_text=_(
            "Indicates a way for other participants to contact you. It can be an email, a social "
            "profile, whatever you want. It will be made public to others participants",
        ),
        blank=True,
        null=True,
    )

    first_aid = models.CharField(
        max_length=1,
        choices=FirstAidChoices.choices,
        default=FirstAidChoices.NO,
        verbose_name=_("First aid"),
        help_text=_(
            "Are you a doctor, a nurse, or a licensed rescuer? We can ask you to intervene in "
            "case accidents occur during the event?",
        ),
        null=True,
    )

    birth_date = models.DateField(verbose_name=_("Birth date"), blank=True, null=True)

    birth_place = models.CharField(max_length=150, verbose_name=_("Birth place"), blank=True, null=True)

    fiscal_code = models.CharField(
        max_length=16,
        verbose_name=_("Fiscal code"),
        blank=True,
        null=True,
        help_text=_("If you are an Italian citizen, indicate your tax code; otherwise leave blank"),
    )

    document_type = models.CharField(
        max_length=1,
        choices=DocumentChoices.choices,
        default=DocumentChoices.IDENT,
        verbose_name=_("Document type"),
        null=True,
        help_text=_("Indicates a type of identification document issued by the nation in which you reside"),
    )

    document = models.CharField(
        max_length=16,
        verbose_name=_("Document number"),
        blank=True,
        null=True,
        help_text=_("Enter the number or code of the identification document indicated above"),
    )

    document_issued = models.DateField(verbose_name=_("Date of issue of the document"), blank=True, null=True)

    document_expiration = models.DateField(
        blank=True,
        null=True,
        verbose_name=_("Date of expiration of the document"),
        help_text=_(
            "Leave blank if the document has no expiration date - Please check that it does not expire before the event you want to signup up for.",
        ),
    )

    residence_address = models.CharField(
        max_length=500,
        verbose_name=_("Residence address"),
        blank=True,
        null=True,
    )

    accessibility = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name=_("Accessibility"),
        help_text=_("Fill in this field if you have accessibility needs"),
    )

    diet = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name=_("Diet"),
        help_text=_(
            "Fill in this field if you follow a personal diet for reasons of choice(e.g. "
            "vegetarian, vegan) or health (celiac disease, allergies). Leave empty if you do "
            "not have things to report!",
        ),
    )

    safety = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name=_("Safety"),
        help_text=_(
            "Fill in this field if there is something you think is important that the "
            "organizers know about you. It's up to you to decide what to share with us. This "
            "information will be treated as strictly confidential: only a restricted part of "
            "the organizers will have access to the answers, and will not be transmitted in "
            "any form. This information may concern: physical health problems, epilepsy, "
            "mental health problems (e.g. neurosis, bipolar disorder, anxiety disorder, "
            "various phobias), trigger topics ('lines and veils', we can't promise that you "
            "won't run into them in the event, but we'll make sure they're not part of your "
            "main quests). Leave empty if you do not have things to report!",
        ),
    )

    newsletter = models.CharField(
        max_length=1,
        choices=NewsletterChoices.choices,
        default=NewsletterChoices.ALL,
        verbose_name=_("Newsletter"),
        help_text=_("Do you wish to be always updated on our events") + "?",
        null=True,
    )

    profile = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("member/"),
        verbose_name=_("Portrait"),
        help_text=_(
            "Upload your portrait photo. It will be shown to other participants to help recognize "
            "you in the event. Choose a photo that you would put in an official document (in which "
            "you are alone, centered on your face)",
        ),
        blank=True,
        null=True,
    )

    profile_thumb = ImageSpecField(
        source="profile",
        processors=[ResizeToFill(500, 500)],
        format="JPEG",
        options={"quality": 90},
    )

    presentation = models.CharField(
        max_length=500,
        verbose_name=_("Presentation"),
        help_text=_("If you are a candidate for the Board, please write an introduction here!"),
        null=True,
        blank=True,
    )

    # If the member is delegated, this field will hold the parent member account
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="delegated")

    class Meta:
        ordering = ["surname", "name"]

    def __str__(self) -> str:
        if self.nickname:
            name = self.display_real()
            nick = self.nickname
            if slugify(nick) != slugify(name):
                name += f" - {nick}"
            return name
        if self.name or self.surname:
            return self.display_real()
        return str(self.user)

    def display_member(self) -> str:
        """Return a user-friendly display name for the member.

        Returns the member's display name in order of preference:
        nickname > real name > email > primary key.

        Returns:
            str: The display name for the member.

        """
        # Use nickname if available
        if self.nickname:
            return str(self.nickname)

        # Fall back to real name (first/last name combination)
        if self.name or self.surname:
            return self.display_real()

        # Use email as last resort before ID
        if self.email:
            return self.email

        # Final fallback to primary key
        return str(self.pk)

    def display_real(self) -> str:
        """Return full real name as 'name surname'."""
        return f"{self.name} {self.surname}"

    def display_profile(self) -> str:
        """Return the URL of the profile thumbnail image."""
        # noinspection PyUnresolvedReferences
        return self.profile_thumb.url

    def get_card_number(self) -> int:
        """Return the member's card number."""
        # noinspection PyUnresolvedReferences
        return self.id

    def show_nick(self) -> str:
        """Return nickname if present, otherwise the string representation."""
        if self.nickname:
            return self.nickname
        return str(self)

    def get_member_filepath(self) -> str:
        """Get the file path for member PDF storage.

        Returns:
            The absolute path to the member's PDF directory.

        """
        # Build base PDF members directory path
        member_pdf_directory = os.path.join(conf_settings.MEDIA_ROOT, "pdf/members")
        # noinspection PyUnresolvedReferences
        # Add member-specific subdirectory using ID
        member_pdf_directory = os.path.join(member_pdf_directory, str(self.id))
        # Ensure directory exists
        Path(member_pdf_directory).mkdir(parents=True, exist_ok=True)
        return member_pdf_directory

    def get_request_filepath(self):
        """Return the full file path for member request PDF."""
        return os.path.join(self.get_member_filepath(), "request.pdf")

    def join(self, association: Association) -> None:
        """Join an association if not already a member."""
        membership = get_user_membership(self, association.id)  # type: ignore[arg-type]
        if membership.status == MembershipStatus.EMPTY:
            membership.status = MembershipStatus.JOINED
            membership.save()

    def get_residence(self) -> str:
        """Return formatted residence address string or empty string if no address."""
        if not self.residence_address:
            return ""

        # Split address components by pipe delimiter
        # noinspection PyUnresolvedReferences
        address_components = self.residence_address.split("|")

        # Format: street number, city (province), country_code (country)
        return f"{address_components[4]} {address_components[5]}, {address_components[2]} ({address_components[3]}), {address_components[1].replace('IT-', '')} ({address_components[0]})"

    def get_config(self, name: str, *, default_value: Any = None, bypass_cache: bool = False):
        """Get configuration value for this member."""
        return get_element_config(self, name, default_value, bypass_cache=bypass_cache)


class MemberConfig(BaseModel):
    name = models.CharField(max_length=150)

    value = models.CharField(max_length=1000)

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="configs")

    def __str__(self) -> str:
        return f"{self.member} {self.name}"

    class Meta:
        indexes = [
            models.Index(fields=["member", "name"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["member", "name", "deleted"],
                name="unique_member_config_with_optional",
            ),
            UniqueConstraint(
                fields=["member", "name"],
                condition=Q(deleted=None),
                name="unique_member_config_without_optional",
            ),
        ]


class MembershipStatus(models.TextChoices):
    EMPTY = "e", _("Absent")
    JOINED = "j", _("Shared")
    UPLOADED = "u", _("Uploaded")
    SUBMITTED = "s", _("Submitted")
    ACCEPTED = "a", _("Accepted")
    REWOKED = "r", _("Kicked out")


class Membership(BaseModel):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="memberships")

    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="memberships")

    compiled = models.BooleanField(default=False)

    credit = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    tokens = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    status = models.CharField(
        max_length=1,
        choices=MembershipStatus.choices,
        default=MembershipStatus.EMPTY,
        db_index=True,
    )

    request = models.FileField(upload_to=UploadToPathAndRename("request/"), null=True, blank=True)

    document = models.FileField(upload_to=UploadToPathAndRename("document/"), null=True, blank=True)

    card_number = models.IntegerField(null=True, blank=True)

    date = models.DateField(blank=True, null=True)

    password_reset = models.CharField(max_length=100, blank=True, null=True)

    newsletter = models.CharField(
        max_length=1,
        choices=NewsletterChoices.choices,
        default=NewsletterChoices.ALL,
        verbose_name=_("Newsletter"),
        help_text=_("Do you wish to be always updated on our events") + "?",
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["association", "member"],
                condition=Q(deleted__isnull=True),
                name="memb_association_mem_act",
            ),
            models.Index(
                fields=["association", "status"],
                condition=Q(deleted__isnull=True),
                name="memb_association_stat_act",
            ),
        ]
        constraints = [
            UniqueConstraint(
                fields=["member", "association", "deleted"],
                name="unique_membership_number_with_optional",
            ),
            UniqueConstraint(
                fields=["member", "association"],
                condition=Q(deleted=None),
                name="unique_membership_number_without_optional",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.member} - {self.association}"

    def get_request_filepath(self):
        """Get request file path from download URL."""
        try:
            # noinspection PyUnresolvedReferences
            return download_d(self.request.url)
        except Exception as exception:
            logger.debug("Request file not available for membership %s: %s", self.id, exception)
            return ""

    def get_document_filepath(self):
        """Get document file path from download URL."""
        try:
            # noinspection PyUnresolvedReferences
            return download_d(self.document.url)
        except Exception as error:
            logger.debug("Document file not available for membership %s: %s", self.id, error)
            return ""


class VolunteerRegistry(BaseModel):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="volunteer")

    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="volunteers")

    start = models.DateField(null=True)

    end = models.DateField(blank=True, null=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["member", "association", "deleted"],
                name="unique_volunteer_registry_with_optional",
            ),
            UniqueConstraint(
                fields=["member", "association"],
                condition=Q(deleted=None),
                name="unique_volunteer_registry_without_optional",
            ),
        ]


class Badge(BaseModel):
    name = models.CharField(max_length=100, verbose_name=_("Name"), help_text=_("Short name"))

    name_eng = models.CharField(
        max_length=100,
        verbose_name=_("Name - international"),
        help_text=_("Short name - international"),
    )

    descr = models.CharField(max_length=500, verbose_name=_("Description"), help_text=_("Extended description"))

    descr_eng = models.CharField(
        max_length=500,
        verbose_name=_("Description - international"),
        help_text=_("Extended description - international"),
    )

    number = models.IntegerField(default=1)

    cod = models.CharField(
        max_length=30,
        verbose_name=_("Code"),
        help_text=_("Unique code for internal use - not visible. Indicate a string without spaces or strange symbols"),
    )

    img = models.ImageField(upload_to=UploadToPathAndRename("badge/"), blank=False)

    img_thumb = ImageSpecField(
        source="img",
        processors=[ResizeToFill(200, 200)],
        format="JPEG",
        options={"quality": 90},
    )

    members = models.ManyToManyField(Member, related_name="badges", blank=True)

    association = models.ForeignKey(Association, on_delete=models.CASCADE)

    def thumb(self) -> str:
        """Return HTML for thumbnail image if available, otherwise empty string."""
        if self.img_thumb:
            # noinspection PyUnresolvedReferences
            return show_thumb(100, self.img_thumb.url)
        return ""

    def show(self) -> dict:
        """Return a dictionary representation for display purposes.

        Args:
            lang: Language code for localization

        Returns:
            Dictionary with id, number, name, description and optional image URL

        """
        # noinspection PyUnresolvedReferences
        js = {"id": self.id, "number": self.number}

        # Add localized name and description attributes
        for s in ["name", "descr"]:
            self.upd_js_attr(js, s)

        # Add thumbnail image URL if available
        if self.img:
            # noinspection PyUnresolvedReferences
            js["img_url"] = self.img_thumb.url
        return js


class Log(BaseModel):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)

    eid = models.IntegerField()

    cls = models.CharField(max_length=100)

    dct = models.TextField()

    dl = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.cls} {self.eid}"


class Vote(BaseModel):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="votes_given")

    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="votes")

    year = models.IntegerField()

    number = models.IntegerField()

    candidate = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="votes_received")

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["member", "association", "year", "number", "deleted"],
                name="unique_vote_number_with_optional",
            ),
            UniqueConstraint(
                fields=["member", "association", "year", "number"],
                condition=Q(deleted=None),
                name="unique_vote_number_without_optional",
            ),
        ]

    def __str__(self) -> str:
        return f"V{self.number} {self.member} ({self.association} - {self.year})"


def get_user_membership(user: Member, association: Association | int) -> Membership:
    """Get or create a membership for a user in an association.

    This function first checks if the user already has a cached membership
    attribute. If not, it retrieves or creates a membership record for the
    user in the specified association.

    Args:
        user: The member object for whom to get the membership
        association: Either an Association instance or an association ID (int)

    Returns:
        The membership object for the user in the association

    Raises:
        Http404: If the association ID is invalid or not found

    """
    # Check if user already has a cached membership attribute
    if hasattr(user, "membership"):
        return user.membership

    # Extract association ID from either Association object or integer
    # noinspection PyUnresolvedReferences
    association_id = association.id if isinstance(association, Association) else association

    # Validate that we have a valid association ID
    if not association_id:
        msg = "Association not found"
        raise Http404(msg)

    # Get existing membership or create a new one for this user/association pair
    membership, _ = Membership.objects.get_or_create(member=user, association_id=association_id)

    # Cache the membership on the user object for future access
    user.membership = membership
    return membership
