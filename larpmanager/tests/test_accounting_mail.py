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


@pytest.mark.django_db
class TestExpenseMailSignals:
    """Test expense-related email notifications"""

    @patch("larpmanager.mail.accounting.get_event_organizers")
    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_expense_post_save_created(
        self, mock_activate, mock_send_mail, mock_get_organizers, expense_item, organizer
    ):
        """Test email sent when expense is created"""
        mock_get_organizers.return_value = [organizer]

        # Trigger the signal
        update_accounting_item_expense_post(sender=AccountingItemExpense, instance=expense_item, created=True)

        mock_activate.assert_called_once_with(organizer.language)
        mock_send_mail.assert_called_once()

    def test_expense_post_save_hidden(self, expense_item, organizer):
        """Test no email sent when expense is hidden"""
        expense_item.hide = True

        with patch("larpmanager.mail.accounting.my_send_mail") as mock_send_mail:
            update_accounting_item_expense_post(sender=AccountingItemExpense, instance=expense_item, created=True)

            mock_send_mail.assert_not_called()

    def test_expense_post_save_not_created(self, expense_item):
        """Test no email sent when expense is updated (not created)"""
        with patch("larpmanager.mail.accounting.my_send_mail") as mock_send_mail:
            update_accounting_item_expense_post(sender=AccountingItemExpense, instance=expense_item, created=False)

            mock_send_mail.assert_not_called()

    def test_get_expense_mail(self, expense_item):
        """Test expense email content generation"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "
            with patch("larpmanager.mail.accounting.get_url") as mock_get_url:
                mock_get_url.return_value = "http://example.com/download"

                subj, body = get_expense_mail(expense_item)

                assert "[TEST]" in subj
                assert "Reimbursement request" in subj
                assert str(expense_item.member) in body
                assert str(expense_item.value) in body
                assert expense_item.descr in body
                assert "download document" in body

    @patch("larpmanager.mail.accounting.AccountingItemExpense.objects.get")
    @patch("larpmanager.mail.accounting.my_send_mail")
    def test_expense_pre_save_approved(self, mock_send_mail, mock_get, expense_item, member):
        """Test email sent when expense is approved"""
        # Mock previous state (not approved)
        previous_expense = Mock()
        previous_expense.is_approved = False
        mock_get.return_value = previous_expense

        # Set current state (approved)
        expense_item.pk = 1
        expense_item.is_approved = True
        expense_item.member = member

        with patch("larpmanager.mail.accounting.get_token_credit_name") as mock_get_names:
            mock_get_names.return_value = ("Tokens", "Credits")

            update_accounting_item_expense_pre(sender=AccountingItemExpense, instance=expense_item)

            mock_send_mail.assert_called_once()

    def test_expense_pre_save_no_member(self, expense_item):
        """Test no email sent when expense has no member"""
        expense_item.pk = 1
        expense_item.member = None

        with patch("larpmanager.mail.accounting.my_send_mail") as mock_send_mail:
            update_accounting_item_expense_pre(sender=AccountingItemExpense, instance=expense_item)

            mock_send_mail.assert_not_called()

    def test_get_token_credit_name_with_config(self, association):
        """Test token/credit name retrieval with custom config"""
        association.get_config = Mock(
            side_effect=lambda key, default: {
                "token_credit_token_name": "Game Points",
                "token_credit_credit_name": "Event Credits",
            }.get(key, default)
        )

        token_name, credit_name = get_token_credit_name(association)

        assert token_name == "Game Points"
        assert credit_name == "Event Credits"

    def test_get_token_credit_name_with_defaults(self, association):
        """Test token/credit name retrieval with defaults"""
        association.get_config = Mock(return_value=None)

        token_name, credit_name = get_token_credit_name(association)

        assert token_name == "Tokens"
        assert credit_name == "Credits"


@pytest.mark.django_db
class TestPaymentMailSignals:
    """Test payment-related email notifications"""

    @patch("larpmanager.mail.accounting.notify_pay_money")
    def test_payment_pre_save_money(self, mock_notify, payment_item):
        """Test money payment notification"""
        payment_item.pk = None  # New payment
        payment_item.pay = PaymentChoices.MONEY
        payment_item.reg.run.event.assoc.get_config = Mock(return_value=True)

        update_accounting_item_payment(sender=AccountingItemPayment, instance=payment_item)

        mock_notify.assert_called_once()

    @patch("larpmanager.mail.accounting.notify_pay_credit")
    def test_payment_pre_save_credit(self, mock_notify, payment_item):
        """Test credit payment notification"""
        payment_item.pk = None  # New payment
        payment_item.pay = PaymentChoices.CREDIT
        payment_item.reg.run.event.assoc.get_config = Mock(return_value=True)

        update_accounting_item_payment(sender=AccountingItemPayment, instance=payment_item)

        mock_notify.assert_called_once()

    @patch("larpmanager.mail.accounting.notify_pay_token")
    def test_payment_pre_save_token(self, mock_notify, payment_item):
        """Test token payment notification"""
        payment_item.pk = None  # New payment
        payment_item.pay = PaymentChoices.TOKEN
        payment_item.reg.run.event.assoc.get_config = Mock(return_value=True)

        update_accounting_item_payment(sender=AccountingItemPayment, instance=payment_item)

        mock_notify.assert_called_once()

    def test_payment_pre_save_disabled(self, payment_item):
        """Test no notification when mail_payment is disabled"""
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
        self, mock_activate, mock_send_mail, mock_get_organizers, payment_item, member, organizer
    ):
        """Test token payment notification to user and organizers"""
        mock_get_organizers.return_value = [organizer]

        notify_pay_token(payment_item, member, payment_item.reg.run, "Game Tokens")

        # Should send email to user and organizer
        assert mock_send_mail.call_count == 2
        assert mock_activate.call_count == 2

    def test_get_pay_token_email(self, payment_item):
        """Test token payment email content"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "

            subj, body = get_pay_token_email(payment_item, payment_item.reg.run, "Game Tokens")

            assert "[TEST]" in subj
            assert "Game Tokens" in subj
            assert "Game Tokens" in body
            assert str(int(payment_item.value)) in body

    def test_get_pay_credit_email(self, payment_item):
        """Test credit payment email content"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "

            subj, body = get_pay_credit_email("Event Credits", payment_item, payment_item.reg.run)

            assert "[TEST]" in subj
            assert "Event Credits" in subj
            assert "Event Credits" in body

    def test_get_pay_money_email(self, payment_item):
        """Test money payment email content"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "

            subj, body = get_pay_money_email("€", payment_item, payment_item.reg.run)

            assert "[TEST]" in subj
            assert "Payment for" in subj
            assert str(payment_item.value) in body
            assert "€" in body


@pytest.mark.django_db
class TestOtherAccountingMailSignals:
    """Test other accounting item email notifications"""

    @patch("larpmanager.mail.accounting.notify_token")
    def test_other_pre_save_token(self, mock_notify, other_item_token):
        """Test token assignment notification"""
        other_item_token.pk = None  # New item

        update_accounting_item_other(sender=AccountingItemOther, instance=other_item_token)

        mock_notify.assert_called_once()

    @patch("larpmanager.mail.accounting.notify_credit")
    def test_other_pre_save_credit(self, mock_notify, other_item_credit):
        """Test credit assignment notification"""
        other_item_credit.pk = None  # New item

        update_accounting_item_other(sender=AccountingItemOther, instance=other_item_credit)

        mock_notify.assert_called_once()

    @patch("larpmanager.mail.accounting.notify_refund")
    def test_other_pre_save_refund(self, mock_notify, other_item_refund):
        """Test refund notification"""
        other_item_refund.pk = None  # New item

        update_accounting_item_other(sender=AccountingItemOther, instance=other_item_refund)

        mock_notify.assert_called_once()

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_notify_credit(self, mock_activate, mock_send_mail, other_item_credit):
        """Test credit notification email"""
        with patch("larpmanager.mail.accounting.get_url") as mock_get_url:
            mock_get_url.return_value = "http://example.com/accounting"

            notify_credit("Event Credits", other_item_credit)

            mock_activate.assert_called_once()
            mock_send_mail.assert_called_once()

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_notify_refund(self, mock_activate, mock_send_mail, other_item_refund):
        """Test refund notification email"""
        notify_refund("Event Credits", other_item_refund)

        mock_activate.assert_called_once()
        mock_send_mail.assert_called_once()

    def test_get_credit_email(self, other_item_credit):
        """Test credit email content generation"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "

            subj, body = get_credit_email("Event Credits", other_item_credit)

            assert "[TEST]" in subj
            assert "Event Credits" in subj
            assert "Event Credits" in body
            assert str(other_item_credit.value) in body
            assert other_item_credit.descr in body

    def test_get_token_email(self, other_item_token):
        """Test token email content generation"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "

            subj, body = get_token_email(other_item_token, "Game Tokens")

            assert "[TEST]" in subj
            assert "Game Tokens" in subj
            assert "Game Tokens" in body


@pytest.mark.django_db
class TestDonationMailSignals:
    """Test donation-related email notifications"""

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_donation_pre_save(self, mock_activate, mock_send_mail, donation_item):
        """Test donation confirmation email"""
        donation_item.pk = None  # New donation

        save_accounting_item_donation(sender=AccountingItemDonation, instance=donation_item)

        mock_activate.assert_called_once()
        mock_send_mail.assert_called_once()

    def test_donation_pre_save_hidden(self, donation_item):
        """Test no email when donation is hidden"""
        donation_item.pk = None
        donation_item.hide = True

        with patch("larpmanager.mail.accounting.my_send_mail") as mock_send_mail:
            save_accounting_item_donation(sender=AccountingItemDonation, instance=donation_item)

            mock_send_mail.assert_not_called()

    def test_donation_pre_save_existing(self, donation_item):
        """Test no email when donation already exists"""
        donation_item.pk = 1  # Existing donation

        with patch("larpmanager.mail.accounting.my_send_mail") as mock_send_mail:
            save_accounting_item_donation(sender=AccountingItemDonation, instance=donation_item)

            mock_send_mail.assert_not_called()


@pytest.mark.django_db
class TestCollectionMailSignals:
    """Test collection-related email notifications"""

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_collection_post_save(self, mock_activate, mock_send_mail, collection):
        """Test collection activation email"""
        with patch("larpmanager.mail.accounting.get_url") as mock_get_url:
            mock_get_url.return_value = "http://example.com/collection"

            send_collection_activation_email(sender=Collection, instance=collection, created=True)

            mock_activate.assert_called_once()
            mock_send_mail.assert_called_once()

    def test_collection_post_save_not_created(self, collection):
        """Test no email when collection is updated"""
        with patch("larpmanager.mail.accounting.my_send_mail") as mock_send_mail:
            send_collection_activation_email(sender=Collection, instance=collection, created=False)

            mock_send_mail.assert_not_called()

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_collection_gift_pre_save(self, mock_activate, mock_send_mail, collection_item):
        """Test collection participation email"""
        collection_item.pk = None  # New participation

        save_collection_gift(sender=AccountingItemCollection, instance=collection_item)

        # Should send email to participant and organizer
        assert mock_activate.call_count == 2
        assert mock_send_mail.call_count == 2


@pytest.mark.django_db
class TestInvoiceAndRefundMails:
    """Test invoice and refund notification functions"""

    @patch("larpmanager.mail.accounting.get_assoc_features")
    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_notify_invoice_check_treasurer(
        self, mock_activate, mock_send_mail, mock_get_features, payment_invoice, member
    ):
        """Test invoice notification to treasurer"""
        mock_get_features.return_value = ["treasurer"]
        payment_invoice.assoc.get_config = Mock(
            side_effect=lambda key, default: {"mail_payment": True, "treasurer_appointees": f"{member.id}"}.get(
                key, default
            )
        )

        with patch("larpmanager.mail.accounting.Member.objects.get") as mock_get_member:
            mock_get_member.return_value = member

            notify_invoice_check(payment_invoice)

            mock_activate.assert_called_once()
            mock_send_mail.assert_called_once()

    @patch("larpmanager.mail.accounting.get_event_organizers")
    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.activate")
    def test_notify_invoice_check_organizers(
        self, mock_activate, mock_send_mail, mock_get_organizers, payment_invoice, organizer
    ):
        """Test invoice notification to event organizers"""
        payment_invoice.typ = PaymentType.REGISTRATION
        payment_invoice.reg = Mock()
        payment_invoice.reg.run.event = Mock()
        payment_invoice.assoc.get_config = Mock(return_value=True)

        mock_get_organizers.return_value = [organizer]

        with patch("larpmanager.mail.accounting.get_assoc_features") as mock_get_features:
            mock_get_features.return_value = []  # No treasurer feature

            notify_invoice_check(payment_invoice)

            mock_activate.assert_called_once()
            mock_send_mail.assert_called_once()

    @patch("larpmanager.mail.accounting.notify_organization_exe")
    def test_notify_invoice_check_fallback(self, mock_notify_org, payment_invoice):
        """Test invoice notification fallback to main email"""
        payment_invoice.assoc.get_config = Mock(return_value=True)

        with patch("larpmanager.mail.accounting.get_assoc_features") as mock_get_features:
            mock_get_features.return_value = []  # No treasurer feature

            notify_invoice_check(payment_invoice)

            mock_notify_org.assert_called_once()

    def test_get_invoice_email(self, payment_invoice):
        """Test invoice email content generation"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "
            with patch("larpmanager.mail.accounting.get_url") as mock_get_url:
                mock_get_url.return_value = "http://example.com/confirm"

                subj, body = get_invoice_email(payment_invoice)

                assert "[TEST]" in subj
                assert "Payment to check" in subj
                assert payment_invoice.causal in body
                assert str(payment_invoice.mc_gross) in body

    @patch("larpmanager.mail.accounting.notify_organization_exe")
    def test_notify_refund_request(self, mock_notify_org, refund_request):
        """Test refund request notification"""
        notify_refund_request(refund_request)

        mock_notify_org.assert_called_once()

    def test_get_notify_refund_email(self, refund_request):
        """Test refund request email content"""
        with patch("larpmanager.mail.accounting.hdr") as mock_hdr:
            mock_hdr.return_value = "[TEST] "

            subj, body = get_notify_refund_email(refund_request)

            assert "[TEST]" in subj
            assert "Request refund" in subj
            assert str(refund_request.member) in subj
            assert refund_request.details in body
            assert str(refund_request.value) in body


# Fixtures
@pytest.fixture
def association():
    return Association.objects.create(name="Test Association", slug="test-assoc", email="test@example.com")


@pytest.fixture
def member():
    user = Member.objects.create(username="testuser", email="test@example.com", first_name="Test", last_name="User")
    user.language = "en"
    return user


@pytest.fixture
def organizer():
    user = Member.objects.create(
        username="organizer", email="organizer@example.com", first_name="Org", last_name="User"
    )
    user.language = "en"
    return user


@pytest.fixture
def event(association):
    return Event.objects.create(name="Test Event", assoc=association, number=1)


@pytest.fixture
def run(event):
    return Run.objects.create(event=event, number=1, name="Test Run", start="2025-01-01", end="2025-01-02")


@pytest.fixture
def registration(member, run):
    return Registration.objects.create(member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"))


@pytest.fixture
def expense_item(member, association, run):
    item = AccountingItemExpense(
        member=member,
        value=Decimal("50.00"),
        assoc=association,
        run=run,
        descr="Test expense",
        exp="a",  # SCENOGR
        hide=False,
    )
    return item


@pytest.fixture
def payment_item(member, association, registration):
    item = AccountingItemPayment(
        member=member,
        value=Decimal("100.00"),
        assoc=association,
        reg=registration,
        pay=PaymentChoices.MONEY,
        hide=False,
    )
    return item


@pytest.fixture
def other_item_token(member, association, run):
    return AccountingItemOther(
        member=member,
        value=Decimal("5"),
        assoc=association,
        run=run,
        oth=OtherChoices.TOKEN,
        descr="Test tokens",
        hide=False,
    )


@pytest.fixture
def other_item_credit(member, association, run):
    return AccountingItemOther(
        member=member,
        value=Decimal("50.00"),
        assoc=association,
        run=run,
        oth=OtherChoices.CREDIT,
        descr="Test credits",
        hide=False,
    )


@pytest.fixture
def other_item_refund(member, association):
    return AccountingItemOther(
        member=member,
        value=Decimal("30.00"),
        assoc=association,
        oth=OtherChoices.REFUND,
        descr="Test refund",
        hide=False,
    )


@pytest.fixture
def donation_item(member, association):
    return AccountingItemDonation(
        member=member, value=Decimal("25.00"), assoc=association, descr="Test donation", hide=False
    )


@pytest.fixture
def collection(member, association):
    collection = Collection(
        name="Test Collection",
        organizer=member,
        assoc=association,
        total=0,
        status="o",  # OPEN
    )
    collection.display_member = Mock(return_value="Test Collection")
    collection.contribute_code = "ABC123"
    return collection


@pytest.fixture
def collection_item(member, association, collection):
    return AccountingItemCollection(member=member, value=Decimal("20.00"), assoc=association, collection=collection)


@pytest.fixture
def payment_invoice(member, association):
    return PaymentInvoice(
        member=member,
        assoc=association,
        typ=PaymentType.REGISTRATION,
        status="c",  # CREATED
        mc_gross=Decimal("100.00"),
        mc_fee=Decimal("5.00"),
        causal="Test payment",
        cod="TEST123",
        txn_id="TXN456",
    )


@pytest.fixture
def refund_request(member, association):
    return Mock(
        member=member,
        assoc=association,
        details="IBAN: IT60 X054 2811 1010 0000 0123 456",
        value=Decimal("50.00"),
        status="r",  # REQUEST
    )
