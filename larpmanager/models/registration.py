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

from typing import Any, ClassVar

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.constraints import UniqueConstraint
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill
from tinymce.models import HTMLField

from larpmanager.models.base import BaseModel, UuidMixin
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member
from larpmanager.models.utils import UploadToPathAndRename
from larpmanager.models.writing import Character


class TicketTier(models.TextChoices):
    """Represents TicketTier model."""

    STANDARD = "b", _("Standard")
    NEW_PLAYER = "y", _("New player")
    LOTTERY = "l", _("Lottery")
    WAITING = "w", _("Waiting")
    FILLER = "f", _("Filler")
    REDUCED = "r", _("Reduced")
    PATRON = "p", _("Patron")
    STAFF = "t", _("Staff")
    NPC = "n", _("NPC")
    COLLABORATOR = "c", _("Collaborator")
    SELLER = "s", _("Seller")

    @classmethod
    def get_mapping(cls) -> Any:
        """Return mapping of ticket tier values to string identifiers."""
        return {
            TicketTier.STANDARD: "Standard",
            TicketTier.NEW_PLAYER: "New player",
            TicketTier.LOTTERY: "Lottery",
            TicketTier.WAITING: "Waiting",
            TicketTier.FILLER: "Filler",
            TicketTier.REDUCED: "Reduced",
            TicketTier.PATRON: "Patron",
            TicketTier.STAFF: "Staff",
            TicketTier.NPC: "NPC",
            TicketTier.COLLABORATOR: "Collaborator",
            TicketTier.SELLER: "Seller",
        }


class RegistrationTicket(UuidMixin, BaseModel):
    """Represents RegistrationTicket model."""

    search = models.CharField(max_length=150, editable=False)

    number = models.IntegerField()

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="tickets")

    tier = models.CharField(
        max_length=1,
        choices=TicketTier.choices,
        default=TicketTier.STANDARD,
        verbose_name=_("Tier"),
        help_text=_("Type of ticket"),
    )

    name = models.CharField(
        max_length=50,
        verbose_name=_("Name"),
        help_text=_("Ticket name (keep it short)"),
    )

    description = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("Description"),
        help_text=_("Optional - Extended description (displayed in small gray text)"),
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Price"),
        help_text=_("Ticket price"),
    )

    max_available = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Total availability"),
        help_text=_("Optional - Maximum number of times it can be requested across all signups (0 = unlimited)"),
    )

    visible = models.BooleanField(
        default=True,
        verbose_name=_("Visible"),
        help_text=_("Is it selectable by participants") + "?",
    )

    casting_priority = models.IntegerField(
        default=1,
        verbose_name=_("Casting priority"),
        help_text=_("Optional - Casting priority granted by this option (e.g., 1 = low, 5 = medium, 25 = high)"),
    )

    giftable = models.BooleanField(
        default=False,
        verbose_name=_("Giftable"),
        help_text=_("Optional - Indicates whether the ticket can be gifted to other participants"),
    )

    order = models.IntegerField(default=0, verbose_name=_("Order"), help_text=_("Display order"))

    def __str__(self) -> str:
        """Return ticket tier string representation with event, tier, name and price."""
        # noinspection PyUnresolvedReferences
        return (
            f"{self.event.name} ({self.get_tier_display()}) {self.name} "
            f"({self.price}{self.event.association.get_currency_symbol()})"
        )

    def show(self) -> dict[str, Any]:
        """Return JSON representation of ticket tier with availability and attributes."""
        js = {"max_available": self.max_available}
        # Update JSON with name, price, and description attributes
        for s in ["name", "price", "description"]:
            self.upd_js_attr(js, s)
        return js

    def get_price(self) -> Any:
        """Return the tier price."""
        return self.price


class RegistrationSection(UuidMixin, BaseModel):
    """Represents RegistrationSection model."""

    search = models.CharField(max_length=1000, editable=False)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="sections")

    name = models.CharField(max_length=100, help_text=_("Name"))

    description = HTMLField(
        max_length=5000,
        blank=True,
        null=True,
        verbose_name=_("Description"),
        help_text=_("Description - will be displayed at the beginning of the section"),
    )

    order = models.IntegerField(default=0)

    def __str__(self) -> str:
        """Return string representation of the registration section."""
        return self.name


class RegistrationQuota(UuidMixin, BaseModel):
    """Represents RegistrationQuota model."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="quotas")

    number = models.IntegerField()

    quotas = models.IntegerField(verbose_name=_("Quotas"), help_text=_("Quotas total number"))

    days_available = models.IntegerField(
        verbose_name=_("Days available"),
        help_text=_("Minimum number of days before the event for which it is made available (0  = always)"),
    )

    surcharge = models.IntegerField(
        default=0,
        verbose_name=_("Surcharge"),
        help_text=_("Extra price applied when this quota is active"),
    )

    class Meta:
        ordering: ClassVar[list] = ["-created"]
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_registraion_quota_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_registraion_quota_without_optional",
            ),
        ]

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.quotas} {self.days_available} ({self.surcharge}€)"


class RegistrationInstallment(UuidMixin, BaseModel):
    """Represents RegistrationInstallment model."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="installments")

    number = models.IntegerField()

    order = models.IntegerField(help_text=_("Payment order"))

    amount = models.IntegerField(
        verbose_name=_("Amount"),
        help_text=_("Total amount of payment to be received by this date (0 = all outstanding)"),
    )

    days_deadline = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Days deadline"),
        help_text=_(
            "Deadline in the measure of days from enrollment (fill in one between the fixed "
            "deadline and the deadline in days)",
        ),
    )

    date_deadline = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date deadline"),
        help_text=_("Deadline date"),
    )

    tickets = models.ManyToManyField(
        RegistrationTicket,
        related_name="installments",
        blank=True,
        verbose_name=_("Tickets"),
        help_text=_("Indicate the tickets for which it is active"),
    )

    class Meta:
        ordering: ClassVar[list] = ["-created"]
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_registration_installment_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_registration_installment_without_optional",
            ),
        ]

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.order} {self.amount} ({self.days_deadline} - {self.date_deadline})"


class RegistrationSurcharge(UuidMixin, BaseModel):
    """Represents RegistrationSurcharge model."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="surcharges")

    number = models.IntegerField()

    amount = models.IntegerField(verbose_name=_("Amount"), help_text=_("Surcharge applied to the ticket"))

    date = models.DateField(verbose_name=_("Date"), help_text=_("Date from when the surcharge is applied"))

    class Meta:
        ordering: ClassVar[list] = ["-created"]
        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_registration_surcharge_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_registration_surcharge_without_optional",
            ),
        ]

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.amount} ({self.date})"


class Registration(UuidMixin, BaseModel):
    """Represents Registration model."""

    search = models.CharField(max_length=150, editable=False)

    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="registrations")

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="registrations")

    quotas = models.IntegerField(default=1)

    ticket = models.ForeignKey(
        RegistrationTicket,
        on_delete=models.CASCADE,
        related_name="registrations",
        null=True,
    )

    additionals = models.IntegerField(
        default=0,
        verbose_name=_("Additionals"),
        help_text=_("Number of additional participants"),
    )

    pay_what = models.IntegerField(
        default=0,
        verbose_name=_("Donation"),
        help_text=_("Donation amount chosen by the participant"),
    )

    num_payments = models.IntegerField(default=1)

    tot_payed = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    tot_iscr = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    quota = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    alert = models.BooleanField(default=False)

    deadline = models.IntegerField(default=0)

    cancellation_date = models.DateTimeField(null=True, blank=True)

    surcharge = models.IntegerField(default=0)

    refunded = models.BooleanField(default=False)

    modified = models.IntegerField(default=0)

    redeem_code = models.CharField(max_length=16, null=True, blank=True)

    # Date when first full payment is detected
    payment_date = models.DateTimeField(null=True, blank=True)

    characters = models.ManyToManyField(
        Character,
        related_name="multi_registrations",
        blank=True,
        through="RegistrationCharacterRel",
        verbose_name=_("Characters"),
    )

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.run} - {self.member}"

    def display_run(self) -> Any:
        """Return string representation of the associated run."""
        return str(self.run)

    def display_member(self) -> str:
        """Delegate to member's display method."""
        # noinspection PyUnresolvedReferences
        return self.member.display_member()

    def display_profile(self) -> str:
        """Delegate to member's profile display method."""
        # noinspection PyUnresolvedReferences
        return self.member.display_profile()

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["run", "member", "cancellation_date"]),
            models.Index(
                fields=["member", "run", "cancellation_date", "redeem_code"],
                condition=Q(deleted__isnull=True),
                name="reg_mem_run_canc_red_act",
            ),
            models.Index(fields=["run"], condition=Q(deleted__isnull=True), name="reg_run_act"),
            # Index for active registrations with specific member and run (Query 1)
            models.Index(
                fields=["member", "run", "redeem_code"],
                condition=Q(deleted__isnull=True, cancellation_date__isnull=True),
                name="reg_mem_run_red_active",
            ),
            # Index for active registrations by run (Query 2)
            models.Index(
                fields=["run"],
                condition=Q(deleted__isnull=True, cancellation_date__isnull=True),
                name="reg_run_active_only",
            ),
            # Performance indexes from migration 0137
            models.Index(
                fields=["cancellation_date"],
                name="reg_cancel_date_idx",
                condition=Q(cancellation_date__isnull=False),
            ),
            models.Index(
                fields=["refunded"],
                name="reg_refunded_idx",
                condition=Q(refunded=True),
            ),
            models.Index(
                fields=["run", "cancellation_date"],
                name="reg_run_cancel_idx",
            ),
        ]

        ordering: ClassVar[list] = ["-created"]

        constraints: ClassVar[list] = [
            UniqueConstraint(
                fields=["run", "member", "cancellation_date", "redeem_code", "deleted"],
                name="unique_registraion_with_optional",
            ),
            UniqueConstraint(
                fields=["run", "member", "redeem_code", "cancellation_date"],
                condition=Q(deleted=None),
                name="unique_registraion_without_optional",
            ),
        ]


class RegistrationCharacterRel(BaseModel):
    """Represents RegistrationCharacterRel model."""

    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name="rcrs")

    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="rcrs")

    custom_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name=_("Character name"),
        help_text=_(
            "Specify your custom character name (depending on the event you can choose the "
            "name, or adapt the name to your chosen gender)",
        ),
    )

    custom_pronoun = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        verbose_name=_("Pronoun"),
        help_text=_("If you wish, indicate a pronoun for your character"),
    )

    custom_song = models.URLField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("Song"),
        help_text=_("Indicate a song you want to dedicate to your character"),
    )

    custom_public = models.TextField(
        max_length=5000,
        blank=True,
        null=True,
        verbose_name=_("Public"),
        help_text=_("Indicates public information about your character, which will be shown to all other participants"),
    )

    custom_private = models.TextField(
        max_length=5000,
        blank=True,
        null=True,
        verbose_name=_("Private"),
        help_text=_(
            "Indicates public information about your character, which will be shown only to you and the organizers",
        ),
    )

    custom_profile = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("registration/"),
        verbose_name=_("Character portrait"),
        help_text=_("Optional: upload a photo of yourself associated with your character specifically for this event!"),
        null=True,
        blank=True,
    )

    profile_thumb = ImageSpecField(
        source="custom_profile",
        processors=[ResizeToFill(500, 500)],
        format="JPEG",
        options={"quality": 90},
    )
