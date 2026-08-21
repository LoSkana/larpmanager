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

"""Unit tests for the background auto-save of the player character form."""

import json
from typing import Any

import pytest
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import RequestFactory

from larpmanager.forms.character import CharacterForm
from larpmanager.models.form import QuestionApplicable, WritingQuestion, WritingQuestionType
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.tests.unit.base import BaseTestCase
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

    def _call(self, character: Character | None, post_data: dict) -> Any:
        request = RequestFactory().post("/", post_data)
        request.user = self.get_user()
        request._messages = CookieStorage(request)  # noqa: SLF001  # no middleware in unit tests
        return character_form(request, self._context(), self.get_event().slug, character, CharacterForm)

    @staticmethod
    def _loaded(character: Character) -> Character:
        """Get the character as loaded by a single request, so each page has its own instance."""
        return Character.objects.get(pk=character.pk)

    @staticmethod
    def _stamp(character: Character) -> str:
        character.refresh_from_db()
        return f"{character.updated.timestamp():.6f}"

    def test_auto_save_stores_changes(self) -> None:
        character = self._character()

        response = self._call(character, {"ajax": "1", "name": "Renamed", "base_updated": self._stamp(character)})

        payload = json.loads(response.content)
        assert payload["res"] == "ok", payload
        character.refresh_from_db()
        assert character.name == "Renamed"

    def test_auto_save_refused_if_saved_elsewhere(self) -> None:
        character = self._character()
        stale_stamp = f"{character.updated.timestamp() - 60:.6f}"

        response = self._call(character, {"ajax": "1", "name": "Renamed", "base_updated": stale_stamp})

        payload = json.loads(response.content)
        assert payload["res"] == "ko", payload
        assert payload["stale"] is True
        character.refresh_from_db()
        assert character.name == "Original"

    def test_auto_save_of_two_pages_open_together(self) -> None:
        character = self._character()
        # both pages are loaded at the same moment, so they hold the same version stamp
        page_stamp = self._stamp(character)

        # the first page saves: it gets a new stamp, and keeps on saving with it
        first = json.loads(
            self._call(self._loaded(character), {"ajax": "1", "name": "First page", "base_updated": page_stamp}).content,
        )
        assert first["res"] == "ok", first

        again = json.loads(
            self._call(
                self._loaded(character),
                {"ajax": "1", "name": "First page again", "base_updated": first["updated"]},
            ).content,
        )
        assert again["res"] == "ok", again

        # the second page still holds the stamp of when it was loaded: it is refused
        second = json.loads(
            self._call(
                self._loaded(character),
                {"ajax": "1", "name": "Second page", "base_updated": page_stamp},
            ).content,
        )
        assert second["res"] == "ko", second
        assert second["stale"] is True
        character.refresh_from_db()
        assert character.name == "First page again"

    def test_auto_save_skips_character_without_name(self) -> None:
        before = Character.objects.count()

        response = self._call(None, {"ajax": "1", "name": "  "})

        payload = json.loads(response.content)
        assert payload["res"] == "ko", payload
        assert Character.objects.count() == before

    def test_auto_save_creates_named_character(self) -> None:
        response = self._call(None, {"ajax": "1", "name": "Brand new"})

        payload = json.loads(response.content)
        assert payload["res"] == "ok", payload
        assert "url" in payload
        character = Character.objects.get(name="Brand new")
        assert character.player_id == self.get_member().id


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
