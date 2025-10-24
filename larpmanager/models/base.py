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
from typing import Any

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Max
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

    def upd_js_attr(self, javascript_object: dict, attribute_name: str) -> dict:
        """Update JavaScript object with model attribute value.

        Retrieves the value of the specified attribute from the model instance
        and adds it to the provided JavaScript object dictionary.

        Args:
            javascript_object: JavaScript object dictionary to update
            attribute_name: Name of the model attribute to retrieve and add

        Returns:
            Updated JavaScript object dictionary with the new attribute

        Example:
            >>> obj.upd_js_attr({'existing': 'value'}, 'name')
            {'existing': 'value', 'name': 'John'}
        """
        # Get attribute value from model instance and add to JS object
        javascript_object[attribute_name] = get_attr(self, attribute_name)
        return javascript_object

    def __str__(self) -> str:
        """Return string representation of the model.

        Returns string representation based on model attributes in order of preference:
        1. 'name' attribute if present
        2. 'search' attribute if present and truthy
        3. Parent class string representation as fallback

        Returns:
            str: Model name, search field, or default string representation.
        """
        # Check for 'name' attribute first - most common display field
        if hasattr(self, "name"):
            return self.name

        # Fall back to 'search' attribute if it exists and has a value
        if hasattr(self, "search") and self.search:
            return self.search

        # Use parent class implementation as final fallback
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

    def as_dict(self, many_to_many: bool = True) -> dict[str, any]:
        """Convert model instance to dictionary representation.

        This method serializes a Django model instance into a dictionary format,
        optionally including many-to-many relationship data as lists of IDs.

        Args:
            many_to_many: Whether to include many-to-many relationships in the
                output dictionary. Defaults to True.

        Returns:
            A dictionary with field names as keys and field values as data.
            Many-to-many fields are represented as lists of related object IDs.

        Example:
            >>> instance = MyModel.objects.get(id=1)
            >>> data = instance.as_dict()
            >>> print(data)
            {'id': 1, 'name': 'example', 'tags': [1, 2, 3]}
        """
        # Get model metadata for field introspection
        # noinspection PyUnresolvedReferences
        model_options = self._meta
        serialized_data = {}

        # Process concrete and private fields (standard model fields)
        # Extract field values using Django's field value accessor
        for field in chain(model_options.concrete_fields, model_options.private_fields):
            field_value = field.value_from_object(self)
            # Only include fields with truthy values to keep dict clean
            if field_value:
                serialized_data[field.name] = field_value

        # Process many-to-many relationships if requested
        if many_to_many:
            # Iterate through all many-to-many field definitions
            for m2m_field in model_options.many_to_many:
                # Extract IDs from related objects for serialization
                # Convert queryset to list of primary key values
                related_ids = [related_obj.id for related_obj in m2m_field.value_from_object(self)]
                # Only include non-empty relationship lists
                if len(related_ids) > 0:
                    serialized_data[m2m_field.name] = related_ids

        return serialized_data


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

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate a secure random key if one doesn't exist, then save the instance."""
        if not self.key:
            self.key = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({'Active' if self.active else 'Inactive'})"


def auto_assign_sequential_numbers(instance):
    """Auto-populate number and order fields for model instances.

    Args:
        instance: Model instance to populate fields for
    """
    for field in ["number", "order"]:
        if hasattr(instance, field) and not getattr(instance, field):
            que = None
            if hasattr(instance, "event") and instance.event:
                que = instance.__class__.objects.filter(event=instance.event)
            if hasattr(instance, "assoc") and instance.assoc:
                que = instance.__class__.objects.filter(assoc=instance.assoc)
            if hasattr(instance, "character") and instance.character:
                que = instance.__class__.objects.filter(character=instance.character)
            if que is not None:
                n = que.aggregate(Max(field))[f"{field}__max"]
                if not n:
                    setattr(instance, field, 1)
                else:
                    setattr(instance, field, n + 1)


def update_model_search_field(instance):
    """Update search field for model instances that have one.

    Args:
        instance: Model instance to update search field for
    """
    if hasattr(instance, "search"):
        instance.search = None
        instance.search = str(instance)
