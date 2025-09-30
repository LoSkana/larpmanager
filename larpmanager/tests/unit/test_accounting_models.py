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
from unittest.mock import Mock, PropertyMock, patch

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
    RecordAccounting,
    RefundRequest,
    RefundStatus,
)
from larpmanager.tests.unit.base import BaseTestCase


class TestPaymentInvoice(TestCase, BaseTestCase):
    def test_str_representation(self):
        invoice = self.invoice()
        expected = f"({self.invoice().status}) Invoice for {self.invoice().member} - {self.invoice().causal} - {self.invoice().txn_id} {self.invoice().mc_gross} {self.invoice().mc_fee}"
        assert str(self.invoice()) == expected

    def test_download_no_invoice(self):
        invoice = self.invoice()
        self.invoice().invoice = None
        assert self.invoice().download() == ""

    def test_download_no_name(self):
        invoice = self.invoice()
        mock_invoice = Mock()
        mock_invoice.name = ""
        self.invoice().invoice = mock_invoice
        assert self.invoice().download() == ""

    @patch("larpmanager.models.accounting.download")
    def test_download_with_file(self, mock_download):
        invoice = self.invoice()
        mock_invoice = Mock()
        mock_invoice.name = "test.pdf"
        mock_invoice.url = "http://example.com/test.pdf"
        invoice.invoice = mock_invoice
        mock_download.return_value = "download_link"

        result = invoice.download()
        mock_download.assert_called_once_with("http://example.com/test.pdf")
        assert result == "download_link"

    def test_get_details_no_method(self):
        invoice = self.invoice()
        # Mock the method property to return None using PropertyMock
        with patch.object(type(self.invoice()), "method", new_callable=PropertyMock) as mock_method:
            mock_method.return_value = None
            assert self.invoice().get_details() == ""

    def test_get_details_with_invoice(self):
        invoice = self.invoice()
        mock_invoice = Mock()
        mock_invoice.url = "http://example.com/test.pdf"
        invoice.invoice = mock_invoice
        invoice.text = "Test text"
        invoice.cod = "TEST123"

        with patch.object(invoice, "download", return_value="download_link"):
            result = invoice.get_details()
            assert " <a href='download_link'>Download</a>" in result
            assert " Test text" in result
            assert " TEST123" in result


class TestElectronicInvoice(TestCase, BaseTestCase):
    def test_save_auto_progressive(self):
        association = self.get_association()
        invoice = ElectronicInvoice(number=1, year=2025, assoc=association)
        invoice.save()
        assert invoice.progressive == 1

    def test_save_auto_progressive_increments(self):
        association = self.get_association()
        # Create first invoice
        ElectronicInvoice.objects.create(progressive=5, number=1, year=2025, assoc=association)

        # Create second invoice
        invoice = ElectronicInvoice(number=2, year=2025, assoc=association)
        invoice.save()
        assert invoice.progressive == 6

    def test_save_auto_number(self):
        association = self.get_association()
        invoice = ElectronicInvoice(year=2025, assoc=association)
        invoice.save()
        assert invoice.number == 1

    def test_save_auto_number_increments(self):
        association = self.get_association()
        # Create first invoice for the year
        ElectronicInvoice.objects.create(progressive=1, number=5, year=2025, assoc=association)

        # Create second invoice for same year
        invoice = ElectronicInvoice(year=2025, assoc=association)
        invoice.save()
        assert invoice.number == 6


class TestAccountingItem(TestCase, BaseTestCase):
    def test_str_representation(self):
        member = self.get_member()
        item = AccountingItemTransaction(member=member, value=Decimal("100.00"), assoc_id=1)
        # Since we can't save abstract class, test the string logic
        result = str(item)
        assert "Voce contabile" in result
        assert "AccountingItemTransaction" in result
        assert str(member) in result

    def test_short_descr_no_attribute(self):
        member = self.get_member()
        item = AccountingItemTransaction(member=member, value=Decimal("100.00"), assoc_id=1)
        assert item.short_descr() == ""

    def test_short_descr_with_attribute(self):
        member = self.get_member()
        item = AccountingItemDonation(
            member=member,
            value=Decimal("100.00"),
            assoc_id=1,
            descr="This is a very long description that should be truncated at one hundred characters to test the short_descr method works properly",
        )
        result = item.short_descr()
        assert len(result) == 100
        assert (
            result
            == "This is a very long description that should be truncated at one hundred characters to test the short"
        )


class TestAccountingItemOther(TestCase, BaseTestCase):
    def test_str_credit_assignment(self):
        member = self.get_member()
        association = self.get_association()
        item = AccountingItemOther(
            member=member, value=Decimal("50.00"), assoc=association, oth=OtherChoices.CREDIT, descr="Test credit"
        )
        result = str(item)
        assert "Credit assignment" in result
        assert str(member) in result

    def test_str_token_assignment(self):
        member = self.get_member()
        association = self.get_association()
        item = AccountingItemOther(
            member=member, value=Decimal("5"), assoc=association, oth=OtherChoices.TOKEN, descr="Test tokens"
        )
        result = str(item)
        assert "Tokens assignment" in result
        assert str(member) in result

    def test_str_refund(self):
        member = self.get_member()
        association = self.get_association()
        item = AccountingItemOther(
            member=member, value=Decimal("100.00"), assoc=association, oth=OtherChoices.REFUND, descr="Test refund"
        )
        result = str(item)
        assert "Refund" in result
        assert str(member) in result


class TestAccountingItemExpense(TestCase, BaseTestCase):
    @patch("larpmanager.models.accounting.download")
    def test_download(self, mock_download):
        member = self.get_member()
        association = self.get_association()
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


class TestAccountingItemFlow(TestCase, BaseTestCase):
    @patch("larpmanager.models.accounting.download")
    def test_download_with_invoice(self, mock_download):
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
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

    def test_download_no_invoice(self):
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
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


class TestDiscount(TestCase, BaseTestCase):
    def test_str_representation(self):
        event = self.get_event()
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

    def test_show(self):
        event = self.get_event()
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

    def test_show_event_with_runs(self):
        event = self.get_event()
        run = self.get_run()
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


class TestAccountingItemDiscount(TestCase, BaseTestCase):
    def test_show_with_expires(self):
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        event = self.get_event()
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

    def test_show_no_expires(self):
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        event = self.get_event()
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


class TestCollection(TestCase, BaseTestCase):
    def test_str_with_member(self):
        member = self.get_member()
        association = self.get_association()
        collection = Collection(
            member=member, organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        result = str(collection)
        assert f"Colletta per {member}" == result

    def test_str_with_name(self):
        member = self.get_member()
        association = self.get_association()
        collection = Collection(
            name="Birthday Gift", organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        result = str(collection)
        assert "Colletta per Birthday Gift" == result

    def test_display_member_with_member(self):
        member = self.get_member()
        association = self.get_association()
        collection = Collection(
            member=member, organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        with patch.object(member, "display_member", return_value="Member Display"):
            result = collection.display_member()
            assert result == "Member Display"

    def test_display_member_with_name(self):
        member = self.get_member()
        association = self.get_association()
        collection = Collection(
            name="Birthday Gift", organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        result = collection.display_member()
        assert result == "Birthday Gift"

    @patch("larpmanager.models.accounting.generate_id")
    def test_unique_contribute_code(self, mock_generate_id):
        member = self.get_member()
        association = self.get_association()
        mock_generate_id.return_value = "UNIQUE123CODE456"
        collection = Collection(
            name="Test Collection", organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        collection.unique_contribute_code()
        assert collection.contribute_code == "UNIQUE123CODE456"

    def test_unique_contribute_code_collision(self):
        member = self.get_member()
        association = self.get_association()
        # Create existing collection with first code (no mocking yet)
        existing_collection = Collection(
            name="Existing",
            organizer=member,
            assoc=association,
            total=0,
            status=CollectionStatus.OPEN,
        )
        existing_collection.save()
        # Set the contribute_code after saving to avoid auto-generation
        Collection.objects.filter(id=existing_collection.id).update(contribute_code="CODE1")
        existing_collection.refresh_from_db()

        # Now apply the mock for generate_id
        with patch("larpmanager.models.accounting.generate_id") as mock_generate_id:
            # Mock generate_id to return collision first, then unique code
            mock_generate_id.side_effect = ["CODE1", "CODE2"]

            collection = Collection(
                name="Test Collection", organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
            )
            collection.unique_contribute_code()
            assert collection.contribute_code == "CODE2"
            assert mock_generate_id.call_count == 2

    @patch("larpmanager.models.accounting.generate_id")
    def test_unique_redeem_code(self, mock_generate_id):
        member = self.get_member()
        association = self.get_association()
        mock_generate_id.return_value = "REDEEM123CODE456"
        collection = Collection(
            name="Test Collection", organizer=member, assoc=association, total=0, status=CollectionStatus.OPEN
        )
        collection.unique_redeem_code()
        assert collection.redeem_code == "REDEEM123CODE456"


class TestRefundRequest(TestCase, BaseTestCase):
    def test_str_representation(self):
        member = self.get_member()
        association = self.get_association()
        refund = RefundRequest(
            member=member,
            assoc=association,
            details="Bank details: IBAN...",
            value=Decimal("50.00"),
            status=RefundStatus.REQUEST,
        )
        result = str(refund)
        assert f"Refund request of {member}" == result


class TestRecordAccounting(TestCase, BaseTestCase):
    def test_creation(self):
        association = self.get_association()
        run = self.get_run()
        record = RecordAccounting.objects.create(
            assoc=association, run=run, global_sum=Decimal("1000.00"), bank_sum=Decimal("950.00")
        )
        assert record.assoc == association
        assert record.run == run
        assert record.global_sum == Decimal("1000.00")
        assert record.bank_sum == Decimal("950.00")
