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
import json
import os
import random
import shutil
import zipfile
from io import BytesIO
from typing import Optional
from uuid import uuid4
from zipfile import ZipFile

from django.conf import settings as conf_settings
from django.core.files.base import ContentFile
from django.db import models
from django.http import HttpResponse
from django.shortcuts import render
from PIL import Image as PILImage
from PIL import ImageOps

from larpmanager.cache.config import get_assoc_config
from larpmanager.models.member import Badge
from larpmanager.models.miscellanea import Album, AlbumImage, AlbumUpload, WarehouseItem


def upload_albums_dir(main, cache_subs: dict, name: str):
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
    name = os.path.dirname(name)

    # Check if this directory path is already cached
    if name not in cache_subs:
        # Determine parent directory for hierarchy creation
        parent = os.path.dirname(name)
        if not parent or parent == "":
            parent = main
        else:
            parent = cache_subs[parent]

        # Search for existing sub-album with matching name
        album = None
        a_name = os.path.basename(name)

        # Query existing sub-albums to avoid duplicates
        for a in parent.sub_albums.all():
            if a.name == a_name:
                album = a

        # Create new album if none exists
        if not album:
            album = Album()
            album.cod = uuid4().hex
            album.name = a_name
            album.parent = parent
            album.run = main.run
            album.save()

        # Cache the album for future lookups
        cache_subs[name] = album

    return cache_subs[name]


def upload_albums_el(f: ZipFile, alb: models.Model, name: str, main: models.Model, o_path: str) -> None:
    """Upload individual file from zip archive to album.

    Processes a single file from a zip archive, creates album upload and image records,
    and moves the file to the appropriate media directory structure.

    Args:
        f: Zip file object containing the archive being processed
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
    u_name = os.path.basename(name)
    for u in alb.uploads.all():
        if u.name == u_name:
            return

    # Create album upload record for the file
    upl = AlbumUpload()
    upl.album = alb
    upl.name = u_name
    upl.typ = AlbumUpload.PHOTO
    upl.save()

    # Create associated album image record
    img = AlbumImage()
    img.upload = upl

    # Generate unique filename preserving original extension
    parts = u_name.split(".")
    ext = parts[-1] if len(parts) > 1 and parts[-1] else "tmp"
    filename = f"{uuid4().hex}.{ext}"

    # Build destination path starting from media root
    fpath = os.path.join(conf_settings.MEDIA_ROOT, "albums")
    fpath = os.path.join(fpath, main.run.event.slug)
    fpath = os.path.join(fpath, str(main.run.number))

    # Traverse album hierarchy to build nested directory structure
    par = alb.parent
    dirs = []
    while par is not None:
        dirs.append(par.id)
        par = par.parent
    dirs.reverse()

    # Create directory structure for nested albums
    for el in dirs:
        fpath = os.path.join(fpath, str(el))
        if not os.path.exists(fpath):
            os.makedirs(fpath)

    # Complete the file path with unique filename
    fpath = os.path.join(fpath, filename)
    print(fpath)

    # Move file from extraction path to final destination
    os.rename(os.path.join(o_path, name), fpath)

    # Store file path and extract image dimensions
    img.original = fpath
    with PILImage.open(fpath) as i:
        img.width, img.height = i.size
    img.save()


def upload_albums(main, el):
    """Extract and upload all files from zip archive to album structure.

    Args:
        main: Main album instance
        el: Zip file to extract

    Side effects:
        Extracts zip file, creates album structure, uploads all images
    """
    cache_subs = {}

    o_path = os.path.join(conf_settings.MEDIA_ROOT, "zip")
    o_path = os.path.join(o_path, uuid4().hex)

    with zipfile.ZipFile(el, "r") as f:
        f.extractall(o_path)

        for name in f.namelist():
            info = f.getinfo(name)
            alb = upload_albums_dir(main, cache_subs, name)
            if info.is_dir():
                continue
            upload_albums_el(f, alb, name, main, o_path)

    shutil.rmtree(o_path)


def zipdir(path, ziph):
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


def check_centauri(request) -> Optional[HttpResponse]:
    """Check and display Centauri easter egg feature.

    Randomly triggers a special Centauri easter egg feature that displays custom content
    and may award badges to authenticated users. The feature must be enabled for the
    association and pass a random probability check.

    Args:
        request: Django HTTP request object containing user authentication and
                association context with features configuration.

    Returns:
        HttpResponse containing the rendered Centauri template if feature is triggered
        and enabled, None otherwise.

    Side Effects:
        Awards a configurable badge to the authenticated user if Centauri is triggered
        and a badge is configured for the association.
    """
    # Early return if Centauri feature is not enabled for this association
    if "centauri" not in request.assoc["features"]:
        return

    # Check random probability condition for triggering Centauri
    if not _go_centauri(request):
        return

    # Build template context with association-specific Centauri content
    ctx = {}
    for s in ["centauri_descr", "centauri_content"]:
        ctx[s] = get_assoc_config(request.assoc["id"], s, None, ctx)

    # Award badge to user if configured for this association
    badge = get_assoc_config(request.assoc["id"], "centauri_badge", None, ctx)
    if badge:
        bdg = Badge.objects.get(cod=badge)
        bdg.members.add(request.user.member)
        bdg.save()

    # Render and return the Centauri easter egg page
    return render(request, "larpmanager/general/centauri.html", ctx)


def _go_centauri(request):
    """Determine if Centauri easter egg should be triggered.

    Args:
        request: Django HTTP request with user and association context

    Returns:
        bool: True if Centauri should be displayed
    """
    if not request.user.is_authenticated:
        return False

    if request.user.member.language == "en":
        return False

    if "centauri_prob" not in request.assoc:
        return False

    prob = int(request.assoc["centauri_prob"])
    if not prob:
        return False

    if random.randint(0, 1000) > prob:
        return False

    return True


def get_warehouse_optionals(context, default_columns):
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
        optionals[field] = get_assoc_config(context["a_id"], f"warehouse_{field}", False, context)
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
        field = instance._meta.get_field("photo")
        if not isinstance(field, models.ImageField):
            return
    except Exception:
        return

    # Get the photo file object from the instance
    f = getattr(instance, "photo", None)
    if not f:
        return

    # Check if this is a new file that needs processing
    if _check_new(f, instance, sender):
        return

    # Open and load the image from the file object
    fileobj = getattr(f, "file", None) or f
    try:
        fileobj.seek(0)
        img = PILImage.open(fileobj)
    except Exception:
        return

    # Apply EXIF orientation and get image dimensions
    img = ImageOps.exif_transpose(img)
    w, h = img.size

    # Skip rotation if image is already landscape or square
    if h <= w:
        return

    # Rotate the image 90 degrees clockwise to make it landscape
    img = img.rotate(90, expand=True)

    # Determine the appropriate file format for saving
    fmt = _get_extension(f, img)

    # Convert incompatible color modes for JPEG format
    if fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")

    # Save the rotated image to a BytesIO buffer with optimization
    out = BytesIO()
    save_kwargs = {"optimize": True}
    if fmt == "JPEG":
        save_kwargs["quality"] = 88
    img.save(out, format=fmt, **save_kwargs)
    out.seek(0)

    # Replace the original photo with the rotated version
    basename = os.path.basename(f.name) or f.name
    instance.photo = ContentFile(out.read(), name=basename)


def _get_extension(f, img) -> str:
    """Get the appropriate image format extension.

    Determines the correct image format based on the file extension and image format.
    Falls back to JPEG if format cannot be determined.

    Args:
        f: File object with a name attribute
        img: Image object with a format attribute

    Returns:
        str: Image format string (e.g., 'JPEG', 'PNG', 'WEBP')
    """
    # Extract file extension and normalize to lowercase
    ext = os.path.splitext(f.name)[1].lower()

    # Get image format, defaulting to empty string if None
    fmt = (img.format or "").upper()

    # If no format detected from image, determine from file extension
    if not fmt:
        if ext in (".jpg", ".jpeg"):
            fmt = "JPEG"
        elif ext == ".png":
            fmt = "PNG"
        elif ext == ".webp":
            fmt = "WEBP"
        else:
            # Default fallback format
            fmt = "JPEG"
    return fmt


def _check_new(file_field, instance, sender) -> bool:
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
        except Exception:
            # Silently handle any database or attribute errors
            pass

    # Default to treating as new file upload
    return False
