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

from decimal import Decimal

from django.test import TestCase

from larpmanager.accounting.registration import get_reg_iscr
from larpmanager.tests.unit.base import BaseTestCase


class TestRegistrationFeeCalculation(TestCase, BaseTestCase):
    """Test self.get_registration() fee calculation logic"""

    def test_get_reg_iscr_basic_ticket_only(self):
        """Test fee calculation with basic ticket only"""
        # Basic ticket costs 100.00
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("100.00"), f"Expected 100.00, got {result}"
        assert isinstance(result, (int, Decimal)), "Result should be numeric"

    def test_get_reg_iscr_with_additional_tickets(self):
        """Test fee calculation with additional tickets"""
        # Base ticket (100) + 2 additionals (200) = 300.00
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("300.00"), f"Expected 300.00, got {result}"

    def test_get_reg_iscr_with_pay_what_amount(self):
        """Test fee calculation with pay-what-you-want amount"""
        # Base ticket (100) + pay what (25) = 125.00
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("125.00"), f"Expected 125.00, got {result}"

    def test_get_reg_iscr_with_options(self):
        """Test fee calculation with self.get_registration() options"""
        # Base ticket (100) + breakfast (15) + dinner (30) = 145.00
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("145.00"), f"Expected 145.00, got {result}"

    def test_get_reg_iscr_with_discount(self):
        """Test fee calculation with discount applied"""
        # Base ticket (100) - discount (20) = 80.00
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("80.00"), f"Expected 80.00, got {result}"

    def test_get_reg_iscr_with_surcharge(self):
        """Test fee calculation with surcharge applied"""
        # Base ticket (100) + surcharge (15) = 115.00
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("115.00"), f"Expected 115.00, got {result}"

    def test_get_reg_iscr_no_discount_for_gifted(self):
        """Test that discounts are not applied to gifted registrations"""
        # Base ticket (100) + no discount applied = 100.00
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("100.00"), f"Expected 100.00 (no discount for gifted), got {result}"

    def test_get_reg_iscr_complex_calculation(self):
        """Test complex fee calculation with all components"""
        # Base ticket (100) + additional (100) + pay what (25) + options (45) + surcharge (10) - discount (30) = 250.00
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("250.00"), f"Expected 250.00, got {result}"

    def test_get_reg_iscr_negative_total_clamped_to_zero(self):
        """Test that negative totals are clamped to zero"""
        # Base ticket (100) - large discount (150) = max(0, -50) = 0
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("0.00"), f"Expected 0.00 (negative clamped), got {result}"
        assert result >= 0, "Result should never be negative"

    def test_get_reg_iscr_zero_price_ticket(self):
        """Test fee calculation with free ticket"""
        # Free ticket (0) + options (20) = 20.00
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("20.00"), f"Expected 20.00, got {result}"

    def test_get_reg_iscr_no_ticket(self):
        """Test fee calculation with no ticket assigned"""
        # No ticket assigned should result in 0
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("0.00"), f"Expected 0.00 (no self.ticket()), got {result}"

    def test_get_reg_iscr_decimal_precision(self):
        """Test fee calculation maintains proper decimal precision"""
        # Ticket (99.99) + option (0.01) = 100.00
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("100.00"), f"Expected 100.00, got {result}"
        assert result.as_tuple().exponent <= -2, "Should maintain at least 2 decimal places"

    def test_get_reg_iscr_multiple_discounts(self):
        """Test fee calculation with multiple discounts"""
        # Ticket (100) - discount1 (10) - discount2 (15) = 75.00
        result = get_reg_iscr(self.get_registration())

        assert result == Decimal("75.00"), f"Expected 75.00, got {result}"
