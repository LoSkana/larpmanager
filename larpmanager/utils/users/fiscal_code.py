from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.conf import settings as conf_settings
from django.utils.translation import gettext_lazy as _

from larpmanager.utils.users.member import almost_equal, count_differences

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
    """Extract 3-character code from last name using consonants, vowels, and padding.

    Args:
        last_name: The last name to process.

    Returns:
        3-character string code.

    """
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


def _clean_birth_place(birth_place: str | None) -> str:
    """Remove parenthetical content from birth place string.

    Args:
        birth_place: The birth place string to clean.

    Returns:
        Cleaned birth place string with parenthetical content removed.

    """
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
        validation_context["error_cf"] = _("One character more or less than expected")
    elif len(validation_context["supplied_cf"]) != expected_fiscal_code_length:
        validation_context["error_cf"] = _("Wrong number of characters")
    elif count_differences(validation_context["calculated_cf"], validation_context["supplied_cf"]) == 1:
        validation_context["error_cf"] = _("Differing by only one character from the expected one")

    # Check specific sections of the fiscal code for targeted error messages
    elif validation_context["calculated_cf"][:6] != validation_context["supplied_cf"][:6]:
        validation_context["error_cf"] = _(
            "First and last name characters do not match (remember to enter the correct first "
            "and last names in legal_name)",
        )
    elif validation_context["calculated_cf"][-6:-1] != validation_context["supplied_cf"][-6:-1]:
        validation_context["error_cf"] = _(
            "Characters relating to place of birth do not match (check exact municipality)",
        )
    elif validation_context["calculated_cf"][6:10] != validation_context["supplied_cf"][6:10]:
        validation_context["error_cf"] = _("Date of birth characters do not match (check exact date)")

    # Set final validation result
    validation_context["correct_cf"] = validation_context["calculated_cf"] == validation_context["supplied_cf"]

    return validation_context
