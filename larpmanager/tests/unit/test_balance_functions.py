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

"""Tests for balance calculation and accounting summary functions"""

from decimal import Decimal
from unittest.mock import patch

from larpmanager.accounting.balance import (
    association_accounting,
    association_accounting_data,
    get_acc_detail,
    get_acc_reg_detail,
    get_acc_reg_type,
    get_run_accounting,
)
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemExpense,
    AccountingItemOther,
    AccountingItemPayment,
    AccountingItemTransaction,
    Discount,
    ExpenseChoices,
    OtherChoices,
    PaymentChoices, DiscountType,
)
from larpmanager.models.event import DevelopStatus
from larpmanager.models.registration import TicketTier
from larpmanager.tests.unit.base import BaseTestCase


class TestAccDetailFunctions(BaseTestCase):
    """Test cases for accounting detail calculation functions"""

    def test_get_acc_detail_with_payments(self) -> None:
        """Test getting detailed accounting breakdown for payments"""
        run = self.get_run()
        member = self.get_member()
        association = self.get_association()
        registration = self.create_registration(member=member, run=run)

        # Create payments
        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("100.00")
        )
        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("50.00")
        )

        result = get_acc_detail(
            "Test Payments", run, "Test description", AccountingItemPayment, PaymentChoices.choices, "pay", filter_by_registration=True
        )

        self.assertEqual(result["name"], "Test Payments")
        self.assertEqual(result["descr"], "Test description")
        self.assertEqual(result["num"], 2)
        self.assertEqual(result["tot"], Decimal("150.00"))
        self.assertIn(PaymentChoices.MONEY, result["detail"])

    def test_get_acc_detail_with_expenses(self) -> None:
        """Test getting detailed accounting breakdown for expenses"""
        run = self.get_run()
        member = self.get_member()
        association = self.get_association()

        # Create expenses
        AccountingItemExpense.objects.create(
            member=member, association=association, run=run, exp=ExpenseChoices.LOCAT, value=Decimal("200.00"), is_approved=True
        )
        AccountingItemExpense.objects.create(
            member=member, association=association, run=run, exp=ExpenseChoices.COST, value=Decimal("150.00"), is_approved=True
        )

        result = get_acc_detail(
            "Test Expenses", run, "Test description", AccountingItemExpense, ExpenseChoices.choices, "exp"
        )

        self.assertEqual(result["num"], 2)
        self.assertEqual(result["tot"], Decimal("350.00"))
        self.assertIn(ExpenseChoices.LOCAT, result["detail"])
        self.assertIn(ExpenseChoices.COST, result["detail"])

    def test_get_acc_detail_with_filters(self) -> None:
        """Test get_acc_detail with additional filters"""
        run = self.get_run()
        member = self.get_member()
        association = self.get_association()

        # Create other items with different types
        AccountingItemOther.objects.create(
            member=member, association=association, run=run, oth=OtherChoices.TOKEN, value=Decimal("50.00"), cancellation=False
        )
        AccountingItemOther.objects.create(
            member=member, association=association, run=run, oth=OtherChoices.CREDIT, value=Decimal("30.00"), cancellation=True
        )

        # Filter only non-cancelled
        result = get_acc_detail(
            "Test Other",
            run,
            "Test description",
            AccountingItemOther,
            OtherChoices.choices,
            "oth",
            filters={"cancellation__exact": False},
        )

        self.assertEqual(result["num"], 1)
        self.assertEqual(result["tot"], Decimal("50.00"))

    def test_get_acc_detail_empty(self) -> None:
        """Test get_acc_detail with no items"""
        run = self.get_run()

        result = get_acc_detail(
            "Empty", run, "No items", AccountingItemPayment, PaymentChoices.choices, "pay", filter_by_registration=True
        )

        self.assertEqual(result["num"], 0)
        self.assertEqual(result["tot"], 0)
        self.assertEqual(result["detail"], {})


class TestRegDetailFunctions(BaseTestCase):
    """Test cases for registration detail functions"""

    def test_get_acc_reg_type_cancelled(self) -> None:
        """Test registration type for cancelled registration"""
        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        from datetime import datetime
        registration.cancellation_date = datetime.now()
        registration.save()

        typ, descr = get_acc_reg_type(registration)

        self.assertEqual(typ, "can")
        self.assertEqual(descr, "Disdetta")

    def test_get_acc_reg_type_with_ticket(self) -> None:
        """Test registration type with ticket tier"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, tier=TicketTier.PATRON)
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        typ, descr = get_acc_reg_type(registration)

        self.assertEqual(typ, TicketTier.PATRON)
        self.assertIsNotNone(descr)

    def test_get_acc_reg_type_no_ticket(self) -> None:
        """Test registration type without ticket"""
        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run, ticket=None)

        typ, descr = get_acc_reg_type(registration)

        self.assertEqual(typ, "")
        self.assertEqual(descr, "")

    def test_get_acc_reg_detail(self) -> None:
        """Test getting registration detail breakdown"""
        run = self.get_run()
        member1 = self.get_member()
        member2 = self.get_member()

        ticket1 = self.ticket(event=run.event, price=Decimal("100.00"), tier=TicketTier.PATRON)
        ticket2 = self.ticket(event=run.event, price=Decimal("50.00"), tier=TicketTier.STANDARD)

        reg1 = self.create_registration(member=member1, run=run, ticket=ticket1, tot_iscr=Decimal("100.00"))
        reg2 = self.create_registration(member=member2, run=run, ticket=ticket2, tot_iscr=Decimal("50.00"))

        result = get_acc_reg_detail("Registrations", run, "Total registrations")

        self.assertEqual(result["name"], "Registrations")
        self.assertEqual(result["num"], 2)
        self.assertEqual(result["tot"], Decimal("150.00"))
        self.assertIn(TicketTier.PATRON, result["detail"])
        self.assertIn(TicketTier.STANDARD, result["detail"])


class TestRunAccountingFunctions(BaseTestCase):
    """Test cases for run accounting calculation"""

    @patch("larpmanager.accounting.balance.get_event_features")
    def test_get_run_accounting_basic(self, mock_features) -> None:
        """Test basic run accounting calculation"""
        mock_features.return_value = {"payment": True}

        run = self.get_run()
        run.development = DevelopStatus.SHOW
        run.save()

        member = self.get_member()
        association = self.get_association()
        registration = self.create_registration(member=member, run=run, tot_iscr=Decimal("100.00"))

        # Create payment
        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("100.00")
        )

        result = get_run_accounting(run, {})

        self.assertIn("pay", result)
        self.assertEqual(result["pay"]["tot"], Decimal("100.00"))

        run.refresh_from_db()
        self.assertGreaterEqual(run.revenue, Decimal("0.00"))

    @patch("larpmanager.accounting.balance.get_event_features")
    def test_get_run_accounting_with_expenses(self, mock_features) -> None:
        """Test run accounting with expenses"""
        mock_features.return_value = {"payment": True, "expense": True}

        run = self.get_run()
        run.development = DevelopStatus.SHOW
        run.save()

        member = self.get_member()
        association = self.get_association()

        # Create expense
        AccountingItemExpense.objects.create(
            member=member, association=association, run=run, exp=ExpenseChoices.LOCAT, value=Decimal("50.00"), is_approved=True
        )

        result = get_run_accounting(run, {})

        self.assertIn("exp", result)
        self.assertEqual(result["exp"]["tot"], Decimal("50.00"))

        run.refresh_from_db()
        self.assertEqual(run.costs, Decimal("50.00"))

    @patch("larpmanager.accounting.balance.get_event_features")
    def test_get_run_accounting_with_tokens_credits(self, mock_features) -> None:
        """Test run accounting with tokens and credits"""
        mock_features.return_value = {"payment": True, "token_credit": True}

        run = self.get_run()
        run.development = DevelopStatus.SHOW
        run.save()

        member = self.get_member()
        association = self.get_association()

        # Create tokens and credits
        AccountingItemOther.objects.create(
            member=member, association=association, run=run, oth=OtherChoices.TOKEN, value=Decimal("20.00"), cancellation=False
        )
        AccountingItemOther.objects.create(
            member=member, association=association, run=run, oth=OtherChoices.CREDIT, value=Decimal("30.00"), cancellation=False
        )

        result = get_run_accounting(run, {"token_name": "Tokens", "credit_name": "Credits"})

        self.assertIn("tok", result)
        self.assertIn("cre", result)
        self.assertEqual(result["tok"]["tot"], Decimal("20.00"))
        self.assertEqual(result["cre"]["tot"], Decimal("30.00"))

        run.refresh_from_db()
        self.assertEqual(run.costs, Decimal("50.00"))

    @patch("larpmanager.accounting.balance.get_event_features")
    def test_get_run_accounting_with_discounts(self, mock_features) -> None:
        """Test run accounting with discounts"""
        mock_features.return_value = {"payment": True, "discount": True}

        run = self.get_run()
        run.development = DevelopStatus.SHOW
        run.save()

        member = self.get_member()
        association = self.get_association()

        # Create discount
        discount = Discount.objects.create(
            name="Test Discount", value=Decimal("20.00"), max_redeem=10, typ=DiscountType.STANDARD, event=run.event, number=1
        )
        discount.runs.add(run)

        AccountingItemDiscount.objects.create(member=member, run=run, disc=discount, value=Decimal("20.00"), association=association)

        result = get_run_accounting(run, {})

        self.assertIn("dis", result)
        self.assertEqual(result["dis"]["tot"], Decimal("20.00"))

    @patch("larpmanager.accounting.balance.get_event_features")
    def test_get_run_accounting_calculates_balance(self, mock_features) -> None:
        """Test run accounting calculates correct balance"""
        mock_features.return_value = {"payment": True, "expense": True}

        run = self.get_run()
        run.development = DevelopStatus.SHOW
        run.save()

        member = self.get_member()
        association = self.get_association()
        registration = self.create_registration(member=member, run=run, tot_iscr=Decimal("200.00"))

        # Create payment and expense
        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("200.00")
        )
        AccountingItemExpense.objects.create(
            member=member, association=association, run=run, exp=ExpenseChoices.LOCAT, value=Decimal("80.00"), is_approved=True
        )

        result = get_run_accounting(run, {})

        run.refresh_from_db()
        self.assertEqual(run.revenue, Decimal("200.00"))
        self.assertEqual(run.costs, Decimal("80.00"))
        self.assertEqual(run.balance, Decimal("120.00"))


class TestAssocAccountingFunctions(BaseTestCase):
    """Test cases for association accounting functions"""

    def test_association_accounting_data_basic(self) -> None:
        """Test basic association accounting data gathering"""
        association = self.get_association()
        context = {"association_id": association.id}

        association_accounting_data(context)

        self.assertIn("outflow_exec_sum", context)
        self.assertIn("inflow_exec_sum", context)
        self.assertIn("membership_sum", context)
        self.assertIn("donations_sum", context)
        self.assertIn("in_sum", context)
        self.assertIn("out_sum", context)

    def test_association_accounting_data_with_year_filter(self) -> None:
        """Test association accounting data with year filter"""
        association = self.get_association()
        context = {"association_id": association.id}

        association_accounting_data(context, year=2024)

        self.assertIn("membership_sum", context)
        # Should only include items from 2024

    def test_association_accounting_calculates_totals(self) -> None:
        """Test association accounting calculates correct totals"""
        association = self.get_association()
        context = {"association_id": association.id}

        association_accounting(context)

        self.assertIn("list", context)
        self.assertIn("tokens_sum", context)
        self.assertIn("credits_sum", context)
        self.assertIn("balance_sum", context)
        self.assertIn("global_sum", context)
        self.assertIn("bank_sum", context)

    def test_association_accounting_includes_member_balances(self) -> None:
        """Test association accounting includes member token/credit balances"""
        association = self.get_association()
        member = self.get_member()
        membership = member.membership

        membership.tokens = Decimal("50.00")
        membership.credit = Decimal("30.00")
        membership.save()

        context = {"association_id": association.id}
        association_accounting(context)

        self.assertGreaterEqual(context["tokens_sum"], Decimal("50.00"))
        self.assertGreaterEqual(context["credits_sum"], Decimal("30.00"))

    def test_association_accounting_includes_run_balances(self) -> None:
        """Test association accounting includes completed run balances"""
        association = self.get_association()
        run = self.get_run()
        run.development = DevelopStatus.DONE
        run.balance = Decimal("100.00")
        run.save()

        context = {"association_id": association.id}
        association_accounting(context)

        self.assertIn("runs", context)
        self.assertGreaterEqual(context["balance_sum"], Decimal("100.00"))
