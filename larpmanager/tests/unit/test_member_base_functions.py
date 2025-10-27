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

"""Tests for member accounting and base utility functions"""

from decimal import Decimal
from unittest.mock import patch

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.accounting.member import _info_token_credit, _init_choices, _init_pending
from larpmanager.models.accounting import (
    AccountingItemExpense,
    AccountingItemOther,
    OtherChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
)
from larpmanager.models.event import DevelopStatus
from larpmanager.models.form import RegistrationChoice
from larpmanager.tests.unit.base import BaseTestCase


class TestMemberAccountingFunctions(BaseTestCase):
    """Test cases for member accounting utility functions"""

    def test_init_pending_no_pending(self):
        """Test _init_pending with no pending payments"""
        member = self.get_member()

        result = _init_pending(member)

        self.assertEqual(result, {})

    def test_init_choices_no_choices(self):
        """Test _init_choices with no registration choices"""
        member = self.get_member()

        result = _init_choices(member)

        self.assertEqual(result, {})

    def test_init_choices_with_choices(self):
        """Test _init_choices with registration choices"""
        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        question, option1, option2 = self.question_with_options(event=run.event)

        # Create registration choice
        RegistrationChoice.objects.create(reg=registration, option=option1, question=question)

        result = _init_choices(member)

        self.assertIn(registration.id, result)
        self.assertIn(question.id, result[registration.id])
        self.assertEqual(result[registration.id][question.id]["question"], question)
        self.assertIn(option1, result[registration.id][question.id]["selected_options"])

    def test_init_choices_multiple_options(self):
        """Test _init_choices with multiple options selected"""
        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        question, option1, option2 = self.question_with_options(event=run.event)

        # Create multiple registration choices
        RegistrationChoice.objects.create(reg=registration, option=option1, question=question)
        RegistrationChoice.objects.create(reg=registration, option=option2, question=question)

        result = _init_choices(member)

        self.assertEqual(len(result[registration.id][question.id]["selected_options"]), 2)

    def test_info_token_credit_no_items(self):
        """Test _info_token_credit with no tokens or credits"""
        member = self.get_member()
        assoc = self.get_association()
        context = {"association_id": assoc.id}

        _info_token_credit(context, member)

        self.assertEqual(context["acc_tokens"], 0)
        self.assertEqual(context["acc_credits"], 0)

    def test_info_token_credit_with_tokens(self):
        """Test _info_token_credit with tokens"""
        member = self.get_member()
        assoc = self.get_association()
        context = {"association_id": assoc.id}

        # Create token items
        AccountingItemOther.objects.create(
            member=member, assoc=assoc, oth=OtherChoices.TOKEN, value=Decimal("50.00"), descr="Test token"
        )

        _info_token_credit(context, member)

        self.assertEqual(context["acc_tokens"], 1)

    def test_info_token_credit_with_credits(self):
        """Test _info_token_credit with credits"""
        member = self.get_member()
        assoc = self.get_association()
        run = self.get_run()
        context = {"association_id": assoc.id}

        # Create credit items
        AccountingItemOther.objects.create(
            member=member, assoc=assoc, oth=OtherChoices.CREDIT, value=Decimal("30.00"), descr="Test credit"
        )
        AccountingItemExpense.objects.create(
            member=member, assoc=assoc, run=run, value=Decimal("20.00"), is_approved=True
        )

        _info_token_credit(context, member)

        self.assertEqual(context["acc_credits"], 2)

    def test_info_token_credit_with_both(self):
        """Test _info_token_credit with both tokens and credits"""
        member = self.get_member()
        assoc = self.get_association()
        run = self.get_run()
        context = {"association_id": assoc.id}

        # Create both tokens and credits
        AccountingItemOther.objects.create(
            member=member, assoc=assoc, oth=OtherChoices.TOKEN, value=Decimal("50.00"), descr="Test token"
        )
        AccountingItemOther.objects.create(
            member=member, assoc=assoc, oth=OtherChoices.CREDIT, value=Decimal("30.00"), descr="Test credit"
        )

        _info_token_credit(context, member)

        self.assertEqual(context["acc_tokens"], 1)
        self.assertEqual(context["acc_credits"], 1)


class TestBaseUtilityFunctions(BaseTestCase):
    """Test cases for base utility functions"""

    @patch("larpmanager.accounting.base.get_event_features")
    def test_is_reg_provisional_no_payment_feature(self, mock_features):
        """Test is_reg_provisional when payment feature is disabled"""
        mock_features.return_value = {}

        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"))

        result = is_reg_provisional(registration)

        self.assertFalse(result)

    @patch("larpmanager.accounting.base.get_event_features")
    def test_is_reg_provisional_fully_paid(self, mock_features):
        """Test is_reg_provisional when fully paid"""
        mock_features.return_value = {"payment": True}

        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("100.00"))

        result = is_reg_provisional(registration)

        self.assertFalse(result)

    @patch("larpmanager.accounting.base.get_event_features")
    def test_is_reg_provisional_no_cost(self, mock_features):
        """Test is_reg_provisional with no cost registration"""
        mock_features.return_value = {"payment": True}

        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run, tot_iscr=Decimal("0.00"), tot_payed=Decimal("0.00"))

        result = is_reg_provisional(registration)

        self.assertFalse(result)

    @patch("larpmanager.accounting.base.get_event_features")
    def test_is_reg_provisional_partial_payment(self, mock_features):
        """Test is_reg_provisional with partial payment"""
        mock_features.return_value = {"payment": True}

        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("50.00"))

        result = is_reg_provisional(registration)

        # Partial payment means not provisional (tot_payed > 0)
        self.assertFalse(result)
