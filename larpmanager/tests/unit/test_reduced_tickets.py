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

"""Tests for patron / reduced ticket availability."""

from decimal import Decimal
from typing import Any
from unittest.mock import patch

from larpmanager.models.event import EventConfig
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.registrations.signals import get_reduced_available_count


class TestReducedAvailableCount(BaseTestCase):
    """Test cases for reduced ticket availability."""

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_unpaid_patron_counted_only_with_config(self, mock_mail: Any) -> None:
        """Unpaid patron tickets count in the ratio only when reduced_unpaid is enabled."""
        run = self.get_run()
        patron = self.ticket(event=run.event, name="Patron", tier=TicketTier.PATRON, price=Decimal("150.00"))
        registration = self.create_registration(run=run, ticket=patron)
        Registration.objects.filter(pk=registration.pk).update(tot_payed=Decimal(0))

        self.assertEqual(get_reduced_available_count(run), 0)

        EventConfig.objects.create(event=run.event, name="reduced_unpaid", value="True")
        self.assertEqual(get_reduced_available_count(run), 1)

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_paid_patron_always_counted(self, mock_mail: Any) -> None:
        """Paid patron tickets count in the ratio regardless of reduced_unpaid."""
        run = self.get_run()
        patron = self.ticket(event=run.event, name="Patron", tier=TicketTier.PATRON, price=Decimal("150.00"))
        registration = self.create_registration(run=run, ticket=patron)
        Registration.objects.filter(pk=registration.pk).update(tot_payed=Decimal("50.00"))

        self.assertEqual(get_reduced_available_count(run), 1)
