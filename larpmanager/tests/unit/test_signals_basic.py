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

"""Basic signal tests that verify signals fire without errors"""

from decimal import Decimal

from django.core.cache import cache

from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemOther,
    AccountingItemPayment,
    OtherChoices,
    PaymentChoices,
)
from larpmanager.models.writing import Character
from larpmanager.tests.unit.base import BaseTestCase


class TestBasicSignals(BaseTestCase):
    """Test basic signal functionality without mocking"""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()

    def test_member_save_signal(self) -> None:
        """Test that Member save operations work correctly"""
        # Create a fresh member using BaseTestCase helper that avoids conflicts
        member = self.get_member()

        # Update and save to trigger signal
        member.name = "Updated"
        member.save()

        # Verify saved correctly
        self.assertIsNotNone(member.id)
        self.assertEqual(member.name, "Updated")

    def test_character_save_signal(self) -> None:
        """Test that Character save operations work correctly"""
        character = self.character()

        # Should not raise exception
        character.save()

        # Verify saved correctly
        self.assertIsNotNone(character.id)

    def test_character_delete_signal(self) -> None:
        """Test that Character delete operations work correctly"""
        character = self.character()
        character.save()
        character_id = character.id

        # Should not raise exception
        character.delete()

        # Verify deleted correctly
        with self.assertRaises(Character.DoesNotExist):
            Character.objects.get(id=character_id)

    def test_accounting_payment_save_signal(self) -> None:
        """Test that AccountingItemPayment save operations work correctly"""
        member = self.get_member()
        registration = self.get_registration()

        payment = AccountingItemPayment(
            member=member,
            value=Decimal("50.00"),
            association=self.get_association(),
            registration=registration,
            pay=PaymentChoices.MONEY,
        )

        # Should not raise exception
        payment.save()

        # Verify saved correctly
        self.assertIsNotNone(payment.id)
        self.assertEqual(payment.value, Decimal("50.00"))

    def test_accounting_payment_delete_signal(self) -> None:
        """Test that AccountingItemPayment delete operations work correctly"""
        member = self.get_member()
        registration = self.get_registration()

        payment = AccountingItemPayment.objects.create(
            member=member,
            value=Decimal("50.00"),
            association=self.get_association(),
            registration=registration,
            pay=PaymentChoices.MONEY,
        )
        payment_id = payment.id

        # Should not raise exception
        payment.delete()

        # Verify deleted correctly
        self.assertFalse(AccountingItemPayment.objects.filter(id=payment_id).exists())

    def test_accounting_discount_save_signal(self) -> None:
        """Test that AccountingItemDiscount save operations work correctly"""
        member = self.get_member()
        discount = self.discount()

        item = AccountingItemDiscount(
            member=member,
            value=Decimal("10.00"),
            association=self.get_association(),
            disc=discount,  # Changed from 'discount' to 'disc'
            run=self.get_run(),
        )

        # Should not raise exception
        item.save()

        # Verify saved correctly
        self.assertIsNotNone(item.id)
        self.assertEqual(item.value, Decimal("10.00"))

    def test_accounting_other_save_signal(self) -> None:
        """Test that AccountingItemOther save operations work correctly"""
        member = self.get_member()

        item = AccountingItemOther(
            member=member,
            value=Decimal("25.00"),
            association=self.get_association(),
            run=self.get_run(),
            oth=OtherChoices.CREDIT,  # Changed from AccountingItemOther.CREDIT to OtherChoices.CREDIT
            descr="Test credit",  # Added required descr field
        )

        # Should not raise exception
        item.save()

        # Verify saved correctly
        self.assertIsNotNone(item.id)
        self.assertEqual(item.value, Decimal("25.00"))

    def test_registration_save_signal(self) -> None:
        """Test that Registration save operations work correctly"""
        registration = self.get_registration()

        # Should not raise exception
        registration.save()

        # Verify saved correctly
        self.assertIsNotNone(registration.id)

    def test_event_save_signal(self) -> None:
        """Test that Event save operations work correctly"""
        event = self.get_event()

        # Should not raise exception
        event.save()

        # Verify saved correctly
        self.assertIsNotNone(event.id)

    def test_signal_chain_integration(self) -> None:
        """Test that multiple related signals work together"""
        # Create a chain of related objects
        member = self.get_member()
        registration = self.get_registration()
        character = self.character()

        # All operations should work without errors
        member.save()
        registration.save()
        character.save()

        # Create accounting item that references all
        payment = AccountingItemPayment(
            member=member,
            value=Decimal("100.00"),
            association=self.get_association(),
            registration=registration,
            pay=PaymentChoices.MONEY,
        )
        payment.save()

        # All objects should be properly created
        self.assertIsNotNone(member.id)
        self.assertIsNotNone(registration.id)
        self.assertIsNotNone(character.id)
        self.assertIsNotNone(payment.id)

        # Relationships should be preserved
        self.assertEqual(payment.member, member)
        self.assertEqual(payment.registration, registration)

    def test_cache_operations_dont_break(self) -> None:
        """Test that cache operations triggered by signals don't break"""
        # Create various objects that should trigger cache updates
        member = self.get_member()
        event = self.get_event()
        registration = self.get_registration()

        # All saves should work without cache errors
        member.save()
        event.save()
        registration.save()

        # Cache should still be functional
        cache.set("test_key", "test_value")
        self.assertEqual(cache.get("test_key"), "test_value")
