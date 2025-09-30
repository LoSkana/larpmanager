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
from django.test import TestCase

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
from larpmanager.tests.unit.base import BaseTestCase


class TestRegistrationModel(TestCase, BaseTestCase):
    """Test Registration model functionality"""

    def test_registration_creation(self):
        """Test basic registration creation"""
        member = self.get_member()
        run = self.get_run()
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

    def test_registration_str_representation(self):
        """Test string representation of registration"""
        member = self.get_member()
        run = self.get_run()
        registration = Registration(member=member, run=run, tot_iscr=Decimal("100.00"))

        expected = f"{run} - {member}"
        assert str(registration) == expected

    def test_registration_with_ticket(self):
        """Test registration with ticket"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket()
        registration = Registration.objects.create(
            member=member, run=run, ticket=ticket, tot_iscr=ticket.price, tot_payed=Decimal("0.00")
        )

        assert registration.ticket == ticket
        assert registration.tot_iscr == ticket.price

    def test_registration_cancellation(self):
        """Test registration cancellation"""
        registration = self.get_registration()
        cancellation_date = datetime.now()
        registration.cancellation_date = cancellation_date
        registration.save()

        assert registration.cancellation_date == cancellation_date

    def test_registration_payment_calculations(self):
        """Test payment status calculations"""
        registration = self.get_registration()
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

    def test_registration_with_additionals(self):
        """Test registration with additional tickets"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket()
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

    def test_registration_with_pay_what(self):
        """Test registration with pay-what-you-want amount"""
        member = self.get_member()
        run = self.get_run()
        pay_what_amount = Decimal("75.00")
        registration = Registration.objects.create(
            member=member, run=run, pay_what=pay_what_amount, tot_iscr=pay_what_amount, tot_payed=Decimal("0.00")
        )

        assert registration.pay_what == pay_what_amount

    def test_registration_surcharge(self):
        """Test registration surcharge handling"""
        registration = self.get_registration()
        surcharge = Decimal("15.00")
        registration.surcharge = surcharge
        registration.save()

        assert registration.surcharge == surcharge

    def test_registration_unique_constraint(self):
        """Test that member can only have one registration per run"""
        # Create a fresh user and get the auto-created member
        user = self.create_user(username="unique_test_user", email="unique@test.com")
        member = user.member  # Django auto-creates this via OneToOneField
        # Create a fresh event and run to avoid unique constraint conflicts
        event = self.create_event(name="Unique Test Event")
        run = self.create_run(event=event, number=99)  # Use unique number

        # Create first registration with explicit field values
        first_registration = Registration.objects.create(
            member=member,
            run=run,
            tot_iscr=Decimal("100.00"),
            tot_payed=Decimal("0.00"),
            cancellation_date=None,
            redeem_code=None,
        )

        # Verify first registration was created successfully
        assert first_registration.id is not None, "First registration should be created successfully"

        # Verify only one registration exists for this member/run combination
        existing_registrations = Registration.objects.filter(member=member, run=run, cancellation_date=None)
        assert existing_registrations.count() == 1, f"Expected 1 registration, found {existing_registrations.count()}"

        # Try to create second registration for same member and run with same constraint fields
        with pytest.raises(IntegrityError) as excinfo:
            Registration.objects.create(
                member=member,
                run=run,
                tot_iscr=Decimal("50.00"),
                tot_payed=Decimal("0.00"),
                cancellation_date=None,
                redeem_code=None,
            )

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


class TestRegistrationTicket(TestCase, BaseTestCase):
    """Test RegistrationTicket model"""

    def test_ticket_creation(self):
        """Test ticket creation"""
        event = self.get_event()
        ticket = RegistrationTicket.objects.create(
            event=event,
            tier=TicketTier.STANDARD,
            name="Standard Ticket",
            price=Decimal("100.00"),
            description="Standard event ticket",
            max_available=50,
            number=1,
        )

        assert ticket.event == event
        assert ticket.tier == TicketTier.STANDARD
        assert ticket.name == "Standard Ticket"
        assert ticket.price == Decimal("100.00")
        assert ticket.max_available == 50

    def test_ticket_str_representation(self):
        """Test ticket string representation"""
        event = self.get_event()
        ticket = RegistrationTicket(
            event=event, tier=TicketTier.STANDARD, name="Standard Ticket", price=Decimal("100.00")
        )

        # Test that the string representation contains expected components
        ticket_str = str(ticket)
        assert "Standard Ticket" in ticket_str
        assert str(event) in ticket_str
        assert "100.00" in ticket_str

    def test_ticket_tiers(self):
        """Test different ticket tiers"""
        event = self.get_event()
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
                event=event, tier=tier, name=f"{name} Ticket", price=Decimal("100.00"), max_available=10, number=tier
            )
            assert ticket.tier == tier

    def test_ticket_validation(self):
        """Test ticket validation"""
        event = self.get_event()
        # Test negative price validation
        with pytest.raises(ValidationError):
            ticket = RegistrationTicket(
                event=event,
                tier=TicketTier.STANDARD,
                name="Invalid Ticket",
                price=Decimal("-50.00"),
                max_available=10,
                number=1,
            )
            ticket.full_clean()

    def test_ticket_max_available(self):
        """Test ticket max_available field"""
        ticket = self.ticket()
        initial_max = 50  # From BaseTestCase default

        # Verify initial state
        assert ticket.max_available == initial_max, (
            f"Ticket should have max_available {initial_max}, got {ticket.max_available}"
        )

        # Test updating max_available
        new_max = 75
        ticket.max_available = new_max
        ticket.save()

        # Verify change
        assert ticket.max_available == new_max, f"Expected max_available {new_max}, got {ticket.max_available}"

        # Verify the change persists in database
        db_ticket = RegistrationTicket.objects.get(id=ticket.id)
        assert db_ticket.max_available == new_max, (
            f"Database should reflect new max_available {new_max}, got {db_ticket.max_available}"
        )

        # Test unlimited availability (0 means unlimited)
        ticket.max_available = 0
        ticket.save()
        assert ticket.max_available == 0, "max_available should be able to be set to 0 (unlimited)"


class TestRegistrationQuestions(TestCase, BaseTestCase):
    """Test registration questions and answers"""

    def test_question_creation(self):
        """Test registration question creation"""
        from larpmanager.models.form import QuestionStatus

        event = self.get_event()
        question = RegistrationQuestion.objects.create(
            event=event,
            name="dietary_requirements",
            description="Do you have any dietary requirements?",
            typ=BaseQuestionType.TEXT,
            status=QuestionStatus.MANDATORY,
            order=1,
        )

        assert question.event == event
        assert question.name == "dietary_requirements"
        assert question.typ == BaseQuestionType.TEXT
        assert question.status == QuestionStatus.MANDATORY

    def test_question_types(self):
        """Test different question types"""
        event = self.get_event()
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
                event=event, name=f"question_{i}", description=f"Question {i}", typ=question_type, order=i
            )
            assert question.typ == question_type

    def test_question_with_options(self):
        """Test question with multiple choice options"""
        from larpmanager.models.form import QuestionStatus

        event = self.get_event()
        question = RegistrationQuestion.objects.create(
            event=event,
            name="accommodation",
            description="What accommodation do you prefer?",
            typ=BaseQuestionType.SINGLE,
            status=QuestionStatus.MANDATORY,
            order=1,
        )

        option1 = RegistrationOption.objects.create(
            event=event, question=question, name="Hotel", price=Decimal("50.00"), order=1
        )

        option2 = RegistrationOption.objects.create(
            event=event, question=question, name="Camping", price=Decimal("20.00"), order=2
        )

        assert option1.question == question
        assert option2.question == question
        assert option1.price == Decimal("50.00")
        assert option2.price == Decimal("20.00")

    def test_registration_answer_text(self):
        """Test text answer to registration question"""
        registration = self.get_registration()
        question = self.question()
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

    def test_registration_choice_single(self):
        """Test single choice answer"""
        registration = self.get_registration()
        question, option1, option2 = self.question_with_options()

        choice = RegistrationChoice.objects.create(reg=registration, question=question, option=option1)

        assert choice.reg == registration
        assert choice.question == question
        assert choice.option == option1

    def test_registration_choice_multiple(self):
        """Test multiple choice answers"""
        registration = self.get_registration()
        question, option1, option2 = self.question_with_options()

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


class TestRegistrationInstallments(TestCase, BaseTestCase):
    """Test registration installment payments"""

    def test_installment_creation(self):
        """Test installment creation"""
        event = self.get_event()
        installment = RegistrationInstallment.objects.create(
            event=event, order=1, number=1, amount=50, days_deadline=30
        )

        assert installment.event == event
        assert installment.order == 1
        assert installment.amount == Decimal("50.00")
        assert installment.days_deadline == 30

    def test_installment_with_date_deadline(self):
        """Test installment with specific date deadline"""
        event = self.get_event()
        deadline_date = date.today() + timedelta(days=30)
        installment = RegistrationInstallment.objects.create(
            event=event, order=1, number=2, amount=50, date_deadline=deadline_date
        )

        assert installment.date_deadline == deadline_date

    def test_installment_ticket_specific(self):
        """Test installment specific to certain tickets"""
        event = self.get_event()
        ticket = self.ticket()
        installment = RegistrationInstallment.objects.create(
            event=event, order=1, number=3, amount=50, days_deadline=30
        )

        installment.tickets.add(ticket)

        assert ticket in installment.tickets.all()

    def test_installment_ordering(self):
        """Test installment ordering"""
        event = self.get_event()
        installment2 = RegistrationInstallment.objects.create(
            event=event, order=2, number=4, amount=50, days_deadline=15
        )

        installment1 = RegistrationInstallment.objects.create(
            event=event, order=1, number=5, amount=30, days_deadline=30
        )

        installments = RegistrationInstallment.objects.filter(event=event).order_by("order")

        assert list(installments) == [installment1, installment2]


class TestRegistrationSurcharges(TestCase, BaseTestCase):
    """Test registration surcharges"""

    def test_surcharge_creation(self):
        """Test surcharge creation"""
        event = self.get_event()
        surcharge_date = date.today() + timedelta(days=30)
        surcharge = RegistrationSurcharge.objects.create(event=event, number=1, date=surcharge_date, amount=25)

        assert surcharge.event == event
        assert surcharge.date == surcharge_date
        assert surcharge.amount == Decimal("25.00")

    def test_multiple_surcharges(self):
        """Test multiple surcharges for an event"""
        event = self.get_event()
        surcharge1 = RegistrationSurcharge.objects.create(
            event=event, number=2, date=date.today() + timedelta(days=30), amount=15
        )

        surcharge2 = RegistrationSurcharge.objects.create(
            event=event, number=3, date=date.today() + timedelta(days=60), amount=25
        )

        surcharges = RegistrationSurcharge.objects.filter(event=event)
        assert surcharges.count() == 2
        assert surcharge1 in surcharges
        assert surcharge2 in surcharges

    def test_surcharge_date_ordering(self):
        """Test surcharges are properly ordered by date"""
        event = self.get_event()
        later_surcharge = RegistrationSurcharge.objects.create(
            event=event, number=4, date=date.today() + timedelta(days=60), amount=25
        )

        earlier_surcharge = RegistrationSurcharge.objects.create(
            event=event, number=5, date=date.today() + timedelta(days=30), amount=15
        )

        surcharges = RegistrationSurcharge.objects.filter(event=event).order_by("date")

        assert list(surcharges) == [earlier_surcharge, later_surcharge]


class TestRegistrationWithCharacters(TestCase, BaseTestCase):
    """Test registration with character assignment"""

    def test_registration_with_character(self):
        """Test linking character to registration"""
        from larpmanager.models.registration import RegistrationCharacterRel

        registration = self.get_registration()
        character = Character.objects.create(name="Test Character", event=registration.run.event, number=10)
        char_rel = RegistrationCharacterRel.objects.create(reg=registration, character=character, principal=True)

        assert char_rel.reg == registration
        assert char_rel.character == character
        assert char_rel.principal is True

    def test_multiple_characters_per_registration(self):
        """Test registration with multiple characters"""
        from larpmanager.models.registration import RegistrationCharacterRel

        registration = self.get_registration()
        character1 = Character.objects.create(name="Character 1", event=registration.run.event, number=1)

        character2 = Character.objects.create(name="Character 2", event=registration.run.event, number=2)

        char_rel1 = RegistrationCharacterRel.objects.create(reg=registration, character=character1, principal=True)

        char_rel2 = RegistrationCharacterRel.objects.create(reg=registration, character=character2, principal=False)

        char_rels = RegistrationCharacterRel.objects.filter(reg=registration)
        assert char_rels.count() == 2

        principal_chars = char_rels.filter(principal=True)
        assert principal_chars.count() == 1
        assert principal_chars.first().character == character1


class TestRegistrationValidation(TestCase, BaseTestCase):
    """Test registration validation and business rules"""

    def test_registration_for_cancelled_event(self):
        """Test registration attempt for cancelled event"""
        member = self.get_member()
        association = self.get_association()
        event = Event.objects.create(name="Cancelled Event", assoc=association)

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

    def test_registration_payment_status_calculation(self):
        """Test payment status calculation"""
        registration = self.get_registration()
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

    def test_registration_with_membership_requirement(self):
        """Test registration requiring membership"""
        member = self.get_member()
        run = self.get_run()
        # Mock membership check
        membership = Membership.objects.create(
            member=member, assoc=run.event.assoc, status=MembershipStatus.ACCEPTED, date=date.today()
        )

        registration = Registration.objects.create(
            member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00")
        )

        assert registration.member == member
        assert membership.status == MembershipStatus.ACCEPTED


class TestRegistrationQueries(TestCase, BaseTestCase):
    """Test registration query methods and managers"""

    def test_active_registrations(self):
        """Test querying active registrations"""
        member = self.get_member()
        association = self.get_association()
        # Create active event
        active_event = Event.objects.create(name="Active Event", assoc=association)

        active_run = Run.objects.create(
            event=active_event,
            number=1,
            name="Active Run",
            start=date.today() + timedelta(days=30),
            end=date.today() + timedelta(days=32),
            development=DevelopStatus.OPEN,
        )

        # Create cancelled event
        cancelled_event = Event.objects.create(name="Cancelled Event", assoc=association)

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

    def test_registrations_by_payment_status(self):
        """Test querying registrations by payment status"""
        association = self.get_association()
        event = Event.objects.create(name="Test Event", assoc=association)

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
