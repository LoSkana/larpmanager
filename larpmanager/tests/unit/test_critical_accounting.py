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

import pytest
from django.contrib.auth.models import User
from django.db import transaction

from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemExpense,
    AccountingItemOther,
    AccountingItemPayment,
    AccountingItemTransaction,
    OtherChoices,
    PaymentChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
)
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.form import (
    BaseQuestionType,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
)
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import (
    Registration,
    RegistrationInstallment,
    RegistrationSurcharge,
    RegistrationTicket,
    TicketTier,
)


@pytest.mark.django_db
class TestCriticalRegistrationAccounting:
    """Test critical registration accounting functions"""

    def test_update_registration_accounting_complete_workflow(self, registration, event):
        """Test complete registration accounting update workflow"""
        from larpmanager.accounting.registration import update_registration_accounting

        # Setup complex registration scenario
        registration.tot_iscr = Decimal("200.00")
        registration.tot_payed = Decimal("0.00")
        registration.quotas = 4
        registration.save()

        # Create some payments
        payment1 = AccountingItemPayment.objects.create(
            member=registration.member,
            reg=registration,
            pay=PaymentChoices.MONEY,
            value=Decimal("50.00"),
            assoc=registration.run.event.assoc,
        )

        payment2 = AccountingItemPayment.objects.create(
            member=registration.member,
            reg=registration,
            pay=PaymentChoices.CREDIT,
            value=Decimal("30.00"),
            assoc=registration.run.event.assoc,
        )

        # Create transaction fee
        transaction_fee = AccountingItemTransaction.objects.create(
            member=registration.member,
            reg=registration,
            value=Decimal("2.50"),
            user_burden=True,
            assoc=registration.run.event.assoc,
        )

        # Create discount
        discount = AccountingItemDiscount.objects.create(
            member=registration.member, run=registration.run, value=Decimal("20.00"), assoc=registration.run.event.assoc
        )

        # Create surcharge
        surcharge = RegistrationSurcharge.objects.create(
            event=event, date=date.today() - timedelta(days=1), amount=Decimal("15.00"), description="Late fee"
        )

        initial_tot_iscr = registration.tot_iscr
        initial_tot_payed = registration.tot_payed

        # Mock feature checking
        with patch("larpmanager.accounting.registration.get_event_features") as mock_features:
            mock_features.return_value = ["payment"]

            # Call the critical function
            update_registration_accounting(registration)

            # Verify tot_iscr calculation (includes surcharge, excludes discount)
            expected_tot_iscr = Decimal("200.00") + Decimal("15.00") - Decimal("20.00")  # 195.00
            assert registration.tot_iscr == expected_tot_iscr, (
                f"Expected tot_iscr {expected_tot_iscr}, got {registration.tot_iscr}"
            )

            # Verify tot_payed calculation (includes payments, excludes transaction fees)
            expected_tot_payed = Decimal("50.00") + Decimal("30.00") - Decimal("2.50")  # 77.50
            assert registration.tot_payed == expected_tot_payed, (
                f"Expected tot_payed {expected_tot_payed}, got {registration.tot_payed}"
            )

            # Verify remaining balance
            expected_remaining = expected_tot_iscr - expected_tot_payed  # 117.50
            actual_remaining = registration.tot_iscr - registration.tot_payed
            assert actual_remaining == expected_remaining, (
                f"Expected remaining {expected_remaining}, got {actual_remaining}"
            )

            # Verify quota calculation is triggered
            assert hasattr(registration, "quota"), "Registration should have quota attribute after accounting update"
            assert hasattr(registration, "deadline"), (
                "Registration should have deadline attribute after accounting update"
            )

    def test_update_registration_accounting_with_tokens_credits(self, registration):
        """Test registration accounting with token/credit usage"""
        from larpmanager.accounting.registration import update_registration_accounting

        # Setup registration with remaining balance
        registration.tot_iscr = Decimal("100.00")
        registration.tot_payed = Decimal("40.00")
        registration.save()

        # Mock member with tokens and credits
        mock_membership = Mock()
        mock_membership.tokens = Decimal("20")
        mock_membership.credit = Decimal("30")

        with patch("larpmanager.accounting.registration.get_event_features") as mock_features:
            mock_features.return_value = ["payment", "token_credit"]

            with patch("larpmanager.accounting.registration.handle_tokes_credits") as mock_handle_tc:
                # Call accounting update
                update_registration_accounting(registration)

                # Verify token/credit handling was called
                mock_handle_tc.assert_called_once()
                call_args = mock_handle_tc.call_args[0]

                assert call_args[0] == registration.run.event.assoc_id, "Should pass correct association ID"
                assert "token_credit" in call_args[1], "Should pass features including token_credit"
                assert call_args[2] == registration, "Should pass registration object"
                assert call_args[3] == Decimal("60.00"), f"Should pass remaining balance 60.00, got {call_args[3]}"

    def test_update_registration_accounting_cancelled_registration(self, registration):
        """Test accounting update for cancelled registration"""
        from larpmanager.accounting.registration import update_registration_accounting

        # Cancel the registration
        registration.cancellation_date = datetime.now()
        registration.save()

        initial_tot_iscr = registration.tot_iscr
        initial_tot_payed = registration.tot_payed

        # Call accounting update
        update_registration_accounting(registration)

        # Verify no changes for cancelled registration
        assert registration.tot_iscr == initial_tot_iscr, "Cancelled registration tot_iscr should not change"
        assert registration.tot_payed == initial_tot_payed, "Cancelled registration tot_payed should not change"

    def test_update_registration_accounting_fully_paid(self, registration):
        """Test accounting update for fully paid registration"""
        from larpmanager.accounting.registration import update_registration_accounting

        # Setup fully paid registration
        registration.tot_iscr = Decimal("100.00")
        registration.tot_payed = Decimal("100.00")
        registration.payment_date = None
        registration.save()

        with patch("larpmanager.accounting.registration.get_event_features") as mock_features:
            mock_features.return_value = ["payment"]

            # Call accounting update
            update_registration_accounting(registration)

            # Verify payment date is set
            assert registration.payment_date is not None, "Payment date should be set for fully paid registration"

            # Verify no quota/deadline for fully paid
            remaining = registration.tot_iscr - registration.tot_payed
            assert remaining == Decimal("0.00"), "Should have no remaining balance"

    def test_update_registration_accounting_membership_required(self, registration):
        """Test accounting update with membership requirement"""
        from larpmanager.accounting.registration import update_registration_accounting

        # Setup membership requirement
        membership = Membership.objects.create(
            member=registration.member,
            assoc=registration.run.event.assoc,
            status=MembershipStatus.PENDING,  # Not accepted
            date=date.today(),
        )

        with patch("larpmanager.accounting.registration.get_event_features") as mock_features:
            mock_features.return_value = ["payment", "membership"]

            with patch("larpmanager.accounting.registration.get_user_membership") as mock_get_membership:
                mock_get_membership.return_value = membership

                initial_values = {
                    "tot_iscr": registration.tot_iscr,
                    "tot_payed": registration.tot_payed,
                }

                # Call accounting update
                update_registration_accounting(registration)

                # Verify early return for non-accepted membership
                # Should not process further accounting
                assert not hasattr(registration, "quota"), "Should not set quota for non-accepted membership"


@pytest.mark.django_db
class TestCriticalPaymentProcessing:
    """Test critical payment processing functions"""

    def test_payment_received_registration_complete_workflow(self, payment_invoice, registration):
        """Test complete payment received workflow for registration"""
        from larpmanager.accounting.payment import payment_received

        # Setup payment invoice for registration
        payment_invoice.typ = PaymentType.REGISTRATION
        payment_invoice.idx = registration.id
        payment_invoice.mc_gross = Decimal("100.00")
        payment_invoice.mc_fee = Decimal("5.00")
        payment_invoice.save()

        # Mock association and features
        mock_assoc = Mock()
        mock_assoc.get_config.return_value = True

        initial_payment_count = AccountingItemPayment.objects.filter(reg=registration).count()
        initial_registration_payments = registration.num_payments if hasattr(registration, "num_payments") else 0

        with patch("larpmanager.accounting.payment.Association.objects.get") as mock_get_assoc:
            mock_get_assoc.return_value = mock_assoc

            with patch("larpmanager.accounting.payment.get_assoc_features") as mock_features:
                mock_features.return_value = ["e-invoice"]

                with patch("larpmanager.accounting.payment.Registration.objects.get") as mock_get_reg:
                    mock_get_reg.return_value = registration

                    with patch("larpmanager.accounting.payment.process_payment") as mock_process_einvoice:
                        # Call the critical function
                        result = payment_received(payment_invoice)

                        # Verify successful processing
                        assert result is True, "Payment processing should return True for success"

                        # Verify payment accounting item was created
                        payment_items = AccountingItemPayment.objects.filter(inv=payment_invoice)
                        assert payment_items.count() == 1, f"Expected 1 payment item, got {payment_items.count()}"

                        payment_item = payment_items.first()
                        assert payment_item.member == payment_invoice.member, "Payment item should have correct member"
                        assert payment_item.reg == registration, "Payment item should be linked to registration"
                        assert payment_item.value == payment_invoice.mc_gross, (
                            f"Payment value should be {payment_invoice.mc_gross}"
                        )
                        assert payment_item.pay == PaymentChoices.MONEY, "Payment should be money type"

                        # Verify e-invoice processing was triggered
                        mock_process_einvoice.assert_called_once_with(payment_invoice.id)

    def test_payment_received_with_fee_processing(self, payment_invoice, registration):
        """Test payment received with fee processing"""
        from larpmanager.accounting.payment import payment_received

        payment_invoice.typ = PaymentType.REGISTRATION
        payment_invoice.idx = registration.id
        payment_invoice.mc_gross = Decimal("100.00")
        payment_invoice.mc_fee = Decimal("5.00")
        payment_invoice.method = Mock()
        payment_invoice.method.slug = "paypal"
        payment_invoice.save()

        mock_assoc = Mock()
        mock_assoc.get_config.side_effect = lambda key, default: {"payment_fees_user": True}.get(key, default)

        with patch("larpmanager.accounting.payment.Association.objects.get") as mock_get_assoc:
            mock_get_assoc.return_value = mock_assoc

            with patch("larpmanager.accounting.payment.get_assoc_features") as mock_features:
                mock_features.return_value = []

                with patch("larpmanager.accounting.payment.get_payment_fee") as mock_get_fee:
                    mock_get_fee.return_value = 2.5  # 2.5% fee

                    with patch("larpmanager.accounting.payment.Registration.objects.get") as mock_get_reg:
                        mock_get_reg.return_value = registration

                        # Call payment processing
                        result = payment_received(payment_invoice)

                        # Verify fee transaction was created
                        fee_transactions = AccountingItemTransaction.objects.filter(inv=payment_invoice)
                        assert fee_transactions.count() == 1, (
                            f"Expected 1 fee transaction, got {fee_transactions.count()}"
                        )

                        fee_transaction = fee_transactions.first()
                        expected_fee = (float(payment_invoice.mc_gross) * 2.5) / 100  # 2.50
                        assert fee_transaction.value == expected_fee, (
                            f"Expected fee {expected_fee}, got {fee_transaction.value}"
                        )
                        assert fee_transaction.user_burden is True, "Fee should be user burden"
                        assert fee_transaction.reg == registration, "Fee should be linked to registration"

    def test_payment_received_membership_processing(self, payment_invoice):
        """Test payment received for membership"""
        from larpmanager.accounting.payment import payment_received

        payment_invoice.typ = PaymentType.MEMBERSHIP
        payment_invoice.mc_gross = Decimal("50.00")
        payment_invoice.save()

        mock_assoc = Mock()

        with patch("larpmanager.accounting.payment.Association.objects.get") as mock_get_assoc:
            mock_get_assoc.return_value = mock_assoc

            with patch("larpmanager.accounting.payment.get_assoc_features") as mock_features:
                mock_features.return_value = []

                # Call payment processing
                result = payment_received(payment_invoice)

                # Verify membership accounting item was created
                from larpmanager.models.accounting import AccountingItemMembership

                membership_items = AccountingItemMembership.objects.filter(inv=payment_invoice)
                assert membership_items.count() == 1, f"Expected 1 membership item, got {membership_items.count()}"

                membership_item = membership_items.first()
                assert membership_item.member == payment_invoice.member, "Membership item should have correct member"
                assert membership_item.value == payment_invoice.mc_gross, (
                    f"Membership value should be {payment_invoice.mc_gross}"
                )
                assert membership_item.year == datetime.now().year, "Membership should be for current year"

    def test_payment_received_donation_processing(self, payment_invoice):
        """Test payment received for donation"""
        from larpmanager.accounting.payment import payment_received

        payment_invoice.typ = PaymentType.DONATE
        payment_invoice.mc_gross = Decimal("75.00")
        payment_invoice.causal = "Donation for event support"
        payment_invoice.save()

        mock_assoc = Mock()

        with patch("larpmanager.accounting.payment.Association.objects.get") as mock_get_assoc:
            mock_get_assoc.return_value = mock_assoc

            with patch("larpmanager.accounting.payment.get_assoc_features") as mock_features:
                mock_features.return_value = ["badge"]

                with patch("larpmanager.accounting.payment.assign_badge") as mock_assign_badge:
                    # Call payment processing
                    result = payment_received(payment_invoice)

                    # Verify donation accounting item was created
                    from larpmanager.models.accounting import AccountingItemDonation

                    donation_items = AccountingItemDonation.objects.filter(inv=payment_invoice)
                    assert donation_items.count() == 1, f"Expected 1 donation item, got {donation_items.count()}"

                    donation_item = donation_items.first()
                    assert donation_item.member == payment_invoice.member, "Donation item should have correct member"
                    assert donation_item.value == payment_invoice.mc_gross, (
                        f"Donation value should be {payment_invoice.mc_gross}"
                    )
                    assert donation_item.descr == payment_invoice.causal, "Donation description should match causal"

                    # Verify badge assignment
                    mock_assign_badge.assert_called_once_with(payment_invoice.member, "donor")


@pytest.mark.django_db
class TestCriticalTokenCreditOperations:
    """Test critical token and credit operations"""

    def test_registration_tokens_credits_use_complete_workflow(self, registration):
        """Test complete token/credit usage workflow"""
        from larpmanager.accounting.token_credit import registration_tokens_credits_use

        # Setup member with tokens and credits
        membership = Membership.objects.create(
            member=registration.member,
            assoc=registration.run.event.assoc,
            tokens=Decimal("15"),
            credit=Decimal("25"),
            status=MembershipStatus.ACCEPTED,
        )

        remaining_balance = Decimal("30.00")  # Will use 15 tokens + 15 credits
        assoc_id = registration.run.event.assoc_id

        initial_token_balance = membership.tokens
        initial_credit_balance = membership.credit
        initial_reg_payed = registration.tot_payed

        with transaction.atomic():
            # Call the critical function
            registration_tokens_credits_use(registration, remaining_balance, assoc_id)

        # Verify token usage
        membership.refresh_from_db()
        assert membership.tokens == Decimal("0"), f"All tokens should be used, remaining: {membership.tokens}"

        # Verify credit usage (15 out of 25)
        expected_remaining_credits = initial_credit_balance - Decimal("15")  # 10
        assert membership.credit == expected_remaining_credits, (
            f"Expected credit balance {expected_remaining_credits}, got {membership.credit}"
        )

        # Verify payment items were created
        token_payments = AccountingItemPayment.objects.filter(reg=registration, pay=PaymentChoices.TOKEN)
        assert token_payments.count() == 1, f"Expected 1 token payment, got {token_payments.count()}"
        assert token_payments.first().value == Decimal("15"), (
            f"Token payment should be 15, got {token_payments.first().value}"
        )

        credit_payments = AccountingItemPayment.objects.filter(reg=registration, pay=PaymentChoices.CREDIT)
        assert credit_payments.count() == 1, f"Expected 1 credit payment, got {credit_payments.count()}"
        assert credit_payments.first().value == Decimal("15"), (
            f"Credit payment should be 15, got {credit_payments.first().value}"
        )

        # Verify registration payment total was updated
        registration.refresh_from_db()
        expected_new_payed = initial_reg_payed + Decimal("30")  # 15 tokens + 15 credits
        assert registration.tot_payed == expected_new_payed, (
            f"Registration payed should be {expected_new_payed}, got {registration.tot_payed}"
        )

    def test_registration_tokens_credits_overpay_reversal(self, registration):
        """Test overpayment reversal with tokens and credits"""
        from larpmanager.accounting.token_credit import registration_tokens_credits_overpay

        # Create existing token and credit payments
        token_payment = AccountingItemPayment.objects.create(
            member=registration.member,
            reg=registration,
            pay=PaymentChoices.TOKEN,
            value=Decimal("20"),
            assoc=registration.run.event.assoc,
        )

        credit_payment = AccountingItemPayment.objects.create(
            member=registration.member,
            reg=registration,
            pay=PaymentChoices.CREDIT,
            value=Decimal("30"),
            assoc=registration.run.event.assoc,
        )

        overpay_amount = Decimal("35.00")  # Will reverse all credit (30) + 5 from tokens
        assoc_id = registration.run.event.assoc_id

        # Call overpayment reversal
        registration_tokens_credits_overpay(registration, overpay_amount, assoc_id)

        # Verify credit payment was completely removed
        remaining_credit_payments = AccountingItemPayment.objects.filter(id=credit_payment.id)
        assert remaining_credit_payments.count() == 0, "Credit payment should be completely removed"

        # Verify token payment was reduced
        token_payment.refresh_from_db()
        expected_token_remaining = Decimal("20") - Decimal("5")  # 15
        assert token_payment.value == expected_token_remaining, (
            f"Token payment should be reduced to {expected_token_remaining}, got {token_payment.value}"
        )

        # Verify total reversal amount
        remaining_payments = AccountingItemPayment.objects.filter(
            reg=registration, pay__in=[PaymentChoices.TOKEN, PaymentChoices.CREDIT]
        )
        total_remaining = sum(p.value for p in remaining_payments)
        original_total = Decimal("50")  # 20 + 30
        expected_remaining = original_total - overpay_amount  # 15
        assert total_remaining == expected_remaining, (
            f"Expected total remaining {expected_remaining}, got {total_remaining}"
        )

    def test_update_token_credit_balance_recalculation(self, member, association):
        """Test token/credit balance recalculation"""
        from larpmanager.accounting.token_credit import update_token_credit

        # Create membership
        membership = Membership.objects.create(
            member=self.get_member(),
            assoc=self.get_association(),
            tokens=Decimal("0"),
            credit=Decimal("0"),
            status=MembershipStatus.ACCEPTED,
        )

        # Create accounting items that should affect balances
        # Token items
        token_given = AccountingItemOther.objects.create(
            member=member, oth=OtherChoices.TOKEN, value=Decimal("25"), assoc=association
        )

        # Credit items (expenses and direct credits)
        expense_approved = AccountingItemExpense.objects.create(
            member=member, value=Decimal("40"), is_approved=True, assoc=association
        )

        credit_given = AccountingItemOther.objects.create(
            member=member, oth=OtherChoices.CREDIT, value=Decimal("15"), assoc=association
        )

        # Refund (reduces credit)
        refund = AccountingItemOther.objects.create(
            member=member, oth=OtherChoices.REFUND, value=Decimal("10"), assoc=association
        )

        with patch("larpmanager.accounting.token_credit.get_assoc_features") as mock_features:
            mock_features.return_value = ["token_credit"]

            # Test token balance update
            update_token_credit(token_given, token=True)

            membership.refresh_from_db()
            assert membership.tokens == Decimal("25"), f"Token balance should be 25, got {membership.tokens}"

            # Test credit balance update
            update_token_credit(expense_approved, token=False)

            membership.refresh_from_db()
            # Credit = expenses(40) + given(15) - used(0) - refunded(10) = 45
            expected_credit = Decimal("45")
            assert membership.credit == expected_credit, (
                f"Credit balance should be {expected_credit}, got {membership.credit}"
            )


@pytest.mark.django_db
class TestCriticalValidationAndBusinessRules:
    """Test critical validation and business rule functions"""

    def test_registration_fee_calculation_with_all_components(self, registration, event):
        """Test complete registration fee calculation"""
        from larpmanager.accounting.registration import get_reg_iscr

        # Setup complex pricing scenario
        ticket = RegistrationTicket.objects.create(
            event=self.get_event(),
            tier=TicketTier.STANDARD,
            name="Standard Ticket",
            price=Decimal("100.00"),
            available=50,
        )

        registration.ticket = ticket
        registration.additionals = 2  # 2 additional tickets
        registration.pay_what = Decimal("25.00")
        registration.redeem_code = None  # Not gifted, can have discounts
        registration.surcharge = Decimal("15.00")

        # Create question with paid options
        question = RegistrationQuestion.objects.create(
            event=event, name="meals", text="Select meals", typ=BaseQuestionType.MULTIPLE, order=1
        )

        option1 = RegistrationOption.objects.create(
            question=question, name="Breakfast", price=Decimal("20.00"), order=1
        )

        option2 = RegistrationOption.objects.create(question=question, name="Dinner", price=Decimal("35.00"), order=2)

        # Create choices
        RegistrationChoice.objects.create(reg=registration, question=question, option=option1)

        RegistrationChoice.objects.create(reg=registration, question=question, option=option2)

        # Create discount
        discount = AccountingItemDiscount.objects.create(
            member=registration.member, run=registration.run, value=Decimal("30.00"), assoc=registration.run.event.assoc
        )

        # Calculate expected total
        # Base ticket: 100.00
        # Additional tickets: 100.00 * 2 = 200.00
        # Pay what: 25.00
        # Options: 20.00 + 35.00 = 55.00
        # Subtotal: 380.00
        # Discount: -30.00
        # Surcharge: +15.00
        # Total: 365.00

        calculated_total = get_reg_iscr(registration)
        expected_total = Decimal("365.00")

        assert calculated_total == expected_total, f"Expected total {expected_total}, got {calculated_total}"

        # Verify individual components
        base_ticket_cost = ticket.price * (1 + registration.additionals)  # 300.00
        options_cost = option1.price + option2.price  # 55.00

        assert base_ticket_cost == Decimal("300.00"), f"Base ticket cost should be 300.00, got {base_ticket_cost}"
        assert options_cost == Decimal("55.00"), f"Options cost should be 55.00, got {options_cost}"

    def test_registration_fee_calculation_with_gift_code(self, registration, event):
        """Test registration fee calculation with gift code (no discounts)"""
        from larpmanager.accounting.registration import get_reg_iscr

        ticket = RegistrationTicket.objects.create(
            event=self.get_event(),
            tier=TicketTier.STANDARD,
            name="Standard Ticket",
            price=Decimal("100.00"),
            available=50,
        )

        registration.ticket = ticket
        registration.redeem_code = "GIFT123"  # Gifted registration
        registration.surcharge = Decimal("0.00")

        # Create discount (should not apply to gifted registration)
        discount = AccountingItemDiscount.objects.create(
            member=registration.member, run=registration.run, value=Decimal("20.00"), assoc=registration.run.event.assoc
        )

        calculated_total = get_reg_iscr(registration)
        expected_total = ticket.price  # 100.00 (no discount applied)

        assert calculated_total == expected_total, (
            f"Gifted registration should not have discounts applied: expected {expected_total}, got {calculated_total}"
        )

    def test_payment_deadline_calculation_complex(self, registration):
        """Test payment deadline calculation with membership date"""
        from larpmanager.accounting.registration import get_payment_deadline

        # Create membership with recent date
        membership_date = date.today() - timedelta(days=5)
        membership = Membership.objects.create(
            member=registration.member,
            assoc=registration.run.event.assoc,
            date=membership_date,
            status=MembershipStatus.ACCEPTED,
        )

        # Registration created 10 days ago
        registration.created = Mock()
        registration.created.date.return_value = date.today() - timedelta(days=10)

        days_to_add = 7
        assoc_id = registration.run.event.assoc_id

        # Call deadline calculation
        calculated_deadline = get_payment_deadline(registration, days_to_add, assoc_id)

        # Should use the later of registration date or membership date
        # Membership date is more recent (-5 days), so use that
        # Deadline = max(-10, -5) + 7 = -5 + 7 = 2 days from today
        expected_deadline = 2

        assert calculated_deadline == expected_deadline, (
            f"Expected deadline {expected_deadline} days, got {calculated_deadline}"
        )

    def test_installment_deadline_calculation(self, registration, event):
        """Test installment deadline calculation"""
        from larpmanager.accounting.registration import installment_check

        ticket = RegistrationTicket.objects.create(
            event=self.get_event(),
            tier=TicketTier.STANDARD,
            name="Standard Ticket",
            price=Decimal("200.00"),
            available=50,
        )

        registration.ticket = ticket
        registration.tot_iscr = Decimal("200.00")
        registration.tot_payed = Decimal("0.00")

        # Create installment schedule
        installment1 = RegistrationInstallment.objects.create(
            event=event, order=1, amount=Decimal("80.00"), days_deadline=5, description="First installment"
        )

        installment2 = RegistrationInstallment.objects.create(
            event=event, order=2, amount=Decimal("120.00"), days_deadline=2, description="Second installment"
        )

        alert_threshold = 7  # Days
        assoc_id = registration.run.event.assoc_id

        with patch("larpmanager.accounting.registration.get_payment_deadline") as mock_deadline:
            mock_deadline.side_effect = [10, 3]  # First installment 10 days, second 3 days

            # Call installment check
            installment_check(registration, alert_threshold, assoc_id)

            # Should select second installment (deadline 3 < alert 7)
            assert hasattr(registration, "quota"), "Should set quota based on installment"
            assert hasattr(registration, "deadline"), "Should set deadline based on installment"

            # Quota should be cumulative amount minus paid
            expected_quota = Decimal("200.00")  # Full amount since second installment covers everything
            assert registration.quota == expected_quota, f"Expected quota {expected_quota}, got {registration.quota}"


# Fixtures
@pytest.fixture
def association():
    return Association.objects.create(name="Test Association", slug="test-assoc", email="test@example.com")


@pytest.fixture
def member():
    user = User.objects.create_user(username="testuser", email="test@example.com", first_name="Test", last_name="User")
    return Member.objects.create(user=user, name="Test", surname="User", email="test@example.com")


@pytest.fixture
def event(association):
    return Event.objects.create(name="Test Event", assoc=association, number=1)


@pytest.fixture
def run(event):
    return Run.objects.create(
        event=event,
        number=1,
        name="Test Run",
        start=date.today() + timedelta(days=30),
        end=date.today() + timedelta(days=32),
    )


@pytest.fixture
def registration(member, run):
    return Registration.objects.create(
        member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"), quotas=1
    )


@pytest.fixture
def payment_invoice(member, association):
    from larpmanager.models.base import PaymentMethod

    method = PaymentMethod.objects.create(name="Test Method", slug="test", fields="")

    return PaymentInvoice.objects.create(
        member=member,
        assoc=association,
        method=method,
        typ=PaymentType.REGISTRATION,
        status=PaymentStatus.CREATED,
        mc_gross=Decimal("100.00"),
        mc_fee=Decimal("5.00"),
        causal="Test payment",
        cod="TEST123",
    )
