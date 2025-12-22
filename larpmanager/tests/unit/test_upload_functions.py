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

"""Tests for upload utility functions"""

from larpmanager.models.writing import Character
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.io.upload import element_load


class TestUploadFunctions(BaseTestCase):
    """Test cases for upload utility functions"""

    def test_element_load_character_without_campaign(self) -> None:
        """Test that characters are loaded in the event when no parent exists"""
        # Create event without parent
        event = self.create_event(name="Standalone Event", slug="standalone")
        member = self.get_member()

        # Prepare context for character upload
        context = {
            "event": event,
            "typ": "character",
            "field_name": "name",
            "fields": {"name": "name"},
            "member": member,
        }

        # Prepare CSV row data
        csv_row = {"name": "Test Character"}

        # Load character
        result = element_load(context, csv_row, {})

        # Verify character was created successfully
        self.assertIn("OK", result)
        self.assertIn("Test Character", result)

        # Verify character exists in the event
        character = Character.objects.get(name="Test Character")
        self.assertEqual(character.event, event)

    def test_element_load_character_with_campaign(self) -> None:
        """Test that characters are loaded in parent event when event is part of campaign"""
        # Create parent event (campaign)
        parent_event = self.create_event(name="Campaign", slug="campaign")

        # Create child event with parent
        child_event = self.create_event(name="Campaign Chapter 1", slug="campaign-ch1", parent=parent_event)

        member = self.get_member()

        # Prepare context for character upload to child event
        context = {
            "event": child_event,
            "typ": "character",
            "field_name": "name",
            "fields": {"name": "name"},
            "member": member,
        }

        # Prepare CSV row data
        csv_row = {"name": "Campaign Character"}

        # Load character
        result = element_load(context, csv_row, {})

        # Verify character was created successfully
        self.assertIn("OK", result)
        self.assertIn("Campaign Character", result)

        # Verify character exists in the PARENT event, not the child
        character = Character.objects.get(name="Campaign Character")
        self.assertEqual(character.event, parent_event)
        self.assertNotEqual(character.event, child_event)

    def test_element_load_character_campaign_with_independence(self) -> None:
        """Test that characters are loaded in child event when campaign independence is enabled"""
        from larpmanager.models.event import EventConfig

        # Create parent event (campaign)
        parent_event = self.create_event(name="Campaign", slug="campaign")

        # Create child event with parent
        child_event = self.create_event(name="Campaign Chapter 1", slug="campaign-ch1", parent=parent_event)

        # Enable campaign character independence for child event
        EventConfig.objects.create(event=child_event, name="campaign_character_indep", value="True")

        member = self.get_member()

        # Prepare context for character upload to child event
        context = {
            "event": child_event,
            "typ": "character",
            "field_name": "name",
            "fields": {"name": "name"},
            "member": member,
        }

        # Prepare CSV row data
        csv_row = {"name": "Independent Character"}

        # Load character
        result = element_load(context, csv_row, {})

        # Verify character was created successfully
        self.assertIn("OK", result)
        self.assertIn("Independent Character", result)

        # Verify character exists in the CHILD event due to independence setting
        character = Character.objects.get(name="Independent Character")
        self.assertEqual(character.event, child_event)
        self.assertNotEqual(character.event, parent_event)

    def test_element_load_character_update_in_campaign(self) -> None:
        """Test that updating a character in campaign updates the parent event character"""
        # Create parent event (campaign)
        parent_event = self.create_event(name="Campaign", slug="campaign")

        # Create child event with parent
        child_event = self.create_event(name="Campaign Chapter 1", slug="campaign-ch1", parent=parent_event)

        # Create existing character in parent event
        existing_character = self.character(event=parent_event, name="Existing Character", teaser="Old teaser")

        member = self.get_member()

        # Prepare context for character upload to child event
        context = {
            "event": child_event,
            "typ": "character",
            "field_name": "name",
            "fields": {"name": "name", "teaser": "teaser"},
            "member": member,
        }

        # Prepare CSV row data with updated teaser
        csv_row = {"name": "Existing Character", "teaser": "New teaser"}

        # Load character (should update existing one)
        result = element_load(context, csv_row, {})

        # Verify character was updated successfully
        self.assertIn("OK", result)
        self.assertIn("Updated", result)

        # Verify character was updated in parent event
        existing_character.refresh_from_db()
        self.assertEqual(existing_character.teaser, "New teaser")
        self.assertEqual(existing_character.event, parent_event)
