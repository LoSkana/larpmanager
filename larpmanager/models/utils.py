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
import string
from datetime import datetime
from html.parser import HTMLParser
from io import StringIO
from uuid import uuid4

from cryptography.fernet import Fernet
from django.conf import settings as conf_settings
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils.deconstruct import deconstructible
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _


def generate_id(length):
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


def decimal_to_str(v):
    s = str(v)
    s = s.replace(".00", "")
    return s


def slug_url_validator(val):
    if not val.islower() or not val.isalnum():
        raise ValidationError(_("Only lowercase characters and numbers are allowed, no spaces or symbols"))


def remove_non_ascii(text):
    max_ascii = 128
    return "".join(char for char in text if ord(char) < max_ascii)


def my_uuid_miny():
    return random.choice(string.ascii_letters) + my_uuid(4)


def my_uuid_short():
    return my_uuid(12)


def my_uuid(length=None):
    s = uuid4().hex
    if length is None:
        return s
    return s[:length]


def download_d(s):
    return download(s)


def download(url):
    s = url
    p = s.rfind("/media/")
    if p >= 0:
        url = s[p:]
    return url


def show_thumb(height, text):
    s = f'<img style="height:{height}px" src="{text}" />'
    return mark_safe(s)


def get_attr(ob, nm):
    if not hasattr(ob, nm):
        return None
    v = getattr(ob, nm)
    if v:
        return v
    return ""


def get_sum(queryset):
    res = queryset.aggregate(Sum("value"))
    if not res or "value__sum" not in res or not res["value__sum"]:
        return 0
    return res["value__sum"]


@deconstructible
class UploadToPathAndRename:
    def __init__(self, sub_path):
        self.sub_path = sub_path

    def __call__(self, instance, filename):
        ext = filename.split(".")[-1].lower()
        filename = f"{uuid4().hex}.{ext}"
        if instance.pk:
            filename = f"{instance.pk}_{filename}"

        path = self.sub_path
        if hasattr(instance, "event") and instance.event:
            path = os.path.join(path, instance.event.slug)
        if hasattr(instance, "run") and instance.run:
            path = os.path.join(path, instance.run.event.slug, str(instance.run.number))
        if hasattr(instance, "album") and instance.album:
            path = os.path.join(path, instance.album.slug)

        new_fn = os.path.join(path, filename)
        # true_fn = os.path.join(conf_settings.MEDIA_ROOT, new_fn)

        if instance.pk:
            bkp_tomove = []
            path_bkp = os.path.join(conf_settings.MEDIA_ROOT, path)
            if os.path.exists(path_bkp):
                for fn in os.listdir(str(path_bkp)):
                    if fn.startswith(f"{instance.pk}_"):
                        bkp_tomove.append(fn)

            for el in bkp_tomove:
                # move to backup previous version
                bkp = os.path.join(conf_settings.MEDIA_ROOT, "bkp", path)
                if not os.path.exists(bkp):
                    os.makedirs(bkp)
                bkp_fn = f"{instance.pk}_{datetime.now()}.{ext}"
                bkp_fn = os.path.join(str(bkp), bkp_fn)
                current_fn = os.path.join(conf_settings.MEDIA_ROOT, path, el)
                # print(bkp)
                # print(bkp_fn)
                os.rename(current_fn, bkp_fn)

        return new_fn


def get_payment_details_path(assoc):
    os.makedirs(conf_settings.PAYMENT_SETTING_FOLDER, exist_ok=True)
    return os.path.join(conf_settings.PAYMENT_SETTING_FOLDER, os.path.basename(assoc.slug) + ".enc")


def get_payment_details(assoc):
    cipher = Fernet(assoc.key)
    encrypted_file_path = get_payment_details_path(assoc)
    if not os.path.exists(encrypted_file_path):
        return {}
    with open(encrypted_file_path, "rb") as f:
        encrypted_data = f.read()
    data_bytes = cipher.decrypt(encrypted_data)
    decrypted_data = json.loads(data_bytes.decode("utf-8"))
    return decrypted_data


def save_payment_details(assoc, payment_details):
    cipher = Fernet(assoc.key)
    data_bytes = json.dumps(payment_details).encode("utf-8")
    encrypted_data = cipher.encrypt(data_bytes)
    encrypted_file_path = get_payment_details_path(assoc)
    with open(encrypted_file_path, "wb") as f:
        f.write(encrypted_data)


def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()


class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = StringIO()

    def handle_data(self, d):
        self.text.write(d)

    def get_data(self):
        return self.text.getvalue()
