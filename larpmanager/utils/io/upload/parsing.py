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

import re
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pandas as pd

from larpmanager.utils.io.upload.constants import _HTML_TAG_RE, _RELATION_COLUMNS

if TYPE_CHECKING:
    from collections.abc import Callable


def _normalize_numeric(value: str) -> str:
    """Normalize numeric string by replacing comma decimal separator with dot."""
    return str(value).replace(",", ".")


def _to_int(value: str) -> int:
    """Convert numeric string to integer, handling both comma and dot decimal separators."""
    return int(float(_normalize_numeric(value)))


def _to_decimal(value: str) -> Decimal:
    """Convert numeric string to Decimal, handling both comma and dot decimal separators."""
    return Decimal(_normalize_numeric(value))


def _is_missing(value: object) -> bool:
    """Return whether a CSV cell carries no value at all (None or NaN).

    An empty string is not missing: it is an explicit request to clear the field.
    """
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _is_blank(value: object) -> bool:
    """Return whether a CSV cell holds no meaningful text."""
    return not str(value).strip()


def _strip_number_prefix(name: str) -> str:
    """Strip initial '#number ' pattern from name."""
    return re.sub(r"^#\d+\s+", "", name)


def _text_to_html_paragraphs(value: str) -> str:
    """Wrap plain-text lines in <p> tags so line breaks render in HTML fields.

    Lines that already contain HTML markup are left untouched, since uploaders
    sometimes paste pre-formatted HTML for some lines but not others.
    """
    text = str(value).strip()
    if not text:
        return text
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "".join(line if _HTML_TAG_RE.search(line) else f"<p>{line}</p>" for line in lines)


def _relation_value(value: object) -> str:
    """Normalize a relation cell, reading a missing value as empty so that it clears the relation."""
    return "" if _is_missing(value) else str(value)


def _skip_row_field(field_name: str, field_value: object, handled: tuple[str, ...]) -> bool:
    """Return whether a CSV field must be skipped, because already handled or holding no value.

    Relation columns are never skipped: an empty cell there clears the relation.
    """
    if field_name in handled:
        return True
    return field_name not in _RELATION_COLUMNS and _is_missing(field_value)


def _get_row_field(
    csv_row: dict, field_name: str, cast: Callable[[object], Any] = lambda value: value
) -> tuple[Any | None, str | None]:
    """Extract, validate and cast a required CSV column. Returns (value, error) tuple."""
    if field_name not in csv_row:
        return None, f"ERR - There is no {field_name} column"
    raw_value = csv_row[field_name]
    if _is_missing(raw_value):
        return None, f"ERR - Empty {field_name}, row skipped"
    try:
        cast_value = cast(raw_value)
    except (TypeError, ValueError):
        return None, f"ERR - Invalid {field_name} value: {raw_value}"
    if cast_value is None or (isinstance(cast_value, str) and not cast_value):
        return None, f"ERR - Empty {field_name}, row skipped"
    return cast_value, None


def _get_row_name(csv_row: dict) -> tuple[str | None, str | None]:
    """Extract and validate name from a CSV row. Returns (name, error) tuple."""
    return _get_row_field(csv_row, "name", cast=lambda value: str(value).strip())


def _get_row_number(csv_row: dict) -> tuple[int | None, str | None]:
    """Extract and validate number from a CSV row. Returns (number, error) tuple."""
    return _get_row_field(csv_row, "number", cast=int)


def invert_dict(dictionary: dict[str, str]) -> dict[str, str]:
    """Invert dictionary keys and values, normalizing values to lowercase and stripping whitespace."""
    return {value.lower().strip(): key for key, value in dictionary.items()}


def _row_result(status: str, logs: list[str]) -> str:
    """Combine the row status with the errors collected while applying its fields."""
    return "; ".join([status, *logs]) if logs else status
