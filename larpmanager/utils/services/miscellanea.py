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

import json
import logging
import os
import random
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Sum
from django.shortcuts import render
from PIL import Image as PILImage, ImageOps

from larpmanager.cache.config import get_association_config
from larpmanager.models.larpmanager import LarpManagerNewsletter, NewsletterStatus
from larpmanager.models.member import Badge
from larpmanager.models.miscellanea import WarehouseItem, WarehouseItemAssignment

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


def zipdir(path: Any, ziph: Any) -> None:
    """Recursively add directory contents to zip file."""
    for root, _dirs, files in os.walk(path):
        for file in files:
            file_path = Path(root) / file
            ziph.write(
                str(file_path),
                str(file_path.relative_to(Path(path).parent)),
            )


def check_centauri(request: HttpRequest, context: dict) -> HttpResponse | None:
    """Check and display Centauri easter egg feature.

    Randomly triggers a special Centauri easter egg feature that displays custom content
    and may award badges to authenticated users. The feature must be enabled for the
    association and pass a random probability check.

    Args:
        request: Django HTTP request object containing user authentication and
                association context with features configuration.
        context: Dict context informations

    Returns:
        HttpResponse containing the rendered Centauri template if feature is triggered
        and enabled, None otherwise.

    Side Effects:
        Awards a configurable badge to the authenticated user if Centauri is triggered
        and a badge is configured for the association.

    """
    # Early return if Centauri feature is not enabled for this association
    if "centauri" not in context["features"]:
        return None

    # Check random probability condition for triggering Centauri
    if not _go_centauri(context):
        return None

    # Build template context with association-specific Centauri content
    template_context = {}
    for config_key in ["centauri_descr", "centauri_content"]:
        template_context[config_key] = get_association_config(
            context["association_id"],
            config_key,
            context=template_context,
        )

    # Award badge to user if configured for this association
    badge_code = get_association_config(context["association_id"], "centauri_badge", context=template_context)
    if badge_code:
        badge = Badge.objects.filter(cod=badge_code).first()
        if badge:
            badge.members.add(context["member"])
            badge.save()

    # Render and return the Centauri easter egg page
    return render(request, "larpmanager/general/centauri.html", template_context)


def _go_centauri(context: dict) -> bool:
    """Determine if Centauri easter egg should be triggered.

    Args:
        context: Dict context data

    Returns:
        bool: True if Centauri should be displayed

    """
    if not context["member"]:
        return False

    if context["member"].language == "en":
        return False

    if "centauri_prob" not in context:
        return False

    centauri_probability = int(context["centauri_prob"])
    if not centauri_probability:
        return False

    random_value = random.randint(0, 1000)  # noqa: S311
    return not random_value > centauri_probability


def get_warehouse_optionals(context: Any, default_columns: Any) -> None:
    """Get warehouse optional field configuration for display.

    Args:
        context (dict): Context dictionary to update
        default_columns (list): Default column configuration

    Side effects:
        Updates context with optionals configuration and header column settings

    """
    optionals = {}
    has_active_optional = 0
    for field in WarehouseItem.get_optional_fields():
        optionals[field] = get_association_config(context["association_id"], f"warehouse_{field}", context=context)
        if optionals[field]:
            has_active_optional = 1
    context["optionals"] = optionals
    context["no_header_cols"] = json.dumps([column + has_active_optional for column in default_columns])


def warehouse_assigned_quantities(items: Any) -> dict[int, int]:
    """Return the quantity already assigned to any area, per warehouse item id."""
    return {
        row["item_id"]: row["total"] or 0
        for row in WarehouseItemAssignment.objects.filter(item__in=items)
        .values("item_id")
        .annotate(total=Sum("quantity"))
    }


def warehouse_available_quantity(item: WarehouseItem, assigned: int | None = None) -> int:
    """Return the stock of an item not yet assigned to any area, 0 if unlimited."""
    if item.quantity is None:
        return 0
    if assigned is None:
        assigned = warehouse_assigned_quantities([item]).get(item.id, 0)
    return max(item.quantity - assigned, 0)


def warehouse_add_assignment(item: WarehouseItem, area: Any, event: Any, quantity: int) -> Any:
    """Add a quantity to the item/area assignment, creating it if missing.

    The lookup matches the unique constraint on (area, item) only: an area may
    be inherited from a parent campaign event, so the same pair can already be
    assigned under a different event, and adding the event to the lookup would
    attempt a duplicate insert.
    """
    assignment, created = WarehouseItemAssignment.objects.get_or_create(
        item=item,
        area=area,
        defaults={"quantity": quantity, "event": event},
    )
    if not created:
        assignment.quantity = (assignment.quantity or 0) + quantity
        assignment.save()
    return assignment


def auto_rotate_vertical_photos(instance: object, sender: type) -> None:
    """Automatically rotate vertical photos to landscape orientation.

    This function is designed to be used as a Django signal handler that processes
    image fields on model instances. It rotates vertical images 90 degrees clockwise
    to convert them to landscape orientation while preserving image quality and
    handling various image formats appropriately.

    Args:
        instance: Model instance containing a 'photo' ImageField that may need rotation
        sender: Model class that sent the signal (typically used in Django signals)

    Returns:
        None: Function performs in-place modification of the instance's photo field

    Note:
        - Only processes images that are taller than they are wide
        - Handles EXIF orientation data automatically
        - Optimizes JPEG quality and converts RGBA/LA/P modes to RGB for JPEG format
        - Silently returns on any errors to avoid breaking the calling process

    """
    # Validate that the instance has a photo ImageField
    try:
        # noinspection PyProtectedMember, PyUnresolvedReferences
        photo_field = instance._meta.get_field("photo")  # noqa: SLF001  # Django model metadata
        if not isinstance(photo_field, models.ImageField):
            return
    except (AttributeError, LookupError):
        return

    # Get the photo file object from the instance
    photo_file = getattr(instance, "photo", None)
    if not photo_file:
        return

    # Check if this is a new file that needs processing
    if _check_new(photo_file, instance, sender):
        return

    # Open and load the image from the file object
    file_object = getattr(photo_file, "file", None) or photo_file
    try:
        file_object.seek(0)
        with PILImage.open(file_object) as img:
            # Apply EXIF orientation and get image dimensions
            oriented_img = ImageOps.exif_transpose(img)
            width, height = oriented_img.size

            # Skip rotation if image is already landscape or square
            if height <= width:
                return

            # Rotate the image 90 degrees clockwise to make it landscape
            rotated_img = oriented_img.rotate(90, expand=True)

            # Determine the appropriate file format for saving
            file_format = _get_extension(photo_file, rotated_img)

            # Convert incompatible color modes for JPEG format
            if file_format == "JPEG" and rotated_img.mode in ("RGBA", "LA", "P"):
                rotated_img = rotated_img.convert("RGB")

            # Save the rotated image to a BytesIO buffer with optimization
            with BytesIO() as output_buffer:
                save_kwargs = {"optimize": True}
                if file_format == "JPEG":
                    save_kwargs["quality"] = 88
                rotated_img.save(output_buffer, format=file_format, **save_kwargs)
                output_buffer.seek(0)

                # Replace the original photo with the rotated version
                original_filename = Path(photo_file.name).name or photo_file.name
                instance.photo = ContentFile(output_buffer.read(), name=original_filename)
    except (OSError, AttributeError):
        return


def _get_extension(uploaded_file: Any, image: Any) -> str:
    """Get the appropriate image format extension.

    Determines the correct image format based on the file extension and image format.
    Falls back to JPEG if format cannot be determined.

    Args:
        uploaded_file: File object with a name attribute
        image: Image object with a format attribute

    Returns:
        str: Image format string (e.g., 'JPEG', 'PNG', 'WEBP')

    """
    # Extract file extension and normalize to lowercase
    file_extension = Path(uploaded_file.name).suffix.lower()

    # Get image format, defaulting to empty string if None
    image_format = (image.format or "").upper()

    # If no format detected from image, determine from file extension
    if not image_format:
        if file_extension in (".jpg", ".jpeg"):
            image_format = "JPEG"
        elif file_extension == ".png":
            image_format = "PNG"
        elif file_extension == ".webp":
            image_format = "WEBP"
        else:
            # Default fallback format
            image_format = "JPEG"
    return image_format


def _check_new(file_field: Any, instance: Any, sender: Any) -> bool:
    """Check if the file field represents a new file upload.

    Args:
        file_field: The file field to check
        instance: The model instance being saved
        sender: The model class that sent the signal

    Returns:
        True if this is not a new file upload (file already exists and unchanged),
        False if this is a new file upload or the file has changed

    """
    # Check if instance already exists in database
    if instance.pk:
        try:
            # Retrieve existing instance with only photo field for efficiency
            existing_instance = sender.objects.filter(pk=instance.pk).only("photo").first()

            if existing_instance:
                # Get the old file name, defaulting to empty string if no photo
                existing_file_name = existing_instance.photo.name if existing_instance.photo else ""

                # Compare file names and check if no new file data is present
                if file_field.name == existing_file_name and not getattr(file_field, "file", None):
                    return True
        except (ObjectDoesNotExist, AttributeError) as e:
            # Silently handle any database or attribute errors
            logger.debug("Error checking file field for instance pk=%s: %s", instance.pk, e)

    # Default to treating as new file upload
    return False


def _newsletter_set_active(email: str) -> None:
    """Prepares a newsletter email for active."""
    _newsletter_set(email, NewsletterStatus.ACTIVE)


def _newsletter_set_non_active(email: str) -> None:
    """Prepares a newsletter email for inactive."""
    _newsletter_set(email, NewsletterStatus.NON_ACTIVE)


def _newsletter_set(email: str, status: NewsletterStatus) -> None:
    """Prepares a newsletter email for given status."""
    if "demo" in email:
        return

    obj, _created = LarpManagerNewsletter.objects.get_or_create(
        email=email,
        defaults={"status": status},
    )
    if obj.status not in {NewsletterStatus.UNSUBSCRIBED, status}:
        obj.status = status
        obj.save(update_fields=["status"])
