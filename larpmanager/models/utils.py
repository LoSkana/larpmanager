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
    """Generate random alphanumeric ID string.

    Args:
        length (int): Length of ID to generate

    Returns:
        str: Random lowercase alphanumeric string of specified length
    """
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


def decimal_to_str(v):
    """Convert decimal to string with .00 removed.

    Args:
        v (Decimal): Decimal value to convert

    Returns:
        str: String representation without trailing .00
    """
    s = str(v)
    s = s.replace(".00", "")
    return s


def slug_url_validator(val):
    """Validate that string contains only lowercase alphanumeric characters.

    Args:
        val (str): String to validate

    Raises:
        ValidationError: If string contains invalid characters
    """
    if not val.islower() or not val.isalnum():
        raise ValidationError(_("Only lowercase characters and numbers are allowed, no spaces or symbols"))


def remove_non_ascii(text):
    """Remove non-ASCII characters from text.

    Args:
        text (str): Input text

    Returns:
        str: Text with only ASCII characters (ordinal < 128)
    """
    max_ascii = 128
    return "".join(char for char in text if ord(char) < max_ascii)


def my_uuid_miny():
    return random.choice(string.ascii_letters) + my_uuid(4)


def my_uuid_short():
    """Generate short UUID string of 12 characters.

    Returns:
        str: 12-character UUID string
    """
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
    """Generate HTML img tag for thumbnail display.

    Args:
        height (int): Height in pixels for the image
        text (str): URL or path to the image

    Returns:
        SafeString: HTML img tag with specified height and source
    """
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
        """
        Generate upload path for file with backup handling.

        Args:
            instance: Model instance being saved
            filename: Original filename

        Returns:
            str: Generated file path for upload
        """
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
    """
    Get encrypted payment details file path for association.

    Args:
        assoc: Association instance

    Returns:
        str: Path to encrypted payment details file
    """
    os.makedirs(conf_settings.PAYMENT_SETTING_FOLDER, exist_ok=True)
    return os.path.join(conf_settings.PAYMENT_SETTING_FOLDER, os.path.basename(assoc.slug) + ".enc")


def save_payment_details(assoc, payment_details):
    """
    Encrypt and save payment details for association.

    Args:
        assoc: Association instance with encryption key
        payment_details: Dictionary of payment details to encrypt
    """
    cipher = Fernet(assoc.key)
    data_bytes = json.dumps(payment_details).encode("utf-8")
    encrypted_data = cipher.encrypt(data_bytes)
    encrypted_file_path = get_payment_details_path(assoc)
    with open(encrypted_file_path, "wb") as f:
        f.write(encrypted_data)


def strip_tags(html):
    """
    Strip HTML tags from text content.

    Args:
        html: HTML string to process

    Returns:
        str: Plain text with HTML tags removed
    """
    if html is None or html == "":
        return ""
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
