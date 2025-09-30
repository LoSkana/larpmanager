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

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from larpmanager.accounting.balance import (
    assoc_accounting,
    assoc_accounting_data,
    check_accounting,
    check_run_accounting,
    get_acc_detail,
    get_acc_reg_detail,
    get_acc_reg_type,
    get_run_accounting,
)
from larpmanager.accounting.invoice import (
    invoice_received_money,
    invoice_verify,
)

# Import all accounting utility modules
from larpmanager.accounting.member import (
    _info_collections,
    _info_donations,
    _info_membership,
    _info_token_credit,
    _init_choices,
    _init_pending,
    _init_regs,
    info_accounting,
)
from larpmanager.models.accounting import (
    AccountingItemPayment,
    PaymentChoices,
    PaymentStatus,
    PaymentType,
)
from larpmanager.models.registration import TicketTier
from larpmanager.tests.unit.base import BaseTestCase


class TestMemberAccountingUtils(TestCase, BaseTestCase):
    """Test member accounting utility functions"""

    def test_info_accounting(self):
        """Test main info_accounting function"""
        member = self.get_member()
        association = self.get_association()
        request = Mock()
        request.assoc = {"features": [], "id": association.id}

        ctx = {"member": member, "a_id": association.id}

        with patch("larpmanager.accounting.member.get_user_membership") as mock_membership:
            with patch("larpmanager.accounting.member._info_membership") as mock_info_membership:
                with patch("larpmanager.accounting.member._info_donations") as mock_info_donations:
                    with patch("larpmanager.accounting.member._info_collections") as mock_info_collections:
                        with patch("larpmanager.accounting.member._info_token_credit") as mock_info_token:
                            with patch("larpmanager.accounting.member.Registration") as mock_reg:
                                mock_reg.objects.filter.return_value.exclude.return_value.select_related.return_value = []

                                info_accounting(request, ctx)

                                mock_membership.assert_called_once_with(member, association.id)
                                mock_info_membership.assert_called_once()
                                mock_info_donations.assert_called_once()
                                mock_info_collections.assert_called_once()
                                mock_info_token.assert_called_once()

                                # Check that required context keys are set
                                assert "reg_list" in ctx
                                assert "payments_todo" in ctx
                                assert "payments_pending" in ctx
                                assert "refunds" in ctx

    def test_init_pending(self):
        """Test pending payment initialization"""
        # Create mock pending invoices
        invoice1 = Mock()
        invoice1.idx = 1
        invoice2 = Mock()
        invoice2.idx = 1
        invoice3 = Mock()
        invoice3.idx = 2

        with patch("larpmanager.accounting.member.PaymentInvoice.objects.filter") as mock_filter:
            mock_filter.return_value = [invoice1, invoice2, invoice3]

            member = self.get_member()
            result = _init_pending(member)

            # Should group by idx
            assert 1 in result
            assert 2 in result
            assert len(result[1]) == 2  # Two invoices for idx 1
            assert len(result[2]) == 1  # One invoice for idx 2

    def test_init_choices(self):
        """Test registration choice initialization"""
        # Create mock registration choices
        choice1 = Mock()
        choice1.reg_id = 1
        choice1.question_id = 10
        choice1.question = Mock()
        choice1.option = Mock()

        choice2 = Mock()
        choice2.reg_id = 1
        choice2.question_id = 10
        choice2.question = Mock()
        choice2.option = Mock()

        choice3 = Mock()
        choice3.reg_id = 1
        choice3.question_id = 20
        choice3.question = Mock()
        choice3.option = Mock()

        with patch("larpmanager.accounting.member.RegistrationChoice.objects.filter") as mock_filter:
            mock_filter.return_value.select_related.return_value = [choice1, choice2, choice3]

            member = self.get_member()
            result = _init_choices(member)

            # Should group by reg_id and question_id
            assert 1 in result
            assert 10 in result[1]
            assert 20 in result[1]
            assert len(result[1][10]["l"]) == 2  # Two options for question 10
            assert len(result[1][20]["l"]) == 1  # One option for question 20

    def test_init_regs(self):
        """Test registration initialization"""
        choices = {}
        ctx = {"reg_list": [], "payments_pending": [], "payments_todo": [], "reg_years": {}}
        pending = {}

        registration = self.get_registration()
        registration.id = 1
        registration.quota = 50
        registration.run.start = date(2025, 6, 15)

        with patch("larpmanager.accounting.member.datetime") as mock_datetime:
            mock_datetime.now.return_value.date.return_value = date(2025, 1, 1)

            _init_regs(choices, ctx, pending, registration)

            # Should add to reg_list
            assert registration in ctx["reg_list"]
            # Should add to payments_todo since quota > 0 and not pending
            assert registration in ctx["payments_todo"]
            # Should add year to reg_years
            assert 2025 in ctx["reg_years"]

    def test_init_regs_pending(self):
        """Test registration initialization with pending payment"""
        choices = {}
        ctx = {"reg_list": [], "payments_pending": [], "payments_todo": [], "reg_years": {}}
        registration = self.get_registration()
        registration.id = 1
        registration.quota = 50
        pending = {registration.id: [Mock()]}  # Has pending payment

        _init_regs(choices, ctx, pending, registration)

        # Should add to payments_pending instead of payments_todo
        assert registration in ctx["payments_pending"]
        assert registration not in ctx["payments_todo"]
        assert registration.pending is True

    def test_info_token_credit(self):
        """Test token and credit balance calculation"""
        member = self.get_member()
        association = self.get_association()
        ctx = {"a_id": association.id}

        # Mock queries
        with patch("larpmanager.accounting.member.AccountingItemOther.objects.filter") as mock_filter_other:
            with patch("larpmanager.accounting.member.AccountingItemExpense.objects.filter") as mock_filter_expense:
                mock_filter_other.return_value.count.return_value = 5  # 5 tokens/credits
                mock_filter_expense.return_value.count.return_value = 3  # 3 approved expenses

                _info_token_credit(ctx, member)

                assert ctx["acc_tokens"] == 5
                assert ctx["acc_credits"] == 8  # 3 expenses + 5 credits

    def test_info_collections_feature_disabled(self):
        """Test collections info when feature is disabled"""
        member = self.get_member()
        association = self.get_association()
        request = Mock()
        request.assoc = {"features": []}  # No collection feature

        ctx = {"a_id": association.id}

        _info_collections(ctx, member, request)

        # Should not add collections to context
        assert "collections" not in ctx
        assert "collection_gifts" not in ctx

    def test_info_collections_feature_enabled(self):
        """Test collections info when feature is enabled"""
        member = self.get_member()
        association = self.get_association()
        request = Mock()
        request.assoc = {"features": ["collection"]}

        ctx = {"a_id": association.id}

        with patch("larpmanager.accounting.member.Collection.objects.filter") as mock_collection:
            with patch("larpmanager.accounting.member.AccountingItemCollection.objects.filter") as mock_gifts:
                mock_collection.return_value = []
                mock_gifts.return_value = []

                _info_collections(ctx, member, request)

                assert "collections" in ctx
                assert "collection_gifts" in ctx

    def test_info_donations_feature_enabled(self):
        """Test donations info when feature is enabled"""
        member = self.get_member()
        association = self.get_association()
        request = Mock()
        request.assoc = {"features": ["donate"]}

        ctx = {"a_id": association.id}

        with patch("larpmanager.accounting.member.AccountingItemDonation.objects.filter") as mock_donations:
            mock_donations.return_value.order_by.return_value = []

            _info_donations(ctx, member, request)

            assert "donations" in ctx

    def test_info_membership_feature_enabled(self):
        """Test membership info when feature is enabled"""
        member = self.get_member()
        association = self.get_association()
        request = Mock()
        request.assoc = {"features": ["membership"]}

        ctx = {"a_id": association.id}

        with patch("larpmanager.accounting.member.datetime") as mock_datetime:
            mock_now = Mock()
            mock_now.year = 2025
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime
            mock_datetime.now.return_value.__lt__ = Mock(return_value=True)

            with patch("larpmanager.accounting.member.AccountingItemMembership.objects.filter") as mock_membership:
                with patch("larpmanager.accounting.member.PaymentInvoice.objects.filter") as mock_invoices:
                    mock_membership.return_value.order_by.return_value = []
                    mock_invoices.return_value.count.return_value = 0

                    with patch("larpmanager.accounting.member.Association.objects.get") as mock_assoc:
                        mock_assoc.return_value = association
                        self.get_association().get_config = Mock(
                            side_effect=lambda key, default: {"membership_day": "01-01", "membership_grazing": "3"}.get(
                                key, default
                            )
                        )

                        _info_membership(ctx, member, request)

                        assert "membership_fee" in ctx
                        assert "year_membership_fee" in ctx
                        assert "year" in ctx
                        assert "grazing" in ctx


class TestInvoiceUtils(TestCase, BaseTestCase):
    """Test invoice utility functions"""

    def test_invoice_verify_successful_match(self):
        """Test successful invoice verification from CSV"""
        payment_invoice = self.payment_invoice()
        request = Mock()
        ctx = {"todo": [payment_invoice]}

        # Create CSV content
        csv_content = "100,00,Test payment,other,data\n"
        csv_upload = Mock()
        csv_upload.read.return_value.decode.return_value = csv_content

        payment_invoice.verified = False
        payment_invoice.causal = "Test payment"
        payment_invoice.mc_gross = Decimal("100.00")
        payment_invoice.reg_cod = None
        payment_invoice.txn_id = None

        with patch("larpmanager.accounting.invoice.detect_delimiter") as mock_delimiter:
            mock_delimiter.return_value = ","
            with patch("larpmanager.accounting.invoice.clean") as mock_clean:
                mock_clean.side_effect = lambda x: x.lower().replace(" ", "")

                result = invoice_verify(request, ctx, csv_upload)

                assert result == 1
                assert payment_invoice.verified is True

    def test_invoice_verify_amount_mismatch(self):
        """Test invoice verification with amount mismatch"""
        payment_invoice = self.payment_invoice()
        request = Mock()
        ctx = {"todo": [payment_invoice]}

        # CSV with lower amount than invoice
        csv_content = "50,00,Test payment,other,data\n"
        csv_upload = Mock()
        csv_upload.read.return_value.decode.return_value = csv_content

        payment_invoice.verified = False
        payment_invoice.causal = "Test payment"
        payment_invoice.mc_gross = Decimal("100.00")  # Higher than CSV amount

        with patch("larpmanager.accounting.invoice.detect_delimiter") as mock_delimiter:
            mock_delimiter.return_value = ","
            with patch("larpmanager.accounting.invoice.clean") as mock_clean:
                mock_clean.side_effect = lambda x: x.lower().replace(" ", "")

                result = invoice_verify(request, ctx, csv_upload)

                assert result == 0  # No matches due to amount mismatch
                assert payment_invoice.verified is False

    def test_invoice_verify_by_registration_code(self):
        """Test invoice verification using registration code"""
        payment_invoice = self.payment_invoice()
        request = Mock()
        ctx = {"todo": [payment_invoice]}

        csv_content = "100,00,REG123456 payment,other,data\n"
        csv_upload = Mock()
        csv_upload.read.return_value.decode.return_value = csv_content

        payment_invoice.verified = False
        payment_invoice.causal = "Different causal"
        payment_invoice.mc_gross = Decimal("100.00")
        payment_invoice.reg_cod = "REG123456"  # Should match
        payment_invoice.txn_id = None

        with patch("larpmanager.accounting.invoice.detect_delimiter") as mock_delimiter:
            mock_delimiter.return_value = ","
            with patch("larpmanager.accounting.invoice.clean") as mock_clean:
                mock_clean.side_effect = lambda x: x.lower().replace(" ", "")

                result = invoice_verify(request, ctx, csv_upload)

                assert result == 1
                assert payment_invoice.verified is True

    def test_invoice_received_money_success(self):
        """Test successful payment processing"""
        with patch("larpmanager.accounting.invoice.PaymentInvoice.objects.get") as mock_get:
            mock_invoice = Mock()
            mock_invoice.status = PaymentStatus.CREATED
            mock_get.return_value = mock_invoice

            result = invoice_received_money(
                cod="TEST123", gross=Decimal("100.00"), fee=Decimal("5.00"), txn_id="TXN456"
            )

            assert result is True
            assert mock_invoice.mc_gross == Decimal("100.00")
            assert mock_invoice.mc_fee == Decimal("5.00")
            assert mock_invoice.txn_id == "TXN456"
            assert mock_invoice.status == PaymentStatus.CHECKED

    def test_invoice_received_money_already_processed(self):
        """Test payment already processed"""
        with patch("larpmanager.accounting.invoice.PaymentInvoice.objects.get") as mock_get:
            mock_invoice = Mock()
            mock_invoice.status = PaymentStatus.CHECKED  # Already processed
            mock_get.return_value = mock_invoice

            result = invoice_received_money(cod="TEST123")

            assert result is True
            # Should not change status again

    def test_invoice_received_money_invalid_code(self):
        """Test payment with invalid invoice code"""
        with patch("larpmanager.accounting.invoice.PaymentInvoice.objects.get") as mock_get:
            mock_get.side_effect = Exception("DoesNotExist")
            with patch("larpmanager.accounting.invoice.notify_admins") as mock_notify:
                result = invoice_received_money(cod="INVALID123")

                assert result is None
                mock_notify.assert_called_once()


class TestBalanceUtils(TestCase, BaseTestCase):
    """Test balance and accounting calculation utilities"""

    def test_get_acc_detail(self):
        """Test accounting detail calculation"""
        # Mock accounting items
        item1 = Mock()
        item1.value = Decimal("50.00")
        item1.pay = PaymentChoices.MONEY

        item2 = Mock()
        item2.value = Decimal("30.00")
        item2.pay = PaymentChoices.CREDIT

        with patch("larpmanager.accounting.balance.AccountingItemPayment.objects.filter") as mock_filter:
            mock_filter.return_value = [item1, item2]

            run = self.get_run()
            result = get_acc_detail(
                nm="Test Payments",
                run=run,
                descr="Test description",
                cls=AccountingItemPayment,
                cho=PaymentChoices.choices,
                typ="pay",
                reg=True,
            )

            assert result["name"] == "Test Payments"
            assert result["descr"] == "Test description"
            assert result["tot"] == Decimal("80.00")  # 50 + 30
            assert result["num"] == 2
            assert PaymentChoices.MONEY in result["detail"]
            assert PaymentChoices.CREDIT in result["detail"]

    def test_get_acc_reg_type_cancelled(self):
        """Test registration type for cancelled registration"""
        registration = self.get_registration()
        registration.cancellation_date = date.today()

        result = get_acc_reg_type(registration)

        assert result == ("can", "Disdetta")

    def test_get_acc_reg_type_with_ticket(self):
        """Test registration type with ticket"""
        registration = self.get_registration()
        registration.cancellation_date = None

        # Mock the ticket using a simple attribute assignment bypass
        mock_ticket = Mock()
        mock_ticket.tier = TicketTier.STANDARD
        # Bypass Django's model validation by setting directly on __dict__
        registration.__dict__["ticket"] = mock_ticket

        with patch("larpmanager.accounting.balance.get_display_choice") as mock_display:
            mock_display.return_value = "Standard Ticket"

            result = get_acc_reg_type(registration)

            assert result == (TicketTier.STANDARD, "Standard Ticket")

    def test_get_acc_reg_detail(self):
        """Test registration detail calculation"""
        # Mock registrations
        reg1 = Mock()
        reg1.ticket = Mock()
        reg1.ticket.tier = TicketTier.STANDARD
        reg1.tot_iscr = Decimal("100.00")

        reg2 = Mock()
        reg2.ticket = Mock()
        reg2.ticket.tier = TicketTier.STANDARD
        reg2.tot_iscr = Decimal("80.00")

        with patch("larpmanager.accounting.balance.Registration.objects.filter") as mock_filter:
            mock_filter.return_value.select_related.return_value.filter.return_value = [reg1, reg2]

            with patch("larpmanager.accounting.balance.get_acc_reg_type") as mock_get_type:
                mock_get_type.return_value = (TicketTier.STANDARD, "Standard")

                run = self.get_run()
                result = get_acc_reg_detail("Registrations", run, "Test registrations")

                assert result["tot"] == Decimal("180.00")  # 100 + 80
                assert result["num"] == 2
                assert TicketTier.STANDARD in result["detail"]

    def test_get_run_accounting(self):
        """Test comprehensive run accounting calculation"""
        ctx = {"token_name": "Game Tokens", "credit_name": "Event Credits"}

        with patch("larpmanager.accounting.balance.get_event_features") as mock_features:
            mock_features.return_value = ["expense", "payment", "inflow", "outflow", "refund", "token_credit"]

            with patch("larpmanager.accounting.balance.get_acc_detail") as mock_get_detail:
                # Mock different accounting detail calls
                mock_get_detail.side_effect = [
                    {"tot": Decimal("100.00"), "num": 2},  # expenses
                    {"tot": Decimal("50.00"), "num": 1},  # outflows
                    {"tot": Decimal("200.00"), "num": 3},  # inflows
                    {"tot": Decimal("500.00"), "num": 5},  # payments
                    {"tot": Decimal("25.00"), "num": 1},  # transactions
                    {"tot": Decimal("30.00"), "num": 1},  # refunds
                    {"tot": Decimal("10.00"), "num": 2},  # tokens
                    {"tot": Decimal("40.00"), "num": 1},  # credits
                ]

                with patch("larpmanager.accounting.balance.get_acc_reg_detail") as mock_reg_detail:
                    mock_reg_detail.return_value = {"tot": Decimal("600.00"), "num": 6}

                    run = self.get_run()
                    result = get_run_accounting(run, ctx)

                    # Check that revenue, costs, and balance are calculated
                    assert run.revenue == Decimal("445.00")  # 500 + 200 - (25 + 30)
                    assert run.costs == Decimal("200.00")  # 50 + 100 + 10 + 40
                    assert run.balance == Decimal("245.00")  # 445 - 200

    def test_check_accounting(self):
        """Test association accounting check"""
        with patch("larpmanager.accounting.balance.assoc_accounting") as mock_assoc:
            with patch("larpmanager.accounting.balance.RecordAccounting.objects.create") as mock_create:
                mock_ctx = {"global_sum": Decimal("1000.00"), "bank_sum": Decimal("950.00")}

                def update_ctx(ctx):
                    ctx.update(mock_ctx)

                mock_assoc.side_effect = update_ctx

                association = self.get_association()
                check_accounting(association.id)

                mock_assoc.assert_called_once()
                mock_create.assert_called_once_with(
                    assoc_id=association.id, global_sum=Decimal("1000.00"), bank_sum=Decimal("950.00")
                )

    def test_check_run_accounting(self):
        """Test run accounting check"""
        with patch("larpmanager.accounting.balance.get_run_accounting") as mock_get_run:
            with patch("larpmanager.accounting.balance.RecordAccounting.objects.create") as mock_create:
                run = self.get_run()
                run.balance = Decimal("100.00")

                check_run_accounting(run)

                mock_get_run.assert_called_once_with(run, {})
                mock_create.assert_called_once()

    def test_assoc_accounting_data(self):
        """Test association accounting data gathering"""
        association = self.get_association()
        ctx = {"a_id": association.id}
        year = 2025

        with patch("larpmanager.accounting.balance.get_sum") as mock_get_sum:
            mock_get_sum.return_value = Decimal("100.00")

            assoc_accounting_data(ctx, year)

            # Check that all sum fields are set
            assert ctx["outflow_exec_sum"] == Decimal("100.00")
            assert ctx["inflow_exec_sum"] == Decimal("100.00")
            assert ctx["membership_sum"] == Decimal("100.00")
            assert ctx["donations_sum"] == Decimal("100.00")
            assert ctx["collections_sum"] == Decimal("100.00")
            assert ctx["in_sum"] == Decimal("400.00")  # Sum of income sources minus transactions
            assert ctx["out_sum"] == Decimal("200.00")  # Sum of outflows and refunds

    def test_assoc_accounting(self):
        """Test comprehensive association accounting"""
        association = self.get_association()
        ctx = {"a_id": association.id}

        # Mock membership data
        mock_membership = Mock()
        mock_membership.member = Mock()
        mock_membership.credit = Decimal("50.00")
        mock_membership.tokens = Decimal("5")

        # Mock run data
        mock_run = Mock()
        mock_run.balance = Decimal("100.00")
        mock_run.development = "done"

        with patch("larpmanager.accounting.balance.Membership.objects.filter") as mock_membership_filter:
            mock_membership_filter.return_value.filter.return_value.select_related.return_value.order_by.return_value = [
                mock_membership
            ]

            with patch("larpmanager.accounting.balance.Run.objects.filter") as mock_run_filter:
                mock_run_filter.return_value.exclude.return_value.exclude.return_value.select_related.return_value.order_by.return_value = [
                    mock_run
                ]

                with patch("larpmanager.accounting.balance.assoc_accounting_data") as mock_data:
                    mock_data_ctx = {
                        "membership_sum": Decimal("200.00"),
                        "donations_sum": Decimal("100.00"),
                        "inflow_exec_sum": Decimal("50.00"),
                        "outflow_exec_sum": Decimal("30.00"),
                        "pay_money_sum": Decimal("500.00"),
                        "inflow_sum": Decimal("50.00"),
                        "outflow_sum": Decimal("30.00"),
                        "transactions_sum": Decimal("25.00"),
                        "refund_sum": Decimal("10.00"),
                    }

                    def update_ctx(ctx_to_update):
                        ctx_to_update.update(mock_data_ctx)

                    mock_data.side_effect = update_ctx

                    with patch("larpmanager.accounting.balance.Association.objects.get") as mock_get_assoc:
                        mock_get_assoc.return_value = association
                        association.created = datetime(2020, 1, 1)

                        with patch("larpmanager.accounting.balance.datetime") as mock_datetime:
                            mock_datetime.now.return_value.date.return_value.year = 2025

                            assoc_accounting(ctx)

                            # Check calculated values
                            assert ctx["tokens_sum"] == Decimal("5")
                            assert ctx["credits_sum"] == Decimal("50.00")
                            assert ctx["balance_sum"] == Decimal("100.00")
                            assert "global_sum" in ctx
                            assert "bank_sum" in ctx
                            assert "sum_year" in ctx


class TestBaseUtils(TestCase, BaseTestCase):
    """Test base accounting utility functions"""

    def test_is_reg_provisional_no_payment_feature(self):
        """Test registration is not provisional without payment feature"""
        from larpmanager.accounting.base import is_reg_provisional

        features = []  # No payment feature
        registration = self.get_registration()
        result = is_reg_provisional(registration, features)
        assert result is False

    def test_is_reg_provisional_payment_disabled(self):
        """Test registration is not provisional when provisional is disabled"""
        from larpmanager.accounting.base import is_reg_provisional

        registration = self.get_registration()
        registration.run.event.get_config = Mock(return_value=True)
        features = ["payment"]

        result = is_reg_provisional(registration, features)
        assert result is False

    def test_is_reg_provisional_with_payment(self):
        """Test registration is provisional with payment feature and unpaid balance"""
        from larpmanager.accounting.base import is_reg_provisional

        registration = self.get_registration()
        registration.run.event.get_config = Mock(return_value=False)
        registration.tot_iscr = Decimal("100.00")
        registration.tot_payed = Decimal("0.00")
        features = ["payment"]

        result = is_reg_provisional(registration, features)
        assert result is True

    def test_is_reg_provisional_fully_paid(self):
        """Test registration is not provisional when fully paid"""
        from larpmanager.accounting.base import is_reg_provisional

        registration = self.get_registration()
        registration.run.event.get_config = Mock(return_value=False)
        registration.tot_iscr = Decimal("100.00")
        registration.tot_payed = Decimal("100.00")
        features = ["payment"]

        result = is_reg_provisional(registration, features)
        assert result is False


class TestVatUtils(TestCase, BaseTestCase):
    """Test VAT calculation utilities"""

    def test_compute_vat_basic(self):
        """Test basic VAT computation"""
        from larpmanager.accounting.vat import compute_vat

        payment_item = self.payment_item()
        payment_item.assoc.get_config = Mock(
            side_effect=lambda key, default: {"vat_ticket": "22", "vat_options": "10"}.get(key, default)
        )

        payment_item.reg.pay_what = Decimal("50.00")
        mock_ticket = Mock()
        mock_ticket.price = Decimal("50.00")
        payment_item.value = Decimal("100.00")
        # Bypass Django's model validation by setting directly on __dict__
        payment_item.reg.__dict__["ticket"] = mock_ticket

        with patch("larpmanager.accounting.vat.get_previous_sum") as mock_get_sum:
            mock_get_sum.return_value = 0
            with patch("larpmanager.accounting.vat.AccountingItemTransaction.objects.filter") as mock_filter:
                mock_filter.return_value = []
                with patch("larpmanager.accounting.vat.AccountingItemPayment.objects.filter") as mock_update:
                    compute_vat(payment_item)
                    mock_update.assert_called_once()

    def test_get_previous_sum(self):
        """Test getting sum of previous payments"""
        from larpmanager.accounting.vat import get_previous_sum
        from larpmanager.models.accounting import AccountingItemPayment

        with patch("larpmanager.models.accounting.AccountingItemPayment.objects.filter") as mock_filter:
            mock_queryset = Mock()
            mock_queryset.aggregate.return_value = {"total": Decimal("50.00")}
            mock_filter.return_value = mock_queryset

            result = get_previous_sum(self.payment_item(), AccountingItemPayment)
            assert result == Decimal("50.00")

    def test_get_previous_sum_none(self):
        """Test getting sum when no previous payments"""
        from larpmanager.accounting.vat import get_previous_sum
        from larpmanager.models.accounting import AccountingItemPayment

        with patch("larpmanager.models.accounting.AccountingItemPayment.objects.filter") as mock_filter:
            mock_queryset = Mock()
            mock_queryset.aggregate.return_value = {"total": None}
            mock_filter.return_value = mock_queryset

            result = get_previous_sum(self.payment_item(), AccountingItemPayment)
            assert result == 0


class TestTokenCreditUtils(TestCase, BaseTestCase):
    """Test token and credit utility functions"""

    def test_registration_tokens_credits_use_no_remaining(self):
        """Test token/credit use with no remaining balance"""
        from larpmanager.accounting.token_credit import registration_tokens_credits_use

        remaining = Decimal("-10.00")  # Negative remaining
        registration = self.get_registration()
        registration_tokens_credits_use(registration, remaining, 1)
        # Should do nothing with negative remaining

    def test_registration_tokens_credits_use_tokens_only(self):
        """Test using tokens for payment"""
        from larpmanager.accounting.token_credit import registration_tokens_credits_use

        mock_membership = Mock()
        mock_membership.tokens = Decimal("10")
        mock_membership.credit = Decimal("0")

        with patch("larpmanager.accounting.token_credit.get_user_membership") as mock_get_membership:
            mock_get_membership.return_value = mock_membership
            with patch("larpmanager.accounting.token_credit.AccountingItemPayment.objects.create") as mock_create:
                registration = self.get_registration()
                registration_tokens_credits_use(registration, Decimal("5.00"), 1)

                assert mock_membership.tokens == Decimal("5")  # 10 - 5
                mock_create.assert_called_once()

    def test_registration_tokens_credits_overpay(self):
        """Test reversing overpayments"""
        from larpmanager.accounting.token_credit import registration_tokens_credits_overpay

        mock_payment = Mock()
        mock_payment.value = Decimal("10.00")

        with patch(
            "larpmanager.accounting.token_credit.AccountingItemPayment.objects.select_for_update"
        ) as mock_select:
            mock_queryset = Mock()
            mock_queryset.filter.return_value = mock_queryset
            mock_queryset.annotate.return_value = mock_queryset
            mock_queryset.order_by.return_value = [mock_payment]
            mock_select.return_value = mock_queryset

            registration = self.get_registration()
            registration_tokens_credits_overpay(registration, Decimal("5.00"), 1)

            assert mock_payment.value == Decimal("5.00")  # 10 - 5
            mock_payment.save.assert_called_once()

    def test_get_regs_paying_incomplete(self):
        """Test getting registrations with incomplete payments"""
        from larpmanager.accounting.token_credit import get_regs_paying_incomplete

        with patch("larpmanager.accounting.token_credit.get_regs") as mock_get_regs:
            mock_queryset = Mock()
            mock_get_regs.return_value = mock_queryset
            mock_queryset.annotate.return_value = mock_queryset
            mock_queryset.filter.return_value = []

            association = self.get_association()
            result = get_regs_paying_incomplete(association)
            mock_get_regs.assert_called_once_with(association)

    def test_update_token_credit_tokens(self):
        """Test updating member token balance"""
        from larpmanager.accounting.token_credit import update_token_credit

        with patch("larpmanager.accounting.token_credit.get_assoc_features") as mock_get_features:
            mock_get_features.return_value = ["token_credit"]

            with patch("larpmanager.accounting.token_credit.get_user_membership") as mock_get_membership:
                mock_membership = Mock()
                mock_membership.tokens = Decimal("0")
                mock_get_membership.return_value = mock_membership

                with patch("larpmanager.accounting.token_credit.get_sum") as mock_get_sum:
                    mock_get_sum.side_effect = [Decimal("10"), Decimal("5")]  # given, used

                    update_token_credit(self.other_item_token(), token=True)

                    assert mock_membership.tokens == Decimal("5")  # 10 - 5
                    mock_membership.save.assert_called_once()

    def test_update_token_credit_credits(self):
        """Test updating member credit balance"""
        from larpmanager.accounting.token_credit import update_token_credit

        with patch("larpmanager.accounting.token_credit.get_assoc_features") as mock_get_features:
            mock_get_features.return_value = ["token_credit"]

            with patch("larpmanager.accounting.token_credit.get_user_membership") as mock_get_membership:
                mock_membership = Mock()
                mock_membership.credit = Decimal("0")
                mock_get_membership.return_value = mock_membership

                with patch("larpmanager.accounting.token_credit.get_sum") as mock_get_sum:
                    mock_get_sum.side_effect = [
                        Decimal("20"),
                        Decimal("10"),
                        Decimal("5"),
                        Decimal("2"),
                    ]  # expenses, given, used, refunded

                    update_token_credit(self.other_item_credit(), token=False)

                    assert mock_membership.credit == Decimal("23")  # 20 + 10 - 5 - 2
                    mock_membership.save.assert_called_once()

    def test_handle_tokes_credits_disabled(self):
        """Test token/credit handling when feature is disabled"""
        from larpmanager.accounting.token_credit import handle_tokes_credits

        features = []  # No token_credit feature

        with patch("larpmanager.accounting.token_credit.registration_tokens_credits_use") as mock_use:
            registration = self.get_registration()
            handle_tokes_credits(1, features, registration, Decimal("10.00"))
            mock_use.assert_not_called()


class TestPaymentUtils(TestCase, BaseTestCase):
    """Test payment utility functions"""

    def test_get_payment_fee(self):
        """Test getting payment fee for method"""
        from larpmanager.accounting.payment import get_payment_fee

        with patch("larpmanager.accounting.payment.get_payment_details") as mock_get_details:
            mock_get_details.return_value = {"paypal_fee": "2.5"}

            association = self.get_association()
            result = get_payment_fee(association, "paypal")
            assert result == 2.5

    def test_get_payment_fee_no_config(self):
        """Test getting payment fee when not configured"""
        from larpmanager.accounting.payment import get_payment_fee

        with patch("larpmanager.accounting.payment.get_payment_details") as mock_get_details:
            mock_get_details.return_value = {}

            association = self.get_association()
            result = get_payment_fee(association, "paypal")
            assert result == 0.0

    def test_unique_invoice_cod(self):
        """Test generating unique invoice code"""
        from larpmanager.accounting.payment import unique_invoice_cod

        with patch("larpmanager.accounting.payment.generate_id") as mock_generate:
            mock_generate.return_value = "UNIQUE123456"
            with patch("larpmanager.accounting.payment.PaymentInvoice.objects.filter") as mock_filter:
                mock_filter.return_value.exists.return_value = False

                result = unique_invoice_cod()
                assert result == "UNIQUE123456"

    def test_unique_invoice_cod_collision(self):
        """Test generating unique invoice code with collision"""
        from larpmanager.accounting.payment import unique_invoice_cod

        with patch("larpmanager.accounting.payment.generate_id") as mock_generate:
            mock_generate.side_effect = ["COLLISION", "UNIQUE123456"]
            with patch("larpmanager.accounting.payment.PaymentInvoice.objects.filter") as mock_filter:
                mock_filter.return_value.exists.side_effect = [True, False]

                result = unique_invoice_cod()
                assert result == "UNIQUE123456"

    def test_round_up_to_two_decimals(self):
        """Test rounding up to two decimal places"""
        from larpmanager.accounting.payment import round_up_to_two_decimals

        assert round_up_to_two_decimals(1.234) == 1.24
        assert round_up_to_two_decimals(1.231) == 1.24
        assert round_up_to_two_decimals(1.200) == 1.20

    def test_update_invoice_gross_fee(self):
        """Test updating invoice with gross amount and fees"""
        from larpmanager.accounting.payment import update_invoice_gross_fee

        payment_invoice = self.payment_invoice()
        association = association
        request = Mock()
        pay_method = Mock()
        pay_method.slug = "paypal"

        self.get_association().get_config = Mock(
            side_effect=lambda key, default: {"payment_fees_user": True}.get(key, default)
        )

        with patch("larpmanager.accounting.payment.get_payment_fee") as mock_get_fee:
            mock_get_fee.return_value = 2.5

            result = update_invoice_gross_fee(request, payment_invoice, Decimal("100.00"), association, pay_method)

            assert payment_invoice.mc_gross == result
            assert payment_invoice.mc_fee > 0

    def test_payment_received_registration(self):
        """Test processing received registration payment"""
        from larpmanager.accounting.payment import payment_received

        payment_invoice = self.payment_invoice()
        payment_invoice.typ = PaymentType.REGISTRATION
        payment_invoice.idx = 1

        with patch("larpmanager.accounting.payment.Association.objects.get") as mock_get_assoc:
            mock_assoc = Mock()
            mock_get_assoc.return_value = mock_assoc

            with patch("larpmanager.accounting.payment.get_assoc_features") as mock_get_features:
                mock_get_features.return_value = []

                with patch("larpmanager.accounting.payment._process_payment") as mock_process:
                    result = payment_received(payment_invoice)
                    assert result is True
                    mock_process.assert_called_once()


class TestRegistrationUtils(TestCase, BaseTestCase):
    """Test registration accounting utility functions"""

    def test_get_reg_iscr_basic(self):
        """Test basic registration signup fee calculation"""
        from larpmanager.accounting.registration import get_reg_iscr

        registration = self.get_registration()
        registration.ticket = Mock()
        registration.ticket.price = Decimal("100.00")
        registration.additionals = 0
        registration.pay_what = None
        registration.redeem_code = None
        registration.surcharge = Decimal("10.00")

        with patch("larpmanager.accounting.registration.RegistrationChoice.objects.filter") as mock_choices:
            mock_choices.return_value.select_related.return_value = []

            with patch("larpmanager.accounting.registration.AccountingItemDiscount.objects.filter") as mock_discounts:
                mock_discounts.return_value.select_related.return_value = []

                result = get_reg_iscr(registration)
                assert result == Decimal("110.00")  # 100 + 10

    def test_get_reg_iscr_with_discounts(self):
        """Test registration fee with discounts"""
        from larpmanager.accounting.registration import get_reg_iscr

        registration = self.get_registration()
        registration.ticket = Mock()
        registration.ticket.price = Decimal("100.00")
        registration.additionals = 0
        registration.pay_what = None
        registration.redeem_code = None
        registration.surcharge = Decimal("0.00")

        mock_discount = Mock()
        mock_discount.disc = Mock()
        mock_discount.disc.value = Decimal("20.00")

        with patch("larpmanager.accounting.registration.RegistrationChoice.objects.filter") as mock_choices:
            mock_choices.return_value.select_related.return_value = []

            with patch("larpmanager.accounting.registration.AccountingItemDiscount.objects.filter") as mock_discounts:
                mock_discounts.return_value.select_related.return_value = [mock_discount]

                result = get_reg_iscr(registration)
                assert result == Decimal("80.00")  # 100 - 20

    def test_get_reg_payments(self):
        """Test calculating total payments for registration"""
        from larpmanager.accounting.registration import get_reg_payments

        mock_payment1 = Mock()
        mock_payment1.pay = "money"
        mock_payment1.value = Decimal("50.00")

        mock_payment2 = Mock()
        mock_payment2.pay = "credit"
        mock_payment2.value = Decimal("30.00")

        mock_payments = [mock_payment1, mock_payment2]

        registration = self.get_registration()
        result = get_reg_payments(registration, mock_payments)
        assert result == Decimal("80.00")
        assert registration.payments == {"money": Decimal("50.00"), "credit": Decimal("30.00")}

    def test_get_reg_transactions(self):
        """Test calculating transaction fees for registration"""
        from larpmanager.accounting.registration import get_reg_transactions

        mock_transaction = Mock()
        mock_transaction.value = Decimal("2.50")

        with patch("larpmanager.accounting.registration.AccountingItemTransaction.objects.filter") as mock_filter:
            mock_filter.return_value = [mock_transaction]
            registration = self.get_registration()
            result = get_reg_transactions(registration)
            assert result == Decimal("2.50")

    def test_get_date_surcharge_staff_ticket(self):
        """Test no surcharge for staff tickets"""
        from larpmanager.accounting.registration import get_date_surcharge
        from larpmanager.models.registration import TicketTier

        registration = self.get_registration()
        event = self.get_event()
        registration.ticket = Mock()
        registration.ticket.tier = TicketTier.STAFF

        result = get_date_surcharge(registration, event)
        assert result == 0

    def test_get_date_surcharge_with_surcharges(self):
        """Test surcharge calculation with date-based surcharges"""
        from larpmanager.accounting.registration import get_date_surcharge
        from larpmanager.models.registration import TicketTier

        registration = self.get_registration()
        event = self.get_event()
        registration.ticket = Mock()
        registration.ticket.tier = TicketTier.STANDARD
        registration.created = date.today()

        mock_surcharge1 = Mock()
        mock_surcharge1.amount = Decimal("10.00")
        mock_surcharge2 = Mock()
        mock_surcharge2.amount = Decimal("5.00")

        with patch("larpmanager.accounting.registration.RegistrationSurcharge.objects.filter") as mock_filter:
            mock_filter.return_value = [mock_surcharge1, mock_surcharge2]

            result = get_date_surcharge(registration, event)
            assert result == Decimal("15.00")  # 10 + 5

    def test_quota_check(self):
        """Test payment quota calculation"""
        from larpmanager.accounting.registration import quota_check

        registration = self.get_registration()
        registration.quotas = 4
        registration.tot_iscr = Decimal("400.00")
        registration.tot_payed = Decimal("100.00")
        registration.created = Mock()
        registration.created.date.return_value = date.today() - timedelta(days=60)

        start_date = date.today() + timedelta(days=30)
        alert = 7

        with patch("larpmanager.accounting.registration.get_time_diff_today") as mock_time_diff:
            mock_time_diff.return_value = 30

            with patch("larpmanager.accounting.registration.get_time_diff") as mock_time_diff2:
                mock_time_diff2.return_value = 90

                with patch("larpmanager.accounting.registration.get_payment_deadline") as mock_deadline:
                    mock_deadline.return_value = 5  # Less than alert

                    quota_check(registration, start_date, alert, 1)

                    assert hasattr(registration, "quota")
                    assert hasattr(registration, "deadline")

    def test_cancel_reg(self):
        """Test registration cancellation"""
        from larpmanager.accounting.registration import cancel_reg

        with patch("larpmanager.accounting.registration.RegistrationCharacterRel.objects.filter") as mock_char_filter:
            with patch("larpmanager.accounting.registration.AssignmentTrait.objects.filter") as mock_trait_filter:
                with patch(
                    "larpmanager.accounting.registration.AccountingItemDiscount.objects.filter"
                ) as mock_discount_filter:
                    with patch(
                        "larpmanager.accounting.registration.AccountingItemOther.objects.filter"
                    ) as mock_other_filter:
                        with patch("larpmanager.accounting.registration.reset_event_links") as mock_reset:
                            registration = self.get_registration()
                            cancel_reg(registration)

                            assert registration.cancellation_date is not None
                            mock_char_filter.assert_called_once()
                            mock_trait_filter.assert_called_once()
                            mock_discount_filter.assert_called_once()
                            mock_other_filter.assert_called_once()
                            mock_reset.assert_called_once()

    def test_round_to_nearest_cent(self):
        """Test rounding to nearest cent with tolerance"""
        from larpmanager.accounting.registration import round_to_nearest_cent

        assert round_to_nearest_cent(10.02) == 10.0
        assert round_to_nearest_cent(10.04) == 10.0  # Within tolerance
        assert round_to_nearest_cent(10.05) == 10.05  # Outside tolerance
