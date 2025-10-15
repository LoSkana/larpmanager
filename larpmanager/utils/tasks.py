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
from typing import Any, Optional, Union

from background_task import background
from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

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

    def decorator(func):
        task = background(schedule=schedule, **background_kwargs)(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            if getattr(conf_settings, "AUTO_BACKGROUND_TASKS", False):
                clean_kwargs = {k: v for k, v in kwargs.items() if k not in INTERNAL_KWARGS}
                return func(*args, **clean_kwargs)
            else:
                return task(*args, **kwargs)

        wrapper.task = task
        wrapper.task_function = func
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
def send_mail_exec(players, subj, body, assoc_id=None, run_id=None, reply_to=None):
    """Send bulk emails to multiple recipients with staggered delivery.

    Args:
        players (str): Comma-separated list of email addresses
        subj (str): Email subject
        body (str): Email body content
        assoc_id (int, optional): Association ID for context
        run_id (int, optional): Run ID for context
        reply_to (str, optional): Reply-to email address

    Side effects:
        Schedules individual emails with delays to prevent spam issues
    """
    aux = {}

    if assoc_id:
        obj = Association.objects.filter(pk=assoc_id).first()
    elif run_id:
        obj = Run.objects.filter(pk=run_id).first()
    else:
        logger.warning(f"Object not found! assoc_id: {assoc_id}, run_id: {run_id}")
        return

    subj = f"[{obj}] {subj}"

    recipients = players.split(",")

    notify_admins(f"Sending {len(recipients)} - [{obj}]", f"{subj}")

    cnt = 0
    for email in recipients:
        if not email:
            continue
        if email in aux:
            continue
        cnt += 1
        # noinspection PyUnboundLocalVariable
        my_send_mail(subj, body, email.strip(), obj, reply_to, schedule=cnt * 10)
        aux[email] = 1


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


def clean_sender(name):
    """Clean sender name for email headers by removing special characters.

    Args:
        name (str): Original sender name

    Returns:
        str: Sanitized sender name safe for email headers
    """
    name = name.replace(":", " ")
    name = name.split(",")[0]
    name = re.sub(r"[^a-zA-Z0-9\s\-\']", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


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

    Side effects:
        Sends email using configured SMTP settings or default connection

    Raises:
        Exception: Re-raises email sending exceptions after logging error details
    """
    hdr = {}
    bcc = []

    # Initialize with default LarpManager sender configuration
    connection = None
    sender_email = "info@larpmanager.com"
    sender = f"LarpManager <{sender_email}>"
    event_settings = False

    try:
        # Apply event-level configuration if run_id is provided and SMTP is configured
        if run_id:
            run = Run.objects.get(pk=run_id)
            event = run.event
            email_host_user = event.get_config("mail_server_host_user", "", bypass_cache=True)

            # Only apply event settings if SMTP host user is configured
            if email_host_user:
                sender_email = email_host_user
                sender = f"{clean_sender(event.name)} <{sender_email}>"
                connection = get_connection(
                    host=event.get_config("mail_server_host", "", bypass_cache=True),
                    port=event.get_config("mail_server_port", "", bypass_cache=True),
                    username=event.get_config("mail_server_host_user", "", bypass_cache=True),
                    password=event.get_config("mail_server_host_password", "", bypass_cache=True),
                    use_tls=event.get_config("mail_server_use_tls", False, bypass_cache=True),
                )
                event_settings = True

        # Apply association-level configuration if assoc_id is provided
        if assoc_id:
            assoc = Association.objects.get(pk=assoc_id)

            # Add association main email to BCC if configured
            if assoc.get_config("mail_cc", False, bypass_cache=True) and assoc.main_mail:
                bcc.append(assoc.main_mail)

            # Apply custom SMTP settings if configured (only if event settings not already applied)
            email_host_user = assoc.get_config("mail_server_host_user", "", bypass_cache=True)
            if email_host_user:
                if not event_settings:
                    sender_email = email_host_user
                    sender = f"{clean_sender(assoc.name)} <{sender_email}>"
                    connection = get_connection(
                        host=assoc.get_config("mail_server_host", "", bypass_cache=True),
                        port=assoc.get_config("mail_server_port", "", bypass_cache=True),
                        username=assoc.get_config("mail_server_host_user", "", bypass_cache=True),
                        password=assoc.get_config("mail_server_host_password", "", bypass_cache=True),
                        use_tls=assoc.get_config("mail_server_use_tls", False, bypass_cache=True),
                    )
            # Use standard LarpManager subdomain sender if no custom SMTP configured
            elif not event_settings:
                sender_email = f"{assoc.slug}@larpmanager.com"
                sender = f"{clean_sender(assoc.name)} <{sender_email}>"

        # Fall back to default SMTP connection if no custom connection configured
        if not connection:
            connection = get_connection()

        # Set custom Reply-To header if provided
        if reply_to:
            hdr["Reply-To"] = reply_to

        # Add RFC-compliant unsubscribe header
        hdr["List-Unsubscribe"] = f"<mailto:{sender_email}>"

        body_html = body

        # Build multipart email with both plain text and HTML versions
        email = EmailMultiAlternatives(
            subj,
            remove_html_tags(body),
            sender,
            [m_email],
            bcc=bcc,
            headers=hdr,
            connection=connection,
        )
        email.attach_alternative(body_html, "text/html")

        # Send the email
        email.send()

        # Log email details in debug mode for troubleshooting
        if conf_settings.DEBUG:
            logger.info(f"Sending email to: {m_email}")
            logger.info(f"Subject: {subj}")
            logger.debug(f"Body: {body}")

    except Exception as e:
        # Log the error and re-raise for caller handling
        mail_error(subj, body, e)
        raise e


def add_unsubscribe_body(assoc):
    """Add unsubscribe footer to email body.

    Args:
        assoc: Association instance for unsubscribe URL

    Returns:
        str: HTML footer with unsubscribe link
    """
    txt = "<br /><br />======================"
    txt += "<br /><br />" + _(
        "Do you want to unsubscribe from our communication lists? <a href='%(url)s'>Unsubscribe</a>"
    ) % {"url": get_url("unsubscribe", assoc)}
    return txt


def my_send_mail(
    subj: str,
    body: str,
    recipient: Union[str, Member],
    obj: Optional[Union[Run, Event, Association, Any]] = None,
    reply_to: Optional[str] = None,
    schedule: int = 0,
) -> None:
    """Queue email for sending with context-aware formatting.

    Main email sending function that adds signatures, unsubscribe links,
    and queues email for background delivery.

    Args:
        subj: Email subject line
        body: Email body content (HTML or plain text)
        recipient: Email recipient address or Member instance
        obj: Context object for extracting association/run information.
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
    subj = subj.replace("  ", " ")

    # Initialize context variables for database relationships
    run_id = None
    assoc_id = None

    # Extract context information from the provided object
    if obj:
        # Handle direct model instances
        if isinstance(obj, Run):
            run_id = obj.id  # type: ignore[attr-defined]
            assoc_id = obj.event.assoc_id  # type: ignore[attr-defined]
        elif isinstance(obj, Event):
            assoc_id = obj.assoc_id  # type: ignore[attr-defined]
        elif isinstance(obj, Association):
            assoc_id = obj.id  # type: ignore[attr-defined]
        # Handle objects with foreign key relationships
        elif hasattr(obj, "run_id") and obj.run_id:
            run_id = obj.run_id
            assoc_id = obj.run.event.assoc_id
        elif hasattr(obj, "assoc_id") and obj.assoc_id:
            assoc_id = obj.assoc_id
        elif hasattr(obj, "event_id") and obj.event_id:
            assoc_id = obj.event.assoc_id

        # Add organization signature if available
        if assoc_id:
            sign = get_assoc_text(assoc_id, AssocTextType.SIGNATURE)
            if sign:
                body += sign

    # Append unsubscribe footer based on context
    body += add_unsubscribe_body(obj)

    # Convert Member instance to email string if needed
    if isinstance(recipient, Member):
        recipient = recipient.email

    # Ensure string types for database storage
    subj_str = str(subj)
    body_str = str(body)

    # Create email record for tracking and delivery
    email = Email.objects.create(
        assoc_id=assoc_id, run_id=run_id, recipient=recipient, subj=subj_str, body=body_str, reply_to=reply_to
    )

    # Queue email for background processing
    my_send_mail_bkg(email.pk, schedule=schedule)


def notify_admins(subj, text, exception=None):
    """Send notification email to system administrators.

    Args:
        subj (str): Notification subject
        text (str): Notification message
        exception (Exception, optional): Exception to include in notification

    Side effects:
        Sends notification emails to all configured ADMINS
    """
    if exception:
        tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        text += "\n" + tb
    for _name, email in conf_settings.ADMINS:
        my_send_mail(subj, text, email)
