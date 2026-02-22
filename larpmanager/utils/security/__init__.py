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
"""Security utilities for LarpManager."""

from __future__ import annotations

from .csv_validation import CsvSecurityError, sanitize_csv_value, sanitize_dataframe
from .file_validation import FileSecurityError, normalize_filename, safe_filename, validate_file_size
from .zip_validation import ZipSecurityError, safe_extract_zip

__all__ = [
    # CSV validation
    "CsvSecurityError",
    # File validation
    "FileSecurityError",
    # ZIP validation
    "ZipSecurityError",
    "normalize_filename",
    "safe_extract_zip",
    "safe_filename",
    "sanitize_csv_value",
    "sanitize_dataframe",
    "validate_file_size",
]
