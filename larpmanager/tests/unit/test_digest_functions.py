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

"""Tests for digest email generation functions"""

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from django.utils import timezone

from larpmanager.mail.digest import (
    digest_help_questions,
    digest_invoice_approvals,
    digest_password_reminders,
    digest_refund_request,
    generate_association_summary_email,
    generate_summary_email,
)
from larpmanager.models.accounting import AccountingItemPayment, PaymentInvoice
from larpmanager.models.member import NotificationQueue, NotificationType
from larpmanager.models.miscellanea import HelpQuestion
from larpmanager.models.registration import Registration
from larpmanager.tests.unit.base import BaseTestCase


class TestDigestFunctions(BaseTestCase):
    """Test cases for digest email generation functions"""

    def setUp(self) -> None:
        """Set up test fixtures"""
        super().setUp()
        self.event = self.get_event()
        self.association = self.get_association()
        self.run = self.get_run()
        self.member = self.get_member()

    def test_generate_summary_email_with_new_registrations(self) -> None:
        """Test generating summary email with new registrations"""
        # Create a registration
        registration = self.get_registration()

        # Create notification
        notification = NotificationQueue.objects.create(
            run=self.run,
            member=self.member,
            notification_type=NotificationType.REGISTRATION_NEW,
            object_id=registration.id,
            sent=False,
        )

        # Generate email
        email_content = generate_summary_email(self.event, [notification])

        # Verify content
        self.assertIn("Daily Summary", email_content)
        self.assertIn("New Registrations", email_content)
        self.assertIn(registration.member.username, email_content)

    def test_generate_summary_email_with_updated_registrations(self) -> None:
        """Test generating summary email with updated registrations"""
        registration = self.get_registration()

        notification = NotificationQueue.objects.create(
            run=self.run,
            member=self.member,
            notification_type=NotificationType.REGISTRATION_UPDATE,
            object_id=registration.id,
            sent=False,
        )

        email_content = generate_summary_email(self.event, [notification])

        self.assertIn("Daily Summary", email_content)
        self.assertIn("Updated Registrations", email_content)
        self.assertIn(registration.member.username, email_content)

    def test_generate_summary_email_with_cancelled_registrations(self) -> None:
        """Test generating summary email with cancelled registrations"""
        registration = self.get_registration()

        notification = NotificationQueue.objects.create(
            run=self.run,
            member=self.member,
            notification_type=NotificationType.REGISTRATION_CANCEL,
            object_id=registration.id,
            sent=False,
        )

        email_content = generate_summary_email(self.event, [notification])

        self.assertIn("Daily Summary", email_content)
        self.assertIn("Cancelled Registrations", email_content)
        self.assertIn(registration.member.username, email_content)

    def test_generate_summary_email_with_payments(self) -> None:
        """Test generating summary email with payments"""
        from larpmanager.models.accounting import PaymentChoices

        registration = self.get_registration()
        payment = AccountingItemPayment.objects.create(
            member=self.member,
            value=Decimal("100.00"),
            association=self.association,
            registration=registration,
            pay=PaymentChoices.MONEY,
        )

        notification = NotificationQueue.objects.create(
            run=self.run,
            member=self.member,
            notification_type=NotificationType.PAYMENT_MONEY,
            object_id=payment.id,
            sent=False,
        )

        email_content = generate_summary_email(self.event, [notification])

        self.assertIn("Daily Summary", email_content)
        self.assertIn("Payments Received", email_content)
        self.assertIn(self.member.username, email_content)

    def test_generate_summary_email_with_invoice_approvals(self) -> None:
        """Test generating summary email with invoice approvals"""
        invoice = PaymentInvoice.objects.create(
            member=self.member,
            association=self.association,
            causal="Test Invoice",
            amount=Decimal("50.00"),
            mc_gross=Decimal("50.00"),
        )

        notification = NotificationQueue.objects.create(
            run=self.run,
            member=self.member,
            notification_type=NotificationType.INVOICE_APPROVAL,
            object_id=invoice.id,
            sent=False,
        )

        email_content = generate_summary_email(self.event, [notification])

        self.assertIn("Daily Summary", email_content)
        self.assertIn("Invoices Awaiting Approval", email_content)
        self.assertIn(self.member.username, email_content)
        self.assertIn("Approve", email_content)

    def test_generate_summary_email_with_multiple_notification_types(self) -> None:
        """Test generating summary email with multiple notification types"""
        registration = self.get_registration()
        from larpmanager.models.accounting import PaymentChoices

        payment = AccountingItemPayment.objects.create(
            member=self.member,
            value=Decimal("75.00"),
            association=self.association,
            registration=registration,
            pay=PaymentChoices.MONEY,
        )

        notifications = [
            NotificationQueue.objects.create(
                run=self.run,
                member=self.member,
                notification_type=NotificationType.REGISTRATION_NEW,
                object_id=registration.id,
                sent=False,
            ),
            NotificationQueue.objects.create(
                run=self.run,
                member=self.member,
                notification_type=NotificationType.PAYMENT_MONEY,
                object_id=payment.id,
                sent=False,
            ),
        ]

        email_content = generate_summary_email(self.event, notifications)

        self.assertIn("Daily Summary", email_content)
        self.assertIn("New Registrations", email_content)
        self.assertIn("Payments Received", email_content)

    def test_generate_association_summary_email_with_help_questions(self) -> None:
        """Test generating association summary email with help questions"""
        question = HelpQuestion.objects.create(
            member=self.member, association=self.association, text="Need help with something important"
        )

        notification = NotificationQueue.objects.create(
            association=self.association,
            member=self.member,
            notification_type=NotificationType.HELP_QUESTION,
            object_id=question.id,
            sent=False,
        )

        email_content = generate_association_summary_email(self.association, [notification])

        self.assertIn("Daily Summary", email_content)
        self.assertIn("Help Questions", email_content)
        self.assertIn(self.member.username, email_content)
        self.assertIn("View", email_content)

    def test_generate_association_summary_email_with_invoice_approvals(self) -> None:
        """Test generating association summary email with invoice approvals"""
        invoice = PaymentInvoice.objects.create(
            member=self.member,
            association=self.association,
            causal="Association Invoice",
            amount=Decimal("150.00"),
            mc_gross=Decimal("150.00"),
        )

        notification = NotificationQueue.objects.create(
            association=self.association,
            member=self.member,
            notification_type=NotificationType.INVOICE_APPROVAL_EXE,
            object_id=invoice.id,
            sent=False,
        )

        email_content = generate_association_summary_email(self.association, [notification])

        self.assertIn("Daily Summary", email_content)
        self.assertIn("Invoices Awaiting Approval", email_content)
        self.assertIn(self.member.username, email_content)
        self.assertIn("Approve", email_content)

    def test_generate_association_summary_email_with_refund_requests(self) -> None:
        """Test generating association summary email with refund requests"""
        invoice = PaymentInvoice.objects.create(
            member=self.member,
            association=self.association,
            causal="Refund Request",
            amount=Decimal("75.00"),
            mc_gross=Decimal("75.00"),
        )

        notification = NotificationQueue.objects.create(
            association=self.association,
            member=self.member,
            notification_type=NotificationType.REFUND_REQUEST,
            object_id=invoice.id,
            sent=False,
        )

        email_content = generate_association_summary_email(self.association, [notification])

        self.assertIn("Daily Summary", email_content)
        self.assertIn("Refund Requests", email_content)
        self.assertIn(self.member.username, email_content)
        self.assertIn("View", email_content)

    def test_generate_association_summary_email_with_password_reminders(self) -> None:
        """Test generating association summary email with password reminders"""
        invoice = PaymentInvoice.objects.create(
            member=self.member,
            association=self.association,
            causal="Password Reminder",
            amount=Decimal("0.00"),
            mc_gross=Decimal("0.00"),
        )

        notification = NotificationQueue.objects.create(
            association=self.association,
            member=self.member,
            notification_type=NotificationType.PASSWORD_REMINDER,
            object_id=invoice.id,
            sent=False,
        )

        email_content = generate_association_summary_email(self.association, [notification])

        self.assertIn("Daily Summary", email_content)
        self.assertIn("Password Reset Requests", email_content)

    def test_generate_association_summary_email_with_multiple_notification_types(self) -> None:
        """Test generating association summary email with multiple notification types"""
        question = HelpQuestion.objects.create(
            member=self.member, association=self.association, text="Need assistance"
        )

        invoice = PaymentInvoice.objects.create(
            member=self.member,
            association=self.association,
            causal="Multi-type test",
            amount=Decimal("100.00"),
            mc_gross=Decimal("100.00"),
        )

        notifications = [
            NotificationQueue.objects.create(
                association=self.association,
                member=self.member,
                notification_type=NotificationType.HELP_QUESTION,
                object_id=question.id,
                sent=False,
            ),
            NotificationQueue.objects.create(
                association=self.association,
                member=self.member,
                notification_type=NotificationType.INVOICE_APPROVAL_EXE,
                object_id=invoice.id,
                sent=False,
            ),
        ]

        email_content = generate_association_summary_email(self.association, notifications)

        self.assertIn("Daily Summary", email_content)
        self.assertIn("Help Questions", email_content)
        self.assertIn("Invoices Awaiting Approval", email_content)

    def test_digest_help_questions_generates_correct_content(self) -> None:
        """Test that digest_help_questions generates correct HTML content"""
        question = HelpQuestion.objects.create(
            member=self.member, association=self.association, text="Test question text" * 10  # Long text
        )

        notification = NotificationQueue.objects.create(
            association=self.association,
            member=self.member,
            notification_type=NotificationType.HELP_QUESTION,
            object_id=question.id,
            sent=False,
        )

        content = digest_help_questions(self.association, [notification])

        self.assertIn("Help Questions", content)
        self.assertIn("(1)", content)
        self.assertIn(self.member.username, content)
        self.assertIn("View", content)

    def test_digest_invoice_approvals_generates_correct_content(self) -> None:
        """Test that digest_invoice_approvals generates correct HTML content"""
        invoice = PaymentInvoice.objects.create(
            member=self.member,
            association=self.association,
            causal="Test Invoice",
            amount=Decimal("200.00"),
            mc_gross=Decimal("200.00"),
        )

        notification = NotificationQueue.objects.create(
            association=self.association,
            member=self.member,
            notification_type=NotificationType.INVOICE_APPROVAL_EXE,
            object_id=invoice.id,
            sent=False,
        )

        content = digest_invoice_approvals(self.association, [notification])

        self.assertIn("Invoices Awaiting Approval", content)
        self.assertIn("(1)", content)
        self.assertIn(self.member.username, content)
        self.assertIn("Approve", content)

    def test_digest_refund_request_generates_correct_content(self) -> None:
        """Test that digest_refund_request generates correct HTML content"""
        invoice = PaymentInvoice.objects.create(
            member=self.member,
            association=self.association,
            causal="Refund Test",
            amount=Decimal("50.00"),
            mc_gross=Decimal("50.00"),
        )

        notification = NotificationQueue.objects.create(
            association=self.association,
            member=self.member,
            notification_type=NotificationType.REFUND_REQUEST,
            object_id=invoice.id,
            sent=False,
        )

        content = digest_refund_request(self.association, [notification])

        self.assertIn("Refund Requests", content)
        self.assertIn("(1)", content)
        self.assertIn(self.member.username, content)
        self.assertIn("View", content)

    def test_generate_summary_email_with_empty_notifications(self) -> None:
        """Test generating summary email with empty notifications list"""
        email_content = generate_summary_email(self.event, [])

        self.assertIn("Daily Summary", email_content)
        self.assertIn(self.event.name, email_content)
        self.assertIn("Go to event dashboard", email_content)

    def test_generate_association_summary_email_with_empty_notifications(self) -> None:
        """Test generating association summary email with empty notifications list"""
        email_content = generate_association_summary_email(self.association, [])

        self.assertIn("Daily Summary", email_content)
        self.assertIn(self.association.name, email_content)
        self.assertIn("Go to association dashboard", email_content)
