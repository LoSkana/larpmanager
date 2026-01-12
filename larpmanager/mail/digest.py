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

import logging

from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.models.accounting import AccountingItemPayment, PaymentInvoice
from larpmanager.models.association import get_url, hdr
from larpmanager.models.event import Event
from larpmanager.models.member import Member, NotificationQueue, NotificationType
from larpmanager.models.registration import Registration
from larpmanager.utils.larpmanager.tasks import my_send_mail

logger = logging.getLogger(__name__)


def send_daily_organizer_summaries() -> None:
    """Send daily summary emails to organizers with queued notifications.

    For each member with unsent notifications, collects all their notifications,
    groups them by event, generates summary emails, and marks notifications as sent.

    Only sends emails for members who have digest mode enabled in their preferences.
    """
    # Get all members with unsent notifications
    members_with_notifications = Member.objects.filter(organizernotificationqueue__sent=False).distinct()

    for member in members_with_notifications:
        # Collect all unsent notifications for this member
        member_notifications = NotificationQueue.objects.filter(member=member, sent=False).select_related(
            "event", "event__association", "registration", "payment", "invoice"
        )

        if not member_notifications.exists():
            continue

        # Group notifications by event
        events_notifications = {}
        for notification in member_notifications:
            event = notification.event
            if event not in events_notifications:
                events_notifications[event] = []
            events_notifications[event].append(notification)

        logger.info(
            "Sending daily summary to %s for %d events with %d total notifications",
            member.username,
            len(events_notifications),
            member_notifications.count(),
        )

        # Send a summary email for each event this member has notifications for
        for event, notifications in events_notifications.items():
            # Activate member's preferred language
            activate(member.language)

            # Generate summary email content for this event
            email_content = generate_summary_email(event, notifications)

            # Build email subject
            email_subject = hdr(event) + _("Daily Summary") + f" - {event.name}"

            # Send the email
            my_send_mail(
                email_subject,
                email_content,
                member,
                event.current_run,
            )

        # Mark all notifications for this member as sent
        member_notifications.update(sent=True, sent_at=timezone.now())
        logger.info("Daily summary sent to %s", member.username)


def generate_summary_email(event: Event, notifications: QuerySet[NotificationQueue]) -> str:
    """Generate HTML email content for daily organizer summary.

    Creates a simple text-based summary with sections for:
    - New registrations
    - Updated registrations
    - Cancelled registrations
    - Payments received
    - Invoices awaiting approval

    Each section includes relevant details and links to review/edit items.

    Args:
        event: Event instance
        notifications: QuerySet of OrganizerNotificationQueue items to include

    Returns:
        str: HTML formatted email body
    """
    process = _digest_organize_notifications(notifications)

    # Start email body
    email_body = "<h2>" + _("Daily Summary") + f" - {event.name}" + "</h2>"
    email_body += "<p>" + _("Here's what happened in the last 24 hours:") + "</p>"

    currency_symbol = event.association.get_currency_symbol()

    if process["new_registrations"]:
        email_body = _digest_new_registrations(event, email_body, process["new_registrations"], currency_symbol)

    if process["updated_registrations"]:
        email_body = _digest_updated_registrations(event, email_body, process["updated_registrations"], currency_symbol)

    if process["cancelled_registrations"]:
        email_body = _digest_cancelled_registrations(event, email_body, process["cancelled_registrations"])

    if process["all_payments"]:
        email_body = _digest_payments(event, email_body, process["all_payments"], currency_symbol)

    if process["invoice_approvals"]:
        email_body = _digest_invoices(event, email_body, process["invoice_approvals"], currency_symbol)

    # Footer
    email_body += "<br/><hr/>"
    event_dashboard_url = get_url(f"/{event.slug}/manage/", event)
    email_body += "<p>" + _("Go to event dashboard") + f': <a href="{event_dashboard_url}">{event.title}</a></p>'

    return email_body


def _digest_organize_notifications(notifications: QuerySet) -> dict:
    """Organize notifications to be sent."""
    # Initialize lists for each notification type
    process = {
        "new_registrations": [],
        "updated_registrations": [],
        "cancelled_registrations": [],
        "all_payments": [],
        "invoice_approvals": [],
    }
    # Single loop through all notifications - group by type
    for notif in notifications:
        if notif.notification_type == NotificationType.REGISTRATION_NEW:
            process["new_registrations"].append(notif)
        elif notif.notification_type == NotificationType.REGISTRATION_UPDATE:
            process["updated_registrations"].append(notif)
        elif notif.notification_type == NotificationType.REGISTRATION_CANCEL:
            process["cancelled_registrations"].append(notif)
        elif notif.notification_type in [
            NotificationType.PAYMENT_MONEY,
            NotificationType.PAYMENT_CREDIT,
            NotificationType.PAYMENT_TOKEN,
        ]:
            process["all_payments"].append(notif)
        elif notif.notification_type == NotificationType.INVOICE_APPROVAL:
            process["invoice_approvals"].append(notif)

    return process


def _digest_invoices(event: Event, email_body: str, invoice_approvals: list, currency_symbol: str) -> str:
    """Generate email content for digest invoice to approve."""
    email_body += "<h3>" + _("Invoices Awaiting Approval") + f" {len(invoice_approvals)}" + "</h3>"
    email_body += "<ul>"
    invoice_ids = [notification.object_id for notification in invoice_approvals]
    for invoice in PaymentInvoice.objects.filter(pk__in=invoice_ids, association_id=event.association_id):
        email_body += f"<li><b>{invoice.member}</b> - {invoice.causal} - {invoice.amount:.2f} {currency_symbol}"
        approve_url = get_url(f"/{event.slug}/manage/invoices/confirm/{invoice.uuid}/", event)
        email_body += f' - <a href="{approve_url}">' + _("Approve") + "</a></li>"
    email_body += "</ul>"

    return email_body


def _digest_payments(event: Event, email_body: str, all_payments: list, currency_symbol: str) -> str:
    """Generate email content for digest payments received."""
    email_body += "<h3>" + _("Payments Received") + f" {len(all_payments)}" + "</h3>"
    email_body += "<ul>"

    payment_ids = [notification.object_id for notification in all_payments]
    for payment in AccountingItemPayment.objects.filter(pk__in=payment_ids, association_id=event.association_id):
        email_body += (
            f"<li><b>{payment.member}</b> - {payment.amount:.2f} {currency_symbol} - {payment.get_pay_displa()}</li>"
        )
    email_body += "</ul>"

    return email_body


def _digest_cancelled_registrations(event: Event, email_body: str, cancelled_registrations: list) -> str:
    """Generate email content for digest cancelled registrations."""
    email_body += "<h3>" + _("Cancelled Registrations") + f" {len(cancelled_registrations)}" + "</h3>"
    email_body += "<ul>"
    registration_ids = [notification.object_id for notification in cancelled_registrations]
    for registration in Registration.objects.filter(pk__in=registration_ids, run__event=event):
        ticket_name = registration.ticket.name if registration.ticket else _("No ticket")
        email_body += f"<li><b>{registration.member.username}</b> - {ticket_name}</li>"
    email_body += "</ul>"

    return email_body


def _digest_updated_registrations(
    event: Event, email_body: str, updated_registrations: list, currency_symbol: str
) -> str:
    """Generate email content for digest updated registrations."""
    email_body += "<h3>" + _("Updated Registrations") + f" {len(updated_registrations)}" + "</h3>"
    email_body += "<ul>"
    registration_ids = [notification.object_id for notification in updated_registrations]
    for registration in Registration.objects.filter(pk__in=registration_ids, run__event=event):
        ticket_name = registration.ticket.name if registration.ticket else _("No ticket")
        email_body += (
            f"<li><b>{registration.member.username}</b> - {ticket_name} - {registration.tot_iscr:.2f} {currency_symbol}"
        )
        edit_url = get_url(f"/{event.slug}/manage/registrations/edit/{registration.uuid}/", event)
        email_body += f' - <a href="{edit_url}">' + _("View/Edit") + "</a></li>"
    email_body += "</ul>"

    return email_body


def _digest_new_registrations(event: Event, email_body: str, new_registrations: list, currency_symbol: str) -> str:
    """Generate email content for digest updated registrations."""
    email_body += "<h3>" + _("New Registrations") + f" {len(new_registrations)}" + "</h3>"
    email_body += "<ul>"
    registration_ids = [notification.object_id for notification in new_registrations]
    for registration in Registration.objects.filter(pk__in=registration_ids, run__event=event):
        ticket_name = registration.ticket.name if registration.ticket else _("No ticket")
        email_body += (
            f"<li><b>{registration.member.username}</b> - {ticket_name} - {registration.tot_iscr:.2f} {currency_symbol}"
        )
        edit_url = get_url(f"/{event.slug}/manage/registrations/edit/{registration.uuid}/", event)
        email_body += f' - <a href="{edit_url}">' + _("View/Edit") + "</a></li>"

    email_body += "</ul>"
    return email_body
