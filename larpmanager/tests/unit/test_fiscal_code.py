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

from datetime import date
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User

from larpmanager.models.member import Member
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.fiscal_code import (
    _calculate_check_digit,
    _calculate_consonants,
    _calculate_vowels,
    _clean_birth_place,
    _extract_birth_date,
    _extract_first_name,
    _extract_last_name,
    _extract_municipality_code,
    _slugify,
    calculate_fiscal_code,
)


class TestFiscalCodeCalculation:
    """Test fiscal code calculation utility functions"""

    def test_calculate_consonants(self):
        """Test consonant extraction from text"""
        assert _calculate_consonants("MARIO") == "MR"
        assert _calculate_consonants("ANTONIO") == "NTN"
        assert _calculate_consonants("GIUSEPPE") == "GSPP"
        assert _calculate_consonants("ÀÈÉÌÒÙ") == ""
        assert _calculate_consonants("AEI123OU") == ""

    def test_calculate_vowels(self):
        """Test vowel extraction from text"""
        assert _calculate_vowels("MARIO") == "AIO"
        assert _calculate_vowels("ANTONIO") == "AOIO"
        assert _calculate_vowels("GIUSEPPE") == "IUEE"
        assert _calculate_vowels("BCDFG") == ""
        assert _calculate_vowels("AEI123OU") == "AEIOU"

    def test_extract_last_name(self):
        """Test last name code extraction"""
        # Standard case with enough consonants
        assert _extract_last_name("ROSSI") == "RSS"
        assert _extract_last_name("BIANCHI") == "BNC"

        # Short names with padding
        assert _extract_last_name("RE") == "REX"
        assert _extract_last_name("O") == "OXX"

        # Names with vowels only
        assert _extract_last_name("AIELLO") == "LLAIEX"[:3]  # Should be "LLA"

    def test_extract_first_name(self):
        """Test first name code extraction"""
        # Standard case
        assert _extract_first_name("MARIO") == "MRA"

        # Four consonants rule - take 1st, 2nd, 3rd
        assert _extract_first_name("GIUSEPPE") == "GSP"

        # Short names
        assert _extract_first_name("ANA") == "NAX"

        # Vowels only
        assert _extract_first_name("ASIA") == "SAX"

    def test_extract_birth_date(self):
        """Test birth date encoding"""
        # Test male birth date encoding
        birth_date = date(1990, 3, 15)
        male_result = _extract_birth_date(birth_date, True)
        assert male_result == "90C15", f"Male encoding should be 90C15, got {male_result}"
        assert len(male_result) == 5, f"Birth date encoding should be 5 chars, got {len(male_result)}"

        # Test female birth date encoding (day + 40)
        female_result = _extract_birth_date(birth_date, False)
        assert female_result == "90C55", f"Female encoding should be 90C55, got {female_result}"
        assert len(female_result) == 5, f"Birth date encoding should be 5 chars, got {len(female_result)}"

        # Test December month encoding (month 12 = T)
        december_date = date(1985, 12, 5)
        december_male = _extract_birth_date(december_date, True)
        assert december_male == "85T05", f"December male should be 85T05, got {december_male}"

        december_female = _extract_birth_date(december_date, False)
        assert december_female == "85T45", f"December female should be 85T45, got {december_female}"

        # Test edge cases
        assert _extract_birth_date(None, True) == "", "None date should return empty string"
        assert _extract_birth_date(None, False) == "", "None date should return empty string regardless of gender"

        # Test month encoding for all months
        month_codes = "ABCDEHLMPRST"
        for month in range(1, 13):
            test_date = date(2000, month, 1)
            result = _extract_birth_date(test_date, True)
            expected_month_code = month_codes[month - 1]
            assert result[2] == expected_month_code, (
                f"Month {month} should encode to {expected_month_code}, got {result[2]}"
            )

    def test_clean_birth_place(self):
        """Test birth place cleaning"""
        assert _clean_birth_place("Roma (RM)") == "Roma "
        assert _clean_birth_place("Milano (Milano)") == "Milano "
        assert _clean_birth_place("Napoli") == "Napoli"
        assert _clean_birth_place("") == ""
        assert _clean_birth_place(None) == ""

    def test_slugify(self):
        """Test text slugification for municipality lookup"""
        assert _slugify("Milano") == "milano"
        assert _slugify("Sant'Antonio") == "santantonio"
        assert _slugify("L'Aquila") == "laquila"
        assert _slugify("Valle d'Aosta") == "valle-daosta"
        assert _slugify("San José") == "san-jose"
        assert _slugify("  Roma  ") == "roma"

    @patch("larpmanager.utils.fiscal_code.open")
    def test_extract_municipality_code_nations(self, mock_open):
        """Test municipality code extraction for foreign nations"""
        # Mock CSV data for nations
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file
        mock_file.__iter__ = Mock(return_value=iter([["Francia", "Z110"], ["Germania", "Z112"], ["Spagna", "Z131"]]))

        result = _extract_municipality_code("Francia")
        assert result == "Z110"

        # Test case sensitivity
        result = _extract_municipality_code("francia")
        assert result == "Z110"

    @patch("larpmanager.utils.fiscal_code.open")
    def test_extract_municipality_code_italian_cities(self, mock_open):
        """Test municipality code extraction for Italian cities"""
        # Mock that nations file doesn't contain the city
        mock_file_nations = Mock()
        mock_file_nations.__iter__ = Mock(return_value=iter([]))

        # Mock CSV data for Italian cities
        mock_file_cities = Mock()
        mock_file_cities.__iter__ = Mock(
            return_value=iter([["Roma/Rome", "H501"], ["Milano", "F205"], ["Napoli", "F839"]])
        )

        # Setup mock to return different files on successive calls
        mock_open.side_effect = [mock_file_nations.__enter__(), mock_file_cities.__enter__()]

        result = _extract_municipality_code("Roma")
        assert result == "H501"

    def test_calculate_check_digit(self):
        """Test check digit calculation"""
        # Test with known valid fiscal codes
        result1 = _calculate_check_digit("RSSMRA90C15H501")
        assert isinstance(result1, str), "Check digit should be a string"
        assert len(result1) == 1, "Check digit should be single character"
        assert result1.isalpha(), "Check digit should be alphabetic"
        assert result1.isupper(), "Check digit should be uppercase"

        result2 = _calculate_check_digit("BNCGPP85T45F205")
        assert isinstance(result2, str), "Check digit should be a string"
        assert len(result2) == 1, "Check digit should be single self.character()"

        # Test with all numbers (edge case)
        result3 = _calculate_check_digit("123456789012345")
        assert isinstance(result3, str), "Check digit should be a string"
        assert result3 in "ABCDEFGHIJKLMNOPQRSTUVWXYZ", f"Check digit should be valid letter, got {result3}"

        # Test with all letters (edge case)
        result4 = _calculate_check_digit("ABCDEFGHILMNOPQ")
        assert isinstance(result4, str), "Check digit should be a string"
        assert result4 in "ABCDEFGHIJKLMNOPQRSTUVWXYZ", f"Check digit should be valid letter, got {result4}"

        # Test consistency
        assert _calculate_check_digit("RSSMRA90C15H501") == _calculate_check_digit("RSSMRA90C15H501"), (
            "Should be deterministic"
        )

    @pytest.mark.django_db
    def test_calculate_fiscal_code_non_italian(self):
        """Test fiscal code calculation for non-Italian citizens"""
        user = User.objects.create_user(username="foreign", email="foreign@test.com")
        member = Member.objects.create(
            user=user,
            name="John",
            surname="Smith",
            nationality="US",
            birth_date=date(1990, 5, 15),
            birth_place="New York",
        )

        result = calculate_fiscal_code(member)
        assert result == {}

    @pytest.mark.django_db
    def test_calculate_fiscal_code_na_fiscal_code(self):
        """Test fiscal code calculation when self.member() has N/A fiscal code"""
        user = User.objects.create_user(username="na_user", email="na@test.com")
        member = Member.objects.create(
            user=user,
            name="Giuseppe",
            surname="Verdi",
            nationality="IT",
            fiscal_code="n/a",
            birth_date=date(1980, 10, 20),
            birth_place="Milano",
        )

        result = calculate_fiscal_code(member)
        assert result == {}

    @pytest.mark.django_db
    @patch("larpmanager.utils.fiscal_code._extract_municipality_code")
    def test_calculate_fiscal_code_valid_italian(self, mock_municipality):
        """Test fiscal code calculation for valid Italian citizen"""
        mock_municipality.return_value = "F205"  # Milano code

        user = User.objects.create_user(username="italian", email="italian@test.com")
        member = Member.objects.create(
            user=user,
            name="Mario",
            surname="Rossi",
            nationality="IT",
            fiscal_code="RSSMRA90E15F205X",
            birth_date=date(1990, 5, 15),
            birth_place="Milano",
        )

        result = calculate_fiscal_code(member)

        # Verify result structure
        assert isinstance(result, dict), "Result should be a dictionary"
        assert "calculated_cf" in result, "Result should contain calculated fiscal code"
        assert "supplied_cf" in result, "Result should contain supplied fiscal code"
        assert "correct_cf" in result, "Result should contain correctness flag"
        assert "membership_cf" in result, "Result should contain membership flag"

        # Verify specific values
        assert result["supplied_cf"] == "RSSMRA90E15F205X", f"Expected supplied code, got {result['supplied_cf']}"
        assert result["membership_cf"] is True, "Should indicate membership fiscal code processing"

        # Verify calculated code structure
        calculated = result["calculated_cf"]
        assert len(calculated) == 16, f"Fiscal code should be 16 characters, got {len(calculated)}"
        assert calculated[:3] == "RSS", f"Last name code should be RSS, got {calculated[:3]}"
        assert calculated[3:6] == "MRA", f"First name code should be MRA, got {calculated[3:6]}"
        assert calculated[6:8] == "90", f"Year should be 90, got {calculated[6:8]}"
        assert calculated[8] == "E", f"Month should be E (May), got {calculated[8]}"
        assert calculated[9:11] == "15", f"Day should be 15, got {calculated[9:11]}"
        assert calculated[11:15] == "F205", f"Municipality should be F205, got {calculated[11:15]}"
        assert calculated[15] in "ABCDEFGHIJKLMNOPQRSTUVWXYZ", f"Check digit should be a letter, got {calculated[15]}"

        # Verify correctness when codes match
        if calculated == result["supplied_cf"]:
            assert result["correct_cf"] is True, "Should be correct when calculated matches supplied"

    @pytest.mark.django_db
    @patch("larpmanager.utils.fiscal_code._extract_municipality_code")
    def test_calculate_fiscal_code_female_date_encoding(self, mock_municipality):
        """Test fiscal code calculation with female gender (different date encoding)"""
        mock_municipality.return_value = "F205"

        user = User.objects.create_user(username="female", email="female@test.com")
        member = Member.objects.create(
            user=user,
            name="Maria",
            surname="Bianchi",
            nationality="IT",
            birth_date=date(1985, 12, 8),
            birth_place="Milano",
        )

        # Test with male=False (should add 40 to day)
        result = calculate_fiscal_code(member)

        calculated = result["calculated_cf"]
        # December = T, day 8 + 40 = 48
        assert calculated[8:11] == "T48"

    @pytest.mark.django_db
    @patch("larpmanager.utils.fiscal_code._extract_municipality_code")
    def test_calculate_fiscal_code_with_legal_name(self, mock_municipality):
        """Test fiscal code calculation using legal name instead of regular name"""
        mock_municipality.return_value = "H501"

        user = User.objects.create_user(username="legal", email="legal@test.com")
        member = Member.objects.create(
            user=user,
            name="Nick",  # Regular name
            surname="Smith",  # Regular surname
            legal_name="Giuseppe Verdi",  # Legal name should be used
            nationality="IT",
            birth_date=date(1975, 8, 25),
            birth_place="Roma",
        )

        result = calculate_fiscal_code(member)

        calculated = result["calculated_cf"]
        # Should use "Giuseppe" and "Verdi" from legal_name
        assert calculated[:3] == "VRD"  # Verdi surname
        assert calculated[3:6] == "GPP"  # Giuseppe name (4+ consonants rule)

    @pytest.mark.django_db
    @patch("larpmanager.utils.fiscal_code._extract_municipality_code")
    def test_calculate_fiscal_code_error_conditions(self, mock_municipality):
        """Test fiscal code calculation error detection"""
        mock_municipality.return_value = ""  # Municipality not found

        user = User.objects.create_user(username="error", email="error@test.com")
        member = Member.objects.create(
            user=user,
            name="Test",
            surname="User",
            nationality="IT",
            fiscal_code="WRONGCODE123",  # Wrong length
            birth_date=date(1990, 1, 1),
            birth_place="Unknown City",
        )

        result = calculate_fiscal_code(member)

        # Verify error detection
        assert "error_cf" in result, "Result should contain error message"
        assert isinstance(result["error_cf"], str), "Error should be a string message"
        assert "ISTAT" in str(result["error_cf"]), f"Should mention ISTAT error, got: {result['error_cf']}"
        assert result["correct_cf"] is False, "Should not be correct when municipality not found"

        # Verify calculated code is still generated (but marked as incorrect)
        assert "calculated_cf" in result, "Should still generate calculated code"
        assert "supplied_cf" in result, "Should still contain supplied code"
        assert result["supplied_cf"] == "WRONGCODE123", "Should preserve supplied code"

    @pytest.mark.django_db
    @patch("larpmanager.utils.fiscal_code._extract_municipality_code")
    def test_calculate_fiscal_code_length_error(self, mock_municipality):
        """Test fiscal code length validation"""
        mock_municipality.return_value = "F205"

        user = User.objects.create_user(username="length", email="length@test.com")
        member = Member.objects.create(
            user=user,
            name="Mario",
            surname="Rossi",
            nationality="IT",
            fiscal_code="TOOLONG123456789",  # 17 characters (too long)
            birth_date=date(1990, 5, 15),
            birth_place="Milano",
        )

        result = calculate_fiscal_code(member)

        # Verify length error detection
        assert "error_cf" in result, "Should detect length error"
        assert "Wrong number of characters" in str(result["error_cf"]), (
            f"Should mention wrong length, got: {result['error_cf']}"
        )
        assert result["correct_cf"] is False, "Should not be correct with wrong length"

        # Verify supplied code length
        assert len(result["supplied_cf"]) == 17, f"Supplied code should be 17 chars, got {len(result['supplied_cf'])}"

        # Verify calculated code is still correct length
        assert len(result["calculated_cf"]) == 16, (
            f"Calculated code should be 16 chars, got {len(result['calculated_cf'])}"
        )

    def test_complex_names_with_special_characters(self):
        """Test fiscal code calculation with complex names"""
        # Test names with apostrophes and spaces
        assert _extract_last_name("D'Angelo") == "DNG", "Should handle apostrophes in surnames"
        assert _extract_first_name("Maria Stella") == "MRS", "Should handle spaces in names"

        # Test very short names
        assert _extract_last_name("Li") == "LIX", "Should pad short surnames"
        assert _extract_first_name("Wu") == "WUX", "Should pad short names"

        # Test names with accented characters
        assert _extract_last_name("Müller") == "MLR", "Should handle accented characters"

    def test_birth_place_cleaning_edge_cases(self):
        """Test birth place cleaning with various formats"""
        # Test multiple parentheses
        assert _clean_birth_place("Roma (RM) (Lazio)") == "Roma  ", "Should remove all parentheses"

        # Test nested parentheses
        assert _clean_birth_place("Milano (MI (Lombardia))") == "Milano ", "Should handle nested parentheses"

        # Test no parentheses
        assert _clean_birth_place("Napoli") == "Napoli", "Should leave clean names unchanged"

    def test_slugification_comprehensive(self):
        """Test comprehensive slugification"""
        # Test various accented characters
        assert _slugify("São Paulo") == "sao-paulo", "Should handle Portuguese accents"
        assert _slugify("Düsseldorf") == "dusseldorf", "Should handle German umlauts"
        assert _slugify("Ålesund") == "alesund", "Should handle Nordic characters"

        # Test punctuation removal
        assert _slugify("Saint-Jean-de-Luz") == "saint-jean-de-luz", "Should preserve meaningful hyphens"
        assert _slugify("L'Aquila") == "laquila", "Should remove apostrophes"

        # Test number handling
        assert _slugify("Test123City") == "test123city", "Should preserve numbers"
