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

"""Tests for membership accounting, modification, and automatic value updates"""

from decimal import Decimal
from unittest.mock import patch

from larpmanager.models.accounting import (
    AccountingItemExpense,
    AccountingItemOther,
    AccountingItemPayment,
    OtherChoices,
    PaymentChoices,
)
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.tests.unit.base import BaseTestCase


class TestMembershipCreation(BaseTestCase):
    """Test cases for membership creation"""

    def test_create_basic_membership(self) -> None:
        """Test creating a basic membership"""
        member = self.get_member()
        association = self.get_association()

        # Delete existing membership if any
        Membership.objects.filter(member=member, association=association).delete()

        membership = Membership(member=member, association=association, credit=Decimal("0.00"), tokens=Decimal("0.00"))
        membership.save()

        self.assertIsNotNone(membership.id)
        self.assertEqual(membership.member, member)
        self.assertEqual(membership.association, association)
        self.assertEqual(membership.credit, Decimal("0.00"))
        self.assertEqual(membership.tokens, Decimal("0.00"))

    def test_create_membership_with_initial_credit(self) -> None:
        """Test creating a membership with initial credit"""
        member = self.get_member()
        association = self.get_association()

        # Delete existing membership if any
        Membership.objects.filter(member=member, association=association).delete()

        membership = Membership(member=member, association=association, credit=Decimal("50.00"), tokens=Decimal("0.00"))
        membership.save()

        self.assertIsNotNone(membership.id)
        self.assertEqual(membership.credit, Decimal("50.00"))

    def test_create_membership_with_initial_tokens(self) -> None:
        """Test creating a membership with initial tokens"""
        member = self.get_member()
        association = self.get_association()

        # Delete existing membership if any
        Membership.objects.filter(member=member, association=association).delete()

        membership = Membership(member=member, association=association, credit=Decimal("0.00"), tokens=Decimal("10.00"))
        membership.save()

        self.assertIsNotNone(membership.id)
        self.assertEqual(membership.tokens, Decimal("10.00"))

    def test_create_membership_with_status(self) -> None:
        """Test creating a membership with specific status"""
        member = self.get_member()
        association = self.get_association()

        # Delete existing membership if any
        Membership.objects.filter(member=member, association=association).delete()

        membership = Membership(
            member=member,
            association=association,
            credit=Decimal("0.00"),
            tokens=Decimal("0.00"),
            status=MembershipStatus.ACCEPTED,
        )
        membership.save()

        self.assertIsNotNone(membership.id)
        self.assertEqual(membership.status, MembershipStatus.ACCEPTED)

    def test_create_membership_with_card_number(self) -> None:
        """Test that card number is auto-generated for accepted membership"""
        member = self.get_member()
        association = self.get_association()

        # Delete existing membership if any
        Membership.objects.filter(member=member, association=association).delete()

        membership = Membership(
            member=member,
            association=association,
            credit=Decimal("0.00"),
            tokens=Decimal("0.00"),
            status=MembershipStatus.ACCEPTED,
        )
        membership.save()

        # Card number should be set automatically by signal
        updated_membership = Membership.objects.get(id=membership.id)
        self.assertIsNotNone(updated_membership.card_number)


class TestMembershipModification(BaseTestCase):
    """Test cases for membership modification"""

    def test_modify_membership_credit(self) -> None:
        """Test modifying membership credit"""
        membership = self.get_member().membership
        original_credit = membership.credit

        membership.credit = Decimal("150.00")
        membership.save()

        updated = Membership.objects.get(id=membership.id)
        self.assertEqual(updated.credit, Decimal("150.00"))

    def test_modify_membership_tokens(self) -> None:
        """Test modifying membership tokens"""
        membership = self.get_member().membership
        original_tokens = membership.tokens

        membership.tokens = Decimal("25.00")
        membership.save()

        updated = Membership.objects.get(id=membership.id)
        self.assertEqual(updated.tokens, Decimal("25.00"))

    def test_modify_membership_status(self) -> None:
        """Test modifying membership status"""
        membership = self.get_member().membership

        membership.status = MembershipStatus.SUBMITTED
        membership.save()

        updated = Membership.objects.get(id=membership.id)
        self.assertEqual(updated.status, MembershipStatus.SUBMITTED)

    def test_modify_membership_compiled_flag(self) -> None:
        """Test modifying membership compiled flag"""
        membership = self.get_member().membership

        membership.compiled = True
        membership.save()

        updated = Membership.objects.get(id=membership.id)
        self.assertTrue(updated.compiled)

    def test_increase_credit(self) -> None:
        """Test increasing membership credit"""
        membership = self.get_member().membership
        original_credit = membership.credit

        membership.credit += Decimal("50.00")
        membership.save()

        updated = Membership.objects.get(id=membership.id)
        self.assertEqual(updated.credit, original_credit + Decimal("50.00"))

    def test_decrease_credit(self) -> None:
        """Test decreasing membership credit"""
        membership = self.get_member().membership
        membership.credit = Decimal("100.00")
        membership.save()

        membership.credit -= Decimal("30.00")
        membership.save()

        updated = Membership.objects.get(id=membership.id)
        self.assertEqual(updated.credit, Decimal("70.00"))


class TestMembershipAccountingAutomation(BaseTestCase):
    """Test cases for automatic membership accounting updates"""

    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_tokens_automatic_update_on_token_given(self, mock_features) -> None:
        """Test automatic token balance update when tokens are given"""
        mock_features.return_value = {"token_credit": True}

        member = self.get_member()
        association = self.get_association()
        membership = member.membership

        # Delete existing token items to start fresh
        AccountingItemOther.objects.filter(member=member, association=association, oth=OtherChoices.TOKEN).delete()
        AccountingItemPayment.objects.filter(member=member, association=association, pay=PaymentChoices.TOKEN).delete()

        # Reset tokens
        membership.tokens = Decimal("0.00")
        membership.save()

        # Give tokens
        AccountingItemOther.objects.create(
            member=member, association=association, oth=OtherChoices.TOKEN, value=Decimal("5.00"), descr="Test tokens"
        )

        # Get updated membership
        updated_membership = Membership.objects.get(id=membership.id)

        # Tokens should be updated automatically
        self.assertEqual(updated_membership.tokens, Decimal("5.00"))

    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_tokens_automatic_update_on_token_used(self, mock_features) -> None:
        """Test automatic token balance update when tokens are used"""
        mock_features.return_value = {"token_credit": True}

        member = self.get_member()
        association = self.get_association()
        membership = member.membership
        registration = self.create_registration(member=member)

        # Delete existing token items to start fresh
        AccountingItemOther.objects.filter(member=member, association=association, oth=OtherChoices.TOKEN).delete()
        AccountingItemPayment.objects.filter(member=member, association=association, pay=PaymentChoices.TOKEN).delete()

        # Give tokens first
        AccountingItemOther.objects.create(
            member=member, association=association, oth=OtherChoices.TOKEN, value=Decimal("10.00"), descr="Test tokens"
        )

        # Use tokens
        payment = AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.TOKEN, value=Decimal("3.00")
        )
        # Trigger signal by saving again (signal only fires on update, not create)
        payment.save()

        # Get updated membership
        updated_membership = Membership.objects.get(id=membership.id)

        # Tokens should be: 10 given - 3 used = 7
        self.assertEqual(updated_membership.tokens, Decimal("7.00"))

    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_credit_automatic_update_on_credit_given(self, mock_features) -> None:
        """Test automatic credit balance update when credit is given"""
        mock_features.return_value = {"token_credit": True}

        member = self.get_member()
        association = self.get_association()
        membership = member.membership

        # Delete existing credit items to start fresh
        AccountingItemOther.objects.filter(member=member, association=association, oth__in=[OtherChoices.CREDIT, OtherChoices.REFUND]).delete()
        AccountingItemPayment.objects.filter(member=member, association=association, pay=PaymentChoices.CREDIT).delete()
        AccountingItemExpense.objects.filter(member=member, association=association).delete()

        # Reset credit
        membership.credit = Decimal("0.00")
        membership.save()

        # Give credit
        AccountingItemOther.objects.create(
            member=member, association=association, oth=OtherChoices.CREDIT, value=Decimal("50.00"), descr="Test credit"
        )

        # Get updated membership
        updated_membership = Membership.objects.get(id=membership.id)

        # Credit should be updated automatically
        self.assertEqual(updated_membership.credit, Decimal("50.00"))

    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_credit_automatic_update_on_credit_used(self, mock_features) -> None:
        """Test automatic credit balance update when credit is used"""
        mock_features.return_value = {"token_credit": True}

        member = self.get_member()
        association = self.get_association()
        membership = member.membership
        registration = self.create_registration(member=member)

        # Delete existing credit items to start fresh
        AccountingItemOther.objects.filter(member=member, association=association, oth__in=[OtherChoices.CREDIT, OtherChoices.REFUND]).delete()
        AccountingItemPayment.objects.filter(member=member, association=association, pay=PaymentChoices.CREDIT).delete()
        AccountingItemExpense.objects.filter(member=member, association=association).delete()

        # Give credit first
        AccountingItemOther.objects.create(
            member=member, association=association, oth=OtherChoices.CREDIT, value=Decimal("100.00"), descr="Test credit"
        )

        # Use credit
        payment = AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.CREDIT, value=Decimal("25.00")
        )
        # Trigger signal by saving again (signal only fires on update, not create)
        payment.save()

        # Get updated membership
        updated_membership = Membership.objects.get(id=membership.id)

        # Credit should be: 100 given - 25 used = 75
        self.assertEqual(updated_membership.credit, Decimal("75.00"))

    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_credit_automatic_update_on_expense_approved(self, mock_features) -> None:
        """Test automatic credit balance update when expense is approved"""
        mock_features.return_value = {"token_credit": True}

        member = self.get_member()
        association = self.get_association()
        membership = member.membership

        # Delete existing credit items to start fresh
        AccountingItemOther.objects.filter(member=member, association=association, oth__in=[OtherChoices.CREDIT, OtherChoices.REFUND]).delete()
        AccountingItemPayment.objects.filter(member=member, association=association, pay=PaymentChoices.CREDIT).delete()
        AccountingItemExpense.objects.filter(member=member, association=association).delete()

        # Reset credit
        membership.credit = Decimal("0.00")
        membership.save()

        # Create approved expense
        AccountingItemExpense.objects.create(
            member=member, association=association, value=Decimal("30.00"), descr="Test expense", is_approved=True
        )

        # Get updated membership
        updated_membership = Membership.objects.get(id=membership.id)

        # Credit should be updated with expense amount
        self.assertEqual(updated_membership.credit, Decimal("30.00"))

    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_credit_automatic_update_on_refund(self, mock_features) -> None:
        """Test automatic credit balance update when refund is given"""
        mock_features.return_value = {"token_credit": True}

        member = self.get_member()
        association = self.get_association()
        membership = member.membership
        run = self.get_run()

        # Delete existing credit items to start fresh
        AccountingItemOther.objects.filter(member=member, association=association, oth__in=[OtherChoices.CREDIT, OtherChoices.REFUND]).delete()
        AccountingItemPayment.objects.filter(member=member, association=association, pay=PaymentChoices.CREDIT).delete()
        AccountingItemExpense.objects.filter(member=member, association=association).delete()

        # Give credit first
        AccountingItemOther.objects.create(
            member=member, association=association, oth=OtherChoices.CREDIT, value=Decimal("100.00"), descr="Test credit"
        )

        # Apply refund (reduces credit)
        AccountingItemOther.objects.create(
            member=member, association=association, run=run, oth=OtherChoices.REFUND, value=Decimal("20.00"), descr="Test refund"
        )

        # Get updated membership
        updated_membership = Membership.objects.get(id=membership.id)

        # Credit should be: 100 credit - 20 refund = 80
        self.assertEqual(updated_membership.credit, Decimal("80.00"))

    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_multiple_token_operations(self, mock_features) -> None:
        """Test automatic token balance with multiple operations"""
        mock_features.return_value = {"token_credit": True}

        member = self.get_member()
        association = self.get_association()
        membership = member.membership
        registration = self.create_registration(member=member)

        # Delete existing token items to start fresh
        AccountingItemOther.objects.filter(member=member, association=association, oth=OtherChoices.TOKEN).delete()
        AccountingItemPayment.objects.filter(member=member, association=association, pay=PaymentChoices.TOKEN).delete()

        # Reset tokens
        membership.tokens = Decimal("0.00")
        membership.save()

        # Give tokens multiple times
        AccountingItemOther.objects.create(
            member=member, association=association, oth=OtherChoices.TOKEN, value=Decimal("5.00"), descr="Tokens 1"
        )
        AccountingItemOther.objects.create(
            member=member, association=association, oth=OtherChoices.TOKEN, value=Decimal("3.00"), descr="Tokens 2"
        )

        # Use some tokens
        payment = AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.TOKEN, value=Decimal("2.00")
        )
        # Trigger signal by saving again (signal only fires on update, not create)
        payment.save()

        # Get updated membership
        updated_membership = Membership.objects.get(id=membership.id)

        # Tokens should be: 5 + 3 - 2 = 6
        self.assertEqual(updated_membership.tokens, Decimal("6.00"))

    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_multiple_credit_operations(self, mock_features) -> None:
        """Test automatic credit balance with multiple operations"""
        mock_features.return_value = {"token_credit": True}

        member = self.get_member()
        association = self.get_association()
        membership = member.membership
        registration = self.create_registration(member=member)
        run = self.get_run()

        # Delete existing credit items to start fresh
        AccountingItemOther.objects.filter(member=member, association=association, oth__in=[OtherChoices.CREDIT, OtherChoices.REFUND]).delete()
        AccountingItemPayment.objects.filter(member=member, association=association, pay=PaymentChoices.CREDIT).delete()
        AccountingItemExpense.objects.filter(member=member, association=association).delete()

        # Reset credit
        membership.credit = Decimal("0.00")
        membership.save()

        # Give credit
        AccountingItemOther.objects.create(
            member=member, association=association, oth=OtherChoices.CREDIT, value=Decimal("100.00"), descr="Credit 1"
        )

        # Add expense
        AccountingItemExpense.objects.create(
            member=member, association=association, value=Decimal("50.00"), descr="Expense", is_approved=True
        )

        # Use some credit
        payment = AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.CREDIT, value=Decimal("30.00")
        )
        # Trigger signal by saving again (signal only fires on update, not create)
        payment.save()

        # Get updated membership
        updated_membership = Membership.objects.get(id=membership.id)

        # Credit should be: 100 given + 50 expense - 30 used = 120
        self.assertEqual(updated_membership.credit, Decimal("120.00"))

    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_no_update_when_feature_disabled(self, mock_features) -> None:
        """Test that automatic updates don't happen when feature is disabled"""
        mock_features.return_value = {}  # token_credit feature disabled

        member = self.get_member()
        association = self.get_association()
        membership = member.membership

        # Set initial value
        membership.tokens = Decimal("5.00")
        membership.save()

        # Try to give tokens (should not update when feature disabled)
        AccountingItemOther.objects.create(
            member=member, association=association, oth=OtherChoices.TOKEN, value=Decimal("10.00"), descr="Test tokens"
        )

        # Get membership - tokens should remain unchanged
        updated_membership = Membership.objects.get(id=membership.id)

        # When feature is disabled, automatic calculation doesn't happen
        # So tokens stay at original value
        self.assertEqual(updated_membership.tokens, Decimal("5.00"))

    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_token_balance_never_negative(self, mock_features) -> None:
        """Test that token balance calculation handles edge cases"""
        mock_features.return_value = {"token_credit": True}

        member = self.get_member()
        association = self.get_association()
        membership = member.membership
        registration = self.create_registration(member=member)

        # Reset tokens
        membership.tokens = Decimal("0.00")
        membership.save()

        # Give 5 tokens
        AccountingItemOther.objects.create(
            member=member, association=association, oth=OtherChoices.TOKEN, value=Decimal("5.00"), descr="Test tokens"
        )

        # Try to use 5 tokens (should work)
        payment = AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.TOKEN, value=Decimal("5.00")
        )
        # Trigger signal by saving again (signal only fires on update, not create)
        payment.save()

        # Get updated membership
        updated_membership = Membership.objects.get(id=membership.id)

        # Tokens should be 0
        self.assertEqual(updated_membership.tokens, Decimal("0.00"))

    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_delete_token_item_updates_balance(self, mock_features) -> None:
        """Test that deleting a token item updates the balance"""
        mock_features.return_value = {"token_credit": True}

        member = self.get_member()
        association = self.get_association()
        membership = member.membership

        # Delete existing token items to start fresh
        AccountingItemOther.objects.filter(member=member, association=association, oth=OtherChoices.TOKEN).delete()
        AccountingItemPayment.objects.filter(member=member, association=association, pay=PaymentChoices.TOKEN).delete()

        # Reset tokens
        membership.tokens = Decimal("0.00")
        membership.save()

        # Give tokens
        token_item = AccountingItemOther.objects.create(
            member=member, association=association, oth=OtherChoices.TOKEN, value=Decimal("10.00"), descr="Test tokens"
        )

        # Verify tokens were added
        updated_membership = Membership.objects.get(id=membership.id)
        self.assertEqual(updated_membership.tokens, Decimal("10.00"))

        # Delete the token item
        token_item.delete()

        # Verify tokens were removed
        updated_membership = Membership.objects.get(id=membership.id)
        self.assertEqual(updated_membership.tokens, Decimal("0.00"))

    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_update_payment_item_recalculates_balance(self, mock_features) -> None:
        """Test that updating a payment item recalculates the balance"""
        mock_features.return_value = {"token_credit": True}

        member = self.get_member()
        association = self.get_association()
        membership = member.membership
        registration = self.create_registration(member=member)

        # Delete existing token items to start fresh
        AccountingItemOther.objects.filter(member=member, association=association, oth=OtherChoices.TOKEN).delete()
        AccountingItemPayment.objects.filter(member=member, association=association, pay=PaymentChoices.TOKEN).delete()

        # Reset tokens
        membership.tokens = Decimal("0.00")
        membership.save()

        # Give tokens
        AccountingItemOther.objects.create(
            member=member, association=association, oth=OtherChoices.TOKEN, value=Decimal("10.00"), descr="Test tokens"
        )

        # Use some tokens
        payment = AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.TOKEN, value=Decimal("3.00")
        )
        # Trigger signal for initial creation
        payment.save()

        # Verify balance: 10 - 3 = 7
        updated_membership = Membership.objects.get(id=membership.id)
        self.assertEqual(updated_membership.tokens, Decimal("7.00"))

        # Update payment value
        payment.value = Decimal("5.00")
        payment.save()

        # Verify balance recalculated: 10 - 5 = 5
        updated_membership = Membership.objects.get(id=membership.id)
        self.assertEqual(updated_membership.tokens, Decimal("5.00"))
