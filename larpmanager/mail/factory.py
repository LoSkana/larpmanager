"""Factory for selecting appropriate email backend."""

import logging

from django.conf import settings

from larpmanager.cache.config import get_event_config
from larpmanager.models import Association, Run

from larpmanager.mail.backends import DefaultEmailBackend, SESEmailBackend, SMTPEmailBackend

logger = logging.getLogger(__name__)


class EmailConnectionFactory:
    """Factory for selecting appropriate email backend based on configuration priority."""

    @staticmethod
    def get_backend(association_id: int | None = None, run_id: int | None = None):
        """Return appropriate email backend following priority order. """

        # Priority 1: Event-level custom SMTP
        if run_id:
            event_smtp_config = _get_event_smtp_config(run_id)
            if event_smtp_config:
                logger.debug(f"Using event-level SMTP for run_id={run_id}")
                return SMTPEmailBackend(event_smtp_config)

        # Priority 2: Association-level custom SMTP
        if association_id:
            assoc_smtp_config = _get_association_smtp_config(association_id)
            if assoc_smtp_config:
                logger.debug(f"Using association-level SMTP for association_id={association_id}")
                return SMTPEmailBackend(assoc_smtp_config)

        # Priority 3: Global Amazon SES
        if _is_ses_configured():
            logger.debug("Using Amazon SES backend")
            return SESEmailBackend()

        # Priority 4: Django default backend
        logger.debug("Using Django default email backend")
        return DefaultEmailBackend()


def _get_event_smtp_config(run_id: int) -> dict | None:
    """Get event-level SMTP configuration.

    Args:
        run_id: Run ID to fetch configuration for

    Returns:
        Dict with SMTP config or None if not configured
    """
    try:
        run = Run.objects.get(pk=run_id)
        event = run.event

        cache_context = {}

        # Check if event has custom SMTP host user configured
        host_user = get_event_config(
            event.id,
            "mail_server_host_user",
            default_value="",
            context=cache_context,
            bypass_cache=True,
        )

        if not host_user:
            return None

        # Return SMTP configuration
        return {
            'host': get_event_config(
                event.id,
                "mail_server_host",
                default_value="",
                context=cache_context,
                bypass_cache=True,
            ),
            'port': get_event_config(
                event.id,
                "mail_server_port",
                default_value="",
                context=cache_context,
                bypass_cache=True,
            ),
            'username': host_user,
            'password': get_event_config(
                event.id,
                "mail_server_host_password",
                default_value="",
                context=cache_context,
                bypass_cache=True,
            ),
            'use_tls': get_event_config(
                event.id,
                "mail_server_use_tls",
                default_value=False,
                context=cache_context,
                bypass_cache=True,
            ),
        }

    except Run.DoesNotExist:
        logger.warning(f"Run with id={run_id} not found")
        return None


def _get_association_smtp_config(association_id: int) -> dict | None:
    """Get association-level SMTP configuration.

    Args:
        association_id: Association ID to fetch configuration for

    Returns:
        Dict with SMTP config or None if not configured
    """

    try:
        association = Association.objects.get(pk=association_id)

        # Check if association has custom SMTP host user configured
        host_user = association.get_config("mail_server_host_user", default_value="", bypass_cache=True)

        if not host_user:
            return None

        # Return SMTP configuration
        return {
            'host': association.get_config("mail_server_host", default_value="", bypass_cache=True),
            'port': association.get_config("mail_server_port", default_value="", bypass_cache=True),
            'username': host_user,
            'password': association.get_config("mail_server_host_password", default_value="", bypass_cache=True),
            'use_tls': association.get_config("mail_server_use_tls", default_value=False, bypass_cache=True),
        }

    except Association.DoesNotExist:
        logger.warning(f"Association with id={association_id} not found")
        return None


def _is_ses_configured() -> bool:
    """Check if Amazon SES is configured in settings.

    Returns:
        True if all required SES settings are present, False otherwise
    """

    return all([
        getattr(settings, 'AWS_SES_ACCESS_KEY_ID', None),
        getattr(settings, 'AWS_SES_SECRET_ACCESS_KEY', None),
        getattr(settings, 'AWS_SES_REGION_NAME', None),
    ])
