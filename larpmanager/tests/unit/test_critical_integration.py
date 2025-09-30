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

from larpmanager.models.accounting import (
    AccountingItemDiscount,
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
from larpmanager.models.base import PaymentMethod
from larpmanager.models.event import DevelopStatus, Event, Run
from larpmanager.models.form import (
    BaseQuestionType,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
)
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import (
    Registration,
    RegistrationInstallment,
    RegistrationSurcharge,
    RegistrationTicket,
    TicketTier,
)


@pytest.mark.django_db
class TestCompleteRegistrationToPaymentWorkflow:
    """Test complete workflow from registration to payment completion"""

    def test_full_registration_and_payment_workflow(self, association, member):
        """Test complete registration, accounting, and payment workflow"""
        from larpmanager.accounting.payment import payment_received
        from larpmanager.accounting.registration import update_registration_accounting

        # Step 1: Create event and run
        event = Event.objects.create(name="Complete Workflow Test Event", assoc=association, number=1)

        run = Run.objects.create(
            event=event,
            number=1,
            name="Complete Test Run",
            start=date.today() + timedelta(days=60),
            end=date.today() + timedelta(days=62),
            development=DevelopStatus.OPEN,
        )

        # Step 2: Create complex ticket pricing
        standard_ticket = RegistrationTicket.objects.create(
            event=event, tier=TicketTier.STANDARD, name="Standard Ticket", price=Decimal("120.00"), available=50
        )

        # Step 3: Create registration questions with options
        accommodation_question = RegistrationQuestion.objects.create(
            event=event,
            name="accommodation",
            text="Select accommodation",
            typ=BaseQuestionType.SINGLE,
            required=True,
            order=1,
        )

        hotel_option = RegistrationOption.objects.create(
            question=accommodation_question, name="Hotel Room", price=Decimal("80.00"), order=1
        )

        meals_question = RegistrationQuestion.objects.create(
            event=event, name="meals", text="Select meals", typ=BaseQuestionType.MULTIPLE, required=False, order=2
        )

        breakfast_option = RegistrationOption.objects.create(
            question=meals_question, name="Breakfast", price=Decimal("15.00"), order=1
        )

        dinner_option = RegistrationOption.objects.create(
            question=meals_question, name="Dinner", price=Decimal("25.00"), order=2
        )

        # Step 4: Create surcharge for late registration
        surcharge = RegistrationSurcharge.objects.create(
            event=event,
            date=date.today() - timedelta(days=30),  # Already applies
            amount=Decimal("20.00"),
            description="Late registration fee",
        )

        # Step 5: Create membership for member
        membership = Membership.objects.create(
            member=member,
            assoc=association,
            status=MembershipStatus.ACCEPTED,
            date=date.today(),
            tokens=Decimal("30"),
            credit=Decimal("50"),
        )

        # Step 6: Create registration
        registration = Registration.objects.create(
            member=member,
            run=run,
            ticket=standard_ticket,
            additionals=1,  # One additional ticket
            pay_what=Decimal("10.00"),  # Extra contribution
            tot_iscr=Decimal("0.00"),  # Will be calculated
            tot_payed=Decimal("0.00"),
            quotas=1,
        )

        # Step 7: Add registration choices
        RegistrationChoice.objects.create(reg=registration, question=accommodation_question, option=hotel_option)

        RegistrationChoice.objects.create(reg=registration, question=meals_question, option=breakfast_option)

        RegistrationChoice.objects.create(reg=registration, question=meals_question, option=dinner_option)

        # Step 8: Create discount
        discount = AccountingItemDiscount.objects.create(
            member=member, run=run, value=Decimal("25.00"), assoc=association
        )

        # Step 9: Update registration accounting
        with patch("larpmanager.accounting.registration.get_event_features") as mock_features:
            mock_features.return_value = ["payment", "token_credit"]

            with patch("larpmanager.accounting.registration.handle_tokes_credits") as mock_handle_tc:
                update_registration_accounting(registration)

                # Verify accounting calculations
                # Expected calculation:
                # Base ticket: 120.00
                # Additional ticket: 120.00
                # Pay what: 10.00
                # Accommodation: 80.00
                # Meals: 15.00 + 25.00 = 40.00
                # Surcharge: 20.00
                # Subtotal: 390.00
                # Discount: -25.00
                # Total: 365.00

                expected_total = Decimal("365.00")
                assert registration.tot_iscr == expected_total, (
                    f"Expected registration total {expected_total}, got {registration.tot_iscr}"
                )

                # Verify token/credit handling was called
                mock_handle_tc.assert_called_once()
                call_args = mock_handle_tc.call_args[0]
                assert call_args[3] == expected_total, f"Token/credit handler should receive total {expected_total}"

        # Step 10: Simulate token/credit usage
        # Use 30 tokens and 50 credits = 80 total
        token_payment = AccountingItemPayment.objects.create(
            member=member, reg=registration, pay=PaymentChoices.TOKEN, value=Decimal("30"), assoc=association
        )

        credit_payment = AccountingItemPayment.objects.create(
            member=member, reg=registration, pay=PaymentChoices.CREDIT, value=Decimal("50"), assoc=association
        )

        # Update membership balances
        membership.tokens = Decimal("0")
        membership.credit = Decimal("0")
        membership.save()

        # Update registration payment total
        registration.tot_payed = Decimal("80.00")
        registration.save()

        # Step 11: Create payment invoice for remaining balance
        payment_method = PaymentMethod.objects.create(name="PayPal", slug="paypal", fields="paypal_id")

        remaining_balance = registration.tot_iscr - registration.tot_payed  # 285.00
        payment_invoice = PaymentInvoice.objects.create(
            member=member,
            assoc=association,
            method=payment_method,
            typ=PaymentType.REGISTRATION,
            idx=registration.id,
            status=PaymentStatus.CREATED,
            mc_gross=remaining_balance,
            mc_fee=Decimal("8.55"),  # 3% fee
            causal=f"Registration for {self.event().name}",
            cod="REG12345",
        )

        # Step 12: Process payment
        with patch("larpmanager.accounting.payment.Association.objects.get") as mock_get_assoc:
            mock_assoc = Mock()
            mock_assoc.get_config.side_effect = lambda key, default: {"payment_fees_user": True}.get(key, default)
            mock_get_assoc.return_value = mock_assoc

            with patch("larpmanager.accounting.payment.get_assoc_features") as mock_features:
                mock_features.return_value = ["e-invoice"]

                with patch("larpmanager.accounting.payment.get_payment_fee") as mock_get_fee:
                    mock_get_fee.return_value = 3.0

                    with patch("larpmanager.accounting.payment.Registration.objects.get") as mock_get_reg:
                        mock_get_reg.return_value = registration

                        with patch("larpmanager.accounting.payment.process_payment") as mock_einvoice:
                            # Process the payment
                            result = payment_received(payment_invoice)

                            assert result is True, "Payment processing should succeed"

        # Step 13: Verify final state
        # Check money payment was created
        money_payments = AccountingItemPayment.objects.filter(reg=registration, pay=PaymentChoices.MONEY)
        assert money_payments.count() == 1, f"Expected 1 money payment, got {money_payments.count()}"
        money_payment = money_payments.first()
        assert money_payment.value == remaining_balance, (
            f"Money payment should be {remaining_balance}, got {money_payment.value}"
        )

        # Check transaction fee was created
        transaction_fees = AccountingItemTransaction.objects.filter(reg=registration, user_burden=True)
        assert transaction_fees.count() == 1, f"Expected 1 transaction fee, got {transaction_fees.count()}"
        fee = transaction_fees.first()
        expected_fee = float(remaining_balance) * 3.0 / 100  # 8.55
        assert abs(fee.value - expected_fee) < 0.01, f"Expected fee ~{expected_fee}, got {fee.value}"

        # Verify total payments
        all_payments = AccountingItemPayment.objects.filter(reg=registration)
        total_payments = sum(p.value for p in all_payments)
        expected_total_payments = Decimal("365.00")  # tokens + credits + money
        assert total_payments == expected_total_payments, (
            f"Expected total payments {expected_total_payments}, got {total_payments}"
        )

        # Verify registration is fully paid (considering fee)
        total_fees = sum(t.value for t in transaction_fees)
        net_payment = total_payments - total_fees
        remaining_after_payment = registration.tot_iscr - net_payment

        # Should be very close to 0 (within fee tolerance)
        assert abs(remaining_after_payment) <= Decimal("0.10"), (
            f"Registration should be essentially paid, remaining: {remaining_after_payment}"
        )

    def test_waitlist_to_confirmed_promotion_workflow(self, association, member):
        """Test complete waitlist promotion workflow"""
        # Step 1: Create event with limited capacity
        event = Event.objects.create(name="Waitlist Test Event", assoc=association, number=1)

        run = Run.objects.create(
            event=event,
            number=1,
            name="Limited Run",
            start=date.today() + timedelta(days=30),
            end=date.today() + timedelta(days=32),
        )

        # Step 2: Create tickets
        standard_ticket = RegistrationTicket.objects.create(
            event=event,
            tier=TicketTier.STANDARD,
            name="Standard Ticket",
            price=Decimal("100.00"),
            available=1,  # Only 1 spot
        )

        waitlist_ticket = RegistrationTicket.objects.create(
            event=event, tier=TicketTier.WAITING, name="Waitlist", price=Decimal("0.00"), available=999
        )

        # Step 3: Create first member who gets the standard ticket
        first_user = User.objects.create_user(username="first_member", email="first@test.com")
        first_member = first_user.member
        first_member.name = "First"
        first_member.surname = "Member"
        first_member.save()

        first_registration = Registration.objects.create(
            member=first_member,
            run=run,
            ticket=standard_ticket,
            tot_iscr=Decimal("100.00"),
            tot_payed=Decimal("100.00"),  # Fully paid
        )

        # Update ticket availability
        standard_ticket.available = 0
        standard_ticket.save()

        # Step 4: Create second member on waitlist
        second_user = User.objects.create_user(username="second_member", email="second@test.com")
        second_member = second_user.member
        second_member.name = "Second"
        second_member.surname = "Member"
        second_member.save()

        waitlist_registration = Registration.objects.create(
            member=second_member, run=run, ticket=waitlist_ticket, tot_iscr=Decimal("0.00"), tot_payed=Decimal("0.00")
        )

        # Verify waitlist state
        assert waitlist_registration.ticket.tier == TicketTier.WAITING, "Should be on waitlist"
        assert waitlist_registration.tot_iscr == Decimal("0.00"), "Waitlist should have no cost"

        # Step 5: First member cancels
        first_registration.cancellation_date = datetime.now()
        first_registration.save()

        # Step 6: Promote waitlist member
        # Increase standard ticket availability
        standard_ticket.available = 1
        standard_ticket.save()

        # Move member from waitlist to standard
        waitlist_registration.ticket = standard_ticket
        waitlist_registration.tot_iscr = standard_ticket.price
        waitlist_registration.save()

        # Update ticket availability again
        standard_ticket.available = 0
        standard_ticket.save()

        # Step 7: Verify promotion
        waitlist_registration.refresh_from_db()
        assert waitlist_registration.ticket.tier == TicketTier.STANDARD, "Should be promoted to standard"
        assert waitlist_registration.tot_iscr == Decimal("100.00"), "Should have standard ticket price"

        # Verify only one active registration exists
        active_registrations = Registration.objects.filter(run=run, cancellation_date__isnull=True)
        assert active_registrations.count() == 1, (
            f"Should have 1 active registration, got {active_registrations.count()}"
        )
        assert active_registrations.first() == waitlist_registration, (
            "Waitlist member should be the active registration"
        )

    def test_installment_payment_workflow(self, association, member):
        """Test complete installment payment workflow"""
        from larpmanager.accounting.registration import update_registration_accounting

        # Step 1: Create event with installment plan
        event = Event.objects.create(name="Installment Test Event", assoc=association, number=1)

        run = Run.objects.create(
            event=event,
            number=1,
            name="Installment Run",
            start=date.today() + timedelta(days=90),
            end=date.today() + timedelta(days=92),
        )

        # Step 2: Create ticket
        ticket = RegistrationTicket.objects.create(
            event=self.event(), tier=TicketTier.STANDARD, name="Installment Ticket", price=Decimal("300.00"), available=50
        )

        # Step 3: Create installment schedule
        installment1 = RegistrationInstallment.objects.create(
            event=event, order=1, amount=Decimal("100.00"), days_deadline=60, description="First installment"
        )

        installment2 = RegistrationInstallment.objects.create(
            event=event, order=2, amount=Decimal("150.00"), days_deadline=30, description="Second installment"
        )

        installment3 = RegistrationInstallment.objects.create(
            event=event,
            order=3,
            amount=None,  # Remaining amount
            days_deadline=7,
            description="Final payment",
        )

        # Step 4: Create registration
        registration = Registration.objects.create(
            member=member, run=run, ticket=ticket, tot_iscr=Decimal("300.00"), tot_payed=Decimal("0.00"), quotas=1
        )

        # Step 5: Test first installment payment
        with patch("larpmanager.accounting.registration.get_event_features") as mock_features:
            mock_features.return_value = ["payment", "reg_installments"]

            with patch("larpmanager.accounting.registration.get_payment_deadline") as mock_deadline:
                mock_deadline.side_effect = [65, 35, 12]  # Days until each deadline

                # Update accounting - should set first installment quota
                update_registration_accounting(registration)

                # Should set quota for first installment
                assert hasattr(registration, "quota"), "Should set installment quota"
                expected_quota = Decimal("100.00")  # First installment
                assert registration.quota == expected_quota, (
                    f"Expected first installment quota {expected_quota}, got {registration.quota}"
                )

        # Step 6: Pay first installment
        payment1 = AccountingItemPayment.objects.create(
            member=member, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("100.00"), assoc=association
        )

        registration.tot_payed = Decimal("100.00")
        registration.save()

        # Step 7: Update accounting for second installment
        with patch("larpmanager.accounting.registration.get_event_features") as mock_features:
            mock_features.return_value = ["payment", "reg_installments"]

            with patch("larpmanager.accounting.registration.get_payment_deadline") as mock_deadline:
                mock_deadline.side_effect = [35, 5]  # Second deadline is urgent

                update_registration_accounting(registration)

                # Should set quota for second installment
                expected_quota = Decimal("150.00")  # 250 total - 100 paid = 150
                assert registration.quota == expected_quota, (
                    f"Expected second installment quota {expected_quota}, got {registration.quota}"
                )

        # Step 8: Pay second installment
        payment2 = AccountingItemPayment.objects.create(
            member=member, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("150.00"), assoc=association
        )

        registration.tot_payed = Decimal("250.00")
        registration.save()

        # Step 9: Final payment
        with patch("larpmanager.accounting.registration.get_event_features") as mock_features:
            mock_features.return_value = ["payment", "reg_installments"]

            with patch("larpmanager.accounting.registration.get_payment_deadline") as mock_deadline:
                mock_deadline.return_value = 2  # Final deadline urgent

                update_registration_accounting(registration)

                # Should set quota for remaining amount
                expected_quota = Decimal("50.00")  # 300 - 250 = 50
                assert registration.quota == expected_quota, (
                    f"Expected final quota {expected_quota}, got {registration.quota}"
                )

        # Step 10: Final payment
        payment3 = AccountingItemPayment.objects.create(
            member=member, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("50.00"), assoc=association
        )

        registration.tot_payed = Decimal("300.00")
        registration.save()

        # Step 11: Verify complete payment
        all_payments = AccountingItemPayment.objects.filter(reg=registration)
        assert all_payments.count() == 3, f"Expected 3 payments, got {all_payments.count()}"

        total_paid = sum(p.value for p in all_payments)
        assert total_paid == registration.tot_iscr, (
            f"Total paid {total_paid} should equal total cost {registration.tot_iscr}"
        )

        # Verify final accounting update
        with patch("larpmanager.accounting.registration.get_event_features") as mock_features:
            mock_features.return_value = ["payment", "reg_installments"]

            update_registration_accounting(registration)

            # Should set payment date for fully paid registration
            assert registration.payment_date is not None, "Payment date should be set for fully paid registration"

    def test_refund_and_cancellation_workflow(self, association, member):
        """Test complete refund and cancellation workflow"""
        from larpmanager.accounting.registration import cancel_reg

        # Step 1: Create event and registration
        event = Event.objects.create(name="Refund Test Event", assoc=association, number=1)

        run = Run.objects.create(
            event=event,
            number=1,
            name="Refund Test Run",
            start=date.today() + timedelta(days=30),
            end=date.today() + timedelta(days=32),
        )

        ticket = RegistrationTicket.objects.create(
            event=self.event(), tier=TicketTier.STANDARD, name="Refundable Ticket", price=Decimal("150.00"), available=50
        )

        registration = Registration.objects.create(
            member=member,
            run=run,
            ticket=ticket,
            tot_iscr=Decimal("150.00"),
            tot_payed=Decimal("150.00"),  # Fully paid
        )

        # Step 2: Create payment history
        money_payment = AccountingItemPayment.objects.create(
            member=member, reg=registration, pay=PaymentChoices.MONEY, value=Decimal("100.00"), assoc=association
        )

        credit_payment = AccountingItemPayment.objects.create(
            member=member, reg=registration, pay=PaymentChoices.CREDIT, value=Decimal("50.00"), assoc=association
        )

        # Step 3: Create character and other related data
        from larpmanager.models.character import Character
        from larpmanager.models.registration import RegistrationCharacterRel

        character = Character.objects.create(name="Test Character", assoc=association)

        char_rel = RegistrationCharacterRel.objects.create(reg=registration, character=character, principal=True)

        # Create discount
        discount = AccountingItemDiscount.objects.create(
            member=member, run=run, value=Decimal("10.00"), assoc=association
        )

        # Step 4: Cancel registration
        with patch("larpmanager.accounting.registration.reset_event_links") as mock_reset_links:
            cancel_reg(registration)

            # Verify cancellation date was set
            registration.refresh_from_db()
            assert registration.cancellation_date is not None, "Cancellation date should be set"

            # Verify character relationship was deleted
            char_rels = RegistrationCharacterRel.objects.filter(reg=registration)
            assert char_rels.count() == 0, "Character relationships should be deleted"

            # Verify discount was deleted
            discounts = AccountingItemDiscount.objects.filter(run=run, member=member)
            assert discounts.count() == 0, "Discounts should be deleted"

            # Verify event links were reset
            mock_reset_links.assert_called_once_with(self.member().id, association.id)

        # Step 5: Process refunds
        # Delete token/credit payments (simulating refund processing)
        AccountingItemPayment.objects.filter(
            member=member, pay__in=[PaymentChoices.TOKEN, PaymentChoices.CREDIT], reg__run=run
        ).delete()

        # Create credit refund for money payment
        money_paid = AccountingItemPayment.objects.filter(
            member=member, pay=PaymentChoices.MONEY, reg__run=run
        ).aggregate(total=models.Sum("value"))["total"] or Decimal("0")

        if money_paid > 0:
            refund_credit = AccountingItemOther.objects.create(
                member=member,
                oth=OtherChoices.CREDIT,
                descr=f"Refund for {run}",
                run=run,
                value=money_paid,
                assoc=association,
                cancellation=True,
            )

        # Mark registration as refunded
        registration.refunded = True
        registration.save()

        # Step 6: Verify final state
        # Check refund credit was created
        refund_credits = AccountingItemOther.objects.filter(
            member=member, oth=OtherChoices.CREDIT, run=run, cancellation=True
        )
        assert refund_credits.count() == 1, f"Expected 1 refund credit, got {refund_credits.count()}"

        refund_credit = refund_credits.first()
        assert refund_credit.value == money_paid, f"Refund credit should be {money_paid}, got {refund_credit.value}"

        # Check token/credit payments were removed
        remaining_tc_payments = AccountingItemPayment.objects.filter(
            member=member, pay__in=[PaymentChoices.TOKEN, PaymentChoices.CREDIT], reg__run=run
        )
        assert remaining_tc_payments.count() == 0, "Token/credit payments should be removed"

        # Verify registration is marked as refunded
        assert registration.refunded is True, "Registration should be marked as refunded"
        assert registration.cancellation_date is not None, "Registration should be cancelled"


# Fixtures
@pytest.fixture
def association():
    return Association.objects.create(
        name="Integration Test Association", slug="integration-test", email="integration@test.com"
    )


@pytest.fixture
def member():
    user = User.objects.create_user(
        username="integration_user", email="integration@test.com", first_name="Integration", last_name="Test"
    )
    member = user.member
    self.member().name = "Integration"
    self.member().surname = "Test"
    self.member().save()
    return member
