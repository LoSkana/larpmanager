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

from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy as _

from larpmanager.utils.users.member import almost_equal, count_differences
from larpmanager.utils.users.municipalities import _clean_birth_place, _extract_municipality_code

if TYPE_CHECKING:
    from datetime import date

    from larpmanager.models.member import Member


def calculate_fiscal_code(member: Any) -> Any:
    """Calculate and validate Italian fiscal code for a member.

    Args:
        member: Member object with personal data for fiscal code calculation

    Returns:
        dict: Dictionary containing fiscal code validation results

    """
    # ignore non-italian citizens
    if member.nationality and member.nationality.lower() != "it":
        return {}
    if member.fiscal_code and member.fiscal_code.lower() == "n/a":
        return {}

    primary_validation_result = _go(member, male=True)

    # If the first try didn't work, try if the user has to indicate the gender female
    if not primary_validation_result["correct_cf"]:
        secondary_validation_result = _go(member, male=False)
        if secondary_validation_result["correct_cf"]:
            return secondary_validation_result

    return primary_validation_result


def _calculate_consonants(fiscal_code_string: str) -> str:
    """Extract consonants from string, excluding vowels and accented vowels."""
    return "".join([c for c in fiscal_code_string if c.isalpha() and c not in "AEIOUÀÈÉÌÒÙ"])


def _calculate_vowels(text: str) -> str:
    """Extract and concatenate all uppercase vowels from text."""
    return "".join([character for character in text if character in "AEIOU"])


def _extract_last_name(last_name: str) -> str:
    """Extract 3-character code from last name using consonants, vowels, and padding."""
    # Convert to uppercase for consistent processing
    normalized_last_name = last_name.upper()

    # Extract consonants and vowels from the name
    consonants = _calculate_consonants(normalized_last_name)
    vowels = _calculate_vowels(normalized_last_name)

    # Combine and pad with 'X' if needed, then take first 3 characters
    return (consonants + vowels + "XXX")[:3]


def _extract_first_name(first_name: str) -> str:
    """Extract first 3 characters from first name using consonants and vowels.

    Args:
        first_name: The first name to process.

    Returns:
        A 3-character string extracted from the first name.

    """
    normalized_name = first_name.upper()

    # Calculate consonants and limit to first 4
    consonants = _calculate_consonants(normalized_name)
    maximum_consonants = 4
    if len(consonants) >= maximum_consonants:
        consonants = consonants[0] + consonants[2] + consonants[3]

    # Add vowels and pad with X if needed
    vowels = _calculate_vowels(normalized_name)
    return (consonants + vowels + "XXX")[:3]


def _extract_birth_date(birth_date: date | None, *, male: bool) -> str:
    """Extract birth date in fiscal code format.

    Args:
        birth_date: The birth date to extract from
        male: Whether the person is male (affects day calculation)

    Returns:
        Formatted birth date string (YYMDD format)

    """
    month_codes = "ABCDEHLMPRST"
    if not birth_date:
        return ""

    # Extract last two digits of year
    year_two_digits = str(birth_date.year)[-2:]

    # Get month code from lookup table
    month_code = month_codes[birth_date.month - 1]

    # Add 40 to day for females, keep original for males
    day_with_gender_offset = birth_date.day + (40 if not male else 0)

    return f"{year_two_digits}{month_code}{str(day_with_gender_offset).zfill(2)}"


def _calculate_check_digit(cf_without_check_digit: str) -> str:
    """Calculate the check digit for Italian fiscal codes (Codice Fiscale).

    Implements the official Italian algorithm using lookup tables for even and odd
    position character values to compute the final check digit according to the
    Ministry of Finance specifications.

    Args:
        cf_without_check_digit: 15-character fiscal code without check digit
                                (format: AAABBB00A00A000)

    Returns:
        Single character check digit (A-Z) to complete the 16-character fiscal code

    """
    # Lookup table for characters in even positions (0-indexed: 1, 3, 5, etc.)
    # Maps each alphanumeric character to its numeric value for checksum calculation
    even_position_values = {
        "0": 0,
        "1": 1,
        "2": 2,
        "3": 3,
        "4": 4,
        "5": 5,
        "6": 6,
        "7": 7,
        "8": 8,
        "9": 9,
        "A": 0,
        "B": 1,
        "C": 2,
        "D": 3,
        "E": 4,
        "F": 5,
        "G": 6,
        "H": 7,
        "I": 8,
        "J": 9,
        "K": 10,
        "L": 11,
        "M": 12,
        "N": 13,
        "O": 14,
        "P": 15,
        "Q": 16,
        "R": 17,
        "S": 18,
        "T": 19,
        "U": 20,
        "V": 21,
        "W": 22,
        "X": 23,
        "Y": 24,
        "Z": 25,
    }

    # Lookup table for characters in odd positions (0-indexed: 0, 2, 4, etc.)
    # Uses different values than even positions as per fiscal code specification
    odd_position_values = {
        "0": 1,
        "1": 0,
        "2": 5,
        "3": 7,
        "4": 9,
        "5": 13,
        "6": 15,
        "7": 17,
        "8": 19,
        "9": 21,
        "A": 1,
        "B": 0,
        "C": 5,
        "D": 7,
        "E": 9,
        "F": 13,
        "G": 15,
        "H": 17,
        "I": 19,
        "J": 21,
        "K": 2,
        "L": 4,
        "M": 18,
        "N": 20,
        "O": 11,
        "P": 3,
        "Q": 6,
        "R": 8,
        "S": 12,
        "T": 14,
        "U": 16,
        "V": 10,
        "W": 22,
        "X": 25,
        "Y": 24,
        "Z": 23,
    }

    # Calculate weighted sum of all characters
    weighted_sum = 0
    for position_index, character in enumerate(cf_without_check_digit):
        # Even positions (1, 3, 5, ...) use even_position_values table
        if position_index % 2 == 1 and character in even_position_values:
            weighted_sum += even_position_values[character]
        # Odd positions (0, 2, 4, ...) use odd_position_values table
        elif character in odd_position_values:
            weighted_sum += odd_position_values[character]

    # Convert the modulo 26 result to a letter (A=0, B=1, ..., Z=25)
    return chr((weighted_sum % 26) + ord("A"))


def _go(member: Member, *, male: bool = True) -> dict[str, Any]:  # noqa: C901 - Complex fiscal code generation algorithm
    """Generate Italian fiscal code for a member and validate against existing code.

    Implements the complete fiscal code algorithm including name/surname processing,
    date encoding, and municipality code lookup. Validates the generated code against
    the member's existing fiscal code and provides detailed error messages.

    Args:
        member: Member instance with personal information for fiscal code generation.
                Must have attributes: legal_name, name, surname, birth_date,
                birth_place, fiscal_code.
        male: Gender flag for date encoding. True for male, False for female.
              Defaults to True.

    Returns:
        Dictionary containing validation results with keys:
            - membership_cf (bool): Always True, indicates fiscal code context
            - calculated_cf (str): Generated fiscal code
            - supplied_cf (str): Member's existing fiscal code (uppercase)
            - error_cf (str): Error message if validation fails
            - correct_cf (bool): True if calculated matches supplied code

    """
    expected_fiscal_code_length = 16
    expected_name_parts_count = 2

    # Process legal name by splitting into name and surname components
    if member.legal_name:
        name_parts = member.legal_name.rsplit(" ", 1)
        if len(name_parts) == expected_name_parts_count:
            member.name, member.surname = name_parts
        else:
            member.name = name_parts[0]

    # Initialize validation context
    validation_context: dict = {"membership_cf": True}

    # Extract fiscal code components using helper functions
    last_name_code = _extract_last_name(member.surname)
    first_name_code = _extract_first_name(member.name)
    birth_date_code = _extract_birth_date(member.birth_date, male=male)

    # Process birth place and get municipality code
    cleaned_birth_place = _clean_birth_place(member.birth_place)
    municipality_code = _extract_municipality_code(cleaned_birth_place)

    # Construct fiscal code without check digit and add check digit
    fiscal_code_without_check_digit = f"{last_name_code}{first_name_code}{birth_date_code}{municipality_code}"
    check_digit = _calculate_check_digit(fiscal_code_without_check_digit)

    # Store calculated and supplied fiscal codes in context
    validation_context["calculated_cf"] = fiscal_code_without_check_digit + check_digit
    if member.fiscal_code:
        validation_context["supplied_cf"] = member.fiscal_code.upper()
    else:
        validation_context["supplied_cf"] = ""

    # Check for municipality code validity
    if not municipality_code:
        validation_context["error_cf"] = _("Place of birth not included in the ISTAT list")

    # Perform detailed validation checks with specific error messages
    if almost_equal(validation_context["calculated_cf"], validation_context["supplied_cf"]):
        validation_context["error_cf"] = _("One symbol more or less than expected")
    elif len(validation_context["supplied_cf"]) != expected_fiscal_code_length:
        validation_context["error_cf"] = _("Wrong length")
    elif count_differences(validation_context["calculated_cf"], validation_context["supplied_cf"]) == 1:
        validation_context["error_cf"] = _("Differs by only one symbol from the expected one")

    # Check specific sections of the fiscal code for targeted error messages
    elif validation_context["calculated_cf"][:6] != validation_context["supplied_cf"][:6]:
        validation_context["error_cf"] = _(
            "Symbols for first and last name do not match (remember to enter the correct first "
            "and last names in legal_name)",
        )
    elif validation_context["calculated_cf"][-6:-1] != validation_context["supplied_cf"][-6:-1]:
        validation_context["error_cf"] = _(
            "Symbols for place of birth do not match (check exact municipality)",
        )
    elif validation_context["calculated_cf"][6:10] != validation_context["supplied_cf"][6:10]:
        validation_context["error_cf"] = _("Symbols for date of birth do not match (check exact date)")

    # Set final validation result
    validation_context["correct_cf"] = validation_context["calculated_cf"] == validation_context["supplied_cf"]

    return validation_context
