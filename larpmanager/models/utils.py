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
import base64
import hashlib
import json
import os
import random
import string
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from io import StringIO
from typing import TYPE_CHECKING
from uuid import uuid4

from cryptography.fernet import Fernet
from django.conf import settings as conf_settings
from django.core.exceptions import ValidationError
from django.db.models import QuerySet, Sum
from django.utils.deconstruct import deconstructible
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from larpmanager.models.association import Association


def generate_id(length):
    """Generate random alphanumeric ID string.

    Args:
        length (int): Length of ID to generate

    Returns:
        str: Random lowercase alphanumeric string of specified length
    """
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


def decimal_to_str(v: Decimal) -> str:
    """Convert decimal to string with .00 removed.

    Takes a Decimal value and converts it to a string representation,
    removing any trailing ".00" to provide cleaner output for whole numbers.

    Args:
        v (Decimal): The decimal value to convert to string format.

    Returns:
        str: String representation of the decimal without trailing ".00".
            For example, Decimal('5.00') becomes '5', while Decimal('5.50')
            becomes '5.50'.

    Example:
        >>> decimal_to_str(Decimal('10.00'))
        '10'
        >>> decimal_to_str(Decimal('10.50'))
        '10.50'
    """
    # Convert decimal to string representation
    s = str(v)
    # Remove trailing .00 for cleaner display of whole numbers
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


def remove_non_ascii(text: str) -> str:
    """Remove non-ASCII characters from text.

    Filters out any characters with ordinal values >= 128, keeping only
    standard ASCII characters (0-127). Useful for sanitizing text data
    or ensuring compatibility with ASCII-only systems.

    Args:
        text: Input text string to filter.

    Returns:
        Filtered string containing only ASCII characters.

    Example:
        >>> remove_non_ascii("Hello 世界!")
        "Hello !"
    """
    # Define ASCII boundary (characters 0-127)
    max_ascii = 128

    # Filter characters using generator expression for memory efficiency
    return "".join(char for char in text if ord(char) < max_ascii)


def my_uuid_miny():
    return random.choice(string.ascii_letters) + my_uuid(4)


def my_uuid_short():
    """Generate short UUID string of 12 characters.

    Returns:
        str: 12-character UUID string
    """
    return my_uuid(12)


def my_uuid(length: int | None = None) -> str:
    """Generate a UUID hex string, optionally truncated to specified length."""
    s = uuid4().hex
    if length is None:
        return s
    return s[:length]


def download_d(s):
    return download(s)


def download(url: str) -> str:
    """Extract media path from URL if present, otherwise return original URL."""
    s = url
    # Find the last occurrence of "/media/" in the URL
    p = s.rfind("/media/")
    # If "/media/" is found, extract the path from that point
    if p >= 0:
        url = s[p:]
    return url


def show_thumb(height: int, text: str) -> SafeString:
    """Generate HTML img tag for thumbnail display.

    Creates an HTML image element with specified height and source URL.
    The image maintains aspect ratio while constraining height.

    Args:
        height: Height in pixels for the image display
        text: URL or file path to the image source

    Returns:
        HTML img tag as a SafeString with specified height and source

    Example:
        >>> show_thumb(100, "/media/image.jpg")
        '<img style="height:100px" src="/media/image.jpg" />'
    """
    # Generate HTML img tag with inline height styling
    s = f'<img style="height:{height}px" src="{text}" />'

    # Return as SafeString to prevent HTML escaping in templates
    return mark_safe(s)


def get_attr(ob: object, nm: str) -> str | None:
    """Get attribute value from object, returning None if missing or empty string if falsy.

    Args:
        ob: Object to get attribute from
        nm: Name of the attribute to retrieve

    Returns:
        Attribute value if truthy, empty string if falsy, None if missing
    """
    # Check if object has the requested attribute
    if not hasattr(ob, nm):
        return None

    # Get the attribute value
    v = getattr(ob, nm)

    # Return value if truthy, otherwise empty string
    if v:
        return v
    return ""


def get_sum(queryset: QuerySet) -> Decimal | int:
    """Sum the 'value' field from a queryset, returning 0 if empty or None."""
    res = queryset.aggregate(Sum("value"))
    # Return 0 if result is None, missing key, or has None value
    if not res or "value__sum" not in res or not res["value__sum"]:
        return 0
    return res["value__sum"]


@deconstructible
class UploadToPathAndRename:
    def __init__(self, sub_path):
        self.sub_path = sub_path

    def __call__(self, instance, filename: str) -> str:
        """
        Generate upload path for file with backup handling.

        Creates a unique filename using UUID and organizes files into directories
        based on instance attributes (event, run, album). When updating existing
        instances, previous files are moved to a backup directory.

        Args:
            instance: Model instance being saved (Event, Run, Album, etc.)
            filename: Original filename from upload

        Returns:
            Generated file path for upload relative to MEDIA_ROOT

        Note:
            Backup files are stored in 'bkp/' subdirectory with timestamp suffix.
        """
        # Extract file extension and generate unique filename
        ext = filename.split(".")[-1].lower()
        filename = f"{uuid4().hex}.{ext}"
        if instance.pk:
            filename = f"{instance.pk}_{filename}"

        # Build directory path based on instance attributes
        path = self.sub_path
        if hasattr(instance, "event") and instance.event:
            path = os.path.join(path, instance.event.slug)
        if hasattr(instance, "run") and instance.run:
            path = os.path.join(path, instance.run.event.slug, str(instance.run.number))
        if hasattr(instance, "album") and instance.album:
            path = os.path.join(path, instance.album.slug)

        # Construct final file path
        new_fn = os.path.join(path, filename)
        # true_fn = os.path.join(conf_settings.MEDIA_ROOT, new_fn)

        # Handle backup of existing files for updates
        if instance.pk:
            bkp_tomove = []
            path_bkp = os.path.join(conf_settings.MEDIA_ROOT, path)

            # Find existing files that match this instance
            if os.path.exists(path_bkp):
                for fn in os.listdir(str(path_bkp)):
                    if fn.startswith(f"{instance.pk}_"):
                        bkp_tomove.append(fn)

            # Move existing files to backup directory
            for el in bkp_tomove:
                # Create backup directory if it doesn't exist
                bkp = os.path.join(conf_settings.MEDIA_ROOT, "bkp", path)
                if not os.path.exists(bkp):
                    os.makedirs(bkp)

                # Generate timestamped backup filename and move file
                bkp_fn = f"{instance.pk}_{datetime.now()}.{ext}"
                bkp_fn = os.path.join(str(bkp), bkp_fn)
                current_fn = os.path.join(conf_settings.MEDIA_ROOT, path, el)
                # print(bkp)
                # print(bkp_fn)
                os.rename(current_fn, bkp_fn)

        return new_fn


def _key_id(fernet_key):
    raw = base64.urlsafe_b64decode(fernet_key)
    return hashlib.sha256(raw).hexdigest()[:12]


def get_payment_details_path(assoc: "Association") -> str:
    """
    Get encrypted payment details file path for association.

    Constructs a secure file path for storing encrypted payment configuration
    data specific to an association. Creates the payment settings directory
    if it doesn't exist and generates a filename using the association's
    slug and encryption key identifier.

    Args:
        assoc: Association instance containing slug and key attributes

    Returns:
        str: Full path to the encrypted payment details file

    Example:
        >>> assoc = Association(slug='my-org', key='secret123')
        >>> path = get_payment_details_path(assoc)
        >>> path
        '/path/to/payment/settings/my-org.abc123.enc'
    """
    # Ensure payment settings directory exists
    os.makedirs(conf_settings.PAYMENT_SETTING_FOLDER, exist_ok=True)

    # Generate key identifier for filename security
    kid = _key_id(assoc.key)

    # Create secure filename with association slug and key ID
    filename = f"{os.path.basename(assoc.slug)}.{kid}.enc"

    # Return full path to encrypted payment file
    return os.path.join(conf_settings.PAYMENT_SETTING_FOLDER, filename)


def save_payment_details(assoc: "Association", payment_details: dict) -> None:
    """
    Encrypt and save payment details for association.

    Args:
        assoc: Association instance with encryption key
        payment_details: Dictionary of payment details to encrypt

    Returns:
        None

    Raises:
        json.JSONEncoder: If payment_details cannot be serialized to JSON
        FileNotFoundError: If the target directory doesn't exist
        PermissionError: If insufficient permissions to write the file
    """
    # Create cipher using association's encryption key
    cipher = Fernet(assoc.key)

    # Convert payment details dictionary to JSON bytes
    data_bytes = json.dumps(payment_details).encode("utf-8")

    # Encrypt the serialized data
    encrypted_data = cipher.encrypt(data_bytes)

    # Get the file path for storing encrypted payment details
    encrypted_file_path = get_payment_details_path(assoc)

    # Write encrypted data to file
    with open(encrypted_file_path, "wb") as f:
        f.write(encrypted_data)


def strip_tags(html: str | None) -> str:
    """Strip HTML tags from text content.

    Args:
        html: HTML string to process. Can be None or empty string.

    Returns:
        Plain text with HTML tags removed. Returns empty string if input
        is None or empty.

    Example:
        >>> strip_tags("<p>Hello <b>world</b></p>")
        "Hello world"
        >>> strip_tags(None)
        ""
    """
    # Handle None and empty string cases early
    if html is None or html == "":
        return ""

    # Create MLStripper instance and process HTML
    s = MLStripper()
    s.feed(html)

    # Return the stripped text content
    return s.get_data()


class MLStripper(HTMLParser):
    def __init__(self) -> None:
        """Initialize the HTML parser with default settings."""
        super().__init__()
        # Reset parser state to initial conditions
        self.reset()
        # Configure parser behavior
        self.strict = False
        self.convert_charrefs = True
        # Initialize text buffer for content extraction
        self.text = StringIO()

    def handle_data(self, d):
        self.text.write(d)

    def get_data(self):
        return self.text.getvalue()
