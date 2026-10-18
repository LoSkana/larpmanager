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

"""Tests for the campaign characters a member can choose to play on signup."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from larpmanager.models.event import Event, EventConfig, Run
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import CharacterConfig, CharacterStatus
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.registrations.characters import assign_campaign_character, get_campaign_characters

FEATURES_PATH = "larpmanager.utils.registrations.characters.get_event_features"


class TestCampaignCharacters(BaseTestCase):
    """Test get_campaign_characters and assign_campaign_character."""

    def setUp(self) -> None:
        """Create a campaign with a parent run already played and a child run."""
        super().setUp()
        self.parent = self.create_event(name="Parent")
        self.child = self.create_event(name="Child", parent=self.parent)
        self.parent_run = self._event_run(self.parent, date(2050, 1, 1))
        self.child_run = self._event_run(self.child, date(2050, 2, 1))
        self.member = self.get_member()

        self.alpha = self.character(event=self.parent, name="Alpha")
        parent_registration = self.create_registration(member=self.member, run=self.parent_run)
        self.previous_rel = RegistrationCharacterRel.objects.create(
            registration=parent_registration, character=self.alpha, custom_name="Custom Alpha"
        )

    @staticmethod
    def _event_run(event: Event, day: date) -> Run:
        """Get the run created with the event, held on the given day."""
        run = Run.objects.get(event=event)
        run.start = day
        run.end = day
        run.save()
        return run

    def test_previous_character_offered(self) -> None:
        """The character played in the parent run is offered in the child run."""
        with patch(FEATURES_PATH, return_value={"campaign"}):
            candidates = get_campaign_characters(self.member.id, self.child_run.id)

        assert [candidate["character"] for candidate in candidates] == [self.alpha]
        assert candidates[0]["previous_rel"] == self.previous_rel

    def test_no_parent(self) -> None:
        """Nothing is offered outside a campaign child event."""
        with patch(FEATURES_PATH, return_value={"campaign"}):
            assert get_campaign_characters(self.member.id, self.parent_run.id) == []

    def test_inactive_excluded(self) -> None:
        """Inactive characters are not offered."""
        CharacterConfig.objects.create(character=self.alpha, name="inactive", value="True")
        with patch(FEATURES_PATH, return_value={"campaign"}):
            assert get_campaign_characters(self.member.id, self.child_run.id) == []

    def test_taken_excluded(self) -> None:
        """Characters already assigned to another registration of the run are not offered."""
        other = self.create_member(user=self.create_user(username="other", email="other@example.com"))
        other_registration = self.create_registration(member=other, run=self.child_run)
        RegistrationCharacterRel.objects.create(registration=other_registration, character=self.alpha)
        with patch(FEATURES_PATH, return_value={"campaign"}):
            assert get_campaign_characters(self.member.id, self.child_run.id) == []

    def test_owned_unapproved_excluded(self) -> None:
        """With approval required, owned characters not yet approved are not offered."""
        owned = self.character(event=self.parent, name="Owned", player=self.member, status=CharacterStatus.CREATION)
        EventConfig.objects.create(event=self.parent, name="user_character_approval", value="True")
        with patch(FEATURES_PATH, return_value={"campaign", "user_character"}):
            candidates = get_campaign_characters(self.member.id, self.child_run.id)

        assert owned not in [candidate["character"] for candidate in candidates]

    def test_assign_carries_custom_data(self) -> None:
        """Assigning the chosen character copies the data customized in the previous run."""
        registration = self.create_registration(member=self.member, run=self.child_run)
        with patch(FEATURES_PATH, return_value={"campaign"}):
            candidate = get_campaign_characters(self.member.id, self.child_run.id)[0]
        assign_campaign_character(registration, candidate)

        new_rel = RegistrationCharacterRel.objects.get(registration=registration)
        assert new_rel.character == self.alpha
        assert new_rel.custom_name == "Custom Alpha"
