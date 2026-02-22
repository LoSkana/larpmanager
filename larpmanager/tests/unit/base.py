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

"""Base test case for unit tests with common methods"""

from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import TestCase
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.models.accounting import DiscountType
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration


@pytest.mark.django_db
class BaseTestCase(TestCase):
    """Base test case with common test object accessors"""

    def get_association(self) -> Any:
        """Get the first association from test fixtures, or create one"""
        association = Association.objects.first()
        if not association:
            association = self.create_association()
        return association

    def get_user(self) -> Any:
        """Get the first user from test fixtures, or create one"""
        user = User.objects.first()
        if not user:
            user = self.create_user()
        return user

    def get_member(self) -> Any:
        """Get the first member from test fixtures, or create one"""
        from decimal import Decimal

        from larpmanager.models.member import Membership

        member = Member.objects.first()
        if not member:
            # Check if we already have a user to avoid constraint violations
            user = User.objects.first()
            if not user:
                user = self.create_user()
            # Check if this user already has a member
            try:
                member = user.member
            except ObjectDoesNotExist:
                member = self.create_member(user=user)

        # Ensure the member has a membership attribute set
        if not hasattr(member, "membership") or member.membership is None:
            association = self.get_association()
            membership, _ = Membership.objects.get_or_create(
                member=member,
                association=association,
                defaults={
                    "credit": Decimal("100.00"),
                    "tokens": Decimal("50.00"),
                },
            )
            member.membership = membership

        return member

    def get_event(self) -> Any:
        """Get the first event from test fixtures, or create one"""
        event = Event.objects.first()
        if not event:
            event = self.create_event()
        return event

    def get_run(self) -> Any:
        """Get the first run from test fixtures, or create one"""
        run = Run.objects.first()
        if not run:
            # Get or create event first
            event = Event.objects.first()
            if not event:
                event = self.create_event()
            # Check if this event already has a run with number 1
            run = Run.objects.filter(event=event, number=1).first()
            if not run:
                run = self.create_run(event=event)
        return run

    def get_registration(self) -> Any:
        """Get the first registration from test fixtures, or create one"""
        registration = Registration.objects.first()
        if not registration:
            registration = self.create_registration()
        return registration

    # Helper methods for creating specific test objects when needed
    def create_association(self, **kwargs: Any) -> Any:
        """Create a new association with defaults"""
        defaults = {"name": "Test Association", "slug": "test-association", "main_mail": "test@example.com"}
        defaults.update(kwargs)
        return Association.objects.create(**defaults)

    def create_user(self, **kwargs: Any) -> Any:
        """Create a new user with defaults"""
        defaults = {"username": "testuser", "email": "test@example.com", "first_name": "Test", "last_name": "User"}
        defaults.update(kwargs)
        return User.objects.create_user(**defaults)

    def create_member(self, user: Any = None, **kwargs: Any) -> Any:
        """Create a new member with defaults"""
        from decimal import Decimal

        from larpmanager.models.member import Membership

        if user is None:
            user = self.create_user()

        member = user.member
        member.name = "Test"
        member.surname = "Member"

        # Create a membership for this member
        association = self.get_association()
        membership, _ = Membership.objects.get_or_create(
            member=member,
            association=association,
            defaults={
                "credit": Decimal("100.00"),
                "tokens": Decimal("50.00"),
            },
        )

        # Set the dynamic membership attribute like the function does
        member.membership = membership

        return member

    def create_event(self, association: Any = None, **kwargs: Any) -> Any:
        """Create a new event with defaults"""
        if association is None:
            association = self.get_association()
        defaults = {"name": "Test Event", "association": association}
        defaults.update(kwargs)
        return Event.objects.create(**defaults)

    def create_run(self, event: Any = None, **kwargs: Any) -> Any:
        """Create a new run with defaults"""
        if event is None:
            event = self.get_event()
        from datetime import date

        defaults = {"event": event, "number": 1, "start": date.today(), "end": date.today()}
        defaults.update(kwargs)
        return Run.objects.create(**defaults)

    def create_registration(self, member: Any = None, run: Any = None, **kwargs: Any) -> Any:
        """Create a new registration with defaults"""
        if member is None:
            member = self.get_member()
        if run is None:
            run = self.get_run()
        from decimal import Decimal

        defaults = {
            "member": member,
            "run": run,
            "tot_iscr": Decimal("100.00"),
            "tot_payed": Decimal("0.00"),
            "quotas": 1,
        }
        defaults.update(kwargs)
        return Registration.objects.create(**defaults)

    def payment_invoice(self, **kwargs: Any) -> Any:
        """Create a payment invoice for testing"""
        from decimal import Decimal

        from larpmanager.models.accounting import PaymentInvoice, PaymentStatus, PaymentType

        defaults = {
            "member": self.get_member(),
            "association": self.get_association(),
            "method": self.payment_method(),
            "typ": PaymentType.REGISTRATION,
            "status": PaymentStatus.CREATED,
            "mc_gross": Decimal("100.00"),
            "mc_fee": Decimal("5.00"),
            "causal": "Test payment",
            "cod": "TEST123",
            "txn_id": "TXN456",
            "verified": False,
        }
        defaults.update(kwargs)
        return PaymentInvoice(**defaults)

    def payment_item(self, **kwargs: Any) -> Any:
        """Create a payment item for testing"""
        from datetime import datetime
        from decimal import Decimal

        from larpmanager.models.accounting import AccountingItemPayment, PaymentChoices

        defaults = {
            "member": self.get_member(),
            "value": Decimal("100.00"),
            "association": self.get_association(),
            "registration": self.get_registration(),
            "pay": PaymentChoices.MONEY,
            "created": datetime.now(),
        }
        defaults.update(kwargs)
        return AccountingItemPayment(**defaults)

    def other_item_token(self, **kwargs: Any) -> Any:
        """Create an other item for tokens"""
        from decimal import Decimal

        from larpmanager.models.accounting import AccountingItemOther, OtherChoices

        defaults = {
            "member": self.get_member(),
            "value": Decimal("5"),
            "association": self.get_association(),
            "run": self.get_run(),
            "oth": OtherChoices.TOKEN,
            "descr": "Test tokens",
        }
        defaults.update(kwargs)
        return AccountingItemOther(**defaults)

    def other_item_credit(self, **kwargs: Any) -> Any:
        """Create an other item for credits"""
        from decimal import Decimal

        from larpmanager.models.accounting import AccountingItemOther, OtherChoices

        defaults = {
            "member": self.get_member(),
            "value": Decimal("50.00"),
            "association": self.get_association(),
            "run": self.get_run(),
            "oth": OtherChoices.CREDIT,
            "descr": "Test credits",
        }
        defaults.update(kwargs)
        return AccountingItemOther(**defaults)

    def payment_method(self, **kwargs: Any) -> Any:
        """Create a payment method for testing"""
        from larpmanager.models.base import PaymentMethod

        defaults = {"name": "Test Method", "slug": "test", "fields": "field1,field2"}
        defaults.update(kwargs)
        return PaymentMethod.objects.create(**defaults)

    def ticket(self, event: Any = None, **kwargs: Any) -> Any:
        """Create a registration ticket for testing"""
        from decimal import Decimal

        from larpmanager.models.registration import RegistrationTicket, TicketTier

        if event is None:
            event = self.get_event()
        defaults = {
            "event": event,
            "tier": TicketTier.STANDARD,
            "name": "Standard Ticket",
            "price": Decimal("100.00"),
            "number": 1,
            "max_available": 50,
        }
        defaults.update(kwargs)
        return RegistrationTicket.objects.create(**defaults)

    def question(self, event: Any = None, **kwargs: Any) -> Any:
        """Create a registration question for testing"""
        from larpmanager.models.form import BaseQuestionType, QuestionStatus, RegistrationQuestion

        if event is None:
            event = self.get_event()
        defaults = {
            "event": event,
            "name": "dietary_requirements",
            "description": "Do you have any dietary requirements?",
            "typ": BaseQuestionType.TEXT,
            "status": QuestionStatus.MANDATORY,
            "order": 1,
        }
        defaults.update(kwargs)
        return RegistrationQuestion.objects.create(**defaults)

    def question_with_options(self, event: Any = None, **kwargs: Any) -> Any:
        """Create a question with multiple choice options for testing"""
        from decimal import Decimal

        from larpmanager.models.form import BaseQuestionType, QuestionStatus, RegistrationOption, RegistrationQuestion

        if event is None:
            event = self.get_event()

        question_defaults = {
            "event": event,
            "name": "accommodation",
            "description": "What accommodation do you prefer?",
            "typ": BaseQuestionType.SINGLE,
            "status": QuestionStatus.MANDATORY,
            "order": 1,
        }
        question_defaults.update(kwargs)
        question = RegistrationQuestion.objects.create(**question_defaults)

        option1 = RegistrationOption.objects.create(
            event=event, question=question, name="Hotel", price=Decimal("50.00"), order=1
        )
        option2 = RegistrationOption.objects.create(
            event=event, question=question, name="Camping", price=Decimal("20.00"), order=2
        )

        return question, option1, option2

    def character(self, event: Any = None, **kwargs: Any) -> Any:
        """Create a character for testing"""
        from larpmanager.models.writing import Character

        if event is None:
            event = self.get_event()

        # Get next available number for this event
        if "number" not in kwargs:
            last_char = Character.objects.filter(event=event).order_by("-number").first()
            next_number = (last_char.number + 1) if last_char else 1
            kwargs["number"] = next_number

        defaults = {"name": "Test Character", "event": event}
        defaults.update(kwargs)
        return Character.objects.create(**defaults)

    def invoice(self) -> Any:
        """Get or create a payment invoice for testing"""
        from larpmanager.models.accounting import PaymentInvoice

        invoice = PaymentInvoice.objects.first()
        if not invoice:
            invoice = self.payment_invoice()
            invoice.save()
        return invoice

    def accounting_item(self) -> Any:
        """Get or create an accounting item for testing"""
        from decimal import Decimal

        from larpmanager.models.accounting import AccountingItemExpense

        item = AccountingItemExpense.objects.first()
        if not item:
            item = AccountingItemExpense.objects.create(
                member=self.get_member(),
                value=Decimal("50.00"),
                association=self.get_association(),
                descr="Test expense",
            )
        return item

    def collection(self) -> Any:
        """Get or create a collection for testing"""
        from larpmanager.models.accounting import Collection

        collection = Collection.objects.first()
        if not collection:
            collection = Collection.objects.create(
                name="Test Collection", association=self.get_association(), organizer=self.organizer()
            )
        return collection

    def collection_item(self) -> Any:
        """Get or create a collection item for testing"""
        from decimal import Decimal

        from larpmanager.models.accounting import AccountingItemCollection

        item = AccountingItemCollection.objects.first()
        if not item:
            item = AccountingItemCollection.objects.create(
                member=self.get_member(),
                value=Decimal("25.00"),
                association=self.get_association(),
                collection=self.collection(),
            )
        return item

    def organizer(self) -> Any:
        """Get or create an organizer (member) for testing"""
        from larpmanager.models.member import Member

        organizer = Member.objects.filter(name="Organizer").first()
        if not organizer:
            # Try to get existing organizer user or create new one
            organizer_user, created = User.objects.get_or_create(
                username="organizer",
                defaults={"email": "organizer@example.com", "first_name": "Test", "last_name": "Organizer"},
            )
            # Check if this user already has a member
            try:
                organizer = organizer_user.member
            except ObjectDoesNotExist:
                organizer = Member.objects.create(user=organizer_user, name="Organizer", surname="Test", language="en")
        return organizer

    def refund_request(self) -> Any:
        """Get or create a refund request for testing"""
        from decimal import Decimal

        from larpmanager.models.accounting import RefundRequest

        refund = RefundRequest.objects.first()
        if not refund:
            refund = RefundRequest.objects.create(
                member=self.get_member(),
                value=Decimal("30.00"),
                details="Test refund request",
                association=self.get_association(),
            )
        return refund

    def other_item_refund(self) -> Any:
        """Create an other item for refunds"""
        from decimal import Decimal

        from larpmanager.models.accounting import AccountingItemOther, OtherChoices

        return AccountingItemOther(
            member=self.get_member(),
            value=Decimal("30.00"),
            association=self.get_association(),
            run=self.get_run(),
            oth=OtherChoices.REFUND,
            descr="Test refund",
        )

    def discount(self) -> Any:
        """Get or create a discount for testing"""
        from decimal import Decimal

        from larpmanager.models.accounting import Discount

        discount = Discount.objects.first()
        if not discount:
            discount = Discount.objects.create(
                name="Test Discount",
                value=Decimal("10.00"),
                max_redeem=10,
                typ=DiscountType.STANDARD,
                event=self.get_event(),
                number=1,
            )
            # Add the current run to the discount
            discount.runs.add(self.get_run())
        return discount

    def user_with_permissions(self) -> Any:
        """Get or create a user with permissions for testing"""
        # This can return the same as member().user for simplicity
        # or create a specific user with permissions if needed
        return self.get_member().user
