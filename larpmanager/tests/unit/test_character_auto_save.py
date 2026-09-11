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

"""Unit tests for the background auto-save of the player character form.

Auto-save stages the posted form as a redis draft and never touches the real record;
the draft is only ever applied to the database when the player explicitly submits the form.
"""

import json
from typing import Any

import pytest
from django.contrib.messages.storage.cookie import CookieStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory

from larpmanager.forms.character import CharacterForm
from larpmanager.models.form import QuestionApplicable, WritingQuestion, WritingQuestionType
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.edit.autosave import _draft_cache_key, draft_element_key
from larpmanager.views.user.character import character_form, propose_character_for_approval


@pytest.mark.django_db
class TestCharacterAutoSave(BaseTestCase):
    """Exercise the ajax auto-save of the character form."""

    def _context(self) -> dict:
        run = self.get_run()
        WritingQuestion.objects.get_or_create(
            event=run.event,
            applicable=QuestionApplicable.CHARACTER,
            typ=WritingQuestionType.NAME,
            defaults={"name": "Name", "order": 1},
        )
        return {
            "event": run.event,
            "run": run,
            "member": self.get_member(),
            "features": {"character", "user_character"},
            "association_id": run.event.association_id,
            "auto_save": True,
        }

    def _character(self) -> Character:
        return Character.objects.create(
            event=self.get_event(),
            player=self.get_member(),
            name="Original",
            status=CharacterStatus.CREATION,
        )

    def _request(self, post_data: dict) -> Any:
        request = RequestFactory().post("/", post_data)
        request.user = self.get_user()
        request._messages = CookieStorage(request)  # noqa: SLF001  # no middleware in unit tests
        SessionMiddleware(lambda _req: None).process_request(request)
        request.session.save()
        return request

    def _call(self, character: Character | None, post_data: dict) -> tuple[Any, Any]:
        request = self._request(post_data)
        response = character_form(request, self._context(), self.get_event().slug, character, CharacterForm)
        return request, response

    def test_auto_save_stages_draft_without_saving_the_record(self) -> None:
        character = self._character()

        _request, response = self._call(character, {"ajax": "1", "name": "Renamed"})

        payload = json.loads(response.content)
        assert payload["res"] == "ok", payload
        character.refresh_from_db()
        assert character.name == "Original"

        draft = cache.get(_draft_cache_key(self.get_member(), draft_element_key(self._context(), "character", character)))
        assert "name=Renamed" in draft["data"]

    def test_auto_save_skips_character_without_name(self) -> None:
        before = Character.objects.count()

        request, response = self._call(None, {"ajax": "1", "name": "  "})

        payload = json.loads(response.content)
        assert payload["res"] == "ok", payload
        assert Character.objects.count() == before

        element_key = draft_element_key(self._context(), "character", None, request)
        assert cache.get(_draft_cache_key(self.get_member(), element_key)) is None

    def test_auto_save_stages_draft_for_not_yet_created_character(self) -> None:
        before = Character.objects.count()

        request, response = self._call(None, {"ajax": "1", "name": "Brand new"})

        payload = json.loads(response.content)
        assert payload["res"] == "ok", payload
        assert Character.objects.count() == before

        element_key = draft_element_key(self._context(), "character", None, request)
        draft = cache.get(_draft_cache_key(self.get_member(), element_key))
        assert "name=Brand+new" in draft["data"]


@pytest.mark.django_db
class TestProposeCharacterForApproval(BaseTestCase):
    """Exercise the guarded CREATION/REVIEW -> PROPOSED transition used by character_confirm."""

    def _character(self, status: str) -> Character:
        return Character.objects.create(
            event=self.get_event(),
            player=self.get_member(),
            name="Original",
            status=status,
        )

    def test_proposes_character_in_creation(self) -> None:
        character = self._character(CharacterStatus.CREATION)

        propose_character_for_approval(character)

        character.refresh_from_db()
        assert character.status == CharacterStatus.PROPOSED

    def test_proposes_character_in_review(self) -> None:
        character = self._character(CharacterStatus.REVIEW)

        propose_character_for_approval(character)

        character.refresh_from_db()
        assert character.status == CharacterStatus.PROPOSED

    def test_does_not_reproposed_already_proposed_character(self) -> None:
        character = self._character(CharacterStatus.PROPOSED)

        propose_character_for_approval(character)

        character.refresh_from_db()
        assert character.status == CharacterStatus.PROPOSED

    def test_does_not_regress_approved_character(self) -> None:
        character = self._character(CharacterStatus.APPROVED)

        propose_character_for_approval(character)

        character.refresh_from_db()
        assert character.status == CharacterStatus.APPROVED
