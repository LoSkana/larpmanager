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

"""Tests for hidden abilities visible to a list of characters"""

from typing import Any

import pytest

from larpmanager.models.base import Feature
from larpmanager.models.experience import AbilityExp
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.io.download import export_abilities
from larpmanager.utils.io.restore import _FakeFile, _FakeForm
from larpmanager.utils.io.upload import abilities_load
from larpmanager.utils.services.experience import calculate_character_experience_points, get_available_ability_exp

PX_AVAIL = 100


@pytest.mark.django_db(transaction=True)
class TestExperienceVisibleCharacters(BaseTestCase):
    """Test cases for the characters that can see a hidden ability"""

    def setUp(self) -> None:
        self.event = self.get_event()
        feature, _created = Feature.objects.get_or_create(
            slug="experience", defaults={"name": "experience", "overall": False}
        )
        self.event.features.add(feature)
        self.system = self.get_system_exp(self.event)
        self.context = {
            "event": self.event,
            "run": self.get_run(),
            "features": set(),
            "association_id": self.event.association_id,
            "member": self.get_member(),
        }

    def _ability(self, name: str, cost: int = 1, **kwargs: Any) -> AbilityExp:
        number = AbilityExp.objects.filter(event=self.event).count() + 1
        return AbilityExp.objects.create(
            event=self.event, name=name, number=number, system=self.system, cost=cost, **kwargs
        )

    def _available_names(self, character: Any) -> set[str]:
        available = get_available_ability_exp(character, {self.system.id: PX_AVAIL})
        return {ability.name for ability in available}

    def test_hidden_ability_visible_only_to_listed(self) -> None:
        """A hidden ability is available only to the listed characters"""
        self._ability("Swordplay")
        secret = self._ability("Secret art", visible=False)
        listed = self.character(event=self.event, name="Listed")
        other = self.character(event=self.event, name="Other")
        secret.visible_characters.add(listed)

        self.assertEqual(self._available_names(listed), {"Swordplay", "Secret art"})
        self.assertEqual(self._available_names(other), {"Swordplay"})

    def test_visible_ability_ignores_list(self) -> None:
        """A visible ability is available to every character, regardless of the list"""
        ability = self._ability("Swordplay")
        listed = self.character(event=self.event, name="Listed")
        other = self.character(event=self.event, name="Other")
        ability.visible_characters.add(listed)

        self.assertEqual(self._available_names(other), {"Swordplay"})

    def test_free_hidden_ability_granted_to_listed(self) -> None:
        """A free hidden ability is granted only to the listed characters"""
        secret = self._ability("Secret art", cost=0, visible=False)
        listed = self.character(event=self.event, name="Listed")
        other = self.character(event=self.event, name="Other")
        secret.visible_characters.add(listed)

        calculate_character_experience_points(listed)
        calculate_character_experience_points(other)
        self.assertIn(secret, listed.exp_ability_list.all())
        self.assertNotIn(secret, other.exp_ability_list.all())

    def test_visible_characters_upload_and_export(self) -> None:
        """The visible characters of the abilities are exported and uploaded"""
        ctx = {**self.context, "typ": "exp_abilitie"}
        secret = self._ability("Secret art", visible=False)
        listed = self.character(event=self.event, name="Listed")
        other = self.character(event=self.event, name="Other")
        secret.visible_characters.add(listed)

        _name, headers, rows = export_abilities(self.context)[0]
        self.assertEqual(rows[0][headers.index("visible_characters")], "Listed")

        abilities_load(ctx, _FakeForm(first=_FakeFile(b'name,visible_characters\nSecret art,"Listed, Other"\n')))
        self.assertEqual(set(secret.visible_characters.all()), {listed, other})
