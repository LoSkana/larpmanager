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
"""File upload security validation utilities.

Provides protection against:
- Memory exhaustion from large files
- Unicode filename attacks (lookalike characters)
"""

from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)


class FileSecurityError(Exception):
    """Raised when file upload fails security validation."""


def validate_file_size(uploaded_file: Any, max_size: int | None = None) -> None:
    """Validate that uploaded file size is within acceptable limits.

    Args:
        uploaded_file: Django UploadedFile object with size attribute
        max_size: Maximum allowed file size in bytes (uses settings.MAX_UPLOAD_SIZE if None)

    Raises:
        FileSecurityError: If file is too large or size cannot be determined

    """
    # Use configured max size or default
    if max_size is None:
        max_size = getattr(settings, "MAX_UPLOAD_SIZE", 10 * 1024 * 1024)  # 10MB default

    # Check if file has size attribute
    if not hasattr(uploaded_file, "size"):
        # Try to get size from file object
        if hasattr(uploaded_file, "file") and hasattr(uploaded_file.file, "size"):
            file_size = uploaded_file.file.size
        else:
            msg = "Cannot determine file size"
            raise FileSecurityError(msg)
    else:
        file_size = uploaded_file.size

    # Validate size
    if file_size > max_size:
        msg = f"File size {file_size} bytes exceeds maximum allowed {max_size} bytes"
        raise FileSecurityError(msg)

    logger.debug("File size validation passed: %d bytes (max: %d bytes)", file_size, max_size)


def normalize_filename(filename: str) -> str:
    """Normalize Unicode filename to prevent lookalike character attacks.

    Unicode contains many visually similar characters that can be used to bypass
    file extension filters.

    This function uses NFKC normalization which:
    - Decomposes characters to their base forms
    - Applies compatibility decomposition
    - Recomposes to canonical form

    Args:
        filename: Original filename with potentially ambiguous Unicode

    Returns:
        Normalized filename with lookalikes converted to standard ASCII equivalents

    References:
        - https://unicode.org/reports/tr15/
        - https://owasp.org/www-community/attacks/Unicode_Encoding

    """
    # Apply NFKC (Compatibility Decomposition, followed by Canonical Composition)
    normalized = unicodedata.normalize("NFKC", filename)

    # Log if normalization changed the filename
    if normalized != filename:
        logger.warning(
            "Filename normalized for security: '%s' -> '%s'",
            filename[:100],
            normalized[:100],
        )

    return normalized


def safe_filename(filename: str, max_length: int = 255) -> str:
    """Create a safe filename by normalizing Unicode and limiting length.

    Args:
        filename: Original filename
        max_length: Maximum allowed filename length (default: 255 for most filesystems)

    Returns:
        Safe filename suitable for storage

    """
    # Normalize Unicode to prevent lookalike attacks
    normalized = normalize_filename(filename)

    # Truncate if too long, preserving extension
    if len(normalized) > max_length:
        path = Path(normalized)
        stem = path.stem
        suffix = path.suffix  # Includes the dot (e.g., ".txt")

        # Calculate how much we can keep of the stem
        # suffix already includes the dot, so no need to subtract 1
        max_stem_length = max_length - len(suffix)
        if max_stem_length > 0:
            truncated_stem = stem[:max_stem_length]
            normalized = truncated_stem + suffix
            logger.warning("Filename truncated: '%s' -> '%s'", filename[:100], normalized[:100])
        else:
            # Extension itself is too long, just truncate everything
            normalized = normalized[:max_length]
            logger.warning("Filename heavily truncated: '%s' -> '%s'", filename[:100], normalized[:100])

    return normalized
