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
from uuid import uuid4

from django.conf import settings as conf_settings
from django.shortcuts import render
from PIL import Image

from larpmanager.models.association import Association
from larpmanager.models.member import Badge
from larpmanager.models.miscellanea import Album, AlbumImage, AlbumUpload, WarehouseItem


def upload_albums_dir(main, cache_subs, name):
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
        print(a_name)
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

    ext = u_name.split(".")[-1]
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
    for root, _dirs, files in os.walk(path):
        for file in files:
            ziph.write(
                os.path.join(root, file),
                os.path.relpath(str(os.path.join(root, file)), os.path.join(path, "..")),
            )


def check_centauri(request):
    if "centauri" not in request.assoc["features"]:
        return

    if not _go_centauri(request):
        return

    assoc = Association.objects.get(pk=request.assoc["id"])
    ctx = {}
    for s in ["centauri_descr", "centauri_content"]:
        ctx[s] = assoc.get_config(s, None)

    badge = assoc.get_config("centauri_badge", None)
    if badge:
        bdg = Badge.objects.get(cod=badge)
        bdg.members.add(request.user.member)
        bdg.save()

    return render(request, "larpmanager/general/centauri.html", ctx)


def _go_centauri(request):
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
    assoc = Association.objects.get(pk=ctx["a_id"])
    optionals = {}
    active = 0
    for field in WarehouseItem.get_optional_fields():
        optionals[field] = assoc.get_config(f"warehouse_{field}", False)
        if optionals[field]:
            active = 1
    ctx["optionals"] = optionals
    ctx["no_header_cols"] = json.dumps([el + active for el in def_cols])
