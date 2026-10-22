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

"""Unit tests for the reset of approved campaign characters back to revision on new assignments."""

from unittest.mock import patch

import pytest
from django.core.cache import cache

from larpmanager.models.event import EventConfig, Run
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.tests.unit.base import BaseTestCase

FEATURES_PATH = "larpmanager.utils.services.character.get_event_features"


@pytest.mark.django_db
class TestResetCharacterStatus(BaseTestCase):
    """Check the status reset of approved characters assigned to a new campaign run."""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.parent = self.create_event(name="Parent")
        self.child = self.create_event(name="Child", parent=self.parent)
        self.first_run = Run.objects.get_or_create(event=self.parent, number=1)[0]
        self.second_run = Run.objects.get_or_create(event=self.child, number=1)[0]
        self.member = self.get_member()
        self.character = Character.objects.create(
            event=self.parent, name="Hero", number=1, player=self.member, status=CharacterStatus.APPROVED
        )

    def _assign(self, run: object) -> None:
        registration = self.create_registration(member=self.member, run=run)
        RegistrationCharacterRel.objects.create(registration=registration, character=self.character)
        self.character.refresh_from_db()

    def _enable_config(self) -> None:
        EventConfig.objects.create(event=self.parent, name="reset_character_status", value="True")

    def test_returning_character_reset_to_revision(self) -> None:
        self._enable_config()
        with patch(FEATURES_PATH, return_value={"campaign", "user_character"}):
            self._assign(self.first_run)
            assert self.character.status == CharacterStatus.APPROVED
            self._assign(self.second_run)
        assert self.character.status == CharacterStatus.REVIEW

    def test_no_reset_without_config(self) -> None:
        with patch(FEATURES_PATH, return_value={"campaign", "user_character"}):
            self._assign(self.first_run)
            self._assign(self.second_run)
        assert self.character.status == CharacterStatus.APPROVED

    def test_no_reset_without_campaign_feature(self) -> None:
        self._enable_config()
        with patch(FEATURES_PATH, return_value={"user_character"}):
            self._assign(self.first_run)
            self._assign(self.second_run)
        assert self.character.status == CharacterStatus.APPROVED
