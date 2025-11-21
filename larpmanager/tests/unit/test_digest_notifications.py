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

"""Unit tests for daily digest notification system"""

from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from django.utils import timezone

from larpmanager.cache.config import set_event_config
from larpmanager.mail.digest import generate_summary_email, send_daily_organizer_summaries
from larpmanager.models.notification import (
    OrganizerNotificationQueue,
    queue_organizer_notification,
    should_queue_notification,
)
from larpmanager.tests.unit.base import BaseTestCase


@pytest.mark.django_db
class DigestNotificationTests(BaseTestCase):
    """Test suite for digest notification functionality"""

    def test_should_queue_notification_default_false(self) -> None:
        """Test that digest mode is OFF by default"""
        event = self.get_event()
        assert should_queue_notification(event) is False

    def test_should_queue_notification_enabled(self) -> None:
        """Test digest mode check when enabled"""
        event = self.get_event()
        set_event_config(event.pk, "mail_orga_digest", True)

        assert should_queue_notification(event) is True

    def test_queue_organizer_notification_creates_record(self) -> None:
        """Test that queueing creates a notification record"""
        event = self.get_event()
        registration = self.get_registration()

        notification = queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_NEW,
            registration=registration,
        )

        assert notification is not None
        assert notification.event == event
        assert notification.registration == registration
        assert notification.notification_type == "registration_new"
        assert notification.sent is False

    def test_queue_organizer_notification_with_details(self) -> None:
        """Test queueing with additional details"""
        event = self.get_event()

        notification = queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_CANCEL,
            details={"member_name": "Test User", "ticket_name": "Standard"},
        )

        assert notification.details == {"member_name": "Test User", "ticket_name": "Standard"}

    def test_notification_model_str(self) -> None:
        """Test string representation of notification"""
        event = self.get_event()
        notification = queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_NEW,
        )

        str_repr = str(notification)
        assert event.title in str_repr
        assert "New Registration" in str_repr

    def test_notification_ordering(self) -> None:
        """Test that notifications are ordered by created_at descending"""
        event = self.get_event()

        # Create multiple notifications
        notif1 = queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_NEW,
        )

        notif2 = queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.PAYMENT_MONEY,
        )

        # Query all notifications
        notifications = OrganizerNotificationQueue.objects.filter(event=event)

        # Should be ordered newest first
        assert list(notifications) == [notif2, notif1]

    def test_generate_summary_email_new_registrations(self) -> None:
        """Test email generation with new registrations"""
        event = self.get_event()
        registration = self.get_registration()

        # Create notification
        queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_NEW,
            registration=registration,
        )

        notifications = OrganizerNotificationQueue.objects.filter(event=event)
        email_content = generate_summary_email(event, notifications)

        # Check email contains expected sections
        assert "Daily Summary" in email_content
        assert "New Registrations" in email_content
        assert registration.member.username in email_content
        assert "View/Edit" in email_content

    def test_generate_summary_email_multiple_types(self) -> None:
        """Test email generation with multiple notification types"""
        event = self.get_event()
        registration = self.get_registration()

        # Create various notification types
        queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_NEW,
            registration=registration,
        )

        queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_UPDATE,
            registration=registration,
        )

        queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_CANCEL,
            details={"member_name": "Test User", "ticket_name": "Standard"},
        )

        notifications = OrganizerNotificationQueue.objects.filter(event=event)
        email_content = generate_summary_email(event, notifications)

        # Check all sections present
        assert "New Registrations" in email_content
        assert "Updated Registrations" in email_content
        assert "Cancelled Registrations" in email_content

    def test_generate_summary_email_payments(self) -> None:
        """Test email generation with payment notifications"""
        event = self.get_event()

        # Create payment notification
        queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.PAYMENT_MONEY,
            details={"member_name": "Test User", "currency_symbol": "€"},
        )

        notifications = OrganizerNotificationQueue.objects.filter(event=event)
        email_content = generate_summary_email(event, notifications)

        assert "Payments Received" in email_content
        assert "Test User" in email_content

    def test_generate_summary_email_invoice_approvals(self) -> None:
        """Test email generation with invoice approval notifications"""
        event = self.get_event()

        # Create invoice notification
        queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.INVOICE_APPROVAL,
            details={
                "member_name": "Test User",
                "invoice_number": 123,
                "amount": Decimal("100.00"),
            },
        )

        notifications = OrganizerNotificationQueue.objects.filter(event=event)
        email_content = generate_summary_email(event, notifications)

        assert "Invoices Awaiting Approval" in email_content
        assert "Test User" in email_content
        assert "123" in email_content
        assert "Approve" in email_content

    def test_generate_summary_email_dashboard_link(self) -> None:
        """Test that email contains link to event dashboard"""
        event = self.get_event()

        queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_NEW,
        )

        notifications = OrganizerNotificationQueue.objects.filter(event=event)
        email_content = generate_summary_email(event, notifications)

        assert "event dashboard" in email_content.lower()
        assert event.slug in email_content

    @patch("larpmanager.mail.digest.my_send_mail")
    @patch("larpmanager.mail.digest.get_event_organizers")
    def test_send_daily_organizer_summaries_sends_email(
        self, mock_get_organizers: Any, mock_send_mail: Any
    ) -> None:
        """Test that daily summary actually sends emails"""
        event = self.get_event()
        member = self.get_member()
        set_event_config(event.pk, "mail_orga_digest", True)

        # Mock organizers
        mock_get_organizers.return_value = [member]

        # Create notification
        queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_NEW,
        )

        # Run daily summary
        send_daily_organizer_summaries()

        # Should have called send_mail
        assert mock_send_mail.called
        assert mock_send_mail.call_count == 1

        # Check email was sent to organizer
        call_args = mock_send_mail.call_args
        assert member in call_args[0]  # Member should be in positional args

    @patch("larpmanager.mail.digest.my_send_mail")
    def test_send_daily_organizer_summaries_marks_as_sent(self, mock_send_mail: Any) -> None:
        """Test that notifications are marked as sent after summary"""
        from larpmanager.models.access import get_event_organizers

        event = self.get_event()
        set_event_config(event.pk, "mail_orga_digest", True)

        # Create notification
        notification = queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_NEW,
        )

        assert notification.sent is False
        assert notification.sent_at is None

        # Run daily summary
        send_daily_organizer_summaries()

        # Refresh notification from database
        notification.refresh_from_db()

        # Should be marked as sent
        assert notification.sent is True
        assert notification.sent_at is not None

    @patch("larpmanager.mail.digest.my_send_mail")
    def test_send_daily_organizer_summaries_skips_disabled_events(
        self, mock_send_mail: Any
    ) -> None:
        """Test that events with digest mode OFF are skipped"""
        event = self.get_event()
        set_event_config(event.pk, "mail_orga_digest", False)  # Digest OFF

        # Create notification
        queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_NEW,
        )

        # Run daily summary
        send_daily_organizer_summaries()

        # Should NOT send email because digest mode is OFF
        assert not mock_send_mail.called

    @patch("larpmanager.mail.digest.my_send_mail")
    def test_send_daily_organizer_summaries_no_duplicate_sends(
        self, mock_send_mail: Any
    ) -> None:
        """Test that already-sent notifications are not sent again"""
        event = self.get_event()
        set_event_config(event.pk, "mail_orga_digest", True)

        # Create and mark as sent
        notification = queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_NEW,
        )
        notification.sent = True
        notification.sent_at = timezone.now()
        notification.save()

        # Run daily summary
        send_daily_organizer_summaries()

        # Should NOT send email for already-sent notification
        assert not mock_send_mail.called

    def test_notification_cascade_delete_with_registration(self) -> None:
        """Test that notification is deleted when registration is deleted"""
        event = self.get_event()
        registration = self.get_registration()

        notification = queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_NEW,
            registration=registration,
        )

        notification_id = notification.id

        # Delete registration
        registration.delete()

        # Notification should also be deleted (cascade)
        assert not OrganizerNotificationQueue.objects.filter(id=notification_id).exists()

    def test_notification_survives_when_registration_is_none(self) -> None:
        """Test that notification without registration reference works"""
        event = self.get_event()

        # Create notification without registration (e.g., for deleted reg)
        notification = queue_organizer_notification(
            event=event,
            notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_CANCEL,
            registration=None,
            details={"member_name": "Deleted User", "ticket_name": "Standard"},
        )

        # Should work fine
        assert notification.registration is None
        assert notification.details["member_name"] == "Deleted User"

        # Email generation should handle None registration
        notifications = OrganizerNotificationQueue.objects.filter(event=event)
        email_content = generate_summary_email(event, notifications)
        assert "Deleted User" in email_content

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.get_association_features")
    def test_payment_notifications_sent_to_treasurer_skip_digest(
        self, mock_get_features: Any, mock_send_mail: Any
    ) -> None:
        """Test that payment notifications are sent immediately to treasurer (skip digest)"""
        from larpmanager.cache.config import set_association_config, set_event_config
        from larpmanager.mail.accounting import notify_pay_money
        from larpmanager.models.accounting import AccountingItemPayment

        event = self.get_event()
        run = self.get_run()
        member = self.get_member()
        treasurer = self.create_member()  # Create a treasurer

        # Enable treasurer feature
        mock_get_features.return_value = ["treasurer"]
        set_association_config(event.association_id, "treasurer_appointees", str(treasurer.pk))

        # Enable digest mode for organizers
        set_event_config(event.pk, "mail_orga_digest", True)

        # Create a payment
        payment = AccountingItemPayment()
        payment.value = Decimal("100.00")

        # Send payment notification
        notify_pay_money("€", payment, member, run)

        # Should send to treasurer immediately (not queued)
        assert mock_send_mail.called
        # Should send to user (1 call) + treasurer (1 call) = 2 calls
        assert mock_send_mail.call_count == 2

        # Should NOT create digest notification for organizers
        notifications = OrganizerNotificationQueue.objects.filter(event=event)
        assert notifications.count() == 0  # No digest queue entry

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.get_association_features")
    def test_payment_notifications_queued_when_no_treasurer(
        self, mock_get_features: Any, mock_send_mail: Any
    ) -> None:
        """Test that payment notifications are queued when there's no treasurer"""
        from larpmanager.cache.config import set_event_config
        from larpmanager.mail.accounting import notify_pay_money
        from larpmanager.models.accounting import AccountingItemPayment

        event = self.get_event()
        run = self.get_run()
        member = self.get_member()

        # No treasurer feature
        mock_get_features.return_value = []

        # Enable digest mode for organizers
        set_event_config(event.pk, "mail_orga_digest", True)

        # Create a payment
        payment = AccountingItemPayment()
        payment.value = Decimal("100.00")

        # Send payment notification
        notify_pay_money("€", payment, member, run)

        # Should only send to user (1 call), NOT to organizers
        assert mock_send_mail.call_count == 1

        # Should create digest notification for organizers
        notifications = OrganizerNotificationQueue.objects.filter(event=event)
        assert notifications.count() == 1
        assert notifications.first().notification_type == "payment_money"
