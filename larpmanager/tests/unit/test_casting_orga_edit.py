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

"""Tests for organizer edit of participant casting preferences"""

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.test import RequestFactory

from larpmanager.models.casting import Casting, CastingAvoid
from larpmanager.models.miscellanea import Log
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.views.orga.casting import _casting_edit_save
from larpmanager.views.user.casting import extract_casting_preferences


@pytest.mark.django_db(transaction=True)
class TestCastingOrgaEdit(BaseTestCase):
    """Test organizer saving of participant casting preferences"""

    def setUp(self):
        """Set up test data"""
        super().setUp()
        self.event = self.get_event()
        self.run = self.get_run()
        self.player = self.create_member()
        self.orga = self.get_member()
        self.registration = self.create_registration(member=self.player, run=self.run)
        self.registration.ticket = self.ticket(event=self.event, tier=TicketTier.STANDARD)
        self.registration.save()

        self.char_old = self.character(event=self.event, name="Old Character")
        self.char_new1 = self.character(event=self.event, name="New Character One")
        self.char_new2 = self.character(event=self.event, name="New Character Two")
        Casting.objects.create(run=self.run, member=self.player, typ=0, element=str(self.char_old.uuid), pref=0)
        CastingAvoid.objects.create(run=self.run, member=self.player, typ=0, text="old avoid")

    def _context(self):
        return {
            "event": self.event,
            "run": self.run,
            "member": self.orga,
            "association_id": self.event.association_id,
            "features": {},
            "gl_name": "Characters",
            "casting_avoid": True,
            "casting_min": 3,
            "casting_max": 3,
            "avoid": "old avoid",
            "valid_element_ids": {str(self.char_new1.uuid), str(self.char_new2.uuid)},
        }

    def _request(self, data):
        request = RequestFactory().post("/", data)
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_save_replaces_preferences_and_logs(self):
        """Saving replaces preferences and avoidance, logs the changes and sends no email"""
        context = self._context()
        request = self._request(
            {"choice0": str(self.char_new2.uuid), "choice1": str(self.char_new1.uuid), "avoid": "new avoid"}
        )

        prefs = extract_casting_preferences(request, context, enforce_min=False)
        self.assertIsNotNone(prefs)
        _casting_edit_save(request, context, self.registration, prefs)

        saved = list(
            Casting.objects.filter(run=self.run, member=self.player, typ=0).order_by("pref").values_list(
                "element", flat=True
            )
        )
        self.assertEqual(saved, [str(self.char_new2.uuid), str(self.char_new1.uuid)])
        self.assertEqual(CastingAvoid.objects.get(run=self.run, member=self.player, typ=0).text, "new avoid")
        self.assertEqual(len(mail.outbox), 0)

        log = Log.objects.get(cls=Registration.__name__, eid=self.registration.id)
        self.assertEqual(log.member, self.orga)
        self.assertIn("Old Character", log.info)
        self.assertIn("New Character Two, New Character One", log.info)
        self.assertIn("'old avoid' -> 'new avoid'", log.info)

    def test_extract_without_min_allows_fewer_preferences(self):
        """Organizer extraction ignores the minimum, participant extraction enforces it"""
        context = self._context()
        data = {"choice0": str(self.char_new1.uuid)}

        self.assertIsNotNone(extract_casting_preferences(self._request(data), context, enforce_min=False))
        self.assertIsNone(extract_casting_preferences(self._request(data), context, enforce_min=True))

    def test_extract_rejects_invalid_element(self):
        """Elements not in the valid list are rejected"""
        context = self._context()
        request = self._request({"choice0": str(self.char_old.uuid)})

        self.assertIsNone(extract_casting_preferences(request, context, enforce_min=False))
