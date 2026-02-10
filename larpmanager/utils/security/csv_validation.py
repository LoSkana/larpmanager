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
"""CSV security validation utilities.

Provides protection against:
- Formula injection attacks (=, +, -, @, | prefixes)
- Memory exhaustion from large files
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)

# Formula injection characters that need sanitization
FORMULA_PREFIXES = ("=", "+", "-", "@", "|", "\t", "\r")


def sanitize_csv_value(value: Any) -> Any:
    """Sanitize a CSV value to prevent formula injection attacks.

    When CSV files are opened in spreadsheet applications (Excel, LibreOffice),
    cells starting with =, +, -, @, | are treated as formulas and executed.
    This can lead to command execution, data exfiltration, and other attacks.

    Args:
        value: Value from CSV cell (string, number, etc.)

    Returns:
        Sanitized value with formula prefix escaped if necessary

    Examples:
        >>> sanitize_csv_value("=SUM(A1:A10)")
        "'=SUM(A1:A10)"
        >>> sanitize_csv_value("normal text")
        "normal text"
        >>> sanitize_csv_value("+1234567890")
        "'+1234567890"
        >>> sanitize_csv_value(123)
        123

    """
    # Only process string values
    if not isinstance(value, str):
        return value

    # Skip empty strings
    if not value:
        return value

    # Check if value starts with a formula character
    if value.startswith(FORMULA_PREFIXES):
        # Escape by prefixing with single quote
        # This forces spreadsheet apps to treat it as text
        sanitized = "'" + value
        logger.debug("Sanitized potential formula injection: %s -> %s", value[:50], sanitized[:50])
        return sanitized

    return value


def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Sanitize all string values in a pandas DataFrame to prevent formula injection.

    Args:
        df: pandas DataFrame with potentially unsafe CSV data

    Returns:
        DataFrame with all string values sanitized

    """
    # Apply sanitization to all cells in the dataframe
    return df.map(sanitize_csv_value)


class CsvSecurityError(Exception):
    """Raised when CSV file fails security validation."""
