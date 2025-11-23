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

from datetime import timedelta
from decimal import Decimal

from larpmanager.accounting.registration import (
    cancel_reg,
    get_date_surcharge,
    get_display_choice,
    get_reg_iscr,
    get_reg_payments,
    get_reg_transactions,
    installment_check,
    registration_payments_status,
    round_to_nearest_cent,
)
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemPayment,
    AccountingItemTransaction,
    Discount,
    DiscountType,
    PaymentChoices,
)
from larpmanager.models.form import RegistrationChoice
from larpmanager.models.registration import (
    RegistrationCharacterRel,
    RegistrationInstallment,
    RegistrationSurcharge,
    TicketTier,
)
from larpmanager.tests.unit.base import BaseTestCase


class TestRegistrationCalculationFunctions(BaseTestCase):
    """Test cases for registration fee calculation functions"""

    def test_get_reg_iscr_basic_ticket(self) -> None:
        """Test basic registration fee with ticket only"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("100.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        result = get_reg_iscr(registration)

        self.assertEqual(result, Decimal("100.00"))

    def test_get_reg_iscr_with_additionals(self) -> None:
        """Test registration fee with additional tickets"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("50.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=2)

        result = get_reg_iscr(registration)

        # Base ticket + 2 additionals = 50 + (50*2) = 150
        self.assertEqual(result, Decimal("150.00"))

    def test_get_reg_iscr_with_zero_additionals(self) -> None:
        """Test registration fee with zero additional tickets"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("50.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=0)

        result = get_reg_iscr(registration)

        # Just base ticket
        self.assertEqual(result, Decimal("50.00"))

    def test_get_reg_iscr_with_one_additional(self) -> None:
        """Test registration fee with one additional ticket"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("75.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=1)

        result = get_reg_iscr(registration)

        # Base ticket + 1 additional = 75 + 75 = 150
        self.assertEqual(result, Decimal("150.00"))

    def test_get_reg_iscr_with_max_additionals(self) -> None:
        """Test registration fee with maximum (5) additional tickets"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("60.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=5)

        result = get_reg_iscr(registration)

        # Base ticket + 5 additionals = 60 + (60*5) = 360
        self.assertEqual(result, Decimal("360.00"))

    def test_get_reg_iscr_additionals_with_options(self) -> None:
        """Test registration fee with both additional tickets and options"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("50.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=2)

        # Add registration option
        question, option1, option2 = self.question_with_options(event=run.event)
        option1.price = Decimal("15.00")
        option1.save()
        RegistrationChoice.objects.create(reg=registration, option=option1, question=question)

        result = get_reg_iscr(registration)

        # Base + additionals + option = 50 + 100 + 15 = 165
        self.assertEqual(result, Decimal("165.00"))

    def test_get_reg_iscr_additionals_with_pay_what(self) -> None:
        """Test registration fee with additional tickets and pay-what-you-want"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("40.00"))
        registration = self.create_registration(
            member=member, run=run, ticket=ticket, additionals=3, pay_what=Decimal("20.00")
        )

        result = get_reg_iscr(registration)

        # Base + additionals + pay_what = 40 + 120 + 20 = 180
        self.assertEqual(result, Decimal("180.00"))

    def test_get_reg_iscr_additionals_with_discount(self) -> None:
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

        result = get_reg_iscr(registration)

        # Base + additionals - discount = 100 + 200 - 50 = 250
        self.assertEqual(result, Decimal("250.00"))

    def test_get_reg_iscr_additionals_with_surcharge(self) -> None:
        """Test registration fee with additional tickets and surcharge"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("80.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, additionals=1)

        # Add surcharge
        registration.surcharge = Decimal("25.00")

        result = get_reg_iscr(registration)

        # Base + additionals + surcharge = 80 + 80 + 25 = 185
        self.assertEqual(result, Decimal("185.00"))

    def test_get_reg_iscr_additionals_all_features(self) -> None:
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
        RegistrationChoice.objects.create(reg=registration, option=option1, question=question)

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

        result = get_reg_iscr(registration)

        # Base + additionals + option + pay_what + surcharge - discount
        # = 60 + 120 + 20 + 10 + 15 - 30 = 195
        self.assertEqual(result, Decimal("195.00"))

    def test_get_reg_iscr_additionals_no_ticket(self) -> None:
        """Test registration fee with additionals but no ticket (edge case)"""
        member = self.get_member()
        run = self.get_run()
        # Create registration without ticket
        registration = self.create_registration(member=member, run=run, ticket=None, additionals=2)

        result = get_reg_iscr(registration)

        # No ticket means no base price, additionals should not add anything
        self.assertEqual(result, 0)

    def test_get_reg_iscr_with_pay_what(self) -> None:
        """Test registration fee with pay-what-you-want amount"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("50.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket, pay_what=Decimal("25.00"))

        result = get_reg_iscr(registration)

        # Ticket + pay_what = 50 + 25 = 75
        self.assertEqual(result, Decimal("75.00"))

    def test_get_reg_iscr_with_options(self) -> None:
        """Test registration fee with registration options"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("50.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        question, option1, option2 = self.question_with_options(event=run.event)
        option1.price = Decimal("10.00")
        option1.save()

        RegistrationChoice.objects.create(reg=registration, option=option1, question=question)

        result = get_reg_iscr(registration)

        # Ticket + option = 50 + 10 = 60
        self.assertEqual(result, Decimal("60.00"))

    def test_get_reg_iscr_with_discount(self) -> None:
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

        result = get_reg_iscr(registration)

        # Ticket - discount = 100 - 20 = 80
        self.assertEqual(result, Decimal("80.00"))

    def test_get_reg_iscr_with_surcharge(self) -> None:
        """Test registration fee with surcharge"""
        member = self.get_member()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("100.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

        # Set surcharge on registration object (not passed to create)
        registration.surcharge = Decimal("15.00")

        result = get_reg_iscr(registration)

        # Ticket + surcharge = 100 + 15 = 115
        self.assertEqual(result, Decimal("115.00"))

    def test_get_reg_iscr_gifted_no_discount(self) -> None:
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

        result = get_reg_iscr(registration)

        # Gifted registrations don't get discounts
        self.assertEqual(result, Decimal("100.00"))

    def test_get_reg_iscr_minimum_zero(self) -> None:
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

        result = get_reg_iscr(registration)

        # Should not go below zero
        self.assertEqual(result, 0)


class TestPaymentCalculationFunctions(BaseTestCase):
    """Test cases for payment calculation functions"""

    def test_get_reg_payments_basic(self) -> None:
        """Test basic payment calculation"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("50.00")
        )

        result = get_reg_payments(registration)

        self.assertEqual(result, Decimal("50.00"))

    def test_get_reg_payments_multiple(self) -> None:
        """Test payment calculation with multiple payments"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("30.00")
        )
        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("20.00")
        )

        result = get_reg_payments(registration)

        self.assertEqual(result, Decimal("50.00"))

    def test_get_reg_payments_excludes_hidden(self) -> None:
        """Test payment calculation excludes hidden payments"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("30.00")
        )
        AccountingItemPayment.objects.create(
            member=member,
            association=association,
            reg=registration,
            pay=PaymentChoices.MONEY,
            value=Decimal("20.00"),
            hide=True,
        )

        result = get_reg_payments(registration)

        # Should exclude hidden payment
        self.assertEqual(result, Decimal("30.00"))

    def test_get_reg_payments_sets_dictionary(self) -> None:
        """Test payment calculation sets payments dictionary"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("30.00")
        )
        AccountingItemPayment.objects.create(
            member=member, association=association, reg=registration, pay=PaymentChoices.TOKEN, value=Decimal("20.00")
        )

        get_reg_payments(registration)

        self.assertIn(PaymentChoices.MONEY, registration.payments)
        self.assertIn(PaymentChoices.TOKEN, registration.payments)
        self.assertEqual(registration.payments[PaymentChoices.MONEY], Decimal("30.00"))
        self.assertEqual(registration.payments[PaymentChoices.TOKEN], Decimal("20.00"))

    def test_get_reg_transactions_basic(self) -> None:
        """Test transaction fee calculation"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemTransaction.objects.create(
            member=member, association=association, reg=registration, value=Decimal("2.50"), user_burden=True
        )

        result = get_reg_transactions(registration)

        self.assertEqual(result, Decimal("2.50"))

    def test_get_reg_transactions_excludes_non_user_burden(self) -> None:
        """Test transaction calculation excludes non-user-burden fees"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        registration = self.create_registration(member=member, run=run)

        AccountingItemTransaction.objects.create(
            member=member, association=association, reg=registration, value=Decimal("2.50"), user_burden=True
        )
        AccountingItemTransaction.objects.create(
            member=member, association=association, reg=registration, value=Decimal("3.00"), user_burden=False
        )

        result = get_reg_transactions(registration)

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
        result = round_to_nearest_cent(10.52)

        self.assertEqual(result, 10.5)

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

        RegistrationCharacterRel.objects.create(reg=registration, character=character)

        cancel_reg(registration)

        # Should delete character relationships
        self.assertEqual(RegistrationCharacterRel.objects.filter(reg=registration).count(), 0)


class TestInstallmentFallbackLogic(BaseTestCase):
    """Test cases for installment payment fallback logic"""

    def test_installment_fallback_no_installments(self) -> None:
        """Test fallback when no installments are configured"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

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
        self.assertIsNone(registration.deadline)

    def test_installment_check_with_close_installment(self) -> None:
        """Test installment check when an installment is within alert threshold"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

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

        # Create installment with negative deadline (already passed)
        RegistrationInstallment.objects.create(
            event=run.event, amount=Decimal("100.00"), days_deadline=-50, order=1, number=1
        )

        # Set registration amounts
        registration.tot_iscr = Decimal("300.00")
        registration.tot_payed = Decimal("0.00")

        # Call installment check
        installment_check(registration, alert=30, association_id=association.id)

        # Should set immediate payment (deadline=0)
        self.assertEqual(registration.quota, Decimal("300.00"))
        self.assertEqual(registration.deadline, 0)

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
        self.assertIsNone(registration.deadline)

    def test_installment_check_partial_payment_close_deadline(self) -> None:
        """Test installment check with partial payment and close deadline"""
        member = self.get_member()
        association = self.get_association()
        run = self.get_run()
        ticket = self.ticket(event=run.event, price=Decimal("300.00"))
        registration = self.create_registration(member=member, run=run, ticket=ticket)

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
