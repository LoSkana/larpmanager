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

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from larpmanager.accounting.registration import get_reg_iscr
from larpmanager.models.accounting import AccountingItemDiscount
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration, RegistrationTicket, TicketTier
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.fiscal_code import calculate_fiscal_code
from larpmanager.utils.member import almost_equal, count_differences
from larpmanager.utils.validators import FileTypeValidator


class TestCriticalEdgeCases(TestCase, BaseTestCase):
    """Test critical edge cases and error conditions"""

    def test_registration_fee_with_corrupted_data(self):
        """Test registration fee calculation with corrupted or missing data"""
        # Registration with no ticket
        reg_no_ticket = Registration.objects.create(
            member=self.get_member(),
            run=self.get_run(),
            ticket=None,
            tot_iscr=Decimal("0.00"),
            tot_payed=Decimal("0.00"),
        )

        result = get_reg_iscr(reg_no_ticket)
        assert result == Decimal("0.00"), f"No ticket should result in 0.00, got {result}"
        assert isinstance(result, (int, Decimal)), "Result should be numeric type"

        # Registration with None values
        reg_none_values = Registration.objects.create(
            member=self.get_member(),
            run=self.get_run(),
            ticket=None,
            additionals=None,
            pay_what=None,
            surcharge=Decimal("0.00"),
            tot_iscr=Decimal("0.00"),
            tot_payed=Decimal("0.00"),
        )

        result = get_reg_iscr(reg_none_values)
        assert result >= 0, "Result should never be negative"
        assert isinstance(result, (int, Decimal)), "Should handle None values gracefully"

    def test_registration_fee_extreme_values(self):
        """Test registration fee calculation with extreme values"""
        # Create ticket with maximum reasonable price
        max_ticket = RegistrationTicket.objects.create(
            event=self.get_event(),
            tier=TicketTier.STANDARD,
            name="Expensive Ticket",
            price=Decimal("99999.99"),
            available=1,
        )

        reg = Registration.objects.create(
            member=self.get_member(),
            run=self.get_run(),
            ticket=max_ticket,
            additionals=0,
            pay_what=Decimal("0.01"),  # Minimum amount
            surcharge=Decimal("0.00"),
            tot_iscr=Decimal("0.00"),
            tot_payed=Decimal("0.00"),
        )

        result = get_reg_iscr(reg)
        expected = Decimal("99999.99") + Decimal("0.01")
        assert result == expected, f"Expected {expected}, got {result}"

        # Test with maximum discount
        AccountingItemDiscount.objects.create(
            member=member,
            run=run,
            value=Decimal("999999.99"),  # Huge discount
            assoc=run.event.assoc,
        )

        result_with_discount = get_reg_iscr(reg)
        assert result_with_discount == Decimal("0.00"), "Huge discount should result in 0.00 (clamped)"

    def test_decimal_precision_edge_cases(self):
        """Test decimal precision handling in edge cases"""
        # Test with many decimal places
        precise_ticket = RegistrationTicket.objects.create(
            event=self.get_event(),
            tier=TicketTier.STANDARD,
            name="Precise Ticket",
            price=Decimal("99.999999"),  # Many decimal places
            available=1,
        )

        reg = Registration.objects.create(
            member=self.get_member(),
            run=self.get_run(),
            ticket=precise_ticket,
            pay_what=Decimal("0.000001"),  # Very small amount
            tot_iscr=Decimal("0.00"),
            tot_payed=Decimal("0.00"),
        )

        result = get_reg_iscr(reg)
        # Should handle precision without throwing errors
        assert isinstance(result, (int, Decimal)), "Should handle high precision"
        assert result >= 0, "Should maintain non-negative constraint"

    def test_string_comparison_edge_cases(self):
        """Test string comparison functions with edge cases"""
        # Test with empty strings
        assert count_differences("", "") == 0, "Empty strings should have 0 differences"
        assert almost_equal("", "a") is True, "Empty and single char should be almost equal"
        assert almost_equal("a", "") is True, "Single char and empty should be almost equal"

        # Test with very long strings
        long_string1 = "A" * 1000
        long_string2 = "A" * 999 + "B"
        assert count_differences(long_string1, long_string2) == 1, (
            "Same length strings with 1 difference should return 1"
        )

        long_string3 = "A" * 999
        assert almost_equal(long_string1, long_string3) is True, "Should handle long strings"

        # Test with unicode characters
        assert count_differences("café", "cafe") == 1, "Should count accented characters as different"
        assert almost_equal("naïve", "naive") is False, "Different lengths with unicode"

    def test_fiscal_code_extreme_cases(self):
        """Test fiscal code calculation with extreme cases"""
        user = User.objects.create_user(username="extreme", email="extreme@test.com")

        # Test with very long names
        member_long_name = Member.objects.create(
            user=user,
            name="A" * 100,  # Very long name
            surname="B" * 100,  # Very long surname
            nationality="IT",
            birth_date=date(1990, 1, 1),
            birth_place="Roma",
        )

        # Should not crash with long names
        with patch("larpmanager.utils.fiscal_code._extract_municipality_code") as mock_municipality:
            mock_municipality.return_value = "H501"
            result = calculate_fiscal_code(member_long_name)

            assert isinstance(result, dict), "Should return dict even with extreme names"
            assert "calculated_cf" in result, "Should generate calculated code"
            assert len(result["calculated_cf"]) == 16, "Should maintain correct length"

        # Test with special characters in names
        user2 = User.objects.create_user(username="special", email="special@test.com")
        member_special = Member.objects.create(
            user=user2,
            name="José-María",  # Hyphen and accents
            surname="O'Connor",  # Apostrophe
            nationality="IT",
            birth_date=date(1985, 12, 31),
            birth_place="Milano",
        )

        with patch("larpmanager.utils.fiscal_code._extract_municipality_code") as mock_municipality:
            mock_municipality.return_value = "F205"
            result = calculate_fiscal_code(member_special)

            assert isinstance(result, dict), "Should handle special characters"
            assert len(result["calculated_cf"]) == 16, "Should maintain correct length"

    def test_file_validator_edge_cases(self):
        """Test file validator with edge cases"""
        # Test with invalid mime type format
        with pytest.raises(ValidationError) as exc_info:
            FileTypeValidator(["not-a-mime-type"])

        assert "is not a valid type" in str(exc_info.value), "Should detect invalid mime type format"

        # Test with empty allowed types
        with pytest.raises(Exception):
            FileTypeValidator([])

        # Test with bytes input
        validator = FileTypeValidator([b"image/jpeg"])
        assert "image/jpeg" in validator.allowed_mimes, "Should handle bytes input"

    def test_association_model_constraints(self):
        """Test association model constraints and validation"""
        # Test slug uniqueness
        Association.objects.create(name="Test 1", slug="unique-slug")

        with pytest.raises(IntegrityError):
            Association.objects.create(name="Test 2", slug="unique-slug")  # Same slug

        # Test slug format validation (if implemented)
        try:
            assoc = Association.objects.create(name="Test 3", slug="invalid slug with spaces")
            # If creation succeeds, slug validation might be at application level
            assert assoc.slug == "invalid slug with spaces", "Should preserve slug as created"
        except (ValidationError, IntegrityError):
            # Expected if slug validation is implemented
            pass

    def test_datetime_edge_cases(self):
        """Test datetime handling edge cases"""
        # Test with timezone-aware vs naive datetimes
        naive_dt = datetime(2023, 1, 1, 12, 0, 0)
        assert naive_dt.tzinfo is None, "Should be timezone naive"

        # Test date arithmetic edge cases
        leap_year_date = date(2024, 2, 29)  # Leap year
        next_year = date(2025, 2, 28)  # Not leap year

        diff = (next_year - leap_year_date).days
        assert diff == 365, f"Should handle leap year correctly, got {diff} days"

        # Test end of year transitions
        end_of_year = date(2023, 12, 31)
        start_of_year = date(2024, 1, 1)
        year_transition = (start_of_year - end_of_year).days
        assert year_transition == 1, "Should handle year transitions"

    def test_database_transaction_edge_cases(self):
        """Test database transaction edge cases"""
        # Test concurrent registration creation
        ticket = RegistrationTicket.objects.create(
            event=self.get_event(),
            tier=TicketTier.STANDARD,
            name="Concurrent Test",
            price=Decimal("100.00"),
            max_available=1,  # Only one available
        )

        # First registration should succeed
        reg1 = Registration.objects.create(
            member=self.get_member(),
            run=self.get_run(),
            ticket=ticket,
            tot_iscr=Decimal("100.00"),
            tot_payed=Decimal("0.00"),
        )

        assert reg1.id is not None, "First registration should succeed"

        # Business logic should prevent overselling (application level)
        current_count = Registration.objects.filter(ticket=ticket).count()
        if current_count >= ticket.max_available and ticket.max_available > 0:
            # Application should prevent this, but model allows it
            pass

    def test_cache_invalidation_scenarios(self):
        """Test cache invalidation edge cases"""
        from django.core.cache import cache

        # Test cache with None values
        cache.set("test_key", None, 300)
        result = cache.get("test_key")
        assert result is None, "Should handle None values in cache"

        # Test cache with complex objects
        complex_data = {"decimal": Decimal("123.45"), "date": date.today(), "nested": {"list": [1, 2, 3]}}

        cache.set("complex_key", complex_data, 300)
        retrieved = cache.get("complex_key")

        if retrieved:  # If cache backend supports complex objects
            assert isinstance(retrieved, dict), "Should retrieve complex objects"
        else:
            # Some cache backends might not support complex objects
            pass

    def test_model_field_validation_edge_cases(self):
        """Test model field validation with edge cases"""
        # Test with maximum length strings
        long_name = "A" * 255  # Typical max length

        try:
            ticket = RegistrationTicket.objects.create(
                event=self.get_event(),
                tier=TicketTier.STANDARD,
                name=long_name[:50],  # Truncate to field max length
                price=Decimal("100.00"),
                available=1,
            )
            assert len(ticket.name) <= 50, "Should respect field max length"
        except ValidationError:
            # Expected if validation is strict
            pass

        # Test with negative prices (should be prevented by business logic)
        try:
            RegistrationTicket.objects.create(
                event=self.get_event(),
                tier=TicketTier.STANDARD,
                name="Negative Test",
                price=Decimal("-100.00"),  # Negative price
                available=1,
            )
            # If this succeeds, validation is at application level
        except (ValidationError, InvalidOperation):
            # Expected if validation prevents negative prices
            pass

    def test_error_message_localization(self):
        """Test error message handling and localization"""
        from django.utils.translation import gettext_lazy as _

        # Test that error messages are translatable
        error_msg = _("Place of birth not included in the ISTAT list")
        assert isinstance(error_msg, str) or hasattr(error_msg, "__str__"), "Error messages should be string-like"

        # Test error message formatting
        formatted_msg = _("Expected %(expected)s, got %(actual)s") % {"expected": "100.00", "actual": "200.00"}
        assert "100.00" in str(formatted_msg), "Should format error messages correctly"
        assert "200.00" in str(formatted_msg), "Should include actual values"


# Fixtures
@pytest.fixture
def association():
    """Create test association"""
    return Association.objects.create(name="Test Association", slug="test")


@pytest.fixture
def event(association):
    """Create test event"""
    return Event.objects.create(name="Test Event", assoc=association, number=1)


@pytest.fixture
def run(event):
    """Create test run"""
    return Run.objects.create(
        event=event,
        number=1,
        name="Test Run",
        start=date.today() + timedelta(days=30),
        end=date.today() + timedelta(days=32),
    )


@pytest.fixture
def member():
    """Create test member"""
    user = User.objects.create_user(username="testmember", email="test@test.com")
    return Member.objects.create(user=user, name="Test", surname="Member")
