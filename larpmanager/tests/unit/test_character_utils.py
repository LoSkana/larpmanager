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

from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member
from larpmanager.models.miscellanea import PlayerRelationship
from larpmanager.models.registration import Registration
from larpmanager.models.writing import Character, Faction, FactionType, Relationship
from larpmanager.utils.character import get_character_relationships
from larpmanager.tests.unit.base import BaseTestCase


class TestCharacterRelationships(BaseTestCase):
    """Test character relationship utilities"""

    def test_get_character_relationships_empty(self):
        """Test relationship retrieval with no relationships"""
        # Create test data
        event = self.event()
        run = self.run()

        # Create source character
        source_char = Character.objects.create(event=event, number=2, name="Source Character")

        # Setup context
        ctx = {"character": source_char, "event": event, "run": run, "factions": {}, "char": {}}

        get_character_relationships(ctx)

        assert ctx["rel"] == []
        assert ctx["pr"] == {}

    def test_get_character_relationships_with_faction_data(self):
        """Test relationship retrieval with character and faction data"""
        # Create test data
        event = self.event()
        run = self.run()

        # Create characters
        source_char = Character.objects.create(event=event, number=10, name="Source Character")

        target_char = Character.objects.create(event=event, number=20, name="Target Character")

        # Create faction
        faction = Faction.objects.create(event=event, number=1, name="Test Faction", typ=FactionType.PRIM)

        # Create relationship
        relationship = Relationship.objects.create(
            source=source_char, target=target_char, text="Close ally and trusted friend"
        )

        # Mock character show method
        target_show_data = {"id": target_char.id, "name": "Target Character", "factions": [faction.number]}

        # Setup context with pre-cached character data
        ctx = {
            "character": source_char,
            "event": event,
            "run": run,
            "chars": {target_char.number: target_show_data},
            "factions": {faction.number: {"name": "Test Faction", "typ": FactionType.PRIM}},
            "char": {},
        }

        get_character_relationships(ctx)

        assert len(ctx["rel"]) == 1
        rel_data = ctx["rel"][0]
        assert rel_data["id"] == target_char.id
        assert rel_data["name"] == "Target Character"
        assert rel_data["text"] == "Close ally and trusted friend"
        assert rel_data["factions_list"] == "Test Faction"
        assert rel_data["font_size"] == int(100 - ((len(rel_data["text"]) / 50) * 4))

    def test_get_character_relationships_secret_faction_filtered(self):
        """Test that secret factions are filtered out"""
        # Create test data
        event = self.event()
        run = self.run()

        source_char = Character.objects.create(event=event, number=30, name="Source")
        target_char = Character.objects.create(event=event, number=40, name="Target")

        # Create secret faction
        secret_faction = Faction.objects.create(event=event, number=11, name="Secret Faction", typ=FactionType.SECRET)

        # Create public faction
        public_faction = Faction.objects.create(event=event, number=21, name="Public Faction", typ=FactionType.PRIM)

        Relationship.objects.create(source=source_char, target=target_char, text="Connected character")

        target_show_data = {
            "id": target_char.id,
            "name": "Target Character",
            "factions": [secret_faction.number, public_faction.number],
        }

        ctx = {
            "character": source_char,
            "event": event,
            "run": run,
            "chars": {target_char.number: target_show_data},
            "factions": {
                secret_faction.number: {"name": "Secret Faction", "typ": FactionType.SECRET},
                public_faction.number: {"name": "Public Faction", "typ": FactionType.PRIM},
            },
            "char": {},
        }

        get_character_relationships(ctx)

        # Should only show public faction
        rel_data = ctx["rel"][0]
        assert rel_data["factions_list"] == "Public Faction"

    @patch("larpmanager.utils.character.Character.objects.get")
    def test_get_character_relationships_character_lookup(self, mock_char_get):
        """Test relationship retrieval with self.character() lookup fallback"""
        # Create test data
        event = self.event()
        run = self.run()

        source_char = Character.objects.create(event=event, number=50, name="Source")
        target_char = Character.objects.create(event=event, number=60, name="Target")

        # Create relationship
        Relationship.objects.create(source=source_char, target=target_char, text="Test relationship")

        # Mock target character lookup
        mock_target = Mock()
        mock_target.show.return_value = {"id": target_char.id, "name": "Target Character", "factions": []}
        mock_char_get.return_value = mock_target

        ctx = {"character": source_char, "event": event, "run": run, "factions": {}, "char": {}}

        get_character_relationships(ctx)

        # Should have found the relationship via lookup
        assert len(ctx["rel"]) == 1
        mock_char_get.assert_called_once_with(event=event, number=target_char.number)
        mock_target.show.assert_called_once_with(run)

    @patch("larpmanager.utils.character.Character.objects.get")
    def test_get_character_relationships_character_not_found(self, mock_char_get):
        """Test relationship retrieval when target character is not found"""
        mock_char_get.side_effect = ObjectDoesNotExist

        # Create test data
        event = self.event()
        run = self.run()

        source_char = Character.objects.create(event=event, number=70, name="Source")

        # Create relationship with non-existent target
        target_char = Character.objects.create(event=event, number=999, name="NonExistent")
        Relationship.objects.create(source=source_char, target=target_char, text="Test relationship")

        ctx = {"character": source_char, "event": event, "run": run, "factions": {}, "char": {}}

        get_character_relationships(ctx)

        # Should skip the relationship
        assert ctx["rel"] == []

    def test_get_character_relationships_with_player_relationships(self):
        """Test relationship retrieval including player-inputted relationships"""
        # Create test data
        event = self.event()
        run = self.run()

        source_char = Character.objects.create(event=event, number=80, name="Source")
        target_char = Character.objects.create(event=event, number=90, name="Target")

        # Create game master relationship
        Relationship.objects.create(source=source_char, target=target_char, text="Official GM relationship")

        # Create player relationship
        PlayerRelationship.objects.create(
            reg=self.registration(), target=target_char, text="Player-defined relationship details"
        )

        target_show_data = {"id": target_char.id, "name": "Target Character", "factions": []}

        ctx = {
            "character": source_char,
            "event": event,
            "run": run,
            "chars": {target_char.number: target_show_data},
            "factions": {},
            "char": {"player_id": self.member().id},  # Player context
        }

        get_character_relationships(ctx)

        # Should prefer player relationship text over GM text
        assert len(ctx["rel"]) == 1
        rel_data = ctx["rel"][0]
        assert rel_data["text"] == "Player-defined relationship details"

        # Should also populate player relationship dict
        assert target_char.id in ctx["pr"]
        assert ctx["pr"][target_char.id].text == "Player-defined relationship details"

    def test_get_character_relationships_restrict_empty(self):
        """Test relationship restriction filtering empty relationships"""
        # Create test data
        event = self.event()
        run = self.run()

        source_char = Character.objects.create(event=event, number=100, name="Source")
        target_char = Character.objects.create(event=event, number=110, name="Target")

        # Create relationship with empty text
        Relationship.objects.create(
            source=source_char,
            target=target_char,
            text="",  # Empty relationship text
        )

        target_show_data = {"id": target_char.id, "name": "Target Character", "factions": []}

        ctx = {
            "character": source_char,
            "event": event,
            "run": run,
            "chars": {target_char.number: target_show_data},
            "factions": {},
            "char": {},
        }

        # Test with restrict=True (default)
        get_character_relationships(ctx, restrict=True)
        assert ctx["rel"] == []  # Should filter out empty relationship

        # Test with restrict=False
        get_character_relationships(ctx, restrict=False)
        assert len(ctx["rel"]) == 1  # Should include empty relationship

    def test_get_character_relationships_sorting_by_length(self):
        """Test that relationships are sorted by text length (descending)"""
        # Create test data
        event = self.event()
        run = self.run()

        source_char = Character.objects.create(event=event, number=120, name="Source")

        # Create target characters with different relationship lengths
        target1 = Character.objects.create(event=event, number=130, name="Target1")
        target2 = Character.objects.create(event=event, number=140, name="Target2")
        target3 = Character.objects.create(event=event, number=150, name="Target3")

        # Create relationships with different text lengths
        Relationship.objects.create(
            source=source_char,
            target=target1,
            text="Short",  # 5 chars
        )

        Relationship.objects.create(
            source=source_char,
            target=target2,
            text="This is a much longer relationship description with many details",  # 67 chars
        )

        Relationship.objects.create(
            source=source_char,
            target=target3,
            text="Medium length text",  # 18 chars
        )

        # Setup character show data
        chars_data = {}
        for char in [target1, target2, target3]:
            chars_data[char.number] = {"id": char.id, "name": char.name, "factions": []}

        ctx = {"character": source_char, "event": event, "run": run, "chars": chars_data, "factions": {}, "char": {}}

        get_character_relationships(ctx)

        # Should be sorted by text length (descending)
        assert len(ctx["rel"]) == 3
        assert len(ctx["rel"][0]["text"]) >= len(ctx["rel"][1]["text"])
        assert len(ctx["rel"][1]["text"]) >= len(ctx["rel"][2]["text"])

        # Verify specific order
        assert ctx["rel"][0]["text"] == "This is a much longer relationship description with many details"
        assert ctx["rel"][1]["text"] == "Medium length text"
        assert ctx["rel"][2]["text"] == "Short"

    def test_get_character_relationships_font_size_calculation(self):
        """Test font size calculation based on text length"""
        # Create test data
        event = self.event()
        run = self.run()

        source_char = Character.objects.create(event=event, number=160, name="Source")
        target_char = Character.objects.create(event=event, number=170, name="Target")

        # Create relationship with specific text length
        relationship_text = "A" * 100  # 100 characters
        Relationship.objects.create(source=source_char, target=target_char, text=relationship_text)

        target_show_data = {"id": target_char.id, "name": "Target Character", "factions": []}

        ctx = {
            "character": source_char,
            "event": event,
            "run": run,
            "chars": {target_char.number: target_show_data},
            "factions": {},
            "char": {},
        }

        get_character_relationships(ctx)

        # Font size calculation: 100 - ((100 / 50) * 4) = 100 - 8 = 92
        expected_font_size = int(100 - ((100 / 50) * 4))
        assert ctx["rel"][0]["font_size"] == expected_font_size
