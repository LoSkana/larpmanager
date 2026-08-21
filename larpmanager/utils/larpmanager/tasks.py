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

import hashlib
import logging
import re
import traceback
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any

from background_task import background
from django.conf import settings as conf_settings
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.utils import timezone

from larpmanager.cache.association_text import get_association_text
from larpmanager.cache.basic import get_event_basic_cache, get_run_association_id
from larpmanager.cache.config import get_event_config
from larpmanager.cache.text_fields import remove_html_tags
from larpmanager.mail.factory import EmailConnectionFactory
from larpmanager.mail.suppression import get_suppressed_emails, is_suppressed, unsuppress_email
from larpmanager.models.access import AssociationRole
from larpmanager.models.association import Association, AssociationTextType, get_url
from larpmanager.models.event import Event, Run
from larpmanager.models.larpmanager import LarpManagerNewsletter, NewsletterStatus
from larpmanager.models.member import Member, Membership, MembershipStatus, NewsletterChoices
from larpmanager.models.miscellanea import EmailContent, EmailRecipient
from larpmanager.utils.services.miscellanea import _newsletter_set_non_active

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

INTERNAL_KWARGS = {"schedule", "repeat", "repeat_until", "remove_existing_tasks"}


def background_auto(schedule: Any = 0, *, skip_duplicates: bool = False, **background_kwargs: Any) -> Any:
    """Conditionally run functions as background tasks.

    Creates a decorator that can run functions either synchronously
    (if AUTO_BACKGROUND_TASKS is True) or as background tasks.

    Args:
        schedule (int): Seconds to delay before execution
        skip_duplicates (bool): Skip scheduling if an identical pending task exists
        **background_kwargs: Additional arguments for background task

    Returns:
        function: Decorator function

    """

    def decorator(original_function: Callable[..., Any]) -> Callable[..., Any]:
        """Conditionally execute a function as a background task.

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
            # Skip scheduling if an identical pending task already exists
            if skip_duplicates:
                from background_task.models import Task  # noqa: PLC0415

                filtered_kwargs = {k: v for k, v in kwargs.items() if k not in INTERNAL_KWARGS}
                if Task.objects.get_task(background_task.name, args=list(args), kwargs=filtered_kwargs).exists():
                    return None
            # Schedule function as background task
            return background_task(*args, **kwargs)

        # Attach task references to wrapper for external access
        wrapper.task = background_task
        wrapper.task_function = original_function
        return wrapper

    return decorator


# MAIL


def mail_error(subject: Any, email_body: Any, exception: Any = None) -> None:
    """Handle email sending errors and notify administrators.

    Args:
        subject (str): Email subject that failed
        email_body (str): Email body that failed
        exception (Exception, optional): Exception that caused the failure

    Side effects:
        Prints error details and sends error notification to admins

    """
    logger.error("Mail error: %s", exception)
    logger.error("Subject: %s", subject)
    logger.error("Body: %s", email_body)
    if exception:
        logger.error("Mail error traceback: %s", traceback.format_exc())
    error_notification_body = f"{subject} <br /><br /> {email_body}"
    error_notification_subject = "[LarpManager] Mail error"
    for _admin_name, admin_email in conf_settings.ADMINS:
        my_send_simple_mail(error_notification_subject, error_notification_body, admin_email)


def split_recipients(recipient_text: str) -> list:
    """Split text by any common separator: comma, semicolon, pipe, whitespace."""
    return [p.strip() for p in re.split(r"[,;\|\s]+", recipient_text) if p.strip()]


def partition_shared_recipients(recipients: list, association_id: int | None) -> tuple[list, list]:
    """Split recipients into those who shared their data with the association and those who did not.

    A recipient is allowed if a Member with that email exists and has a Membership for the given
    association whose status is not EMPTY (i.e. they shared their data). When association_id is
    missing, no filtering is applied and every recipient is allowed.

    Args:
        recipients: List of recipient email addresses.
        association_id: Association the email is sent on behalf of.

    Returns:
        Tuple (allowed, ignored) of email addresses, preserving input order.

    """
    if not association_id:
        return list(recipients), []

    shared_emails = {
        email.lower()
        for email in Membership.objects.filter(
            association_id=association_id,
        )
        .exclude(status=MembershipStatus.EMPTY)
        .values_list("member__email", flat=True)
        if email
    }

    allowed = []
    ignored = []
    for email in recipients:
        if email.strip().lower() in shared_emails:
            allowed.append(email)
        else:
            ignored.append(email)
    return allowed, ignored


def partition_newsletter_recipients(recipients: list, association_id: int | None) -> tuple[list, list]:
    """Split recipients into those who accept bulk communications and those who opted out.

    Association mails honour the membership newsletter preference, platform
    mails the global newsletter status. The opted out set is resolved with a
    single query, so a broadcast does not hit the database once per recipient.

    Args:
        recipients: List of recipient email addresses.
        association_id: Association the email is sent on behalf of.

    Returns:
        Tuple (allowed, opted_out) of email addresses, preserving input order.

    """
    if association_id:
        queryset = Membership.objects.filter(
            association_id=association_id,
            newsletter=NewsletterChoices.NO,
        ).values_list("member__email", flat=True)
    else:
        queryset = LarpManagerNewsletter.objects.filter(
            status=NewsletterStatus.UNSUBSCRIBED,
        ).values_list("email", flat=True)

    opted_out_emails = {email.lower() for email in queryset if email}

    allowed = []
    opted_out = []
    for email in recipients:
        if email.strip().lower() in opted_out_emails:
            opted_out.append(email)
        else:
            allowed.append(email)
    return allowed, opted_out


def _create_bulk_recipients(
    email_content: Any,
    recipients: list,
    seen_emails: dict,
    opted_out: list | None = None,
) -> list:
    """Create EmailRecipient records for valid, unique addresses and return their PKs.

    Addresses that opted out of bulk communications, or that bounced or
    complained in the past, get a recipient row flagged as skipped, so the send
    is traceable, but are never queued. Callers that already resolved the opted
    out addresses pass them in, so the query is not repeated; in that case
    recipients only holds the allowed ones.
    """
    if opted_out is None:
        recipients, opted_out = partition_newsletter_recipients(recipients, email_content.association_id)
    opted_out_emails = set(opted_out)
    # Resolved once for the whole broadcast, instead of one query per recipient
    suppressed_emails = get_suppressed_emails(recipients)

    recipient_ids = []
    for email in recipients + opted_out:
        if not email or email in seen_emails:
            continue
        try:
            validate_email(email.strip())
        except ValidationError:
            logger.warning("Skipping invalid email address in bulk send")
            continue
        seen_emails[email] = 1
        email_recipient = EmailRecipient.objects.create(
            email_content=email_content,
            recipient=email.strip(),
            language_code=None,
        )
        if email in opted_out_emails:
            logger.info("Skipping bulk recipient opted out of the newsletter")
            _mark_skipped(email_recipient, "newsletter")
            continue
        # Bounced or complaining addresses are excluded from every bulk communication
        if email.strip().lower() in suppressed_emails:
            logger.info("Skipping bulk recipient on the suppression list")
            _mark_skipped(email_recipient, "suppressed")
            continue
        recipient_ids.append(email_recipient.pk)
    return recipient_ids


def _broadcast_size_allowed(total_recipients: int) -> bool:
    """Check that a broadcast has recipients and stays within the configured limit.

    Opted out addresses are traced as skipped rows, so they count towards the size.
    """
    if not total_recipients:
        logger.info("Broadcast skipped: no recipient left")
        return False

    max_recipients = getattr(conf_settings, "MAIL_MAX_RECIPIENTS", 2000)
    if total_recipients > max_recipients:
        logger.warning("Broadcast rejected: %d recipients exceeds limit of %d", total_recipients, max_recipients)
        return False

    return True


@background_auto(queue="mail")
def release_suppressed_emails(emails: list) -> None:
    """Release a list of addresses from the local and the SES suppression lists.

    Each release calls SES, so a bulk release runs out of the request cycle:
    a few hundred addresses would otherwise time out the browser.
    """
    for email in emails:
        unsuppress_email(email)


@background_auto()
def send_mail_exec(
    recipient_list: str,
    subj: str,
    body: str,
    association_id: int | None = None,
    run_id: int | None = None,
    interval: int | None = None,
    opted_out: list | None = None,
) -> None:
    """Send bulk emails to multiple recipients with batch delivery.

    Sends emails to a comma-separated list of recipients in batches of 10,
    with a configurable delay between batches to prevent spam filtering.
    Emails are prefixed with the organization/run name.

    This function creates a single EmailContent object and multiple EmailRecipient
    objects to avoid duplicating email content in the database.

    Args:
        recipient_list: Text list of email addresses to send to
        subj: Email subject line (will be prefixed with org/run name)
        body: Email body content in HTML or plain text
        association_id: Association ID for determining sender context
        run_id: Run ID for determining sender context (alternative to association_id)
        interval: Seconds to wait between each batch (defaults to MAIL_BATCH_INTERVAL)
        opted_out: Addresses already known to have opted out, excluded from recipient_list

    Returns:
        None

    Side Effects:
        - Creates one EmailContent and multiple EmailRecipient records
        - Schedules batch emails with 1 second interval between batches
        - Sends notification to admins about bulk email operation
        - Logs warning if neither association_id nor run_id are provided

    """
    seen_emails = {}

    sender_context = None
    # Determine sender context: run wins over association
    if run_id:
        sender_context = Run.objects.filter(pk=run_id).first()
        if not sender_context:
            # Run was deleted since this task was scheduled; drop the dead FK
            run_id = None
        # Extract association_id from run if not provided
        elif not association_id:
            association_id = sender_context.event.association_id
    elif association_id:
        sender_context = Association.objects.filter(pk=association_id).first()
        if not sender_context:
            # Association was deleted since this task was scheduled; drop the dead FK
            association_id = None

    if sender_context:
        # Add organization/run prefix to subject line
        subj = f"[{sender_context}] {subj}"

    # Parse symbol-separated email list
    recipients = split_recipients(recipient_list)

    if not _broadcast_size_allowed(len(recipients) + len(opted_out or [])):
        return

    # Notify administrators about bulk email operation, only when something is really sent
    if sender_context and recipients:
        notify_admins(f"Sending {len(recipients)} - [{sender_context}]", f"{subj}")

    # Create a single EmailContent object for all recipients
    email_content = EmailContent.objects.create(
        association_id=association_id,
        run_id=run_id,
        subj=subj,
        body=str(body),
        bulk=True,
    )

    recipient_ids = _create_bulk_recipients(email_content, recipients, seen_emails, opted_out)

    # Split into batches
    batches = [
        recipient_ids[i : i + conf_settings.MAIL_BATCH_SIZE]
        for i in range(0, len(recipient_ids), conf_settings.MAIL_BATCH_SIZE)
    ]

    # Schedule each batch with X second delay between batches
    batch_interval = interval if interval is not None else conf_settings.MAIL_BATCH_INTERVAL
    for batch_index, batch in enumerate(batches):
        my_send_mail_bkg(batch, schedule=batch_index * batch_interval)


@background_auto(queue="mail")
def my_send_mail_bkg(email_recipient_pk: int | list[int]) -> None:
    """Background task to send a queued email or batch of emails.

    Args:
        email_recipient_pk: Primary key or list of primary keys of EmailRecipient to send

    Side effects:
        Sends the email(s) and marks successfully sent emails as sent in database.
        Failed emails remain unsent for retry in next execution.

    """
    # Handle both single ID and list of IDs
    email_recipient_pks = [email_recipient_pk] if isinstance(email_recipient_pk, int) else email_recipient_pk

    for pk in email_recipient_pks:
        try:
            email_recipient = EmailRecipient.objects.select_related("email_content").get(pk=pk)
        except ObjectDoesNotExist:
            logger.warning("EmailRecipient %s not found", pk)
            continue

        # Checked first: a batch retried after a mid batch failure must not restamp
        # rows that were already delivered
        if email_recipient.sent:
            logger.info("Email %s already sent!", pk)
            continue

        if "@" not in email_recipient.recipient:
            logger.info("Email recipient invalid: %s", email_recipient.recipient)
            _mark_skipped(email_recipient, "invalid")
            continue

        domain = email_recipient.recipient.split("@")[-1].lower()

        forbidden = ["demo", "test"]
        if any(keyword in domain for keyword in forbidden):
            logger.info("Email recipient forbidden: %s", email_recipient.recipient)
            _mark_skipped(email_recipient, "forbidden")
            continue

        email_content = email_recipient.email_content

        # Rechecked at send time with the real nature of the mail: a batch queued hours
        # earlier may hold addresses suppressed after the queue time filter ran
        if is_suppressed(email_recipient.recipient, bulk=email_content.bulk):
            logger.info("Email recipient suppressed: %s", email_recipient.recipient)
            _mark_skipped(email_recipient, "suppressed")
            continue

        body = email_content.body

        association = None
        if email_content.association_id:
            # Add organization signature if available
            signature = get_association_text(
                email_content.association_id, AssociationTextType.SIGNATURE, email_recipient.language_code
            )
            if signature:
                body += signature

            association = Association.objects.get(pk=email_content.association_id)

        # Append unsubscribe footer, reusing the same link in the message headers
        unsubscribe_url = build_unsubscribe_url(association, email_recipient.recipient)
        body += add_unsubscribe_body(unsubscribe_url)

        # RFC 8058 one-click is meant for bulk mail only: pressing the mail client button
        # on a receipt or a password reset must not silently drop the newsletter
        header_url = unsubscribe_url
        if email_content.bulk:
            header_url = build_unsubscribe_url(association, email_recipient.recipient, one_click=True)

        my_send_simple_mail(
            email_content.subj,
            body,
            email_recipient.recipient,
            email_content.association_id,
            email_content.run_id,
            email_content.reply_to,
            email_content.attachment_path,
            email_content.attachment_name,
            header_url,
            one_click=email_content.bulk,
        )

        # Only mark as sent if successful
        email_recipient.sent = timezone.now()
        email_recipient.save()


def _mark_skipped(email_recipient: EmailRecipient, reason: str) -> None:
    """Flag a recipient as not deliverable, so it is not retried forever."""
    email_recipient.skipped = reason
    # updated drives the archive ordering, so it must be refreshed along with the flag
    email_recipient.save(update_fields=["skipped", "updated"])


def clean_sender(sender_name: Any) -> Any:
    """Clean sender name for email headers by removing special characters."""
    sender_name = sender_name.replace(":", " ")
    sender_name = sender_name.split(",")[0]
    sender_name = re.sub(r"[^a-zA-Z0-9\s\-\']", "", sender_name)
    return re.sub(r"\s+", " ", sender_name).strip()


def my_send_simple_mail(  # noqa: PLR0913 - transport wrapper carrying the whole message description
    subj: str,
    body: str,
    m_email: str,
    association_id: int | None = None,
    run_id: int | None = None,
    reply_to: str | None = None,
    attachment_path: str | None = None,
    attachment_name: str | None = None,
    unsubscribe_url: str | None = None,
    *,
    one_click: bool = False,
) -> None:
    """Send email with association/event-specific configuration.

    Uses priority order: Custom SMTP -> Amazon SES -> Default backend

    Handles custom SMTP settings, sender addresses, BCC lists, and email formatting
    based on association and event configuration. Prioritizes event-level settings
    over association-level settings when both are available.

    Args:
        subj: Email subject line
        body: Email body content (HTML format)
        m_email: Recipient email address
        association_id: Association ID for custom SMTP settings and sender configuration
        run_id: Run ID for event-specific SMTP settings (overrides association settings)
        reply_to: Custom Reply-To email address header
        attachment_path: Optional absolute filesystem path to a file to attach as PDF
        attachment_name: Optional filename to use in the email attachment (overrides the on-disk name)
        unsubscribe_url: Optional unsubscribe link, published in the message headers
        one_click: Whether the link accepts an RFC 8058 one-click post (bulk mails only)

    Raises:
        Exception: Re-raises email sending exceptions after logging error details

    Note:
        Sends email using configured backend (Custom SMTP, SES, or default).
        Logs email details in debug mode for troubleshooting.
    """
    try:
        # Gather metadata (sender, BCC, headers)
        metadata = _prepare_email_metadata(association_id, run_id, reply_to, unsubscribe_url, one_click=one_click)

        # Build email message
        email_message = _build_email_message(subj, body, m_email, metadata)

        if attachment_path:
            if Path(attachment_path).exists():
                if attachment_name:
                    email_message.attach(attachment_name, Path(attachment_path).read_bytes(), "application/pdf")
                else:
                    email_message.attach_file(attachment_path, "application/pdf")
            else:
                logger.warning("Receipt attachment not found, sending without it: %s", attachment_path)

        # Get backend and send
        backend = EmailConnectionFactory.get_backend(association_id, run_id)
        backend.send_message(email_message)

        # Debug logging
        if conf_settings.DEBUG:
            logger.info("Sending email to: %s", m_email)
            logger.info("Subject: %s", subj)
            logger.debug("Body: %s", body)

    except Exception as email_sending_exception:
        # Log the error and re-raise for caller handling
        mail_error(subj, body, email_sending_exception)
        raise


def _prepare_email_metadata(
    association_id: int | None,
    run_id: int | None,
    reply_to: str | None,
    unsubscribe_url: str | None = None,
    *,
    one_click: bool = False,
) -> dict:
    """Extract email metadata from association/event config.

    Args:
        association_id: Association ID for metadata extraction
        run_id: Run ID for event-specific metadata
        reply_to: Custom Reply-To email address
        unsubscribe_url: Unsubscribe link to publish in the headers
        one_click: Whether to advertise RFC 8058 one-click support

    Returns:
        Dict containing sender_email, sender_name, headers, and bcc_recipients
    """
    metadata = {
        "sender_email": "info@larpmanager.com",
        "sender_name": "LarpManager",
        "headers": {},
        "bcc_recipients": [],
        "base_url": get_url("").rstrip("/"),
    }

    cache_context = {}
    event_settings_applied = False

    # Apply event-level metadata
    if run_id:
        run = Run.objects.get(pk=run_id)
        event = run.event

        event_smtp_user = get_event_config(
            event.id,
            "mail_server_host_user",
            context=cache_context,
            bypass_cache=True,
        )
        if event_smtp_user:
            metadata["sender_email"] = event_smtp_user
            metadata["sender_name"] = event.name
            event_settings_applied = True

    # Apply association-level metadata
    if association_id:
        association = Association.objects.get(pk=association_id)

        # Base URL for absolutizing relative links/images in the body
        metadata["base_url"] = get_url("", association).rstrip("/")

        # Add BCC if configured
        if association.get_config("mail_cc", bypass_cache=True) and association.main_mail:
            metadata["bcc_recipients"].append(association.main_mail)

        # Store organization main email for potential Reply-To (used by SES backend)
        if association.main_mail:
            metadata["org_main_mail"] = association.main_mail

        # Set sender (only if event didn't set it)
        if not event_settings_applied:
            assoc_smtp_user = association.get_config("mail_server_host_user", bypass_cache=True)
            if assoc_smtp_user:
                metadata["sender_email"] = assoc_smtp_user
                metadata["sender_name"] = association.name
            else:
                # Use subdomain sender
                metadata["sender_email"] = f"{association.slug}@larpmanager.com"
                metadata["sender_name"] = association.name

    _add_email_headers(metadata, reply_to, unsubscribe_url, one_click=one_click)

    return metadata


def _add_email_headers(
    metadata: dict,
    reply_to: str | None,
    unsubscribe_url: str | None,
    *,
    one_click: bool = False,
) -> None:
    """Fill the message headers with the reply-to and unsubscribe entries."""
    if reply_to:
        if "\r" in reply_to or "\n" in reply_to:
            msg = "Invalid characters in reply-to address"
            raise ValueError(msg)
        metadata["headers"]["Reply-To"] = reply_to

    # RFC 8058: mailbox providers require an http link plus the one-click marker, which
    # may only be advertised on bulk mails
    if unsubscribe_url:
        metadata["headers"]["List-Unsubscribe"] = f"<{unsubscribe_url}>, <mailto:{metadata['sender_email']}>"
        if one_click:
            metadata["headers"]["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    else:
        metadata["headers"]["List-Unsubscribe"] = f"<mailto:{metadata['sender_email']}>"


# A whole html tag, rewritten one at a time so every attribute inside it is considered;
# quoted attribute values are consumed as a unit, so a ">" inside them does not end the tag
_TAG_RE = re.compile(r"""<[^>'"]*(?:(?:"[^"]*"|'[^']*')[^>'"]*)*>""")

# Content of a style block, the only place outside tags where css url() references are expected
_STYLE_BLOCK_RE = re.compile(r"(<style\b[^>]*>)(.*?)(</style\s*>)", re.IGNORECASE | re.DOTALL)

# Root-relative single-value attributes (excludes protocol-relative "//host/path")
_RELATIVE_URL_RE = re.compile(r"""(\s(?:src|href|poster|background)\s*=\s*["'])(/(?!/)[^"']*)(["'])""", re.IGNORECASE)

# Srcset attributes, whose value is a comma separated list of candidates
_RELATIVE_SRCSET_RE = re.compile(r"""(\ssrcset\s*=\s*["'])([^"']*)(["'])""", re.IGNORECASE)

# Root-relative CSS url() references, in inline styles or <style> blocks
_RELATIVE_CSS_URL_RE = re.compile(r"""(url\(\s*['"]?)(/(?!/)[^)'"]*)""", re.IGNORECASE)

# Root-relative url at the start of a srcset candidate (excludes protocol-relative "//host/path")
_SRCSET_CANDIDATE_RE = re.compile(r"(\A|,)(\s*)(/(?!/)[^\s,]*)")


def _absolute_srcset(value: str, base_url: str) -> str:
    """Prefix every root-relative candidate of a srcset value with the base url.

    Values holding a data uri are left untouched: their comma separated base64
    payload cannot be told apart from a candidate list, and may itself start
    with a slash.
    """
    if "data:" in value.lower():
        return value
    return _SRCSET_CANDIDATE_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}{base_url}{match.group(3)}", value)


def _absolute_css(css: str, base_url: str) -> str:
    """Prefix every root-relative css url() reference with the base url."""
    return _RELATIVE_CSS_URL_RE.sub(lambda match: f"{match.group(1)}{base_url}{match.group(2)}", css)


def _absolute_tag(tag: str, base_url: str) -> str:
    """Absolutize every root-relative url attribute of a single html tag."""
    tag = _RELATIVE_URL_RE.sub(lambda match: f"{match.group(1)}{base_url}{match.group(2)}{match.group(3)}", tag)
    tag = _RELATIVE_SRCSET_RE.sub(
        lambda match: f"{match.group(1)}{_absolute_srcset(match.group(2), base_url)}{match.group(3)}", tag
    )
    # covers inline styles, the only css that lives inside a tag
    return _absolute_css(tag, base_url)


def absolute_email_urls(body: str, base_url: str) -> str:
    """Rewrite root-relative links, media references and CSS urls to absolute urls.

    Urls are rewritten only where they can appear: inside html tags (attributes
    and inline styles) and inside style blocks, so plain text and scripts are
    left untouched.
    """
    if not body:
        return body
    body = _TAG_RE.sub(lambda match: _absolute_tag(match.group(0), base_url), body)
    return _STYLE_BLOCK_RE.sub(
        lambda match: f"{match.group(1)}{_absolute_css(match.group(2), base_url)}{match.group(3)}", body
    )


def _build_email_message(subj: str, body: str, m_email: str, metadata: dict) -> EmailMultiAlternatives:
    """Build EmailMultiAlternatives from components.

    Args:
        subj: Email subject
        body: Email body (HTML format)
        m_email: Recipient email address
        metadata: Dict with sender_email, sender_name, headers, bcc_recipients, base_url, org_main_mail (optional)

    Returns:
        EmailMultiAlternatives instance ready to send
    """
    sender = f"{clean_sender(metadata['sender_name'])} <{metadata['sender_email']}>"

    if metadata.get("base_url"):
        body = absolute_email_urls(body, metadata["base_url"])

    # Note: Connection is NOT set here - backend handles sending
    message = EmailMultiAlternatives(
        subj,
        remove_html_tags(body),
        sender,
        [m_email],
        bcc=metadata["bcc_recipients"],
        headers=metadata["headers"],
    )
    message.attach_alternative(body, "text/html")

    # Store organization main email for SES backend to use as Reply-To if needed
    if "org_main_mail" in metadata:
        message.org_main_mail = metadata["org_main_mail"]

    return message


def build_unsubscribe_url(association: Any, recipient_email: str = "", *, one_click: bool = False) -> str:
    """Build the signed unsubscribe link of a recipient, scoped to an association.

    The one-click variant points to the endpoint reserved to the RFC 8058 post
    sent by mail clients, which is the only one exempted from CSRF.
    """
    token_data: dict[str, Any] = {"email": recipient_email}
    if association:
        token_data["association_slug"] = association.slug
    token = signing.dumps(token_data, salt="unsubscribe")
    hex_token = token.encode().hex()
    path = "unsubscribe-one-click" if one_click else "unsubscribe"
    return get_url(f"{path}/{hex_token}/", association)


def add_unsubscribe_body(unsubscribe_url: str) -> str:
    """Add unsubscribe footer to email body."""
    html_footer = "<br /><br />-<br />"
    html_footer += f"<a ses:no-track href='{unsubscribe_url}'>Unsubscribe</a>"
    return html_footer


def my_send_mail(
    subject: str,
    body: str,
    recipient: str | Member,
    context_object: Run | Event | Association | Any | None = None,
    reply_to: str | None = None,
    schedule: int = 0,
    attachment_path: str | None = None,
    attachment_name: str | None = None,
) -> None:
    """Queue email for sending with context-aware formatting.

    Main email sending function that adds signatures, unsubscribe links,
    and queues email for background delivery.

    Args:
        subject: Email subject line
        body: Email body content (HTML or plain text)
        recipient: Email recipient address or Member instance
        context_object: Context object for extracting association/run information.
             Supports Run, Event, Association, or objects with run_id/association_id/event_id
        reply_to: Custom reply-to email address
        schedule: Delay in seconds before sending email
        attachment_path: Optional absolute filesystem path to a file to attach
        attachment_name: Optional filename to use in the email attachment (overrides the on-disk name)

    Returns:
        None

    Side Effects:
        - Creates EmailContent and EmailRecipient records in database
        - Schedules background task for email delivery
        - Modifies body with signature and unsubscribe link

    """
    # Clean up duplicate spaces in subject line
    subject = subject.replace("  ", " ")

    # Determine language for translations
    language_code = None
    if isinstance(recipient, Member):
        language_code = recipient.language

    # Initialize context variables
    association_id, run_id = get_context_elements(context_object)

    # Convert Member instance to email string if needed
    if isinstance(recipient, Member):
        recipient = recipient.email

    # Ensure string types for database storage
    subject_string = str(subject)
    body_string = str(body)

    # Create email content record for tracking
    email_content = EmailContent.objects.create(
        association_id=association_id,
        run_id=run_id,
        subj=subject_string,
        body=body_string,
        reply_to=reply_to,
        attachment_path=attachment_path,
        attachment_name=attachment_name,
    )

    # Create email recipient record
    email_recipient = EmailRecipient.objects.create(
        email_content=email_content,
        recipient=recipient,
        language_code=language_code,
    )

    # Queue email for background processing
    my_send_mail_bkg(email_recipient.pk, schedule=schedule)


def get_context_elements(context_object: dict) -> tuple[int, int]:
    """Extract run and association element ids."""
    association_id = None
    run_id = None
    # Extract context information from the provided object
    if context_object:
        # Handle direct model instances
        if isinstance(context_object, Run):
            run_id = context_object.id  # type: ignore[attr-defined]
            association_id = get_run_association_id(run_id)
        elif isinstance(context_object, Event):
            association_id = context_object.association_id  # type: ignore[attr-defined]
        elif isinstance(context_object, Association):
            association_id = context_object.id  # type: ignore[attr-defined]
        # Handle objects with foreign key relationships
        elif hasattr(context_object, "run_id") and context_object.run_id:
            run_id = context_object.run_id
            association_id = get_run_association_id(run_id)
        elif hasattr(context_object, "association_id") and context_object.association_id:
            association_id = context_object.association_id
        elif hasattr(context_object, "event_id") and context_object.event_id:
            association_id = get_event_basic_cache(context_object.event_id)["association_id"]
    return association_id, run_id


def notify_admins(subject: str, message_text: str = "", exception: Exception | None = None) -> None:
    """Send notification email to system administrators."""
    # Rate-limit: suppress duplicate notifications for the same subject within 5 minutes
    rate_key = "notify_admins:" + hashlib.md5(subject.encode(), usedforsecurity=False).hexdigest()
    if cache.get(rate_key):
        return
    cache.set(rate_key, 1, timeout=300)

    # Ensure message_text is a string to prevent type errors during concatenation
    message_text = str(message_text)

    if exception:
        logger.error(
            "Admin notification traceback: %s",
            "".join(traceback.format_exception(type(exception), exception, exception.__traceback__)),
        )
    for _name, email in conf_settings.ADMINS:
        my_send_mail(subject, message_text, email)


# DELETION


@background(schedule=0)
def delete_run_task(run_uuid: str) -> None:
    """Delete the event (and all its runs) identified by this run uuid.

    Nulls out parent FK on child events first to prevent cascade-deleting them.
    """
    try:
        run = Run.objects.select_related("event").get(uuid=run_uuid)
    except Run.DoesNotExist:
        return
    event = run.event
    Event.objects.filter(parent=event).update(parent=None)
    event.delete()


@background(schedule=0)
def delete_association_task(association_slug: str) -> None:
    """Unsubscribe newsletter and delete association in the background.

    Nulls out parent FK on child events whose parent belongs to this association,
    so external child events are not cascade-deleted.
    """
    try:
        association = Association.objects.get(slug=association_slug)
    except Association.DoesNotExist:
        return
    events_in_assoc = Event.objects.filter(association=association)
    Event.objects.filter(parent__in=events_in_assoc).update(parent=None)
    newsletter_emails = set(
        AssociationRole.objects.filter(association=association, number=1).values_list("members__email", flat=True)
    )
    if association.main_mail:
        newsletter_emails.add(association.main_mail)
    for email in newsletter_emails:
        if email:
            _newsletter_set_non_active(email)
    association.delete()
