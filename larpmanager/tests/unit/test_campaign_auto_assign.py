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

"""Unit tests for the automatic assignment of the previous campaign character upon registration."""

from unittest.mock import patch

import pytest
from django.core.cache import cache

from larpmanager.models.event import EventConfig, Run
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import Character
from larpmanager.tests.unit.base import BaseTestCase

FEATURES_PATH = "larpmanager.utils.services.event.get_event_features"


@pytest.mark.django_db
class TestCampaignAutoAssign(BaseTestCase):
    """Check the previous campaign character is assigned on new registrations unless disabled."""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.parent = self.create_event(name="Parent")
        self.child = self.create_event(name="Child", parent=self.parent)
        self.first_run = Run.objects.get_or_create(event=self.parent, number=1)[0]
        self.second_run = Run.objects.get_or_create(event=self.child, number=1)[0]
        self.member = self.get_member()
        self.character = Character.objects.create(event=self.parent, name="Hero", number=1, player=self.member)
        first_registration = self.create_registration(member=self.member, run=self.first_run)
        RegistrationCharacterRel.objects.create(registration=first_registration, character=self.character)

    def _assigned(self) -> bool:
        return RegistrationCharacterRel.objects.filter(
            registration__run=self.second_run, character=self.character
        ).exists()

    def test_character_auto_assigned(self) -> None:
        with patch(FEATURES_PATH, return_value={"campaign"}):
            self.create_registration(member=self.member, run=self.second_run)
        assert self._assigned()

    def test_no_auto_assign_when_disabled(self) -> None:
        EventConfig.objects.create(event=self.parent, name="campaign_disable_auto_assign", value="True")
        with patch(FEATURES_PATH, return_value={"campaign"}):
            self.create_registration(member=self.member, run=self.second_run)
        assert not self._assigned()
