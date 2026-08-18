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

"""Unit tests for the default options assigned by the character form."""

import pytest
from django.core.cache import cache

from larpmanager.forms.base import get_question_key
from larpmanager.forms.character import CharacterForm, OrgaCharacterForm
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    WritingChoice,
    WritingOption,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.tests.unit.base import BaseTestCase


@pytest.mark.django_db
class TestCharacterOptionDefaults(BaseTestCase):
    """Check the options assigned automatically on the questions the player cannot answer."""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.run = self.get_run()
        self.event = self.run.event

        WritingQuestion.objects.get_or_create(
            event=self.event,
            applicable=QuestionApplicable.CHARACTER,
            typ=WritingQuestionType.NAME,
            defaults={"name": "Name", "order": 1},
        )

        self.origin = self._question("Origin", order=2)
        self.role = self._question("Role", order=3, status=QuestionStatus.HIDDEN)

        self.bunker = WritingOption.objects.create(event=self.event, question=self.origin, name="Bunker", order=1)
        self.wasteland = WritingOption.objects.create(event=self.event, question=self.origin, name="Wasteland", order=2)

        self.scout = WritingOption.objects.create(
            event=self.event, question=self.role, name="Scout", order=1, default=True
        )
        self.guard = WritingOption.objects.create(
            event=self.event, question=self.role, name="Guard", order=2, default=True
        )

    def _question(self, name: str, order: int, status: str = QuestionStatus.OPTIONAL) -> WritingQuestion:
        return WritingQuestion.objects.create(
            event=self.event,
            applicable=QuestionApplicable.CHARACTER,
            typ=BaseQuestionType.SINGLE,
            status=status,
            name=name,
            order=order,
        )

    def _context(self, registration: object | None = None) -> dict:
        context = {
            "event": self.event,
            "run": self.run,
            "member": self.get_member(),
            "features": {"character", "user_character", "wri_que_requirements"},
            "association_id": self.event.association_id,
        }
        if registration:
            context["registration"] = registration
        return context

    def _character(self) -> Character:
        return Character.objects.create(
            event=self.event,
            player=self.get_member(),
            name="Original",
            status=CharacterStatus.CREATION,
        )

    def _data(self, origin: WritingOption | None = None, **extra: str) -> dict:
        data = {"name": "Original"}
        if origin:
            data[get_question_key(self.origin)] = str(origin.uuid)
        data.update(extra)
        return data

    def _save(self, data: dict, character: Character | None = None) -> Character:
        form = CharacterForm(data, instance=character or self._character(), context=self._context())
        assert form.is_valid(), form.errors
        return form.save()

    def test_hidden_question_filled_with_first_default(self) -> None:
        character = self._save(self._data(self.bunker))

        assert WritingChoice.objects.filter(element_id=character.id, option=self.scout).exists()

    def test_first_eligible_default_wins(self) -> None:
        # the first default cannot be assigned, so the next one is evaluated
        self.scout.requirements.set([self.wasteland])

        character = self._save(self._data(self.bunker))

        assert not WritingChoice.objects.filter(element_id=character.id, option=self.scout).exists()
        assert WritingChoice.objects.filter(element_id=character.id, option=self.guard).exists()

    def test_default_assigned_when_requirements_satisfied(self) -> None:
        self.scout.requirements.set([self.bunker])

        character = self._save(self._data(self.bunker))

        assert WritingChoice.objects.filter(element_id=character.id, option=self.scout).exists()

    def test_no_default_assigned_when_none_eligible(self) -> None:
        self.scout.requirements.set([self.wasteland])
        self.guard.requirements.set([self.wasteland])

        character = self._save(self._data(self.bunker))

        assert not WritingChoice.objects.filter(element_id=character.id, question=self.role).exists()

    def test_default_of_hidden_question_satisfies_another_default(self) -> None:
        # the default assigned on a question unlocks the default of the next one, in a later pass
        squad = self._question("Squad", order=4, status=QuestionStatus.HIDDEN)
        alpha = WritingOption.objects.create(event=self.event, question=squad, name="Alpha", order=1, default=True)
        alpha.requirements.set([self.scout])

        character = self._save(self._data(self.bunker))

        assert WritingChoice.objects.filter(element_id=character.id, option=self.scout).exists()
        assert WritingChoice.objects.filter(element_id=character.id, option=alpha).exists()

    def test_existing_choice_not_replaced(self) -> None:
        character = self._character()
        WritingChoice.objects.create(question=self.role, option=self.guard, element_id=character.id)

        self._save(self._data(self.bunker), character=character)

        assert WritingChoice.objects.filter(element_id=character.id, question=self.role).count() == 1
        assert WritingChoice.objects.filter(element_id=character.id, option=self.guard).exists()

    def test_no_default_on_question_the_player_can_answer(self) -> None:
        # the question is shown: leaving it empty is a choice of the player
        role_key = get_question_key(self.role)
        self.role.status = QuestionStatus.OPTIONAL
        self.role.save()

        character = self._save(self._data(self.bunker, **{role_key: ""}))

        assert not WritingChoice.objects.filter(element_id=character.id, question=self.role).exists()

    def test_default_assigned_on_disabled_question(self) -> None:
        self.role.status = QuestionStatus.DISABLED
        self.role.save()

        character = self._save(self._data(self.bunker))

        assert WritingChoice.objects.filter(element_id=character.id, option=self.scout).exists()

    def test_sold_out_default_skipped(self) -> None:
        self.scout.max_available = 1
        self.scout.save()

        form = CharacterForm(self._data(self.bunker), instance=self._character(), context=self._context())
        form.registration_counts = {form.get_option_key_count({"id": self.scout.id}): 1}

        assert form.is_valid(), form.errors
        character = form.save()

        assert not WritingChoice.objects.filter(element_id=character.id, option=self.scout).exists()
        assert WritingChoice.objects.filter(element_id=character.id, option=self.guard).exists()

    def test_default_restricted_to_another_ticket_skipped(self) -> None:
        # the option is reserved to a ticket the player does not hold, so the next default is used
        reserved = self.ticket(event=self.event, name="Reserved", number=2)
        self.scout.tickets.set([reserved])
        registration = self.create_registration(run=self.run, ticket=self.ticket(event=self.event, name="Standard"))

        form = CharacterForm(self._data(self.bunker), instance=self._character(), context=self._context(registration))

        assert form.is_valid(), form.errors
        character = form.save()

        assert not WritingChoice.objects.filter(element_id=character.id, option=self.scout).exists()
        assert WritingChoice.objects.filter(element_id=character.id, option=self.guard).exists()

    def test_default_restricted_to_the_ticket_of_the_player_assigned(self) -> None:
        allowed = self.ticket(event=self.event, name="Allowed", number=2)
        self.scout.tickets.set([allowed])
        registration = self.create_registration(run=self.run, ticket=allowed)

        form = CharacterForm(self._data(self.bunker), instance=self._character(), context=self._context(registration))

        assert form.is_valid(), form.errors
        character = form.save()

        assert WritingChoice.objects.filter(element_id=character.id, option=self.scout).exists()

    def test_gated_question_gets_no_default(self) -> None:
        # the question is dropped by its unmet prerequisites: it must keep no answer at all
        self.role.status = QuestionStatus.OPTIONAL
        self.role.save()
        self.role.requirements.set([self.wasteland])

        form = CharacterForm(self._data(self.bunker), instance=self._character(), context=self._context())

        assert form.is_valid(), form.errors
        character = form.save()

        assert form.gated_questions
        assert not WritingChoice.objects.filter(element_id=character.id, question=self.role).exists()

    def test_organizer_form_assigns_no_default(self) -> None:
        # organizers can answer every question, so nothing is assigned for them
        form = OrgaCharacterForm(self._data(self.bunker), instance=self._character(), context=self._context())

        assert form.is_valid(), form.errors
        character = form.save()

        assert not WritingChoice.objects.filter(element_id=character.id, question=self.role).exists()
