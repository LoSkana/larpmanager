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

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from larpmanager.accounting.registration import get_reg_iscr
from larpmanager.models.accounting import AccountingItemDiscount
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.form import (
    BaseQuestionType,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
)
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration, RegistrationTicket, TicketTier


@pytest.mark.django_db
class TestRegistrationFeeCalculation:
    """Test registration fee calculation logic"""

    def test_get_reg_iscr_basic_ticket_only(self, basic_registration):
        """Test fee calculation with basic ticket only"""
        # Basic ticket costs 100.00
        result = get_reg_iscr(basic_registration)

        assert result == Decimal("100.00"), f"Expected 100.00, got {result}"
        assert isinstance(result, (int, Decimal)), "Result should be numeric"

    def test_get_reg_iscr_with_additional_tickets(self, registration_with_additionals):
        """Test fee calculation with additional tickets"""
        # Base ticket (100) + 2 additionals (200) = 300.00
        result = get_reg_iscr(registration_with_additionals)

        assert result == Decimal("300.00"), f"Expected 300.00, got {result}"

    def test_get_reg_iscr_with_pay_what_amount(self, registration_with_pay_what):
        """Test fee calculation with pay-what-you-want amount"""
        # Base ticket (100) + pay what (25) = 125.00
        result = get_reg_iscr(registration_with_pay_what)

        assert result == Decimal("125.00"), f"Expected 125.00, got {result}"

    def test_get_reg_iscr_with_options(self, registration_with_options):
        """Test fee calculation with registration options"""
        # Base ticket (100) + breakfast (15) + dinner (30) = 145.00
        result = get_reg_iscr(registration_with_options)

        assert result == Decimal("145.00"), f"Expected 145.00, got {result}"

    def test_get_reg_iscr_with_discount(self, registration_with_discount):
        """Test fee calculation with discount applied"""
        # Base ticket (100) - discount (20) = 80.00
        result = get_reg_iscr(registration_with_discount)

        assert result == Decimal("80.00"), f"Expected 80.00, got {result}"

    def test_get_reg_iscr_with_surcharge(self, registration_with_surcharge):
        """Test fee calculation with surcharge applied"""
        # Base ticket (100) + surcharge (15) = 115.00
        result = get_reg_iscr(registration_with_surcharge)

        assert result == Decimal("115.00"), f"Expected 115.00, got {result}"

    def test_get_reg_iscr_no_discount_for_gifted(self, gifted_registration_with_discount):
        """Test that discounts are not applied to gifted registrations"""
        # Base ticket (100) + no discount applied = 100.00
        result = get_reg_iscr(gifted_registration_with_discount)

        assert result == Decimal("100.00"), f"Expected 100.00 (no discount for gifted), got {result}"

    def test_get_reg_iscr_complex_calculation(self, complex_registration):
        """Test complex fee calculation with all components"""
        # Base ticket (100) + additional (100) + pay what (25) + options (45) + surcharge (10) - discount (30) = 250.00
        result = get_reg_iscr(complex_registration)

        assert result == Decimal("250.00"), f"Expected 250.00, got {result}"

    def test_get_reg_iscr_negative_total_clamped_to_zero(self, registration_with_large_discount):
        """Test that negative totals are clamped to zero"""
        # Base ticket (100) - large discount (150) = max(0, -50) = 0
        result = get_reg_iscr(registration_with_large_discount)

        assert result == Decimal("0.00"), f"Expected 0.00 (negative clamped), got {result}"
        assert result >= 0, "Result should never be negative"

    def test_get_reg_iscr_zero_price_ticket(self, free_ticket_registration):
        """Test fee calculation with free ticket"""
        # Free ticket (0) + options (20) = 20.00
        result = get_reg_iscr(free_ticket_registration)

        assert result == Decimal("20.00"), f"Expected 20.00, got {result}"

    def test_get_reg_iscr_no_ticket(self, registration_without_ticket):
        """Test fee calculation with no ticket assigned"""
        # No ticket assigned should result in 0
        result = get_reg_iscr(registration_without_ticket)

        assert result == Decimal("0.00"), f"Expected 0.00 (no ticket), got {result}"

    def test_get_reg_iscr_decimal_precision(self, registration_with_decimal_amounts):
        """Test fee calculation maintains proper decimal precision"""
        # Ticket (99.99) + option (0.01) = 100.00
        result = get_reg_iscr(registration_with_decimal_amounts)

        assert result == Decimal("100.00"), f"Expected 100.00, got {result}"
        assert result.as_tuple().exponent <= -2, "Should maintain at least 2 decimal places"

    def test_get_reg_iscr_multiple_discounts(self, registration_with_multiple_discounts):
        """Test fee calculation with multiple discounts"""
        # Ticket (100) - discount1 (10) - discount2 (15) = 75.00
        result = get_reg_iscr(registration_with_multiple_discounts)

        assert result == Decimal("75.00"), f"Expected 75.00, got {result}"


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


@pytest.fixture
def standard_ticket(event):
    """Create standard ticket"""
    return RegistrationTicket.objects.create(
        event=event, tier=TicketTier.STANDARD, name="Standard Ticket", price=Decimal("100.00"), available=50
    )


@pytest.fixture
def free_ticket(event):
    """Create free ticket"""
    return RegistrationTicket.objects.create(
        event=event, tier=TicketTier.STAFF, name="Free Ticket", price=Decimal("0.00"), available=10
    )


@pytest.fixture
def basic_registration(member, run, standard_ticket):
    """Create basic registration with just a ticket"""
    return Registration.objects.create(
        member=member, run=run, ticket=standard_ticket, tot_iscr=Decimal("0.00"), tot_payed=Decimal("0.00")
    )


@pytest.fixture
def registration_with_additionals(member, run, standard_ticket):
    """Create registration with additional tickets"""
    return Registration.objects.create(
        member=member,
        run=run,
        ticket=standard_ticket,
        additionals=2,  # 2 additional tickets
        tot_iscr=Decimal("0.00"),
        tot_payed=Decimal("0.00"),
    )


@pytest.fixture
def registration_with_pay_what(member, run, standard_ticket):
    """Create registration with pay-what-you-want amount"""
    return Registration.objects.create(
        member=member,
        run=run,
        ticket=standard_ticket,
        pay_what=Decimal("25.00"),
        tot_iscr=Decimal("0.00"),
        tot_payed=Decimal("0.00"),
    )


@pytest.fixture
def registration_with_options(member, run, standard_ticket, event):
    """Create registration with options selected"""
    registration = Registration.objects.create(
        member=member, run=run, ticket=standard_ticket, tot_iscr=Decimal("0.00"), tot_payed=Decimal("0.00")
    )

    # Create question and options
    question = RegistrationQuestion.objects.create(
        event=event, name="meals", text="Select meals", typ=BaseQuestionType.MULTIPLE, order=1
    )

    breakfast = RegistrationOption.objects.create(question=question, name="Breakfast", price=Decimal("15.00"), order=1)

    dinner = RegistrationOption.objects.create(question=question, name="Dinner", price=Decimal("30.00"), order=2)

    # Create choices
    RegistrationChoice.objects.create(reg=registration, question=question, option=breakfast)
    RegistrationChoice.objects.create(reg=registration, question=question, option=dinner)

    return registration


@pytest.fixture
def registration_with_discount(member, run, standard_ticket):
    """Create registration with discount"""
    registration = Registration.objects.create(
        member=member, run=run, ticket=standard_ticket, tot_iscr=Decimal("0.00"), tot_payed=Decimal("0.00")
    )

    # Create discount
    AccountingItemDiscount.objects.create(member=member, run=run, value=Decimal("20.00"), assoc=run.event.assoc)

    return registration


@pytest.fixture
def registration_with_surcharge(member, run, standard_ticket):
    """Create registration with surcharge"""
    return Registration.objects.create(
        member=member,
        run=run,
        ticket=standard_ticket,
        surcharge=Decimal("15.00"),
        tot_iscr=Decimal("0.00"),
        tot_payed=Decimal("0.00"),
    )


@pytest.fixture
def gifted_registration_with_discount(member, run, standard_ticket):
    """Create gifted registration with discount (should not apply)"""
    registration = Registration.objects.create(
        member=member,
        run=run,
        ticket=standard_ticket,
        redeem_code="GIFT123",  # Gifted registration
        tot_iscr=Decimal("0.00"),
        tot_payed=Decimal("0.00"),
    )

    # Create discount (should not be applied)
    AccountingItemDiscount.objects.create(member=member, run=run, value=Decimal("20.00"), assoc=run.event.assoc)

    return registration


@pytest.fixture
def complex_registration(member, run, standard_ticket, event):
    """Create complex registration with all components"""
    registration = Registration.objects.create(
        member=member,
        run=run,
        ticket=standard_ticket,
        additionals=1,  # 1 additional ticket
        pay_what=Decimal("25.00"),
        surcharge=Decimal("10.00"),
        tot_iscr=Decimal("0.00"),
        tot_payed=Decimal("0.00"),
    )

    # Add options
    question = RegistrationQuestion.objects.create(
        event=event, name="extras", text="Select extras", typ=BaseQuestionType.MULTIPLE, order=1
    )

    option1 = RegistrationOption.objects.create(question=question, name="Extra 1", price=Decimal("20.00"), order=1)

    option2 = RegistrationOption.objects.create(question=question, name="Extra 2", price=Decimal("25.00"), order=2)

    RegistrationChoice.objects.create(reg=registration, question=question, option=option1)
    RegistrationChoice.objects.create(reg=registration, question=question, option=option2)

    # Add discount
    AccountingItemDiscount.objects.create(member=member, run=run, value=Decimal("30.00"), assoc=run.event.assoc)

    return registration


@pytest.fixture
def registration_with_large_discount(member, run, standard_ticket):
    """Create registration with discount larger than total"""
    registration = Registration.objects.create(
        member=member, run=run, ticket=standard_ticket, tot_iscr=Decimal("0.00"), tot_payed=Decimal("0.00")
    )

    # Large discount that would make total negative
    AccountingItemDiscount.objects.create(member=member, run=run, value=Decimal("150.00"), assoc=run.event.assoc)

    return registration


@pytest.fixture
def free_ticket_registration(member, run, free_ticket, event):
    """Create registration with free ticket but paid options"""
    registration = Registration.objects.create(
        member=member, run=run, ticket=free_ticket, tot_iscr=Decimal("0.00"), tot_payed=Decimal("0.00")
    )

    # Add paid option
    question = RegistrationQuestion.objects.create(
        event=event, name="addon", text="Select addon", typ=BaseQuestionType.SINGLE, order=1
    )

    option = RegistrationOption.objects.create(question=question, name="Paid Addon", price=Decimal("20.00"), order=1)

    RegistrationChoice.objects.create(reg=registration, question=question, option=option)

    return registration


@pytest.fixture
def registration_without_ticket(member, run):
    """Create registration without ticket assigned"""
    return Registration.objects.create(
        member=member,
        run=run,
        ticket=None,  # No ticket
        tot_iscr=Decimal("0.00"),
        tot_payed=Decimal("0.00"),
    )


@pytest.fixture
def registration_with_decimal_amounts(member, run, event):
    """Create registration with decimal amounts"""
    # Create ticket with decimal price
    ticket = RegistrationTicket.objects.create(
        event=event, tier=TicketTier.STANDARD, name="Decimal Ticket", price=Decimal("99.99"), available=50
    )

    registration = Registration.objects.create(
        member=member, run=run, ticket=ticket, tot_iscr=Decimal("0.00"), tot_payed=Decimal("0.00")
    )

    # Add option with small decimal amount
    question = RegistrationQuestion.objects.create(
        event=event, name="small_fee", text="Small fee", typ=BaseQuestionType.SINGLE, order=1
    )

    option = RegistrationOption.objects.create(question=question, name="Small Fee", price=Decimal("0.01"), order=1)

    RegistrationChoice.objects.create(reg=registration, question=question, option=option)

    return registration


@pytest.fixture
def registration_with_multiple_discounts(member, run, standard_ticket):
    """Create registration with multiple discounts"""
    registration = Registration.objects.create(
        member=member, run=run, ticket=standard_ticket, tot_iscr=Decimal("0.00"), tot_payed=Decimal("0.00")
    )

    # Create multiple discounts
    AccountingItemDiscount.objects.create(member=member, run=run, value=Decimal("10.00"), assoc=run.event.assoc)

    AccountingItemDiscount.objects.create(member=member, run=run, value=Decimal("15.00"), assoc=run.event.assoc)

    return registration
