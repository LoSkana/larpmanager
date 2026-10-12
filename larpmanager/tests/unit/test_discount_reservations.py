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

"""Tests for discount reservations kept in cache and their effect on discount limits"""

from decimal import Decimal

from django.core.cache import cache

from larpmanager.cache.discount import (
    clear_member_reservation,
    count_discounts_reservations,
    get_member_reservations,
    reserve_discount,
)
from larpmanager.models.accounting import AccountingItemDiscount, Discount, DiscountType
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.registrations.discount import _check_discount, count_discount_redemptions


class TestDiscountReservations(BaseTestCase):
    """Test discount reservations and redemption limits"""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.run = self.get_run()
        self.member = self.get_member()
        self.other_member = self.create_member(self.create_user(username="other", email="other@example.com"))
        self.disc = Discount.objects.create(
            name="Limited",
            value=Decimal("10.00"),
            max_redeem=1,
            typ=DiscountType.STANDARD,
            event=self.run.event,
            number=99,
            only_reg=False,
        )
        self.disc.runs.add(self.run)

    def test_reserve_and_clear(self) -> None:
        """Test reservations are listed per member and removed on clear"""
        reserve_discount(self.run.id, self.disc.id, self.member.id)

        self.assertIn(self.disc.id, get_member_reservations(self.run.id, [self.disc.id], self.member.id))
        self.assertEqual(get_member_reservations(self.run.id, [self.disc.id], self.other_member.id), {})
        self.assertEqual(count_discounts_reservations(self.run.id, [self.disc.id]), {self.disc.id: 1})

        clear_member_reservation(self.run.id, self.disc.id, self.member.id)

        self.assertEqual(count_discounts_reservations(self.run.id, [self.disc.id]), {})

    def test_redemptions_count_confirmed_and_reserved(self) -> None:
        """Test redemptions include confirmed items and reservations of other members"""
        registration = self.create_registration(member=self.member, run=self.run)
        AccountingItemDiscount.objects.create(
            registration=registration,
            disc=self.disc,
            value=self.disc.value,
            association=self.get_association(),
        )
        reserve_discount(self.run.id, self.disc.id, self.other_member.id)

        self.assertEqual(count_discount_redemptions(self.disc, self.run), 2)
        self.assertEqual(count_discount_redemptions(self.disc, self.run, self.other_member.id), 1)

    def test_reservation_blocks_other_member_at_limit(self) -> None:
        """Test a reservation consumes the last slot for other members"""
        self.assertIsNone(_check_discount(self.disc, self.other_member, self.run, self.run.event))

        reserve_discount(self.run.id, self.disc.id, self.member.id)

        self.assertIsNotNone(_check_discount(self.disc, self.other_member, self.run, self.run.event))
        self.assertIsNotNone(_check_discount(self.disc, self.member, self.run, self.run.event))
