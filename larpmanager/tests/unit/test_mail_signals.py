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
from larpmanager.models.form import ChatMessage, HelpQuestion
from larpmanager.models.registration import PreRegistration, Registration, RegistrationCharacterRel
from larpmanager.models.writing import Character
from larpmanager.tests.unit.base import BaseTestCase


class TestMailSignals(BaseTestCase):
    """Test cases for mail-related signal receivers"""

    @patch("larpmanager.mail.base.my_send_mail")
    def test_assignment_trait_post_save_sends_mail(self, mock_mail):
        """Test that AssignmentTrait post_save signal sends mail notification"""
        character = self.character()
        trait = Trait.objects.create(name="Test Trait", assoc=self.get_association())

        assignment = AssignmentTrait(character=character, trait=trait)
        assignment.save()

        # Should send mail notification
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.base.my_send_mail")
    def test_character_pre_save_sends_mail_on_status_change(self, mock_mail):
        """Test that Character pre_save signal sends mail on status change"""
        character = self.character()
        original_status = character.status

        # Change character status
        character.status = Character.DRAFT if original_status != Character.DRAFT else Character.PUBLISHED
        character.save()

        # Should send mail notification for status change
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.member.my_send_mail")
    def test_accounting_item_membership_pre_save_sends_mail(self, mock_mail):
        """Test that AccountingItemMembership pre_save signal sends mail"""
        member = self.get_member()

        item = AccountingItemMembership(
            member=member, value=Decimal("100.00"), assoc=self.get_association(), descr="Membership payment"
        )
        item.save()

        # Should send mail notification
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.member.my_send_mail")
    def test_help_question_pre_save_sends_mail(self, mock_mail):
        """Test that HelpQuestion pre_save signal sends mail"""
        member = self.get_member()

        question = HelpQuestion(
            member=member,
            assoc=self.get_association(),
            subject="Test Help Question",
            message="Need help with something",
        )
        question.save()

        # Should send mail notification
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.member.my_send_mail")
    def test_chat_message_pre_save_sends_mail(self, mock_mail):
        """Test that ChatMessage pre_save signal sends mail"""
        member = self.get_member()
        event = self.get_event()

        message = ChatMessage(member=member, event=event, message="Test chat message", typ=ChatMessage.GENERAL)
        message.save()

        # Should send mail notification
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_registration_character_rel_post_save_sends_mail(self, mock_mail):
        """Test that RegistrationCharacterRel post_save signal sends mail"""
        registration = self.get_registration()
        character = self.character()

        rel = RegistrationCharacterRel(registration=registration, character=character)
        rel.save()

        # Should send mail notification
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_registration_pre_save_sends_mail_on_status_change(self, mock_mail):
        """Test that Registration pre_save signal sends mail on status change"""
        registration = self.get_registration()
        original_status = registration.status

        # Change registration status
        registration.status = (
            Registration.CONFIRMED if original_status != Registration.CONFIRMED else Registration.WAITING
        )
        registration.save()

        # Should send mail notification for status change
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_registration_pre_delete_sends_mail(self, mock_mail):
        """Test that Registration pre_delete signal sends mail"""
        registration = self.get_registration()
        registration.delete()

        # Should send mail notification for deletion
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_pre_registration_pre_save_sends_mail(self, mock_mail):
        """Test that PreRegistration pre_save signal sends mail"""
        member = self.get_member()
        event = self.get_event()

        pre_reg = PreRegistration(member=member, event=event, message="Test pre-registration")
        pre_reg.save()

        # Should send mail notification
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_item_expense_post_save_sends_mail_notification(self, mock_mail):
        """Test that AccountingItemExpense post_save signal sends mail notification"""
        member = self.get_member()

        expense = AccountingItemExpense(
            member=member, value=Decimal("50.00"), assoc=self.get_association(), descr="Test expense"
        )
        expense.save()

        # Should send mail notification
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_item_expense_pre_save_sends_mail_on_status_change(self, mock_mail):
        """Test that AccountingItemExpense pre_save signal sends mail on status change"""
        member = self.get_member()

        expense = AccountingItemExpense.objects.create(
            member=member,
            value=Decimal("50.00"),
            assoc=self.get_association(),
            descr="Test expense",
            status=AccountingItemExpense.PENDING,
        )

        # Change status
        expense.status = AccountingItemExpense.APPROVED
        expense.save()

        # Should send mail notification for status change
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_item_payment_pre_save_sends_mail_on_status_change(self, mock_mail):
        """Test that AccountingItemPayment pre_save signal sends mail on status change"""
        member = self.get_member()

        payment = AccountingItemPayment.objects.create(
            member=member,
            value=Decimal("100.00"),
            assoc=self.get_association(),
            reg=self.get_registration(),
            pay=AccountingItemPayment.MONEY,
            status=AccountingItemPayment.PENDING,
        )

        # Change status
        payment.status = AccountingItemPayment.APPROVED
        payment.save()

        # Should send mail notification for status change
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_item_other_pre_save_sends_mail_on_status_change(self, mock_mail):
        """Test that AccountingItemOther pre_save signal sends mail on status change"""
        member = self.get_member()

        other = AccountingItemOther.objects.create(
            member=member,
            value=Decimal("25.00"),
            assoc=self.get_association(),
            run=self.get_run(),
            oth=AccountingItemOther.CREDIT,
            descr="Test credit",
            status=AccountingItemOther.PENDING,
        )

        # Change status
        other.status = AccountingItemOther.APPROVED
        other.save()

        # Should send mail notification for status change
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_item_donation_pre_save_sends_mail(self, mock_mail):
        """Test that AccountingItemDonation pre_save signal sends mail"""
        from larpmanager.models.accounting import AccountingItemDonation

        member = self.get_member()

        donation = AccountingItemDonation(
            member=member, value=Decimal("50.00"), assoc=self.get_association(), descr="Test donation"
        )
        donation.save()

        # Should send mail notification
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_collection_post_save_sends_mail(self, mock_mail):
        """Test that Collection post_save signal sends mail"""
        assoc = self.get_association()
        organizer = self.organizer()

        collection = Collection(name="Test Collection", assoc=assoc, organizer=organizer)
        collection.save()

        # Should send mail notification
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_item_collection_pre_save_sends_mail_on_status_change(self, mock_mail):
        """Test that AccountingItemCollection pre_save signal sends mail on status change"""
        from larpmanager.models.accounting import AccountingItemCollection

        member = self.get_member()
        collection = self.collection()

        item = AccountingItemCollection.objects.create(
            member=member,
            value=Decimal("30.00"),
            assoc=self.get_association(),
            collection=collection,
            status=AccountingItemCollection.PENDING,
        )

        # Change status
        item.status = AccountingItemCollection.APPROVED
        item.save()

        # Should send mail notification for status change
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.base.my_send_mail")
    def test_mail_signals_respect_mail_settings(self, mock_mail):
        """Test that mail signals respect mail settings and don't send when disabled"""
        character = self.character()
        trait = Trait.objects.create(name="Test Trait", assoc=self.get_association())

        # Simulate mail being disabled
        with patch("larpmanager.mail.base.should_send_mail", return_value=False):
            assignment = AssignmentTrait(character=character, trait=trait)
            assignment.save()

            # Should not send mail when disabled
            mock_mail.assert_not_called()

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_registration_signals_handle_different_statuses(self, mock_mail):
        """Test that registration signals handle different status transitions correctly"""
        registration = self.get_registration()

        # Test various status changes
        status_transitions = [
            (Registration.PENDING, Registration.CONFIRMED),
            (Registration.CONFIRMED, Registration.CANCELLED),
            (Registration.CANCELLED, Registration.WAITING),
        ]

        for old_status, new_status in status_transitions:
            mock_mail.reset_mock()
            registration.status = old_status
            registration.save()

            registration.status = new_status
            registration.save()

            # Should send mail for each status change
            self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_accounting_signals_handle_different_payment_types(self, mock_mail):
        """Test that accounting signals handle different payment types correctly"""
        member = self.get_member()

        # Test different payment types
        payment_types = [
            AccountingItemPayment.MONEY,
            AccountingItemPayment.CREDIT,
            AccountingItemPayment.TOKENS,
        ]

        for payment_type in payment_types:
            mock_mail.reset_mock()
            payment = AccountingItemPayment(
                member=member,
                value=Decimal("50.00"),
                assoc=self.get_association(),
                reg=self.get_registration(),
                pay=payment_type,
            )
            payment.save()

            # Should send mail for each payment type
            self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.member.my_send_mail")
    def test_help_question_signals_handle_different_types(self, mock_mail):
        """Test that help question signals handle different question types correctly"""
        member = self.get_member()

        # Test different question types
        question_types = [
            HelpQuestion.BUG,
            HelpQuestion.FEATURE,
            HelpQuestion.HELP,
            HelpQuestion.OTHER,
        ]

        for question_type in question_types:
            mock_mail.reset_mock()
            question = HelpQuestion(
                member=member,
                assoc=self.get_association(),
                subject=f"Test {question_type} Question",
                message="Test message",
                typ=question_type,
            )
            question.save()

            # Should send mail for each question type
            self.assertTrue(mock_mail.called)

    @patch("larpmanager.mail.member.my_send_mail")
    def test_chat_message_signals_handle_different_message_types(self, mock_mail):
        """Test that chat message signals handle different message types correctly"""
        member = self.get_member()
        event = self.get_event()

        # Test different message types
        message_types = [
            ChatMessage.GENERAL,
            ChatMessage.STAFF,
            ChatMessage.PLAYER,
        ]

        for message_type in message_types:
            mock_mail.reset_mock()
            message = ChatMessage(member=member, event=event, message=f"Test {message_type} message", typ=message_type)
            message.save()

            # Should send mail for each message type
            self.assertTrue(mock_mail.called)
