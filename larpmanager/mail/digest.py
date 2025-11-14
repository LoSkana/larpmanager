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
from typing import TYPE_CHECKING

from django.utils import timezone
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_event_config
from larpmanager.models.access import get_event_organizers
from larpmanager.models.association import get_url, hdr
from larpmanager.models.notification import OrganizerNotificationQueue
from larpmanager.utils.tasks import my_send_mail

if TYPE_CHECKING:
    from larpmanager.models.event import Event
    from larpmanager.models.member import Member
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)


def send_daily_organizer_summaries() -> None:
    """
    Send daily summary emails to organizers for all events with queued notifications.

    For each event with digest mode enabled and unsent notifications, collects all
    notifications from the queue, generates a summary email, sends it to event
    organizers, and marks notifications as sent.

    Only sends emails if:
    - Event has mail_orga_digest config enabled
    - There are unsent notifications for the event
    """
    from larpmanager.models.event import Event

    # Get all events with unsent notifications
    events_with_notifications = (
        Event.objects.filter(organizernotificationqueue__sent=False)
        .distinct()
        .select_related("association")
    )

    for event in events_with_notifications:
        # Only send if digest mode is enabled for this event
        if not get_event_config(event.pk, "mail_orga_digest", False):
            logger.info(
                f"Skipping event {event.slug} - digest mode not enabled"
            )
            continue

        # Collect all unsent notifications for this event
        notifications = OrganizerNotificationQueue.objects.filter(
            event=event, sent=False
        ).select_related("registration", "payment", "invoice")

        if not notifications.exists():
            continue

        logger.info(
            f"Sending daily summary for event {event.slug} with {notifications.count()} notifications"
        )

        # Generate summary email content
        email_content = generate_summary_email(event, notifications)

        # Send to all event organizers
        organizers = get_event_organizers(event)
        for organizer in organizers:
            activate(organizer.language)
            email_subject = hdr(event) + _("Daily Summary - %(event)s") % {
                "event": event.title
            }

            my_send_mail(
                email_subject,
                email_content,
                organizer,
                event.current_run,
            )

        # Mark all notifications as sent
        notifications.update(sent=True, sent_at=timezone.now())
        logger.info(f"Daily summary sent for event {event.slug}")


def generate_summary_email(
    event: "Event", notifications: "QuerySet[OrganizerNotificationQueue]"
) -> str:
    """
    Generate HTML email content for daily organizer summary.

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
    # Group notifications by type
    new_registrations = notifications.filter(
        notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_NEW
    )
    updated_registrations = notifications.filter(
        notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_UPDATE
    )
    cancelled_registrations = notifications.filter(
        notification_type=OrganizerNotificationQueue.NotificationType.REGISTRATION_CANCEL
    )
    money_payments = notifications.filter(
        notification_type=OrganizerNotificationQueue.NotificationType.PAYMENT_MONEY
    )
    credit_payments = notifications.filter(
        notification_type=OrganizerNotificationQueue.NotificationType.PAYMENT_CREDIT
    )
    token_payments = notifications.filter(
        notification_type=OrganizerNotificationQueue.NotificationType.PAYMENT_TOKEN
    )
    invoice_approvals = notifications.filter(
        notification_type=OrganizerNotificationQueue.NotificationType.INVOICE_APPROVAL
    )

    # All payment types combined
    all_payments = list(money_payments) + list(credit_payments) + list(token_payments)

    # Start email body
    email_body = (
        "<h2>"
        + str(_("Daily Summary - %(event)s") % {"event": event.title})
        + "</h2>"
    )
    email_body += "<p>" + str(_("Here's what happened in the last 24 hours:")) + "</p>"

    currency_symbol = event.association.get_currency_symbol()

    # New Registrations Section
    if new_registrations.exists():
        email_body += (
            "<h3>"
            + str(
                _("New Registrations (%(count)d)")
                % {"count": new_registrations.count()}
            )
            + "</h3>"
        )
        email_body += "<ul>"
        for notif in new_registrations:
            reg = notif.registration
            if reg:
                ticket_name = reg.ticket.name if reg.ticket else _("No ticket")
                email_body += f"<li><b>{reg.member.username}</b> - {ticket_name} - {reg.tot_iscr:.2f} {currency_symbol}"

                # Add link to edit registration
                edit_url = get_url(
                    f"/{event.slug}/manage/registrations/edit/{reg.pk}/", event
                )
                email_body += (
                    f' - <a href="{edit_url}">' + str(_("View/Edit")) + "</a>"
                )
                email_body += "</li>"
        email_body += "</ul>"

        # Link to registrations list
        list_url = get_url(f"/{event.slug}/manage/registrations/", event)
        email_body += (
            f'<p><a href="{list_url}" style="display:inline-block; padding:10px 20px; background-color:#007bff; color:white; text-decoration:none; border-radius:5px;">'
            + str(_("View All Registrations"))
            + "</a></p>"
        )

    # Updated Registrations Section
    if updated_registrations.exists():
        email_body += (
            "<h3>"
            + str(
                _("Updated Registrations (%(count)d)")
                % {"count": updated_registrations.count()}
            )
            + "</h3>"
        )
        email_body += "<ul>"
        for notif in updated_registrations:
            reg = notif.registration
            if reg:
                ticket_name = reg.ticket.name if reg.ticket else _("No ticket")
                email_body += f"<li><b>{reg.member.username}</b> - {ticket_name} - {reg.tot_iscr:.2f} {currency_symbol}"

                # Add link to edit registration
                edit_url = get_url(
                    f"/{event.slug}/manage/registrations/edit/{reg.pk}/", event
                )
                email_body += (
                    f' - <a href="{edit_url}">' + str(_("View/Edit")) + "</a>"
                )
                email_body += "</li>"
        email_body += "</ul>"

        # Link to registrations list
        list_url = get_url(f"/{event.slug}/manage/registrations/", event)
        email_body += (
            f'<p><a href="{list_url}" style="display:inline-block; padding:10px 20px; background-color:#007bff; color:white; text-decoration:none; border-radius:5px;">'
            + str(_("View All Registrations"))
            + "</a></p>"
        )

    # Cancelled Registrations Section
    if cancelled_registrations.exists():
        email_body += (
            "<h3>"
            + str(
                _("Cancelled Registrations (%(count)d)")
                % {"count": cancelled_registrations.count()}
            )
            + "</h3>"
        )
        email_body += "<ul>"
        for notif in cancelled_registrations:
            reg = notif.registration
            if reg:
                member_name = notif.details.get("member_name", reg.member.username if reg.member else _("Unknown"))
                ticket_name = notif.details.get("ticket_name", _("Unknown ticket"))
                email_body += f"<li><b>{member_name}</b> - {ticket_name}</li>"
        email_body += "</ul>"

        # Link to cancellations list
        cancellations_url = get_url(f"/{event.slug}/manage/cancellations/", event)
        email_body += (
            f'<p><a href="{cancellations_url}" style="display:inline-block; padding:10px 20px; background-color:#007bff; color:white; text-decoration:none; border-radius:5px;">'
            + str(_("View Cancellations"))
            + "</a></p>"
        )

    # Payments Section
    if all_payments:
        email_body += (
            "<h3>"
            + str(_("Payments Received (%(count)d)") % {"count": len(all_payments)})
            + "</h3>"
        )
        email_body += "<ul>"
        for notif in all_payments:
            payment = notif.payment
            if payment:
                amount = payment.amount if hasattr(payment, "amount") else 0
                payment_type = notif.get_notification_type_display()

                # Get member name from related registration or details
                member_name = _("Unknown")
                if payment.item and payment.item.registration:
                    member_name = payment.item.registration.member.username
                elif "member_name" in notif.details:
                    member_name = notif.details["member_name"]

                email_body += f"<li><b>{member_name}</b> - {amount:.2f} {currency_symbol} - {payment_type}</li>"
        email_body += "</ul>"

        # Link to payments list
        payments_url = get_url(f"/{event.slug}/manage/payments/", event)
        email_body += (
            f'<p><a href="{payments_url}" style="display:inline-block; padding:10px 20px; background-color:#007bff; color:white; text-decoration:none; border-radius:5px;">'
            + str(_("View All Payments"))
            + "</a></p>"
        )

    # Invoice Approvals Section
    if invoice_approvals.exists():
        email_body += (
            "<h3>"
            + str(
                _("Invoices Awaiting Approval (%(count)d)")
                % {"count": invoice_approvals.count()}
            )
            + "</h3>"
        )
        email_body += "<ul>"
        for notif in invoice_approvals:
            invoice = notif.invoice
            if invoice:
                # Get invoice details from stored details or model
                invoice_number = notif.details.get("invoice_number", invoice.pk)
                amount = notif.details.get("amount", getattr(invoice, "amount", 0))
                member_name = notif.details.get(
                    "member_name",
                    invoice.registration.member.username
                    if hasattr(invoice, "registration") and invoice.registration
                    else _("Unknown"),
                )

                email_body += f"<li><b>{member_name}</b> - {str(_('Invoice'))} #{invoice_number} - {amount:.2f} {currency_symbol}"

                # Add link to approve invoice
                approve_url = get_url(
                    f"/{event.slug}/manage/invoices/confirm/{invoice.pk}/", event
                )
                email_body += (
                    f' - <a href="{approve_url}" style="display:inline-block; padding:5px 15px; background-color:#28a745; color:white; text-decoration:none; border-radius:3px;">'
                    + str(_("Approve"))
                    + "</a>"
                )
                email_body += "</li>"
        email_body += "</ul>"

        # Link to invoices list
        invoices_url = get_url(f"/{event.slug}/manage/invoices/", event)
        email_body += (
            f'<p><a href="{invoices_url}" style="display:inline-block; padding:10px 20px; background-color:#007bff; color:white; text-decoration:none; border-radius:5px;">'
            + str(_("View All Invoices"))
            + "</a></p>"
        )

    # Footer
    email_body += "<br/><hr/>"
    event_dashboard_url = get_url(f"/{event.slug}/manage/", event)
    email_body += (
        "<p>"
        + str(_("Go to event dashboard"))
        + f': <a href="{event_dashboard_url}">{event.title}</a></p>'
    )

    return email_body
