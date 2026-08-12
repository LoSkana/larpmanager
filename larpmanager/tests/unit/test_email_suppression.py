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

"""Unit tests for the email suppression list and the SES/SNS notification flow."""

import base64
import datetime
import json
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from django.core.cache import cache

from larpmanager.mail.sns import _canonical_string, handle_sns_payload, verify_sns_signature
from larpmanager.mail.suppression import (
    SOFT_BOUNCE_LIMIT,
    is_suppressed,
    suppress_email,
    unsuppress_email,
)
from larpmanager.models.miscellanea import EmailContent, EmailRecipient, EmailSuppression, SuppressionReason
from larpmanager.tests.unit.base import BaseTestCase

CERT_URL = "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-abc.pem"


def build_certificate():
    """Return a self signed certificate and its private key for signature tests."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return certificate, key


def sign_payload(payload: dict, key) -> dict:
    """Return the payload with a valid SNS signature computed with the given key."""
    payload = dict(payload)
    payload["SignatureVersion"] = "1"
    payload["SigningCertURL"] = CERT_URL
    signature = key.sign(_canonical_string(payload), padding.PKCS1v15(), hashes.SHA1())
    payload["Signature"] = base64.b64encode(signature).decode()
    return payload


def bounce_payload(email: str, bounce_type: str = "Permanent", message_id: str = "msg-1") -> dict:
    """Return an SNS notification payload carrying an SES bounce."""
    message = {
        "notificationType": "Bounce",
        "bounce": {
            "bounceType": bounce_type,
            "bouncedRecipients": [{"emailAddress": email}],
        },
    }
    return {
        "Type": "Notification",
        "MessageId": message_id,
        "TopicArn": "arn:aws:sns:eu-west-1:1:topic",
        "Timestamp": "2026-01-01T00:00:00.000Z",
        "Message": json.dumps(message),
    }


class TestSuppressionList(BaseTestCase):
    """Tests for recording and releasing suppressed addresses."""

    def setUp(self):
        """Clear the suppression cache between tests."""
        cache.clear()

    def test_permanent_bounce_suppresses_immediately(self):
        """A single permanent bounce blocks the address."""
        suppress_email("dead@example.com", SuppressionReason.BOUNCE_PERMANENT)

        assert is_suppressed("dead@example.com")
        assert is_suppressed("DEAD@example.com")

    def test_complaint_suppresses_immediately(self):
        """A complaint blocks the address at the first event."""
        suppress_email("angry@example.com", SuppressionReason.COMPLAINT)

        assert is_suppressed("angry@example.com")

    def test_transient_bounce_needs_repeated_failures(self):
        """Transient bounces accumulate before blocking the address."""
        for _index in range(SOFT_BOUNCE_LIMIT - 1):
            suppress_email("full@example.com", SuppressionReason.BOUNCE_TRANSIENT)
            cache.clear()
            assert not is_suppressed("full@example.com")

        suppress_email("full@example.com", SuppressionReason.BOUNCE_TRANSIENT)
        cache.clear()
        assert is_suppressed("full@example.com")

    def test_unsuppress_releases_address(self):
        """Releasing an address clears the block and the counter."""
        suppress_email("back@example.com", SuppressionReason.BOUNCE_PERMANENT)

        with patch("larpmanager.mail.suppression._ses_delete_suppressed_destination"):
            unsuppress_email("back@example.com")

        assert not is_suppressed("back@example.com")
        assert EmailSuppression.objects.get(email="back@example.com").bounce_count == 0

    def test_invalid_address_is_ignored(self):
        """Malformed addresses never enter the suppression list."""
        assert suppress_email("not-an-email", SuppressionReason.MANUAL) is None
        assert EmailSuppression.objects.count() == 0


class TestSnsSignature(BaseTestCase):
    """Tests for the verification of SNS payload signatures."""

    def setUp(self):
        """Build a signing certificate and clear caches."""
        cache.clear()
        self.certificate, self.key = build_certificate()
        self.pem = self.certificate.public_bytes(serialization.Encoding.PEM)

    def test_valid_signature_accepted(self):
        """A payload signed by the advertised certificate is accepted."""
        payload = sign_payload(bounce_payload("a@example.com"), self.key)

        with patch("larpmanager.mail.sns._fetch_certificate", return_value=self.certificate):
            assert verify_sns_signature(payload)

    def test_tampered_payload_rejected(self):
        """Editing a signed field invalidates the signature."""
        payload = sign_payload(bounce_payload("a@example.com"), self.key)
        payload["Message"] = json.dumps({"notificationType": "Bounce"})

        with patch("larpmanager.mail.sns._fetch_certificate", return_value=self.certificate):
            assert not verify_sns_signature(payload)

    def test_untrusted_certificate_url_rejected(self):
        """Certificates served outside amazonaws.com are refused."""
        payload = sign_payload(bounce_payload("a@example.com"), self.key)
        payload["SigningCertURL"] = "https://evil.example.com/cert.pem"

        with patch("larpmanager.mail.sns._fetch_certificate", return_value=self.certificate) as mock_fetch:
            assert not verify_sns_signature(payload)
            mock_fetch.assert_not_called()

    def test_missing_signature_rejected(self):
        """Unsigned payloads are refused."""
        assert not verify_sns_signature(bounce_payload("a@example.com"))

    def test_unexpected_topic_rejected(self):
        """Payloads from another topic are refused when the topic is pinned."""
        payload = sign_payload(bounce_payload("a@example.com"), self.key)

        with (
            patch("larpmanager.mail.sns.conf_settings.AWS_SNS_TOPIC_ARN", "arn:aws:sns:eu-west-1:1:other", create=True),
            patch("larpmanager.mail.sns._fetch_certificate", return_value=self.certificate),
        ):
            assert not verify_sns_signature(payload)


class TestSnsHandling(BaseTestCase):
    """Tests for the processing of verified SNS payloads."""

    def setUp(self):
        """Clear caches between tests."""
        cache.clear()

    def test_permanent_bounce_recorded(self):
        """A permanent bounce notification suppresses the recipient."""
        handle_sns_payload(bounce_payload("gone@example.com"))

        suppression = EmailSuppression.objects.get(email="gone@example.com")
        assert suppression.reason == SuppressionReason.BOUNCE_PERMANENT
        assert suppression.active

    def test_transient_bounce_recorded_without_blocking(self):
        """A transient bounce is tracked but does not block the address."""
        handle_sns_payload(bounce_payload("busy@example.com", bounce_type="Transient"))

        suppression = EmailSuppression.objects.get(email="busy@example.com")
        assert suppression.reason == SuppressionReason.BOUNCE_TRANSIENT
        assert not suppression.active

    def test_complaint_recorded(self):
        """A complaint notification suppresses the recipient."""
        message = {
            "notificationType": "Complaint",
            "complaint": {"complainedRecipients": [{"emailAddress": "spam@example.com"}]},
        }
        payload = bounce_payload("unused@example.com")
        payload["Message"] = json.dumps(message)

        handle_sns_payload(payload)

        assert EmailSuppression.objects.get(email="spam@example.com").reason == SuppressionReason.COMPLAINT

    def test_duplicate_notification_ignored(self):
        """Replayed notifications do not inflate the bounce counter."""
        payload = bounce_payload("dup@example.com", bounce_type="Transient", message_id="same-id")

        handle_sns_payload(payload)
        handle_sns_payload(payload)

        assert EmailSuppression.objects.get(email="dup@example.com").bounce_count == 1

    def test_delivery_notification_ignored(self):
        """Delivery events do not create suppressions."""
        payload = bounce_payload("ok@example.com")
        payload["Message"] = json.dumps({"notificationType": "Delivery"})

        handle_sns_payload(payload)

        assert EmailSuppression.objects.count() == 0

    def test_subscription_confirmation_calls_back_aws(self):
        """Subscription confirmations are completed by calling the AWS url."""
        payload = {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "https://sns.eu-west-1.amazonaws.com/?Action=ConfirmSubscription",
        }

        with patch("larpmanager.mail.sns.urllib.request.urlopen") as mock_open:
            assert handle_sns_payload(payload)
            mock_open.assert_called_once()

    def test_subscription_confirmation_ignores_foreign_url(self):
        """Subscription confirmations pointing outside AWS are not followed."""
        payload = {"Type": "SubscriptionConfirmation", "SubscribeURL": "https://evil.example.com/"}

        with patch("larpmanager.mail.sns.urllib.request.urlopen") as mock_open:
            handle_sns_payload(payload)
            mock_open.assert_not_called()


class TestSuppressionOnSend(BaseTestCase):
    """Tests that suppressed addresses are never contacted."""

    def setUp(self):
        """Clear caches between tests."""
        cache.clear()

    def _build_recipient(self, email: str) -> EmailRecipient:
        """Create a queued email for the given address."""
        content = EmailContent.objects.create(subj="Subject", body="Body")
        return EmailRecipient.objects.create(email_content=content, recipient=email)

    def test_suppressed_recipient_is_skipped(self):
        """A suppressed address is flagged and never handed to the backend."""
        from larpmanager.utils.larpmanager.tasks import my_send_mail_bkg

        suppress_email("blocked@example.com", SuppressionReason.COMPLAINT)
        recipient = self._build_recipient("blocked@example.com")

        with patch("larpmanager.utils.larpmanager.tasks.my_send_simple_mail") as mock_send:
            my_send_mail_bkg.task_function(recipient.pk)
            mock_send.assert_not_called()

        recipient.refresh_from_db()
        assert recipient.skipped == "suppressed"
        assert recipient.sent is None

    def test_regular_recipient_is_sent(self):
        """A clean address is delivered and gets a one-click unsubscribe link."""
        from larpmanager.utils.larpmanager.tasks import my_send_mail_bkg

        recipient = self._build_recipient("clean@example.com")

        with patch("larpmanager.utils.larpmanager.tasks.my_send_simple_mail") as mock_send:
            my_send_mail_bkg.task_function(recipient.pk)
            mock_send.assert_called_once()
            unsubscribe_url = mock_send.call_args[0][8]
            assert "unsubscribe/" in unsubscribe_url

        recipient.refresh_from_db()
        assert recipient.skipped is None
        assert recipient.sent is not None


class TestUnsubscribeHeaders(BaseTestCase):
    """Tests for the RFC 8058 one-click unsubscribe headers."""

    def test_one_click_headers_present(self):
        """The unsubscribe link is published together with the one-click marker."""
        from larpmanager.utils.larpmanager.tasks import _prepare_email_metadata

        metadata = _prepare_email_metadata(None, None, None, "https://larpmanager.com/unsubscribe/abc/")

        assert metadata["headers"]["List-Unsubscribe"].startswith("<https://larpmanager.com/unsubscribe/abc/>")
        assert metadata["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    def test_one_click_marker_absent_without_link(self):
        """Without a link only the mailto form is published."""
        from larpmanager.utils.larpmanager.tasks import _prepare_email_metadata

        metadata = _prepare_email_metadata(None, None, None)

        assert metadata["headers"]["List-Unsubscribe"].startswith("<mailto:")
        assert "List-Unsubscribe-Post" not in metadata["headers"]
