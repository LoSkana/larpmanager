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

"""Unit tests for the CSP violation report endpoint and the daily digest."""

import json
from http import HTTPStatus
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.larpmanager.csp import pop_csp_reports, record_csp_report, send_csp_digest


def build_report(**fields):
    """Return a legacy report-uri payload with sensible defaults."""
    report = {
        "document-uri": "https://test.larpmanager.com/event/?token=secret",
        "effective-directive": "script-src-elem",
        "blocked-uri": "inline",
        "source-file": "https://test.larpmanager.com/event/",
        "line-number": 42,
    }
    report.update(fields)
    return {"csp-report": report}


class TestCspAggregation(BaseTestCase):
    """Tests that reports are grouped by violation and cleared by the digest."""

    def setUp(self):
        """Start from an empty cache."""
        cache.clear()

    def test_same_violation_is_counted_once(self):
        """Repeated reports of the same violation share a single counter."""
        for _unused in range(3):
            assert record_csp_report(build_report())
        record_csp_report(build_report(**{"line-number": 7}))

        violations = pop_csp_reports()

        assert [violation["count"] for violation in violations] == [3, 1]
        assert pop_csp_reports() == []

    def test_querystring_is_stripped(self):
        """Tokens in the page URL never reach the digest."""
        record_csp_report(build_report())

        assert pop_csp_reports()[0]["document"] == "https://test.larpmanager.com/event/"

    def test_extension_and_malformed_reports_are_discarded(self):
        """Browser extension noise and payloads without a report are ignored."""
        assert not record_csp_report(build_report(**{"blocked-uri": "chrome-extension://abc/inject.js"}))
        assert not record_csp_report({"other": {}})
        assert not record_csp_report([])

        assert pop_csp_reports() == []

    def test_digest_escapes_report_content(self):
        """Report fields are attacker controlled, so they are escaped in the email."""
        record_csp_report(build_report(**{"blocked-uri": "<script>alert(1)</script>"}))

        with patch("larpmanager.utils.larpmanager.csp.notify_admins") as notify:
            send_csp_digest()

        body = notify.call_args.args[1]
        assert "<script>" not in body
        assert "&lt;script&gt;" in body

    def test_digest_skipped_without_reports(self):
        """No email is sent when nothing was reported."""
        with patch("larpmanager.utils.larpmanager.csp.notify_admins") as notify:
            send_csp_digest()

        notify.assert_not_called()


class TestCspReportEndpoint(BaseTestCase):
    """Tests the public endpoint receiving browser reports."""

    def setUp(self):
        """Start from an empty cache, with CSRF enforced as for a real browser."""
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)

    def test_report_is_recorded(self):
        """A valid report is accepted without a CSRF token."""
        response = self.client.post(
            reverse("csp_report"), json.dumps(build_report()), content_type="application/csp-report"
        )

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert pop_csp_reports()[0]["count"] == 1

    def test_invalid_body_is_rejected(self):
        """A body that is not JSON is refused."""
        response = self.client.post(reverse("csp_report"), "not json", content_type="application/csp-report")

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_get_not_allowed(self):
        """Only POST is accepted."""
        assert self.client.get(reverse("csp_report")).status_code == HTTPStatus.METHOD_NOT_ALLOWED
