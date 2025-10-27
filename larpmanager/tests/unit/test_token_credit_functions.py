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

"""Tests for token and credit accounting functions"""

from decimal import Decimal

from django.db.models import Sum

from larpmanager.accounting.token_credit import (
    get_regs,
    get_regs_paying_incomplete,
    registration_tokens_credits_overpay,
    registration_tokens_credits_use,
)
from larpmanager.models.accounting import (
    AccountingItemPayment,
    OtherChoices,
    PaymentChoices,
)
from larpmanager.models.event import DevelopStatus
from larpmanager.tests.unit.base import BaseTestCase


class TestTokenCreditUseFunctions(BaseTestCase):
    """Test cases for token and credit usage functions"""

    def test_registration_tokens_credits_use_no_balance(self):
        """Test token/credit use with no member balance"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run, tot_iscr=Decimal("100.00"))

        membership = member.membership
        membership.tokens = Decimal("0.00")
        membership.credit = Decimal("0.00")
        membership.save()

        registration_tokens_credits_use(registration, Decimal("50.00"), association.id)

        registration.refresh_from_db()
        # No tokens or credits available, tot_payed should remain unchanged
        self.assertEqual(registration.tot_payed, Decimal("0.00"))

    def test_registration_tokens_credits_use_tokens_only(self):
        """Test using tokens to pay registration"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"))

        membership = member.membership
        membership.tokens = Decimal("30.00")
        membership.credit = Decimal("0.00")
        membership.save()

        registration_tokens_credits_use(registration, Decimal("50.00"), association.id)

        registration.refresh_from_db()
        membership.refresh_from_db()
        # Should use all 30 tokens
        self.assertEqual(registration.tot_payed, Decimal("30.00"))
        self.assertEqual(membership.tokens, Decimal("0.00"))

    def test_registration_tokens_credits_use_credits_only(self):
        """Test using credits to pay registration"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"))

        membership = member.membership
        membership.tokens = Decimal("0.00")
        membership.credit = Decimal("40.00")
        membership.save()

        registration_tokens_credits_use(registration, Decimal("50.00"), association.id)

        registration.refresh_from_db()
        membership.refresh_from_db()
        # Should use all 40 credits
        self.assertEqual(registration.tot_payed, Decimal("40.00"))
        self.assertEqual(membership.credit, Decimal("0.00"))

    def test_registration_tokens_credits_use_both(self):
        """Test using both tokens and credits"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"))

        membership = member.membership
        membership.tokens = Decimal("30.00")
        membership.credit = Decimal("40.00")
        membership.save()

        registration_tokens_credits_use(registration, Decimal("50.00"), association.id)

        registration.refresh_from_db()
        membership.refresh_from_db()
        # Should use 30 tokens + 20 credits = 50 total
        self.assertEqual(registration.tot_payed, Decimal("50.00"))
        self.assertEqual(membership.tokens, Decimal("0.00"))
        self.assertEqual(membership.credit, Decimal("20.00"))

    def test_registration_tokens_credits_use_negative_remaining(self):
        """Test token/credit use with negative remaining (overpay)"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        membership = member.membership
        membership.tokens = Decimal("50.00")
        membership.save()

        # Negative remaining should return without changes
        registration_tokens_credits_use(registration, Decimal("-10.00"), association.id)

        membership.refresh_from_db()
        self.assertEqual(membership.tokens, Decimal("50.00"))

    def test_registration_tokens_credits_use_partial_tokens(self):
        """Test using partial tokens when remaining is less than balance"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"))

        membership = member.membership
        membership.tokens = Decimal("100.00")
        membership.save()

        registration_tokens_credits_use(registration, Decimal("25.00"), association.id)

        registration.refresh_from_db()
        membership.refresh_from_db()
        # Should use only 25 tokens
        self.assertEqual(registration.tot_payed, Decimal("25.00"))
        self.assertEqual(membership.tokens, Decimal("75.00"))


class TestTokenCreditOverpayFunctions(BaseTestCase):
    """Test cases for token and credit overpay reversal"""

    def test_registration_tokens_credits_overpay_no_payments(self):
        """Test overpay reversal with no token/credit payments"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        # No payments exist
        registration_tokens_credits_overpay(registration, Decimal("10.00"), association.id)

        # Should complete without error
        payments = AccountingItemPayment.objects.filter(reg=registration)
        self.assertEqual(payments.count(), 0)

    def test_registration_tokens_credits_overpay_credit_first(self):
        """Test overpay reversal removes credits before tokens"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        # Create token and credit payments
        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.TOKEN, value=Decimal("30.00")
        )
        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.CREDIT, value=Decimal("20.00")
        )

        registration_tokens_credits_overpay(registration, Decimal("15.00"), association.id)

        # Should remove 15 from credit first
        credit_payment = AccountingItemPayment.objects.filter(reg=registration, pay=PaymentChoices.CREDIT).first()
        token_payment = AccountingItemPayment.objects.filter(reg=registration, pay=PaymentChoices.TOKEN).first()

        self.assertEqual(credit_payment.value, Decimal("5.00"))
        self.assertEqual(token_payment.value, Decimal("30.00"))

    def test_registration_tokens_credits_overpay_delete_empty(self):
        """Test overpay reversal deletes payment when value reaches zero"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.CREDIT, value=Decimal("20.00")
        )

        registration_tokens_credits_overpay(registration, Decimal("20.00"), association.id)

        # Payment should be deleted
        payments = AccountingItemPayment.objects.filter(reg=registration, pay=PaymentChoices.CREDIT)
        self.assertEqual(payments.count(), 0)

    def test_registration_tokens_credits_overpay_multiple_payments(self):
        """Test overpay reversal with multiple payments"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        # Create multiple credit payments
        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.CREDIT, value=Decimal("10.00")
        )
        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.CREDIT, value=Decimal("15.00")
        )

        registration_tokens_credits_overpay(registration, Decimal("20.00"), association.id)

        # Should remove payments until overpay is covered
        total = AccountingItemPayment.objects.filter(reg=registration, pay=PaymentChoices.CREDIT).aggregate(
            total=Sum("value")
        )["total"] or Decimal("0.00")
        self.assertEqual(total, Decimal("5.00"))

    def test_registration_tokens_credits_overpay_zero_amount(self):
        """Test overpay reversal with zero amount"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.TOKEN, value=Decimal("30.00")
        )

        registration_tokens_credits_overpay(registration, Decimal("0.00"), association.id)

        # Should not change anything
        payment = AccountingItemPayment.objects.get(reg=registration)
        self.assertEqual(payment.value, Decimal("30.00"))


class TestRegistrationQueryFunctions(BaseTestCase):
    """Test cases for registration query functions"""

    def test_get_regs_basic(self):
        """Test getting active registrations"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        regs = get_regs(association)

        self.assertIn(registration, regs)

    def test_get_regs_excludes_cancelled(self):
        """Test get_regs excludes cancelled registrations"""
        from datetime import datetime

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)
        registration.cancellation_date = datetime.now()
        registration.save()

        regs = get_regs(association)

        self.assertNotIn(registration, regs)

    def test_get_regs_excludes_done_events(self):
        """Test get_regs excludes registrations from completed events"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        run.development = DevelopStatus.DONE
        run.save()
        registration = self.create_registration(member=member, run=run)

        regs = get_regs(association)

        self.assertNotIn(registration, regs)

    def test_get_regs_excludes_cancelled_events(self):
        """Test get_regs excludes registrations from cancelled events"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        run.development = DevelopStatus.CANC
        run.save()
        registration = self.create_registration(member=member, run=run)

        regs = get_regs(association)

        self.assertNotIn(registration, regs)

    def test_get_regs_paying_incomplete_basic(self):
        """Test getting registrations with incomplete payments"""
        from larpmanager.models.registration import Registration

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        # Update fields directly in DB to avoid signal triggers
        Registration.objects.filter(pk=registration.pk).update(
            tot_iscr=Decimal("100.00"),
            tot_payed=Decimal("50.00")
        )

        regs = get_regs_paying_incomplete(association)

        self.assertIn(registration, regs)

    def test_get_regs_paying_incomplete_excludes_paid(self):
        """Test get_regs_paying_incomplete excludes fully paid"""
        from larpmanager.models.registration import Registration

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        # Update fields directly in DB
        Registration.objects.filter(pk=registration.pk).update(
            tot_iscr=Decimal("100.00"),
            tot_payed=Decimal("100.00")
        )

        regs = get_regs_paying_incomplete(association)

        self.assertNotIn(registration, regs)

    def test_get_regs_paying_incomplete_ignores_small_diff(self):
        """Test get_regs_paying_incomplete ignores small differences"""
        from larpmanager.models.registration import Registration

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        # Update fields directly in DB
        Registration.objects.filter(pk=registration.pk).update(
            tot_iscr=Decimal("100.00"),
            tot_payed=Decimal("99.98")
        )

        regs = get_regs_paying_incomplete(association)

        # Difference is 0.02, should be ignored (threshold is 0.05)
        self.assertNotIn(registration, regs)

    def test_get_regs_paying_incomplete_includes_overpay(self):
        """Test get_regs_paying_incomplete includes overpayments"""
        from larpmanager.models.registration import Registration

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        # Update fields directly in DB
        Registration.objects.filter(pk=registration.pk).update(
            tot_iscr=Decimal("100.00"),
            tot_payed=Decimal("110.00")
        )

        regs = get_regs_paying_incomplete(association)

        # Overpayment of 10 should be included
        self.assertIn(registration, regs)
