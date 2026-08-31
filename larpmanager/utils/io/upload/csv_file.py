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
from typing import Any

import pandas as pd

from larpmanager.utils.io.download import _get_column_names
from larpmanager.utils.io.upload.constants import MAX_CSV_FILE_SIZE
from larpmanager.utils.security import FileSecurityError, sanitize_dataframe, validate_file_size

logger = logging.getLogger(__name__)


def _read_uploaded_csv(uploaded_file: Any) -> pd.DataFrame | None:
    """Read CSV file with multiple encoding fallbacks.

    Attempts to read a CSV file using various character encodings to handle
    files from different sources and systems. Falls back through common
    encodings until successful parsing or all options are exhausted.

    Args:
        uploaded_file: Django uploaded file object containing CSV data.

    Returns:
        pandas.DataFrame or None: Parsed CSV data with all columns as strings,
            or None if parsing failed with all attempted encodings.

    """
    # Early return if no file provided
    if not uploaded_file:
        return None

    # SECURITY: Validate file size to prevent memory exhaustion
    try:
        validate_file_size(uploaded_file)
    except FileSecurityError:
        logger.exception("File size validation failed: %s")
        return None

    # Define encoding priority list - most common first
    encodings = [
        "utf-8-sig",
        "utf-8",
        "latin1",
        "windows-1252",
        "utf-16",
        "utf-32",
        "ascii",
        "mac-roman",
        "cp437",
        "cp850",
    ]

    # Try each encoding until one succeeds
    for encoding in encodings:
        try:
            # Reset file pointer to beginning
            uploaded_file.seek(0)

            # Read with size limit already validated above (prevent issues with compressed data)
            file_content = uploaded_file.read()

            # Decode file content with current encoding
            decoded_content = file_content.decode(encoding)
            string_buffer = io.StringIO(decoded_content)

            # Parse CSV with automatic delimiter detection
            df = pd.read_csv(string_buffer, encoding=encoding, sep=None, engine="python", dtype=str)

            # Sanitize all values to prevent formula injection
            return sanitize_dataframe(df)

        except Exception as parsing_error:  # noqa: BLE001 - Must try all encodings on any parsing error
            # Log error and continue to next encoding
            logger.debug("Failed to parse CSV with encoding %s: %s", encoding, parsing_error)
            continue

    # Return None if all encodings failed
    return None


def _get_file(context: dict, file: Any, column_id: int | None = None) -> tuple[pd.DataFrame | None, list[str]]:
    """Get file path and save uploaded file to media directory.

    Args:
        context: Context dictionary containing event information and column definitions.
        file: Uploaded file object to be processed.
        column_id: Optional column identifier for file naming. Defaults to None.

    Returns:
        A tuple containing:
            - DataFrame: Processed pandas DataFrame if successful, None if failed.
            - list[str]: List of error messages, empty if no errors occurred.

    Note:
        Function validates that all columns in the uploaded CSV are recognized
        based on the context configuration.

    """
    # Check if file was provided
    if not file:
        return None, ["ERR - No file provided. Please select a file to upload"]

    # Check file size before parsing to prevent memory exhaustion
    file_size = getattr(file, "size", None)
    if file_size is None and hasattr(file, "file"):
        file_size = getattr(file.file, "size", None)
    if file_size is not None and file_size > MAX_CSV_FILE_SIZE:
        max_mb = MAX_CSV_FILE_SIZE / (1024 * 1024)
        actual_mb = file_size / (1024 * 1024)
        return None, [f"ERR - File too large: {actual_mb:.1f}MB exceeds limit of {max_mb:.0f}MB"]

    # Get available column names from context
    _get_column_names(context)
    allowed_column_names = []

    # Add columns from specific column_id if provided
    if column_id is not None:
        allowed_column_names.extend(list(context["columns"][column_id].keys()))

    # Add fields from context if available
    if "fields" in context:
        allowed_column_names.extend(context["fields"].keys())

    # Add columns accepted on upload but not shown in the template
    allowed_column_names.extend(context.get("extra_columns", []))

    # Convert all allowed column names to lowercase for comparison
    allowed_column_names = [column_name.lower() for column_name in allowed_column_names]

    # Read and parse the uploaded CSV file
    input_dataframe = _read_uploaded_csv(file)
    if input_dataframe is None:
        return None, ["ERR - Could not parse the uploaded file. Please check the file format and encoding"]

    # Normalize column names to lowercase for validation
    input_dataframe.columns = [column.lower() for column in input_dataframe.columns]

    # Drop the columns that are not recognized, reporting them once instead of on every row
    not_recognized = [column for column in input_dataframe.columns if column.lower() not in allowed_column_names]
    logs = []
    if not_recognized:
        logs.append(f"WARN - columns ignored: {', '.join(not_recognized)}")
        input_dataframe = input_dataframe.drop(columns=not_recognized)

    return input_dataframe, logs
