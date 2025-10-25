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
import re
import traceback
from functools import wraps
from typing import Any, Callable, Optional, Union

from background_task import background
from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils import timezone

from larpmanager.cache.config import get_event_config
from larpmanager.cache.text_fields import remove_html_tags
from larpmanager.models.association import Association, AssocTextType, get_url
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member
from larpmanager.models.miscellanea import Email
from larpmanager.utils.text import get_assoc_text

logger = logging.getLogger(__name__)

INTERNAL_KWARGS = {"schedule", "repeat", "repeat_until", "remove_existing_tasks"}


def background_auto(schedule=0, **background_kwargs):
    """Decorator to conditionally run functions as background tasks.

    Creates a decorator that can run functions either synchronously
    (if AUTO_BACKGROUND_TASKS is True) or as background tasks.

    Args:
        schedule (int): Seconds to delay before execution
        **background_kwargs: Additional arguments for background task

    Returns:
        function: Decorator function
    """

    def decorator(original_function: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator that conditionally executes a function as a background task.

        Args:
            original_function: The function to be decorated for potential background execution.

        Returns:
            A wrapper function that either executes the original function directly
            or schedules it as a background task based on configuration.
        """
        # Create background task from the original function
        background_task = background(schedule=schedule, **background_kwargs)(original_function)

        @wraps(original_function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Execute function directly or schedule as background task based on settings."""
            # Check if auto background tasks are enabled in settings
            if getattr(conf_settings, "AUTO_BACKGROUND_TASKS", False):
                # Filter out internal kwargs that shouldn't be passed to the function
                filtered_kwargs = {key: value for key, value in kwargs.items() if key not in INTERNAL_KWARGS}
                # Execute function directly in foreground
                return original_function(*args, **filtered_kwargs)
            else:
                # Schedule function as background task
                return background_task(*args, **kwargs)

        # Attach task references to wrapper for external access
        wrapper.task = background_task
        wrapper.task_function = original_function
        return wrapper

    return decorator


# MAIL


def mail_error(subj, body, e=None):
    """Handle email sending errors and notify administrators.

    Args:
        subj (str): Email subject that failed
        body (str): Email body that failed
        e (Exception, optional): Exception that caused the failure

    Side effects:
        Prints error details and sends error notification to admins
    """
    logger.error(f"Mail error: {e}")
    logger.error(f"Subject: {subj}")
    logger.error(f"Body: {body}")
    if e:
        body = f"{traceback.format_exc()} <br /><br /> {subj} <br /><br /> {body}"
    else:
        body = f"{subj} <br /><br /> {body}"
    subj = "[LarpManager] Mail error"
    for _name, email in conf_settings.ADMINS:
        my_send_simple_mail(subj, body, email)


@background_auto()
def send_mail_exec(
    players: str,
    subj: str,
    body: str,
    assoc_id: int | None = None,
    run_id: int | None = None,
    reply_to: str | None = None,
) -> None:
    """Send bulk emails to multiple recipients with staggered delivery.

    Sends emails to a comma-separated list of recipients with automatic delays
    between sends to prevent spam filtering. Emails are prefixed with the
    organization/run name and scheduled with 10-second intervals.

    Args:
        players: Comma-separated list of email addresses to send to
        subj: Email subject line (will be prefixed with org/run name)
        body: Email body content in HTML or plain text
        assoc_id: Association ID for determining sender context
        run_id: Run ID for determining sender context (alternative to assoc_id)
        reply_to: Custom reply-to email address

    Returns:
        None

    Side Effects:
        - Schedules individual emails with 10-second delays via background tasks
        - Sends notification to admins about bulk email operation
        - Logs warning if neither assoc_id nor run_id are provided
    """
    seen_emails = {}

    sender_context = None
    # Determine sender context (Association or Run object, or LM )
    if assoc_id:
        sender_context = Association.objects.filter(pk=assoc_id).first()
    elif run_id:
        sender_context = Run.objects.filter(pk=run_id).first()

    if sender_context:
        # Add organization/run prefix to subject line
        subj = f"[{sender_context}] {subj}"

    # Parse comma-separated email list
    recipients = players.split(",")

    # Notify administrators about bulk email operation
    if sender_context:
        notify_admins(f"Sending {len(recipients)} - [{sender_context}]", f"{subj}")

    email_count = 0
    # Process each recipient with deduplication
    for email in recipients:
        if not email:
            continue
        if email in seen_emails:
            continue
        email_count += 1
        # Schedule email with 10-second delay per recipient to prevent spam filtering
        # noinspection PyUnboundLocalVariable
        my_send_mail(subj, body, email.strip(), sender_context, reply_to, schedule=email_count * 10)
        seen_emails[email] = 1


@background_auto(queue="mail")
def my_send_mail_bkg(email_pk):
    """Background task to send a queued email.

    Args:
        email_pk (int): Primary key of Email model instance to send

    Side effects:
        Sends the email and marks it as sent in database
    """
    try:
        email = Email.objects.get(pk=email_pk)
    except ObjectDoesNotExist:
        return

    if email.sent:
        logger.info("Email already sent!")
        return

    my_send_simple_mail(email.subj, email.body, email.recipient, email.assoc_id, email.run_id, email.reply_to)

    email.sent = timezone.now()
    email.save()


def clean_sender(sender_name):
    """Clean sender name for email headers by removing special characters.

    Args:
        sender_name (str): Original sender name

    Returns:
        str: Sanitized sender name safe for email headers
    """
    sender_name = sender_name.replace(":", " ")
    sender_name = sender_name.split(",")[0]
    sender_name = re.sub(r"[^a-zA-Z0-9\s\-\']", "", sender_name)
    sender_name = re.sub(r"\s+", " ", sender_name).strip()
    return sender_name


def my_send_simple_mail(
    subj: str,
    body: str,
    m_email: str,
    assoc_id: int | None = None,
    run_id: int | None = None,
    reply_to: str | None = None,
) -> None:
    """Send email with association/event-specific configuration.

    Handles custom SMTP settings, sender addresses, BCC lists, and email formatting
    based on association and event configuration. Prioritizes event-level settings
    over association-level settings when both are available.

    Args:
        subj: Email subject line
        body: Email body content (HTML format)
        m_email: Recipient email address
        assoc_id: Association ID for custom SMTP settings and sender configuration
        run_id: Run ID for event-specific SMTP settings (overrides association settings)
        reply_to: Custom Reply-To email address header

    Raises:
        Exception: Re-raises email sending exceptions after logging error details

    Note:
        Sends email using configured SMTP settings or default connection.
        Logs email details in debug mode for troubleshooting.
    """
    # Initialize email headers and BCC list
    email_headers = {}
    bcc_recipients = []

    # Initialize with default LarpManager sender configuration
    smtp_connection = None
    sender_email = "info@larpmanager.com"
    sender = f"LarpManager <{sender_email}>"
    event_settings_applied = False

    cache_context = {}

    try:
        # Apply event-level configuration if run_id is provided and SMTP is configured
        if run_id:
            run = Run.objects.get(pk=run_id)
            event = run.event

            # Check if event has custom SMTP configuration
            event_smtp_host_user = get_event_config(
                event.id, "mail_server_host_user", "", ctx=cache_context, bypass_cache=True
            )

            # Only apply event settings if SMTP host user is configured
            if event_smtp_host_user:
                sender_email = event_smtp_host_user
                sender = f"{clean_sender(event.name)} <{sender_email}>"

                # Create custom SMTP connection for event
                smtp_connection = get_connection(
                    host=get_event_config(event.id, "mail_server_host", "", ctx=cache_context, bypass_cache=True),
                    port=get_event_config(event.id, "mail_server_port", "", ctx=cache_context, bypass_cache=True),
                    username=get_event_config(
                        event.id, "mail_server_host_user", "", ctx=cache_context, bypass_cache=True
                    ),
                    password=get_event_config(
                        event.id, "mail_server_host_password", "", ctx=cache_context, bypass_cache=True
                    ),
                    use_tls=get_event_config(
                        event.id, "mail_server_use_tls", False, ctx=cache_context, bypass_cache=True
                    ),
                )
                event_settings_applied = True

        # Apply association-level configuration if assoc_id is provided
        if assoc_id:
            association = Association.objects.get(pk=assoc_id)

            # Add association main email to BCC if configured
            if association.get_config("mail_cc", False, bypass_cache=True) and association.main_mail:
                bcc_recipients.append(association.main_mail)

            # Apply custom SMTP settings if configured (only if event settings not already applied)
            association_smtp_host_user = association.get_config("mail_server_host_user", "", bypass_cache=True)

            # Check if association has custom SMTP and event settings aren't active
            if association_smtp_host_user:
                if not event_settings_applied:
                    sender_email = association_smtp_host_user
                    sender = f"{clean_sender(association.name)} <{sender_email}>"

                    # Create custom SMTP connection for association
                    smtp_connection = get_connection(
                        host=association.get_config("mail_server_host", "", bypass_cache=True),
                        port=association.get_config("mail_server_port", "", bypass_cache=True),
                        username=association.get_config("mail_server_host_user", "", bypass_cache=True),
                        password=association.get_config("mail_server_host_password", "", bypass_cache=True),
                        use_tls=association.get_config("mail_server_use_tls", False, bypass_cache=True),
                    )
            # Use standard LarpManager subdomain sender if no custom SMTP configured
            elif not event_settings_applied:
                sender_email = f"{association.slug}@larpmanager.com"
                sender = f"{clean_sender(association.name)} <{sender_email}>"

        # Fall back to default SMTP connection if no custom connection configured
        if not smtp_connection:
            smtp_connection = get_connection()

        # Set custom Reply-To header if provided
        if reply_to:
            email_headers["Reply-To"] = reply_to

        # Add RFC-compliant unsubscribe header
        email_headers["List-Unsubscribe"] = f"<mailto:{sender_email}>"

        # Store HTML body for multipart email
        body_html = body

        # Build multipart email with both plain text and HTML versions
        email_message = EmailMultiAlternatives(
            subj,
            remove_html_tags(body),
            sender,
            [m_email],
            bcc=bcc_recipients,
            headers=email_headers,
            connection=smtp_connection,
        )

        # Attach HTML alternative to the email
        email_message.attach_alternative(body_html, "text/html")

        # Send the email
        email_message.send()

        # Log email details in debug mode for troubleshooting
        if conf_settings.DEBUG:
            logger.info(f"Sending email to: {m_email}")
            logger.info(f"Subject: {subj}")
            logger.debug(f"Body: {body}")

    except Exception as email_sending_exception:
        # Log the error and re-raise for caller handling
        mail_error(subj, body, email_sending_exception)
        raise email_sending_exception


def add_unsubscribe_body(assoc):
    """Add unsubscribe footer to email body.

    Args:
        assoc: Association instance for unsubscribe URL

    Returns:
        str: HTML footer with unsubscribe link
    """
    html_footer = "<br /><br />-<br />"
    html_footer += f"<a href='{get_url('unsubscribe', assoc)}'>Unsubscribe</a>"
    return html_footer


def my_send_mail(
    subject: str,
    body: str,
    recipient: Union[str, Member],
    context_object: Optional[Union[Run, Event, Association, Any]] = None,
    reply_to: Optional[str] = None,
    schedule: int = 0,
) -> None:
    """Queue email for sending with context-aware formatting.

    Main email sending function that adds signatures, unsubscribe links,
    and queues email for background delivery.

    Args:
        subject: Email subject line
        body: Email body content (HTML or plain text)
        recipient: Email recipient address or Member instance
        context_object: Context object for extracting association/run information.
             Supports Run, Event, Association, or objects with run_id/assoc_id/event_id
        reply_to: Custom reply-to email address
        schedule: Delay in seconds before sending email

    Returns:
        None

    Side Effects:
        - Creates Email record in database
        - Schedules background task for email delivery
        - Modifies body with signature and unsubscribe link
    """
    # Clean up duplicate spaces in subject line
    subject = subject.replace("  ", " ")

    # Initialize context variables for database relationships
    run_id = None
    association_id = None

    # Extract context information from the provided object
    if context_object:
        # Handle direct model instances
        if isinstance(context_object, Run):
            run_id = context_object.id  # type: ignore[attr-defined]
            association_id = context_object.event.assoc_id  # type: ignore[attr-defined]
        elif isinstance(context_object, Event):
            association_id = context_object.assoc_id  # type: ignore[attr-defined]
        elif isinstance(context_object, Association):
            association_id = context_object.id  # type: ignore[attr-defined]
        # Handle objects with foreign key relationships
        elif hasattr(context_object, "run_id") and context_object.run_id:
            run_id = context_object.run_id
            association_id = context_object.run.event.assoc_id
        elif hasattr(context_object, "assoc_id") and context_object.assoc_id:
            association_id = context_object.assoc_id
        elif hasattr(context_object, "event_id") and context_object.event_id:
            association_id = context_object.event.assoc_id

        # Add organization signature if available
        if association_id:
            signature = get_assoc_text(association_id, AssocTextType.SIGNATURE)
            if signature:
                body += signature

    # Append unsubscribe footer based on context
    body += add_unsubscribe_body(context_object)

    # Convert Member instance to email string if needed
    if isinstance(recipient, Member):
        recipient = recipient.email

    # Ensure string types for database storage
    subject_string = str(subject)
    body_string = str(body)

    # Create email record for tracking and delivery
    email = Email.objects.create(
        assoc_id=association_id,
        run_id=run_id,
        recipient=recipient,
        subj=subject_string,
        body=body_string,
        reply_to=reply_to,
    )

    # Queue email for background processing
    my_send_mail_bkg(email.pk, schedule=schedule)


def notify_admins(subject, message_text, exception=None):
    """Send notification email to system administrators.

    Args:
        subject (str): Notification subject
        message_text (str): Notification message
        exception (Exception, optional): Exception to include in notification

    Side effects:
        Sends notification emails to all configured ADMINS
    """
    if exception:
        traceback_text = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        message_text += "\n" + traceback_text
    for _name, email in conf_settings.ADMINS:
        my_send_mail(subject, message_text, email)
