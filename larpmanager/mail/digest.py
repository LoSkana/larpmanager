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
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_association_config, get_member_config
from larpmanager.mail.templates import (
    get_help_email,
    get_invoice_email,
    get_notify_refund_email,
    get_password_reminder_email,
    get_password_reset_url,
    get_pay_credit_email,
    get_pay_money_email,
    get_pay_token_email,
    get_registration_cancel_organizer_email,
    get_registration_new_organizer_email,
    get_registration_update_organizer_email,
    get_token_credit_name,
)
from larpmanager.models.access import get_association_executives
from larpmanager.models.accounting import AccountingItemPayment, PaymentInvoice
from larpmanager.models.association import Association, get_url, hdr
from larpmanager.models.member import Member, Membership, NotificationQueue, NotificationType
from larpmanager.models.miscellanea import HelpQuestion
from larpmanager.models.registration import Registration
from larpmanager.utils.larpmanager.tasks import my_send_mail
from larpmanager.utils.users.member import queue_executive_notification, queue_organizer_notification

if TYPE_CHECKING:
    from larpmanager.models.event import Event, Run

logger = logging.getLogger(__name__)


def my_send_digest_email(
    member: Member,
    run: Run,
    instance: Any,
    notification_type: Any,
) -> None:
    """Send notification email to a single organizer with digest mode support.

    Centralizes the logic for sending email to an organizer. Checks their personal
    digest preference:
    - If digest mode is enabled: queues notification for daily digest
    - If digest mode is disabled: sends immediate email

    This function standardizes email/notification handling across the codebase,
    replacing duplicate digest_mode checks. The appropriate email generator is
    selected based on the notification_type.

    Args:
        member: Member instance to notify
        run: Run instance for which to send the notification
        instance: Object of the notification (Registration, AccountingItemPayment, PaymentInvoice, etc.)
        notification_type: Type of notification for the queue (from NotificationType enum)

    Returns:
        None
    """
    should_queue = get_member_config(member.pk, "mail_orga_digest", default_value=False)

    # Check if this organizer has enabled digest mode for their notifications
    if should_queue:
        object_id = instance.id if instance else 0
        # Queue notification for daily digest summary for this specific organizer
        queue_organizer_notification(run=run, member=member, notification_type=notification_type, object_id=object_id)
    else:
        # Activate organizer's preferred language
        activate(member.language)

        # Determine which email generator to use based on notification type
        if notification_type == NotificationType.REGISTRATION_NEW:
            email_context = {"event": instance.run, "user": instance.member}
            subject, body = get_registration_new_organizer_email(instance, email_context)

        elif notification_type == NotificationType.REGISTRATION_UPDATE:
            email_context = {"event": instance.run, "user": instance.member}
            subject, body = get_registration_update_organizer_email(instance, email_context)

        elif notification_type == NotificationType.REGISTRATION_CANCEL:
            email_context = {"event": instance.run, "user": instance.member}
            subject, body = get_registration_cancel_organizer_email(instance, email_context)

        elif notification_type == NotificationType.PAYMENT_MONEY:
            currency_symbol = run.event.association.get_currency_symbol()
            subject, body = get_pay_money_email(currency_symbol, instance, run)
            subject += _(" for %(user)s") % {"user": instance.registration.member}

        elif notification_type == NotificationType.PAYMENT_CREDIT:
            tokens_name, credits_name = get_token_credit_name(instance.registration.run.event.association_id)
            subject, body = get_pay_credit_email(credits_name, instance, run)
            subject += _(" for %(user)s") % {"user": instance.registration.member}

        elif notification_type == NotificationType.PAYMENT_TOKEN:
            tokens_name, credits_name = get_token_credit_name(instance.registration.run.event.association_id)
            subject, body = get_pay_token_email(instance, run, tokens_name)
            subject += _(" for %(user)s") % {"user": instance.registration.member}

        elif notification_type == NotificationType.INVOICE_APPROVAL:
            subject, body = get_invoice_email(instance)

        else:
            # This should never happen, but just in case
            msg = f"Unknown notification type: {notification_type}"
            raise ValueError(msg)

        # Send the email to this organizer
        my_send_mail(subject, body, member, instance)


def _get_association_notification_generator(notification_type: str) -> callable:
    """Get notification generator for association-level notifications."""
    generators = {
        NotificationType.HELP_QUESTION: get_help_email,
        NotificationType.PASSWORD_REMINDER: get_password_reminder_email,
        NotificationType.REFUND_REQUEST: get_notify_refund_email,
        NotificationType.INVOICE_APPROVAL_EXE: get_invoice_email,
    }

    notification_generator = generators.get(notification_type)
    if not notification_generator:
        msg = f"Unknown notification type: {notification_type}"
        raise ValueError(msg)

    return notification_generator


def my_send_digest_email_exe(
    member: Member | None,
    association: Association,
    instance: Any,
    notification_type: Any,
) -> None:
    """Send notification email to a single recipient with digest mode support.

    Based on personal digest preference (or association digest preference if member is None):
    - If digest mode is enabled: queues notification for daily digest
    - If digest mode is disabled: sends immediate email

    Args:
        member: Member instance to notify (association executive), or None for association main_mail
        association: Association instance for which to send the notification
        instance: Object of the notification (HelpQuestion, PaymentInvoice, etc.)
        notification_type: Type of notification for the queue (from NotificationType enum)

    Returns:
        None
    """
    # Get the notification generator for this type
    notification_generator = _get_association_notification_generator(notification_type)

    # Determine if we should queue the notification
    if member:
        # Check individual executive's digest preference
        should_queue = get_member_config(member.pk, "mail_orga_digest", default_value=False)
    else:
        # Check association-level digest preference for main_mail
        should_queue = get_association_config(association.pk, "mail_exe_digest", default_value=False)

    if should_queue:
        object_id = instance.id if instance and hasattr(instance, "id") else 0
        # Queue notification for daily digest summary
        queue_executive_notification(
            association=association, member=member, notification_type=notification_type, object_id=object_id
        )
    # Send immediate email
    elif member:
        # Send to individual executive
        activate(member.language)
        subject, body = notification_generator(instance)
        my_send_mail(subject, body, member, instance)
    else:
        # Send to main_mail
        activate(get_exec_language(association))
        subject, body = notification_generator(instance)
        my_send_mail(subject, body, association.main_mail, instance)


def send_daily_organizer_summaries() -> None:
    """Send daily summary emails to organizers and executives with queued notifications.

    For each member with unsent notifications, collects all their notifications,
    groups them by event (for event organizers) or association (for executives),
    generates summary emails, and marks notifications as sent.

    Handles both event-level notifications (sent to event organizers) and
    association-level notifications (sent to association executives or main_mail).
    """
    # Get all members with unsent notifications
    members_with_notifications = Member.objects.filter(organizernotificationqueue__sent=False).distinct()

    for member in members_with_notifications:
        _daily_member_summaries(member)

    # Handle association notifications (member is None, sent to association.main_mail)
    associations_with_main_mail_notifications = Association.objects.filter(
        organizernotificationqueue__sent=False, organizernotificationqueue__member__isnull=True
    ).distinct()

    for association in associations_with_main_mail_notifications:
        # Collect all unsent notifications for this association's main_mail
        association_notifications = NotificationQueue.objects.filter(
            association=association, member__isnull=True, sent=False
        ).select_related("association")

        if not association_notifications.exists():
            continue

        logger.info(
            "Sending daily summary to %s main_mail with %d notifications",
            association.name,
            association_notifications.count(),
        )

        # Activate association's executive language
        activate(get_exec_language(association))

        # Generate summary email content for this association
        email_content = generate_association_summary_email(association, list(association_notifications))

        # Build email subject
        email_subject = f"[{association.name}] " + _("Daily Summary")

        # Send the email to main_mail
        my_send_mail(
            email_subject,
            email_content,
            association.main_mail,
            association,
        )

        # Mark all notifications for this association's main_mail as sent
        association_notifications.update(sent=True, sent_at=timezone.now())
        logger.info("Daily summary sent to %s main_mail", association.name)


def _daily_member_summaries(member: Member) -> None:
    """Send a summary of all unsent notifications for a member."""
    # Collect all unsent notifications for this member
    member_notifications = NotificationQueue.objects.filter(member=member, sent=False).select_related(
        "run__event", "run__event__association", "association"
    )

    if not member_notifications.exists():
        return

    # Separate event-level and association-level notifications
    events_notifications = {}
    associations_notifications = {}
    for notification in member_notifications:
        if notification.run:
            # Event-level notification
            event = notification.run.event
            if event not in events_notifications:
                events_notifications[event] = []
            events_notifications[event].append(notification)

        elif notification.association:
            # Association-level notification
            association = notification.association
            if association not in associations_notifications:
                associations_notifications[association] = []
            associations_notifications[association].append(notification)

    logger.info(
        "Sending daily summary to %s for %d events and %d associations with %d total notifications",
        str(member),
        len(events_notifications),
        len(associations_notifications),
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

    # Send a summary email for each association this member has notifications for
    for association, notifications in associations_notifications.items():
        # Activate member's preferred language
        activate(member.language)

        # Generate summary email content for this association
        email_content = generate_association_summary_email(association, notifications)

        # Build email subject
        email_subject = f"[{association.name}] " + _("Daily Summary")

        # Send the email
        my_send_mail(
            email_subject,
            email_content,
            member,
            association,
        )

    # Mark all notifications for this member as sent
    member_notifications.update(sent=True, sent_at=timezone.now())
    logger.info("Daily summary sent to %s", str(member))


def generate_summary_email(event: Event, notifications: list) -> str:
    """Generate HTML email content for daily organizer summary.

    Args:
        event: Event instance
        notifications: List of notifications to include

    Returns:
        str: HTML formatted email body
    """
    # Group notifications by type
    grouped_notifications = _digest_organize_notifications(notifications)

    # Start email body
    email_body = "<h2>" + _("Daily Summary") + f" - {event.name}" + "</h2>"
    email_body += "<p>" + _("Here's what happened in the last 24 hours:") + "</p>"

    currency_symbol = event.association.get_currency_symbol()

    # Map group keys to their handler functions (in display order)
    notification_handlers = [
        ("new_registrations", _digest_new_registrations),
        ("updated_registrations", _digest_updated_registrations),
        ("cancelled_registrations", _digest_cancelled_registrations),
        ("all_payments", _digest_payments),
        ("invoice_approvals", _digest_invoices),
    ]

    # Process each notification group using its handler
    for group_key, handler_func in notification_handlers:
        if group_key in grouped_notifications:
            email_body = handler_func(event, email_body, grouped_notifications[group_key], currency_symbol)

    # Footer
    email_body += "<br/><hr/>"
    event_dashboard_url = get_url(reverse("manage", kwargs={"event_slug": event.slug}), event)
    email_body += "<p>" + _("Go to event dashboard") + f': <a href="{event_dashboard_url}">{event.name}</a></p>'

    return email_body


def _digest_organize_notifications(notifications: list) -> dict:
    """Organize notifications to be sent."""
    # Map notification types to their respective dictionary keys
    type_to_key = {
        NotificationType.REGISTRATION_NEW: "new_registrations",
        NotificationType.REGISTRATION_UPDATE: "updated_registrations",
        NotificationType.REGISTRATION_CANCEL: "cancelled_registrations",
        NotificationType.PAYMENT_MONEY: "all_payments",
        NotificationType.PAYMENT_CREDIT: "all_payments",
        NotificationType.PAYMENT_TOKEN: "all_payments",
        NotificationType.INVOICE_APPROVAL: "invoice_approvals",
    }

    # Group notifications by type using the mapping
    process = {}
    for notification in notifications:
        key = type_to_key.get(notification.notification_type)
        if not key:
            continue
        if key not in process:
            process[key] = []
        process[key].append(notification)

    return process


def _digest_invoices(event: Event, email_body: str, invoice_approvals: list, currency_symbol: str) -> str:
    """Generate email content for digest invoice to approve."""
    email_body += "<h3>" + _("Invoices Awaiting Approval") + f" {len(invoice_approvals)}" + "</h3>"
    email_body += "<ul>"
    invoice_ids = [notification.object_id for notification in invoice_approvals]
    for invoice in PaymentInvoice.objects.filter(pk__in=invoice_ids, association_id=event.association_id):
        email_body += f"<li><b>{invoice.member}</b> - {invoice.causal} - {invoice.mc_gross:.2f} {currency_symbol}"
        approve_url = get_url(
            reverse("orga_invoices_confirm", kwargs={"event_slug": event.slug, "invoice_uuid": invoice.uuid}), event
        )
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
            f"<li><b>{payment.member}</b> - {payment.value:.2f} {currency_symbol} - {payment.get_pay_display()}</li>"
        )
    email_body += "</ul>"

    return email_body


def _digest_cancelled_registrations(
    event: Event,
    email_body: str,
    cancelled_registrations: list,
    currency_symbol: str,  # noqa: ARG001
) -> str:
    """Generate email content for digest cancelled registrations."""
    email_body += "<h3>" + _("Cancelled Registrations") + f" {len(cancelled_registrations)}" + "</h3>"
    email_body += "<ul>"
    registration_ids = [notification.object_id for notification in cancelled_registrations]
    for registration in Registration.objects.filter(pk__in=registration_ids, run__event=event):
        ticket_name = registration.ticket.name if registration.ticket else _("No ticket")
        email_body += f"<li><b>{registration.member}</b> - {ticket_name}</li>"
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
            f"<li><b>{registration.member}</b> - {ticket_name} - {registration.tot_iscr:.2f} {currency_symbol}"
        )
        edit_url = get_url(
            reverse(
                "orga_registrations_edit", kwargs={"event_slug": event.slug, "registration_uuid": registration.uuid}
            ),
            event,
        )
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
            f"<li><b>{registration.member}</b> - {ticket_name} - {registration.tot_iscr:.2f} {currency_symbol}"
        )
        edit_url = get_url(
            reverse(
                "orga_registrations_edit", kwargs={"event_slug": event.slug, "registration_uuid": registration.uuid}
            ),
            event,
        )
        email_body += f' - <a href="{edit_url}">' + _("View/Edit") + "</a></li>"

    email_body += "</ul>"
    return email_body


def generate_association_summary_email(association: Association, notifications: list) -> str:
    """Generate HTML email content for daily association executive summary.

    Args:
        association: Association instance
        notifications: List of notifications to include

    Returns:
        str: HTML formatted email body
    """
    # Start email body
    email_body = "<h2>" + _("Daily Summary") + f" - {association.name}" + "</h2>"
    email_body += "<p>" + _("Here's what happened in the last 24 hours:") + "</p>"

    # Map notification types to their handler functions
    notification_handlers = {
        NotificationType.HELP_QUESTION: digest_help_questions,
        NotificationType.INVOICE_APPROVAL_EXE: digest_invoice_approvals,
        NotificationType.REFUND_REQUEST: digest_refund_request,
        NotificationType.PASSWORD_REMINDER: digest_password_reminders,
    }

    # Group notifications by type
    grouped_notifications = {}
    for notification in notifications:
        notification_type = notification.notification_type
        if notification_type in notification_handlers:
            if notification_type not in grouped_notifications:
                grouped_notifications[notification_type] = []
            grouped_notifications[notification_type].append(notification)

    # Process each notification type using its handler
    for notification_type, handler_func in notification_handlers.items():
        if notification_type in grouped_notifications:
            email_body += handler_func(association, grouped_notifications[notification_type])

    # Footer
    email_body += "<br/><hr/>"
    assoc_url = get_url(reverse("manage"), association)
    email_body += "<p>" + _("Go to organization dashboard") + f': <a href="{assoc_url}">{association.name}</a></p>'

    return email_body


def digest_password_reminders(association: Association, password_reminders: list[NotificationQueue]) -> str:
    """Handles password reminders digest summary emails."""
    content = "<h3>" + _("Password Reset Requests") + f" ({len(password_reminders)})" + "</h3>"
    content += "<ul>"
    membership_ids = [notification.object_id for notification in password_reminders]
    for membership in Membership.objects.filter(pk__in=membership_ids, association=association):
        content += (
            "<li>"
            + _("Password reset request url for")
            + f"""
             {membership.member}: <a href='{get_password_reset_url(membership)}'>link</a>
            </li>
            """
        )
    content += "</ul>"
    return content


def digest_refund_request(association: Association, refund_requests: list[NotificationQueue]) -> str:
    """Handles refund request digest summary emails."""
    content = "<h3>" + _("Refund Requests") + f" ({len(refund_requests)})" + "</h3>"
    content += "<ul>"
    invoice_ids = [notification.object_id for notification in refund_requests]
    for invoice in PaymentInvoice.objects.filter(pk__in=invoice_ids, association=association):
        content += f"<li><b>{invoice.member}</b> - {invoice.causal} - {invoice.mc_gross:.2f}"
        content += " - " + _("Refund requested")
        view_url = get_url(reverse("exe_invoices"), association)
        content += f' - <a href="{view_url}">' + _("View") + "</a></li>"
    content += "</ul>"
    return content


def digest_invoice_approvals(association: Association, invoice_approvals: list[NotificationQueue]) -> str:
    """Handles invoice approvals digest summary emails."""
    content = "<h3>" + _("Invoices Awaiting Approval") + f" ({len(invoice_approvals)})" + "</h3>"
    content += "<ul>"
    invoice_ids = [notification.object_id for notification in invoice_approvals]
    for invoice in PaymentInvoice.objects.filter(pk__in=invoice_ids, association=association):
        content += f"<li><b>{invoice.member}</b> - {invoice.causal} - {invoice.mc_gross:.2f}"
        content += " - " + _("Awaiting approval")
        approve_url = get_url(reverse("exe_invoices_confirm", kwargs={"invoice_uuid": invoice.uuid}), association)
        content += f' - <a href="{approve_url}">' + _("Approve") + "</a></li>"
    content += "</ul>"
    return content


def digest_help_questions(association: Association, help_questions: list[NotificationQueue]) -> str:
    """Handles help questions digest summary emails."""
    content = "<h3>" + _("Help Questions") + f" ({len(help_questions)})" + "</h3>"
    content += "<ul>"
    question_ids = [notification.object_id for notification in help_questions]
    for question in HelpQuestion.objects.filter(pk__in=question_ids, association=association):
        content += f"<li><b>{question.member}</b>: {question.text[:100]}..."
        help_url = get_url(reverse("exe_questions"), association)
        content += f' - <a href="{help_url}">' + _("View") + "</a></li>"
    content += "</ul>"
    return content


def get_exec_language(association: Association) -> str:
    """Determine the most common language among association executives.

    Analyzes the language preferences of all association executives and returns
    the most frequently used language code. If no executives are found or no
    language preferences are set, defaults to English.

    Args:
        association: Association instance containing executives to analyze

    Returns:
        str: The language code (e.g., 'en', 'it', 'fr') preferred by the majority
             of executives, or 'en' if no executives found or no preferences set

    """
    # Initialize dictionary to count language occurrences
    language_counts = {}

    # Iterate through all association executives
    for executive in get_association_executives(association):
        executive_language = executive.language

        # Count each language preference
        if executive_language not in language_counts:
            language_counts[executive_language] = 1
        else:
            language_counts[executive_language] += 1

    # Determine the most common language or default to English
    return max(language_counts, key=language_counts.get) if language_counts else "en"
