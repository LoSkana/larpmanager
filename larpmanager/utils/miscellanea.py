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
from django.core.files.uploadedfile import UploadedFile
from django.db import models
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from PIL import Image as PILImage
from PIL import ImageOps

from larpmanager.cache.config import get_assoc_config
from larpmanager.models.member import Badge
from larpmanager.models.miscellanea import Album, AlbumImage, AlbumUpload, WarehouseItem


def upload_albums_dir(main: Album, cache_subs: dict[str, Album], name: str) -> Album:
    """Create or find album directory structure for uploaded files.

    This function handles the creation of nested album directory structures
    when uploading files from zip archives. It maintains a cache to avoid
    duplicate database queries and ensures proper parent-child relationships.

    Args:
        main: Main album instance that serves as the root parent
        cache_subs: Cache dictionary mapping directory paths to Album instances
        name: Directory path from zip file (file path, not directory path)

    Returns:
        Album instance corresponding to the directory structure

    Side Effects:
        - Creates new Album instances in the database for missing directories
        - Updates the cache_subs dictionary with newly created albums
        - Establishes parent-child relationships between albums
    """
    # Extract directory path from the file path
    name = os.path.dirname(name)

    # Check if directory album already exists in cache
    if name not in cache_subs:
        # Determine parent directory for nested structure
        parent = os.path.dirname(name)
        if not parent or parent == "":
            parent = main
        else:
            parent = cache_subs[parent]

        # Search for existing sub-album with matching name
        album = None
        a_name = os.path.basename(name)

        # Check if album already exists as sub-album of parent
        for a in parent.sub_albums.all():
            if a.name == a_name:
                album = a

        # Create new album if none found
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


def upload_albums(main: Album, el: UploadedFile) -> None:
    """Extract and upload all files from zip archive to album structure.

    Extracts a zip file and creates an album structure by organizing images
    into subdirectories. Each directory in the zip becomes a sub-album, and
    all images are uploaded to their respective albums.

    Args:
        main: Main album instance to serve as the root container
        el: Zip file to extract and process

    Side Effects:
        - Extracts zip file to temporary directory
        - Creates album structure based on zip directory layout
        - Uploads all images to corresponding albums
        - Removes temporary extraction directory
    """
    cache_subs = {}

    # Create unique temporary directory for extraction
    o_path = os.path.join(conf_settings.MEDIA_ROOT, "zip")
    o_path = os.path.join(o_path, uuid4().hex)

    with zipfile.ZipFile(el, "r") as f:
        # Extract all contents to temporary directory
        f.extractall(o_path)

        # Process each file/directory in the zip archive
        for name in f.namelist():
            info = f.getinfo(name)
            # Get or create album for this directory path
            alb = upload_albums_dir(main, cache_subs, name)

            # Skip directories, only process files
            if info.is_dir():
                continue

            # Upload individual file to its corresponding album
            upload_albums_el(f, alb, name, main, o_path)

    # Clean up temporary extraction directory
    shutil.rmtree(o_path)


def zipdir(path: str, ziph: zipfile.ZipFile) -> None:
    """Recursively add directory contents to zip file.

    Args:
        path: Directory path to compress
        ziph: Zip file handle to write to

    Returns:
        None

    Raises:
        OSError: If the directory path does not exist or is not accessible
    """
    # Walk through all directories and subdirectories
    for root, _dirs, files in os.walk(path):
        # Process each file in the current directory
        for file in files:
            # Create full file path
            file_path = os.path.join(root, file)

            # Calculate relative path for archive to maintain directory structure
            archive_path = os.path.relpath(str(file_path), os.path.join(path, ".."))

            # Add file to zip archive
            ziph.write(file_path, archive_path)


def check_centauri(request: HttpRequest) -> Optional[HttpResponse]:
    """Check and display Centauri easter egg feature.

    Randomly triggers a special Centauri easter egg feature with configurable
    probability. When triggered, displays custom content and optionally awards
    a badge to the authenticated user.

    Args:
        request: Django HTTP request object containing user authentication
                and association context with feature flags

    Returns:
        HttpResponse: Rendered Centauri page if easter egg is triggered
        None: If feature is disabled or easter egg doesn't trigger

    Side Effects:
        - May award a badge to the authenticated user's member profile
        - Badge assignment is permanent and saved to database
    """
    # Check if Centauri feature is enabled for this association
    if "centauri" not in request.assoc["features"]:
        return

    # Determine if easter egg should trigger based on random chance
    if not _go_centauri(request):
        return

    # Build context with association-specific Centauri configuration
    ctx = {}
    for s in ["centauri_descr", "centauri_content"]:
        ctx[s] = get_assoc_config(request.assoc["id"], s, None)

    # Award badge to user if configured for this association
    badge = get_assoc_config(request.assoc["id"], "centauri_badge", None)
    if badge:
        bdg = Badge.objects.get(cod=badge)
        bdg.members.add(request.user.member)
        bdg.save()

    # Render and return the Centauri easter egg page
    return render(request, "larpmanager/general/centauri.html", ctx)


def _go_centauri(request: HttpRequest) -> bool:
    """Determine if Centauri easter egg should be triggered.

    This function checks various conditions to determine whether the Centauri
    easter egg should be displayed to the user, including authentication status,
    language preference, and probability settings.

    Args:
        request: Django HTTP request object containing user and association context.
                Must have 'user' and 'assoc' attributes.

    Returns:
        bool: True if all conditions are met and random probability check passes,
              False otherwise.
    """
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return False

    # Skip for English language users
    if request.user.member.language == "en":
        return False

    # Verify centauri probability setting exists in association config
    if "centauri_prob" not in request.assoc:
        return False

    # Get probability value and check if it's enabled
    prob = int(request.assoc["centauri_prob"])
    if not prob:
        return False

    # Perform random probability check (prob out of 1000)
    if random.randint(0, 1000) > prob:
        return False

    return True


def get_warehouse_optionals(ctx: dict, def_cols: list) -> None:
    """Get warehouse optional field configuration for display.

    Retrieves configuration for optional warehouse fields from association settings,
    determines if any optional fields are active, and updates the context with
    column configuration for display purposes.

    Args:
        ctx: Context dictionary containing association ID ('a_id') that will be
             updated with optionals configuration and header column settings
        def_cols: Default column configuration list used for calculating
                  header column offsets

    Returns:
        None: Function modifies ctx in place

    Side Effects:
        - Updates ctx['optionals'] with field name to boolean mapping
        - Updates ctx['no_header_cols'] with JSON string of adjusted column indices
    """
    # Initialize optionals dictionary and active flag
    optionals = {}
    active = 0

    # Iterate through all optional warehouse fields
    for field in WarehouseItem.get_optional_fields():
        # Get configuration value for this field from association settings
        optionals[field] = get_assoc_config(ctx["a_id"], f"warehouse_{field}", False)

        # Set active flag if any optional field is enabled
        if optionals[field]:
            active = 1

    # Update context with optionals configuration
    ctx["optionals"] = optionals

    # Calculate adjusted column indices and store as JSON string
    ctx["no_header_cols"] = json.dumps([el + active for el in def_cols])


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
    """Get the appropriate image format string for the given file and image.

    Determines the image format based on the PIL Image format attribute first,
    then falls back to file extension if format is not available.

    Args:
        f: File object with a 'name' attribute containing the filename
        img: PIL Image object with optional 'format' attribute

    Returns:
        str: Uppercase format string (e.g., 'JPEG', 'PNG', 'WEBP')
    """
    # Extract file extension and normalize to lowercase
    ext = os.path.splitext(f.name)[1].lower()

    # Get format from PIL Image, defaulting to empty string
    fmt = (img.format or "").upper()

    # If PIL didn't detect format, determine from file extension
    if not fmt:
        if ext in (".jpg", ".jpeg"):
            fmt = "JPEG"
        elif ext == ".png":
            fmt = "PNG"
        elif ext == ".webp":
            fmt = "WEBP"
        else:
            # Default to JPEG for unknown extensions
            fmt = "JPEG"

    return fmt


def _check_new(f, instance, sender) -> bool:
    """
    Check if a file field is new or unchanged from the previous version.

    This function determines whether a file field on a model instance represents
    a new file upload or if it's the same as the existing file in the database.

    Args:
        f: The file field to check
        instance: The model instance being processed
        sender: The model class that sent the signal

    Returns:
        bool: True if the file is unchanged from the database version,
              False if it's a new file or if the instance is new
    """
    # Only check existing instances (those with a primary key)
    if instance.pk:
        try:
            # Fetch only the photo field from the database for efficiency
            old = sender.objects.filter(pk=instance.pk).only("photo").first()

            # If we found the old instance, compare file names
            if old:
                # Get the old file name, defaulting to empty string if no file
                old_name = old.photo.name if old.photo else ""

                # Check if names match and no new file data is present
                # This indicates the file field hasn't been changed
                if f.name == old_name and not getattr(f, "file", None):
                    return True
        except Exception:
            # Silently handle any database or attribute errors
            pass

    # Return False for new instances or when file has changed
    return False
