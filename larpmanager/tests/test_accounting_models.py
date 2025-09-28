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

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemOther,
    AccountingItemOutflow,
    AccountingItemTransaction,
    BalanceChoices,
    Collection,
    CollectionStatus,
    Discount,
    ElectronicInvoice,
    ExpenseChoices,
    OtherChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
    RecordAccounting,
    RefundRequest,
    RefundStatus,
)
from larpmanager.models.association import Association
from larpmanager.models.base import PaymentMethod
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member


@pytest.mark.django_db
class TestPaymentInvoice:
    def test_str_representation(self, payment_invoice):
        expected = f"({payment_invoice.status}) Invoice for {payment_invoice.member} - {payment_invoice.causal} - {payment_invoice.txn_id} {payment_invoice.mc_gross} {payment_invoice.mc_fee}"
        assert str(payment_invoice) == expected

    def test_download_no_invoice(self, payment_invoice):
        payment_invoice.invoice = None
        assert payment_invoice.download() == ""

    def test_download_no_name(self, payment_invoice):
        mock_invoice = Mock()
        mock_invoice.name = ""
        payment_invoice.invoice = mock_invoice
        assert payment_invoice.download() == ""

    @patch("larpmanager.models.accounting.download")
    def test_download_with_file(self, mock_download, payment_invoice):
        mock_invoice = Mock()
        mock_invoice.name = "test.pdf"
        mock_invoice.url = "http://example.com/test.pdf"
        payment_invoice.invoice = mock_invoice
        mock_download.return_value = "download_link"

        result = payment_invoice.download()
        mock_download.assert_called_once_with("http://example.com/test.pdf")
        assert result == "download_link"

    def test_get_details_no_method(self, payment_invoice):
        payment_invoice.method = None
        assert payment_invoice.get_details() == ""

    def test_get_details_with_invoice(self, payment_invoice):
        payment_invoice.invoice = Mock()
        payment_invoice.invoice.url = "http://example.com/test.pdf"
        payment_invoice.text = "Test text"
        payment_invoice.cod = "TEST123"

        with patch.object(payment_invoice, "download", return_value="download_link"):
            result = payment_invoice.get_details()
            assert " <a href='download_link'>Download</a>" in result
            assert " Test text" in result
            assert " TEST123" in result


@pytest.mark.django_db
class TestElectronicInvoice:
    def test_save_auto_progressive(self, association):
        invoice = ElectronicInvoice(number=1, year=2025, assoc=association)
        invoice.save()
        assert invoice.progressive == 1

    def test_save_auto_progressive_increments(self, association):
        # Create first invoice
        ElectronicInvoice.objects.create(progressive=5, number=1, year=2025, assoc=association)

        # Create second invoice
        invoice = ElectronicInvoice(number=2, year=2025, assoc=association)
        invoice.save()
        assert invoice.progressive == 6

    def test_save_auto_number(self, association):
        invoice = ElectronicInvoice(year=2025, assoc=association)
        invoice.save()
        assert invoice.number == 1

    def test_save_auto_number_increments(self, association):
        # Create first invoice for the year
        ElectronicInvoice.objects.create(progressive=1, number=5, year=2025, assoc=association)

        # Create second invoice for same year
        invoice = ElectronicInvoice(year=2025, assoc=association)
        invoice.save()
        assert invoice.number == 6


@pytest.mark.django_db
class TestAccountingItem:
    def test_str_representation(self, member):
        item = AccountingItemTransaction(member=member, value=Decimal("100.00"), assoc_id=1)
        # Since we can't save abstract class, test the string logic
        result = str(item)
        assert "Voce contabile" in result
        assert "AccountingItemTransaction" in result
        assert str(member) in result

    def test_short_descr_no_attribute(self, member):
        item = AccountingItemTransaction(member=member, value=Decimal("100.00"), assoc_id=1)
        assert item.short_descr() == ""

    def test_short_descr_with_attribute(self, member):
        item = AccountingItemDonation(
            member=member,
            value=Decimal("100.00"),
            assoc_id=1,
            descr="This is a very long description that should be truncated at one hundred characters to test the short_descr method works properly",
        )
        result = item.short_descr()
        assert len(result) == 100
        assert result == "This is a very long description that should be truncated at one hundred characters to test "


@pytest.mark.django_db
class TestAccountingItemOther:
    def test_str_credit_assignment(self, member, association):
        item = AccountingItemOther(
            member=member, value=Decimal("50.00"), assoc=association, oth=OtherChoices.CREDIT, descr="Test credit"
        )
        result = str(item)
        assert "Credit assignment" in result
        assert str(member) in result

    def test_str_token_assignment(self, member, association):
        item = AccountingItemOther(
            member=member, value=Decimal("5"), assoc=association, oth=OtherChoices.TOKEN, descr="Test tokens"
        )
        result = str(item)
        assert "Tokens assignment" in result
        assert str(member) in result

    def test_str_refund(self, member, association):
        item = AccountingItemOther(
            member=member, value=Decimal("100.00"), assoc=association, oth=OtherChoices.REFUND, descr="Test refund"
        )
        result = str(item)
        assert "Refund" in result
        assert str(member) in result


@pytest.mark.django_db
class TestAccountingItemExpense:
    @patch("larpmanager.models.accounting.download")
    def test_download(self, mock_download, member, association):
        item = AccountingItemExpense(
            member=member, value=Decimal("100.00"), assoc=association, descr="Test expense", exp=ExpenseChoices.COST
        )
        mock_invoice = Mock()
        mock_invoice.url = "http://example.com/invoice.pdf"
        item.invoice = mock_invoice
        mock_download.return_value = "download_link"

        result = item.download()
        mock_download.assert_called_once_with("http://example.com/invoice.pdf")
        assert result == "download_link"


@pytest.mark.django_db
class TestAccountingItemFlow:
    @patch("larpmanager.models.accounting.download")
    def test_download_with_invoice(self, mock_download, member, association, run):
        item = AccountingItemOutflow(
            member=member,
            value=Decimal("100.00"),
            assoc=association,
            run=run,
            descr="Test outflow",
            exp=ExpenseChoices.TRANS,
            balance=BalanceChoices.SERV,
            payment_date=date.today(),
        )
        mock_invoice = Mock()
        mock_invoice.url = "http://example.com/invoice.pdf"
        item.invoice = mock_invoice
        mock_download.return_value = "download_link"

        result = item.download()
        mock_download.assert_called_once_with("http://example.com/invoice.pdf")
        assert result == "download_link"

    def test_download_no_invoice(self, member, association, run):
        item = AccountingItemOutflow(
            member=member,
            value=Decimal("100.00"),
            assoc=association,
            run=run,
            descr="Test outflow",
            exp=ExpenseChoices.TRANS,
            balance=BalanceChoices.SERV,
            payment_date=date.today(),
        )
        item.invoice = None
        assert item.download() == ""


@pytest.mark.django_db
class TestDiscount:
    def test_str_representation(self, event):
        discount = Discount(
            name="Early Bird",
            value=Decimal("20.00"),
            typ=Discount.STANDARD,
            event=event,
            number=1,
            max_redeem=10,
            cod="EARLY20",
            visible=True,
            only_reg=True,
        )
        result = str(discount)
        assert "Early Bird" in result
        assert "(Standard)" in result
        assert "20.00" in result

    def test_show(self, event):
        discount = Discount(
            name="Early Bird",
            value=Decimal("20.00"),
            typ=Discount.STANDARD,
            event=event,
            number=1,
            max_redeem=10,
            cod="EARLY20",
            visible=True,
            only_reg=True,
        )
        result = discount.show()
        expected = {"value": Decimal("20.00"), "max_redeem": 10, "name": "Early Bird"}
        assert result == expected

    def test_show_event_with_runs(self, event, run):
        discount = Discount(
            name="Early Bird",
            value=Decimal("20.00"),
            typ=Discount.STANDARD,
            event=event,
            number=1,
            max_redeem=10,
            cod="EARLY20",
            visible=True,
            only_reg=True,
        )
        discount.save()
        discount.runs.add(run)

        result = discount.show_event()
        assert str(run) in result


@pytest.mark.django_db
class TestAccountingItemDiscount:
    def test_show_with_expires(self, member, association, run, event):
        discount = Discount.objects.create(
            name="Test Discount",
            value=Decimal("10.00"),
            typ=Discount.STANDARD,
            event=event,
            number=1,
            max_redeem=5,
            cod="TEST10",
            visible=True,
            only_reg=True,
        )

        expires_time = datetime.now().replace(hour=15, minute=30)
        item = AccountingItemDiscount(
            member=member, value=Decimal("10.00"), assoc=association, run=run, disc=discount, expires=expires_time
        )

        result = item.show()
        expected = {"name": "Test Discount", "value": Decimal("10.00"), "expires": "15:30"}
        assert result == expected

    def test_show_no_expires(self, member, association, run, event):
        discount = Discount.objects.create(
            name="Test Discount",
            value=Decimal("10.00"),
            typ=Discount.STANDARD,
            event=event,
            number=1,
            max_redeem=5,
            cod="TEST10",
            visible=True,
            only_reg=True,
        )

        item = AccountingItemDiscount(
            member=member, value=Decimal("10.00"), assoc=association, run=run, disc=discount, expires=None
        )

        result = item.show()
        expected = {"name": "Test Discount", "value": Decimal("10.00"), "expires": ""}
        assert result == expected


@pytest.mark.django_db
class TestCollection:
    def test_str_with_member(self, member, association):
        collection = Collection(
            member=member, organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        result = str(collection)
        assert f"Colletta per {member}" == result

    def test_str_with_name(self, member, association):
        collection = Collection(
            name="Birthday Gift", organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        result = str(collection)
        assert "Colletta per Birthday Gift" == result

    def test_display_member_with_member(self, member, association):
        collection = Collection(
            member=member, organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        with patch.object(member, "display_member", return_value="Member Display"):
            result = collection.display_member()
            assert result == "Member Display"

    def test_display_member_with_name(self, member, association):
        collection = Collection(
            name="Birthday Gift", organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        result = collection.display_member()
        assert result == "Birthday Gift"

    @patch("larpmanager.models.accounting.generate_id")
    def test_unique_contribute_code(self, mock_generate_id, member, association):
        mock_generate_id.return_value = "UNIQUE123CODE456"
        collection = Collection(
            name="Test Collection", organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        collection.unique_contribute_code()
        assert collection.contribute_code == "UNIQUE123CODE456"

    @patch("larpmanager.models.accounting.generate_id")
    def test_unique_contribute_code_collision(self, mock_generate_id, member, association):
        # Create existing collection with first code
        existing_collection = Collection.objects.create(
            name="Existing",
            organizer=member,
            assoc=association,
            total=0,
            status=CollectionStatus.OPEN,
            contribute_code="CODE1",
        )

        # Mock generate_id to return collision first, then unique code
        mock_generate_id.side_effect = ["CODE1", "CODE2"]

        collection = Collection(
            name="Test Collection", organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        collection.unique_contribute_code()
        assert collection.contribute_code == "CODE2"
        assert mock_generate_id.call_count == 2

    @patch("larpmanager.models.accounting.generate_id")
    def test_unique_redeem_code(self, mock_generate_id, member, association):
        mock_generate_id.return_value = "REDEEM123CODE456"
        collection = Collection(
            name="Test Collection", organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        collection.unique_redeem_code()
        assert collection.redeem_code == "REDEEM123CODE456"


@pytest.mark.django_db
class TestRefundRequest:
    def test_str_representation(self, member, association):
        refund = RefundRequest(
            member=member,
            assoc=association,
            details="Bank details: IBAN...",
            value=Decimal("50.00"),
            status=RefundStatus.REQUEST,
        )
        result = str(refund)
        assert f"Refund request of {member}" == result


@pytest.mark.django_db
class TestRecordAccounting:
    def test_creation(self, association, run):
        record = RecordAccounting.objects.create(
            assoc=association, run=run, global_sum=Decimal("1000.00"), bank_sum=Decimal("950.00")
        )
        assert record.assoc == association
        assert record.run == run
        assert record.global_sum == Decimal("1000.00")
        assert record.bank_sum == Decimal("950.00")


# Fixtures for tests
@pytest.fixture
def association():
    return Association.objects.create(name="Test Association", slug="test-assoc", email="test@example.com")


@pytest.fixture
def member():
    return Member.objects.create(username="testuser", email="test@example.com", first_name="Test", last_name="User")


@pytest.fixture
def event(association):
    return Event.objects.create(name="Test Event", assoc=association, number=1)


@pytest.fixture
def run(event):
    return Run.objects.create(event=event, number=1, name="Test Run", start=date.today(), end=date.today())


@pytest.fixture
def payment_method():
    return PaymentMethod.objects.create(name="Test Method", slug="test", fields="field1,field2")


@pytest.fixture
def payment_invoice(member, association, payment_method):
    return PaymentInvoice.objects.create(
        member=member,
        assoc=association,
        method=payment_method,
        typ=PaymentType.REGISTRATION,
        status=PaymentStatus.CREATED,
        mc_gross=Decimal("100.00"),
        mc_fee=Decimal("5.00"),
        causal="Test payment",
        cod="TEST123",
        txn_id="TXN456",
    )
