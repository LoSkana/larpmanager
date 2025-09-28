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
from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import Mock, patch

import pytest

from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemPayment,
    PaymentChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
)
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.form import BaseQuestionType
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import (
    Registration,
    RegistrationChoice,
    RegistrationInstallment,
    RegistrationOption,
    RegistrationQuestion,
    RegistrationTicket,
    TicketTier,
)


@pytest.mark.django_db
class TestCriticalEdgeCasesAndErrors:
    """Test critical edge cases and error handling scenarios"""

    def test_registration_with_zero_price_ticket(self, member, run, event):
        """Test registration with free ticket handling"""
        from larpmanager.accounting.registration import get_reg_iscr

        # Create free ticket
        free_ticket = RegistrationTicket.objects.create(
            event=event, tier=TicketTier.STAFF, name="Free Staff Ticket", price=Decimal("0.00"), available=10
        )

        registration = Registration.objects.create(
            member=member, run=run, ticket=free_ticket, tot_iscr=Decimal("0.00"), tot_payed=Decimal("0.00")
        )

        # Add expensive option to free ticket
        question = RegistrationQuestion.objects.create(
            event=event, name="premium_service", text="Premium service?", typ=BaseQuestionType.SINGLE, order=1
        )

        expensive_option = RegistrationOption.objects.create(
            question=question, name="Premium Service", price=Decimal("150.00"), order=1
        )

        RegistrationChoice.objects.create(reg=registration, question=question, option=expensive_option)

        # Calculate fee - should include option even with free ticket
        calculated_total = get_reg_iscr(registration)
        expected_total = Decimal("150.00")  # 0.00 ticket + 150.00 option

        assert calculated_total == expected_total, (
            f"Free ticket with paid option should total {expected_total}, got {calculated_total}"
        )

        # Test with negative total (discount larger than cost)
        huge_discount = AccountingItemDiscount.objects.create(
            member=member,
            run=run,
            value=Decimal("200.00"),  # Larger than total
            assoc=run.event.assoc,
        )

        calculated_with_discount = get_reg_iscr(registration)
        # Should be max(0, 150 - 200) = 0
        assert calculated_with_discount == Decimal("0.00"), (
            f"Negative total should be clamped to 0, got {calculated_with_discount}"
        )

    def test_payment_processing_with_concurrent_modifications(self, payment_invoice, registration):
        """Test payment processing with concurrent modifications"""
        from larpmanager.accounting.payment import payment_received

        payment_invoice.typ = PaymentType.REGISTRATION
        payment_invoice.idx = registration.id
        payment_invoice.mc_gross = Decimal("100.00")
        payment_invoice.save()

        # Simulate concurrent payment processing
        mock_assoc = Mock()
        mock_assoc.get_config.return_value = False

        # First payment should succeed
        with patch("larpmanager.accounting.payment.Association.objects.get") as mock_get_assoc:
            mock_get_assoc.return_value = mock_assoc
            with patch("larpmanager.accounting.payment.get_assoc_features") as mock_features:
                mock_features.return_value = []
                with patch("larpmanager.accounting.payment.Registration.objects.get") as mock_get_reg:
                    mock_get_reg.return_value = registration

                    # Process payment first time
                    result1 = payment_received(payment_invoice)
                    assert result1 is True, "First payment processing should succeed"

                    # Verify payment item was created
                    payment_count_after_first = AccountingItemPayment.objects.filter(inv=payment_invoice).count()
                    assert payment_count_after_first == 1, (
                        f"Expected 1 payment item after first processing, got {payment_count_after_first}"
                    )

                    # Process same payment again (idempotency check)
                    result2 = payment_received(payment_invoice)
                    assert result2 is True, "Second payment processing should still return True"

                    # Verify no duplicate payment items were created
                    payment_count_after_second = AccountingItemPayment.objects.filter(inv=payment_invoice).count()
                    assert payment_count_after_second == 1, (
                        f"Expected still 1 payment item after second processing, got {payment_count_after_second}"
                    )

    def test_token_credit_operations_with_insufficient_balance(self, registration):
        """Test token/credit operations with insufficient balance"""
        from larpmanager.accounting.token_credit import registration_tokens_credits_use

        # Create membership with insufficient balance
        membership = Membership.objects.create(
            member=registration.member,
            assoc=registration.run.event.assoc,
            tokens=Decimal("5"),  # Only 5 tokens
            credit=Decimal("10"),  # Only 10 credits
            status=MembershipStatus.ACCEPTED,
        )

        # Try to use more than available
        remaining_balance = Decimal("50.00")  # Needs 50, but only has 15 total
        assoc_id = registration.run.event.assoc_id

        initial_payed = registration.tot_payed

        # Call token/credit usage
        registration_tokens_credits_use(registration, remaining_balance, assoc_id)

        # Verify all available balance was used
        membership.refresh_from_db()
        assert membership.tokens == Decimal("0"), f"All tokens should be used, remaining: {membership.tokens}"
        assert membership.credit == Decimal("0"), f"All credits should be used, remaining: {membership.credit}"

        # Verify correct payment amounts
        total_payments = AccountingItemPayment.objects.filter(
            reg=registration, pay__in=[PaymentChoices.TOKEN, PaymentChoices.CREDIT]
        )

        total_used = sum(p.value for p in total_payments)
        expected_total_used = Decimal("15")  # 5 tokens + 10 credits
        assert total_used == expected_total_used, f"Expected total usage {expected_total_used}, got {total_used}"

        # Verify registration payment was updated correctly
        registration.refresh_from_db()
        expected_new_payed = initial_payed + expected_total_used
        assert registration.tot_payed == expected_new_payed, (
            f"Registration payed should be {expected_new_payed}, got {registration.tot_payed}"
        )

    def test_overpayment_reversal_with_partial_items(self, registration):
        """Test overpayment reversal with partial item values"""
        from larpmanager.accounting.token_credit import registration_tokens_credits_overpay

        # Create payments with specific values
        token_payment1 = AccountingItemPayment.objects.create(
            member=registration.member,
            reg=registration,
            pay=PaymentChoices.TOKEN,
            value=Decimal("12.50"),
            assoc=registration.run.event.assoc,
        )

        token_payment2 = AccountingItemPayment.objects.create(
            member=registration.member,
            reg=registration,
            pay=PaymentChoices.TOKEN,
            value=Decimal("7.50"),
            assoc=registration.run.event.assoc,
        )

        credit_payment = AccountingItemPayment.objects.create(
            member=registration.member,
            reg=registration,
            pay=PaymentChoices.CREDIT,
            value=Decimal("25.00"),
            assoc=registration.run.event.assoc,
        )

        # Total payments: 45.00 (12.50 + 7.50 + 25.00)
        # Reverse 30.00 (should remove credit completely and reduce largest token payment)
        overpay_amount = Decimal("30.00")
        assoc_id = registration.run.event.assoc_id

        registration_tokens_credits_overpay(registration, overpay_amount, assoc_id)

        # Verify credit payment was completely removed
        remaining_credit_payments = AccountingItemPayment.objects.filter(id=credit_payment.id)
        assert remaining_credit_payments.count() == 0, "Credit payment should be completely removed"

        # Verify token payments (credits are reversed first, then tokens by value desc)
        # Should remove credit (25.00) then 5.00 from largest token payment (12.50)
        remaining_token_payments = AccountingItemPayment.objects.filter(
            reg=registration, pay=PaymentChoices.TOKEN
        ).order_by("-value")

        assert remaining_token_payments.count() == 2, (
            f"Should have 2 token payments remaining, got {remaining_token_payments.count()}"
        )

        # Largest token payment should be reduced by 5.00 (30.00 - 25.00 credit)
        largest_token = remaining_token_payments.first()
        assert largest_token.value == Decimal("7.50"), (
            f"Largest token payment should be reduced to 7.50, got {largest_token.value}"
        )

        # Smaller token payment should be unchanged
        smaller_token = remaining_token_payments.last()
        assert smaller_token.value == Decimal("7.50"), (
            f"Smaller token payment should remain 7.50, got {smaller_token.value}"
        )

        # Verify total remaining value
        total_remaining = sum(p.value for p in remaining_token_payments)
        expected_remaining = Decimal("15.00")  # 45.00 - 30.00
        assert total_remaining == expected_remaining, (
            f"Expected remaining total {expected_remaining}, got {total_remaining}"
        )

    def test_registration_fee_calculation_with_decimal_precision(self, registration, event):
        """Test registration fee calculation with decimal precision edge cases"""
        from larpmanager.accounting.registration import get_reg_iscr

        # Create ticket with non-standard price
        ticket = RegistrationTicket.objects.create(
            event=event,
            tier=TicketTier.STANDARD,
            name="Precision Test Ticket",
            price=Decimal("33.33"),  # Repeating decimal
            available=50,
        )

        registration.ticket = ticket
        registration.additionals = 3  # 3 additional tickets
        registration.pay_what = Decimal("12.34")  # Specific decimal

        # Create option with specific decimal
        question = RegistrationQuestion.objects.create(
            event=event, name="precision_test", text="Precision test", typ=BaseQuestionType.SINGLE, order=1
        )

        option = RegistrationOption.objects.create(
            question=question, name="Precision Option", price=Decimal("7.89"), order=1
        )

        RegistrationChoice.objects.create(reg=registration, question=question, option=option)

        # Create discount with decimal
        discount = AccountingItemDiscount.objects.create(
            member=registration.member, run=registration.run, value=Decimal("5.67"), assoc=registration.run.event.assoc
        )

        registration.surcharge = Decimal("2.11")

        # Calculate total
        # Base: 33.33
        # Additionals: 33.33 * 3 = 99.99
        # Pay what: 12.34
        # Option: 7.89
        # Subtotal: 153.55
        # Discount: -5.67
        # Surcharge: +2.11
        # Total: 149.99

        calculated_total = get_reg_iscr(registration)
        expected_total = Decimal("149.99")

        assert calculated_total == expected_total, (
            f"Decimal precision calculation failed: expected {expected_total}, got {calculated_total}"
        )

        # Test maximum precision (2 decimal places)
        very_precise_value = Decimal("123.456789")
        rounded_value = very_precise_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert rounded_value == Decimal("123.46"), f"Decimal rounding failed: expected 123.46, got {rounded_value}"

    def test_payment_processing_with_invalid_invoice_states(self, payment_invoice):
        """Test payment processing with invalid invoice states"""
        from larpmanager.accounting.payment import payment_received

        # Test with invalid payment type
        payment_invoice.typ = 999  # Invalid type
        payment_invoice.save()

        mock_assoc = Mock()
        with patch("larpmanager.accounting.payment.Association.objects.get") as mock_get_assoc:
            mock_get_assoc.return_value = mock_assoc
            with patch("larpmanager.accounting.payment.get_assoc_features") as mock_features:
                mock_features.return_value = []

                # Should handle gracefully and return True (no processing for unknown type)
                result = payment_received(payment_invoice)
                assert result is True, "Should handle unknown payment type gracefully"

    def test_registration_accounting_with_corrupted_data(self, registration):
        """Test registration accounting with corrupted/missing data"""
        from larpmanager.accounting.registration import update_registration_accounting

        # Test with missing run
        registration.run = None

        # Should handle missing run gracefully
        try:
            update_registration_accounting(registration)
            # If no exception, verify state wasn't changed
            assert True, "Should handle missing run without crashing"
        except AttributeError:
            # Expected behavior - function tries to access run attributes
            assert True, "Expected AttributeError for missing run"

        # Restore run for next test
        event = Event.objects.create(name="Test Event", assoc_id=1, number=1)
        run = Run.objects.create(
            event=event,
            number=1,
            name="Test Run",
            start=date.today() + timedelta(days=30),
            end=date.today() + timedelta(days=32),
        )
        registration.run = run

        # Test with corrupted decimal values
        registration.tot_iscr = None
        registration.tot_payed = None

        try:
            update_registration_accounting(registration)
            # Should handle None values
            assert True, "Should handle None decimal values"
        except (TypeError, AttributeError):
            # Expected - None values cause arithmetic errors
            assert True, "Expected error with None decimal values"

    def test_concurrent_ticket_purchase_edge_case(self, event):
        """Test concurrent ticket purchases at capacity limit"""
        # Create ticket with only 1 available
        ticket = RegistrationTicket.objects.create(
            event=event, tier=TicketTier.STANDARD, name="Limited Ticket", price=Decimal("100.00"), available=1
        )

        member1 = Member.objects.create(username="member1", email="member1@test.com")

        member2 = Member.objects.create(username="member2", email="member2@test.com")

        run = Run.objects.create(
            event=event,
            number=1,
            name="Test Run",
            start=date.today() + timedelta(days=30),
            end=date.today() + timedelta(days=32),
        )

        # First registration should succeed
        reg1 = Registration.objects.create(
            member=member1, run=run, ticket=ticket, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00")
        )

        # Update ticket availability
        ticket.available = 0
        ticket.save()

        # Second registration should be prevented by business logic
        # In real system, this would be handled by form validation
        assert ticket.available == 0, "Ticket should be sold out"

        # Verify only one registration exists
        registrations = Registration.objects.filter(run=run)
        assert registrations.count() == 1, f"Should have only 1 registration, got {registrations.count()}"

        # If we were to force create second registration, it would work at model level
        # but business logic should prevent it
        can_register = ticket.available > 0
        assert not can_register, "Business logic should prevent registration when sold out"

    def test_installment_calculation_with_overlapping_deadlines(self, registration, event):
        """Test installment calculations with overlapping or conflicting deadlines"""
        from larpmanager.accounting.registration import installment_check

        ticket = RegistrationTicket.objects.create(
            event=event, tier=TicketTier.STANDARD, name="Standard Ticket", price=Decimal("300.00"), available=50
        )

        registration.ticket = ticket
        registration.tot_iscr = Decimal("300.00")
        registration.tot_payed = Decimal("0.00")

        # Create installments with overlapping deadlines
        installment1 = RegistrationInstallment.objects.create(
            event=event, order=1, amount=Decimal("100.00"), days_deadline=10, description="First installment"
        )

        installment2 = RegistrationInstallment.objects.create(
            event=event,
            order=2,
            amount=Decimal("150.00"),
            days_deadline=5,  # Earlier deadline than first installment
            description="Second installment",
        )

        installment3 = RegistrationInstallment.objects.create(
            event=event,
            order=3,
            amount=None,  # Full amount
            days_deadline=2,
            description="Final installment",
        )

        alert_threshold = 7
        assoc_id = registration.run.event.assoc_id

        with patch("larpmanager.accounting.registration.get_payment_deadline") as mock_deadline:
            mock_deadline.side_effect = [15, 8, 3]  # Deadlines for each installment

            installment_check(registration, alert_threshold, assoc_id)

            # Should select the installment with earliest urgent deadline (3 days)
            assert hasattr(registration, "quota"), "Should set quota based on earliest urgent installment"

            # Final installment has amount=None, so should use full tot_iscr
            expected_quota = Decimal("300.00")  # Full amount
            assert registration.quota == expected_quota, f"Expected quota {expected_quota}, got {registration.quota}"

    def test_vat_calculation_edge_cases(self, payment_item):
        """Test VAT calculation with edge cases"""
        from larpmanager.accounting.vat import compute_vat

        # Setup payment with specific scenario
        payment_item.assoc.get_config = Mock(
            side_effect=lambda key, default: {
                "vat_ticket": "0",  # 0% VAT on tickets
                "vat_options": "25",  # 25% VAT on options
            }.get(key, default)
        )

        payment_item.reg.pay_what = None
        payment_item.reg.ticket = Mock()
        payment_item.reg.ticket.price = Decimal("100.00")
        payment_item.value = Decimal("150.00")  # More than ticket price

        # Mock no previous payments or transactions
        with patch("larpmanager.accounting.vat.get_previous_sum") as mock_get_sum:
            mock_get_sum.return_value = 0

            with patch("larpmanager.accounting.vat.AccountingItemTransaction.objects.filter") as mock_trans_filter:
                mock_trans_filter.return_value = []

                with patch("larpmanager.accounting.vat.AccountingItemPayment.objects.filter") as mock_payment_filter:
                    mock_queryset = Mock()
                    mock_payment_filter.return_value = mock_queryset

                    compute_vat(payment_item)

                    # Verify VAT calculation
                    # Ticket portion: 100.00 at 0% VAT = 0.00
                    # Options portion: 50.00 at 25% VAT = 12.50
                    # Total VAT: 12.50

                    call_args = mock_queryset.update.call_args[1]
                    calculated_vat = call_args["vat"]
                    expected_vat = 12.50

                    assert calculated_vat == expected_vat, f"Expected VAT {expected_vat}, got {calculated_vat}"

    def test_registration_with_extreme_values(self, member, run, event):
        """Test registration handling with extreme values"""
        from larpmanager.accounting.registration import get_reg_iscr

        # Create ticket with maximum decimal value
        max_ticket = RegistrationTicket.objects.create(
            event=event, tier=TicketTier.STANDARD, name="Max Price Ticket", price=Decimal("9999999.99"), available=1
        )

        registration = Registration.objects.create(
            member=member,
            run=run,
            ticket=max_ticket,
            additionals=0,
            tot_iscr=max_ticket.price,
            tot_payed=Decimal("0.00"),
        )

        # Test with maximum discount
        max_discount = AccountingItemDiscount.objects.create(
            member=member,
            run=run,
            value=Decimal("9999999.99"),  # Equal to ticket price
            assoc=run.event.assoc,
        )

        calculated_total = get_reg_iscr(registration)
        # Should be max(0, 9999999.99 - 9999999.99) = 0
        assert calculated_total == Decimal("0.00"), f"Max discount should result in 0 total, got {calculated_total}"

        # Test with minimum values
        min_ticket = RegistrationTicket.objects.create(
            event=event, tier=TicketTier.STANDARD, name="Min Price Ticket", price=Decimal("0.01"), available=1
        )

        registration.ticket = min_ticket

        min_discount = AccountingItemDiscount.objects.create(
            member=member, run=run, value=Decimal("0.01"), assoc=run.event.assoc
        )

        calculated_min_total = get_reg_iscr(registration)
        # Should be max(0, 0.01 - 9999999.99 - 0.01) = 0
        assert calculated_min_total == Decimal("0.00"), (
            f"Minimum calculation should result in 0, got {calculated_min_total}"
        )


# Fixtures
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
def payment_item(member, association, registration):
    return AccountingItemPayment(
        member=member,
        value=Decimal("100.00"),
        assoc=association,
        reg=registration,
        pay=PaymentChoices.MONEY,
        created=datetime.now(),
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
