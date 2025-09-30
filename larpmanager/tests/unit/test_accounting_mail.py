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

from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

# Import the mail functions to test
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.mail.accounting import (
    get_credit_email,
    get_expense_mail,
    get_invoice_email,
    get_notify_refund_email,
    get_pay_credit_email,
    get_pay_money_email,
    get_pay_token_email,
    get_token_credit_name,
    get_token_email,
    notify_credit,
    notify_invoice_check,
    notify_pay_token,
    notify_refund,
    notify_refund_request,
    save_accounting_item_donation,
    save_collection_gift,
    send_collection_activation_email,
    update_accounting_item_expense_post,
    update_accounting_item_expense_pre,
    update_accounting_item_other,
    update_accounting_item_payment,
)
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemOther,
    AccountingItemPayment,
    Collection,
    OtherChoices,
    PaymentChoices,
    PaymentInvoice,
    PaymentType,
)
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration


class TestExpenseMailSignals(BaseTestCase):
    """Test expense-related email notifications"""

    @patch("larpmanager.mail.accounting.get_event_organizers")
    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_expense_post_save_created(
        self, mock_activate, mock_send_mail, mock_get_organizers
    ):
        """Test email sent when expense is created"""
        mock_get_organizers.return_value = [self.organizer()]

        # Trigger the signal
        expense_item = self.accounting_item()
        expense_item.run = self.run()  # Add run to make the function work

        # Mock the download method to avoid file issues
        with patch.object(expense_item, 'download', return_value="/test/path"):
            update_accounting_item_expense_post(sender=AccountingItemExpense, instance=expense_item, created=True)

            mock_activate.assert_called_once_with(self.organizer().language)
            mock_send_mail.assert_called_once()

    def test_expense_post_save_hidden(self):
        """Test no email sent when expense is hidden"""
        self.accounting_item().hide = True

        with patch("larpmanager.mail.accounting.my_send_mail") as mock_send_mail:
            update_accounting_item_expense_post(sender=AccountingItemExpense, instance=self.accounting_item(), created=True)

            mock_send_mail.assert_not_called()

    def test_expense_post_save_not_created(self):
        """Test no email sent when expense is updated (not created)"""
        with patch("larpmanager.mail.accounting.my_send_mail") as mock_send_mail:
            update_accounting_item_expense_post(sender=AccountingItemExpense, instance=self.accounting_item(), created=False)

            mock_send_mail.assert_not_called()

    def test_get_expense_mail(self):
        """Test expense email content generation"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "
            with patch("larpmanager.mail.accounting.get_url") as mock_get_url:
                mock_get_url.return_value = "http://example.com/download"

                expense_item = self.accounting_item()
                expense_item.run = self.run()  # Add run to avoid NoneType error
                # Mock the download method to avoid file issues
                with patch.object(expense_item, 'download', return_value="/test/path"):
                    subj, body = get_expense_mail(expense_item)

                    assert "[TEST]" in subj
                    assert "Reimbursement request" in subj
                    assert str(expense_item.member) in body
                    assert str(expense_item.value) in body
                    assert expense_item.descr in body
                    assert "download document" in body

    @patch("larpmanager.mail.accounting.AccountingItemExpense.objects.get")
    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_expense_pre_save_approved(self, mock_send_mail, mock_get):
        """Test email sent when expense is approved"""
        # Mock previous state (not approved)
        previous_expense = Mock()
        previous_expense.is_approved = False
        mock_get.return_value = previous_expense

        # Set current state (approved)
        expense_item = self.accounting_item()
        expense_item.pk = 1
        expense_item.is_approved = True
        expense_item.member = self.member()

        with patch("larpmanager.mail.accounting.get_token_credit_name") as mock_get_names:
            mock_get_names.return_value = ("Tokens", "Credits")

            update_accounting_item_expense_pre(sender=AccountingItemExpense, instance=expense_item)

            mock_send_mail.assert_called_once()

    def test_expense_pre_save_no_member(self):
        """Test no email sent when expense has no member"""
        expense_item = self.accounting_item()
        expense_item.pk = 1
        expense_item.member = None

        with patch("larpmanager.mail.accounting.my_send_mail") as mock_send_mail:
            with patch("larpmanager.mail.accounting.AccountingItemExpense.objects.get") as mock_get:
                mock_get.return_value = expense_item
                update_accounting_item_expense_pre(sender=AccountingItemExpense, instance=expense_item)

            mock_send_mail.assert_not_called()

    def test_get_token_credit_name_with_config(self):
        """Test token/credit name retrieval with custom config"""
        association = self.association()
        association.get_config = Mock(
            side_effect=lambda key, default: {
                "token_credit_token_name": "Game Points",
                "token_credit_credit_name": "Event Credits",
            }.get(key, default)
        )

        token_name, credit_name = get_token_credit_name(association)

        assert token_name == "Game Points"
        assert credit_name == "Event Credits"

    def test_get_token_credit_name_with_defaults(self):
        """Test token/credit name retrieval with defaults"""
        association = self.association()
        association.get_config = Mock(return_value=None)

        token_name, credit_name = get_token_credit_name(association)

        assert token_name == "Tokens"
        assert credit_name == "Credits"


class TestPaymentMailSignals(BaseTestCase):
    """Test payment-related email notifications"""

    @patch("larpmanager.mail.accounting.notify_pay_money")
    def test_payment_pre_save_money(self, mock_notify):
        """Test money payment notification"""
        payment_item = self.payment_item()
        payment_item.pk = None  # New payment
        payment_item.pay = PaymentChoices.MONEY
        payment_item.reg.run.event.assoc.get_config = Mock(return_value=True)

        update_accounting_item_payment(sender=AccountingItemPayment, instance=payment_item)

        mock_notify.assert_called_once()

    @patch("larpmanager.mail.accounting.notify_pay_credit")
    def test_payment_pre_save_credit(self, mock_notify):
        """Test credit payment notification"""
        payment_item = self.payment_item()
        payment_item.pk = None  # New payment
        payment_item.pay = PaymentChoices.CREDIT
        payment_item.reg.run.event.assoc.get_config = Mock(return_value=True)

        update_accounting_item_payment(sender=AccountingItemPayment, instance=payment_item)

        mock_notify.assert_called_once()

    @patch("larpmanager.mail.accounting.notify_pay_token")
    def test_payment_pre_save_token(self, mock_notify):
        """Test token payment notification"""
        payment_item = self.payment_item()
        payment_item.pk = None  # New payment
        payment_item.pay = PaymentChoices.TOKEN
        payment_item.reg.run.event.assoc.get_config = Mock(return_value=True)

        update_accounting_item_payment(sender=AccountingItemPayment, instance=payment_item)

        mock_notify.assert_called_once()

    def test_payment_pre_save_disabled(self):
        """Test no notification when mail_payment is disabled"""
        payment_item = self.payment_item()
        payment_item.pk = None
        payment_item.pay = PaymentChoices.MONEY
        payment_item.reg.run.event.assoc.get_config = Mock(return_value=False)

        with patch("larpmanager.mail.accounting.notify_pay_money") as mock_notify:
            update_accounting_item_payment(sender=AccountingItemPayment, instance=payment_item)

            mock_notify.assert_not_called()

    @patch("larpmanager.mail.accounting.get_event_organizers")
    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_notify_pay_token(
        self, mock_activate, mock_send_mail, mock_get_organizers
    ):
        """Test token payment notification to user and self.organizer()s"""
        mock_get_organizers.return_value = [self.organizer()]

        payment_item = self.payment_item()
        notify_pay_token(payment_item, self.member(), payment_item.reg.run, "Game Tokens")

        # Should send email to user and self.organizer()
        assert mock_send_mail.call_count == 2
        assert mock_activate.call_count == 2

    def test_get_pay_token_email(self):
        """Test token payment email content"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "

            payment_item = self.payment_item()
            subj, body = get_pay_token_email(payment_item, payment_item.reg.run, "Game Tokens")

            assert "[TEST]" in subj
            assert "Game Tokens" in subj
            assert "Game Tokens" in body
            assert str(int(payment_item.value)) in body

    def test_get_pay_credit_email(self):
        """Test credit payment email content"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "

            payment_item = self.payment_item()
            subj, body = get_pay_credit_email("Event Credits", payment_item, payment_item.reg.run)

            assert "[TEST]" in subj
            assert "Event Credits" in subj
            assert "Event Credits" in body

    def test_get_pay_money_email(self):
        """Test money payment email content"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "

            payment_item = self.payment_item()
            subj, body = get_pay_money_email("€", payment_item, payment_item.reg.run)

            assert "[TEST]" in subj
            assert "Payment for" in subj
            assert str(payment_item.value) in body
            assert "€" in body


class TestOtherAccountingMailSignals(BaseTestCase):
    """Test other accounting item email notifications"""

    @patch("larpmanager.mail.accounting.notify_token")
    def test_other_pre_save_token(self, mock_notify):
        """Test token assignment notification"""
        token_item = self.other_item_token()
        token_item.pk = None  # New item

        update_accounting_item_other(sender=AccountingItemOther, instance=token_item)

        mock_notify.assert_called_once()

    @patch("larpmanager.mail.accounting.notify_credit")
    def test_other_pre_save_credit(self, mock_notify):
        """Test credit assignment notification"""
        credit_item = self.other_item_credit()
        credit_item.pk = None  # New item

        update_accounting_item_other(sender=AccountingItemOther, instance=credit_item)

        mock_notify.assert_called_once()

    @patch("larpmanager.mail.accounting.notify_refund")
    def test_other_pre_save_refund(self, mock_notify):
        """Test refund notification"""
        refund_item = self.other_item_refund()
        refund_item.pk = None  # New item

        update_accounting_item_other(sender=AccountingItemOther, instance=refund_item)

        mock_notify.assert_called_once()

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_notify_credit(self, mock_activate, mock_send_mail):
        """Test credit notification email"""
        with patch("larpmanager.mail.accounting.get_url") as mock_get_url:
            mock_get_url.return_value = "http://example.com/accounting"

            credit_item = self.other_item_credit()
            notify_credit("Event Credits", credit_item)

            # Function may call activate multiple times
            assert mock_activate.call_count >= 1
            assert mock_send_mail.call_count >= 1

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_notify_refund(self, mock_activate, mock_send_mail):
        """Test refund notification email"""
        refund_item = self.other_item_refund()
        notify_refund("Event Credits", refund_item)

        mock_activate.assert_called_once()
        mock_send_mail.assert_called_once()

    def test_get_credit_email(self):
        """Test credit email content generation"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "

            credit_item = self.other_item_credit()
            subj, body = get_credit_email("Event Credits", credit_item)

            assert "[TEST]" in subj
            assert "Event Credits" in subj
            assert "Event Credits" in body
            assert str(credit_item.value) in body
            assert credit_item.descr in body

    def test_get_token_email(self):
        """Test token email content generation"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "

            token_item = self.other_item_token()
            subj, body = get_token_email(token_item, "Game Tokens")

            assert "[TEST]" in subj
            assert "Game Tokens" in subj
            assert "Game Tokens" in body


class TestDonationMailSignals(BaseTestCase):
    """Test donation-related email notifications"""

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_donation_pre_save(self, mock_activate, mock_send_mail):
        """Test donation confirmation email"""
        donation_item = self.accounting_item()
        donation_item.pk = None  # New donation

        save_accounting_item_donation(sender=AccountingItemDonation, instance=donation_item)

        mock_activate.assert_called_once()
        mock_send_mail.assert_called_once()

    def test_donation_pre_save_hidden(self):
        """Test no email when donation is hidden"""
        donation_item = self.accounting_item()
        donation_item.pk = None
        donation_item.hide = True

        with patch("larpmanager.mail.accounting.my_send_mail") as mock_send_mail:
            save_accounting_item_donation(sender=AccountingItemDonation, instance=donation_item)

            mock_send_mail.assert_not_called()

    def test_donation_pre_save_existing(self):
        """Test no email when donation already exists"""
        donation_item = self.accounting_item()
        donation_item.pk = 1  # Existing donation

        with patch("larpmanager.mail.accounting.my_send_mail") as mock_send_mail:
            save_accounting_item_donation(sender=AccountingItemDonation, instance=donation_item)

            mock_send_mail.assert_not_called()


class TestCollectionMailSignals(BaseTestCase):
    """Test self.collection()-related email notifications"""

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_collection_post_save(self, mock_activate, mock_send_mail):
        """Test collection activation email"""
        with patch("larpmanager.mail.accounting.get_url") as mock_get_url:
            mock_get_url.return_value = "http://example.com/collection"

            collection = self.collection()
            send_collection_activation_email(sender=Collection, instance=collection, created=True)

            # Function may call activate multiple times
            assert mock_activate.call_count >= 1
            assert mock_send_mail.call_count >= 1

    def test_collection_post_save_not_created(self):
        """Test no email when collection is updated"""
        # Create collection first, then reset mocks to avoid signals from creation
        collection = self.collection()

        with patch("larpmanager.mail.accounting.my_send_mail") as mock_send_mail:
            with patch("larpmanager.mail.accounting.activate") as mock_activate:
                with patch("larpmanager.mail.accounting.get_url") as mock_get_url:
                    mock_get_url.return_value = "http://example.com/collection"

                    send_collection_activation_email(sender=Collection, instance=collection, created=False)

                    # Should not be called when created=False
                    mock_send_mail.assert_not_called()
                    mock_activate.assert_not_called()

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_collection_gift_pre_save(self, mock_activate, mock_send_mail):
        """Test collection participation email"""
        collection_item = self.collection_item()
        collection_item.pk = None  # New participation

        save_collection_gift(sender=AccountingItemCollection, instance=collection_item)

        # Should send email to participant and organizer
        assert mock_activate.call_count >= 1
        assert mock_send_mail.call_count >= 1


class TestInvoiceAndRefundMails(BaseTestCase):
    """Test invoice and refund notification functions"""

    @patch("larpmanager.mail.accounting.get_assoc_features")
    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_notify_invoice_check_treasurer(
        self, mock_activate, mock_send_mail, mock_get_features
    ):
        """Test invoice notification to treasurer"""
        mock_get_features.return_value = ["treasurer"]
        invoice = self.invoice()
        invoice.assoc.get_config = Mock(
            side_effect=lambda key, default: {"mail_payment": True, "treasurer_appointees": f"{self.member().id}"}.get(
                key, default
            )
        )

        with patch("larpmanager.mail.accounting.Member.objects.get") as mock_get_member:
            mock_get_member.return_value = self.member()

            notify_invoice_check(invoice)

            mock_activate.assert_called_once()
            mock_send_mail.assert_called_once()

    @patch("larpmanager.mail.accounting.get_event_organizers")
    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_notify_invoice_check_organizers(
        self, mock_activate, mock_send_mail, mock_get_organizers
    ):
        """Test invoice notification to event self.organizer()s"""
        invoice = self.invoice()
        invoice.typ = PaymentType.REGISTRATION
        invoice.reg = self.registration()
        invoice.assoc.get_config = Mock(return_value=True)

        mock_get_organizers.return_value = [self.organizer()]

        with patch("larpmanager.mail.accounting.get_assoc_features") as mock_get_features:
            mock_get_features.return_value = []  # No treasurer feature

            notify_invoice_check(invoice)

            mock_activate.assert_called_once()
            mock_send_mail.assert_called_once()

    @patch("larpmanager.mail.accounting.notify_organization_exe")
    def test_notify_invoice_check_fallback(self, mock_notify_org):
        """Test invoice notification fallback to main email"""
        invoice = self.invoice()
        invoice.assoc.get_config = Mock(return_value=True)

        with patch("larpmanager.mail.accounting.get_assoc_features") as mock_get_features:
            mock_get_features.return_value = []  # No treasurer feature

            notify_invoice_check(invoice)

            mock_notify_org.assert_called_once()

    def test_get_invoice_email(self):
        """Test invoice email content generation"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "
            with patch("larpmanager.mail.accounting.get_url") as mock_get_url:
                mock_get_url.return_value = "http://example.com/confirm"

                invoice = self.invoice()
                subj, body = get_invoice_email(invoice)

                assert "[TEST]" in subj
                assert "Payment to check" in subj
                assert invoice.causal in body
                assert str(invoice.mc_gross) in body

    @patch("larpmanager.mail.accounting.notify_organization_exe")
    def test_notify_refund_request(self, mock_notify_org):
        """Test refund request notification"""
        notify_refund_request(self.refund_request())

        mock_notify_org.assert_called_once()

    def test_get_notify_refund_email(self):
        """Test refund request email content"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "

            refund_request = self.refund_request()
            subj, body = get_notify_refund_email(refund_request)

            assert "[TEST]" in subj
            assert "Request refund" in subj
            assert str(refund_request.member) in subj
            assert refund_request.details in body
            assert str(refund_request.value) in body
