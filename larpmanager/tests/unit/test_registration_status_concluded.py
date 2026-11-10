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

"""Tests for the registration status of concluded and cancelled runs."""

import datetime as dt

from django.utils import timezone

from larpmanager.models.event import DevelopStatus, RegistrationStatus
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.registrations.status import registration_status


class TestRegistrationStatusConcluded(BaseTestCase):
    """Test cases for runs that no longer accept registrations."""

    def _status_for(self, development: str) -> dict:
        run = self.get_run()
        run.development = development
        run.registration_status = RegistrationStatus.OPEN
        run.end = timezone.localdate() + dt.timedelta(days=30)
        run.save()
        return registration_status({}, run, None)

    def test_visible_run_is_open(self) -> None:
        """Test a visible run with open registrations accepts registrations."""
        self.assertTrue(self._status_for(DevelopStatus.SHOW)["open"])

    def test_concluded_run_is_closed(self) -> None:
        """Test a concluded run with a future end date accepts no registrations."""
        status = self._status_for(DevelopStatus.DONE)

        self.assertFalse(status["open"])
        self.assertEqual(status["text_long"], "This event has concluded")

    def test_cancelled_run_is_closed(self) -> None:
        """Test a cancelled run accepts no registrations."""
        status = self._status_for(DevelopStatus.CANC)

        self.assertFalse(status["open"])
        self.assertEqual(status["text_long"], "This event has been cancelled")
