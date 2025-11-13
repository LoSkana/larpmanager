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
import shutil
import zipfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from django.conf import settings as conf_settings
from django.core.files.base import ContentFile
from django.db import models
from django.shortcuts import render
from PIL import Image as PILImage
from PIL import ImageOps

from larpmanager.cache.config import get_association_config
from larpmanager.models.member import Badge
from larpmanager.models.miscellanea import Album, AlbumImage, AlbumUpload, WarehouseItem

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


def upload_albums_dir(main: Any, cache_subs: dict, name: str) -> Any:
    """Create or find album directory structure for uploaded files.

    Creates a hierarchical album structure based on directory paths from zip files.
    Uses caching to avoid duplicate database queries for existing albums.

    Args:
        main: Main album instance that serves as the root parent
        cache_subs (dict): Cache mapping directory paths to Album instances
        name (str): Full directory path from zip file entry

    Returns:
        Album: Album instance representing the directory structure

    Side Effects:
        - Creates new Album instances in database for missing directories
        - Updates cache_subs dictionary with newly created albums

    """
    # Extract directory path, removing filename component
    path_obj = Path(name)
    directory_path = str(path_obj.parent) if path_obj.parent != Path() else ""

    # Check if this directory path is already cached
    if directory_path not in cache_subs:
        # Determine parent directory for hierarchy creation
        parent_path_obj = Path(directory_path) if directory_path else Path()
        parent_directory_path = (
            str(parent_path_obj.parent) if directory_path and parent_path_obj.parent != Path() else ""
        )
        if not parent_directory_path or parent_directory_path == "":
            parent_album = main
        else:
            parent_album = cache_subs[parent_directory_path]

        # Search for existing sub-album with matching name
        existing_album = None
        album_name = path_obj.parent.name if path_obj.parent != Path() else ""

        # Query existing sub-albums to avoid duplicates
        for sub_album in parent_album.sub_albums.all():
            if sub_album.name == album_name:
                existing_album = sub_album

        # Create new album if none exists
        if not existing_album:
            existing_album = Album()
            existing_album.cod = uuid4().hex
            existing_album.name = album_name
            existing_album.parent = parent_album
            existing_album.run = main.run
            existing_album.save()

        # Cache the album for future lookups
        cache_subs[directory_path] = existing_album

    return cache_subs[directory_path]


def upload_albums_el(alb: models.Model, name: str, main: models.Model, o_path: str) -> None:
    """Upload individual file from zip archive to album.

    Processes a single file from a zip archive, creates album upload and image records,
    and moves the file to the appropriate media directory structure.

    Args:
        alb: Album instance to upload the file to
        name: File name from zip archive (including path if nested)
        main: Main album instance containing run and event references
        o_path: Output path where zip contents were extracted

    Side Effects:
        - Creates AlbumUpload and AlbumImage database records
        - Moves file from extraction path to media directory
        - Creates directory structure if it doesn't exist
        - Generates unique filename using UUID to prevent conflicts

    Returns:
        None

    """
    # Check if file already exists in album to avoid duplicates
    upload_name = Path(name).name
    for existing_upload in alb.uploads.all():
        if existing_upload.name == upload_name:
            return

    # Create album upload record for the file
    album_upload = AlbumUpload()
    album_upload.album = alb
    album_upload.name = upload_name
    album_upload.typ = AlbumUpload.PHOTO
    album_upload.save()

    # Create associated album image record
    album_image = AlbumImage()
    album_image.upload = album_upload

    # Generate unique filename preserving original extension
    filename_parts = upload_name.split(".")
    file_extension = filename_parts[-1] if len(filename_parts) > 1 and filename_parts[-1] else "tmp"
    unique_filename = f"{uuid4().hex}.{file_extension}"

    # Build destination path starting from media root
    destination_path = os.path.join(conf_settings.MEDIA_ROOT, "albums")
    destination_path = os.path.join(destination_path, main.run.event.slug)
    destination_path = os.path.join(destination_path, str(main.run.number))

    # Traverse album hierarchy to build nested directory structure
    parent_album = alb.parent
    parent_directories = []
    while parent_album is not None:
        parent_directories.append(parent_album.id)
        parent_album = parent_album.parent
    parent_directories.reverse()

    # Create directory structure for nested albums
    for directory_id in parent_directories:
        destination_path = os.path.join(destination_path, str(directory_id))
        if not os.path.exists(destination_path):
            Path(destination_path).mkdir(parents=True, exist_ok=True)

    # Complete the file path with unique filename
    destination_path = os.path.join(destination_path, unique_filename)
    logger.debug("Uploading album image to: %s", destination_path)

    # Move file from extraction path to final destination
    Path(o_path, name).rename(destination_path)

    # Store file path and extract image dimensions
    album_image.original = destination_path
    with PILImage.open(destination_path) as image_file:
        album_image.width, album_image.height = image_file.size
    album_image.save()


def upload_albums(main: Any, el: Any) -> None:
    """Extract and upload all files from zip archive to album structure.

    Args:
        main: Main album instance
        el: Zip file to extract

    Side effects:
        Extracts zip file, creates album structure, uploads all images

    """
    cache_subalbums = {}

    extraction_path = os.path.join(conf_settings.MEDIA_ROOT, "zip")
    extraction_path = os.path.join(extraction_path, uuid4().hex)

    with zipfile.ZipFile(el, "r") as zip_file:
        zip_file.extractall(extraction_path)

        for filename in zip_file.namelist():
            file_info = zip_file.getinfo(filename)
            album = upload_albums_dir(main, cache_subalbums, filename)
            if file_info.is_dir():
                continue
            upload_albums_el(album, filename, main, extraction_path)

    shutil.rmtree(extraction_path)


def zipdir(path: Any, ziph: Any) -> None:
    """Recursively add directory contents to zip file.

    Args:
        path (str): Directory path to compress
        ziph: Zip file handle to write to

    Side effects:
        Adds all files in directory tree to zip archive

    """
    for root, _dirs, files in os.walk(path):
        for file in files:
            ziph.write(
                os.path.join(root, file),
                os.path.relpath(str(os.path.join(root, file)), os.path.join(path, "..")),
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
            default_value=None,
            context=template_context,
        )

    # Award badge to user if configured for this association
    badge_code = get_association_config(
        context["association_id"], "centauri_badge", default_value=None, context=template_context
    )
    if badge_code:
        badge = Badge.objects.get(cod=badge_code)
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
        optionals[field] = get_association_config(
            context["association_id"], f"warehouse_{field}", default_value=False, context=context
        )
        if optionals[field]:
            has_active_optional = 1
    context["optionals"] = optionals
    context["no_header_cols"] = json.dumps([column + has_active_optional for column in default_columns])


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
        photo_field = instance._meta.get_field("photo")
        if not isinstance(photo_field, models.ImageField):
            return
    except Exception:
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
        image = PILImage.open(file_object)
    except Exception:
        return

    # Apply EXIF orientation and get image dimensions
    image = ImageOps.exif_transpose(image)
    width, height = image.size

    # Skip rotation if image is already landscape or square
    if height <= width:
        return

    # Rotate the image 90 degrees clockwise to make it landscape
    image = image.rotate(90, expand=True)

    # Determine the appropriate file format for saving
    file_format = _get_extension(photo_file, image)

    # Convert incompatible color modes for JPEG format
    if file_format == "JPEG" and image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGB")

    # Save the rotated image to a BytesIO buffer with optimization
    output_buffer = BytesIO()
    save_kwargs = {"optimize": True}
    if file_format == "JPEG":
        save_kwargs["quality"] = 88
    image.save(output_buffer, format=file_format, **save_kwargs)
    output_buffer.seek(0)

    # Replace the original photo with the rotated version
    original_filename = Path(photo_file.name).name or photo_file.name
    instance.photo = ContentFile(output_buffer.read(), name=original_filename)


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
        except Exception as e:
            # Silently handle any database or attribute errors
            logger.debug("Error checking file field for instance pk=%s: %s", instance.pk, e)

    # Default to treating as new file upload
    return False
