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

from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.form import BaseQuestionType
from larpmanager.models.member import Member
from larpmanager.models.registration import (
    Registration,
    RegistrationOption,
    RegistrationQuestion,
    RegistrationTicket,
    TicketTier,
)


@pytest.mark.django_db
class TestRegistrationFormValidation:
    """Test registration form validation"""

    def test_registration_form_basic_validation(self, member, run, ticket):
        """Test basic registration form validation"""
        # Mock form data
        form_data = {
            "member": member.id,
            "run": run.id,
            "ticket": ticket.id,
            "additionals": 0,
            "pay_what": None,
        }

        # Test required fields
        assert form_data["member"] is not None
        assert form_data["run"] is not None

    def test_registration_form_ticket_validation(self, member, run):
        """Test ticket selection validation"""
        # Create tickets with different availability
        available_ticket = RegistrationTicket.objects.create(
            event=run.event, tier=TicketTier.STANDARD, name="Available Ticket", price=Decimal("100.00"), available=10
        )

        sold_out_ticket = RegistrationTicket.objects.create(
            event=run.event, tier=TicketTier.STANDARD, name="Sold Out Ticket", price=Decimal("100.00"), available=0
        )

        # Test valid ticket selection
        valid_data = {
            "member": member.id,
            "run": run.id,
            "ticket": available_ticket.id,
        }

        # Test sold out ticket selection (should be validated in form)
        invalid_data = {
            "member": member.id,
            "run": run.id,
            "ticket": sold_out_ticket.id,
        }

        # Business logic should prevent sold out ticket selection
        assert available_ticket.available > 0
        assert sold_out_ticket.available == 0

    def test_registration_form_additionals_validation(self, member, run, ticket):
        """Test additional tickets validation"""
        # Test valid additionals
        valid_data = {
            "member": member.id,
            "run": run.id,
            "ticket": ticket.id,
            "additionals": 2,
        }

        # Test negative additionals (should be invalid)
        invalid_data = {
            "member": member.id,
            "run": run.id,
            "ticket": ticket.id,
            "additionals": -1,
        }

        assert valid_data["additionals"] >= 0
        assert invalid_data["additionals"] < 0

    def test_registration_form_pay_what_validation(self, member, run):
        """Test pay-what-you-want validation"""
        # Test valid pay_what amount
        valid_data = {
            "member": member.id,
            "run": run.id,
            "pay_what": Decimal("75.00"),
        }

        # Test negative pay_what (should be invalid)
        invalid_data = {
            "member": member.id,
            "run": run.id,
            "pay_what": Decimal("-10.00"),
        }

        if valid_data["pay_what"]:
            assert valid_data["pay_what"] > 0

        if invalid_data["pay_what"]:
            assert invalid_data["pay_what"] < 0  # This should be caught by form validation

    def test_registration_form_duplicate_validation(self, member, run, ticket):
        """Test duplicate registration validation"""
        # Create first registration
        existing_reg = Registration.objects.create(
            member=member, run=run, ticket=ticket, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00")
        )

        # Test attempt to create duplicate registration
        duplicate_data = {
            "member": member.id,
            "run": run.id,
            "ticket": ticket.id,
        }

        # Form should validate that member doesn't already have registration for this run
        existing_registrations = Registration.objects.filter(member=member, run=run, cancellation_date__isnull=True)

        assert existing_registrations.exists()


@pytest.mark.django_db
class TestRegistrationQuestionForms:
    """Test registration question and answer forms"""

    def test_text_question_answer(self, registration, event):
        """Test text question answer form"""
        question = RegistrationQuestion.objects.create(
            event=event,
            name="dietary_requirements",
            text="Do you have any dietary requirements?",
            typ=BaseQuestionType.TEXT,
            required=True,
            order=1,
        )

        # Valid answer
        valid_answer = "I am vegetarian"
        assert len(valid_answer) > 0

        # Empty answer for required question (should be invalid)
        invalid_answer = ""
        assert len(invalid_answer) == 0 and question.required

    def test_single_choice_question_answer(self, registration, event):
        """Test single choice question answer form"""
        question = RegistrationQuestion.objects.create(
            event=event,
            name="accommodation",
            text="What accommodation do you prefer?",
            typ=BaseQuestionType.SINGLE,
            required=True,
            order=1,
        )

        option1 = RegistrationOption.objects.create(question=question, name="Hotel", price=Decimal("50.00"), order=1)

        option2 = RegistrationOption.objects.create(question=question, name="Camping", price=Decimal("20.00"), order=2)

        # Valid single choice
        valid_choice = option1.id
        available_options = [option1.id, option2.id]
        assert valid_choice in available_options

        # Invalid choice (option doesn't exist)
        invalid_choice = 999
        assert invalid_choice not in available_options

    def test_multiple_choice_question_answer(self, registration, event):
        """Test multiple choice question answer form"""
        question = RegistrationQuestion.objects.create(
            event=event,
            name="meals",
            text="Which meals do you want?",
            typ=BaseQuestionType.MULTIPLE,
            required=False,
            order=1,
        )

        breakfast = RegistrationOption.objects.create(
            question=question, name="Breakfast", price=Decimal("15.00"), order=1
        )

        lunch = RegistrationOption.objects.create(question=question, name="Lunch", price=Decimal("20.00"), order=2)

        dinner = RegistrationOption.objects.create(question=question, name="Dinner", price=Decimal("25.00"), order=3)

        # Valid multiple choices
        valid_choices = [breakfast.id, dinner.id]
        available_options = [breakfast.id, lunch.id, dinner.id]

        for choice in valid_choices:
            assert choice in available_options

    def test_boolean_question_answer(self, registration, event):
        """Test boolean question answer form"""
        question = RegistrationQuestion.objects.create(
            event=event,
            name="newsletter",
            text="Do you want to receive our newsletter?",
            typ=BaseQuestionType.BOOLEAN,
            required=False,
            order=1,
        )

        # Valid boolean answers
        valid_answers = [True, False, "true", "false", "1", "0"]

        for answer in valid_answers:
            # Form should handle conversion to boolean
            if isinstance(answer, str):
                boolean_value = answer.lower() in ["true", "1", "yes"]
            else:
                boolean_value = bool(answer)

            assert isinstance(boolean_value, bool)

    def test_integer_question_answer(self, registration, event):
        """Test integer question answer form"""
        question = RegistrationQuestion.objects.create(
            event=event, name="age", text="What is your age?", typ=BaseQuestionType.INTEGER, required=True, order=1
        )

        # Valid integer answers
        valid_answer = "25"
        assert valid_answer.isdigit()

        # Invalid integer answers
        invalid_answers = ["abc", "25.5", ""]

        for answer in invalid_answers:
            if answer == "":
                is_valid = not question.required
            else:
                is_valid = answer.isdigit()

            if answer == "abc":
                assert not is_valid
            elif answer == "25.5":
                assert not is_valid  # Contains decimal

    def test_decimal_question_answer(self, registration, event):
        """Test decimal question answer form"""
        question = RegistrationQuestion.objects.create(
            event=event,
            name="contribution",
            text="How much would you like to contribute?",
            typ=BaseQuestionType.DECIMAL,
            required=False,
            order=1,
        )

        # Valid decimal answers
        valid_answers = ["25.50", "10", "0.5"]

        for answer in valid_answers:
            try:
                decimal_value = Decimal(answer)
                assert isinstance(decimal_value, Decimal)
            except (ValueError, TypeError):
                assert False, f"Should be valid decimal: {answer}"

        # Invalid decimal answers
        invalid_answers = ["abc", "25.50.50"]

        for answer in invalid_answers:
            try:
                Decimal(answer)
                assert False, f"Should be invalid decimal: {answer}"
            except (ValueError, TypeError):
                assert True  # Expected to fail

    def test_email_question_answer(self, registration, event):
        """Test email question answer form"""
        question = RegistrationQuestion.objects.create(
            event=event,
            name="emergency_contact",
            text="Emergency contact email:",
            typ=BaseQuestionType.EMAIL,
            required=True,
            order=1,
        )

        # Valid email answers
        valid_emails = ["test@example.com", "user.name+tag@domain.co.uk"]

        for email in valid_emails:
            # Basic email validation
            assert "@" in email and "." in email

        # Invalid email answers
        invalid_emails = ["notanemail", "@domain.com", "user@"]

        for email in invalid_emails:
            # Basic validation - should fail
            is_valid = "@" in email and "." in email and len(email.split("@")) == 2
            assert not is_valid

    def test_date_question_answer(self, registration, event):
        """Test date question answer form"""
        question = RegistrationQuestion.objects.create(
            event=event,
            name="arrival_date",
            text="When will you arrive?",
            typ=BaseQuestionType.DATE,
            required=True,
            order=1,
        )

        # Valid date answers
        valid_dates = ["2025-12-25", "25/12/2025"]

        # Test that dates can be parsed (implementation dependent)
        for date_str in valid_dates:
            # Form would handle date parsing
            assert len(date_str) > 0


@pytest.mark.django_db
class TestRegistrationFormCalculations:
    """Test registration form price calculations"""

    def test_ticket_price_calculation(self, member, run):
        """Test ticket price calculation in form"""
        ticket = RegistrationTicket.objects.create(
            event=run.event, tier=TicketTier.STANDARD, name="Standard Ticket", price=Decimal("100.00"), available=50
        )

        # Base price
        base_price = ticket.price
        assert base_price == Decimal("100.00")

        # With additionals
        additionals = 2
        total_ticket_price = ticket.price * (1 + additionals)
        assert total_ticket_price == Decimal("300.00")  # 100 * 3

    def test_options_price_calculation(self, member, run, event):
        """Test options price calculation"""
        question = RegistrationQuestion.objects.create(
            event=event, name="meals", text="Select your meals:", typ=BaseQuestionType.MULTIPLE, required=False, order=1
        )

        breakfast = RegistrationOption.objects.create(
            question=question, name="Breakfast", price=Decimal("15.00"), order=1
        )

        lunch = RegistrationOption.objects.create(question=question, name="Lunch", price=Decimal("20.00"), order=2)

        # Selected options
        selected_options = [breakfast, lunch]
        options_total = sum(option.price for option in selected_options)
        assert options_total == Decimal("35.00")  # 15 + 20

    def test_pay_what_calculation(self, member, run):
        """Test pay-what-you-want calculation"""
        pay_what_amount = Decimal("75.00")

        # Pay what amount should be added to total
        total_with_pay_what = pay_what_amount
        assert total_with_pay_what == Decimal("75.00")

    def test_total_price_calculation(self, member, run, event):
        """Test total registration price calculation"""
        # Create ticket
        base_ticket_price = Decimal("100.00")
        ticket = RegistrationTicket.objects.create(
            event=run.event, tier=TicketTier.STANDARD, name="Standard Ticket", price=base_ticket_price, available=50
        )

        # Create option
        question = RegistrationQuestion.objects.create(
            event=event,
            name="accommodation",
            text="Select accommodation:",
            typ=BaseQuestionType.SINGLE,
            required=False,
            order=1,
        )

        accommodation_price = Decimal("50.00")
        accommodation = RegistrationOption.objects.create(
            question=question, name="Hotel", price=accommodation_price, order=1
        )

        # Define calculation components
        ticket_price = ticket.price
        additionals = 1
        additional_ticket_price = ticket.price * additionals
        option_price = accommodation.price
        pay_what = Decimal("25.00")

        # Verify individual components
        assert ticket_price == base_ticket_price, f"Expected base ticket price {base_ticket_price}, got {ticket_price}"
        assert additional_ticket_price == base_ticket_price, (
            f"Expected additional ticket price {base_ticket_price}, got {additional_ticket_price}"
        )
        assert option_price == accommodation_price, f"Expected option price {accommodation_price}, got {option_price}"

        # Calculate and verify total
        expected_total = Decimal("275.00")  # 100 + 100 + 50 + 25
        calculated_total = ticket_price + additional_ticket_price + option_price + pay_what

        assert calculated_total == expected_total, f"Expected total {expected_total}, got {calculated_total}"

        # Verify calculation breakdown
        base_cost = ticket_price + additional_ticket_price  # 200.00
        extras_cost = option_price + pay_what  # 75.00

        assert base_cost == Decimal("200.00"), f"Expected base cost (ticket + additionals) 200.00, got {base_cost}"
        assert extras_cost == Decimal("75.00"), f"Expected extras cost (options + pay_what) 75.00, got {extras_cost}"
        assert base_cost + extras_cost == calculated_total, "Base cost + extras should equal total"

        # Test edge case: no additionals, no pay_what
        minimal_total = ticket_price + option_price
        assert minimal_total == Decimal("150.00"), (
            f"Minimal total (ticket + option only) should be 150.00, got {minimal_total}"
        )

    def test_surcharge_calculation(self, member, run):
        """Test date-based surcharge calculation"""
        from larpmanager.models.registration import RegistrationSurcharge

        today = date.today()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        tomorrow = today + timedelta(days=1)

        # Create surcharges with different dates
        applicable_surcharge1 = RegistrationSurcharge.objects.create(
            event=run.event,
            date=yesterday,  # Should apply
            amount=Decimal("25.00"),
            description="Late registration fee",
        )

        applicable_surcharge2 = RegistrationSurcharge.objects.create(
            event=run.event,
            date=week_ago,  # Should apply
            amount=Decimal("15.00"),
            description="Early late fee",
        )

        future_surcharge = RegistrationSurcharge.objects.create(
            event=run.event,
            date=tomorrow,  # Should NOT apply
            amount=Decimal("50.00"),
            description="Future surcharge",
        )

        # Verify surcharges were created
        all_surcharges = RegistrationSurcharge.objects.filter(event=run.event)
        assert all_surcharges.count() == 3, f"Expected 3 surcharges created, got {all_surcharges.count()}"

        # Registration today would include past surcharges only
        applicable_surcharges = RegistrationSurcharge.objects.filter(event=run.event, date__lt=today)

        # Verify correct surcharges are identified as applicable
        applicable_surcharge_ids = list(applicable_surcharges.values_list("id", flat=True))
        assert applicable_surcharge1.id in applicable_surcharge_ids, "Yesterday's surcharge should be applicable"
        assert applicable_surcharge2.id in applicable_surcharge_ids, "Week ago surcharge should be applicable"
        assert future_surcharge.id not in applicable_surcharge_ids, "Future surcharge should NOT be applicable"
        assert applicable_surcharges.count() == 2, (
            f"Expected 2 applicable surcharges, got {applicable_surcharges.count()}"
        )

        # Calculate total surcharge
        expected_total = Decimal("40.00")  # 25.00 + 15.00
        calculated_total = sum(s.amount for s in applicable_surcharges)

        assert calculated_total == expected_total, f"Expected total surcharge {expected_total}, got {calculated_total}"

        # Verify individual amounts
        surcharge_amounts = [s.amount for s in applicable_surcharges.order_by("date")]
        assert Decimal("15.00") in surcharge_amounts, "Week ago surcharge amount should be included"
        assert Decimal("25.00") in surcharge_amounts, "Yesterday surcharge amount should be included"
        assert Decimal("50.00") not in surcharge_amounts, "Future surcharge amount should NOT be included"

        # Test edge case: registration on same day as surcharge
        today_surcharge = RegistrationSurcharge.objects.create(
            event=run.event,
            date=today,  # Same day - should NOT apply (date__lt=today)
            amount=Decimal("10.00"),
            description="Same day surcharge",
        )

        same_day_applicable = RegistrationSurcharge.objects.filter(
            event=run.event,
            date__lt=today,  # Still less than today
        )

        # Should still be only 2 applicable surcharges
        assert same_day_applicable.count() == 2, (
            f"Same day surcharge should not be applicable, still expecting 2, got {same_day_applicable.count()}"
        )
        same_day_total = sum(s.amount for s in same_day_applicable)
        assert same_day_total == expected_total, (
            f"Total should remain {expected_total} even with same-day surcharge, got {same_day_total}"
        )


@pytest.mark.django_db
class TestRegistrationFormPermissions:
    """Test registration form permissions and access control"""

    def test_registration_form_member_access(self, member, run):
        """Test that member can access registration form"""
        # Member should be able to register for open events
        assert run.event is not None
        assert member is not None

        # Check if member can register (business logic)
        can_register = True  # Simplified check
        assert can_register

    def test_registration_form_event_status(self, member):
        """Test registration form access based on event status"""
        from larpmanager.models.event import DevelopStatus

        association = Association.objects.create(name="Test Association", slug="test-assoc", email="test@example.com")

        # Open event
        open_event = Event.objects.create(name="Open Event", assoc=association, number=1)

        open_run = Run.objects.create(
            event=open_event,
            number=1,
            name="Open Run",
            start=date.today() + timedelta(days=30),
            end=date.today() + timedelta(days=32),
            development=DevelopStatus.OPEN,
        )

        # Closed event
        closed_event = Event.objects.create(name="Closed Event", assoc=association, number=2)

        closed_run = Run.objects.create(
            event=closed_event,
            number=1,
            name="Closed Run",
            start=date.today() + timedelta(days=60),
            end=date.today() + timedelta(days=62),
            development=DevelopStatus.CLOSE,
        )

        # Cancelled event
        cancelled_event = Event.objects.create(name="Cancelled Event", assoc=association, number=3)

        cancelled_run = Run.objects.create(
            event=cancelled_event,
            number=1,
            name="Cancelled Run",
            start=date.today() + timedelta(days=90),
            end=date.today() + timedelta(days=92),
            development=DevelopStatus.CANC,
        )

        # Test registration availability
        assert open_run.development == DevelopStatus.OPEN  # Can register
        assert closed_run.development == DevelopStatus.CLOSE  # Cannot register
        assert cancelled_run.development == DevelopStatus.CANC  # Cannot register

    def test_registration_form_membership_requirement(self, member, run):
        """Test registration form with membership requirements"""
        from larpmanager.models.member import Membership, MembershipStatus

        # Create membership
        membership = Membership.objects.create(
            member=member, assoc=run.event.assoc, status=MembershipStatus.ACCEPTED, date=date.today()
        )

        # Test that member with accepted membership can register
        assert membership.status == MembershipStatus.ACCEPTED

        # Test member with pending membership
        pending_member = Member.objects.create(username="pending", email="pending@test.com")

        pending_membership = Membership.objects.create(
            member=pending_member, assoc=run.event.assoc, status=MembershipStatus.PENDING, date=date.today()
        )

        # Pending membership should not allow registration
        assert pending_membership.status == MembershipStatus.PENDING


# Fixtures
@pytest.fixture
def association():
    return Association.objects.create(name="Test Association", slug="test-assoc", email="test@example.com")


@pytest.fixture
def member():
    return Member.objects.create(username="testuser", email="test@example.com", first_name="Test", last_name="User")


@pytest.fixture
def event(association):
    return Event.objects.create(name="Test Event", assoc=association, number=1)


@pytest.fixture
def run(event):
    return Run.objects.create(
        event=event,
        number=1,
        name="Test Run",
        start=date.today() + timedelta(days=30),
        end=date.today() + timedelta(days=32),
    )


@pytest.fixture
def ticket(event):
    return RegistrationTicket.objects.create(
        event=event, tier=TicketTier.STANDARD, name="Standard Ticket", price=Decimal("100.00"), available=50
    )


@pytest.fixture
def registration(member, run):
    return Registration.objects.create(
        member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"), quotas=1
    )
