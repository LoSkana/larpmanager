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

import io
import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.conf import settings as conf_settings
from django.utils import timezone
from PIL import Image

from larpmanager.models.utils import UploadToPathAndRename
from larpmanager.models.writing import Character, get_event_elements
from larpmanager.utils.io.upload.constants import (
    _QUALITY_MIN,
    _QUALITY_START,
    _QUALITY_STEP,
    _SCALE_MIN,
    _SCALE_STEP,
    MAX_PROFILE_IMAGE_SIZE,
    MAX_PROFILE_UPLOAD_SIZE,
)
from larpmanager.utils.security import safe_extract_zip

if TYPE_CHECKING:
    from larpmanager.models.event import Run

logger = logging.getLogger(__name__)


def normalize_profile_image(img_data: bytes) -> bytes:
    """Normalize and reduce uploaded profile size."""
    if len(img_data) > MAX_PROFILE_UPLOAD_SIZE:
        msg = "Uploaded image exceeds maximum allowed size"
        raise ValueError(msg)

    # Always converts to JPEG. Reduces quality in steps first, then scales down.
    with Image.open(io.BytesIO(img_data)) as im:
        if im.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", im.size, (255, 255, 255))
            rgba = im.convert("RGBA")
            background.paste(rgba, mask=rgba.split()[3])
            rgb = background
        else:
            rgb = im.convert("RGB")
        width, height = rgb.size

        quality = _QUALITY_START
        while quality >= _QUALITY_MIN:
            buf = io.BytesIO()
            rgb.save(buf, format="JPEG", quality=quality)
            if buf.tell() <= MAX_PROFILE_IMAGE_SIZE:
                return buf.getvalue()
            quality -= _QUALITY_STEP

        scale = 1.0 - _SCALE_STEP
        while scale >= _SCALE_MIN:
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            resized = rgb.resize(new_size, Image.LANCZOS)
            buf = io.BytesIO()
            resized.save(buf, format="JPEG", quality=_QUALITY_MIN)
            if buf.tell() <= MAX_PROFILE_IMAGE_SIZE:
                return buf.getvalue()
            scale -= _SCALE_STEP

        buf.seek(0)
        return buf.read()


def get_csv_upload_tmp(csv_upload: Any, run: Run) -> str:
    """Create a temporary file for CSV upload processing.

    Creates a temporary directory structure under MEDIA_ROOT/tmp/event_slug/
    and saves the uploaded CSV file with a timestamp-based filename.

    Args:
        csv_upload: The uploaded CSV file object with chunks() method
        run: Run object containing event information with slug attribute

    Returns:
        str: Full path to the created temporary file

    """
    # Create base temporary directory path
    tmp_file = str(Path(conf_settings.MEDIA_ROOT) / "tmp")

    # Add event-specific subdirectory
    tmp_file = str(Path(tmp_file) / run.event.slug)

    # Ensure directory exists
    if not Path(tmp_file).exists():
        Path(tmp_file).mkdir(mode=0o770, parents=True, exist_ok=True)

    # Generate timestamped filename
    tmp_file = str(Path(tmp_file) / timezone.now().strftime("%Y-%m-%d-%H:%M:%S"))

    # Write uploaded file chunks to temporary file
    with Path(tmp_file).open("wb") as destination:
        destination.writelines(csv_upload.chunks())

    return tmp_file


def cover_load(context: dict, z_obj: Any) -> None:
    """Handle cover image upload and processing from ZIP archive.

    Args:
        context: Context dictionary containing run and event information
        z_obj: ZIP file object containing character cover images

    Side effects:
        Extracts ZIP contents, processes images, updates character cover fields,
        and moves files to proper media directory structure
    """
    # extract images
    fpath = str(Path(conf_settings.MEDIA_ROOT) / "cover_load")
    fpath = str(Path(fpath) / context["run"].event.slug)
    fpath = str(Path(fpath) / str(context["run"].number))
    if Path(fpath).exists():
        shutil.rmtree(fpath)

    safe_extract_zip(z_obj, fpath)
    covers = {}
    # get images
    for root, _dirnames, filenames in os.walk(fpath):
        for el in filenames:
            num = Path(el).stem
            covers[num] = str(Path(root) / el)
    logger.debug("Extracted covers: %s", covers)
    upload_to = UploadToPathAndRename("character/cover/")
    # cicle characters
    for c in get_event_elements(context["run"].event_id, Character, context=context):
        num = str(c.number)
        if num not in covers:
            continue
        fn = upload_to.__call__(c, covers[num])
        c.cover = fn
        c.save()
        Path(covers[num]).rename(Path(conf_settings.MEDIA_ROOT) / fn)
