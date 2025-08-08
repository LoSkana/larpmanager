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
from larpmanager.models.larpmanager import LarpManagerPlan
from larpmanager.models.utils import UploadToPathAndRename


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
        upload_to="assoc_background/",
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
        upload_to=UploadToPathAndRename("assoc_font/"),
        verbose_name=_("Title font"),
        help_text=_("Font to be used in page titles"),
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

    plan = models.CharField(max_length=1, choices=LarpManagerPlan.choices, default=LarpManagerPlan.FREE)

    gdpr_contract = models.FileField(upload_to=UploadToPathAndRename("contract/gdpr/"), null=True, blank=True)

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

    class Meta:
        constraints = [
            UniqueConstraint(fields=["slug", "deleted"], name="unique_association_with_optional"),
            UniqueConstraint(
                fields=["slug"],
                condition=Q(deleted=None),
                name="unique_association_without_optional",
            ),
        ]

    def get_currency_symbol(self):
        # noinspection PyUnresolvedReferences
        return get_currency_symbol(self.get_payment_currency_display())

    def get_config(self, name, def_v=None):
        return get_element_config(self, name, def_v)

    def promoter_dict(self):
        res = {"slug": self.slug, "name": self.name}
        if self.promoter_thumb:
            # noinspection PyUnresolvedReferences
            res["promoter_url"] = self.promoter_thumb.url
        return res


class AssociationConfig(BaseModel):
    name = models.CharField(max_length=150)

    value = models.CharField(max_length=1000)

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="configs")

    def __str__(self):
        return f"{self.assoc} {self.name}"

    class Meta:
        indexes = [
            models.Index(fields=["assoc", "name"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["assoc", "name", "deleted"],
                name="unique_assoc_config_with_optional",
            ),
            UniqueConstraint(
                fields=["assoc", "name"],
                condition=Q(deleted=None),
                name="unique_assoc_config_without_optional",
            ),
        ]


class AssocTextType(models.TextChoices):
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


class AssocText(BaseModel):
    number = models.IntegerField(null=True, blank=True)

    text = HTMLField(blank=True, null=True)

    typ = models.CharField(
        max_length=2, choices=AssocTextType.choices, verbose_name=_("Type"), help_text=_("Type of text")
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

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="texts")

    def __str__(self):
        # noinspection PyUnresolvedReferences
        return f"{self.get_typ_display()} {self.get_language_display()}"

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["assoc", "typ", "language", "deleted"],
                name="unique_assoc_text_with_optional",
            ),
            UniqueConstraint(
                fields=["assoc", "typ", "language"],
                condition=Q(deleted=None),
                name="nique_assoc_text_without_optional",
            ),
        ]


def hdr(obj):
    if isinstance(obj, Association):
        return f"[{obj.name}] "
    if obj.assoc:
        return f"[{obj.assoc.name}] "
    else:
        return "[LarpManager] "


def get_url(s, obj=None):
    if obj:
        if isinstance(obj, Association):
            url = f"https://{obj.slug}.{obj.skin.domain}/{s}"
        elif hasattr(obj, "assoc"):
            url = f"https://{obj.assoc.slug}.{obj.assoc.skin.domain}/{s}"
        else:
            url = f"https://{obj}.larpmanager.com/{s}"
    else:
        url = "https://larpmanager.com/" + s

    return url.replace("//", "/").replace(":/", "://")
