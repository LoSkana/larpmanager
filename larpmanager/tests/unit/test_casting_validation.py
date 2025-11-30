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
from django.test import Client
from django.urls import reverse

from larpmanager.models.access import Feature
from larpmanager.models.casting import Casting
from larpmanager.models.registration import RegistrationTicket, TicketTier
from larpmanager.tests.unit.base import BaseTestCase


@pytest.mark.django_db
class TestCastingValidation(BaseTestCase):
    """Test casting validation prevents hidden character selection"""

    def setUp(self):
        """Set up test data"""
        super().setUp()
        self.client = Client()

        # Create event with slug - this automatically creates a Run with number=1
        association = self.get_association()
        self.event = self.create_event(association=association, slug="test-event")
        # Get the automatically created run
        self.run = self.event.runs.first()
        self.member = self.get_member()
        self.registration = self.create_registration(member=self.member, run=self.run)

        # Create a standard ticket and assign to registration
        self.ticket = self.ticket(event=self.event, tier=TicketTier.STANDARD)
        self.registration.ticket = self.ticket
        self.registration.save()

        # Enable casting feature
        casting_feature, _ = Feature.objects.get_or_create(
            name="casting", defaults={"overall": False, "slug": "casting", "order": 100}
        )
        self.event.features.add(casting_feature)

        # Create characters
        self.visible_char1 = self.character(event=self.event, name="Visible Character 1", hide=False, number=1)
        self.visible_char2 = self.character(event=self.event, name="Visible Character 2", hide=False, number=2)
        self.hidden_char = self.character(event=self.event, name="Hidden Character", hide=True, number=3)

        # Login the user
        self.client.force_login(self.member.user)

    def test_cannot_select_hidden_character(self):
        """Test that POST request with hidden character ID is rejected"""
        url = reverse("casting", kwargs={"event_slug": self.event.slug, "casting_type": 0})

        # Try to submit casting preferences with a hidden character
        response = self.client.post(
            url,
            {
                "choice0": str(self.visible_char1.id),
                "choice1": str(self.hidden_char.id),  # This should be rejected
            },
        )

        # Should redirect back to the form
        self.assertEqual(response.status_code, 302)

        # No casting preferences should be saved
        casting_count = Casting.objects.filter(run=self.run, member=self.member).count()
        self.assertEqual(casting_count, 0, "Hidden character casting should not be saved")

    def test_can_select_visible_characters(self):
        """Test that POST request with only visible characters works"""
        url = reverse("casting", kwargs={"event_slug": self.event.slug, "casting_type": 0})

        # Submit casting preferences with only visible characters
        response = self.client.post(
            url,
            {
                "choice0": str(self.visible_char1.id),
                "choice1": str(self.visible_char2.id),
            },
        )

        # Debug output
        if response.status_code != 302:
            print(f"Response status: {response.status_code}")
            print(f"Response content: {response.content[:500]}")

        # Should redirect back to the form (success)
        self.assertEqual(response.status_code, 302)

        # Two casting preferences should be saved
        casting_count = Casting.objects.filter(run=self.run, member=self.member).count()
        self.assertEqual(casting_count, 2, "Should save visible character castings")

        # Verify the correct characters were saved
        castings = Casting.objects.filter(run=self.run, member=self.member).order_by("pref")
        self.assertEqual(castings[0].element, self.visible_char1.id)
        self.assertEqual(castings[1].element, self.visible_char2.id)

    def test_hidden_character_not_in_context(self):
        """Test that hidden characters don't appear in the context"""
        url = reverse("casting", kwargs={"event_slug": self.event.slug, "casting_type": 0})

        # GET request to load the form
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check that valid_element_ids doesn't contain the hidden character
        valid_ids = response.context.get("valid_element_ids", set())
        self.assertNotIn(self.hidden_char.id, valid_ids, "Hidden character should not be in valid IDs")
        self.assertIn(self.visible_char1.id, valid_ids, "Visible character should be in valid IDs")
        self.assertIn(self.visible_char2.id, valid_ids, "Visible character should be in valid IDs")

    def test_character_becomes_hidden_after_selection(self):
        """Test that if a character becomes hidden after being selected, it remains in preferences"""
        url = reverse("casting", kwargs={"event_slug": self.event.slug, "casting_type": 0})

        # First, select visible characters
        self.client.post(
            url,
            {
                "choice0": str(self.visible_char1.id),
                "choice1": str(self.visible_char2.id),
            },
        )

        # Verify selections were saved
        casting_count = Casting.objects.filter(run=self.run, member=self.member).count()
        self.assertEqual(casting_count, 2)

        # Now hide one of the selected characters
        self.visible_char1.hide = True
        self.visible_char1.save()

        # Try to update preferences - should still work with remaining visible characters
        # But cannot add the now-hidden character again
        response = self.client.post(
            url,
            {
                "choice0": str(self.visible_char2.id),
            },
        )

        self.assertEqual(response.status_code, 302)

        # Should now have only 1 casting (the visible one)
        casting_count = Casting.objects.filter(run=self.run, member=self.member).count()
        self.assertEqual(casting_count, 1)

    def test_invalid_character_id(self):
        """Test that completely invalid character IDs are rejected"""
        url = reverse("casting", kwargs={"event_slug": self.event.slug, "casting_type": 0})

        # Try to submit with a non-existent character ID
        response = self.client.post(
            url,
            {
                "choice0": "99999",  # Non-existent ID
            },
        )

        # Should redirect back to the form
        self.assertEqual(response.status_code, 302)

        # No casting preferences should be saved
        casting_count = Casting.objects.filter(run=self.run, member=self.member).count()
        self.assertEqual(casting_count, 0, "Invalid character ID should not be saved")
