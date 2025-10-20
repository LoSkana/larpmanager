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

    def __init__(self, allowed_types, allowed_extensions=()):
        self.input_allowed_types = allowed_types
        self.allowed_mimes = self._normalize(allowed_types)
        self.allowed_exts = allowed_extensions

    def __call__(self, fileobj) -> None:
        """Validate file type and extension against allowed types.

        Validates both the MIME type (detected via libmagic) and file extension
        against the configured allowed types and extensions. Special handling
        is provided for Microsoft Office files which may be misdetected.

        Args:
            fileobj: File object to validate, must have 'read', 'seek' and 'name' attributes

        Raises:
            ValidationError: If file type or extension is not allowed, with details
                about the detected type and allowed types in error parameters

        Note:
            The file position is reset to the beginning after validation to allow
            subsequent reads without manual seeking.
        """
        # Read initial bytes to detect MIME type via libmagic
        detected_type = magic.from_buffer(fileobj.read(READ_SIZE), mime=True)

        # Extract file extension from filename (case-insensitive)
        root, extension = os.path.splitext(fileobj.name.lower())

        # Reset file position to beginning for subsequent operations
        # This ensures the file can be read normally after validation
        fileobj.seek(0)

        # Handle libmagic detection issues with Microsoft Office files
        # Some versions report generic types instead of specific Office MIME types
        if detected_type in ("application/octet-stream", "application/vnd.ms-office"):
            detected_type = self._check_word_or_excel(fileobj, detected_type, extension)

        # Validate detected MIME type against allowed types
        # Check both exact MIME type and general category (e.g., "image/*")
        if detected_type not in self.allowed_mimes and detected_type.split("/")[0] not in self.allowed_mimes:
            raise ValidationError(
                message=self.type_message,
                params={
                    "detected_type": detected_type,
                    "allowed_types": ", ".join(self.input_allowed_types),
                },
                code="invalid_type",
            )

        # Validate file extension if extension restrictions are configured
        if self.allowed_exts and (extension not in self.allowed_exts):
            raise ValidationError(
                message=self.extension_message,
                params={
                    "extension": extension,
                    "allowed_extensions": ", ".join(self.allowed_exts),
                },
                code="invalid_extension",
            )

    def _normalize(self, allowed_types: list[str | bytes]) -> list[str]:
        """
        Validate and transform given allowed MIME types.

        Wildcard character specifications are normalized (e.g., 'text/*' becomes 'text').

        Args:
            allowed_types: List of MIME type strings or bytes to validate and normalize.
                          Can include wildcards like 'text/*'.

        Returns:
            List of normalized MIME type strings.

        Raises:
            ValidationError: If any MIME type format is invalid (not in 'type/subtype' format).
        """
        allowed_mimes = []

        # Process each allowed type in the input list
        for allowed_type_orig in allowed_types:
            # Convert bytes to string if necessary
            allowed_type = allowed_type_orig.decode() if type(allowed_type_orig) is bytes else allowed_type_orig

            # Split MIME type into parts (type/subtype)
            parts = allowed_type.split("/")
            max_parts = 2

            # Validate MIME type format and normalize wildcards
            if len(parts) == max_parts:
                if parts[1] == "*":
                    # Wildcard subtype: use only the main type (e.g., 'text/*' -> 'text')
                    allowed_mimes.append(parts[0])
                else:
                    # Specific subtype: use full MIME type
                    allowed_mimes.append(allowed_type)
            else:
                # Invalid MIME type format
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
        # Define signature strings for different Microsoft Office applications
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

        # Read file content to detect specific Office application type
        file_type_details = magic.from_buffer(fileobj.read(READ_SIZE))

        # Reset file pointer to beginning for subsequent operations
        fileobj.seek(0)

        # Check for Word document signatures in file content
        if any(string in file_type_details for string in word_strings):
            detected_type = "application/msword"
        # Check for Excel document signatures in file content
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
