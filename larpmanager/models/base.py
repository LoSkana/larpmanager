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
import contextlib
import os
import secrets
import sys
import time
from itertools import chain
from typing import Any, ClassVar

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.validators import RegexValidator
from django.db import IntegrityError, models, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField
from model_clone import CloneMixin
from pilkit.processors import ResizeToFill
from safedelete.models import SOFT_DELETE_CASCADE, SafeDeleteModel
from tinymce.models import HTMLField

from larpmanager.models.utils import UploadToPathAndRename, get_attr, my_uuid_short

AlphanumericValidator = RegexValidator(r"^[0-9a-z_-]*$", "Only characters allowed are: 0-9, a-z, _, -.")

UUID_RETRY_LIMIT = 5


class UuidMixin(models.Model):
    """Adds an uuid field to the model."""

    uuid = models.CharField(
        max_length=12,
        unique=True,
        db_index=True,
        editable=False,
    )

    class Meta:
        abstract = True


class BaseModel(CloneMixin, SafeDeleteModel):
    """Represents BaseModel model."""

    created = models.DateTimeField(default=timezone.now, editable=False)

    updated = models.DateTimeField(auto_now=True)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        abstract = True
        ordering: ClassVar[list] = ["-updated"]

    def upd_js_attr(self, dict_object: dict, attribute_name: str) -> dict:
        """Update dict object with model attribute value."""
        dict_object[attribute_name] = get_attr(self, attribute_name)
        return dict_object

    def __str__(self) -> str:
        """Return string representation of the model.

        Returns string representation based on model attributes in order of preference:
        1. 'name' - most common display field
        2. 'title' - used in blog posts, guides, showcases
        3. 'question' - used in FAQs (truncated to 100 chars)
        4. 'author' - used in reviews
        5. 'info' - used in highlights (truncated to 50 chars)
        6. 'text' - truncated text content (100 chars)
        7. 'search' - search field
        8. Parent class string representation as fallback

        Returns:
            str: Model representation based on available fields.

        """
        # Define fields to check in order of preference with optional truncation length
        field_checks = [
            ("name", None),
            ("title", None),
            ("question", 100),
            ("author", None),
            ("info", 50),
            ("text", 100),
            ("search", None),
        ]

        # Check each field in order and return first available value
        for field_name, max_length in field_checks:
            if hasattr(self, field_name):
                value = getattr(self, field_name)
                if value:
                    return value[:max_length] if max_length else value

        # Use parent class implementation as final fallback
        return super().__str__()

    def get_absolute_url(self) -> Any:
        """Get absolute URL for the model instance."""
        # noinspection PyUnresolvedReferences
        return reverse("event", kwargs={"event_slug": self.slug})

    def small_text(self) -> Any:
        """Get truncated text preview."""
        if hasattr(self, "text"):
            return self.text[:100]
        return ""

    def as_dict(self, *, many_to_many: bool = True) -> dict[str, any]:
        """Convert model instance to dictionary representation.

        This method serializes a Django model instance into a dictionary format,
        optionally including many-to-many relationship data as lists of IDs.

        Args:
            many_to_many: Whether to include many-to-many relationships in the
                output dictionary. Defaults to True.

        Returns:
            A dictionary with field names as keys and field values as data.
            Many-to-many fields are represented as lists of related object IDs
        """
        # Get model metadata for field introspection
        # noinspection PyUnresolvedReferences
        model_options = self._meta
        serialized_data = {}

        # Process concrete and private fields (standard model fields)
        for field in chain(model_options.concrete_fields, model_options.private_fields):
            field_value = field.value_from_object(self)
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
    """Represents FeatureNationality model."""

    ITALY = "it", _("Italy")


class FeatureModule(BaseModel):
    """Represents FeatureModule model."""

    name = models.CharField(max_length=100)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], db_index=True, unique=True)

    icon = models.CharField(max_length=100)

    order = models.IntegerField()

    nationality = models.CharField(max_length=2, choices=FeatureNationality.choices, blank=True, null=True)


class Feature(BaseModel):
    """Represents Feature model."""

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
        ordering: ClassVar[list] = ["module", "order"]

    def __str__(self) -> str:
        """Return string representation of the feature."""
        return f"{self.name} - {self.module}"


class PaymentMethod(UuidMixin, BaseModel):
    """Represents PaymentMethod model."""

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

    def as_dict(self, **kwargs: Any) -> Any:  # noqa: ARG002
        """Convert payment method to dictionary with profile image."""
        # noinspection PyUnresolvedReferences
        result = {"slug": self.slug, "name": self.name}
        if self.profile:
            with contextlib.suppress(FileNotFoundError):
                result["profile"] = self.profile_thumb.url
        return result


class PublisherApiKey(BaseModel):
    """Represents PublisherApiKey model."""

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

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.name} ({'Active' if self.active else 'Inactive'})"


def auto_assign_sequential_numbers(instance: Any) -> None:  # noqa: C901
    """Auto-populate number and order fields for model instances using cache-based locking."""
    for field_name in ["number", "order"]:
        if hasattr(instance, field_name) and not getattr(instance, field_name):
            queryset = None
            scope_id = None
            if hasattr(instance, "event") and instance.event:
                queryset = instance.__class__.objects.filter(event=instance.event)
                scope_id = f"event_{instance.event.id}"
            if hasattr(instance, "association") and instance.association:
                queryset = instance.__class__.objects.filter(association=instance.association)
                scope_id = f"assoc_{instance.association.id}"
            if hasattr(instance, "character") and instance.character:
                queryset = instance.__class__.objects.filter(character=instance.character)
                scope_id = f"char_{instance.character.id}"

            if queryset is not None and scope_id is not None:
                # Create a unique lock key for this model + scope combination
                model_name = instance.__class__.__name__
                lock_key = f"auto_number_lock_{model_name}_{field_name}_{scope_id}"

                # Try to acquire lock with retries (max 3 seconds total)
                max_retries = 30
                retry_delay = 0.1  # 100ms
                lock_acquired = False

                for _ in range(max_retries):
                    # cache.add() is atomic - returns True only if key doesn't exist
                    if cache.add(lock_key, "locked", timeout=10):
                        lock_acquired = True
                        break
                    time.sleep(retry_delay)

                if not lock_acquired:
                    # Fallback: force set the lock and continue (prevents indefinite blocking)
                    cache.set(lock_key, "locked", timeout=10)

                try:
                    # Now safely query for max number within transaction
                    with transaction.atomic():
                        max_instance = queryset.select_for_update().order_by(f"-{field_name}").first()
                        if not max_instance:
                            setattr(instance, field_name, 1)
                        else:
                            max_value = getattr(max_instance, field_name)
                            setattr(instance, field_name, max_value + 1)
                finally:
                    # Always release the lock
                    cache.delete(lock_key)


def auto_set_uuid(instance: Any) -> None:
    """Set uuid field if missing value."""
    # If the model does not have uuid field, or already has a value, skip
    if not hasattr(instance, "uuid") or instance.uuid:
        return

    for _try in range(UUID_RETRY_LIMIT):
        instance.uuid = my_uuid_short()
        try:
            with transaction.atomic():
                return
        except IntegrityError:
            instance.uuid = None

    msg = "UUID collision after retries"
    raise RuntimeError(msg)


def debug_set_uuid(instance: Any, *, created: bool) -> None:
    """Simplifiy uuid for debug purposes."""
    # Check if running in PyCharm via pytest runner
    is_pycharm = (
        os.getenv("PYCHARM_DEBUG") == "1"
        or os.getenv("PYCHARM_HOSTED") == "1"
        or any("_jb_pytest_runner" in arg or "pycharm" in arg.lower() for arg in sys.argv)
    )

    debug_enviro = (
        conf_settings.DEBUG or os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true" or is_pycharm
    )
    if not created or not hasattr(instance, "uuid") or not debug_enviro:
        return

    debug_uuid = f"u{instance.id}"
    instance.__class__.objects.filter(pk=instance.pk).update(uuid=debug_uuid)
    instance.uuid = debug_uuid


def update_model_search_field(model_instance: Any) -> None:
    """Update search field for model instances that have one."""
    if hasattr(model_instance, "search"):
        model_instance.search = None
        model_instance.search = str(model_instance)
