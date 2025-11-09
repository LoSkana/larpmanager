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

"""Tests for utility functions in models/utils.py"""

import re
from decimal import Decimal

from larpmanager.models.utils import (
    decimal_to_str,
    generate_id,
    get_attr,
    get_sum,
    my_uuid,
    my_uuid_miny,
    my_uuid_short,
    remove_non_ascii,
    strip_tags,
)
from larpmanager.tests.unit.base import BaseTestCase


class TestIDGenerationFunctions(BaseTestCase):
    """Test cases for ID generation utility functions"""

    def test_generate_id_creates_id(self) -> None:
        """Test generate_id creates an ID of specified length"""
        result = generate_id(10)

        self.assertEqual(len(result), 10)
        self.assertTrue(result.isalnum())

    def test_generate_id_is_unique(self) -> None:
        """Test generate_id generates unique IDs"""
        id1 = generate_id(10)
        id2 = generate_id(10)

        self.assertNotEqual(id1, id2)

    def test_generate_id_different_lengths(self) -> None:
        """Test generate_id with different lengths"""
        id5 = generate_id(5)
        id20 = generate_id(20)

        self.assertEqual(len(id5), 5)
        self.assertEqual(len(id20), 20)

    def test_my_uuid_default_length(self) -> None:
        """Test my_uuid with default length (32 hex chars)"""
        result = my_uuid()

        self.assertEqual(len(result), 32)

    def test_my_uuid_custom_length(self) -> None:
        """Test my_uuid with custom length"""
        result = my_uuid(length=12)

        self.assertEqual(len(result), 12)

    def test_my_uuid_short(self) -> None:
        """Test my_uuid_short generates 12 character ID"""
        result = my_uuid_short()

        self.assertEqual(len(result), 12)

    def test_my_uuid_miny(self) -> None:
        """Test my_uuid_miny generates 5 character ID (letter + 4)"""
        result = my_uuid_miny()

        self.assertEqual(len(result), 5)
        # First char should be a letter
        self.assertTrue(result[0].isalpha())


class TestStringUtilityFunctions(BaseTestCase):
    """Test cases for string manipulation utility functions"""

    def test_decimal_to_str_basic(self) -> None:
        """Test decimal_to_str converts decimal to string"""
        result = decimal_to_str(Decimal("10.50"))

        # Function only removes .00, not all trailing zeros
        self.assertEqual(result, "10.50")

    def test_decimal_to_str_with_trailing_zeros(self) -> None:
        """Test decimal_to_str removes .00"""
        result = decimal_to_str(Decimal("10.00"))

        self.assertEqual(result, "10")

    def test_decimal_to_str_integer(self) -> None:
        """Test decimal_to_str with integer value"""
        result = decimal_to_str(Decimal("100"))

        self.assertEqual(result, "100")

    def test_decimal_to_str_many_decimals(self) -> None:
        """Test decimal_to_str with many decimal places"""
        result = decimal_to_str(Decimal("10.123456"))

        self.assertIn("10.12", result)

    def test_remove_non_ascii_no_special_chars(self) -> None:
        """Test remove_non_ascii with plain ASCII"""
        result = remove_non_ascii("Hello World")

        self.assertEqual(result, "Hello World")

    def test_remove_non_ascii_with_accents(self) -> None:
        """Test remove_non_ascii removes accented characters"""
        result = remove_non_ascii("Café résumé")

        # Should remove accented characters
        self.assertNotIn("é", result)
        self.assertIn("Caf", result)

    def test_remove_non_ascii_with_special_symbols(self) -> None:
        """Test remove_non_ascii removes special symbols"""
        result = remove_non_ascii("Hello™ World®")

        self.assertNotIn("™", result)
        self.assertNotIn("®", result)
        self.assertIn("Hello", result)
        self.assertIn("World", result)

    def test_strip_tags_no_tags(self) -> None:
        """Test strip_tags with plain text"""
        result = strip_tags("Hello World")

        self.assertEqual(result, "Hello World")

    def test_strip_tags_simple_tags(self) -> None:
        """Test strip_tags removes HTML tags"""
        result = strip_tags("<p>Hello</p> <b>World</b>")

        self.assertEqual(result, "Hello World")

    def test_strip_tags_nested_tags(self) -> None:
        """Test strip_tags with nested HTML"""
        result = strip_tags("<div><p>Hello <strong>World</strong></p></div>")

        self.assertEqual(result, "Hello World")

    def test_strip_tags_with_attributes(self) -> None:
        """Test strip_tags removes tags with attributes"""
        result = strip_tags('<a href="http://example.com">Link</a>')

        self.assertEqual(result, "Link")

    def test_strip_tags_preserves_entities(self) -> None:
        """Test strip_tags handles HTML entities"""
        result = strip_tags("<p>Hello &amp; Goodbye</p>")

        # Should preserve the text representation
        self.assertIn("Hello", result)
        self.assertIn("Goodbye", result)


class TestDataAggregationFunctions(BaseTestCase):
    """Test cases for data aggregation utility functions"""

    def test_get_sum_empty_queryset(self) -> None:
        """Test get_sum with empty queryset"""
        from larpmanager.models.accounting import AccountingItemPayment

        queryset = AccountingItemPayment.objects.none()
        result = get_sum(queryset)

        self.assertEqual(result, Decimal("0"))

    def test_get_sum_single_item(self) -> None:
        """Test get_sum with single item"""
        from larpmanager.models.accounting import AccountingItemPayment, PaymentChoices

        member = self.get_member()
        association = self.get_association()
        registration = self.create_registration(member=member)

        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("100.00")
        )

        queryset = AccountingItemPayment.objects.filter(member=member)
        result = get_sum(queryset)

        self.assertEqual(result, Decimal("100.00"))

    def test_get_sum_multiple_items(self) -> None:
        """Test get_sum aggregates multiple items"""
        from larpmanager.models.accounting import AccountingItemPayment, PaymentChoices

        member = self.get_member()
        association = self.get_association()
        registration = self.create_registration(member=member)

        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("50.00")
        )
        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("30.00")
        )
        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("20.00")
        )

        queryset = AccountingItemPayment.objects.filter(member=member)
        result = get_sum(queryset)

        self.assertEqual(result, Decimal("100.00"))

    def test_get_attr_simple_attribute(self) -> None:
        """Test get_attr retrieves simple attribute"""

        class TestObj:
            name = "Test"

        obj = TestObj()
        result = get_attr(obj, "name")

        self.assertEqual(result, "Test")

    def test_get_attr_nested_attribute(self) -> None:
        """Test get_attr doesn't support nested attributes"""

        class Inner:
            value = 42

        class Outer:
            inner = Inner()

        obj = Outer()
        # Function doesn't support __ notation, just checks simple attributes
        result = get_attr(obj, "inner")

        # Should return the Inner object itself
        self.assertIsNotNone(result)

    def test_get_attr_missing_attribute(self) -> None:
        """Test get_attr with missing attribute"""

        class TestObj:
            name = "Test"

        obj = TestObj()
        result = get_attr(obj, "missing")

        # Returns None for missing attributes
        self.assertIsNone(result)

    def test_get_attr_none_object(self) -> None:
        """Test get_attr with None object"""
        result = get_attr(None, "name")

        # Returns None for None object
        self.assertIsNone(result)

    def test_get_attr_callable(self) -> None:
        """Test get_attr with callable attribute"""

        class TestObj:
            def get_name(self) -> str:
                return "Callable Result"

        obj = TestObj()
        result = get_attr(obj, "get_name")

        # get_attr doesn't call the method, just returns it
        self.assertIsNotNone(result)
        self.assertTrue(callable(result))
