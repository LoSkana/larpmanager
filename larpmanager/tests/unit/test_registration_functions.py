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

"""Tests for registration accounting functions"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest

from larpmanager.accounting.registration import (
    cancel_reg,
    get_date_surcharge,
    get_registration_iscr,
    get_registration_payments,
    get_registration_transactions,
    installment_check,
    quota_check,
    registration_payments_status,
    round_to_nearest_cent,
)
from larpmanager.accounting.member import get_membership_fee_for_reg
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemMembership,
    AccountingItemPayment,
    AccountingItemTransaction,
    Discount,
    DiscountType,
    PaymentChoices,
)
from larpmanager.models.association import AssociationConfig
from larpmanager.models.form import RegistrationChoice
from larpmanager.models.member import get_user_membership
from larpmanager.models.registration import (
    RegistrationCharacterRel,
    RegistrationInstallment,
    RegistrationSurcharge,
    TicketTier,
)
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.core.common import get_display_choice


class TestRegistrationCalculationFunctions(BaseTestCase):
    """Test cases for registration fee calculation functions"""

    def test_get_registration_iscr_basic_ticket(self) -> None:
        """Test basic registration fee with ticket only"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("100.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        result = get_registration_iscr(registration)

        self.assertEqual(result, Decimal("100.00"))

    def test_get_registration_iscr_with_additionals(self) -> None:
        """Test registration fee with additional tickets"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("50.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=2)

        result = get_registration_iscr(registration)

        # Base ticket + 2 additionals = 50 + (50*2) = 150
        self.assertEqual(result, Decimal("150.00"))

    def test_get_registration_iscr_with_zero_additionals(self) -> None:
        """Test registration fee with zero additional tickets"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("50.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=0)

        result = get_registration_iscr(registration)

        # Just base ticket
        self.assertEqual(result, Decimal("50.00"))

    def test_get_registration_iscr_with_one_additional(self) -> None:
        """Test registration fee with one additional ticket"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("75.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=1)

        result = get_registration_iscr(registration)

        # Base ticket + 1 additional = 75 + 75 = 150
        self.assertEqual(result, Decimal("150.00"))

    def test_get_registration_iscr_with_max_additionals(self) -> None:
        """Test registration fee with maximum (5) additional tickets"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("60.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=5)

        result = get_registration_iscr(registration)

        # Base ticket + 5 additionals = 60 + (60*5) = 360
        self.assertEqual(result, Decimal("360.00"))

    def test_get_registration_iscr_additionals_with_options(self) -> None:
        """Test registration fee with both additional tickets and options"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("50.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=2)

        # Add registration option
        question, option1, option2 = self.question_with_options(event=run.event)
        option1.price = Decimal("15.00")
        option1.save()
        RegistrationChoice.objects.create(registration=registration, option=option1, question=question)

        result = get_registration_iscr(registration)

        # Base + additionals + option = 50 + 100 + 15 = 165
        self.assertEqual(result, Decimal("165.00"))

    def test_get_registration_iscr_additionals_with_pay_what(self) -> None:
        """Test registration fee with additional tickets and pay-what-you-want"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("40.00"))
        registration = self.create_registration(
            member=member, run=run, ticket=ticket, additionals=3, pay_what=Decimal("20.00")
        )

        result = get_registration_iscr(registration)

        # Base + additionals + pay_what = 40 + 120 + 20 = 180
        self.assertEqual(result, Decimal("180.00"))

    def test_get_registration_iscr_additionals_with_discount(self) -> None:
        """Test registration fee with additional tickets and discount"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("100.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=2)

        # Create discount
        discount = Discount.objects.create(
            name="Early Bird",
            value=Decimal("50.00"),
            max_redeem=10,
            typ=DiscountType.STANDARD,
            event=run.event,
            number=1,
        )
        discount.runs.add(run)
        AccountingItemDiscount.objects.create(
            member=member, run=run, disc=discount, value=Decimal("50.00"), association=association
        )

        result = get_registration_iscr(registration)

        # Base + additionals - discount = 100 + 200 - 50 = 250
        self.assertEqual(result, Decimal("250.00"))

    def test_get_registration_iscr_additionals_with_surcharge(self) -> None:
        """Test registration fee with additional tickets and surcharge"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("80.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=1)

        # Add surcharge
        registration.surcharge = Decimal("25.00")

        result = get_registration_iscr(registration)

        # Base + additionals + surcharge = 80 + 80 + 25 = 185
        self.assertEqual(result, Decimal("185.00"))

    def test_get_registration_iscr_additionals_all_features(self) -> None:
        """Test registration fee with additionals and all pricing features combined"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("60.00"))
        registration = self.create_registration(
            member=member, run=run, ticket=ticket, additionals=2, pay_what=Decimal("10.00")
        )

        # Add registration option
        question, option1, option2 = self.question_with_options(event=run.event)
        option1.price = Decimal("20.00")
        option1.save()
        RegistrationChoice.objects.create(registration=registration, option=option1, question=question)

        # Add surcharge
        registration.surcharge = Decimal("15.00")

        # Add discount
        discount = Discount.objects.create(
            name="Combo Discount",
            value=Decimal("30.00"),
            max_redeem=10,
            typ=DiscountType.STANDARD,
            event=run.event,
            number=1,
        )
        discount.runs.add(run)
        AccountingItemDiscount.objects.create(
            member=member, run=run, disc=discount, value=Decimal("30.00"), association=association
        )

        result = get_registration_iscr(registration)

        # Base + additionals + option + pay_what + surcharge - discount
        # = 60 + 120 + 20 + 10 + 15 - 30 = 195
        self.assertEqual(result, Decimal("195.00"))

    def test_get_registration_iscr_additionals_no_ticket(self) -> None:
        """Test registration fee with additionals but no ticket (edge case)"""
        member = self.get_member()
        run = self.get_run()
        # Create registration without ticket
        registration = self.create_registration(member=member, run=run, ticket=None, additionals=2)

        result = get_registration_iscr(registration)

        # No ticket means no base price, additionals should not add anything
        self.assertEqual(result, 0)

    def test_get_registration_iscr_with_pay_what(self) -> None:
        """Test registration fee with pay-what-you-want amount"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("50.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, pay_what=Decimal("25.00"))

        result = get_registration_iscr(registration)

        # Ticket + pay_what = 50 + 25 = 75
        self.assertEqual(result, Decimal("75.00"))

    def test_get_registration_iscr_with_options(self) -> None:
        """Test registration fee with registration options"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("50.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        question, option1, option2 = self.question_with_options(event=run.event)
        option1.price = Decimal("10.00")
        option1.save()

        RegistrationChoice.objects.create(registration=registration, option=option1, question=question)

        result = get_registration_iscr(registration)

        # Ticket + option = 50 + 10 = 60
        self.assertEqual(result, Decimal("60.00"))

    def test_get_registration_iscr_with_discount(self) -> None:
        """Test registration fee with discount"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("100.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        discount = Discount.objects.create(
            name="Test Discount",
            value=Decimal("20.00"),
            max_redeem=10,
            typ=DiscountType.STANDARD,
            event=run.event,
            number=1,
        )
        discount.runs.add(run)
        AccountingItemDiscount.objects.create(
            member=member, run=run, disc=discount, value=Decimal("20.00"), association=association
        )

        result = get_registration_iscr(registration)

        # Ticket - discount = 100 - 20 = 80
        self.assertEqual(result, Decimal("80.00"))

    def test_get_registration_iscr_with_surcharge(self) -> None:
        """Test registration fee with surcharge"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("100.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Set surcharge on registration object (not passed to create)
        registration.surcharge = Decimal("15.00")

        result = get_registration_iscr(registration)

        # Ticket + surcharge = 100 + 15 = 115
        self.assertEqual(result, Decimal("115.00"))

    def test_get_registration_iscr_gifted_no_discount(self) -> None:
        """Test registration fee for gifted (no discount applied)"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("100.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, redeem_code="GIFT123")

        discount = Discount.objects.create(
            name="Test Discount",
            value=Decimal("20.00"),
            max_redeem=10,
            typ=DiscountType.STANDARD,
            event=run.event,
            number=1,
        )
        discount.runs.add(run)
        AccountingItemDiscount.objects.create(
            member=member, run=run, disc=discount, value=Decimal("20.00"), association=association
        )

        result = get_registration_iscr(registration)

        # Gifted registrations don't get discounts
        self.assertEqual(result, Decimal("100.00"))

    def test_get_registration_iscr_minimum_zero(self) -> None:
        """Test registration fee has minimum of zero"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("50.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        discount = Discount.objects.create(
            name="Large Discount",
            value=Decimal("100.00"),
            max_redeem=10,
            typ=DiscountType.STANDARD,
            event=run.event,
            number=1,
        )
        discount.runs.add(run)
        AccountingItemDiscount.objects.create(
            member=member, run=run, disc=discount, value=Decimal("100.00"), association=association
        )

        result = get_registration_iscr(registration)

        # Should not go below zero
        self.assertEqual(result, 0)


class TestPaymentCalculationFunctions(BaseTestCase):
    """Test cases for payment calculation functions"""

    def test_get_registration_payments_basic(self) -> None:
        """Test basic payment calculation"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemPayment.objects.create(
            member=member, association=association, registration=registration, pay=PaymentChoices.MONEY, value=Decimal("50.00")
        )

        result = get_registration_payments(registration)

        self.assertEqual(result, Decimal("50.00"))

    def test_get_registration_payments_multiple(self) -> None:
        """Test payment calculation with multiple payments"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemPayment.objects.create(
            member=member, association=association, registration=registration, pay=PaymentChoices.MONEY, value=Decimal("30.00")
        )
        AccountingItemPayment.objects.create(
            member=member, association=association, registration=registration, pay=PaymentChoices.MONEY, value=Decimal("20.00")
        )

        result = get_registration_payments(registration)

        self.assertEqual(result, Decimal("50.00"))

    def test_get_registration_payments_excludes_hidden(self) -> None:
        """Test payment calculation excludes hidden payments"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemPayment.objects.create(
            member=member, association=association, registration=registration, pay=PaymentChoices.MONEY, value=Decimal("30.00")
        )
        AccountingItemPayment.objects.create(
            member=member,
            association=association,
            registration=registration,
            pay=PaymentChoices.MONEY,
            value=Decimal("20.00"),
            hide=True,
        )

        result = get_registration_payments(registration)

        # Should exclude hidden payment
        self.assertEqual(result, Decimal("30.00"))

    def test_get_registration_payments_sets_dictionary(self) -> None:
        """Test payment calculation sets payments dictionary"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemPayment.objects.create(
            member=member, association=association, registration=registration, pay=PaymentChoices.MONEY, value=Decimal("30.00")
        )
        AccountingItemPayment.objects.create(
            member=member, association=association, registration=registration, pay=PaymentChoices.TOKEN, value=Decimal("20.00")
        )

        get_registration_payments(registration)

        self.assertIn(PaymentChoices.MONEY, registration.payments)
        self.assertIn(PaymentChoices.TOKEN, registration.payments)
        self.assertEqual(registration.payments[PaymentChoices.MONEY], Decimal("30.00"))
        self.assertEqual(registration.payments[PaymentChoices.TOKEN], Decimal("20.00"))

    def test_get_registration_transactions_basic(self) -> None:
        """Test transaction fee calculation"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemTransaction.objects.create(
            member=member, association=association, registration=registration, value=Decimal("2.50"), user_burden=True
        )

        result = get_registration_transactions(registration)

        self.assertEqual(result, Decimal("2.50"))

    def test_get_registration_transactions_excludes_non_user_burden(self) -> None:
        """Test transaction calculation excludes non-user-burden fees"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemTransaction.objects.create(
            member=member, association=association, registration=registration, value=Decimal("2.50"), user_burden=True
        )
        AccountingItemTransaction.objects.create(
            member=member, association=association, registration=registration, value=Decimal("3.00"), user_burden=False
        )

        result = get_registration_transactions(registration)

        # Should only include user_burden transactions
        self.assertEqual(result, Decimal("2.50"))


class TestRegistrationUtilityFunctions(BaseTestCase):
    """Test cases for registration utility functions"""

    def test_registration_payments_status_completed(self) -> None:
        """Test payment status for completed payment"""
        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)
        registration.tot_iscr = Decimal("100.00")
        registration.tot_payed = Decimal("100.00")

        registration_payments_status(registration)

        self.assertEqual(registration.payment_status, "c")

    def test_registration_payments_status_none(self) -> None:
        """Test payment status for no payment"""
        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)
        registration.tot_iscr = Decimal("100.00")
        registration.tot_payed = Decimal("0.00")

        registration_payments_status(registration)

        self.assertEqual(registration.payment_status, "n")

    def test_registration_payments_status_partial(self) -> None:
        """Test payment status for partial payment"""
        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)
        registration.tot_iscr = Decimal("100.00")
        registration.tot_payed = Decimal("50.00")

        registration_payments_status(registration)

        self.assertEqual(registration.payment_status, "p")

    def test_registration_payments_status_overpaid(self) -> None:
        """Test payment status for overpayment"""
        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)
        registration.tot_iscr = Decimal("100.00")
        registration.tot_payed = Decimal("150.00")

        registration_payments_status(registration)

        self.assertEqual(registration.payment_status, "t")

    def test_round_to_nearest_cent_basic(self) -> None:
        """Test rounding to nearest cent"""
        result = round_to_nearest_cent(10.54)

        # 10.54 is outside tolerance from 10.5, returns original
        self.assertEqual(result, 10.54)

    def test_round_to_nearest_cent_within_tolerance(self) -> None:
        """Test rounding within tolerance"""
        result = round_to_nearest_cent(10.521)

        self.assertEqual(result, 10.52)

    def test_round_to_nearest_cent_exceeds_tolerance(self) -> None:
        """Test rounding exceeds tolerance"""
        result = round_to_nearest_cent(10.55)

        # Difference from 10.5 is 0.05, exceeds tolerance of 0.03
        self.assertEqual(result, 10.55)

    def test_get_display_choice_found(self) -> None:
        """Test getting display name for choice"""
        choices = [("a", "Option A"), ("b", "Option B"), ("c", "Option C")]

        result = get_display_choice(choices, "b")

        self.assertEqual(result, "Option B")

    def test_get_display_choice_not_found(self) -> None:
        """Test getting display name for missing choice"""
        choices = [("a", "Option A"), ("b", "Option B")]

        result = get_display_choice(choices, "z")

        self.assertEqual(result, "")

    def test_get_date_surcharge_no_surcharges(self) -> None:
        """Test date surcharge with no configured surcharges"""
        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        result = get_date_surcharge(registration, run.event)

        self.assertEqual(result, 0)

    def test_get_date_surcharge_with_surcharge(self) -> None:
        """Test date surcharge calculation"""
        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        # Create surcharge before registration date
        RegistrationSurcharge.objects.create(
            event=run.event, date=registration.created.date() - timedelta(days=1), amount=Decimal("15.00")
        )

        result = get_date_surcharge(registration, run.event)

        self.assertEqual(result, Decimal("15.00"))

    def test_get_date_surcharge_waiting_tier(self) -> None:
        """Test date surcharge for waiting tier (should be 0)"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, tier=TicketTier.WAITING)
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        RegistrationSurcharge.objects.create(
            event=run.event, date=registration.created.date() - timedelta(days=1), amount=Decimal("15.00")
        )

        result = get_date_surcharge(registration, run.event)

        # Waiting tier should not have surcharge
        self.assertEqual(result, 0)

    def test_cancel_reg_basic(self) -> None:
        """Test cancelling a registration"""
        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        cancel_reg(registration)

        registration.refresh_from_db()
        self.assertIsNotNone(registration.cancellation_date)

    def test_cancel_reg_deletes_characters(self) -> None:
        """Test cancel_reg deletes character assignments"""
        member = self.get_member()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)
        character = self.character(event=run.event)

        RegistrationCharacterRel.objects.create(registration=registration, character=character)

        cancel_reg(registration)

        # Should delete character relationships
        self.assertEqual(RegistrationCharacterRel.objects.filter(registration=registration).count(), 0)


@pytest.mark.django_db(transaction=True)
class TestInstallmentFallbackLogic(BaseTestCase):
    """Test cases for installment payment fallback logic"""

    def test_installment_fallback_no_installments(self) -> None:
        """Test fallback when no installments are configured"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Ensure membership has no approval date to avoid interference with deadline calculation
        membership = get_user_membership(member, association.id)
        membership.date = None
        membership.save()

        # Set registration amounts
        registration.tot_iscr = Decimal("300.00")
        registration.tot_payed = Decimal("0.00")

        # Call installment check with no installments configured
        installment_check(registration, alert=30, association_id=association.id)

        # Should use registration creation date as deadline
        self.assertIsNotNone(registration.deadline)
        self.assertEqual(registration.quota, Decimal("300.00"))

    def test_installment_fallback_all_distant(self) -> None:
        """Test fallback when all installments are beyond alert threshold"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Create two installments both distant
        RegistrationInstallment.objects.create(
            event=run.event, amount=Decimal("100.00"), days_deadline=150, order=1, number=1
        )
        RegistrationInstallment.objects.create(
            event=run.event, amount=Decimal("200.00"), days_deadline=300, order=2, number=2
        )

        # Set registration amounts - player paid first installment
        registration.tot_iscr = Decimal("300.00")
        registration.tot_payed = Decimal("200.00")

        # Call installment check with alert threshold of 30 days
        installment_check(registration, alert=30, association_id=association.id)

        # Should NOT set alert - quota should be 0
        self.assertEqual(registration.quota, 0)
        self.assertEqual(registration.deadline, 0)

    def test_installment_check_with_close_installment(self) -> None:
        """Test installment check when an installment is within alert threshold"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Ensure membership has no approval date to avoid interference with deadline calculation
        membership = get_user_membership(member, association.id)
        membership.date = None
        membership.save()

        # Create installment that is close (within 30 days)
        RegistrationInstallment.objects.create(
            event=run.event, amount=Decimal("100.00"), days_deadline=10, order=1, number=1
        )

        # Set registration amounts
        registration.tot_iscr = Decimal("300.00")
        registration.tot_payed = Decimal("0.00")

        # Call installment check
        installment_check(registration, alert=30, association_id=association.id)

        # Should set quota and deadline
        self.assertEqual(registration.quota, Decimal("100.00"))
        self.assertIsNotNone(registration.deadline)
        self.assertGreaterEqual(registration.deadline, 0)

    def test_installment_fallback_debt_no_valid_deadline(self) -> None:
        """Test fallback when there's debt but no valid installment deadline"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Ensure membership has no approval date to avoid interference with deadline calculation
        membership = get_user_membership(member, association.id)
        membership.date = None
        membership.save()

        # Clean up any existing installments from previous tests
        RegistrationInstallment.objects.filter(event=run.event).delete()

        # Create installment with negative deadline (already passed)
        RegistrationInstallment.objects.create(
            event=run.event, amount=Decimal("100.00"), days_deadline=-50, order=1, number=1
        )

        # Set registration amounts
        registration.tot_iscr = Decimal("300.00")
        registration.tot_payed = Decimal("0.00")

        # Call installment check
        installment_check(registration, alert=30, association_id=association.id)

        # Should set immediate payment (deadline negative)
        self.assertEqual(registration.quota, Decimal("300.00"))
        self.assertEqual(registration.deadline, -50)

    def test_installment_check_player_paid_enough(self) -> None:
        """Test installment check when player has paid enough for current installment"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Create two installments
        RegistrationInstallment.objects.create(
            event=run.event, amount=Decimal("100.00"), days_deadline=10, order=1, number=1
        )
        RegistrationInstallment.objects.create(
            event=run.event, amount=Decimal("200.00"), days_deadline=150, order=2, number=2
        )

        # Player has paid more than first installment
        registration.tot_iscr = Decimal("300.00")
        registration.tot_payed = Decimal("150.00")

        # Call installment check
        installment_check(registration, alert=30, association_id=association.id)

        # First installment is covered, second is distant, should not set alert
        self.assertEqual(registration.quota, 0)
        self.assertEqual(registration.deadline, 0)

    def test_installment_check_partial_payment_close_deadline(self) -> None:
        """Test installment check with partial payment and close deadline"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Ensure membership has no approval date to avoid interference with deadline calculation
        membership = get_user_membership(member, association.id)
        membership.date = None
        membership.save()

        # Create installment close to deadline
        RegistrationInstallment.objects.create(
            event=run.event, amount=Decimal("150.00"), days_deadline=15, order=1, number=1
        )

        # Player has paid partially
        registration.tot_iscr = Decimal("300.00")
        registration.tot_payed = Decimal("50.00")

        # Call installment check
        installment_check(registration, alert=30, association_id=association.id)

        # Should set remaining quota for this installment
        self.assertEqual(registration.quota, Decimal("100.00"))  # 150 - 50
        self.assertIsNotNone(registration.deadline)
        self.assertGreaterEqual(registration.deadline, 0)

    def test_installment_fallback_overdue_with_distant_future(self) -> None:
        """Test fallback when overdue installments exist alongside distant future ones.

        Regression test: previously quota was incorrectly set to 0 when has_distant_installments
        was True, even if earlier installments were already past due and unpaid.
        """
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("585.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Ensure membership has no approval date to avoid interference with deadline calculation
        membership = get_user_membership(member, association.id)
        membership.date = None
        membership.save()

        # Installment 1: overdue (days_deadline negative -> in the past)
        RegistrationInstallment.objects.create(
            event=run.event, amount=Decimal("125.00"), days_deadline=-200, order=1, number=1
        )
        # Installment 2: overdue (fixed date in the past)
        RegistrationInstallment.objects.create(
            event=run.event,
            amount=Decimal("150.00"),
            date_deadline=date.today() - timedelta(days=2),
            order=2,
            number=2,
        )
        # Installment 3: distant future (beyond alert threshold of 30)
        RegistrationInstallment.objects.create(
            event=run.event,
            amount=Decimal("150.00"),
            date_deadline=date.today() + timedelta(days=59),
            order=3,
            number=3,
        )

        # Player has not paid anything
        registration.tot_iscr = Decimal("585.00")
        registration.tot_payed = Decimal("0.00")
        registration.quota = 0

        installment_check(registration, alert=30, association_id=association.id)

        # Overdue cumulative is 275 (125 + 150); quota should reflect that debt
        self.assertEqual(registration.quota, Decimal("275.00"))
        self.assertEqual(registration.deadline, -200)


class TestQuotaCheckFallbackLogic(BaseTestCase):
    """Test cases for quota_check payment fallback logic"""

    def test_quota_check_all_distant(self) -> None:
        """Test quota_check when all quotas are beyond alert threshold"""
        from datetime import timedelta

        from django.utils import timezone

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("400.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Set event start date far in future (120 days)
        run.start = timezone.now().date() + timedelta(days=120)
        run.save()

        # Set registration to have 4 quotas
        registration.quotas = 4
        registration.tot_iscr = Decimal("400.00")
        registration.tot_payed = Decimal("300.00")  # Paid 3 quotas already

        # Call quota_check with alert threshold of 30 days
        # All 4 quota deadlines will be beyond 30 days (at ~90, 60, 30, 0 days from event)
        # Since event is 120 days away, even the last quota is beyond alert
        quota_check(registration, run.start, alert=30, association_id=association.id)

        # Should NOT require immediate payment - quota should be 0
        self.assertEqual(registration.quota, 0)
        self.assertEqual(registration.deadline, 0)

    def test_quota_check_partial_payment_close_deadline(self) -> None:
        """Test quota_check with partial payment and close deadline"""
        from datetime import timedelta

        from django.utils import timezone

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("400.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Set event start date relatively soon (40 days)
        run.start = timezone.now().date() + timedelta(days=40)
        run.save()

        # Set registration to have 4 quotas
        registration.quotas = 4
        registration.tot_iscr = Decimal("400.00")
        registration.tot_payed = Decimal("200.00")  # Paid 2 quotas

        # Call quota_check with alert threshold of 30 days
        quota_check(registration, run.start, alert=30, association_id=association.id)

        # Should set quota for next payment
        self.assertGreater(registration.quota, 0)
        self.assertIsNotNone(registration.deadline)
        self.assertGreaterEqual(registration.deadline, 0)

    def test_quota_check_no_payment_immediate_event(self) -> None:
        """Test quota_check when event is imminent and no payment made"""
        from datetime import timedelta

        from django.utils import timezone

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("400.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Set event start date very soon (5 days)
        run.start = timezone.now().date() + timedelta(days=5)
        run.save()

        # Set registration to have 4 quotas
        registration.quotas = 4
        registration.tot_iscr = Decimal("400.00")
        registration.tot_payed = Decimal("0.00")  # No payment

        # Call quota_check with alert threshold of 30 days
        quota_check(registration, run.start, alert=30, association_id=association.id)

        # Should require payment for first quota that's within alert
        # The function returns at the FIRST valid quota found
        self.assertGreater(registration.quota, 0)
        self.assertIsNotNone(registration.deadline)

    def test_quota_check_paid_ahead_next_distant(self) -> None:
        """Test quota_check when player paid ahead and next quota is distant"""
        from datetime import timedelta

        from django.utils import timezone

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("400.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Set event start date in future (90 days)
        run.start = timezone.now().date() + timedelta(days=90)
        run.save()

        # Set registration to have 4 quotas (100€ each)
        # Quotas due at: ~67, 45, 22, 0 days from now
        registration.quotas = 4
        registration.tot_iscr = Decimal("400.00")
        registration.tot_payed = Decimal("100.00")  # Paid first quota

        # Call quota_check with alert threshold of 30 days
        # Quota 1 (67 days): beyond alert, skip
        # Quota 2 (45 days): beyond alert, skip
        # Quota 3 (22 days): within alert, but already paid enough (cumulative 300 > 100 paid)
        quota_check(registration, run.start, alert=30, association_id=association.id)

        # Next payment due is quota 3 at ~22 days, should set that
        # OR if all remaining quotas have been evaluated and next is distant, quota=0
        # Since quota 3 is at 22 days (< 30 alert), it should be set
        if registration.deadline > 0:
            self.assertGreater(registration.quota, 0)
        else:
            # If all quotas evaluated were already paid or distant
            self.assertEqual(registration.quota, 0)

    def test_quota_check_overdue_with_future_quota(self) -> None:
        """Test quota_check with overdue quota and valid future quota - should accumulate"""
        from datetime import timedelta

        from django.utils import timezone

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Set event 90 days in future, registration created 10 days ago
        run.start = timezone.now().date() + timedelta(days=90)
        run.save()
        registration.created = timezone.now() - timedelta(days=10)

        # 3 quotas: quota 1 deadline ~18 days, quota 2 ~23 days (both within alert), quota 3 ~56 days
        registration.quotas = 3
        registration.tot_iscr = Decimal("300.00")
        registration.tot_payed = Decimal("0.00")

        quota_check(registration, run.start, alert=30, association_id=association.id)

        # Should show quota 1 + quota 2 accumulated (199€ due to floor), with quota 2's deadline
        # floor(300 * 2/3) = floor(200.0) but with Decimal can be 199
        self.assertIn(registration.quota, [199, Decimal("200.00")])
        self.assertGreater(registration.deadline, 0)  # Should be around 23 days
        self.assertLess(registration.deadline, 30)

    def test_quota_check_only_overdue_quotas(self) -> None:
        """Test quota_check with overdue quota followed by distant quota"""
        from datetime import timedelta

        from django.utils import timezone

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Event 100 days in future, registration created 80 days ago
        # This creates: quota 1 @ 88 days (beyond alert), quota 2 @ -20 days (overdue), quota 3 @ 40 days (beyond alert)
        run.start = timezone.now().date() + timedelta(days=100)
        run.save()
        registration.created = timezone.now() - timedelta(days=80)

        # 3 quotas
        registration.quotas = 3
        registration.tot_iscr = Decimal("300.00")
        registration.tot_payed = Decimal("0.00")

        quota_check(registration, run.start, alert=30, association_id=association.id)

        # Quota 1 is beyond alert (88), quota 2 is overdue (-20), quota 3 is beyond alert (40)
        # Quota 2 represents CUMULATIVE 2/3 of total (200€), not just the second installment
        # So should show 199-200€ (cumulative up to quota 2) with immediate deadline
        self.assertIn(registration.quota, [199, Decimal("200.00")])
        self.assertEqual(registration.deadline, -72)  # Immediate payment

    def test_quota_check_first_quota_always_shown(self) -> None:
        """Test quota_check shows first quota when within alert threshold"""
        from datetime import timedelta

        from django.utils import timezone

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Event 90 days in future, registration just created (10 days ago)
        # This creates: quota 1 @ 18 days, quota 2 @ 23 days (both within alert)
        run.start = timezone.now().date() + timedelta(days=90)
        run.save()
        registration.created = timezone.now() - timedelta(days=10)

        # 3 quotas: first two within alert (18, 23 days), third beyond (56 days)
        registration.quotas = 3
        registration.tot_iscr = Decimal("300.00")
        registration.tot_payed = Decimal("0.00")

        quota_check(registration, run.start, alert=30, association_id=association.id)

        # First two quotas are within alert, so should show ~199-200€ (due to floor)
        self.assertIn(registration.quota, [199, Decimal("200.00")])
        self.assertGreater(registration.deadline, 0)
        self.assertLess(registration.deadline, 30)

    def test_quota_check_multiple_overdue_accumulation(self) -> None:
        """Test quota_check accumulates multiple overdue quotas correctly"""
        from datetime import timedelta

        from django.utils import timezone

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("400.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Event 50 days in future, registration created 60 days ago
        run.start = timezone.now().date() + timedelta(days=50)
        run.save()
        registration.created = timezone.now() - timedelta(days=60)

        # 4 quotas: first 3 overdue, last one within alert
        registration.quotas = 4
        registration.tot_iscr = Decimal("400.00")
        registration.tot_payed = Decimal("0.00")

        quota_check(registration, run.start, alert=30, association_id=association.id)

        # Should show all 4 quotas accumulated (400€) with last quota's deadline
        self.assertEqual(registration.quota, Decimal("400.00"))
        self.assertGreaterEqual(registration.deadline, 0)

    def test_quota_check_overdue_with_partial_payment(self) -> None:
        """Test quota_check with overdue quotas and partial payment"""
        from datetime import timedelta

        from django.utils import timezone

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Event 90 days in future, registration created 20 days ago
        run.start = timezone.now().date() + timedelta(days=90)
        run.save()
        registration.created = timezone.now() - timedelta(days=20)

        # 3 quotas, first one overdue
        registration.quotas = 3
        registration.tot_iscr = Decimal("300.00")
        registration.tot_payed = Decimal("50.00")  # Partial payment of first quota

        quota_check(registration, run.start, alert=30, association_id=association.id)

        # Should show remaining from overdue + next quota
        self.assertGreater(registration.quota, Decimal("50.00"))
        self.assertLessEqual(registration.quota, Decimal("200.00"))
        self.assertGreater(registration.deadline, 0)


class TestMembershipFeeForReg(BaseTestCase):
    """Test cases for get_membership_fee_for_reg bundling logic."""

    MEMBERSHIP_FEE = 20

    def _setup(self, event_year: int, separated: bool = False) -> tuple:

        member = self.get_member()
        association = self.get_association()
        run = self.get_run()

        run.start = date(event_year, 6, 1)
        run.end = date(event_year, 6, 2)
        run.save()

        AssociationConfig.objects.filter(association=association, name="membership_fee_separated").delete()
        AssociationConfig.objects.filter(association=association, name="membership_fee").delete()

        AssociationConfig.objects.create(
            association=association,
            name="membership_fee_separated",
            value=str(separated),
        )
        AssociationConfig.objects.create(
            association=association,
            name="membership_fee",
            value=str(self.MEMBERSHIP_FEE),
        )

        registration = self.create_registration(member=member, run=run)
        return association, member, registration

    def test_separated_true_returns_zero(self) -> None:
        """When membership_fee_separated is True, fee is not bundled."""
        from django.utils import timezone

        year = timezone.now().year
        association, _member, registration = self._setup(year, separated=True)
        result = get_membership_fee_for_reg(association.id, registration.member_id, registration.run, registration)
        self.assertEqual(result, 0)

    @patch("larpmanager.accounting.member.get_association_features", return_value={"membership": 1})
    def test_current_year_bundled(self, mock_features: Any) -> None:
        """Event in current year with separated=False bundles the fee."""
        from django.utils import timezone

        year = timezone.now().year
        association, _member, registration = self._setup(year, separated=False)
        result = get_membership_fee_for_reg(association.id, registration.member_id, registration.run, registration)
        self.assertEqual(result, self.MEMBERSHIP_FEE)

    @patch("larpmanager.accounting.member.get_association_features", return_value={"membership": 1})
    def test_next_year_bundled(self, mock_features: Any) -> None:
        """Event in next year with separated=False bundles the fee."""
        from django.utils import timezone

        year = timezone.now().year + 1
        association, _member, registration = self._setup(year, separated=False)
        result = get_membership_fee_for_reg(association.id, registration.member_id, registration.run, registration)
        self.assertEqual(result, self.MEMBERSHIP_FEE)

    @patch("larpmanager.accounting.member.get_association_features", return_value={"membership": 1})
    def test_future_year_bundled(self, mock_features: Any) -> None:
        """Event two years ahead is still bundled (only past years are excluded)."""
        from django.utils import timezone

        year = timezone.now().year + 2
        association, _member, registration = self._setup(year, separated=False)
        result = get_membership_fee_for_reg(association.id, registration.member_id, registration.run, registration)
        self.assertEqual(result, self.MEMBERSHIP_FEE)

    def test_already_paid_returns_zero(self) -> None:
        """Member who already paid membership for event year gets no duplicate charge."""
        from django.utils import timezone

        year = timezone.now().year
        association, member, registration = self._setup(year, separated=False)
        AccountingItemMembership.objects.create(
            member=member,
            association=association,
            year=year,
            value=self.MEMBERSHIP_FEE,
        )
        result = get_membership_fee_for_reg(association.id, registration.member_id, registration.run, registration)
        self.assertEqual(result, 0)

    def test_no_fee_configured_returns_zero(self) -> None:
        """When membership_fee is 0, nothing is bundled."""
        from django.utils import timezone

        year = timezone.now().year
        association, _member, registration = self._setup(year, separated=False)
        cfg = AssociationConfig.objects.get(association=association, name="membership_fee")
        cfg.value = "0"
        cfg.save()
        result = get_membership_fee_for_reg(association.id, registration.member_id, registration.run, registration)
        self.assertEqual(result, 0)

    def test_get_registration_iscr_excludes_membership_fee(self) -> None:
        """get_registration_iscr never includes the membership fee (tracked separately)."""
        from django.utils import timezone

        from larpmanager.models.registration import RegistrationTicket

        year = timezone.now().year
        _association, _member, registration = self._setup(year, separated=False)
        ticket = RegistrationTicket.objects.create(
            event=registration.run.event,
            name="Standard",
            price=50,
        )
        registration.ticket = ticket
        result = get_registration_iscr(registration)
        self.assertEqual(result, 50)

    @patch("larpmanager.accounting.member.get_association_features", return_value={})
    def test_membership_feature_not_enabled_returns_zero(self, mock_features: Any) -> None:
        """When the membership feature is not enabled, fee is not bundled."""
        from django.utils import timezone

        year = timezone.now().year
        association, _member, registration = self._setup(year, separated=False)
        result = get_membership_fee_for_reg(association.id, registration.member_id, registration.run, registration)
        self.assertEqual(result, 0)

    @patch("larpmanager.accounting.member.get_association_features", return_value={"membership": 1})
    def test_membership_feature_enabled_returns_fee(self, mock_features: Any) -> None:
        """When the membership feature is enabled, fee is bundled."""
        from django.utils import timezone

        year = timezone.now().year
        association, _member, registration = self._setup(year, separated=False)
        result = get_membership_fee_for_reg(association.id, registration.member_id, registration.run, registration)
        self.assertEqual(result, self.MEMBERSHIP_FEE)


@pytest.mark.django_db(transaction=True)
class TestProcessPaymentMembershipSplit(BaseTestCase):
    """Tests that _process_payment splits the bundled membership fee out of the
    registration payment and creates AccountingItemMembership atomically."""

    TICKET_PRICE = 100
    MEMBERSHIP_FEE = 30

    def setUp(self) -> None:
        from unittest.mock import patch

        from django.core.cache import cache

        super().setUp()
        cache.clear()
        self._features_patcher = patch(
            "larpmanager.accounting.member.get_association_features",
            return_value={"membership": 1},
        )
        self._features_patcher.start()

    def tearDown(self) -> None:
        self._features_patcher.stop()
        super().tearDown()

    def _setup(self, year: int):
        from datetime import date
        from decimal import Decimal

        from larpmanager.accounting.member import membership_fee_pending_config_name
        from larpmanager.models.accounting import PaymentInvoice, PaymentStatus, PaymentType
        from larpmanager.models.base import PaymentMethod
        from larpmanager.models.member import MemberConfig
        from larpmanager.models.registration import RegistrationTicket

        association = self.get_association()
        member = self.get_member()

        AssociationConfig.objects.filter(association=association, name="membership_fee_separated").delete()
        AssociationConfig.objects.filter(association=association, name="membership_fee").delete()
        AssociationConfig.objects.create(association=association, name="membership_fee_separated", value="False")
        AssociationConfig.objects.create(association=association, name="membership_fee", value=str(self.MEMBERSHIP_FEE))

        run = self.get_run()
        run.start = date(year, 7, 1)
        run.end = date(year, 7, 2)
        run.save()
        ticket = RegistrationTicket.objects.create(event=run.event, name="T", price=self.TICKET_PRICE)
        registration = self.create_registration(member=member, run=run, ticket=ticket)
        registration.tot_iscr = self.TICKET_PRICE
        registration.tot_payed = 0
        registration.save()

        # Simulate the invoice created when user submits payment (mc_gross = ticket + membership)
        method, _ = PaymentMethod.objects.get_or_create(slug="wire", defaults={"name": "Wire"})
        invoice = PaymentInvoice.objects.create(
            typ=PaymentType.REGISTRATION,
            idx=registration.id,
            member=member,
            association=association,
            mc_gross=Decimal(self.TICKET_PRICE + self.MEMBERSHIP_FEE),
            mc_fee=Decimal(0),
            status=PaymentStatus.CREATED,
            causal="test",
            cod=f"TEST-{registration.id}",
            method=method,
        )

        # Simulate the MemberConfig reservation created in set_data_invoice
        config_name = membership_fee_pending_config_name(association.id, year)
        MemberConfig.objects.create(member=member, name=config_name, value=str(registration.id))

        return association, member, registration, invoice

    def test_payment_value_reduced_by_membership_fee(self) -> None:
        """AccountingItemPayment.value equals ticket price only, not ticket+membership."""
        from django.utils import timezone

        from larpmanager.accounting.payment import _process_payment
        from larpmanager.models.accounting import AccountingItemPayment

        year = timezone.now().year
        _association, _member, registration, invoice = self._setup(year)
        _process_payment(invoice)
        item = AccountingItemPayment.objects.get(registration=registration)
        self.assertEqual(item.value, self.TICKET_PRICE)

    def test_membership_item_created_on_payment(self) -> None:
        """AccountingItemMembership is created when the bundled payment is processed."""
        from django.utils import timezone

        from larpmanager.accounting.payment import _process_payment

        year = timezone.now().year
        association, member, _registration, invoice = self._setup(year)
        _process_payment(invoice)
        self.assertTrue(
            AccountingItemMembership.objects.filter(
                member=member, association=association, year=year, deleted__isnull=True
            ).exists()
        )

    def test_member_config_reservation_deleted_after_payment(self) -> None:
        """MemberConfig reservation is cleaned up once the membership is created."""
        from django.utils import timezone

        from larpmanager.accounting.payment import _process_payment
        from larpmanager.accounting.member import membership_fee_pending_config_name
        from larpmanager.models.member import MemberConfig

        year = timezone.now().year
        association, member, _registration, invoice = self._setup(year)
        _process_payment(invoice)
        config_name = membership_fee_pending_config_name(association.id, year)
        self.assertFalse(MemberConfig.objects.filter(member=member, name=config_name, deleted__isnull=True).exists())
