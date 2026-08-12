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
"""Verification and handling of Amazon SNS notifications carrying SES events."""

from __future__ import annotations

import base64
import json
import logging
import re
import urllib.request
from typing import Any
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509 import load_pem_x509_certificate
from django.conf import settings as conf_settings
from django.core.cache import cache

from larpmanager.mail.suppression import suppress_email
from larpmanager.models.miscellanea import SuppressionReason

logger = logging.getLogger(__name__)

# Fields signed by SNS, in the order required to rebuild the canonical string
SIGNED_FIELDS = {
    "Notification": ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"),
    "SubscriptionConfirmation": ("Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"),
    "UnsubscribeConfirmation": ("Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"),
}

# Only the SNS service endpoints may host a signing certificate or a subscribe url
SNS_HOST_RE = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com$")

CERT_CACHE_TIMEOUT = 86400

CERT_FETCH_TIMEOUT = 10

# Notifications already processed are ignored for this long
DEDUP_TIMEOUT = 86400


def _is_aws_url(url: str) -> bool:
    """Check that a url points to an https endpoint owned by the SNS service.

    Only sns.<region>.amazonaws.com is accepted.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = parsed.netloc.split(":")[0].lower()
    return bool(SNS_HOST_RE.match(host))


def _canonical_string(payload: dict[str, Any]) -> bytes:
    """Build the string signed by SNS for this payload."""
    fields = SIGNED_FIELDS.get(payload.get("Type", ""))
    if not fields:
        msg = "Unknown SNS message type"
        raise ValueError(msg)
    parts = []
    for field in fields:
        if field not in payload:
            continue
        parts.append(f"{field}\n{payload[field]}\n")
    return "".join(parts).encode()


def _fetch_certificate(url: str) -> Any:
    """Download and cache the SNS signing certificate."""
    cached = cache.get(f"sns_cert_{url}")
    if cached:
        return load_pem_x509_certificate(cached)

    with urllib.request.urlopen(url, timeout=CERT_FETCH_TIMEOUT) as response:  # noqa: S310
        pem = response.read()
    cache.set(f"sns_cert_{url}", pem, CERT_CACHE_TIMEOUT)
    return load_pem_x509_certificate(pem)


def verify_sns_signature(payload: dict[str, Any]) -> bool:
    """Verify the RSA signature of an SNS payload against its signing certificate.

    Without this check any client could post forged bounces and poison the
    suppression list, so a failure must discard the notification.
    """
    signature_b64 = payload.get("Signature")
    cert_url = payload.get("SigningCertURL") or payload.get("SigningCertUrl")
    if not signature_b64 or not cert_url or not _is_aws_url(cert_url):
        logger.warning("SNS payload rejected: missing signature or untrusted certificate url")
        return False

    topic_arn = getattr(conf_settings, "AWS_SNS_TOPIC_ARN", None)
    if not topic_arn:
        logger.warning("SNS payload rejected: AWS_SNS_TOPIC_ARN is not configured")
        return False
    if payload.get("TopicArn") != topic_arn:
        logger.warning("SNS payload rejected: unexpected topic")
        return False

    try:
        certificate = _fetch_certificate(cert_url)
        public_key = certificate.public_key()
        if not isinstance(public_key, rsa.RSAPublicKey):
            logger.warning("SNS payload rejected: certificate key is not RSA")
            return False
        # SHA1 is imposed by SNS signature version 1, still the default on many topics
        algorithm = hashes.SHA256() if str(payload.get("SignatureVersion")) == "2" else hashes.SHA1()  # noqa: S303
        public_key.verify(
            base64.b64decode(signature_b64),
            _canonical_string(payload),
            padding.PKCS1v15(),
            algorithm,
        )
    except (InvalidSignature, ValueError, OSError) as exc:
        logger.warning("SNS payload rejected: signature verification failed (%s)", exc)
        return False

    return True


def _confirm_subscription(payload: dict[str, Any]) -> None:
    """Confirm an SNS subscription by calling back the provided url."""
    subscribe_url = payload.get("SubscribeURL", "")
    if not _is_aws_url(subscribe_url):
        logger.warning("SNS subscription confirmation rejected: untrusted url")
        return
    with urllib.request.urlopen(subscribe_url, timeout=CERT_FETCH_TIMEOUT):  # noqa: S310
        logger.info("SNS subscription confirmed for topic %s", payload.get("TopicArn"))


def _bounce_reason(bounce: dict[str, Any]) -> str:
    """Map an SES bounce type to a suppression reason."""
    if bounce.get("bounceType") == "Permanent":
        return SuppressionReason.BOUNCE_PERMANENT
    return SuppressionReason.BOUNCE_TRANSIENT


def _handle_ses_message(message: dict[str, Any]) -> None:
    """Record suppressions for the recipients of a bounce or complaint event."""
    notification_type = message.get("notificationType") or message.get("eventType")

    if notification_type == "Bounce":
        bounce = message.get("bounce", {})
        reason = _bounce_reason(bounce)
        for recipient in bounce.get("bouncedRecipients", []):
            suppress_email(recipient.get("emailAddress", ""), reason, raw=recipient)
        return

    if notification_type == "Complaint":
        complaint = message.get("complaint", {})
        for recipient in complaint.get("complainedRecipients", []):
            suppress_email(recipient.get("emailAddress", ""), SuppressionReason.COMPLAINT, raw=complaint)
        return

    logger.debug("SES notification ignored: %s", notification_type)


def handle_sns_payload(payload: dict[str, Any]) -> bool:
    """Process a verified SNS payload, returning whether it was handled.

    Notifications are deduplicated on their SNS message id, so retries from
    Amazon do not inflate bounce counters.
    """
    message_type = payload.get("Type")

    if message_type == "SubscriptionConfirmation":
        _confirm_subscription(payload)
        return True

    if message_type != "Notification":
        logger.debug("SNS message ignored: %s", message_type)
        return False

    message_id = payload.get("MessageId")
    dedup_key = f"sns_seen_{message_id}" if message_id else ""
    if dedup_key and cache.get(dedup_key):
        logger.info("SNS notification already processed: %s", message_id)
        return True

    try:
        message = json.loads(payload.get("Message", "{}"))
    except json.JSONDecodeError:
        logger.warning("SNS notification carries an invalid message body")
        return False

    _handle_ses_message(message)

    # Marked as seen only once handled, so that a retry of a failed delivery is not discarded
    if dedup_key:
        cache.set(dedup_key, 1, DEDUP_TIMEOUT)

    return True
