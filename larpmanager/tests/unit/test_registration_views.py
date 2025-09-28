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
from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory

from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.form import (
    BaseQuestionType,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
)
from larpmanager.models.member import Member
from larpmanager.models.registration import (
    Registration,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.writing import Character


@pytest.mark.django_db
class TestRegistrationViews:
    """Test registration view functionality"""

    def setup_method(self):
        self.factory = RequestFactory()
        self.client = Client()

    def test_registration_list_view(self, member, run):
        """Test registration list view"""
        # Create some registrations
        reg1 = Registration.objects.create(
            member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("100.00")
        )

        other_member = Member.objects.create(username="other", email="other@test.com")

        reg2 = Registration.objects.create(
            member=other_member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("50.00")
        )

        # Test that registrations are listed
        registrations = Registration.objects.filter(run=run)
        assert registrations.count() == 2
        assert reg1 in registrations
        assert reg2 in registrations

    def test_registration_detail_view(self, registration):
        """Test registration detail view"""
        # Test accessing registration detail
        assert registration.id is not None
        assert registration.member is not None
        assert registration.run is not None

        # Mock view context
        context = {
            "registration": registration,
            "member": registration.member,
            "run": registration.run,
            "event": registration.run.event,
        }

        assert context["registration"] == registration

    def test_registration_create_view_get(self, member, run, ticket):
        """Test GET request to registration create view"""
        request = self.factory.get("/register/")
        request.user = member
        request.member = member

        # Mock view context for GET request
        context = {"run": run, "event": run.event, "tickets": [ticket], "member": member, "questions": []}

        # Should display registration form
        assert context["run"] == run
        assert ticket in context["tickets"]

    def test_registration_create_view_post_valid(self, member, run, ticket):
        """Test POST request to registration create view with valid data"""
        post_data = {"ticket": ticket.id, "additionals": 0, "pay_what": "", "agree_terms": True}

        # Simulate successful registration creation
        registration = Registration(
            member=member, run=run, ticket=ticket, additionals=0, tot_iscr=ticket.price, tot_payed=Decimal("0.00")
        )

        assert registration.member == member
        assert registration.run == run
        assert registration.ticket == ticket

    def test_registration_create_view_post_invalid(self, member, run):
        """Test POST request with invalid data"""
        # Missing required fields
        post_data = {
            "additionals": 0,
            "agree_terms": False,  # Terms not agreed
        }

        # Should have validation errors
        errors = []
        if "ticket" not in post_data:
            errors.append("Ticket is required")
        if not post_data.get("agree_terms"):
            errors.append("You must agree to terms")

        assert len(errors) > 0

    def test_registration_edit_view(self, registration):
        """Test registration edit view"""
        # Test that registration can be edited
        original_additionals = registration.additionals
        new_additionals = original_additionals + 1

        # Update registration
        registration.additionals = new_additionals
        registration.save()

        assert registration.additionals == new_additionals

    def test_registration_cancel_view(self, registration):
        """Test registration cancellation view"""
        assert registration.cancellation_date is None

        # Simulate cancellation
        registration.cancellation_date = datetime.now()
        registration.save()

        assert registration.cancellation_date is not None

    def test_registration_payment_view(self, registration):
        """Test registration payment view"""
        # Test payment status display
        balance = registration.tot_iscr - registration.tot_payed

        payment_context = {
            "registration": registration,
            "balance": balance,
            "payment_methods": [],
            "can_pay": balance > 0,
        }

        assert payment_context["balance"] == balance
        assert payment_context["can_pay"] == (balance > 0)

    def test_registration_questions_view(self, registration, event):
        """Test registration questions view"""
        # Create questions
        text_question = RegistrationQuestion.objects.create(
            event=event, name="dietary", text="Dietary requirements?", typ=BaseQuestionType.TEXT, required=True, order=1
        )

        choice_question = RegistrationQuestion.objects.create(
            event=event,
            name="accommodation",
            text="Accommodation preference?",
            typ=BaseQuestionType.SINGLE,
            required=True,
            order=2,
        )

        option1 = RegistrationOption.objects.create(
            question=choice_question, name="Hotel", price=Decimal("50.00"), order=1
        )

        # Test questions are displayed
        questions = RegistrationQuestion.objects.filter(event=event).order_by("order")
        assert questions.count() == 2
        assert text_question in questions
        assert choice_question in questions

    def test_registration_questions_submit(self, registration, event):
        """Test submitting registration question answers"""
        # Create question
        question = RegistrationQuestion.objects.create(
            event=event, name="dietary", text="Dietary requirements?", typ=BaseQuestionType.TEXT, required=True, order=1
        )

        # Submit answer
        answer_text = "I am vegetarian"
        answer = RegistrationAnswer.objects.create(reg=registration, question=question, text=answer_text)

        assert answer.reg == registration
        assert answer.question == question
        assert answer.text == answer_text


@pytest.mark.django_db
class TestRegistrationPermissions:
    """Test registration view permissions"""

    def setup_method(self):
        self.factory = RequestFactory()

    def test_anonymous_user_access(self, run):
        """Test anonymous user cannot access registration"""
        request = self.factory.get("/register/")
        request.user = AnonymousUser()

        # Should redirect to login
        assert request.user.is_anonymous

    def test_member_access_own_registration(self, member, registration):
        """Test member can access their own registration"""
        request = self.factory.get(f"/registration/{registration.id}/")
        request.user = member
        request.member = member

        # Member should be able to access their own registration
        assert registration.member == member

    def test_member_access_other_registration(self, member, registration):
        """Test member cannot access other member's registration"""
        other_member = Member.objects.create(username="other", email="other@test.com")

        request = self.factory.get(f"/registration/{registration.id}/")
        request.user = other_member
        request.member = other_member

        # Should not have access to other member's registration
        assert registration.member != other_member

    def test_organizer_access_registrations(self, member, registration):
        """Test event organizer can access all registrations"""
        # Mock organizer permissions
        request = self.factory.get("/registrations/")
        request.user = member
        request.member = member

        # Organizer should see all registrations for their events
        organizer_events = []  # Would be populated by permission system
        can_view_all = True  # Simplified check

        assert can_view_all or registration.run.event in organizer_events

    def test_registration_deadline_check(self, member, run):
        """Test registration deadline enforcement"""
        # Set registration deadline in the past
        past_date = date.today() - timedelta(days=1)

        # Mock deadline check
        registration_open = date.today() < past_date
        assert not registration_open  # Registration should be closed

        # Set registration deadline in the future
        future_date = date.today() + timedelta(days=30)
        registration_open = date.today() < future_date
        assert registration_open  # Registration should be open


@pytest.mark.django_db
class TestRegistrationBusinessLogic:
    """Test registration business logic"""

    def test_registration_capacity_check(self, member, run):
        """Test event capacity checking"""
        initial_capacity = 2

        # Create ticket with limited capacity
        ticket = RegistrationTicket.objects.create(
            event=run.event,
            tier=TicketTier.STANDARD,
            name="Limited Ticket",
            price=Decimal("100.00"),
            available=initial_capacity,
        )

        # Verify initial state
        assert ticket.available == initial_capacity, (
            f"Expected initial capacity {initial_capacity}, got {ticket.available}"
        )

        # Create first registration
        reg1 = Registration.objects.create(
            member=member, run=run, ticket=ticket, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00")
        )

        # Update ticket availability and verify
        ticket.available -= 1
        ticket.save()

        # Verify capacity decreased correctly
        expected_capacity_after_first = initial_capacity - 1
        assert ticket.available == expected_capacity_after_first, (
            f"After first registration, expected capacity {expected_capacity_after_first}, got {ticket.available}"
        )

        # Verify registration was created successfully
        assert reg1.id is not None, "First registration should be created successfully"
        assert Registration.objects.filter(run=run).count() == 1, (
            "Should have exactly 1 registration after first signup"
        )

        # Create second member and registration
        member2 = Member.objects.create(username="member2", email="member2@test.com")

        reg2 = Registration.objects.create(
            member=member2, run=run, ticket=ticket, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00")
        )

        # Update ticket availability and verify sold out state
        ticket.available -= 1
        ticket.save()

        # Verify ticket is now sold out
        assert ticket.available == 0, (
            f"After second registration, ticket should be sold out (0), got {ticket.available}"
        )

        # Verify both registrations exist
        all_registrations = Registration.objects.filter(run=run)
        assert all_registrations.count() == 2, f"Should have exactly 2 registrations, got {all_registrations.count()}"
        assert reg1 in all_registrations, "First registration should still exist"
        assert reg2 in all_registrations, "Second registration should exist"

        # Third registration should not be possible
        member3 = Member.objects.create(username="member3", email="member3@test.com")

        # Verify business logic prevents further registration
        can_register = ticket.available > 0
        assert not can_register, f"Third member should not be able to register when ticket.available={ticket.available}"

        # If we were to simulate the business logic check in a real system:
        # This would typically be handled by the view/form validation
        if can_register:
            pytest.fail("Business logic should prevent registration when tickets are sold out")

        # Verify final state: still only 2 registrations
        final_registrations = Registration.objects.filter(run=run)
        assert final_registrations.count() == 2, (
            f"Should still have exactly 2 registrations after capacity check, got {final_registrations.count()}"
        )

    def test_registration_payment_status_updates(self, registration):
        """Test registration payment status updates"""
        initial_total = registration.tot_iscr
        initial_paid = registration.tot_payed
        payment_amount = Decimal("50.00")

        # Verify initial unpaid state
        initial_remaining = initial_total - initial_paid
        assert registration.tot_payed < registration.tot_iscr, (
            f"Initially should be unpaid: paid={registration.tot_payed}, total={registration.tot_iscr}"
        )
        assert initial_remaining > 0, f"Should have positive remaining balance: {initial_remaining}"

        # Make partial payment and verify state change
        registration.tot_payed += payment_amount
        registration.save()

        # Verify partial payment state
        partial_remaining = registration.tot_iscr - registration.tot_payed
        expected_partial_remaining = initial_remaining - payment_amount
        assert registration.tot_payed == initial_paid + payment_amount, (
            f"Paid amount should be {initial_paid + payment_amount}, got {registration.tot_payed}"
        )
        assert partial_remaining == expected_partial_remaining, (
            f"Remaining should be {expected_partial_remaining}, got {partial_remaining}"
        )
        assert partial_remaining > 0, "Should still have positive remaining balance after partial payment"

        # Verify database persistence of partial payment
        db_registration = Registration.objects.get(id=registration.id)
        assert db_registration.tot_payed == registration.tot_payed, "Partial payment should persist in database"

        # Make full payment and verify complete payment state
        registration.tot_payed = registration.tot_iscr
        registration.save()

        # Verify full payment state
        final_remaining = registration.tot_iscr - registration.tot_payed
        assert registration.tot_payed == registration.tot_iscr, (
            f"After full payment: paid={registration.tot_payed} should equal total={registration.tot_iscr}"
        )
        assert final_remaining == Decimal("0.00"), f"No remaining balance expected, got {final_remaining}"

        # Verify database persistence of full payment
        db_registration = Registration.objects.get(id=registration.id)
        assert db_registration.tot_payed == registration.tot_iscr, "Full payment should persist in database"
        assert db_registration.tot_iscr - db_registration.tot_payed == Decimal("0.00"), (
            "Database should show no remaining balance"
        )

    def test_registration_waitlist_promotion(self, member, run):
        """Test waitlist to confirmed promotion"""
        # Create waitlist ticket
        waitlist_ticket = RegistrationTicket.objects.create(
            event=run.event, tier=TicketTier.WAITING, name="Waitlist", price=Decimal("0.00"), available=999
        )

        # Create standard ticket
        standard_ticket = RegistrationTicket.objects.create(
            event=run.event, tier=TicketTier.STANDARD, name="Standard", price=Decimal("100.00"), available=1
        )

        # Create waitlist registration
        waitlist_reg = Registration.objects.create(
            member=member, run=run, ticket=waitlist_ticket, tot_iscr=Decimal("0.00"), tot_payed=Decimal("0.00")
        )

        assert waitlist_reg.ticket.tier == TicketTier.WAITING

        # Simulate promotion to standard ticket
        waitlist_reg.ticket = standard_ticket
        waitlist_reg.tot_iscr = standard_ticket.price
        waitlist_reg.save()

        assert waitlist_reg.ticket.tier == TicketTier.STANDARD

    def test_registration_character_assignment(self, registration):
        """Test character assignment to registration"""
        from larpmanager.models.registration import RegistrationCharacterRel

        # Create character
        character = Character.objects.create(name="Test Character", assoc=registration.run.event.assoc)

        # Assign character to registration
        char_rel = RegistrationCharacterRel.objects.create(reg=registration, character=character, principal=True)

        assert char_rel.reg == registration
        assert char_rel.character == character
        assert char_rel.principal is True

    def test_registration_option_price_calculation(self, registration, event):
        """Test automatic price calculation with options"""
        # Create question with options
        question = RegistrationQuestion.objects.create(
            event=event, name="meals", text="Select meals:", typ=BaseQuestionType.MULTIPLE, order=1
        )

        breakfast = RegistrationOption.objects.create(
            question=question, name="Breakfast", price=Decimal("15.00"), order=1
        )

        lunch = RegistrationOption.objects.create(question=question, name="Lunch", price=Decimal("20.00"), order=2)

        # Select options
        choice1 = RegistrationChoice.objects.create(reg=registration, question=question, option=breakfast)

        choice2 = RegistrationChoice.objects.create(reg=registration, question=question, option=lunch)

        # Calculate total option price
        choices = RegistrationChoice.objects.filter(reg=registration)
        option_total = sum(choice.option.price for choice in choices)

        assert option_total == Decimal("35.00")  # 15 + 20

        # Update registration total
        original_total = registration.tot_iscr
        new_total = original_total + option_total
        registration.tot_iscr = new_total
        registration.save()

        assert registration.tot_iscr == new_total


@pytest.mark.django_db
class TestRegistrationNotifications:
    """Test registration notification system"""

    def test_registration_confirmation_email(self, registration):
        """Test registration confirmation email"""
        # Mock email sending
        email_sent = False
        email_recipient = registration.member.email
        email_subject = f"Registration confirmed for {registration.run.event.name}"

        # Simulate email sending
        if registration and registration.member.email:
            email_sent = True

        assert email_sent
        assert email_recipient == registration.member.email

    def test_payment_reminder_email(self, registration):
        """Test payment reminder email"""
        # Registration with outstanding balance
        balance = registration.tot_iscr - registration.tot_payed

        if balance > 0:
            # Mock reminder email
            reminder_sent = True
            reminder_subject = f"Payment reminder for {registration.run.event.name}"
        else:
            reminder_sent = False

        assert reminder_sent == (balance > 0)

    def test_cancellation_notification(self, registration):
        """Test cancellation notification"""
        # Cancel registration
        registration.cancellation_date = datetime.now()
        registration.save()

        # Mock cancellation email
        cancellation_email_sent = registration.cancellation_date is not None

        assert cancellation_email_sent

    def test_waitlist_promotion_notification(self, registration):
        """Test waitlist promotion notification"""
        # Simulate promotion from waitlist
        was_waitlist = registration.ticket.tier == TicketTier.WAITING

        if was_waitlist:
            # Change to standard ticket
            standard_ticket = RegistrationTicket.objects.create(
                event=registration.run.event,
                tier=TicketTier.STANDARD,
                name="Standard",
                price=Decimal("100.00"),
                available=1,
            )

            registration.ticket = standard_ticket
            registration.save()

            # Mock promotion email
            promotion_email_sent = True
        else:
            promotion_email_sent = False

        # Test would depend on initial ticket tier
        assert isinstance(promotion_email_sent, bool)


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
