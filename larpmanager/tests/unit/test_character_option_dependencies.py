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

from larpmanager.cache.question import get_character_option_dependencies
from larpmanager.forms.base import get_question_key
from larpmanager.forms.character import CharacterForm, OrgaCharacterForm
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
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

    def test_dependencies_cached_and_cleared_on_requirement_change(self) -> None:
        features = {"character", "wri_que_requirements"}
        assert get_character_option_dependencies(self.event, features) == {
            str(self.psionic.uuid): [str(self.bunker.uuid)]
        }

        # the requirements are written after the option is saved, so the m2m change must clear the cache
        self.psionic.requirements.set([self.wasteland])

        assert get_character_option_dependencies(self.event, features) == {
            str(self.psionic.uuid): [str(self.wasteland.uuid)]
        }

        self.psionic.requirements.clear()

        assert get_character_option_dependencies(self.event, features) == {}

    def test_dependencies_empty_without_character_feature(self) -> None:
        assert get_character_option_dependencies(self.event, {"user_character"}) == {}

    def test_dependencies_empty_without_requirements_feature(self) -> None:
        assert get_character_option_dependencies(self.event, {"character"}) == {}

    def test_organizer_form_not_bound_by_requirements(self) -> None:
        form = OrgaCharacterForm(
            self._data(self.wasteland, self.psionic),
            instance=self._character(),
            context=self._context(),
        )

        assert form.is_valid(), form.errors
        assert str(self.psionic.uuid) in form.dependencies
