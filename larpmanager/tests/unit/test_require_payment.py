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
"""Tests for the require_payment event config, blocking characters until a payment is made."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from larpmanager.accounting.base import is_registration_payment_pending
from larpmanager.models.accounting import PaymentChoices, PaymentInvoice, PaymentStatus, PaymentType
from larpmanager.models.base import PaymentMethod
from larpmanager.tests.unit.base import BaseTestCase


def _config(*, require_payment: bool) -> Any:
    """Return a get_event_config replacement with the given require_payment value."""

    def get_config(_event_id: int, name: str, **_kwargs: Any) -> Any:
        return require_payment if name == "require_payment" else False

    return get_config


@patch("larpmanager.accounting.base.get_event_features", return_value={"payment": True})
class TestRequirePayment(BaseTestCase):
    """Test cases for is_registration_payment_pending."""

    def _registration(self, tot_iscr: Decimal = Decimal("100.00")) -> Any:
        """Create a registration with the given price, each for a new member."""
        self._count = getattr(self, "_count", 0) + 1
        user = self.create_user(username=f"payer{self._count}", email=f"payer{self._count}@example.com")
        registration = self.create_registration(member=self.create_member(user=user))
        registration.tot_iscr = tot_iscr
        return registration

    def _check(self, registration: Any, *, require_payment: bool = True) -> bool:
        """Run the check with the require_payment config set."""
        with patch(
            "larpmanager.accounting.base.get_event_config", side_effect=_config(require_payment=require_payment)
        ):
            return is_registration_payment_pending(registration, event_id=registration.run.event_id)

    def _invoice(self, registration: Any, status: str, cod: str) -> None:
        """Create a registration invoice with the given status."""
        PaymentInvoice.objects.create(
            member=registration.member,
            association=self.get_association(),
            method=PaymentMethod.objects.get_or_create(slug="wire", defaults={"name": "Wire", "fields": ""})[0],
            typ=PaymentType.REGISTRATION,
            idx=registration.id,
            registration=registration,
            status=status,
            mc_gross=Decimal("100.00"),
            causal="Test payment",
            cod=cod,
        )

    def test_config_disabled(self, _mock_features: Any) -> None:
        """Without the config nothing is blocked."""
        self.assertFalse(self._check(self._registration(), require_payment=False))

    def test_no_payment_feature(self, mock_features: Any) -> None:
        """Without the payment feature nothing is blocked."""
        mock_features.return_value = {}
        self.assertFalse(self._check(self._registration()))

    def test_unpaid_registration(self, _mock_features: Any) -> None:
        """A registration with a price and no payment is blocked."""
        self.assertTrue(self._check(self._registration()))

    def test_free_registration(self, _mock_features: Any) -> None:
        """A free registration is never blocked."""
        self.assertFalse(self._check(self._registration(tot_iscr=Decimal("0.00"))))

    def test_created_invoice(self, _mock_features: Any) -> None:
        """An invoice only created (abandoned checkout) does not unlock the registration."""
        registration = self._registration()
        self._invoice(registration, PaymentStatus.CREATED, "CREATED1")
        self.assertTrue(self._check(registration))

    def test_paid_invoice_statuses(self, _mock_features: Any) -> None:
        """A submitted, confirmed or checked invoice unlocks the registration."""
        for status in [PaymentStatus.SUBMITTED, PaymentStatus.CONFIRMED, PaymentStatus.CHECKED]:
            registration = self._registration()
            self._invoice(registration, status, f"INV{status}")
            self.assertFalse(self._check(registration), status)

    def test_deleted_invoice(self, _mock_features: Any) -> None:
        """A deleted invoice blocks the registration again."""
        registration = self._registration()
        registration.run.start = date.today()
        registration.run.save()
        self._invoice(registration, PaymentStatus.SUBMITTED, "DELETED1")
        registration.invoices.first().delete()
        self.assertTrue(self._check(registration))

    def test_payment_items(self, _mock_features: Any) -> None:
        """Any payment item (money, tokens, credits) unlocks the registration."""
        for pay in [PaymentChoices.MONEY, PaymentChoices.TOKEN, PaymentChoices.CREDIT]:
            registration = self._registration()
            self.payment_item(member=registration.member, registration=registration, pay=pay).save()
            registration.tot_iscr = Decimal("100.00")
            self.assertFalse(self._check(registration), pay)
