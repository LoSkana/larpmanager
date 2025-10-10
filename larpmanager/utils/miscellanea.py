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
from uuid import uuid4

from django.conf import settings as conf_settings
from django.core.files.base import ContentFile
from django.db import models
from django.shortcuts import render
from PIL import Image, ImageOps
from PIL import Image as PILImage

from larpmanager.cache.config import get_assoc_config
from larpmanager.models.member import Badge
from larpmanager.models.miscellanea import Album, AlbumImage, AlbumUpload, WarehouseItem


def upload_albums_dir(main, cache_subs, name):
    """Create or find album directory structure for uploaded files.

    Args:
        main: Main album instance
        cache_subs (dict): Cache of subdirectory albums
        name (str): Directory path from zip file

    Returns:
        Album: Album instance for the directory

    Side effects:
        Creates new Album instances for directories as needed
    """
    name = os.path.dirname(name)
    if name not in cache_subs:
        parent = os.path.dirname(name)
        if not parent or parent == "":
            parent = main
        else:
            parent = cache_subs[parent]
        # search if sub album of parent with same name exists
        album = None
        a_name = os.path.basename(name)

        for a in parent.sub_albums.all():
            if a.name == a_name:
                album = a
        if not album:
            album = Album()
            album.cod = uuid4().hex
            album.name = a_name
            album.parent = parent
            album.run = main.run
            album.save()
        cache_subs[name] = album
    return cache_subs[name]


def upload_albums_el(f, alb, name, main, o_path):
    """Upload individual file from zip archive to album.

    Args:
        f: Zip file object
        alb: Album instance to upload to
        name (str): File name from zip archive
        main: Main album instance
        o_path (str): Output path for extraction

    Side effects:
        Creates AlbumUpload and AlbumImage records, moves files to media directory
    """
    # check if exists already
    u_name = os.path.basename(name)
    for u in alb.uploads.all():
        if u.name == u_name:
            return

            # check if image
    upl = AlbumUpload()
    upl.album = alb
    upl.name = u_name
    upl.typ = AlbumUpload.PHOTO
    upl.save()

    img = AlbumImage()
    img.upload = upl

    parts = u_name.split(".")
    ext = parts[-1] if len(parts) > 1 and parts[-1] else "tmp"
    filename = f"{uuid4().hex}.{ext}"

    fpath = os.path.join(conf_settings.MEDIA_ROOT, "albums")
    fpath = os.path.join(fpath, main.run.event.slug)
    fpath = os.path.join(fpath, str(main.run.number))
    par = alb.parent
    dirs = []
    while par is not None:
        dirs.append(par.id)
        par = par.parent
    dirs.reverse()
    for el in dirs:
        fpath = os.path.join(fpath, str(el))
        if not os.path.exists(fpath):
            os.makedirs(fpath)
    fpath = os.path.join(fpath, filename)
    print(fpath)

    os.rename(os.path.join(o_path, name), fpath)

    img.original = fpath
    with Image.open(fpath) as i:
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


def check_centauri(request):
    """Check and display Centauri easter egg feature.

    Random chance to show special content and award badges to users.

    Args:
        request: Django HTTP request with user and association context

    Returns:
        HttpResponse or None: Centauri page response if triggered, None otherwise

    Side effects:
        May award badge to user if Centauri is triggered
    """
    if "centauri" not in request.assoc["features"]:
        return

    if not _go_centauri(request):
        return

    ctx = {}
    for s in ["centauri_descr", "centauri_content"]:
        ctx[s] = get_assoc_config(request.assoc["id"], s, None)

    badge = get_assoc_config(request.assoc["id"], "centauri_badge", None)
    if badge:
        bdg = Badge.objects.get(cod=badge)
        bdg.members.add(request.user.member)
        bdg.save()

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


def get_warehouse_optionals(ctx, def_cols):
    """Get warehouse optional field configuration for display.

    Args:
        ctx (dict): Context dictionary to update
        def_cols (list): Default column configuration

    Side effects:
        Updates ctx with optionals configuration and header column settings
    """
    optionals = {}
    active = 0
    for field in WarehouseItem.get_optional_fields():
        optionals[field] = get_assoc_config(ctx["a_id"], f"warehouse_{field}", False)
        if optionals[field]:
            active = 1
    ctx["optionals"] = optionals
    ctx["no_header_cols"] = json.dumps([el + active for el in def_cols])


def auto_rotate_vertical_photos(instance, sender):
    """Automatically rotate vertical photos to landscape orientation.

    Args:
        instance: Model instance with a 'photo' ImageField
        sender: Model class that sent the signal
    """
    try:
        # noinspection PyProtectedMember, PyUnresolvedReferences
        field = instance._meta.get_field("photo")
        if not isinstance(field, models.ImageField):
            return
    except Exception:
        return

    f = getattr(instance, "photo", None)
    if not f:
        return

    if _check_new(f, instance, sender):
        return

    fileobj = getattr(f, "file", None) or f
    try:
        fileobj.seek(0)
        img = PILImage.open(fileobj)
    except Exception:
        return

    img = ImageOps.exif_transpose(img)
    w, h = img.size
    if h <= w:
        return

    img = img.rotate(90, expand=True)

    fmt = _get_extension(f, img)

    if fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")

    out = BytesIO()
    save_kwargs = {"optimize": True}
    if fmt == "JPEG":
        save_kwargs["quality"] = 88
    img.save(out, format=fmt, **save_kwargs)
    out.seek(0)

    basename = os.path.basename(f.name) or f.name
    instance.photo = ContentFile(out.read(), name=basename)


def _get_extension(f, img):
    ext = os.path.splitext(f.name)[1].lower()
    fmt = (img.format or "").upper()
    if not fmt:
        if ext in (".jpg", ".jpeg"):
            fmt = "JPEG"
        elif ext == ".png":
            fmt = "PNG"
        elif ext == ".webp":
            fmt = "WEBP"
        else:
            fmt = "JPEG"
    return fmt


def _check_new(f, instance, sender):
    if instance.pk:
        try:
            old = sender.objects.filter(pk=instance.pk).only("photo").first()
            if old:
                old_name = old.photo.name if old.photo else ""
                if f.name == old_name and not getattr(f, "file", None):
                    return True
        except Exception:
            pass

    return False
