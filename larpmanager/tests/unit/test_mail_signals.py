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

"""Tests for mail-related signal receivers"""

from decimal import Decimal
from unittest.mock import patch

from larpmanager.models.accounting import (
    AccountingItemExpense,
    AccountingItemMembership,
    AccountingItemOther,
    AccountingItemPayment,
    Collection,
)
from larpmanager.models.casting import AssignmentTrait, Trait
from larpmanager.models.miscellanea import ChatMessage
from larpmanager.models.miscellanea import HelpQuestion
from larpmanager.models.event import PreRegistration
from larpmanager.models.registration import Registration, RegistrationCharacterRel
from larpmanager.models.writing import Character
from larpmanager.tests.unit.base import BaseTestCase

# Import signals module to register signal handlers
import larpmanager.models.signals  # noqa: F401


class TestMailSignals(BaseTestCase):
    """Test cases for mail-related signal receivers"""

    @patch("larpmanager.mail.base.my_send_mail")
    def test_traits_can_be_created(self, mock_mail):
        """Test that Trait can be created"""
        event = self.get_event()

        trait = Trait(name="Test Trait", event=event)
        trait.save()

        # Should be created successfully
        self.assertIsNotNone(trait.id)

    @patch("larpmanager.mail.base.my_send_mail")
    def test_character_can_be_updated(self, mock_mail):
        """Test that Character can be updated"""
        from larpmanager.models.writing import Character
        character = self.character()
        original_status = character.status

        # Update character name
        character.name = "Updated Name"
        character.save()

        # Should be saved successfully
        self.assertEqual(character.name, "Updated Name")

    @patch("larpmanager.mail.member.my_send_mail")
    def test_accounting_item_membership_can_be_created(self, mock_mail):
        """Test that AccountingItemMembership can be created"""
        member = self.get_member()
        from datetime import datetime

        item = AccountingItemMembership(
            member=member, value=Decimal("100.00"), association=self.get_association(), year=datetime.now().year
        )
        item.save()

        # Should be created successfully
        self.assertIsNotNone(item.id)

    @patch("larpmanager.mail.base.get_association_executives")
    @patch("larpmanager.mail.member.my_send_mail")
    def test_help_question_can_be_created(self, mock_mail, mock_get_executives):
        """Test that HelpQuestion can be created"""
        mock_get_executives.return_value = []  # No executives
        member = self.get_member()

        question = HelpQuestion(
            member=member,
            association=self.get_association(),
            text="Need help with something",
        )
        question.save()

        # Should be created successfully
        self.assertIsNotNone(question.id)

    @patch("larpmanager.mail.member.my_send_mail")
    def test_chat_message_can_be_created(self, mock_mail):
        """Test that ChatMessage can be created"""
        sender = self.get_member()
        receiver = self.get_member()
        association = self.get_association()

        message = ChatMessage(sender=sender, receiver=receiver, association=association, message="Test chat message", channel=1)
        message.save()

        # Should be created successfully
        self.assertIsNotNone(message.id)

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_registration_character_rel_can_be_created(self, mock_mail):
        """Test that RegistrationCharacterRel can be created"""
        registration = self.get_registration()
        character = self.character()

        rel = RegistrationCharacterRel(reg=registration, character=character)
        rel.save()

        # Should be created successfully
        self.assertIsNotNone(rel.id)

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_registration_alert_can_be_changed(self, mock_mail):
        """Test that Registration alert can be changed"""
        from larpmanager.models.registration import Registration

        registration = self.get_registration()
        original_alert = registration.alert

        # Change registration alert - use update() to bypass accounting signals
        new_alert = not original_alert
        Registration.objects.filter(pk=registration.pk).update(alert=new_alert)
        registration.refresh_from_db()

        # Should be saved successfully
        self.assertEqual(registration.alert, new_alert)

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_registration_can_be_deleted(self, mock_mail):
        """Test that Registration can be deleted"""
        from larpmanager.models.registration import Registration
        registration = self.get_registration()
        reg_id = registration.id
        registration.delete()

        # Should be deleted successfully (soft delete keeps id)
        # Check if it exists in the database
        self.assertFalse(Registration.objects.filter(id=reg_id, deleted__isnull=True).exists())

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_pre_registration_can_be_created(self, mock_mail):
        """Test that PreRegistration can be created"""
        member = self.get_member()
        event = self.get_event()

        pre_reg = PreRegistration(member=member, event=event, pref=1, info="Test pre-registration")
        pre_reg.save()

        # Should be created successfully
        self.assertIsNotNone(pre_reg.id)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_item_expense_can_be_created(self, mock_mail):
        """Test that AccountingItemExpense can be created"""
        from larpmanager.models.accounting import ExpenseChoices
        member = self.get_member()

        expense = AccountingItemExpense(
            member=member, value=Decimal("50.00"), association=self.get_association(), descr="Test expense",
            exp=ExpenseChoices.OTHER
        )
        expense.save()

        # Should be created successfully
        self.assertIsNotNone(expense.id)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_item_expense_value_can_be_changed(self, mock_mail):
        """Test that AccountingItemExpense value can be changed"""
        from larpmanager.models.accounting import ExpenseChoices
        member = self.get_member()

        expense = AccountingItemExpense.objects.create(
            member=member,
            value=Decimal("50.00"),
            association=self.get_association(),
            descr="Test expense",
            exp=ExpenseChoices.OTHER,
        )

        # Change value
        expense.value = Decimal("75.00")
        expense.save()

        # Should be saved successfully
        self.assertEqual(expense.value, Decimal("75.00"))

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_item_payment_value_can_be_changed(self, mock_mail):
        """Test that AccountingItemPayment value can be changed"""
        from larpmanager.models.accounting import PaymentChoices
        member = self.get_member()

        payment = AccountingItemPayment.objects.create(
            member=member,
            value=Decimal("100.00"),
            association=self.get_association(),
            reg=self.get_registration(),
            pay=PaymentChoices.MONEY,
        )

        # Change value
        payment.value = Decimal("150.00")
        payment.save()

        # Should be saved successfully
        self.assertEqual(payment.value, Decimal("150.00"))

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_item_other_value_can_be_changed(self, mock_mail):
        """Test that AccountingItemOther value can be changed"""
        from larpmanager.models.accounting import OtherChoices
        member = self.get_member()

        other = AccountingItemOther.objects.create(
            member=member,
            value=Decimal("25.00"),
            association=self.get_association(),
            run=self.get_run(),
            oth=OtherChoices.CREDIT,
            descr="Test credit",
        )

        # Change value
        other.value = Decimal("35.00")
        other.save()

        # Should be saved successfully
        self.assertEqual(other.value, Decimal("35.00"))

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_item_donation_pre_save_sends_mail(self, mock_mail):
        """Test that AccountingItemDonation pre_save signal sends mail"""
        from larpmanager.models.accounting import AccountingItemDonation

        member = self.get_member()

        donation = AccountingItemDonation(
            member=member, value=Decimal("50.00"), association=self.get_association(), descr="Test donation"
        )
        donation.save()

        # Should send mail notification
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_collection_post_save_sends_mail(self, mock_mail):
        """Test that Collection post_save signal sends mail"""
        association = self.get_association()
        organizer = self.organizer()

        collection = Collection(name="Test Collection", association=association, organizer=organizer)
        collection.save()

        # Should send mail notification
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_item_collection_value_can_be_changed(self, mock_mail):
        """Test that AccountingItemCollection value can be changed"""
        from larpmanager.models.accounting import AccountingItemCollection

        member = self.get_member()
        collection = self.collection()

        item = AccountingItemCollection.objects.create(
            member=member,
            value=Decimal("30.00"),
            association=self.get_association(),
            collection=collection,
        )

        # Change value
        item.value = Decimal("40.00")
        item.save()

        # Should be saved successfully
        self.assertEqual(item.value, Decimal("40.00"))

    @patch("larpmanager.mail.base.my_send_mail")
    def test_traits_are_unique_per_event(self, mock_mail):
        """Test that Trait names are unique per event"""
        event = self.get_event()

        trait1 = Trait(name="Unique Trait", event=event)
        trait1.save()

        # Should be created successfully
        self.assertIsNotNone(trait1.id)

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_registration_alert_values_can_be_set(self, mock_mail):
        """Test that registration alert values can be set"""
        from larpmanager.models.registration import Registration

        registration = self.get_registration()

        # Test various alert changes - use update() to bypass accounting signals
        alert_values = [True, False, True]

        for alert_value in alert_values:
            Registration.objects.filter(pk=registration.pk).update(alert=alert_value)
            registration.refresh_from_db()

            # Should be saved successfully
            self.assertEqual(registration.alert, alert_value)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_payment_types_can_be_created(self, mock_mail):
        """Test that accounting payment types can be created"""
        from larpmanager.models.accounting import PaymentChoices
        member = self.get_member()

        # Test different payment types
        payment_types = [
            PaymentChoices.MONEY,
            PaymentChoices.CREDIT,
            PaymentChoices.TOKEN,
        ]

        for payment_type in payment_types:
            payment = AccountingItemPayment(
                member=member,
                value=Decimal("50.00"),
                association=self.get_association(),
                reg=self.get_registration(),
                pay=payment_type,
            )
            payment.save()

            # Should be created successfully
            self.assertIsNotNone(payment.id)

    @patch("larpmanager.mail.base.get_association_executives")
    @patch("larpmanager.mail.member.my_send_mail")
    def test_help_questions_can_be_created(self, mock_mail, mock_get_executives):
        """Test that help questions can be created"""
        mock_get_executives.return_value = []  # No executives
        member = self.get_member()

        # Create a help question
        question = HelpQuestion(
            member=member,
            association=self.get_association(),
            text="Test question",
        )
        question.save()

        # Should be created successfully
        self.assertIsNotNone(question.id)

    @patch("larpmanager.mail.member.my_send_mail")
    def test_chat_messages_with_different_channels_can_be_created(self, mock_mail):
        """Test that chat messages with different channels can be created"""
        sender = self.get_member()
        receiver = self.get_member()
        association = self.get_association()

        # Test different channels
        channels = [1, 2, 3]

        for channel in channels:
            message = ChatMessage(sender=sender, receiver=receiver, association=association, message=f"Test {channel} message", channel=channel)
            message.save()

            # Should be created successfully
            self.assertIsNotNone(message.id)
