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
"""ZIP file security validation and safe extraction utilities.

Provides protection against:
- Path traversal attacks (malicious paths with ../ or absolute paths)
- ZIP bomb attacks (files with extreme compression ratios)
- Resource exhaustion (excessive file counts or total size)
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)

# Security limits for ZIP extraction
MAX_ARCHIVE_SIZE = 100 * 1024 * 1024  # 100 MB total uncompressed size
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB per individual file
MAX_FILE_COUNT = 1000  # Maximum number of files in archive
MAX_COMPRESSION_RATIO = 100  # Maximum allowed compression ratio (uncompressed/compressed)


class ZipSecurityError(Exception):
    """Raised when a ZIP file fails security validation."""


def _validate_zip_path(member_name: str, extraction_path: Path) -> None:
    """Validate that a ZIP member path is safe for extraction.

    Args:
        member_name: Name/path of the ZIP member to validate
        extraction_path: Base directory where extraction will occur

    Raises:
        ZipSecurityError: If the path contains directory traversal or absolute path components

    """
    # Check for absolute paths
    if member_name.startswith(("/", "\\")):
        msg = f"Absolute path detected in ZIP: {member_name}"
        raise ZipSecurityError(msg)

    # Check for directory traversal
    if ".." in Path(member_name).parts:
        msg = f"Directory traversal detected in ZIP: {member_name}"
        raise ZipSecurityError(msg)

    # Verify resolved path is within extraction directory
    member_path = Path(extraction_path) / member_name
    try:
        resolved_path = member_path.resolve()
        extraction_path_resolved = Path(extraction_path).resolve()

        # Check if the resolved path is within the extraction directory
        if not str(resolved_path).startswith(str(extraction_path_resolved)):
            msg = f"Path traversal attempt detected: {member_name} resolves outside extraction directory"
            raise ZipSecurityError(msg)
    except (OSError, RuntimeError) as e:
        msg = f"Error resolving path for {member_name}: {e}"
        raise ZipSecurityError(msg) from e


def _validate_zip_bomb(zip_file: zipfile.ZipFile) -> None:
    """Validate ZIP file against bomb/resource exhaustion attacks.

    Args:
        zip_file: ZipFile object to validate

    Raises:
        ZipSecurityError: If the ZIP file exceeds security limits

    """
    total_uncompressed_size = 0
    file_count = 0

    for info in zip_file.infolist():
        # Skip directories
        if info.is_dir():
            continue

        file_count += 1

        # Check file count limit
        if file_count > MAX_FILE_COUNT:
            msg = f"ZIP contains too many files (>{MAX_FILE_COUNT})"
            raise ZipSecurityError(msg)

        # Check individual file size
        if info.file_size > MAX_FILE_SIZE:
            msg = f"File too large in ZIP: {info.filename} ({info.file_size} bytes > {MAX_FILE_SIZE} bytes)"
            raise ZipSecurityError(msg)

        # Check compression ratio to detect ZIP bombs
        if info.compress_size > 0:
            compression_ratio = info.file_size / info.compress_size
            if compression_ratio > MAX_COMPRESSION_RATIO:
                msg = (
                    f"Suspicious compression ratio for {info.filename}: "
                    f"{compression_ratio:.1f}x (>{MAX_COMPRESSION_RATIO}x)"
                )
                raise ZipSecurityError(msg)

        # Track total uncompressed size
        total_uncompressed_size += info.file_size

        # Check total size limit
        if total_uncompressed_size > MAX_ARCHIVE_SIZE:
            msg = f"ZIP total uncompressed size too large (>{MAX_ARCHIVE_SIZE} bytes)"
            raise ZipSecurityError(msg)

    logger.info(
        "ZIP validation passed: %d files, %d bytes uncompressed",
        file_count,
        total_uncompressed_size,
    )


def safe_extract_zip(zip_file: zipfile.ZipFile | Any, extraction_path: str | Path) -> None:
    """Safely extract a ZIP file with security validations.

    Validates against:
    - Path traversal attacks
    - ZIP bomb attacks
    - Resource exhaustion

    Args:
        zip_file: ZipFile object or path to ZIP file
        extraction_path: Directory where files will be extracted

    Raises:
        ZipSecurityError: If security validation fails
        ValueError: If inputs are invalid

    """
    # Convert extraction path to Path object
    extraction_path = Path(extraction_path)

    # Ensure extraction path is absolute
    if not extraction_path.is_absolute():
        msg = "Extraction path must be absolute"
        raise ValueError(msg)

    # Create extraction directory if it doesn't exist
    extraction_path.mkdir(parents=True, exist_ok=True)

    # Open ZIP file if path was provided
    if isinstance(zip_file, (str, Path)):
        with zipfile.ZipFile(zip_file, "r") as zf:
            _safe_extract_zip_impl(zf, extraction_path)
    else:
        _safe_extract_zip_impl(zip_file, extraction_path)


def _safe_extract_zip_impl(zip_file: zipfile.ZipFile, extraction_path: Path) -> None:
    """Internal implementation of safe ZIP extraction.

    Args:
        zip_file: Open ZipFile object
        extraction_path: Path object for extraction directory

    Raises:
        ZipSecurityError: If security validation fails

    """
    # Validate against ZIP bombs and resource exhaustion
    _validate_zip_bomb(zip_file)

    # Validate and extract each member
    for member in zip_file.namelist():
        # Validate path safety
        _validate_zip_path(member, extraction_path)

        # Extract the member
        zip_file.extract(member, path=extraction_path)

    logger.info("Successfully extracted ZIP to %s", extraction_path)
