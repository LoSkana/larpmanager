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

from typing import Any

from django.db import models
from django.db.models import Q
from django.db.models.constraints import UniqueConstraint
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill
from tinymce.models import HTMLField

from larpmanager.models.base import BaseModel
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member
from larpmanager.models.utils import UploadToPathAndRename, decimal_to_str, my_uuid_short
from larpmanager.models.writing import Character


class TicketTier(models.TextChoices):
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
    def get_mapping(cls):
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


class RegistrationTicket(BaseModel):
    search = models.CharField(max_length=150, editable=False)

    number = models.IntegerField()

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="tickets")

    tier = models.CharField(
        max_length=1,
        choices=TicketTier.choices,
        default=TicketTier.STANDARD,
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

    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    max_available = models.IntegerField(
        default=0,
        help_text=_("Optional - Maximum number of times it can be requested across all signups (0 = unlimited)"),
    )

    visible = models.BooleanField(default=True, help_text=_("Is it selectable by participants") + "?")

    casting_priority = models.IntegerField(
        default=1,
        help_text=_("Optional - Casting priority granted by this option (e.g., 1 = low, 5 = medium, 25 = high)"),
    )

    giftable = models.BooleanField(
        default=False,
        help_text=_("Optional - Indicates whether the ticket can be gifted to other participants"),
    )

    order = models.IntegerField(default=0)

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

    def get_price(self):
        """Return the tier price."""
        return self.price

    def get_form_text(self, run: Run = None, currency_symbol: str | None = None) -> str:
        """Generate formatted text representation for form display.

        Creates a text string combining the ticket name, price (if available),
        and availability count (if the ticket has an available attribute).

        Args:
            run: Optional run parameter passed to show method
            currency_symbol: Currency symbol string. If not provided, will be fetched
                from the event's association

        Returns:
            Formatted string containing ticket information for display

        """
        # Get ticket display information from show method
        ticket_data = self.show(run)
        formatted_text = ticket_data["name"]

        # Add price information if available
        if ticket_data["price"]:
            if not currency_symbol:
                # noinspection PyUnresolvedReferences
                currency_symbol = self.event.association.get_currency_symbol()
            formatted_text += f" - {decimal_to_str(ticket_data['price'])}{currency_symbol}"

        # Add availability count if ticket has available attribute
        if hasattr(self, "available"):
            formatted_text += f" - ({_('Available')}: {self.available})"

        return formatted_text


class RegistrationSection(BaseModel):
    search = models.CharField(max_length=1000, editable=False)

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="sections")

    name = models.CharField(max_length=100, help_text=_("Text"))

    description = HTMLField(
        max_length=5000,
        blank=True,
        null=True,
        help_text=_("Description - will be displayed at the beginning of the section"),
    )

    order = models.IntegerField(default=0)


class RegistrationQuota(BaseModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="quotas")

    number = models.IntegerField()

    quotas = models.IntegerField(help_text=_("Quotas total number"))

    days_available = models.IntegerField(
        help_text=_("Minimum number of days before the event for which it is made available (0  = always)"),
    )

    surcharge = models.IntegerField(default=0)

    class Meta:
        ordering = ["-created"]
        constraints = [
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
        return f"{self.quotas} {self.days_available} ({self.surcharge}€)"


class RegistrationInstallment(BaseModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="installments")

    number = models.IntegerField()

    order = models.IntegerField(help_text=_("Payment order"))

    amount = models.IntegerField(
        help_text=_("Total amount of payment to be received by this date (0 = all outstanding)"),
    )

    days_deadline = models.IntegerField(
        null=True,
        blank=True,
        help_text=_(
            "Deadline in the measure of days from enrollment (fill in one between the fixed "
            "deadline and the deadline in days)",
        ),
    )

    date_deadline = models.DateField(null=True, blank=True, help_text=_("Deadline date"))

    tickets = models.ManyToManyField(
        RegistrationTicket,
        related_name="installments",
        blank=True,
        help_text=_("Indicate the tickets for which it is active"),
    )

    class Meta:
        ordering = ["-created"]
        constraints = [
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
        return f"{self.order} {self.amount} ({self.days_deadline} - {self.date_deadline})"


class RegistrationSurcharge(BaseModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="surcharges")

    number = models.IntegerField()

    amount = models.IntegerField(help_text=_("Surcharge applied to the ticket"))

    date = models.DateField(help_text=_("Date from when the surcharge is applied"))

    class Meta:
        ordering = ["-created"]
        constraints = [
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
        return f"{self.amount} ({self.date})"


class Registration(BaseModel):
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

    additionals = models.IntegerField(default=0)

    pay_what = models.IntegerField(default=0)

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

    special_cod = models.CharField(
        max_length=12,
        verbose_name=_("Unique code"),
        unique=True,
        default=my_uuid_short,
        db_index=True,
    )

    redeem_code = models.CharField(max_length=16, null=True, blank=True)

    # Date when first full payment is detected
    payment_date = models.DateTimeField(null=True, blank=True)

    characters = models.ManyToManyField(
        Character,
        related_name="multi_registrations",
        blank=True,
        through="RegistrationCharacterRel",
    )

    def __str__(self) -> str:
        return f"{self.run} - {self.member}"

    def display_run(self):
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
        indexes = [
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
        ]

        ordering = ["-created"]

        constraints = [
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
    reg = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name="rcrs")

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
