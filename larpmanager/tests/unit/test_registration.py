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
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models

from larpmanager.models.association import Association
from larpmanager.models.event import DevelopStatus, Event, Run
from larpmanager.models.form import (
    BaseQuestionType,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
)
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import (
    Registration,
    RegistrationInstallment,
    RegistrationSurcharge,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.writing import Character


@pytest.mark.django_db
class TestRegistrationModel:
    """Test Registration model functionality"""

    def test_registration_creation(self, member, run):
        """Test basic registration creation"""
        registration = Registration.objects.create(
            member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"), quotas=1
        )

        # Verify registration was created with correct attributes
        assert registration.id is not None, "Registration should have an ID after creation"
        assert registration.member == member, f"Expected member {member}, got {registration.member}"
        assert registration.run == run, f"Expected run {run}, got {registration.run}"
        assert registration.tot_iscr == Decimal("100.00"), f"Expected tot_iscr 100.00, got {registration.tot_iscr}"
        assert registration.tot_payed == Decimal("0.00"), f"Expected tot_payed 0.00, got {registration.tot_payed}"
        assert registration.quotas == 1, f"Expected quotas 1, got {registration.quotas}"
        assert registration.cancellation_date is None, "New registration should not be cancelled"

        # Verify registration exists in database
        db_registration = Registration.objects.get(id=registration.id)
        assert db_registration.member == member, "Registration not properly saved to database"
        assert db_registration.run == run, "Run association not properly saved"

    def test_registration_str_representation(self, member, run):
        """Test string representation of registration"""
        registration = Registration(member=member, run=run, tot_iscr=Decimal("100.00"))

        expected = f"Registration of {member} for {run}"
        assert str(registration) == expected

    def test_registration_with_ticket(self, member, run, ticket):
        """Test registration with ticket"""
        registration = Registration.objects.create(
            member=member, run=run, ticket=ticket, tot_iscr=ticket.price, tot_payed=Decimal("0.00")
        )

        assert registration.ticket == ticket
        assert registration.tot_iscr == ticket.price

    def test_registration_cancellation(self, registration):
        """Test registration cancellation"""
        cancellation_date = datetime.now()
        registration.cancellation_date = cancellation_date
        registration.save()

        assert registration.cancellation_date == cancellation_date

    def test_registration_payment_calculations(self, registration):
        """Test payment status calculations"""
        initial_iscr = Decimal("100.00")
        partial_payment = Decimal("50.00")
        full_payment = Decimal("100.00")
        overpayment = Decimal("120.00")

        registration.tot_iscr = initial_iscr
        registration.tot_payed = partial_payment
        registration.save()

        # Test partial payment state
        remaining_balance = registration.tot_iscr - registration.tot_payed
        assert registration.tot_iscr > registration.tot_payed, (
            f"Partial payment: {registration.tot_payed} should be less than total {registration.tot_iscr}"
        )
        assert remaining_balance == Decimal("50.00"), f"Expected remaining balance 50.00, got {remaining_balance}"

        # Test full payment state
        registration.tot_payed = full_payment
        registration.save()
        remaining_balance = registration.tot_iscr - registration.tot_payed
        assert registration.tot_iscr == registration.tot_payed, (
            f"Full payment: {registration.tot_payed} should equal total {registration.tot_iscr}"
        )
        assert remaining_balance == Decimal("0.00"), f"Expected no remaining balance, got {remaining_balance}"

        # Test overpayment state
        registration.tot_payed = overpayment
        registration.save()
        overpaid_amount = registration.tot_payed - registration.tot_iscr
        assert registration.tot_payed > registration.tot_iscr, (
            f"Overpayment: {registration.tot_payed} should be greater than total {registration.tot_iscr}"
        )
        assert overpaid_amount == Decimal("20.00"), f"Expected overpayment of 20.00, got {overpaid_amount}"

    def test_registration_with_additionals(self, member, run, ticket):
        """Test registration with additional tickets"""
        registration = Registration.objects.create(
            member=member,
            run=run,
            ticket=ticket,
            additionals=2,  # 2 additional tickets
            tot_iscr=ticket.price * 3,  # Base + 2 additional
            tot_payed=Decimal("0.00"),
        )

        assert registration.additionals == 2
        assert registration.tot_iscr == ticket.price * 3

    def test_registration_with_pay_what(self, member, run):
        """Test registration with pay-what-you-want amount"""
        pay_what_amount = Decimal("75.00")
        registration = Registration.objects.create(
            member=member, run=run, pay_what=pay_what_amount, tot_iscr=pay_what_amount, tot_payed=Decimal("0.00")
        )

        assert registration.pay_what == pay_what_amount

    def test_registration_surcharge(self, registration):
        """Test registration surcharge handling"""
        surcharge = Decimal("15.00")
        registration.surcharge = surcharge
        registration.save()

        assert registration.surcharge == surcharge

    def test_registration_unique_constraint(self, member, run):
        """Test that member can only have one registration per run"""
        # Create first registration
        first_registration = Registration.objects.create(
            member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00")
        )

        # Verify first registration was created successfully
        assert first_registration.id is not None, "First registration should be created successfully"

        # Verify only one registration exists for this member/run combination
        existing_registrations = Registration.objects.filter(member=member, run=run)
        assert existing_registrations.count() == 1, f"Expected 1 registration, found {existing_registrations.count()}"

        # Try to create second registration for same member and run
        with pytest.raises(IntegrityError) as excinfo:
            Registration.objects.create(member=member, run=run, tot_iscr=Decimal("50.00"), tot_payed=Decimal("0.00"))

        # Verify the IntegrityError was raised and still only one registration exists
        assert "unique" in str(excinfo.value).lower() or "duplicate" in str(excinfo.value).lower(), (
            "IntegrityError should mention uniqueness or duplication"
        )

        # Verify database state after failed insertion
        final_registrations = Registration.objects.filter(member=member, run=run)
        assert final_registrations.count() == 1, (
            f"After failed duplicate insertion, should still have exactly 1 registration, found {final_registrations.count()}"
        )
        assert final_registrations.first().id == first_registration.id, (
            "The original registration should still exist unchanged"
        )


@pytest.mark.django_db
class TestRegistrationTicket:
    """Test RegistrationTicket model"""

    def test_ticket_creation(self, event):
        """Test ticket creation"""
        ticket = RegistrationTicket.objects.create(
            event=event,
            tier=TicketTier.STANDARD,
            name="Standard Ticket",
            price=Decimal("100.00"),
            description="Standard event ticket",
            available=50,
        )

        assert ticket.event == event
        assert ticket.tier == TicketTier.STANDARD
        assert ticket.name == "Standard Ticket"
        assert ticket.price == Decimal("100.00")
        assert ticket.available == 50

    def test_ticket_str_representation(self, event):
        """Test ticket string representation"""
        ticket = RegistrationTicket(
            event=event, tier=TicketTier.STANDARD, name="Standard Ticket", price=Decimal("100.00")
        )

        expected = f"Standard Ticket - {event} (Standard - €100.00)"
        assert str(ticket) == expected

    def test_ticket_tiers(self, event):
        """Test different ticket tiers"""
        tiers = [
            (TicketTier.STANDARD, "Standard"),
            (TicketTier.EARLY_BIRD, "Early Bird"),
            (TicketTier.LATE, "Late"),
            (TicketTier.STAFF, "Staff"),
            (TicketTier.NPC, "NPC"),
            (TicketTier.WAITING, "Waiting List"),
        ]

        for tier, name in tiers:
            ticket = RegistrationTicket.objects.create(
                event=event, tier=tier, name=f"{name} Ticket", price=Decimal("100.00"), available=10
            )
            assert ticket.tier == tier

    def test_ticket_validation(self, event):
        """Test ticket validation"""
        # Test negative price validation
        with pytest.raises(ValidationError):
            ticket = RegistrationTicket(
                event=event, tier=TicketTier.STANDARD, name="Invalid Ticket", price=Decimal("-50.00"), available=10
            )
            ticket.full_clean()

    def test_ticket_availability(self, ticket):
        """Test ticket availability tracking"""
        initial_available = ticket.available
        expected_after_purchase = initial_available - 1

        # Verify initial state
        assert initial_available > 0, f"Ticket should have initial availability > 0, got {initial_available}"

        # Simulate ticket purchase
        ticket.available -= 1
        ticket.save()

        # Verify availability decreased by exactly 1
        assert ticket.available == expected_after_purchase, (
            f"Expected availability {expected_after_purchase}, got {ticket.available}"
        )

        # Verify the change persists in database
        db_ticket = RegistrationTicket.objects.get(id=ticket.id)
        assert db_ticket.available == expected_after_purchase, (
            f"Database should reflect new availability {expected_after_purchase}, got {db_ticket.available}"
        )

        # Test boundary condition - cannot go below 0
        if ticket.available > 0:
            ticket.available = 0
            ticket.save()
            assert ticket.available == 0, "Availability should be able to reach 0"

            # In real system, business logic should prevent going negative
            # Here we just verify the state is as expected


@pytest.mark.django_db
class TestRegistrationQuestions:
    """Test registration questions and answers"""

    def test_question_creation(self, event):
        """Test registration question creation"""
        question = RegistrationQuestion.objects.create(
            event=event,
            name="dietary_requirements",
            text="Do you have any dietary requirements?",
            typ=BaseQuestionType.TEXT,
            required=True,
            order=1,
        )

        assert question.event == event
        assert question.name == "dietary_requirements"
        assert question.typ == BaseQuestionType.TEXT
        assert question.required is True

    def test_question_types(self, event):
        """Test different question types"""
        types = [
            BaseQuestionType.TEXT,
            BaseQuestionType.TEXTAREA,
            BaseQuestionType.SINGLE,
            BaseQuestionType.MULTIPLE,
            BaseQuestionType.BOOLEAN,
            BaseQuestionType.INTEGER,
            BaseQuestionType.DECIMAL,
            BaseQuestionType.DATE,
            BaseQuestionType.EMAIL,
            BaseQuestionType.PHONE,
            BaseQuestionType.URL,
        ]

        for i, question_type in enumerate(types):
            question = RegistrationQuestion.objects.create(
                event=event, name=f"question_{i}", text=f"Question {i}", typ=question_type, order=i
            )
            assert question.typ == question_type

    def test_question_with_options(self, event):
        """Test question with multiple choice options"""
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

        assert option1.question == question
        assert option2.question == question
        assert option1.price == Decimal("50.00")
        assert option2.price == Decimal("20.00")

    def test_registration_answer_text(self, registration, question):
        """Test text answer to registration question"""
        answer_text = "I am vegetarian"

        # Create answer and verify creation
        answer = RegistrationAnswer.objects.create(reg=registration, question=question, text=answer_text)

        # Verify answer object properties
        assert answer.id is not None, "Answer should have an ID after creation"
        assert answer.reg == registration, f"Expected registration {registration}, got {answer.reg}"
        assert answer.question == question, f"Expected question {question}, got {answer.question}"
        assert answer.text == answer_text, f"Expected text '{answer_text}', got '{answer.text}'"

        # Verify database persistence
        db_answer = RegistrationAnswer.objects.get(id=answer.id)
        assert db_answer.reg == registration, "Registration association should persist in database"
        assert db_answer.question == question, "Question association should persist in database"
        assert db_answer.text == answer_text, (
            f"Answer text should persist in database: expected '{answer_text}', got '{db_answer.text}'"
        )

        # Verify answer can be retrieved through registration
        reg_answers = RegistrationAnswer.objects.filter(reg=registration)
        assert answer in reg_answers, "Answer should be retrievable through registration filter"

        # Verify answer can be retrieved through question
        question_answers = RegistrationAnswer.objects.filter(question=question)
        assert answer in question_answers, "Answer should be retrievable through question filter"

    def test_registration_choice_single(self, registration, question_with_options):
        """Test single choice answer"""
        question, option1, option2 = question_with_options

        choice = RegistrationChoice.objects.create(reg=registration, question=question, option=option1)

        assert choice.reg == registration
        assert choice.question == question
        assert choice.option == option1

    def test_registration_choice_multiple(self, registration, question_with_options):
        """Test multiple choice answers"""
        question, option1, option2 = question_with_options

        # Configure question for multiple choice
        question.typ = BaseQuestionType.MULTIPLE
        question.save()

        # Verify question type was updated
        db_question = RegistrationQuestion.objects.get(id=question.id)
        assert db_question.typ == BaseQuestionType.MULTIPLE, f"Question type should be MULTIPLE, got {db_question.typ}"

        # Select both options
        choice1 = RegistrationChoice.objects.create(reg=registration, question=question, option=option1)

        choice2 = RegistrationChoice.objects.create(reg=registration, question=question, option=option2)

        # Verify individual choice creation
        assert choice1.id is not None, "First choice should have an ID after creation"
        assert choice2.id is not None, "Second choice should have an ID after creation"
        assert choice1.reg == registration, f"First choice registration should be {registration}"
        assert choice2.reg == registration, f"Second choice registration should be {registration}"
        assert choice1.option == option1, f"First choice should select option1 {option1}"
        assert choice2.option == option2, f"Second choice should select option2 {option2}"

        # Query and verify multiple selections
        choices = RegistrationChoice.objects.filter(reg=registration, question=question)

        assert choices.count() == 2, f"Expected 2 choices for multiple selection, got {choices.count()}"
        assert choice1 in choices, "First choice should be in query results"
        assert choice2 in choices, "Second choice should be in query results"

        # Verify database consistency
        choice_ids = list(choices.values_list("id", flat=True))
        assert choice1.id in choice_ids, "First choice ID should be in database results"
        assert choice2.id in choice_ids, "Second choice ID should be in database results"

        # Verify option associations in database
        db_choices = RegistrationChoice.objects.filter(reg=registration).select_related("option")
        selected_options = [choice.option for choice in db_choices]
        assert option1 in selected_options, "Option1 should be selected in database"
        assert option2 in selected_options, "Option2 should be selected in database"

        # Verify no duplicate selections for same option
        option1_choices = choices.filter(option=option1)
        option2_choices = choices.filter(option=option2)
        assert option1_choices.count() == 1, f"Should have exactly 1 choice for option1, got {option1_choices.count()}"
        assert option2_choices.count() == 1, f"Should have exactly 1 choice for option2, got {option2_choices.count()}"


@pytest.mark.django_db
class TestRegistrationInstallments:
    """Test registration installment payments"""

    def test_installment_creation(self, event):
        """Test installment creation"""
        installment = RegistrationInstallment.objects.create(
            event=event, order=1, amount=Decimal("50.00"), days_deadline=30, description="First installment"
        )

        assert installment.event == event
        assert installment.order == 1
        assert installment.amount == Decimal("50.00")
        assert installment.days_deadline == 30

    def test_installment_with_date_deadline(self, event):
        """Test installment with specific date deadline"""
        deadline_date = date.today() + timedelta(days=30)
        installment = RegistrationInstallment.objects.create(
            event=event, order=1, amount=Decimal("50.00"), date_deadline=deadline_date, description="First installment"
        )

        assert installment.date_deadline == deadline_date

    def test_installment_ticket_specific(self, event, ticket):
        """Test installment specific to certain tickets"""
        installment = RegistrationInstallment.objects.create(
            event=event, order=1, amount=Decimal("50.00"), days_deadline=30, description="Ticket-specific installment"
        )

        installment.tickets.add(ticket)

        assert ticket in installment.tickets.all()

    def test_installment_ordering(self, event):
        """Test installment ordering"""
        installment2 = RegistrationInstallment.objects.create(
            event=event, order=2, amount=Decimal("50.00"), days_deadline=15
        )

        installment1 = RegistrationInstallment.objects.create(
            event=event, order=1, amount=Decimal("30.00"), days_deadline=30
        )

        installments = RegistrationInstallment.objects.filter(event=event).order_by("order")

        assert list(installments) == [installment1, installment2]


@pytest.mark.django_db
class TestRegistrationSurcharges:
    """Test registration surcharges"""

    def test_surcharge_creation(self, event):
        """Test surcharge creation"""
        surcharge_date = date.today() + timedelta(days=30)
        surcharge = RegistrationSurcharge.objects.create(
            event=event, date=surcharge_date, amount=Decimal("25.00"), description="Late registration fee"
        )

        assert surcharge.event == event
        assert surcharge.date == surcharge_date
        assert surcharge.amount == Decimal("25.00")

    def test_multiple_surcharges(self, event):
        """Test multiple surcharges for an event"""
        surcharge1 = RegistrationSurcharge.objects.create(
            event=event, date=date.today() + timedelta(days=30), amount=Decimal("15.00"), description="First surcharge"
        )

        surcharge2 = RegistrationSurcharge.objects.create(
            event=event, date=date.today() + timedelta(days=60), amount=Decimal("25.00"), description="Second surcharge"
        )

        surcharges = RegistrationSurcharge.objects.filter(event=event)
        assert surcharges.count() == 2
        assert surcharge1 in surcharges
        assert surcharge2 in surcharges

    def test_surcharge_date_ordering(self, event):
        """Test surcharges are properly ordered by date"""
        later_surcharge = RegistrationSurcharge.objects.create(
            event=event, date=date.today() + timedelta(days=60), amount=Decimal("25.00")
        )

        earlier_surcharge = RegistrationSurcharge.objects.create(
            event=event, date=date.today() + timedelta(days=30), amount=Decimal("15.00")
        )

        surcharges = RegistrationSurcharge.objects.filter(event=event).order_by("date")

        assert list(surcharges) == [earlier_surcharge, later_surcharge]


@pytest.mark.django_db
class TestRegistrationWithCharacters:
    """Test registration with character assignment"""

    def test_registration_with_character(self, registration, character):
        """Test linking character to registration"""
        from larpmanager.models.registration import RegistrationCharacterRel

        char_rel = RegistrationCharacterRel.objects.create(reg=registration, character=character, principal=True)

        assert char_rel.reg == registration
        assert char_rel.character == character
        assert char_rel.principal is True

    def test_multiple_characters_per_registration(self, registration):
        """Test registration with multiple characters"""
        from larpmanager.models.registration import RegistrationCharacterRel

        character1 = Character.objects.create(name="Character 1", assoc=registration.run.event.assoc)

        character2 = Character.objects.create(name="Character 2", assoc=registration.run.event.assoc)

        char_rel1 = RegistrationCharacterRel.objects.create(reg=registration, character=character1, principal=True)

        char_rel2 = RegistrationCharacterRel.objects.create(reg=registration, character=character2, principal=False)

        char_rels = RegistrationCharacterRel.objects.filter(reg=registration)
        assert char_rels.count() == 2

        principal_chars = char_rels.filter(principal=True)
        assert principal_chars.count() == 1
        assert principal_chars.first().character == character1


@pytest.mark.django_db
class TestRegistrationValidation:
    """Test registration validation and business rules"""

    def test_registration_for_cancelled_event(self, member):
        """Test registration attempt for cancelled event"""
        event = Event.objects.create(name="Cancelled Event", assoc_id=1, number=1)

        run = Run.objects.create(
            event=event,
            number=1,
            name="Cancelled Run",
            start=date.today() + timedelta(days=30),
            end=date.today() + timedelta(days=32),
            development=DevelopStatus.CANC,
        )

        # Registration for cancelled run should be possible in model
        # but business logic should prevent it
        registration = Registration(member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"))

        # Model allows it, but business logic should handle it
        assert registration.run.development == DevelopStatus.CANC

    def test_registration_payment_status_calculation(self, registration):
        """Test payment status calculation"""
        # Not paid
        registration.tot_iscr = Decimal("100.00")
        registration.tot_payed = Decimal("0.00")

        remaining = registration.tot_iscr - registration.tot_payed
        assert remaining == Decimal("100.00")

        # Partially paid
        registration.tot_payed = Decimal("50.00")
        remaining = registration.tot_iscr - registration.tot_payed
        assert remaining == Decimal("50.00")

        # Fully paid
        registration.tot_payed = Decimal("100.00")
        remaining = registration.tot_iscr - registration.tot_payed
        assert remaining == Decimal("0.00")

        # Overpaid
        registration.tot_payed = Decimal("120.00")
        remaining = registration.tot_iscr - registration.tot_payed
        assert remaining == Decimal("-20.00")

    def test_registration_with_membership_requirement(self, member, run):
        """Test registration requiring membership"""
        # Mock membership check
        membership = Membership.objects.create(
            member=member, assoc=run.event.assoc, status=MembershipStatus.ACCEPTED, date=date.today()
        )

        registration = Registration.objects.create(
            member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00")
        )

        assert registration.member == member
        assert membership.status == MembershipStatus.ACCEPTED


@pytest.mark.django_db
class TestRegistrationQueries:
    """Test registration query methods and managers"""

    def test_active_registrations(self, member, association):
        """Test querying active registrations"""
        # Create active event
        active_event = Event.objects.create(name="Active Event", assoc=association, number=1)

        active_run = Run.objects.create(
            event=active_event,
            number=1,
            name="Active Run",
            start=date.today() + timedelta(days=30),
            end=date.today() + timedelta(days=32),
            development=DevelopStatus.OPEN,
        )

        # Create cancelled event
        cancelled_event = Event.objects.create(name="Cancelled Event", assoc=association, number=2)

        cancelled_run = Run.objects.create(
            event=cancelled_event,
            number=1,
            name="Cancelled Run",
            start=date.today() + timedelta(days=60),
            end=date.today() + timedelta(days=62),
            development=DevelopStatus.CANC,
        )

        # Create registrations
        active_reg = Registration.objects.create(
            member=member, run=active_run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00")
        )

        cancelled_reg = Registration.objects.create(
            member=member, run=cancelled_run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00")
        )

        # Query active registrations (exclude cancelled)
        active_registrations = Registration.objects.exclude(
            run__development__in=[DevelopStatus.CANC, DevelopStatus.DONE]
        )

        assert active_reg in active_registrations
        assert cancelled_reg not in active_registrations

    def test_registrations_by_payment_status(self, association):
        """Test querying registrations by payment status"""
        event = Event.objects.create(name="Test Event", assoc=association, number=1)

        run = Run.objects.create(
            event=event,
            number=1,
            name="Test Run",
            start=date.today() + timedelta(days=30),
            end=date.today() + timedelta(days=32),
        )

        user1 = User.objects.create_user(username="member1", email="member1@test.com")
        member1 = user1.member
        member1.name = "Member"
        member1.surname = "One"
        member1.save()

        user2 = User.objects.create_user(username="member2", email="member2@test.com")
        member2 = user2.member
        member2.name = "Member"
        member2.surname = "Two"
        member2.save()

        user3 = User.objects.create_user(username="member3", email="member3@test.com")
        member3 = user3.member
        member3.name = "Member"
        member3.surname = "Three"
        member3.save()

        # Create registrations with different payment statuses
        unpaid_reg = Registration.objects.create(
            member=member1, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00")
        )

        paid_reg = Registration.objects.create(
            member=member2, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("100.00")
        )

        partial_paid_reg = Registration.objects.create(
            member=member3, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("50.00")
        )

        # Verify all registrations were created
        all_registrations = Registration.objects.filter(run=run)
        assert all_registrations.count() == 3, f"Expected 3 registrations, got {all_registrations.count()}"

        # Query unpaid registrations (including partially paid)
        unpaid = Registration.objects.filter(tot_iscr__gt=Decimal("0.00"), tot_payed__lt=models.F("tot_iscr"))

        # Verify unpaid query results
        unpaid_ids = list(unpaid.values_list("id", flat=True))
        assert unpaid_reg.id in unpaid_ids, "Completely unpaid registration should be in unpaid query"
        assert partial_paid_reg.id in unpaid_ids, "Partially paid registration should be in unpaid query"
        assert paid_reg.id not in unpaid_ids, "Fully paid registration should NOT be in unpaid query"
        assert unpaid.count() == 2, f"Expected 2 unpaid/partial registrations, got {unpaid.count()}"

        # Query fully paid registrations
        paid = Registration.objects.filter(tot_iscr=models.F("tot_payed"))

        # Verify paid query results
        paid_ids = list(paid.values_list("id", flat=True))
        assert paid_reg.id in paid_ids, "Fully paid registration should be in paid query"
        assert unpaid_reg.id not in paid_ids, "Unpaid registration should NOT be in paid query"
        assert partial_paid_reg.id not in paid_ids, "Partially paid registration should NOT be in paid query"
        assert paid.count() == 1, f"Expected 1 fully paid registration, got {paid.count()}"

        # Query completely unpaid (zero payment)
        zero_paid = Registration.objects.filter(tot_iscr__gt=Decimal("0.00"), tot_payed=Decimal("0.00"))

        zero_paid_ids = list(zero_paid.values_list("id", flat=True))
        assert unpaid_reg.id in zero_paid_ids, "Zero payment registration should be in zero paid query"
        assert paid_reg.id not in zero_paid_ids, "Paid registration should NOT be in zero paid query"
        assert partial_paid_reg.id not in zero_paid_ids, "Partially paid registration should NOT be in zero paid query"
        assert zero_paid.count() == 1, f"Expected 1 zero payment registration, got {zero_paid.count()}"

        # Verify payment status calculations
        for reg in [unpaid_reg, paid_reg, partial_paid_reg]:
            db_reg = Registration.objects.get(id=reg.id)
            balance = db_reg.tot_iscr - db_reg.tot_payed

            if reg == unpaid_reg:
                assert balance == Decimal("100.00"), f"Unpaid registration should have 100.00 balance, got {balance}"
            elif reg == paid_reg:
                assert balance == Decimal("0.00"), f"Paid registration should have 0.00 balance, got {balance}"
            elif reg == partial_paid_reg:
                assert balance == Decimal("50.00"), (
                    f"Partial paid registration should have 50.00 balance, got {balance}"
                )


# Fixtures
@pytest.fixture
def association():
    return Association.objects.create(name="Test Association", slug="test-assoc", email="test@example.com")


@pytest.fixture
def member():
    user = User.objects.create_user(username="testuser", email="test@example.com", first_name="Test", last_name="User")
    member = user.member
    member.name = "Test"
    member.surname = "User"
    member.save()
    return member


@pytest.fixture
def event(association):
    return Event.objects.create(name="Test Event", assoc=association)


@pytest.fixture
def run(event):
    return Run.objects.create(
        event=event,
        number=1,
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


@pytest.fixture
def question(event):
    return RegistrationQuestion.objects.create(
        event=event,
        name="dietary_requirements",
        text="Do you have any dietary requirements?",
        typ=BaseQuestionType.TEXT,
        required=True,
        order=1,
    )


@pytest.fixture
def question_with_options(event):
    """Question with multiple choice options"""
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

    return question, option1, option2


@pytest.fixture
def character(association):
    return Character.objects.create(name="Test Character", assoc=association)
