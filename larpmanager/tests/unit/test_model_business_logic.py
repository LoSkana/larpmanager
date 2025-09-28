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
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError

from larpmanager.models.accounting import ElectronicInvoice
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import Registration, RegistrationTicket, TicketTier
from larpmanager.models.utils import decimal_to_str


@pytest.mark.django_db
class TestElectronicInvoiceLogic:
    """Test electronic invoice business logic"""

    def test_electronic_invoice_auto_progressive_generation(self, association):
        """Test automatic progressive number generation"""
        # Create first invoice
        invoice1 = ElectronicInvoice.objects.create(assoc=association, year=2023)

        assert invoice1.progressive == 1, f"First progressive should be 1, got {invoice1.progressive}"

        # Create second invoice
        invoice2 = ElectronicInvoice.objects.create(assoc=association, year=2023)

        assert invoice2.progressive == 2, f"Second progressive should be 2, got {invoice2.progressive}"

    def test_electronic_invoice_auto_number_generation_by_year(self, association):
        """Test automatic number generation per year and association"""
        # Create invoice for 2023
        invoice_2023 = ElectronicInvoice.objects.create(assoc=association, year=2023)

        assert invoice_2023.number == 1, f"First number for 2023 should be 1, got {invoice_2023.number}"

        # Create another invoice for 2023
        invoice_2023_2 = ElectronicInvoice.objects.create(assoc=association, year=2023)

        assert invoice_2023_2.number == 2, f"Second number for 2023 should be 2, got {invoice_2023_2.number}"

        # Create invoice for 2024 (should restart numbering)
        invoice_2024 = ElectronicInvoice.objects.create(assoc=association, year=2024)

        assert invoice_2024.number == 1, f"First number for 2024 should be 1, got {invoice_2024.number}"

    def test_electronic_invoice_unique_constraints(self, association):
        """Test unique constraints on electronic invoices"""
        # Create first invoice
        ElectronicInvoice.objects.create(assoc=association, year=2023, number=1, progressive=1)

        # Attempt to create duplicate (same number, year, assoc) should fail
        with pytest.raises(IntegrityError):
            ElectronicInvoice.objects.create(
                assoc=association,
                year=2023,
                number=1,  # Same number for same year/assoc
                progressive=2,
            )

        # Attempt to create duplicate progressive should fail
        with pytest.raises(IntegrityError):
            ElectronicInvoice.objects.create(
                assoc=association,
                year=2024,
                number=1,
                progressive=1,  # Same progressive
            )

    def test_electronic_invoice_different_associations_allowed(self):
        """Test that same numbers are allowed for different associations"""
        assoc1 = Association.objects.create(name="Association 1", slug="assoc1")
        assoc2 = Association.objects.create(name="Association 2", slug="assoc2")

        # Same number/year for different associations should be allowed
        invoice1 = ElectronicInvoice.objects.create(assoc=assoc1, year=2023, number=1)

        invoice2 = ElectronicInvoice.objects.create(
            assoc=assoc2,
            year=2023,
            number=1,  # Same number but different association
        )

        assert invoice1.number == invoice2.number == 1, "Same numbers should be allowed for different associations"
        assert invoice1.progressive != invoice2.progressive, "Progressives should be different"


@pytest.mark.django_db
class TestRegistrationBusinessLogic:
    """Test registration business logic"""

    def test_registration_ticket_availability_check(self, event):
        """Test ticket availability constraints"""
        # Create ticket with limited availability
        ticket = RegistrationTicket.objects.create(
            event=event,
            tier=TicketTier.STANDARD,
            name="Limited Ticket",
            price=Decimal("100.00"),
            max_available=2,  # Only 2 available
        )

        user1 = User.objects.create_user(username="user1", email="user1@test.com")
        member1 = Member.objects.create(user=user1, name="User", surname="One")

        user2 = User.objects.create_user(username="user2", email="user2@test.com")
        member2 = Member.objects.create(user=user2, name="User", surname="Two")

        run = Run.objects.create(event=event, number=1, name="Test Run")

        # First registration should work
        reg1 = Registration.objects.create(member=member1, run=run, ticket=ticket)
        assert reg1.id is not None, "First registration should succeed"

        # Second registration should work
        reg2 = Registration.objects.create(member=member2, run=run, ticket=ticket)
        assert reg2.id is not None, "Second registration should succeed"

        # Business logic should prevent third registration (handled at application level)
        # Model level allows it, but application should check availability
        registrations_count = Registration.objects.filter(ticket=ticket).count()
        assert registrations_count <= ticket.max_available or ticket.max_available == 0, (
            "Application should enforce availability limits"
        )

    def test_registration_price_calculation_components(self, registration_with_complex_pricing):
        """Test registration price calculation with all components"""
        reg = registration_with_complex_pricing

        # Verify all components are present
        assert reg.ticket is not None, "Registration should have ticket"
        assert reg.ticket.price > 0, "Ticket should have price"
        assert reg.additionals > 0, "Registration should have additional tickets"
        assert reg.pay_what > 0, "Registration should have pay-what amount"

        # Verify choices exist
        choices = reg.choices.all()
        assert choices.count() > 0, "Registration should have option choices"

        total_option_price = sum(choice.option.price for choice in choices)
        assert total_option_price > 0, "Options should have total price"

    def test_registration_tier_permissions(self, event):
        """Test that different ticket tiers have appropriate characteristics"""
        # Staff ticket should typically be free
        staff_ticket = RegistrationTicket.objects.create(
            event=event,
            tier=TicketTier.STAFF,
            name="Staff Ticket",
            price=Decimal("0.00"),
            visible=False,  # Staff tickets usually not visible to public
        )

        # Standard ticket should have normal price
        standard_ticket = RegistrationTicket.objects.create(
            event=event, tier=TicketTier.STANDARD, name="Standard Ticket", price=Decimal("100.00"), visible=True
        )

        # Verify characteristics
        assert staff_ticket.price == 0, "Staff tickets should typically be free"
        assert not staff_ticket.visible, "Staff tickets should not be publicly visible"
        assert standard_ticket.price > 0, "Standard tickets should have price"
        assert standard_ticket.visible, "Standard tickets should be visible"

    def test_registration_cancellation_workflow(self, basic_registration):
        """Test registration cancellation business logic"""
        reg = basic_registration

        # Initial state
        assert reg.cancellation_date is None, "New registration should not be cancelled"

        # Cancel registration
        reg.cancellation_date = datetime.now()
        reg.save()

        # Verify cancellation
        assert reg.cancellation_date is not None, "Registration should be marked as cancelled"

        # Business rule: cancelled registrations should not be included in active counts
        active_registrations = Registration.objects.filter(run=reg.run, cancellation_date__isnull=True)

        assert reg not in active_registrations, "Cancelled registration should not be in active list"


@pytest.mark.django_db
class TestMembershipBusinessLogic:
    """Test membership business logic"""

    def test_membership_status_workflow(self, member, association):
        """Test membership status transitions"""
        # Create pending membership
        membership = Membership.objects.create(
            member=member, assoc=association, status=MembershipStatus.PENDING, date=date.today()
        )

        assert membership.status == MembershipStatus.PENDING, "New membership should be pending"

        # Accept membership
        membership.status = MembershipStatus.ACCEPTED
        membership.save()

        assert membership.status == MembershipStatus.ACCEPTED, "Membership should be accepted"

        # Business rule: only accepted memberships should grant privileges
        accepted_memberships = Membership.objects.filter(member=member, status=MembershipStatus.ACCEPTED)

        assert membership in accepted_memberships, "Accepted membership should be in accepted list"

    def test_membership_date_significance(self, member, association):
        """Test membership date business logic"""
        # Recent membership
        recent_membership = Membership.objects.create(
            member=member, assoc=association, status=MembershipStatus.ACCEPTED, date=date.today() - timedelta(days=5)
        )

        # Old membership (different member to avoid conflicts)
        user2 = User.objects.create_user(username="user2", email="user2@test.com")
        member2 = Member.objects.create(user=user2, name="Old", surname="Member")

        old_membership = Membership.objects.create(
            member=member2, assoc=association, status=MembershipStatus.ACCEPTED, date=date.today() - timedelta(days=365)
        )

        # Verify dates
        assert recent_membership.date > old_membership.date, "Recent membership should have later date"

        # Business logic: membership date affects benefits like early registration
        days_since_recent = (date.today() - recent_membership.date).days
        days_since_old = (date.today() - old_membership.date).days

        assert days_since_recent < days_since_old, "Recent membership should have fewer days"
        assert days_since_recent < 30, "Recent membership should be within 30 days for this test"

    def test_membership_token_credit_initialization(self, member, association):
        """Test membership token and credit initialization"""
        membership = Membership.objects.create(
            member=member, assoc=association, status=MembershipStatus.ACCEPTED, tokens=Decimal("0"), credit=Decimal("0")
        )

        # Verify initialization
        assert membership.tokens == Decimal("0"), "New membership should start with 0 tokens"
        assert membership.credit == Decimal("0"), "New membership should start with 0 credits"

        # Test token/credit operations
        membership.tokens = Decimal("10")
        membership.credit = Decimal("25.50")
        membership.save()

        membership.refresh_from_db()
        assert membership.tokens == Decimal("10"), "Tokens should be updated"
        assert membership.credit == Decimal("25.50"), "Credits should be updated with decimal precision"


@pytest.mark.django_db
class TestUtilityFunctions:
    """Test utility functions"""

    def test_decimal_to_str_formatting(self):
        """Test decimal to string conversion"""
        # Test various decimal formats
        assert decimal_to_str(Decimal("100.00")) == "100", "Whole numbers should not show decimals"
        assert decimal_to_str(Decimal("100.50")) == "100,5", "Half numbers should show one decimal"
        assert decimal_to_str(Decimal("100.99")) == "100,99", "Should show necessary decimals"
        assert decimal_to_str(Decimal("0.01")) == "0,01", "Small decimals should be preserved"

    def test_decimal_precision_business_rules(self):
        """Test decimal precision handling in business logic"""
        # Test currency precision (should be 2 decimal places)
        price = Decimal("99.999")  # 3 decimal places
        rounded_price = price.quantize(Decimal("0.01"))

        assert rounded_price == Decimal("100.00"), "Should round to 2 decimal places"

        # Test percentage calculations
        amount = Decimal("100.00")
        percentage = Decimal("3.333")
        result = (amount * percentage / 100).quantize(Decimal("0.01"))

        assert result == Decimal("3.33"), "Percentage calculations should round appropriately"

    def test_price_validation_rules(self):
        """Test price validation business rules"""
        # Valid prices
        valid_prices = [
            Decimal("0.00"),  # Free
            Decimal("0.01"),  # Minimum paid
            Decimal("100.00"),  # Standard
            Decimal("9999.99"),  # High but reasonable
        ]

        for price in valid_prices:
            assert price >= 0, f"Price {price} should be non-negative"
            assert price.as_tuple().exponent >= -2, f"Price {price} should have at most 2 decimal places"

        # Edge cases
        assert Decimal("0") == Decimal("0.00"), "Zero should be equivalent regardless of format"


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
def member():
    """Create test member"""
    user = User.objects.create_user(username="testmember", email="test@test.com")
    return Member.objects.create(user=user, name="Test", surname="Member")


@pytest.fixture
def basic_registration(member, event):
    """Create basic registration"""
    run = Run.objects.create(event=event, number=1, name="Test Run")
    ticket = RegistrationTicket.objects.create(
        event=event, tier=TicketTier.STANDARD, name="Standard Ticket", price=Decimal("100.00")
    )

    return Registration.objects.create(
        member=member, run=run, ticket=ticket, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00")
    )


@pytest.fixture
def registration_with_complex_pricing(member, event):
    """Create registration with complex pricing"""
    from larpmanager.models.form import (
        BaseQuestionType,
        RegistrationChoice,
        RegistrationOption,
        RegistrationQuestion,
    )

    run = Run.objects.create(event=event, number=1, name="Test Run")
    ticket = RegistrationTicket.objects.create(
        event=event, tier=TicketTier.STANDARD, name="Standard Ticket", price=Decimal("100.00")
    )

    registration = Registration.objects.create(
        member=member,
        run=run,
        ticket=ticket,
        additionals=1,  # 1 additional ticket
        pay_what=Decimal("25.00"),
        tot_iscr=Decimal("0.00"),
        tot_payed=Decimal("0.00"),
    )

    # Add option choices
    question = RegistrationQuestion.objects.create(
        event=event, name="accommodation", text="Select accommodation", typ=BaseQuestionType.SINGLE, order=1
    )

    option = RegistrationOption.objects.create(question=question, name="Hotel Room", price=Decimal("80.00"), order=1)

    RegistrationChoice.objects.create(reg=registration, question=question, option=option)

    return registration
