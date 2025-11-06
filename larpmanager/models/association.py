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
from typing import Any

from babel.numbers import get_currency_symbol
from colorfield.fields import ColorField
from django.conf import settings as conf_settings
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from pilkit.processors import ResizeToFill, ResizeToFit
from tinymce.models import HTMLField

from larpmanager.cache.config import get_element_config
from larpmanager.models.base import AlphanumericValidator, BaseModel, Feature, FeatureNationality, PaymentMethod
from larpmanager.models.utils import UploadToPathAndRename
from larpmanager.utils.validators import FileTypeValidator


class MemberFieldType(models.TextChoices):
    ABSENT = "a", _("Absent")
    OPTIONAL = "o", _("Optional")
    MANDATORY = "m", _("Mandatory")


class Currency(models.TextChoices):
    EUR = "e", "EUR"
    USD = "u", "USD"
    GBP = "g", "GBP"
    CAD = "c", "CAD"
    JPY = "j", "JPY"


class AssociationPlan(models.TextChoices):
    FREE = "f", _("Free")
    SUPPORT = "p", _("Support")


class AssociationSkin(BaseModel):
    name = models.CharField(max_length=100)

    domain = models.CharField(max_length=100)

    default_features = models.ManyToManyField(Feature, related_name="skins", blank=True)

    default_mandatory_fields = models.CharField(max_length=1000, blank=True)

    default_optional_fields = models.CharField(max_length=1000, blank=True)

    default_css = models.CharField(max_length=1000, blank=True)

    default_nation = models.CharField(
        max_length=2,
        choices=FeatureNationality.choices,
        blank=True,
        null=True,
    )

    managed = models.BooleanField(default=False)


class Association(BaseModel):
    skin = models.ForeignKey(AssociationSkin, on_delete=models.CASCADE, default=1)

    name = models.CharField(max_length=100, help_text=_("Complete name of the Organization"))

    slug = models.CharField(
        max_length=20,
        verbose_name=_("URL identifier"),
        help_text=_("The subdomain identifier")
        + " - "
        + _("Only lowercase characters and numbers are allowed, no spaces or symbols"),
        validators=[AlphanumericValidator],
        db_index=True,
    )

    activated = models.DateTimeField(auto_now_add=True, null=True)

    profile = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("association/"),
        verbose_name=_("Logo"),
        null=True,
        blank=True,
        help_text=_("Optional logo image - you can upload a file of any size, it will be automatically resized"),
    )

    profile_thumb = ImageSpecField(
        source="profile",
        processors=[ResizeToFill(200, 200)],
        format="JPEG",
        options={"quality": 90},
    )

    profile_fav = ImageSpecField(
        source="profile",
        processors=[ResizeToFill(64, 64)],
        format="JPEG",
        options={"quality": 90},
    )

    main_mail = models.EmailField(
        blank=True,
        null=True,
        help_text="(" + _("Optional") + ") " + _("Indicate an organization contact address for sending communications"),
    )

    mandatory_fields = models.CharField(max_length=1000, blank=True)

    optional_fields = models.CharField(max_length=1000, blank=True)

    payment_methods = models.ManyToManyField(
        PaymentMethod,
        related_name="associations_payments",
        blank=True,
        verbose_name=_("Payment Methods"),
        help_text=_("Indicate the payment methods you wish to be available to participants"),
    )

    payment_currency = models.CharField(
        max_length=1,
        choices=Currency.choices,
        default=Currency.EUR,
        blank=True,
        null=True,
        verbose_name=_("Payment currency"),
        help_text=_("Indicates the currency in which to receive payments"),
    )

    promoter = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("promot/"),
        null=True,
        blank=True,
        help_text=_("Image shown on homepage as promoter"),
    )

    promoter_thumb = ImageSpecField(
        source="promoter",
        processors=[ResizeToFit(height=200)],
        format="JPEG",
        options={"quality": 90},
    )

    features = models.ManyToManyField(Feature, related_name="associations", blank=True)

    background = models.ImageField(
        max_length=500,
        upload_to="association_background/",
        verbose_name=_("Background image"),
        blank=True,
        help_text=_("Background of web pages"),
    )

    background_red = ImageSpecField(
        source="background",
        processors=[ResizeToFit(width=1000)],
        format="JPEG",
        options={"quality": 80},
    )

    font = models.FileField(
        upload_to=UploadToPathAndRename("association_font/"),
        verbose_name=_("Title font"),
        help_text=_("Font to be used in page titles"),
        blank=True,
        null=True,
        validators=[
            FileTypeValidator(
                [
                    "font/ttf",
                    "font/otf",
                    "application/font-woff",
                    "application/font-woff2",
                    "font/woff",
                    "font/woff2",
                    "font/sfnt",
                ]
            )
        ],
    )

    css_code = models.CharField(max_length=32, editable=False, default="")

    pri_rgb = ColorField(
        verbose_name=_("Color texts"),
        help_text=_("Indicate the color that will be used for the texts"),
        blank=True,
        null=True,
    )

    sec_rgb = ColorField(
        verbose_name=_("Color highlight"),
        help_text=_("Indicate the color that will be used to highlight texts"),
        blank=True,
        null=True,
    )

    ter_rgb = ColorField(
        verbose_name=_("Color links"),
        help_text=_("Indicate the color that will be used for the links"),
        blank=True,
        null=True,
    )

    plan = models.CharField(max_length=1, choices=AssociationPlan.choices, default=AssociationPlan.FREE)

    gdpr_contract = models.FileField(
        upload_to=UploadToPathAndRename("contract/gdpr/"),
        null=True,
        blank=True,
        validators=[FileTypeValidator(["application/pdf"])],
    )

    review_done = models.BooleanField(default=False)

    images_shared = models.BooleanField(default=False)

    # payment setting key file
    key = models.BinaryField(null=True)

    nationality = models.CharField(
        max_length=2,
        choices=FeatureNationality.choices,
        blank=True,
        null=True,
        default="",
        verbose_name=_("Nationality"),
        help_text="("
        + _("Optional")
        + ") "
        + _("Indicate the organization nationality to activate nation-specific features"),
    )

    demo = models.BooleanField(default=False)

    maintainers = models.ManyToManyField(
        "larpmanager.Member",
        related_name="maintained_associations",
        blank=True,
        verbose_name=_("Maintainers"),
        help_text=_("Users who can manage support tickets and receive ticket notifications"),
    )

    class Meta:
        constraints = [
            UniqueConstraint(fields=["slug", "deleted"], name="unique_association_with_optional"),
            UniqueConstraint(
                fields=["slug"],
                condition=Q(deleted=None),
                name="unique_association_without_optional",
            ),
        ]

    def get_currency_symbol(self) -> str:
        """Return the currency symbol for the payment currency."""
        # noinspection PyUnresolvedReferences
        return get_currency_symbol(self.get_payment_currency_display())

    def get_config(self, name, default_value=None, bypass_cache=False):
        return get_element_config(self, name, default_value, bypass_cache)

    def promoter_dict(self) -> dict[str, str]:
        """Return a dictionary with promoter information including slug, name, and optional thumbnail URL."""
        promoter_data = {"slug": self.slug, "name": self.name}

        # Add thumbnail URL if available
        if self.promoter_thumb:
            # noinspection PyUnresolvedReferences
            promoter_data["promoter_url"] = self.promoter_thumb.url
        return promoter_data


class AssociationConfig(BaseModel):
    name = models.CharField(max_length=150)

    value = models.CharField(max_length=1000)

    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="configs")

    def __str__(self):
        return f"{self.association} {self.name}"

    class Meta:
        indexes = [
            models.Index(fields=["association", "name"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["association", "name", "deleted"],
                name="unique_association_config_with_optional",
            ),
            UniqueConstraint(
                fields=["association", "name"],
                condition=Q(deleted=None),
                name="unique_association_config_without_optional",
            ),
        ]


class AssociationTextType(models.TextChoices):
    PROFILE = "p", _("Profile")
    HOME = "h", _("Home")
    SIGNUP = "u", _("Registration mail")
    MEMBERSHIP = "m", _("Membership")
    STATUTE = "s", _("Statute")
    LEGAL = "l", _("Legal notice")
    FOOTER = "f", _("Footer")
    TOC = "t", _("Terms and Conditions")
    RECEIPT = "r", _("Receipt")
    SIGNATURE = "g", _("Mail signature")
    PRIVACY = "y", _("Privacy")

    REMINDER_MEMBERSHIP = "rm", _("Reminder membership request")
    REMINDER_MEMBERSHIP_FEE = "rf", _("Reminder membership fee")
    REMINDER_PAY = "rp", _("Reminder payment")
    REMINDER_PROFILE = "rr", _("Reminder profile")


class AssociationText(BaseModel):
    number = models.IntegerField(null=True, blank=True)

    text = HTMLField(blank=True, null=True)

    typ = models.CharField(
        max_length=2, choices=AssociationTextType.choices, verbose_name=_("Type"), help_text=_("Type of text")
    )

    language = models.CharField(
        max_length=3,
        choices=conf_settings.LANGUAGES,
        default="en",
        null=True,
        verbose_name=_("Language"),
        help_text=_("Text language"),
    )

    default = models.BooleanField(default=True)

    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="texts")

    def __str__(self) -> str:
        """Return string representation combining type and language displays."""
        # noinspection PyUnresolvedReferences
        return f"{self.get_typ_display()} {self.get_language_display()}"

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["association", "typ", "language", "deleted"],
                name="unique_association_text_with_optional",
            ),
            UniqueConstraint(
                fields=["association", "typ", "language"],
                condition=Q(deleted=None),
                name="nique_association_text_without_optional",
            ),
        ]


class AssociationTranslation(BaseModel):
    """Per-organization custom translation overrides for Django i18n strings.

    This model enables multi-tenant translation customization, allowing each
    association/organization to override specific Django translation strings
    without modifying the global .po files. These custom translations are
    injected at request time via the AssociationTranslationMiddleware.

    The model follows the gettext convention:
    - msgid: The original English text that appears in the code
    - msgstr: The custom translation for this organization
    - context: Optional msgctxt for disambiguating identical strings

    Use cases:
    - Organizations wanting different terminology (e.g., "Character" vs "Hero")
    - Regional variations within the same language
    - Brand-specific vocabulary customization

    The active flag allows temporarily disabling translations without deletion,
    and the unique constraints ensure no duplicate translations exist for the
    same msgid/context/language combination within an association.
    """

    number = models.IntegerField(
        null=True, blank=True, verbose_name=_("Number"), help_text=_("Optional ordering number")
    )

    association = models.ForeignKey(
        Association,
        on_delete=models.CASCADE,
        related_name="custom_translations",
        verbose_name=_("Association"),
        help_text=_("The organization this translation belongs to"),
    )

    language = models.CharField(
        max_length=3,
        choices=conf_settings.LANGUAGES,
        verbose_name=_("Language"),
        help_text=_("ISO language code (e.g., 'en', 'it', 'de')"),
    )

    msgid = models.TextField(
        verbose_name=_("Original text"),
        help_text=_("The original English text as it appears in the code (msgid in gettext)"),
        db_index=True,
    )

    msgstr = models.TextField(
        verbose_name=_("Translated text"),
        help_text=_("The custom translation that will replace the default for this organization"),
    )

    context = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("Context"),
        help_text=_("Optional context for disambiguation when the same text has different meanings (msgctxt)"),
    )

    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Whether this translation override is currently active. Inactive translations are ignored."),
    )

    def __str__(self) -> str:
        """Return a human-readable string representation of the translation.

        Returns:
            A formatted string showing association, language, and truncated original text
        """
        return f"{self.association.name} - {self.get_language_display()}: {self.msgid[:50]}"

    class Meta:
        constraints = [
            # Ensure unique translations including soft-deleted records
            UniqueConstraint(
                fields=["association", "language", "msgid", "context", "deleted"],
                name="unique_assoc_translation_with_deleted",
            ),
            # Ensure unique translations for active records only
            UniqueConstraint(
                fields=["association", "language", "msgid", "context"],
                condition=Q(deleted=None),
                name="unique_assoc_translation_without_deleted",
            ),
        ]
        indexes = [
            # Composite index for fast translation lookups
            models.Index(fields=["association", "language", "msgid"]),
            # Index for filtering active/inactive translations
            models.Index(fields=["active"]),
        ]
        verbose_name = _("Association Translation")
        verbose_name_plural = _("Association Translations")


def hdr(association_or_related_object: Association | Any) -> str:
    """Return a formatted header string with the association name in brackets."""
    # Check if object is an Association instance directly
    if isinstance(association_or_related_object, Association):
        return f"[{association_or_related_object.name}] "
    # Check if object has an associated Association via association attribute
    if association_or_related_object.association:
        return f"[{association_or_related_object.association.name}] "
    else:
        return "[LarpManager] "


def get_association_maintainers(association: Association):
    """Get all maintainers for an association.

    Args:
        association: Association instance

    Returns:
        QuerySet of Member instances who are maintainers for this association
    """
    return association.maintainers.all()


def get_url(path: str, obj: object = None) -> str:
    """Generate a URL for the given path and object.

    Constructs URLs based on the type of object provided. For Association objects,
    uses the association's slug and domain. For objects with an 'association' attribute,
    uses the associated organization's slug and domain. Falls back to default
    larpmanager.com domain when no object is provided.

    Args:
        path: The path/route to append to the base URL
        obj: Optional object to determine the base URL. Can be Association,
             an object with 'association' attribute, or a string slug

    Returns:
        Complete URL string with proper protocol formatting
    """
    if obj:
        # Handle Association objects directly
        if isinstance(obj, Association):
            url = f"https://{obj.slug}.{obj.skin.domain}/{path}"
        # Handle objects that belong to an association
        elif hasattr(obj, "association"):
            url = f"https://{obj.association.slug}.{obj.association.skin.domain}/{path}"
        # Handle string slugs or other objects
        else:
            url = f"https://{obj}.larpmanager.com/{path}"
    else:
        # Default to main larpmanager.com domain
        url = "https://larpmanager.com/" + path

    # Clean up double slashes while preserving protocol
    return url.replace("//", "/").replace(":/", "://")
