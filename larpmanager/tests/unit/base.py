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

import pytest
from django.contrib.auth.models import User

from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration


@pytest.mark.django_db
class BaseTestCase:
    """Base test case with common test object accessors"""

    def association(self):
        """Get the first association from test fixtures, or create one"""
        association = Association.objects.first()
        if not association:
            association = self.create_association()
        return association

    def user(self):
        """Get the first user from test fixtures, or create one"""
        user = User.objects.first()
        if not user:
            user = self.create_user()
        return user

    def member(self):
        """Get the first member from test fixtures, or create one"""
        member = Member.objects.first()
        if not member:
            # Check if we already have a user to avoid constraint violations
            user = User.objects.first()
            if not user:
                user = self.create_user()
            # Check if this user already has a member
            try:
                member = user.member
            except Member.DoesNotExist:
                member = self.create_member(user=user)
        return member

    def event(self):
        """Get the first event from test fixtures, or create one"""
        event = Event.objects.first()
        if not event:
            event = self.create_event()
        return event

    def run(self):
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

    def registration(self):
        """Get the first registration from test fixtures, or create one"""
        registration = Registration.objects.first()
        if not registration:
            registration = self.create_registration()
        return registration

    # Helper methods for creating specific test objects when needed
    def create_association(self, **kwargs):
        """Create a new association with defaults"""
        defaults = {
            'name': 'Test Association',
            'slug': 'test-assoc',
            'email': 'test@example.com'
        }
        defaults.update(kwargs)
        return Association.objects.create(**defaults)

    def create_user(self, **kwargs):
        """Create a new user with defaults"""
        defaults = {
            'username': 'testuser',
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User'
        }
        defaults.update(kwargs)
        return User.objects.create_user(**defaults)

    def create_member(self, user=None, **kwargs):
        """Create a new member with defaults"""
        if user is None:
            user = self.create_user()
        defaults = {
            'user': user,
            'name': 'Test',
            'surname': 'Member'
        }
        defaults.update(kwargs)
        return Member.objects.create(**defaults)

    def create_event(self, association=None, **kwargs):
        """Create a new event with defaults"""
        if association is None:
            association = self.association()
        defaults = {
            'name': 'Test Event',
            'assoc': association
        }
        defaults.update(kwargs)
        return Event.objects.create(**defaults)

    def create_run(self, event=None, **kwargs):
        """Create a new run with defaults"""
        if event is None:
            event = self.event()
        from datetime import date
        defaults = {
            'event': event,
            'number': 1,
            'start': date.today(),
            'end': date.today()
        }
        defaults.update(kwargs)
        return Run.objects.create(**defaults)

    def create_registration(self, member=None, run=None, **kwargs):
        """Create a new registration with defaults"""
        if member is None:
            member = self.member()
        if run is None:
            run = self.run()
        from decimal import Decimal
        defaults = {
            'member': member,
            'run': run,
            'tot_iscr': Decimal('100.00'),
            'tot_payed': Decimal('0.00'),
            'quotas': 1
        }
        defaults.update(kwargs)
        return Registration.objects.create(**defaults)

    def payment_invoice(self, **kwargs):
        """Create a payment invoice for testing"""
        from larpmanager.models.accounting import PaymentInvoice, PaymentType, PaymentStatus
        from decimal import Decimal

        defaults = {
            'member': self.member(),
            'assoc': self.association(),
            'method': self.payment_method(),
            'typ': PaymentType.REGISTRATION,
            'status': PaymentStatus.CREATED,
            'mc_gross': Decimal('100.00'),
            'mc_fee': Decimal('5.00'),
            'causal': 'Test payment',
            'cod': 'TEST123',
            'txn_id': 'TXN456',
            'verified': False,
        }
        defaults.update(kwargs)
        return PaymentInvoice(**defaults)

    def payment_item(self, **kwargs):
        """Create a payment item for testing"""
        from larpmanager.models.accounting import AccountingItemPayment, PaymentChoices
        from decimal import Decimal
        from datetime import datetime

        defaults = {
            'member': self.member(),
            'value': Decimal('100.00'),
            'assoc': self.association(),
            'reg': self.registration(),
            'pay': PaymentChoices.MONEY,
            'created': datetime.now(),
        }
        defaults.update(kwargs)
        return AccountingItemPayment(**defaults)

    def other_item_token(self, **kwargs):
        """Create an other item for tokens"""
        from larpmanager.models.accounting import AccountingItemOther, OtherChoices
        from decimal import Decimal

        defaults = {
            'member': self.member(),
            'value': Decimal('5'),
            'assoc': self.association(),
            'run': self.run(),
            'oth': OtherChoices.TOKEN,
            'descr': 'Test tokens'
        }
        defaults.update(kwargs)
        return AccountingItemOther(**defaults)

    def other_item_credit(self, **kwargs):
        """Create an other item for credits"""
        from larpmanager.models.accounting import AccountingItemOther, OtherChoices
        from decimal import Decimal

        defaults = {
            'member': self.member(),
            'value': Decimal('50.00'),
            'assoc': self.association(),
            'run': self.run(),
            'oth': OtherChoices.CREDIT,
            'descr': 'Test credits'
        }
        defaults.update(kwargs)
        return AccountingItemOther(**defaults)

    def payment_method(self, **kwargs):
        """Create a payment method for testing"""
        from larpmanager.models.base import PaymentMethod

        defaults = {
            'name': 'Test Method',
            'slug': 'test',
            'fields': 'field1,field2'
        }
        defaults.update(kwargs)
        return PaymentMethod.objects.create(**defaults)

    def ticket(self, event=None, **kwargs):
        """Create a registration ticket for testing"""
        from larpmanager.models.registration import RegistrationTicket, TicketTier
        from decimal import Decimal

        if event is None:
            event = self.event()
        defaults = {
            'event': event,
            'tier': TicketTier.STANDARD,
            'name': 'Standard Ticket',
            'price': Decimal('100.00'),
            'number': 1,
            'max_available': 50
        }
        defaults.update(kwargs)
        return RegistrationTicket.objects.create(**defaults)

    def question(self, event=None, **kwargs):
        """Create a registration question for testing"""
        from larpmanager.models.form import RegistrationQuestion, BaseQuestionType, QuestionStatus

        if event is None:
            event = self.event()
        defaults = {
            'event': event,
            'name': 'dietary_requirements',
            'description': 'Do you have any dietary requirements?',
            'typ': BaseQuestionType.TEXT,
            'status': QuestionStatus.MANDATORY,
            'order': 1
        }
        defaults.update(kwargs)
        return RegistrationQuestion.objects.create(**defaults)

    def question_with_options(self, event=None, **kwargs):
        """Create a question with multiple choice options for testing"""
        from larpmanager.models.form import RegistrationQuestion, RegistrationOption, BaseQuestionType, QuestionStatus
        from decimal import Decimal

        if event is None:
            event = self.event()

        question_defaults = {
            'event': event,
            'name': 'accommodation',
            'description': 'What accommodation do you prefer?',
            'typ': BaseQuestionType.SINGLE,
            'status': QuestionStatus.MANDATORY,
            'order': 1
        }
        question_defaults.update(kwargs)
        question = RegistrationQuestion.objects.create(**question_defaults)

        option1 = RegistrationOption.objects.create(
            event=event, question=question, name='Hotel', price=Decimal('50.00'), order=1
        )
        option2 = RegistrationOption.objects.create(
            event=event, question=question, name='Camping', price=Decimal('20.00'), order=2
        )

        return question, option1, option2

    def character(self, association=None, **kwargs):
        """Create a character for testing"""
        from larpmanager.models.writing import Character

        if association is None:
            association = self.association()
        defaults = {
            'name': 'Test Character',
            'assoc': association
        }
        defaults.update(kwargs)
        return Character.objects.create(**defaults)