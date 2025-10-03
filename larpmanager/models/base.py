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
import secrets
from datetime import datetime
from itertools import chain

from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from model_clone import CloneMixin
from pilkit.processors import ResizeToFill
from safedelete.models import SOFT_DELETE_CASCADE, SafeDeleteModel
from tinymce.models import HTMLField

from larpmanager.models.utils import UploadToPathAndRename, get_attr

AlphanumericValidator = RegexValidator(r"^[0-9a-z_-]*$", "Only characters allowed are: 0-9, a-z, _, -.")


class BaseModel(CloneMixin, SafeDeleteModel):
    created = models.DateTimeField(default=datetime.now, editable=False)

    updated = models.DateTimeField(auto_now=True)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        abstract = True
        ordering = ["-updated"]

    def upd_js_attr(self, js, nm):
        """Update JavaScript object with model attribute value.

        Args:
            js (dict): JavaScript object to update
            nm (str): Attribute name to get and set

        Returns:
            dict: Updated JavaScript object
        """
        js[nm] = get_attr(self, nm)
        return js

    def __str__(self):
        """Return string representation of the model.

        Returns:
            str: Model name, search field, or default string representation
        """
        if hasattr(self, "name"):
            return self.name
        if hasattr(self, "search") and self.search:
            return self.search
        return super().__str__()

    def get_absolute_url(self):
        """Get absolute URL for the model instance.

        Returns:
            str: URL for the event view using model slug
        """
        # noinspection PyUnresolvedReferences
        return reverse("event", kwargs={"s": self.slug})

    def small_text(self):
        """Get truncated text preview.

        Returns:
            str: First 100 characters of text field or empty string
        """
        if hasattr(self, "text"):
            return self.text[:100]
        return ""

    def as_dict(self, many_to_many=True):
        """Convert model instance to dictionary representation.

        Args:
            many_to_many (bool): Whether to include many-to-many relationships

        Returns:
            dict: Dictionary with field names as keys and values as data
        """
        # noinspection PyUnresolvedReferences
        opts = self._meta
        data = {}
        for f in chain(opts.concrete_fields, opts.private_fields):
            v = f.value_from_object(self)
            if v:
                data[f.name] = v
        if many_to_many:
            for f in opts.many_to_many:
                d = [i.id for i in f.value_from_object(self)]
                if len(d) > 0:
                    data[f.name] = d
        return data


class FeatureNationality(models.TextChoices):
    ITALY = "it", _("Italy")


class FeatureModule(BaseModel):
    name = models.CharField(max_length=100)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], db_index=True, unique=True)

    icon = models.CharField(max_length=100)

    order = models.IntegerField()

    nationality = models.CharField(max_length=2, choices=FeatureNationality.choices, blank=True, null=True)


class Feature(BaseModel):
    name = models.CharField(max_length=100)

    descr = models.TextField(max_length=500, blank=True)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], db_index=True, unique=True)

    order = models.IntegerField()

    overall = models.BooleanField(default=False)

    tutorial = models.CharField(max_length=500, blank=True)

    module = models.ForeignKey(
        FeatureModule,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="features",
    )

    after_link = models.TextField(max_length=100, blank=True, null=True)

    after_text = models.TextField(max_length=300, blank=True, null=True)

    # If the feature is a placeholder (used to indicate the permissions that does not require a true feature)
    placeholder = models.BooleanField(default=False)

    hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ["module", "order"]

    def __str__(self):
        """Return string representation of the feature.

        Returns:
            str: Feature name and module combination
        """
        return f"{self.name} - {self.module}"


class PaymentMethod(BaseModel):
    name = models.CharField(max_length=100)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], db_index=True, unique=True)

    instructions = HTMLField(blank=True, null=True)

    fields = models.CharField(max_length=500)

    profile = models.ImageField(
        max_length=500,
        upload_to=UploadToPathAndRename("payment_methods/"),
        verbose_name=_("Logo"),
        null=True,
        help_text=_("Logo image (you can upload a file of any size, it will be resized automatically)"),
    )

    profile_thumb = ImageSpecField(
        source="profile",
        processors=[ResizeToFill(100, 100)],
        format="JPEG",
        options={"quality": 90},
    )

    def as_dict(self, **kwargs):
        """Convert payment method to dictionary with profile image.

        Args:
            **kwargs: Additional keyword arguments

        Returns:
            dict: Payment method data with slug, name, and optional profile URL
        """
        # noinspection PyUnresolvedReferences
        return {"slug": self.slug, "name": self.name, **({"profile": self.profile_thumb.url} if self.profile else {})}


class PublisherApiKey(BaseModel):
    name = models.CharField(max_length=100, help_text=_("Descriptive name for this API key"))

    key = models.CharField(max_length=64, unique=True, db_index=True, editable=False)

    active = models.BooleanField(default=True)

    last_used = models.DateTimeField(blank=True, null=True)

    usage_count = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({'Active' if self.active else 'Inactive'})"
