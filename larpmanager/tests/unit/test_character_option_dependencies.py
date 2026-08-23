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

"""Unit tests for the option requirements enforced by the character forms."""

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from larpmanager.cache.question import get_character_option_dependencies, get_character_question_dependencies
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
class TestCharacterOptionDependencies(BaseTestCase):
    """Check that options with unmet requirements are refused on the player form."""

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
        self.mutation = self._question("Mutation", order=3)

        self.bunker = WritingOption.objects.create(event=self.event, question=self.origin, name="Bunker", order=1)
        self.wasteland = WritingOption.objects.create(event=self.event, question=self.origin, name="Wasteland", order=2)
        self.psionic = WritingOption.objects.create(event=self.event, question=self.mutation, name="Psionic", order=1)
        self.psionic.requirements.set([self.bunker])

    def _question(self, name: str, order: int) -> WritingQuestion:
        return WritingQuestion.objects.create(
            event=self.event,
            applicable=QuestionApplicable.CHARACTER,
            typ=BaseQuestionType.SINGLE,
            status=QuestionStatus.OPTIONAL,
            name=name,
            order=order,
        )

    def _context(self) -> dict:
        return {
            "event": self.event,
            "run": self.run,
            "member": self.get_member(),
            "features": {"character", "user_character", "wri_que_requirements"},
            "association_id": self.event.association_id,
        }

    def _character(self) -> Character:
        return Character.objects.create(
            event=self.event,
            player=self.get_member(),
            name="Original",
            status=CharacterStatus.CREATION,
        )

    def _data(self, origin: WritingOption | None, mutation: WritingOption | None) -> dict:
        data = {"name": "Original"}
        if origin:
            data[get_question_key(self.origin)] = str(origin.uuid)
        if mutation:
            data[get_question_key(self.mutation)] = str(mutation.uuid)
        return data

    def test_option_refused_when_requirement_not_selected(self) -> None:
        form = CharacterForm(
            self._data(self.wasteland, self.psionic),
            instance=self._character(),
            context=self._context(),
        )

        assert not form.is_valid()
        assert get_question_key(self.mutation) in form.errors
        # the error names the option that is missing, so the player knows what to select
        assert "Bunker" in str(form.errors[get_question_key(self.mutation)])

    def test_dependencies_reused_from_context(self) -> None:
        context = self._context()
        context["dependencies"] = {}

        form = CharacterForm(
            self._data(self.wasteland, self.psionic),
            instance=self._character(),
            context=context,
        )

        assert form.dependencies == {}
        assert form.is_valid(), form.errors

    def test_option_accepted_when_requirement_selected(self) -> None:
        form = CharacterForm(
            self._data(self.bunker, self.psionic),
            instance=self._character(),
            context=self._context(),
        )

        assert form.is_valid(), form.errors

    def test_option_without_requirements_accepted(self) -> None:
        form = CharacterForm(
            self._data(self.wasteland, None),
            instance=self._character(),
            context=self._context(),
        )

        assert form.is_valid(), form.errors

    def test_auto_save_bound_by_requirements(self) -> None:
        # the auto-save stores the choices, so it must not be able to write an invalid combination
        context = self._context()
        context["request"] = RequestFactory().post("/", {"ajax": "1"})

        form = CharacterForm(
            self._data(self.wasteland, self.psionic),
            instance=self._character(),
            context=context,
        )

        assert form.is_auto_save()
        assert not form.is_valid()
        assert get_question_key(self.mutation) in form.errors

    def test_requirement_ignored_when_not_available(self) -> None:
        # a sold out requirement is removed from the page, so it can not be enforced
        form = CharacterForm(
            self._data(self.wasteland, self.psionic),
            instance=self._character(),
            context=self._context(),
        )
        form.unavail[self.origin.uuid] = [str(self.bunker.uuid)]

        assert form.is_valid(), form.errors

    def test_requirements_on_same_question_are_alternatives(self) -> None:
        # only one option of a single choice question can be picked, so requirements on it are alternatives
        self.psionic.requirements.set([self.bunker, self.wasteland])

        form = CharacterForm(
            self._data(self.wasteland, self.psionic),
            instance=self._character(),
            context=self._context(),
        )

        assert form.is_valid(), form.errors

    def test_requirements_on_other_questions_are_all_needed(self) -> None:
        training = self._question("Training", order=4)
        medic = WritingOption.objects.create(event=self.event, question=training, name="Medic", order=1)
        self.psionic.requirements.set([self.bunker, self.wasteland, medic])

        data = self._data(self.wasteland, self.psionic)
        form = CharacterForm(data, instance=self._character(), context=self._context())

        assert not form.is_valid()
        errors = str(form.errors[get_question_key(self.mutation)])
        # the origin group is satisfied by the wasteland choice, only the missing training is reported
        assert "Medic" in errors
        assert "Bunker" not in errors

        data[get_question_key(training)] = str(medic.uuid)
        form = CharacterForm(data, instance=self._character(), context=self._context())

        assert form.is_valid(), form.errors

    def test_dependencies_cached_and_cleared_on_requirement_change(self) -> None:
        features = {"character", "wri_que_requirements"}
        assert get_character_option_dependencies(self.event.id, features) == {
            str(self.psionic.uuid): [str(self.bunker.uuid)]
        }

        # the requirements are written after the option is saved, so the m2m change must clear the cache
        self.psionic.requirements.set([self.wasteland])

        assert get_character_option_dependencies(self.event.id, features) == {
            str(self.psionic.uuid): [str(self.wasteland.uuid)]
        }

        self.psionic.requirements.clear()

        assert get_character_option_dependencies(self.event.id, features) == {}

    def test_dependencies_empty_without_character_feature(self) -> None:
        assert get_character_option_dependencies(self.event.id, {"user_character"}) == {}

    def test_dependencies_empty_without_requirements_feature(self) -> None:
        assert get_character_option_dependencies(self.event.id, {"character"}) == {}

    def test_organizer_form_bound_by_requirements(self) -> None:
        form = OrgaCharacterForm(
            self._data(self.wasteland, self.psionic),
            instance=self._character(),
            context=self._context(),
        )

        assert not form.is_valid()
        assert "Bunker" in str(form.errors[get_question_key(self.mutation)])
        assert str(self.psionic.uuid) in form.dependencies

    def _excel_form(self, origin: WritingOption) -> OrgaCharacterForm:
        """Build the organizer form of a character holding the given origin, as the excel edit does."""
        character = self._character()
        WritingChoice.objects.create(question=self.origin, option=origin, element_id=character.id)
        return OrgaCharacterForm(instance=character, context=self._context())

    def test_excel_edit_hides_options_with_unmet_requirements(self) -> None:
        # a single field is edited alone: the gating cannot run on the client, the choices are filtered here
        form = self._excel_form(self.wasteland)
        field_key = get_question_key(self.mutation)

        form.filter_gated_choices(field_key)

        assert str(self.psionic.uuid) not in [str(value) for value, _label in form.fields[field_key].choices]

    def test_excel_edit_keeps_options_with_met_requirements(self) -> None:
        form = self._excel_form(self.bunker)
        field_key = get_question_key(self.mutation)

        form.filter_gated_choices(field_key)

        assert str(self.psionic.uuid) in [str(value) for value, _label in form.fields[field_key].choices]

    def test_excel_edit_refuses_gated_option_on_submit(self) -> None:
        # the popup can be stale: the filtered choices reject the option at validation too
        character = self._character()
        WritingChoice.objects.create(question=self.origin, option=self.wasteland, element_id=character.id)
        field_key = get_question_key(self.mutation)

        form = OrgaCharacterForm(
            {"name": "Original", field_key: str(self.psionic.uuid)},
            instance=character,
            context=self._context(),
        )
        form.filter_gated_choices(field_key)

        assert not form.is_valid()
        assert field_key in form.errors

    def test_organizer_form_accepted_when_requirement_selected(self) -> None:
        form = OrgaCharacterForm(
            self._data(self.bunker, self.psionic),
            instance=self._character(),
            context=self._context(),
        )

        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestCharacterQuestionDependencies(BaseTestCase):
    """Check that questions with unmet requirements are hidden and not stored."""

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
        # mandatory, so the gating is what lets the form be saved without an answer
        self.gear = self._question("Gear", order=3, status=QuestionStatus.MANDATORY)

        self.bunker = WritingOption.objects.create(event=self.event, question=self.origin, name="Bunker", order=1)
        self.wasteland = WritingOption.objects.create(event=self.event, question=self.origin, name="Wasteland", order=2)
        self.rifle = WritingOption.objects.create(event=self.event, question=self.gear, name="Rifle", order=1)

        self.gear.requirements.set([self.bunker])

    def _question(self, name: str, order: int, status: str = QuestionStatus.OPTIONAL) -> WritingQuestion:
        return WritingQuestion.objects.create(
            event=self.event,
            applicable=QuestionApplicable.CHARACTER,
            typ=BaseQuestionType.SINGLE,
            status=status,
            name=name,
            order=order,
        )

    def _context(self) -> dict:
        return {
            "event": self.event,
            "run": self.run,
            "member": self.get_member(),
            "features": {"character", "user_character", "wri_que_requirements"},
            "association_id": self.event.association_id,
        }

    def _character(self) -> Character:
        return Character.objects.create(
            event=self.event,
            player=self.get_member(),
            name="Original",
            status=CharacterStatus.CREATION,
        )

    def _data(self, origin: WritingOption | None, gear: WritingOption | None) -> dict:
        data = {"name": "Original"}
        if origin:
            data[get_question_key(self.origin)] = str(origin.uuid)
        if gear:
            data[get_question_key(self.gear)] = str(gear.uuid)
        return data

    def test_gated_question_not_required_when_requirement_missing(self) -> None:
        form = CharacterForm(self._data(self.wasteland, None), instance=self._character(), context=self._context())

        assert form.is_valid(), form.errors
        assert form.gated_questions

    def test_gated_question_required_when_requirement_selected(self) -> None:
        form = CharacterForm(self._data(self.bunker, None), instance=self._character(), context=self._context())

        assert not form.is_valid()
        assert get_question_key(self.gear) in form.errors

    def test_gated_question_answer_kept_when_requirement_selected(self) -> None:
        form = CharacterForm(self._data(self.bunker, self.rifle), instance=self._character(), context=self._context())

        assert form.is_valid(), form.errors
        character = form.save()

        assert WritingChoice.objects.filter(element_id=character.id, option=self.rifle).exists()

    def test_gated_question_answer_discarded_on_save(self) -> None:
        # the answer was given when the question was shown: hiding it again must remove it
        character = self._character()
        WritingChoice.objects.create(question=self.gear, option=self.rifle, element_id=character.id)

        form = CharacterForm(self._data(self.wasteland, self.rifle), instance=character, context=self._context())

        assert form.is_valid(), form.errors
        form.save()

        assert not WritingChoice.objects.filter(element_id=character.id, question=self.gear).exists()

    def test_organizer_form_bound_by_question_requirements(self) -> None:
        form = OrgaCharacterForm(
            self._data(self.wasteland, self.rifle), instance=self._character(), context=self._context()
        )

        assert form.is_valid(), form.errors
        character = form.save()

        # the gated question is hidden for organizers too: its answer is discarded
        assert not WritingChoice.objects.filter(element_id=character.id, option=self.rifle).exists()

    def test_organizer_form_question_kept_when_requirement_selected(self) -> None:
        form = OrgaCharacterForm(
            self._data(self.bunker, self.rifle), instance=self._character(), context=self._context()
        )

        assert form.is_valid(), form.errors
        character = form.save()

        assert WritingChoice.objects.filter(element_id=character.id, option=self.rifle).exists()

    def test_question_dependencies_cached_and_cleared_on_requirement_change(self) -> None:
        features = {"character", "wri_que_requirements"}
        assert get_character_question_dependencies(self.event.id, features) == {
            str(self.gear.uuid): [str(self.bunker.uuid)]
        }

        self.gear.requirements.set([self.wasteland])

        assert get_character_question_dependencies(self.event.id, features) == {
            str(self.gear.uuid): [str(self.wasteland.uuid)]
        }

        self.gear.requirements.clear()

        assert get_character_question_dependencies(self.event.id, features) == {}

    def test_question_dependencies_empty_without_requirements_feature(self) -> None:
        assert get_character_question_dependencies(self.event.id, {"character"}) == {}
