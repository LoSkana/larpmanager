"""Email backend implementations for different sending methods."""

import logging
from abc import ABC, abstractmethod

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

logger = logging.getLogger(__name__)


class EmailBackend(ABC):
    """Abstract base class for email backends."""

    @abstractmethod
    def send_message(self, email_message: EmailMultiAlternatives) -> None:
        """Send email message."""


class SMTPEmailBackend(EmailBackend):
    """Email backend using custom SMTP configuration."""

    def __init__(self, smtp_config: dict) -> None:
        """Initialize SMTP backend with custom configuration."""
        self.smtp_config = smtp_config
        self.connection = get_connection(
            host=smtp_config.get("host"),
            port=smtp_config.get("port"),
            username=smtp_config.get("username"),
            password=smtp_config.get("password"),
            use_tls=smtp_config.get("use_tls", False),
        )

    def send_message(self, email_message: EmailMultiAlternatives) -> None:
        """Send email via custom SMTP server."""
        # Set the connection on the message
        email_message.connection = self.connection
        email_message.send()
        logger.debug("Email sent via custom SMTP: %s", self.smtp_config.get("host"))


class SESEmailBackend(EmailBackend):
    """Email backend using Amazon SES."""

    def __init__(self) -> None:
        """Initialize SES backend with credentials from settings."""
        self.boto3 = boto3
        self.ClientError = ClientError

        self.client = boto3.client(
            "ses",
            aws_access_key_id=settings.AWS_SES_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SES_SECRET_ACCESS_KEY,
            region_name=settings.AWS_SES_REGION_NAME,
        )

    def send_message(self, email_message: EmailMultiAlternatives) -> None:
        """Send email via Amazon SES using raw email API."""
        # Add organization main email as Reply-To if not already set
        if hasattr(email_message, "org_main_mail") and "Reply-To" not in email_message.extra_headers:
            email_message.extra_headers["Reply-To"] = email_message.org_main_mail
            logger.debug("SES: Added Reply-To header: %s", email_message.org_main_mail)

        # Convert EmailMultiAlternatives to raw MIME message
        raw_message = email_message.message().as_bytes()

        # Prepare destinations (to + bcc)
        destinations = list(email_message.to)
        if email_message.bcc:
            destinations.extend(email_message.bcc)

        # Send via SES
        response = self.client.send_raw_email(
            Source=email_message.from_email, Destinations=destinations, RawMessage={"Data": raw_message}
        )

        message_id = response.get("MessageId", "unknown")
        logger.info("SES email sent: MessageId=%s", message_id)


class DefaultEmailBackend(EmailBackend):
    """Email backend using Django's default email configuration."""

    def __init__(self) -> None:
        """Initialize default backend."""
        self.connection = get_connection()

    def send_message(self, email_message: EmailMultiAlternatives) -> None:
        """Send email via Django's default email backend."""
        email_message.connection = self.connection
        email_message.send()
        logger.debug("Email sent via default Django backend")
