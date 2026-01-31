"""Email backend implementations for different sending methods."""

import logging
import time
from abc import ABC, abstractmethod

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

logger = logging.getLogger(__name__)


class EmailBackend(ABC):
    """Abstract base class for email backends."""

    @abstractmethod
    def send_message(self, email_message: EmailMultiAlternatives) -> None:
        """Send email message.

        Args:
            email_message: Django EmailMultiAlternatives instance to send

        Raises:
            Exception: If sending fails
        """
        pass


class SMTPEmailBackend(EmailBackend):
    """Email backend using custom SMTP configuration."""

    def __init__(self, smtp_config: dict):
        """Initialize SMTP backend with custom configuration."""

        self.smtp_config = smtp_config
        self.connection = get_connection(
            host=smtp_config.get('host'),
            port=smtp_config.get('port'),
            username=smtp_config.get('username'),
            password=smtp_config.get('password'),
            use_tls=smtp_config.get('use_tls', False),
        )

    def send_message(self, email_message: EmailMultiAlternatives) -> None:
        """Send email via custom SMTP server."""

        # Set the connection on the message
        email_message.connection = self.connection
        email_message.send()
        logger.debug(f"Email sent via custom SMTP: {self.smtp_config.get('host')}")


class SESEmailBackend(EmailBackend):
    """Email backend using Amazon SES."""

    def __init__(self):
        """Initialize SES backend with credentials from settings."""
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError as e:
            raise ImportError("boto3 is required for SES backend. Install with: pip install boto3") from e

        self.boto3 = boto3
        self.ClientError = ClientError

        self.client = boto3.client(
            'ses',
            aws_access_key_id=settings.AWS_SES_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SES_SECRET_ACCESS_KEY,
            region_name=settings.AWS_SES_REGION_NAME,
        )

    def send_message(self, email_message: EmailMultiAlternatives) -> None:
        """Send email via Amazon SES using raw email API."""

        max_retries = 3
        retry_delay = 1  # seconds

        for attempt in range(max_retries):
            try:
                # Add organization main email as Reply-To if not already set
                if hasattr(email_message, 'org_main_mail') and 'Reply-To' not in email_message.extra_headers:
                    email_message.extra_headers['Reply-To'] = email_message.org_main_mail
                    logger.debug(f"SES: Added Reply-To header: {email_message.org_main_mail}")

                # Convert EmailMultiAlternatives to raw MIME message
                raw_message = email_message.message().as_bytes()

                # Prepare destinations (to + bcc)
                destinations = list(email_message.to)
                if email_message.bcc:
                    destinations.extend(email_message.bcc)

                # Send via SES
                response = self.client.send_raw_email(
                    Source=email_message.from_email,
                    Destinations=destinations,
                    RawMessage={'Data': raw_message}
                )

                message_id = response.get('MessageId', 'unknown')
                logger.info(f"SES email sent: MessageId={message_id}")
                return

            except self.ClientError as e:
                error_code = e.response['Error']['Code']
                error_message = e.response['Error']['Message']

                # Handle throttling with exponential backoff
                if error_code in ['Throttling', 'ServiceUnavailable']:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"SES {error_code} error (attempt {attempt + 1}/{max_retries}). "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"SES max retries exceeded after {error_code}")
                        raise

                # Handle permanent failures (don't retry)
                elif error_code == 'MessageRejected':
                    logger.error(f"SES message rejected: {error_message}")
                    raise

                elif error_code == 'InvalidParameterValue':
                    logger.error(f"SES invalid parameter: {error_message}")
                    raise

                elif error_code == 'AccountSendingPausedException':
                    logger.critical(f"SES account suspended: {error_message}")
                    raise

                else:
                    # Unknown error - log and raise
                    logger.error(f"SES error {error_code}: {error_message}")
                    raise


class DefaultEmailBackend(EmailBackend):
    """Email backend using Django's default email configuration."""

    def __init__(self):
        """Initialize default backend."""
        self.connection = get_connection()

    def send_message(self, email_message: EmailMultiAlternatives) -> None:
        """Send email via Django's default email backend."""

        email_message.connection = self.connection
        email_message.send()
        logger.debug("Email sent via default Django backend")
