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

"""Tests for creation only abilities and exclusive groups of abilities"""

from typing import Any

import pytest

from larpmanager.models.base import Feature
from larpmanager.models.event import EventConfig
from larpmanager.models.experience import AbilityExp, ExclusiveExp
from larpmanager.models.writing import CharacterStatus
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.io.download import export_abilities, export_exclusives, zip_exports
from larpmanager.utils.io.restore import _FakeFile, _FakeForm, execute_restore, preview_restore
from larpmanager.utils.io.upload import abilities_load, exclusives_load
from larpmanager.utils.services.experience import (
    calculate_character_experience_points,
    get_ability_exclusive_labels,
    get_available_ability_exp,
    get_exclusive_blocked_abilities,
    is_creation_closed,
    remove_char_ability,
)

PX_AVAIL = 100


@pytest.mark.django_db(transaction=True)
class TestExperienceExclusives(BaseTestCase):
    """Test cases for creation only abilities and exclusive groups"""

    def setUp(self) -> None:
        self.event = self.get_event()
        self.event.features.add(self._feature("experience"))
        self.system = self.get_system_exp(self.event)
        self.context = {
            "event": self.event,
            "run": self.get_run(),
            "features": set(),
            "association_id": self.event.association_id,
            "member": self.get_member(),
        }

    @staticmethod
    def _feature(slug: str) -> Feature:
        feature, _created = Feature.objects.get_or_create(slug=slug, defaults={"name": slug, "overall": False})
        return feature

    def _config(self, name: str, value: str = "True", event: Any = None) -> None:
        EventConfig.objects.update_or_create(event=event or self.event, name=name, defaults={"value": value})

    def _ability(self, name: str, cost: int = 1, **kwargs: Any) -> AbilityExp:
        number = AbilityExp.objects.filter(event=self.event).count() + 1
        return AbilityExp.objects.create(
            event=self.event, name=name, number=number, system=self.system, cost=cost, **kwargs
        )

    def _exclusive(self, name: str, abilities: list[AbilityExp], max_count: int = 1) -> ExclusiveExp:
        number = ExclusiveExp.objects.filter(event=self.event).count() + 1
        exclusive = ExclusiveExp.objects.create(event=self.event, name=name, number=number, max_count=max_count)
        exclusive.abilities.set(abilities)
        return exclusive

    def _available_names(self, character: Any) -> set[str]:
        available = get_available_ability_exp(character, {self.system.id: PX_AVAIL})
        return {ability.name for ability in available}

    def _enable_creation_review(self) -> None:
        self.event.features.add(self._feature("user_character"))
        self._config("exp_user")
        self._config("user_character_approval")

    # Creation only

    def test_creation_only_available_until_approved(self) -> None:
        """Creation only abilities are available in every status except approved"""
        self._enable_creation_review()
        self._ability("Noble birth", creation_only=True)
        self._ability("Swordplay")
        character = self.character(event=self.event)

        for status in (CharacterStatus.CREATION, CharacterStatus.PROPOSED, CharacterStatus.REVIEW):
            character.status = status
            character.save()
            self.assertEqual(self._available_names(character), {"Noble birth", "Swordplay"}, status)

        character.status = CharacterStatus.APPROVED
        character.save()
        self.assertTrue(is_creation_closed(character))
        self.assertEqual(self._available_names(character), {"Swordplay"})

    def test_creation_only_ignored_without_review(self) -> None:
        """Without the review process, or without character creation, the flag has no effect"""
        self._ability("Noble birth", creation_only=True)
        character = self.character(event=self.event, status=CharacterStatus.APPROVED)

        # Approval config set, but character creation feature missing
        self._config("user_character_approval")
        self.assertFalse(is_creation_closed(character))
        self.assertEqual(self._available_names(character), {"Noble birth"})

        # Character creation active, but approval disabled
        self.event.features.add(self._feature("user_character"))
        self._config("user_character_approval", "")
        self.assertFalse(is_creation_closed(character))
        self.assertEqual(self._available_names(character), {"Noble birth"})

    def test_creation_only_kept_after_approval(self) -> None:
        """An ability obtained during creation stays on the character after approval"""
        self._enable_creation_review()
        ability = self._ability("Noble birth", creation_only=True)
        character = self.character(event=self.event)
        character.exp_ability_list.add(ability)

        character.status = CharacterStatus.APPROVED
        character.save()
        calculate_character_experience_points(character)
        self.assertIn(ability, character.exp_ability_list.all())

    def test_creation_only_staff_assignment(self) -> None:
        """Staff can assign a creation only ability to an approved character"""
        self._enable_creation_review()
        ability = self._ability("Noble birth", creation_only=True)
        character = self.character(event=self.event, status=CharacterStatus.APPROVED)
        ability.characters.add(character)
        self.assertIn(ability, character.exp_ability_list.all())

    def test_creation_only_form_field(self) -> None:
        """The form shows the creation only field only under the character creation review process"""
        from larpmanager.forms.experience import OrgaAbilityExpForm

        params = {**self.context, "features": {"experience": 1}}
        self._config("exp_user")
        self.assertNotIn("creation_only", OrgaAbilityExpForm(context=params).fields)

        self._enable_creation_review()
        params = {**self.context, "features": {"experience": 1, "user_character": 1}}
        self.assertIn("creation_only", OrgaAbilityExpForm(context=params).fields)

    # Exclusive groups

    def test_exclusive_max_one(self) -> None:
        """Once an ability of a group with maximum one is owned, the others are no longer available"""
        self._config("exp_exclusives")
        first, second, third = self._ability("Sword"), self._ability("Axe"), self._ability("Spear")
        self._ability("Shield")
        self._exclusive("Weapons", [first, second, third])
        character = self.character(event=self.event)

        self.assertEqual(self._available_names(character), {"Sword", "Axe", "Spear", "Shield"})
        character.exp_ability_list.add(first)
        self.assertEqual(self._available_names(character), {"Shield"})

    def test_exclusive_max_two(self) -> None:
        """A group with maximum two blocks only once two abilities are owned"""
        self._config("exp_exclusives")
        abilities = [self._ability(name) for name in ("Fire", "Water", "Earth")]
        self._exclusive("Schools", abilities, max_count=2)
        character = self.character(event=self.event)

        character.exp_ability_list.add(abilities[0])
        self.assertEqual(self._available_names(character), {"Water", "Earth"})
        character.exp_ability_list.add(abilities[1])
        self.assertEqual(self._available_names(character), set())

    def test_exclusive_disabled_config(self) -> None:
        """Without the exclusive groups config, groups are ignored"""
        first, second = self._ability("Sword"), self._ability("Axe")
        self._exclusive("Weapons", [first, second])
        character = self.character(event=self.event)
        character.exp_ability_list.add(first)

        self.assertEqual(get_exclusive_blocked_abilities(self.event.id, {first.id}), set())
        self.assertEqual(self._available_names(character), {"Axe"})

    def test_exclusive_removal_frees_group(self) -> None:
        """Removing an owned ability of a full group makes the others available again"""
        self._config("exp_exclusives")
        first, second = self._ability("Sword"), self._ability("Axe")
        self._exclusive("Weapons", [first, second])
        character = self.character(event=self.event)
        character.exp_ability_list.add(first)
        self.assertEqual(self._available_names(character), set())

        remove_char_ability(character, first.id)
        self.assertEqual(self._available_names(character), {"Sword", "Axe"})

    def test_exclusive_cache_refresh(self) -> None:
        """Changing the abilities or the maximum of a group refreshes the cached groups"""
        self._config("exp_exclusives")
        first, second, third = self._ability("Sword"), self._ability("Axe"), self._ability("Spear")
        exclusive = self._exclusive("Weapons", [first, second])
        self.assertEqual(get_exclusive_blocked_abilities(self.event.id, {first.id}), {second.id})

        exclusive.abilities.add(third)
        self.assertEqual(get_exclusive_blocked_abilities(self.event.id, {first.id}), {second.id, third.id})

        exclusive.max_count = 2
        exclusive.save()
        self.assertEqual(get_exclusive_blocked_abilities(self.event.id, {first.id}), set())

        exclusive.max_count = 1
        exclusive.save()
        third.exclusives.remove(exclusive)
        self.assertEqual(get_exclusive_blocked_abilities(self.event.id, {first.id}), {second.id})

    def test_exclusive_labels(self) -> None:
        """Each ability of a group gets the group name with owned and maximum count"""
        self._config("exp_exclusives")
        first, second = self._ability("Sword"), self._ability("Axe")
        self._exclusive("Weapons", [first, second], max_count=1)
        labels = get_ability_exclusive_labels(self.event.id, set())
        self.assertEqual(labels[second.id], ["Weapons (0/1)"])

    def test_exclusive_auto_buy(self) -> None:
        """Auto buy skips the abilities of a group that already reached its maximum"""
        self._config("exp_start", "10")
        self._config("exp_auto_buy")
        expensive, medium, cheap = self._ability("Sword", 5), self._ability("Axe", 4), self._ability("Shield", 3)
        character = self.character(event=self.event)

        # Without groups, auto buy gets the two most expensive abilities
        calculate_character_experience_points(character)
        self.assertEqual(set(character.exp_ability_list.all()), {expensive, medium})

        # Clearing the abilities triggers the recompute, so the group must already be in place
        self._config("exp_exclusives")
        self._exclusive("Weapons", [expensive, medium])
        character.exp_ability_list.clear()
        calculate_character_experience_points(character)
        self.assertEqual(set(character.exp_ability_list.all()), {expensive, cheap})

    def test_exclusive_free_abilities(self) -> None:
        """Free abilities granted automatically respect exclusive groups"""
        self._config("exp_exclusives")
        first, second = self._ability("Sword", 0), self._ability("Axe", 0)
        self._exclusive("Weapons", [first, second])
        character = self.character(event=self.event)

        calculate_character_experience_points(character)
        self.assertEqual(character.exp_ability_list.filter(pk__in=[first.id, second.id]).count(), 1)

    def test_exclusive_staff_assignment(self) -> None:
        """Staff can assign abilities beyond the group maximum"""
        self._config("exp_exclusives")
        first, second = self._ability("Sword"), self._ability("Axe")
        self._exclusive("Weapons", [first, second])
        character = self.character(event=self.event)
        first.characters.add(character)
        second.characters.add(character)
        self.assertEqual(set(character.exp_ability_list.all()), {first, second})

    def test_exclusive_campaign_parent(self) -> None:
        """A campaign child event uses the abilities, groups and configs of its parent"""
        self._config("exp_exclusives")
        first, second = self._ability("Sword"), self._ability("Axe")
        self._exclusive("Weapons", [first, second])
        child = self.create_event(parent=self.event, slug="child-event")

        self.assertEqual(get_exclusive_blocked_abilities(child.id, {first.id}), {second.id})
        self.assertEqual(get_ability_exclusive_labels(child.id, {first.id})[second.id], ["Weapons (1/1)"])

    def test_exclusive_form_validation(self) -> None:
        """The form requires at least two abilities and a maximum lower than their number"""
        from larpmanager.forms.experience import OrgaExclusiveExpForm

        first, second = self._ability("Sword"), self._ability("Axe")
        params = {**self.context, "features": {"experience": 1}, "elementTyp": ExclusiveExp}

        form = OrgaExclusiveExpForm({"name": "Weapons", "max_count": 1, "abilities": [first.id]}, context=params)
        self.assertFalse(form.is_valid())
        self.assertIn("abilities", form.errors)

        form = OrgaExclusiveExpForm(
            {"name": "Weapons", "max_count": 2, "abilities": [first.id, second.id]}, context=params
        )
        self.assertFalse(form.is_valid())
        self.assertIn("max_count", form.errors)

        form = OrgaExclusiveExpForm(
            {"name": "Weapons", "max_count": 1, "abilities": [first.id, second.id]}, context=params
        )
        self.assertTrue(form.is_valid(), form.errors)

    # Upload, download and restore

    def test_exclusive_upload_and_export(self) -> None:
        """Uploaded groups are created, updated by name, and exported with their abilities"""
        self._ability("Sword")
        self._ability("Axe")
        self._ability("Spear")
        ctx = {**self.context, "typ": "exp_exclusive"}

        logs = exclusives_load(ctx, _FakeForm(first=_FakeFile(b'name,max,abilities\nWeapons,1,"Sword, Axe"\n')))
        self.assertTrue(logs[0].startswith("OK - Created"), logs)
        exclusive = ExclusiveExp.objects.get(event=self.event, name="Weapons")
        self.assertEqual(exclusive.max_count, 1)
        self.assertEqual({ability.name for ability in exclusive.abilities.all()}, {"Sword", "Axe"})

        logs = exclusives_load(ctx, _FakeForm(first=_FakeFile(b'name,max,abilities\nweapons,2,"Axe, Spear, Sword"\n')))
        self.assertTrue(logs[0].startswith("OK - Updated"), logs)
        self.assertEqual(ExclusiveExp.objects.filter(event=self.event).count(), 1)
        exclusive.refresh_from_db()
        self.assertEqual(exclusive.max_count, 2)

        name, headers, rows = export_exclusives(self.context)[0]
        self.assertEqual(name, "exclusives")
        self.assertEqual(headers, ["name", "max", "abilities"])
        self.assertEqual(rows[0][:2], ["Weapons", 2])
        self.assertEqual(set(rows[0][2].split(", ")), {"Sword", "Axe", "Spear"})

    def test_ability_creation_only_upload_and_export(self) -> None:
        """The creation only flag of the abilities is exported and uploaded"""
        ctx = {**self.context, "typ": "exp_abilitie"}
        self._ability("Noble birth", creation_only=True)
        _name, headers, rows = export_abilities(self.context)[0]
        self.assertEqual(rows[0][headers.index("creation_only")], "true")

        abilities_load(ctx, _FakeForm(first=_FakeFile(b"name,creation_only\nNoble birth,false\n")))
        self.assertFalse(AbilityExp.objects.get(event=self.event, name="Noble birth").creation_only)

    def test_exclusive_backup_restore_round_trip(self) -> None:
        """Groups exported in a backup are restored after their abilities"""
        first, second = self._ability("Sword"), self._ability("Axe")
        self._exclusive("Weapons", [first, second])
        exports = export_abilities(self.context) + export_exclusives(self.context)
        zip_bytes = zip_exports(self.context, exports, "Backup").content

        ExclusiveExp.objects.filter(event=self.event).delete()
        sections, unknown = preview_restore(self.context, zip_bytes)
        self.assertEqual(unknown, [])
        self.assertIn("Weapons", str(sections))

        logs = execute_restore(self.context, zip_bytes)
        self.assertFalse([log for log in logs if log.startswith("ERR")], logs)
        exclusive = ExclusiveExp.objects.get(event=self.event, name="Weapons")
        self.assertEqual(set(exclusive.abilities.all()), {first, second})
