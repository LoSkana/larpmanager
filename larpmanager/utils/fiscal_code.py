import csv
import os
import re
import unicodedata
from typing import Any

from django.conf import settings as conf_settings
from django.utils.translation import gettext_lazy as _

from larpmanager.models.member import Member
from larpmanager.utils.member import almost_equal, count_differences


def calculate_fiscal_code(member: Member) -> dict:
    """Calculate and validate Italian fiscal code for a member.

    This function calculates the Italian fiscal code (codice fiscale) for a given member
    and validates its correctness. It handles gender ambiguity by trying both male and
    female options if the initial calculation fails.

    Args:
        member: Member object containing personal data required for fiscal code calculation.
                Must have attributes: nationality, fiscal_code, and other personal details.

    Returns:
        dict: Dictionary containing fiscal code validation results. Returns empty dict
              if member is not Italian or has fiscal_code set to "n/a".
              Otherwise contains validation status and calculated fiscal code.

    Note:
        Only processes Italian citizens (nationality "it"). Non-Italian citizens
        and members with fiscal_code "n/a" are skipped.
    """
    # Skip non-Italian citizens - fiscal code only applies to Italian residents
    if member.nationality and member.nationality.lower() != "it":
        return {}

    # Skip members who explicitly don't have a fiscal code
    if member.fiscal_code and member.fiscal_code.lower() == "n/a":
        return {}

    # First attempt: calculate fiscal code assuming male gender
    first_ctx = _go(member, True)

    # If first calculation failed, try with female gender assumption
    # This handles cases where gender determination is ambiguous
    if not first_ctx["correct_cf"]:
        second_ctx = _go(member, False)

        # Return female calculation if it succeeded
        if second_ctx["correct_cf"]:
            return second_ctx

    # Return the first calculation result (either successful or failed)
    return first_ctx


def _calculate_consonants(s):
    return "".join([c for c in s if c.isalpha() and c not in "AEIOUÀÈÉÌÒÙ"])


def _calculate_vowels(s):
    return "".join([c for c in s if c in "AEIOU"])


def _extract_last_name(last_name):
    last_name = last_name.upper()
    consonants = _calculate_consonants(last_name)
    vowels = _calculate_vowels(last_name)
    return (consonants + vowels + "XXX")[:3]


def _extract_first_name(first_name):
    first_name = first_name.upper()
    consonants = _calculate_consonants(first_name)
    max_consonants = 4
    if len(consonants) >= max_consonants:
        consonants = consonants[0] + consonants[2] + consonants[3]
    vowels = _calculate_vowels(first_name)
    return (consonants + vowels + "XXX")[:3]


def _extract_birth_date(birth_date, male):
    month_codes = "ABCDEHLMPRST"
    if not birth_date:
        return ""
    year = str(birth_date.year)[-2:]
    month = month_codes[birth_date.month - 1]
    day = birth_date.day + (40 if not male else 0)
    return f"{year}{month}{str(day).zfill(2)}"


def _clean_birth_place(birth_place):
    if not birth_place:
        return ""
    # Remove everything in parenthesis
    cleaned_birth_place = re.sub(r"\(.*?\)", "", birth_place)
    return cleaned_birth_place


def _slugify(text: str) -> str:
    """Normalize text for fiscal code generation by removing accents and special characters.

    This function performs comprehensive text normalization by removing Italian accents,
    converting to ASCII, normalizing whitespace, and creating URL-friendly slugs.

    Args:
        text (str): Input text to be normalized

    Returns:
        str: Normalized text with accents removed, lowercased, and special characters replaced

    Example:
        >>> _slugify("Café à Paris")
        "cafe-a-paris"
    """
    # Remove common Italian accented characters manually
    for char in ["à", "è", "é", "ì", "ò", "ù"]:
        text = text.replace(char, "")

    # Normalize text using Unicode normalization to decompose accented characters
    # then encode to ASCII ignoring non-ASCII characters
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

    # Convert to lowercase for consistency
    text = text.lower()

    # Remove quotation marks that could interfere with processing
    text = text.replace('"', "").replace("'", "")

    # Remove all non-alphanumeric characters except spaces and hyphens
    text = re.sub(r"[^a-z0-9\s-]", "", text)

    # Replace sequences of whitespace or hyphens with single hyphen
    text = re.sub(r"[\s-]+", "-", text)

    # Clean up leading and trailing hyphens
    text = text.strip("-")
    return text


def _extract_municipality_code(birth_place: str) -> str:
    """Extract municipality code from birth place name using ISTAT data.

    Searches for the given birth place in ISTAT nation and municipality databases.
    First checks for exact matches in nations, then in municipalities (including
    alternative names separated by '/'), and finally performs partial matching.

    Args:
        birth_place (str): Name of the birth place (city/nation)

    Returns:
        str: ISTAT code for the municipality, or empty string if not found

    Note:
        Uses slugified comparison for fuzzy matching of place names.
    """
    slug = _slugify(birth_place)

    # Search in nations database for exact matches
    file_path = os.path.join(conf_settings.BASE_DIR, "../data/istat-nations.csv")
    with open(file_path) as file:
        reader = csv.reader(file)
        # Check each nation name for exact match
        for row in reader:
            if slug == _slugify(row[0]):
                return row[1]

    # Search in municipalities database
    file_path = os.path.join(conf_settings.BASE_DIR, "../data/istat-codes.csv")
    with open(file_path) as file:
        reader = csv.reader(file)

        # First pass: check exact matches including alternative names (separated by '/')
        for row in reader:
            for el in row[0].split("/"):
                if slug == _slugify(el):
                    return row[1]

        # Second pass: check partial matches in municipality names
        for row in reader:
            if slug in _slugify(row[0]):
                return row[1]

    # Return empty string if no match found
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
    even_values = {
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
    odd_values = {
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
    total = 0
    for i, char in enumerate(cf_without_check_digit):
        # Even positions (1, 3, 5, ...) use even_values table
        if i % 2 == 1 and char in even_values:
            total += even_values[char]
        # Odd positions (0, 2, 4, ...) use odd_values table
        elif char in odd_values:
            total += odd_values[char]

    # Convert the modulo 26 result to a letter (A=0, B=1, ..., Z=25)
    check_digit = chr((total % 26) + ord("A"))
    return check_digit


def _go(member: Member, male: bool = True) -> dict[str, Any]:
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
    fiscal_code_length = 16
    name_number = 2

    # Process legal name by splitting into name and surname components
    if member.legal_name:
        splitted = member.legal_name.rsplit(" ", 1)
        if len(splitted) == name_number:
            member.name, member.surname = splitted
        else:
            member.name = splitted[0]

    # Initialize validation context
    ctx: dict[str, Any] = {"membership_cf": True}

    # Extract fiscal code components using helper functions
    last_name_code = _extract_last_name(member.surname)
    first_name_code = _extract_first_name(member.name)
    birth_date_code = _extract_birth_date(member.birth_date, male)

    # Process birth place and get municipality code
    cleaned_birth_place = _clean_birth_place(member.birth_place)
    municipality_code = _extract_municipality_code(cleaned_birth_place)

    # Construct fiscal code without check digit and add check digit
    cf_without_check_digit = f"{last_name_code}{first_name_code}{birth_date_code}{municipality_code}"
    check_digit = _calculate_check_digit(cf_without_check_digit)

    # Store calculated and supplied fiscal codes in context
    ctx["calculated_cf"] = cf_without_check_digit + check_digit
    if member.fiscal_code:
        ctx["supplied_cf"] = member.fiscal_code.upper()
    else:
        ctx["supplied_cf"] = ""

    # Check for municipality code validity
    if not municipality_code:
        ctx["error_cf"] = _("Place of birth not included in the ISTAT list")

    # Perform detailed validation checks with specific error messages
    if almost_equal(ctx["calculated_cf"], ctx["supplied_cf"]):
        ctx["error_cf"] = _("One character more or less than expected")
    elif len(ctx["supplied_cf"]) != fiscal_code_length:
        ctx["error_cf"] = _("Wrong number of characters")
    elif count_differences(ctx["calculated_cf"], ctx["supplied_cf"]) == 1:
        ctx["error_cf"] = _("Differing by only one character from the expected one")

    # Check specific sections of the fiscal code for targeted error messages
    elif ctx["calculated_cf"][:6] != ctx["supplied_cf"][:6]:
        ctx["error_cf"] = _(
            "First and last name characters do not match (remember to enter the correct first "
            "and last names in legal_name)"
        )
    elif ctx["calculated_cf"][-6:-1] != ctx["supplied_cf"][-6:-1]:
        ctx["error_cf"] = _("Characters relating to place of birth do not match (check exact municipality)")
    elif ctx["calculated_cf"][6:10] != ctx["supplied_cf"][6:10]:
        ctx["error_cf"] = _("Date of birth characters do not match (check exact date)")

    # Set final validation result
    ctx["correct_cf"] = ctx["calculated_cf"] == ctx["supplied_cf"]

    return ctx
