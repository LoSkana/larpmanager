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

"""Tests for member utility and text caching functions"""

from unittest.mock import patch

from larpmanager.utils.member import almost_equal, count_differences
from larpmanager.utils.text import (
    association_text_key,
    association_text_key_def,
    event_text_key,
    event_text_key_def,
    get_association_text,
    get_event_text,
)
from larpmanager.tests.unit.base import BaseTestCase


class TestMemberUtilityFunctions(BaseTestCase):
    """Test cases for member utility functions"""

    def test_count_differences_identical(self):
        """Test count_differences with identical strings"""
        result = count_differences("hello", "hello")

        self.assertEqual(result, 0)

    def test_count_differences_one_diff(self):
        """Test count_differences with one difference"""
        result = count_differences("hello", "hallo")

        self.assertEqual(result, 1)

    def test_count_differences_multiple_diff(self):
        """Test count_differences with multiple differences"""
        result = count_differences("hello", "world")

        self.assertEqual(result, 4)

    def test_count_differences_different_length(self):
        """Test count_differences with different length strings"""
        result = count_differences("hello", "hi")

        self.assertEqual(result, False)

    def test_almost_equal_one_extra_char(self):
        """Test almost_equal with one extra character"""
        result = almost_equal("hello", "helo")

        self.assertTrue(result)

    def test_almost_equal_one_extra_at_end(self):
        """Test almost_equal with one extra at end"""
        result = almost_equal("hello", "hellox")

        self.assertTrue(result)

    def test_almost_equal_one_extra_at_start(self):
        """Test almost_equal with one extra at start"""
        result = almost_equal("xhello", "hello")

        self.assertTrue(result)

    def test_almost_equal_different_chars(self):
        """Test almost_equal with different characters"""
        result = almost_equal("hello", "hallo")

        # Same length, different chars - not almost equal
        self.assertFalse(result)

    def test_almost_equal_two_length_diff(self):
        """Test almost_equal with two length difference"""
        result = almost_equal("hello", "hel")

        # Difference of 2, not almost equal
        self.assertFalse(result)

    def test_almost_equal_no_match(self):
        """Test almost_equal with completely different strings"""
        result = almost_equal("hello", "worldx")

        self.assertFalse(result)


class TestTextCachingFunctions(BaseTestCase):
    """Test cases for text caching functions"""

    def test_event_text_key_format(self):
        """Test event text key format"""
        result = event_text_key(123, "welcome", "en")

        self.assertEqual(result, "event_text_123_welcome_en")

    def test_event_text_key_def_format(self):
        """Test event text default key format"""
        result = event_text_key_def(123, "welcome")

        self.assertEqual(result, "event_text_def_123_welcome")

    def test_association_text_key_format(self):
        """Test association text key format"""
        result = association_text_key(456, "terms", "it")

        self.assertEqual(result, "association_text_456_terms_it")

    def test_association_text_key_def_format(self):
        """Test association text default key format"""
        result = association_text_key_def(456, "terms")

        self.assertEqual(result, "association_text_def_456_terms")

    @patch("larpmanager.utils.text.get_event_text_cache")
    @patch("larpmanager.utils.text.get_event_text_cache_def")
    @patch("larpmanager.utils.text.get_language")
    def test_get_event_text_with_lang(self, mock_lang, mock_def, mock_cache):
        """Test get_event_text with language"""
        mock_lang.return_value = "en"
        mock_cache.return_value = "Welcome text"

        result = get_event_text(123, "welcome", "en")

        self.assertEqual(result, "Welcome text")
        mock_cache.assert_called_once_with(123, "welcome", "en")
        mock_def.assert_not_called()

    @patch("larpmanager.utils.text.get_event_text_cache")
    @patch("larpmanager.utils.text.get_event_text_cache_def")
    @patch("larpmanager.utils.text.get_language")
    def test_get_event_text_fallback_to_default(self, mock_lang, mock_def, mock_cache):
        """Test get_event_text falls back to default"""
        mock_lang.return_value = "en"
        mock_cache.return_value = None
        mock_def.return_value = "Default welcome"

        result = get_event_text(123, "welcome", "en")

        self.assertEqual(result, "Default welcome")
        mock_cache.assert_called_once_with(123, "welcome", "en")
        mock_def.assert_called_once_with(123, "welcome")

    @patch("larpmanager.utils.text.get_event_text_cache")
    @patch("larpmanager.utils.text.get_language")
    def test_get_event_text_uses_current_lang(self, mock_lang, mock_cache):
        """Test get_event_text uses current language when not specified"""
        mock_lang.return_value = "it"
        mock_cache.return_value = "Benvenuto"

        result = get_event_text(123, "welcome")

        mock_cache.assert_called_once_with(123, "welcome", "it")
        self.assertEqual(result, "Benvenuto")

    @patch("larpmanager.utils.text.get_association_text_cache")
    @patch("larpmanager.utils.text.get_association_text_cache_def")
    @patch("larpmanager.utils.text.get_language")
    def test_get_association_text_with_lang(self, mock_lang, mock_def, mock_cache):
        """Test get_association_text with language"""
        mock_lang.return_value = "en"
        mock_cache.return_value = "Terms text"

        result = get_association_text(456, "terms", "en")

        self.assertEqual(result, "Terms text")
        mock_cache.assert_called_once_with(456, "terms", "en")
        mock_def.assert_not_called()

    @patch("larpmanager.utils.text.get_association_text_cache")
    @patch("larpmanager.utils.text.get_association_text_cache_def")
    @patch("larpmanager.utils.text.get_language")
    def test_get_association_text_fallback_to_default(self, mock_lang, mock_def, mock_cache):
        """Test get_association_text falls back to default"""
        mock_lang.return_value = "en"
        mock_cache.return_value = None
        mock_def.return_value = "Default terms"

        result = get_association_text(456, "terms", "en")

        self.assertEqual(result, "Default terms")
        mock_cache.assert_called_once_with(456, "terms", "en")
        mock_def.assert_called_once_with(456, "terms")
