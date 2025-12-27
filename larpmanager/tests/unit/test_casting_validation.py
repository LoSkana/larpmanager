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

"""Tests for casting validation to prevent hidden character selection"""

import pytest

from larpmanager.models.registration import TicketTier
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.views.user.casting import casting_characters, casting_quest_traits


@pytest.mark.django_db(transaction=True)
class TestCastingValidationFunctions(BaseTestCase):
    """Test casting validation functions prevent hidden character selection"""

    def setUp(self):
        """Set up test data"""
        super().setUp()
        self.event = self.get_event()
        self.run = self.get_run()
        self.member = self.get_member()
        self.registration = self.create_registration(member=self.member, run=self.run)

        # Create a standard ticket and assign to registration
        self.ticket = self.ticket(event=self.event, tier=TicketTier.STANDARD)
        self.registration.ticket = self.ticket
        self.registration.save()

        # Create characters (numbers auto-generated to avoid collisions in parallel tests)
        self.visible_char1 = self.character(event=self.event, name="Visible Character 1", hide=False)
        self.visible_char2 = self.character(event=self.event, name="Visible Character 2", hide=False)
        self.hidden_char = self.character(event=self.event, name="Hidden Character", hide=True)

    def test_casting_characters_excludes_hidden(self):
        """Test that casting_characters function excludes hidden characters from valid_element_ids"""
        context = {
            "event": self.event,
            "run": self.run,
            "features": {},
        }

        # Call the function that should populate valid_element_ids
        casting_characters(context, self.registration)

        # Check that valid_element_ids is set
        self.assertIn("valid_element_ids", context, "valid_element_ids should be in context")

        valid_ids = context["valid_element_ids"]

        # Hidden character should NOT be in valid IDs (now using UUID strings)
        self.assertNotIn(str(self.hidden_char.uuid), valid_ids, "Hidden character should not be in valid IDs")

        # Visible characters SHOULD be in valid IDs (now using UUID strings)
        self.assertIn(str(self.visible_char1.uuid), valid_ids, "Visible character 1 should be in valid IDs")
        self.assertIn(str(self.visible_char2.uuid), valid_ids, "Visible character 2 should be in valid IDs")

    def test_casting_characters_sorted_by_number(self):
        """Test that characters are sorted by number in casting_characters"""
        # Create characters with auto-generated numbers (will be sequential after setUp characters)
        char_first = self.character(event=self.event, name="Character First", hide=False)
        char_second = self.character(event=self.event, name="Character Second", hide=False)
        char_third = self.character(event=self.event, name="Character Third", hide=False)

        # Store numbers for later verification
        char_10 = char_third
        char_7 = char_second
        char_4 = char_first

        context = {
            "event": self.event,
            "run": self.run,
            "features": {},
        }

        casting_characters(context, self.registration)

        # Parse the choices JSON to verify ordering
        import json

        choices = json.loads(context["choices"])

        # Get all character UUIDs in order they appear (now using UUID strings)
        character_uuids = []
        for faction_name, faction_chars in choices.items():
            for char_uuid in faction_chars.keys():
                character_uuids.append(char_uuid)

        # Verify the characters are in the correct order (by their numbers)
        char_4_index = character_uuids.index(str(char_4.uuid))
        char_7_index = character_uuids.index(str(char_7.uuid))
        char_10_index = character_uuids.index(str(char_10.uuid))

        self.assertLess(char_4_index, char_7_index, "Character with number=4 should come before number=7")
        self.assertLess(char_7_index, char_10_index, "Character with number=7 should come before number=10")


    def test_valid_element_ids_type(self):
        """Test that valid_element_ids is a set"""
        context = {
            "event": self.event,
            "run": self.run,
            "features": {},
        }

        casting_characters(context, self.registration)

        self.assertIsInstance(context["valid_element_ids"], set, "valid_element_ids should be a set")

    def test_casting_characters_empty_when_all_hidden(self):
        """Test that valid_element_ids is empty when all characters are hidden"""
        # Hide all characters for this event (including any from previous tests)
        from larpmanager.models.writing import Character

        Character.objects.filter(event=self.event).update(hide=True)

        context = {
            "event": self.event,
            "run": self.run,
            "features": {},
        }

        casting_characters(context, self.registration)

        valid_ids = context["valid_element_ids"]

        # Should have no valid IDs since all are hidden
        self.assertEqual(len(valid_ids), 0, "Should have no valid IDs when all characters are hidden")
