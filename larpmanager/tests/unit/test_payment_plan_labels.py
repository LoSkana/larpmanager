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

"""Tests for the amounts and currency shown by payment plans."""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from django.template.loader import render_to_string
from django.utils import timezone

from larpmanager.forms.registration import RegistrationForm
from larpmanager.models.registration import RegistrationQuota
from larpmanager.tests.unit.base import BaseTestCase


class TestPaymentPlanLabels(BaseTestCase):
    """Test the labels of instalments and dynamic rates."""

    def _render_next_payment(self, deadline: int) -> str:
        registration = SimpleNamespace(
            uuid=str(uuid4()), tot_iscr=Decimal(140), tot_payed=Decimal(0), quota=Decimal(40), deadline=deadline
        )
        return render_to_string(
            "elements/reg_status.html",
            {
                "run_status": {"text": "Provisional", "registration": registration},
                "registration": registration,
                "reg_uuid": "",
                "long_text": False,
                "pending_invoices": False,
                "membership_fee": "",
                "features": {"payment": True},
                "currency_symbol": "$",
            },
        )

    def test_next_payment_due_shows_amount(self) -> None:
        """Test a payment due in the future shows its amount and currency."""
        self.assertIn("Next payment: 40$ expected within 7 days", self._render_next_payment(7))

    def test_next_payment_overdue_shows_amount(self) -> None:
        """Test an overdue payment shows its amount and currency."""
        self.assertIn("Next payment: 40$ overdue by 5 days", self._render_next_payment(-5))

    def test_quota_surcharge_uses_event_currency(self) -> None:
        """Test the surcharge of a dynamic rate is labelled with the currency of the event."""
        event = self.get_event()
        run = self.get_run()
        run.end = timezone.localdate() + dt.timedelta(days=90)
        run.save()
        RegistrationQuota.objects.create(event=event, number=1, quotas=1, days_available=0)
        RegistrationQuota.objects.create(event=event, number=2, quotas=2, days_available=0, surcharge=10)
        registration = self.create_registration(member=self.get_member(), run=run)
        context = {
            "event": event,
            "run": run,
            "member": self.get_member(),
            "currency_symbol": "$",
            "features": ["reg_quotas"],
        }

        form = RegistrationForm(context=context, instance=registration)

        self.assertIn((2, "Two (10$)"), [(int(value), str(label)) for value, label in form.fields["quotas"].choices])
