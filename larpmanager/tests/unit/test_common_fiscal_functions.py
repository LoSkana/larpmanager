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

"""Tests for common utility and fiscal code functions"""

from datetime import date
from unittest.mock import MagicMock, patch

from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.core.common import cantor, check_already, get_channel
from larpmanager.utils.users.fiscal_code import (
    _calculate_consonants,
    _calculate_vowels,
    _clean_birth_place,
    _extract_birth_date,
    _extract_first_name,
    _extract_last_name,
    _slugify,
    calculate_fiscal_code,
)


class TestCommonUtilityFunctions(BaseTestCase):
    """Test cases for common utility functions"""

    def test_cantor_basic(self) -> None:
        """Test cantor pairing function with basic values"""
        result = cantor(5, 7)

        # Cantor pairing function: ((k1 + k2)(k1 + k2 + 1))/2 + k2
        expected = ((5 + 7) * (5 + 7 + 1)) // 2 + 7
        self.assertEqual(result, expected)

    def test_cantor_zero_values(self) -> None:
        """Test cantor with zero values"""
        result = cantor(0, 0)

        self.assertEqual(result, 0)

    def test_cantor_one_zero(self) -> None:
        """Test cantor with one zero value"""
        result = cantor(5, 0)

        expected = ((5 + 0) * (5 + 0 + 1)) // 2 + 0
        self.assertEqual(result, expected)

    def test_cantor_large_values(self) -> None:
        """Test cantor with large values"""
        result = cantor(100, 200)

        # Should produce a unique large number
        self.assertGreater(result, 0)
        self.assertIsInstance(result, float)

    def test_cantor_uniqueness(self) -> None:
        """Test cantor produces unique values for different pairs"""
        result1 = cantor(3, 5)
        result2 = cantor(5, 3)

        # Different pairs should produce different results
        self.assertNotEqual(result1, result2)

    def test_get_channel_basic(self) -> None:
        """Test get_channel creates unique ID"""
        result = get_channel(123, 456)

        # Should use cantor pairing and return int
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

    def test_get_channel_same_ids(self) -> None:
        """Test get_channel with same IDs"""
        result = get_channel(100, 100)

        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

    def test_check_already_no_match(self) -> None:
        """Test check_already when no match found"""
        params = {"user": "test@example.com", "name": "Test User"}

        result = check_already("email", params)

        self.assertFalse(result)

    def test_check_already_email_match(self) -> None:
        """Test check_already matches task params"""
        from datetime import datetime

        import pytz
        from background_task.models import Task

        # check_already checks if a background task exists with matching params
        # It compares task_name and task_params
        params = '["test@example.com", "Test User"]'
        Task.objects.create(task_name="test_task", task_params=params, run_at=datetime.now(pytz.UTC))

        result = check_already("test_task", params)

        self.assertTrue(result)

    def test_check_already_no_match_different_params(self) -> None:
        """Test check_already with different params"""
        from datetime import datetime

        import pytz
        from background_task.models import Task

        params1 = '["test@example.com", "Test User"]'
        params2 = '["other@example.com", "Other User"]'
        Task.objects.create(task_name="test_task", task_params=params1, run_at=datetime.now(pytz.UTC))

        result = check_already("test_task", params2)

        self.assertFalse(result)


class TestFiscalCodeFunctions(BaseTestCase):
    """Test cases for Italian fiscal code calculation"""

    def test_calculate_consonants_basic(self) -> None:
        """Test extracting consonants from string"""
        result = _calculate_consonants("MARIO")

        self.assertEqual(result, "MR")

    def test_calculate_consonants_all_vowels(self) -> None:
        """Test consonants with all vowels"""
        result = _calculate_consonants("AEIOU")

        self.assertEqual(result, "")

    def test_calculate_consonants_mixed(self) -> None:
        """Test consonants with mixed characters"""
        result = _calculate_consonants("BIANCHI")

        # Should extract: B, N, C, H
        self.assertIn("B", result)
        self.assertIn("N", result)

    def test_calculate_vowels_basic(self) -> None:
        """Test extracting vowels from string"""
        result = _calculate_vowels("MARIO")

        self.assertEqual(result, "AIO")

    def test_calculate_vowels_no_vowels(self) -> None:
        """Test vowels with no vowels"""
        result = _calculate_vowels("BCDFG")

        self.assertEqual(result, "")

    def test_calculate_vowels_mixed(self) -> None:
        """Test vowels with mixed characters"""
        result = _calculate_vowels("BIANCHI")

        self.assertEqual(result, "IAI")

    def test_extract_last_name_long(self) -> None:
        """Test extracting last name code with enough consonants"""
        result = _extract_last_name("ROSSI")

        # Should use first 3 consonants: RSS
        self.assertEqual(result, "RSS")

    def test_extract_last_name_short(self) -> None:
        """Test extracting last name code with few consonants"""
        result = _extract_last_name("RE")

        # Should pad with X: REX
        self.assertEqual(len(result), 3)
        self.assertIn("X", result)

    def test_extract_first_name_long(self) -> None:
        """Test extracting first name code with 4+ consonants"""
        result = _extract_first_name("ALESSANDRO")

        # Should use 1st, 3rd, 4th consonants
        self.assertEqual(len(result), 3)

    def test_extract_first_name_three_consonants(self) -> None:
        """Test extracting first name with exactly 3 consonants"""
        result = _extract_first_name("MARIO")

        self.assertEqual(result, "MRA")

    def test_extract_first_name_short(self) -> None:
        """Test extracting first name with few consonants"""
        result = _extract_first_name("IO")

        # Should pad with X
        self.assertEqual(len(result), 3)

    def test_extract_birth_date_male(self) -> None:
        """Test extracting birth date code for male"""
        birth_date = date(1990, 3, 15)
        result = _extract_birth_date(birth_date, male=True)

        # Format: YY + Month Letter + DD
        # 1990 -> 90, March -> C, 15 -> 15
        self.assertEqual(result, "90C15")

    def test_extract_birth_date_female(self) -> None:
        """Test extracting birth date code for female"""
        birth_date = date(1990, 3, 15)
        result = _extract_birth_date(birth_date, male=False)

        # For female, day + 40
        # 1990 -> 90, March -> C, 15+40 -> 55
        self.assertEqual(result, "90C55")

    def test_extract_birth_date_single_digit_day(self) -> None:
        """Test birth date with single digit day"""
        birth_date = date(2000, 1, 5)
        result = _extract_birth_date(birth_date, male=True)

        # Should pad day with zero: 05
        self.assertEqual(result, "00A05")

    def test_clean_birth_place_basic(self) -> None:
        """Test cleaning birth place string"""
        result = _clean_birth_place("Roma")

        # _clean_birth_place only removes parentheses, doesn't uppercase
        self.assertEqual(result, "Roma")

    def test_clean_birth_place_with_apostrophe(self) -> None:
        """Test cleaning birth place with apostrophe"""
        result = _clean_birth_place("Sant'Angelo")

        # _clean_birth_place only removes parentheses, not apostrophes
        self.assertIn("'", result)

    def test_slugify_basic(self) -> None:
        """Test slugifying text"""
        result = _slugify("Hello World")

        self.assertEqual(result, "hello-world")

    def test_slugify_special_chars(self) -> None:
        """Test slugifying with special characters"""
        result = _slugify("Città di Roma!")

        # Should remove special chars and normalize
        self.assertNotIn("!", result)
        self.assertNotIn("à", result)

    def test_calculate_fiscal_code_basic(self) -> None:
        """Test calculating complete fiscal code"""
        member = MagicMock()
        member.name = "MARIO"
        member.surname = "ROSSI"
        member.birth_date = date(1980, 1, 15)
        member.male = True
        member.birth_place = "MILANO"
        member.fiscal_code = "RSSMRA80A15F205X"
        member.nationality = "it"
        member.legal_name = None

        with patch("larpmanager.utils.fiscal_code._extract_municipality_code", return_value="F205"):
            result = calculate_fiscal_code(member)

            # calculate_fiscal_code returns a dict
            self.assertIsInstance(result, dict)
            self.assertIn("calculated_cf", result)
            self.assertEqual(len(result["calculated_cf"]), 16)
            # Should start with last name code
            self.assertTrue(result["calculated_cf"].startswith("RSS"))

    def test_calculate_fiscal_code_female(self) -> None:
        """Test _extract_birth_date for female with day+40"""
        # Test the helper directly
        birth_date = date(1985, 6, 20)
        result = _extract_birth_date(birth_date, male=False)

        # For female, day + 40 (20 + 40 = 60)
        self.assertEqual(result, "85H60")

    def test_calculate_fiscal_code_missing_data(self) -> None:
        """Test fiscal code calculation with missing data"""
        member = MagicMock()
        member.nationality = "us"  # Non-Italian

        result = calculate_fiscal_code(member)

        # Should return empty dict for non-Italian
        self.assertEqual(result, {})
