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

import csv
import re
import unicodedata
from pathlib import Path
from typing import Any

from django.conf import settings as conf_settings


def _clean_birth_place(birth_place: str | None) -> str:
    """Remove parenthetical content from birth place string."""
    if not birth_place:
        return ""
    # Remove everything in parenthesis
    return re.sub(r"\(.*?\)", "", birth_place)


def _slugify(input_text: Any) -> Any:
    """Normalize text for fiscal code generation by removing accents and special characters.

    Args:
        input_text: Input text to be normalized

    Returns:
        str: Normalized text with accents removed, lowercased, and special characters replaced

    """
    # Remove accents
    normalized_text = input_text
    for accented_char in ["à", "è", "é", "ì", "ò", "ù"]:
        normalized_text = normalized_text.replace(accented_char, "")
    # Normalize text to remove accents and convert to ASCII
    normalized_text = unicodedata.normalize("NFKD", normalized_text).encode("ascii", "ignore").decode("ascii")
    # Convert text to lowercase
    normalized_text = normalized_text.lower()
    # Remove quotes
    normalized_text = normalized_text.replace('"', "").replace("'", "")
    # Replace any non-alphanumeric character (excluding hyphens) with a space
    normalized_text = re.sub(r"[^a-z0-9\s-]", "", normalized_text)
    # Replace any sequence of whitespace or hyphens with a single hyphen
    normalized_text = re.sub(r"[\s-]+", "-", normalized_text)
    # Strip leading and trailing hyphens
    return normalized_text.strip("-")


def _extract_municipality_code(birth_place: str) -> str:
    """Extract municipality code from birth place name using ISTAT data.

    This function searches for ISTAT codes by first checking against nation codes,
    then municipality codes with exact matching, and finally partial matching.

    Args:
        birth_place (str): Name of the birth place (city/nation) to look up.

    Returns:
        str: ISTAT code for the municipality, or empty string if not found.

    Note:
        The function performs case-insensitive matching using slugified names.
        It searches first in nations data, then in municipality codes with
        exact and partial matching strategies.

    """
    # Convert birth place to slugified format for consistent matching
    slugified_birth_place = _slugify(birth_place)

    # First search: Look for exact matches in nations data
    nations_file_path = Path(conf_settings.BASE_DIR) / ".." / "data" / "istat-nations.csv"
    with nations_file_path.open() as nations_file:
        nations_reader = csv.reader(nations_file)
        # Search for exact nation name matches
        for nation_row in nations_reader:
            if slugified_birth_place == _slugify(nation_row[0]):
                return nation_row[1]

    # Second search: Look in municipality codes file
    municipalities_file_path = Path(conf_settings.BASE_DIR) / ".." / "data" / "istat-codes.csv"
    with municipalities_file_path.open() as municipalities_file:
        municipalities_reader = csv.reader(municipalities_file)
        # First pass: Search for exact matches in split municipality names
        for municipality_row in municipalities_reader:
            for municipality_name_variant in municipality_row[0].split("/"):
                if slugified_birth_place == _slugify(municipality_name_variant):
                    return municipality_row[1]

        # Second pass: Search for partial matches in municipality names
        for municipality_row in municipalities_reader:
            if slugified_birth_place in _slugify(municipality_row[0]):
                return municipality_row[1]

    # Return empty string if no match found in any dataset
    return ""


def get_province_for_birth_place(birth_place: str | None) -> str:
    """Look up the Italian province code (sigla) for a birth place, by exact comune name match.

    Args:
        birth_place (str | None): Name of the birth place (city) to look up.

    Returns:
        str: Province sigla (e.g. "MI"), or empty string if not found.

    """
    if not birth_place:
        return ""

    slugified_birth_place = _slugify(_clean_birth_place(birth_place))

    comuni_file_path = Path(conf_settings.BASE_DIR) / ".." / "data" / "Elenco-comuni-italiani.csv"
    with comuni_file_path.open(encoding="utf-8") as comuni_file:
        comuni_reader = csv.reader(comuni_file)
        next(comuni_reader)  # skip header
        for comune_row in comuni_reader:
            if slugified_birth_place == _slugify(comune_row[5]):
                return comune_row[14]

    return ""
