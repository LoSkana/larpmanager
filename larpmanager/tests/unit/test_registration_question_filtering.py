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
#    a network, you must also make the complete source code available under the same license.
#
# For more information or to purchase a commercial license, contact:
# commercial@larpmanager.com
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary

"""Tests for registration question filtering features (reg_que_*)"""

import uuid
from decimal import Decimal

import pytest

from larpmanager.cache.question import get_cached_registration_questions
from larpmanager.forms.registration import RegistrationForm
from larpmanager.models.form import QuestionStatus, RegistrationQuestion
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration
from larpmanager.models.writing import Faction
from larpmanager.tests.unit.base import BaseTestCase


class TestRegistrationQuestionTicketFiltering(BaseTestCase):
    """Test cases for reg_que_tickets feature - filtering questions by ticket type"""

    def test_question_skip_when_ticket_required_but_no_ticket_selected(self) -> None:
        """Test question is skipped when ticket is required but registration has no ticket"""
        event = self.get_event()
        run = self.get_run()
        member = self.get_member()
        ticket1 = self.ticket(event=event, name="VIP", number=1)
        ticket2 = self.ticket(event=event, name="Standard", number=2)

        # Create question that requires ticket1
        question = self.question(event=event)
        question.tickets.add(ticket1)

        # Create registration without ticket
        registration = self.create_registration(member=member, run=run, ticket=None)

        # Annotate tickets_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Question should be skipped (no ticket selected)
        result = question.skip(registration, features=["reg_que_tickets"])
        self.assertTrue(result)

    def test_question_skip_when_wrong_ticket_selected(self) -> None:
        """Test question is skipped when wrong ticket is selected"""
        event = self.get_event()
        run = self.get_run()
        member = self.get_member()
        ticket1 = self.ticket(event=event, name="VIP", number=1)
        ticket2 = self.ticket(event=event, name="Standard", number=2)

        # Create question that requires ticket1
        question = self.question(event=event)
        question.tickets.add(ticket1)

        # Create registration with ticket2
        registration = self.create_registration(member=member, run=run, ticket=ticket2)

        # Annotate tickets_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Question should be skipped (wrong ticket)
        result = question.skip(registration, features=["reg_que_tickets"])
        self.assertTrue(result)

    def test_question_shown_when_correct_ticket_selected(self) -> None:
        """Test question is shown when correct ticket is selected"""
        event = self.get_event()
        run = self.get_run()
        member = self.get_member()
        ticket1 = self.ticket(event=event, name="VIP", number=1)

        # Create question that requires ticket1
        question = self.question(event=event)
        question.tickets.add(ticket1)

        # Create registration with ticket1
        registration = self.create_registration(member=member, run=run, ticket=ticket1)

        # Annotate tickets_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Question should NOT be skipped (correct ticket)
        result = question.skip(registration, features=["reg_que_tickets"])
        self.assertFalse(result)

    def test_question_shown_when_one_of_multiple_tickets_selected(self) -> None:
        """Test question is shown when registration has one of multiple allowed tickets"""
        event = self.get_event()
        run = self.get_run()
        member = self.get_member()
        ticket1 = self.ticket(event=event, name="VIP", number=1)
        ticket2 = self.ticket(event=event, name="Premium", number=2)
        ticket3 = self.ticket(event=event, name="Standard", number=3)

        # Create question that accepts ticket1 or ticket2
        question = self.question(event=event)
        question.tickets.add(ticket1, ticket2)

        # Create registration with ticket2
        registration = self.create_registration(member=member, run=run, ticket=ticket2)

        # Annotate tickets_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Question should NOT be skipped (ticket2 is allowed)
        result = question.skip(registration, features=["reg_que_tickets"])
        self.assertFalse(result)

    def test_question_shown_when_no_tickets_required(self) -> None:
        """Test question is shown for all tickets when no ticket requirement is set"""
        event = self.get_event()
        run = self.get_run()
        member = self.get_member()
        ticket = self.ticket(event=event)

        # Create question without ticket requirement
        question = self.question(event=event)

        # Create registration with any ticket
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Annotate tickets_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Question should NOT be skipped (no ticket restriction)
        result = question.skip(registration, features=["reg_que_tickets"])
        self.assertFalse(result)

    def test_form_field_not_required_for_wrong_ticket(self) -> None:
        """Test form field becomes not required when wrong ticket is selected"""
        event = self.get_event()
        run = self.get_run()
        member = self.get_member()
        ticket1 = self.ticket(event=event, name="VIP", number=1)
        ticket2 = self.ticket(event=event, name="Standard", number=2)

        # Create mandatory question for ticket1
        question = self.question(event=event, status=QuestionStatus.MANDATORY)
        question.tickets.add(ticket1)

        # Create registration with ticket2
        registration = self.create_registration(member=member, run=run, ticket=ticket2)

        # Create form context
        context = {
            "event": event,
            "run": run,
            "member": member,
            "currency_symbol": "€",
            "features": ["reg_que_tickets"],
        }

        # Initialize form
        form = RegistrationForm(context=context, instance=registration)

        # Call sel_ticket_map with ticket2's uuid
        form.sel_ticket_map(str(ticket2.uuid))

        # Field should not be required for ticket2
        field_name = f"que_{question.uuid}_tr"
        if field_name in form.fields:
            self.assertFalse(form.fields[field_name].required)

    def get_question(self, questions: list, id: int):
        for question in questions:
            if question.id == id:
                return question
        return None


class TestRegistrationQuestionFactionFiltering(BaseTestCase):
    """Test cases for reg_que_faction feature - filtering questions by character faction"""

    def test_question_skip_when_no_character_assigned(self) -> None:
        """Test question is skipped when faction is required but no character assigned"""
        event = self.get_event()
        run = self.get_run()
        member = self.get_member()

        # Create faction and question
        faction = Faction.objects.create(name="Rebels", event=event)
        question = self.question(event=event)
        question.factions.add(faction)

        # Create registration without character
        registration = self.create_registration(member=member, run=run)

        # Annotate factions_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Question should be skipped (no character)
        result = question.skip(registration, features=["reg_que_faction"])
        self.assertTrue(result)

    def test_question_skip_when_character_has_wrong_faction(self) -> None:
        """Test question is skipped when character has different faction"""
        from larpmanager.models.registration import RegistrationCharacterRel

        event = self.get_event()
        run = self.get_run()
        member = self.get_member()

        # Create factions
        faction1 = Faction.objects.create(name="Rebels", event=event)
        faction2 = Faction.objects.create(name="Empire", event=event)

        # Create character with faction2
        character = self.character(event=event)
        character.factions_list.add(faction2)

        # Create question that requires faction1
        question = self.question(event=event)
        question.factions.add(faction1)

        # Create registration and assign character
        registration = self.create_registration(member=member, run=run)
        RegistrationCharacterRel.objects.create(registration=registration, character=character)

        # Annotate factions_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Question should be skipped (wrong faction)
        result = question.skip(registration, features=["reg_que_faction"])
        self.assertTrue(result)

    def test_question_shown_when_character_has_correct_faction(self) -> None:
        """Test question is shown when character has the required faction"""
        from larpmanager.models.registration import RegistrationCharacterRel

        event = self.get_event()
        run = self.get_run()
        member = self.get_member()

        # Create faction
        faction = Faction.objects.create(name="Rebels", event=event)

        # Create character with faction
        character = self.character(event=event)
        character.factions_list.add(faction)

        # Create question that requires faction
        question = self.question(event=event)
        question.factions.add(faction)

        # Create registration and assign character
        registration = self.create_registration(member=member, run=run)
        RegistrationCharacterRel.objects.create(registration=registration, character=character)

        # Annotate factions_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Question should NOT be skipped (correct faction)
        result = question.skip(registration, features=["reg_que_faction"])
        self.assertFalse(result)

    def test_question_shown_when_character_has_one_of_multiple_factions(self) -> None:
        """Test question is shown when character has one of multiple allowed factions"""
        from larpmanager.models.registration import RegistrationCharacterRel

        event = self.get_event()
        run = self.get_run()
        member = self.get_member()

        # Create factions
        faction1 = Faction.objects.create(name="Rebels", event=event)
        faction2 = Faction.objects.create(name="Neutrals", event=event)
        faction3 = Faction.objects.create(name="Empire", event=event)

        # Create character with faction2
        character = self.character(event=event)
        character.factions_list.add(faction2)

        # Create question that accepts faction1 or faction2
        question = self.question(event=event)
        question.factions.add(faction1, faction2)

        # Create registration and assign character
        registration = self.create_registration(member=member, run=run)
        RegistrationCharacterRel.objects.create(registration=registration, character=character)

        # Annotate factions_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Question should NOT be skipped (faction2 is allowed)
        result = question.skip(registration, features=["reg_que_faction"])
        self.assertFalse(result)

    def test_question_shown_when_no_faction_required(self) -> None:
        """Test question is shown for all factions when no faction requirement is set"""
        from larpmanager.models.registration import RegistrationCharacterRel

        event = self.get_event()
        run = self.get_run()
        member = self.get_member()

        # Create faction and character
        faction = Faction.objects.create(name="Rebels", event=event)
        character = self.character(event=event)
        character.factions_list.add(faction)

        # Create question without faction requirement
        question = self.question(event=event)

        # Create registration and assign character
        registration = self.create_registration(member=member, run=run)
        RegistrationCharacterRel.objects.create(registration=registration, character=character)

        # Annotate factions_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Question should NOT be skipped (no faction restriction)
        result = question.skip(registration, features=["reg_que_faction"])
        self.assertFalse(result)

    def test_question_skip_for_new_registration_with_faction_requirement(self) -> None:
        """Test question is skipped for new registrations (without pk) when faction is required"""
        from larpmanager.models.registration import Registration

        event = self.get_event()
        run = self.get_run()
        member = self.get_member()

        # Create faction and question with faction requirement
        faction = Faction.objects.create(name="Rebels", event=event)
        question = self.question(event=event)
        question.factions.add(faction)

        # Create new registration WITHOUT saving (no pk)
        registration = Registration(member=member, run=run)
        # Note: registration.pk is None since we didn't save it

        # Annotate factions_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Question should be skipped (new registration with faction requirement)
        result = question.skip(registration, features=["reg_que_faction"])
        self.assertTrue(result)


@pytest.mark.django_db_reset_sequences
class TestRegistrationQuestionAllowedMembersFiltering(BaseTestCase):
    """Test cases for reg_que_allowed feature - filtering questions by allowed members (organizers only)

    Note: Some tests that require creating additional members are disabled due to database
    constraint issues in the test environment (duplicate user_id). The core functionality
    is still tested with existing members.
    """

    def test_question_skip_when_not_organizer_and_members_restricted(self) -> None:
        """Test question is skipped for non-organizers when specific members are allowed"""
        event = self.get_event()
        run = self.get_run()
        member = self.get_member()
        unique_id = uuid.uuid4().hex[:8]
        user = self.create_user(username=f"other_{unique_id}", email=f"other_{unique_id}@example.com")
        other_member = self.create_member(user=user)

        # Create question that only allows other_member
        question = self.question(event=event)
        question.allowed.add(other_member)

        # Create registration
        registration = self.create_registration(member=member, run=run)

        # Annotate allowed_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Prepare params for organizer context
        params = {"run": run, "all_runs": {}, "member": member}

        # Question should be skipped for non-organizer (not in allowed list)
        result = question.skip(registration, features=["reg_que_allowed"], params=params, is_organizer=True)
        self.assertTrue(result)

    def test_question_shown_when_member_in_allowed_list(self) -> None:
        """Test question is shown when member is in the allowed list"""
        event = self.get_event()
        run = self.get_run()
        member = self.get_member()

        # Create question that allows this member
        question = self.question(event=event)
        question.allowed.add(member)

        # Create registration
        registration = self.create_registration(member=member, run=run)

        # Annotate allowed_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Prepare params for organizer context
        params = {"run": run, "all_runs": {}, "member": member}

        # Question should NOT be skipped (member in allowed list)
        result = question.skip(registration, features=["reg_que_allowed"], params=params, is_organizer=True)
        self.assertFalse(result)

    def test_question_shown_when_run_organizer(self) -> None:
        """Test question is always shown to run organizers regardless of allowed list"""
        event = self.get_event()
        run = self.get_run()
        member = self.get_member()
        unique_id = uuid.uuid4().hex[:8]
        other_member = self.create_member(
            user=self.create_user(username=f"other_{unique_id}", email=f"other_{unique_id}@example.com")
        )

        # Create question that only allows other_member
        question = self.question(event=event)
        question.allowed.add(other_member)

        # Create registration
        registration = self.create_registration(member=member, run=run)

        # Annotate allowed_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Prepare params indicating member is run organizer (permission level 1)
        params = {"run": run, "all_runs": {run.id: {1: True}}, "member": member}

        # Question should NOT be skipped (run organizer sees all)
        result = question.skip(registration, features=["reg_que_allowed"], params=params, is_organizer=True)
        self.assertFalse(result)

    def test_question_shown_when_no_allowed_members_set(self) -> None:
        """Test question is shown to all organizers when no specific members are allowed"""
        event = self.get_event()
        run = self.get_run()
        member = self.get_member()

        # Create question without allowed member restriction
        question = self.question(event=event)

        # Create registration
        registration = self.create_registration(member=member, run=run)

        # Annotate allowed_map for the question
        questions = get_cached_registration_questions(event=event)
        question = self.get_question(questions, question.id)

        # Prepare params for organizer context
        params = {"run": run, "all_runs": {}, "member": member}

        # Question should NOT be skipped (no restriction)
        result = question.skip(registration, features=["reg_que_allowed"], params=params, is_organizer=True)
        self.assertFalse(result)

    def test_question_shown_to_non_organizer_when_no_restriction(self) -> None:
        """Test question is shown to non-organizers when feature is disabled"""
        event = self.get_event()
        run = self.get_run()
        member = self.get_member()

        # Create question with allowed members
        question = self.question(event=event)
        unique_id = uuid.uuid4().hex[:8]
        other_member = self.create_member(
            user=self.create_user(username=f"other_{unique_id}", email=f"other_{unique_id}@example.com")
        )
        question.allowed.add(other_member)

        # Create registration
        registration = self.create_registration(member=member, run=run)

        # Question should NOT be skipped when feature is not enabled
        result = question.skip(registration, features=[], params=None, is_organizer=False)
        self.assertFalse(result)
