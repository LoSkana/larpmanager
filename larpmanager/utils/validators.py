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

import os

import magic
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

READ_SIZE = 2048


@deconstructible
class FileTypeValidator:
    """
    File type validator for validating mimetypes and extensions

    Args:
        allowed_types (list): list of acceptable mimetypes e.g; ['image/jpeg', 'application/pdf']
                    see https://www.iana.org/assignments/media-types/media-types.xhtml
        allowed_extensions (list, optional): list of allowed file extensions e.g; ['.jpeg', '.pdf', '.docx']
    """

    type_message = _("File type '%(detected_type)s' is not allowed.Allowed types are: '%(allowed_types)s'.")

    extension_message = _(
        "File extension '%(extension)s' is not allowed. Allowed extensions are: '%(allowed_extensions)s'."
    )

    invalid_message = _(
        "Allowed type '%(allowed_type)s' is not a valid type.See "
        "https://www.iana.org/assignments/media-types/media-types.xhtml"
    )

    def __init__(self, allowed_types: list[str], allowed_extensions: tuple[str, ...] = ()) -> None:
        """Initialize validator with allowed MIME types and file extensions."""
        # Store original input and normalize MIME types
        self.input_allowed_types = allowed_types
        self.allowed_mimes = self._normalize(allowed_types)
        self.allowed_exts = allowed_extensions

    def __call__(self, fileobj) -> None:
        """Validate file type and extension against allowed types.

        Validates the uploaded file by checking both its MIME type (using libmagic)
        and file extension against the configured allowed types and extensions.

        Args:
            fileobj: File object to validate. Must have 'read', 'seek', and 'name' methods.

        Raises:
            ValidationError: If file type is not in allowed_mimes or if extension
                is not in allowed_exts (when extension validation is enabled).

        Note:
            The file position is reset to the beginning after validation to ensure
            the file can be read normally by subsequent operations.
        """
        # Read file header to detect MIME type using libmagic
        detected_type = magic.from_buffer(fileobj.read(READ_SIZE), mime=True)

        # Extract file extension from filename
        root, extension = os.path.splitext(fileobj.name.lower())

        # Reset file position to beginning for subsequent reads
        fileobj.seek(0)

        # Handle libmagic limitations with Office document detection
        # Some versions return generic types instead of specific Office MIME types
        if detected_type in ("application/octet-stream", "application/vnd.ms-office"):
            detected_type = self._check_word_or_excel(fileobj, detected_type, extension)

        # Validate MIME type against allowed types list
        # Check both exact match and category match (e.g., "image/*")
        if detected_type not in self.allowed_mimes and detected_type.split("/")[0] not in self.allowed_mimes:
            raise ValidationError(
                message=self.type_message,
                params={
                    "detected_type": detected_type,
                    "allowed_types": ", ".join(self.input_allowed_types),
                },
                code="invalid_type",
            )

        # Validate file extension if extension checking is enabled
        if self.allowed_exts and (extension not in self.allowed_exts):
            raise ValidationError(
                message=self.extension_message,
                params={
                    "extension": extension,
                    "allowed_extensions": ", ".join(self.allowed_exts),
                },
                code="invalid_extension",
            )

    def _normalize(self, allowed_types):
        """
        Validate and transforms given allowed types
        e.g; wildcard character specification will be normalized as text/* -> text
        """
        allowed_mimes = []
        for allowed_type_orig in allowed_types:
            allowed_type = allowed_type_orig.decode() if type(allowed_type_orig) is bytes else allowed_type_orig
            parts = allowed_type.split("/")
            max_parts = 2
            if len(parts) == max_parts:
                if parts[1] == "*":
                    allowed_mimes.append(parts[0])
                else:
                    allowed_mimes.append(allowed_type)
            else:
                raise ValidationError(
                    message=self.invalid_message,
                    params={"allowed_type": allowed_type},
                    code="invalid_input",
                )

        return allowed_mimes

    @staticmethod
    def _check_word_or_excel(fileobj, detected_type: str, extension: str) -> str:
        """
        Returns proper mimetype in case of word or excel files.

        Args:
            fileobj: File object to analyze
            detected_type: Initially detected MIME type
            extension: File extension (e.g., '.doc', '.xlsx')

        Returns:
            str: Corrected MIME type for Microsoft Office files
        """
        # Define known Microsoft Office file type identifiers
        word_strings = [
            "Microsoft Word",
            "Microsoft Office Word",
            "Microsoft Macintosh Word",
        ]
        excel_strings = [
            "Microsoft Excel",
            "Microsoft Office Excel",
            "Microsoft Macintosh Excel",
        ]
        office_strings = ["Microsoft OOXML"]

        # Read file content to analyze file type details
        file_type_details = magic.from_buffer(fileobj.read(READ_SIZE))

        # Reset file pointer to beginning
        fileobj.seek(0)

        # Check for Word documents based on magic string detection
        if any(string in file_type_details for string in word_strings):
            detected_type = "application/msword"
        # Check for Excel documents based on magic string detection
        elif any(string in file_type_details for string in excel_strings):
            detected_type = "application/vnd.ms-excel"
        # Handle generic Office files or OOXML format - use extension for disambiguation
        elif any(string in file_type_details for string in office_strings) or (
            detected_type == "application/vnd.ms-office"
        ):
            # Determine specific type based on file extension
            if extension in (".doc", ".docx"):
                detected_type = "application/msword"
            if extension in (".xls", ".xlsx"):
                detected_type = "application/vnd.ms-excel"

        return detected_type
