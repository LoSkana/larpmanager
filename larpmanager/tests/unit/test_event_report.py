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
"""Unit tests for the event report sent by secondary installations to the main deployment."""

import json
from http import HTTPStatus
from typing import Any
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse

from larpmanager.models.event import DevelopStatus, Run
from larpmanager.models.larpmanager import LarpManagerEventReport
from larpmanager.models.miscellanea import Log
from larpmanager.models.registration import Registration, RegistrationTicket
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.larpmanager import event_report


@override_settings(EVENT_REPORT="https://main.test/event-report/")
class TestEventReportSender(BaseTestCase):
    """Tests the build and the sending of the run reports."""

    def setUp(self) -> None:
        """Never reach the network from the save signals."""
        super().setUp()
        post_patch = patch("larpmanager.utils.larpmanager.event_report.requests.post")
        post_patch.start()
        self.addCleanup(post_patch.stop)

    def test_report_counts_signups_by_ticket(self) -> None:
        """Only active registrations are counted, grouped by ticket name."""
        registration = self.get_registration()
        run = registration.run
        ticket = RegistrationTicket.objects.filter(event=run.event).first() or RegistrationTicket.objects.create(
            event=run.event, name="Report ticket", number=99
        )
        Registration.objects.filter(pk=registration.pk).update(ticket=ticket, cancellation_date=None, pending=False)
        Registration.objects.filter(run=run).exclude(pk=registration.pk).delete()

        report = event_report.build_run_report(run)

        assert report["association"]["uuid"] == run.event.association.uuid
        assert report["run"]["uuid"] == run.uuid
        assert report["event"]["name"] == run.event.name
        counts = {ticket["name"]: ticket["signups"] for ticket in report["tickets"]}
        assert counts[ticket.name] == 1
        assert report["signups_total"] == 1

        Registration.objects.filter(pk=registration.pk).update(pending=True)
        report = event_report.build_run_report(run)
        assert report["signups_total"] == 0

    @patch("larpmanager.utils.larpmanager.event_report.requests.post")
    def test_send_posts_payload(self, mock_post: Any) -> None:
        """The report is posted to the configured URL."""
        mock_post.return_value = MagicMock(ok=True)
        run = self.get_run()

        event_report.send_run_report(run.id)

        args, kwargs = mock_post.call_args
        assert args[0] == "https://main.test/event-report/"
        assert kwargs["json"]["run"]["uuid"] == run.uuid
        assert kwargs["headers"][event_report.EVENT_REPORT_TOKEN_HEADER] == event_report.get_event_report_token()

    @patch("larpmanager.utils.larpmanager.event_report.send_run_report")
    def test_daily_send_skips_concluded_runs(self, mock_send: Any) -> None:
        """The daily sending skips concluded and cancelled runs."""
        run = self.get_run()
        Run.objects.filter(pk=run.pk).update(development=DevelopStatus.DONE)
        mock_send.reset_mock()

        event_report.send_all_run_reports()

        sent = {call.args[0] for call in mock_send.call_args_list}
        assert run.id not in sent
        assert sent == set(
            Run.objects.filter(event__template=False)
            .exclude(development__in=[DevelopStatus.DONE, DevelopStatus.CANC])
            .values_list("id", flat=True)
        )

    @patch("larpmanager.utils.larpmanager.event_report.requests.post")
    def test_send_errors_are_ignored(self, mock_post: Any) -> None:
        """A failing request or report build never raises in the sending installation."""
        run = self.get_run()
        mock_post.side_effect = RuntimeError("down")
        event_report.send_run_report(run.id)

        with patch("larpmanager.utils.larpmanager.event_report.build_run_report", side_effect=ValueError):
            event_report.send_run_report(run.id)
            run.save()
            run.event.save()

        with patch(
            "larpmanager.utils.larpmanager.event_report._send_run_report_task", side_effect=RuntimeError("queue")
        ):
            event_report.send_all_run_reports()

    @patch("larpmanager.utils.larpmanager.event_report.send_run_report")
    def test_event_save_sends_all_runs(self, mock_send: Any) -> None:
        """Saving an event sends the report of each of its runs."""
        event = self.get_event()

        event.save()

        sent = {call.args[0] for call in mock_send.call_args_list}
        assert sent == set(event.runs.values_list("id", flat=True))

    @override_settings(EVENT_REPORT=None)
    @patch("larpmanager.utils.larpmanager.event_report.requests.post")
    def test_nothing_sent_without_url(self, mock_post: Any) -> None:
        """An installation without the URL, as the main deployment, never sends."""
        event_report.send_run_report(self.get_run().id)
        event_report.send_all_run_reports()

        mock_post.assert_not_called()


class TestEventReportReceiver(BaseTestCase):
    """Tests the endpoint storing the reports on the main deployment."""

    def setUp(self) -> None:
        """Act as the main installation."""
        super().setUp()
        self.settings_override = override_settings(EVENT_REPORT=None)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.client = Client()
        cache.clear()

    def post(self, payload: Any, token: str = "installation-token") -> Any:
        """Post a payload to the endpoint, with the token of the sending installation."""
        return self.client.post(
            reverse("event_report"),
            json.dumps(payload),
            content_type="application/json",
            headers={event_report.EVENT_REPORT_TOKEN_HEADER: token},
        )

    @staticmethod
    def payload(association_uuid: str = "abc123", run_uuid: str = "def456") -> dict:
        """Return a minimal valid report."""
        return {"association": {"uuid": association_uuid, "name": "Org"}, "run": {"uuid": run_uuid}}

    def test_token_is_bound_to_association(self) -> None:
        """Once an association has reported, only its token can send or overwrite its reports."""
        assert self.post(self.payload()).status_code == HTTPStatus.OK

        assert self.post(self.payload(), token="attacker").status_code == HTTPStatus.FORBIDDEN
        assert self.post(self.payload(run_uuid="other"), token="attacker").status_code == HTTPStatus.FORBIDDEN
        assert self.post(self.payload(run_uuid="other")).status_code == HTTPStatus.OK
        assert LarpManagerEventReport.objects.filter(association_uuid="abc123").count() == 2

        assert self.post(self.payload(association_uuid="xyz"), token="attacker").status_code == HTTPStatus.OK

    def test_missing_token_is_rejected(self) -> None:
        """Reports without a token are refused."""
        response = self.post(self.payload(), token="")

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert not LarpManagerEventReport.objects.exists()

    def test_cleared_token_is_bound_again(self) -> None:
        """Clearing the stored hash, as after a SECRET_KEY change, binds the next token."""
        self.post(self.payload())
        LarpManagerEventReport.objects.update(token_hash="")

        assert self.post(self.payload(), token="new-token").status_code == HTTPStatus.OK
        assert self.post(self.payload()).status_code == HTTPStatus.FORBIDDEN

    def test_new_associations_per_ip_are_limited(self) -> None:
        """A single IP address cannot create unlimited associations."""
        with patch.object(event_report, "MAX_NEW_ASSOCIATIONS_PER_IP", 2):
            assert self.post(self.payload(association_uuid="a1")).status_code == HTTPStatus.OK
            assert self.post(self.payload(association_uuid="a2")).status_code == HTTPStatus.OK
            assert self.post(self.payload(association_uuid="a3")).status_code == HTTPStatus.TOO_MANY_REQUESTS
            assert self.post(self.payload(association_uuid="a1", run_uuid="r2")).status_code == HTTPStatus.OK

    def test_report_is_saved_by_uuids(self) -> None:
        """A valid report is stored once per run, the latest replacing the previous one."""
        payload = {
            "association": {"uuid": "abc123", "name": "Remote org"},
            "event": {"name": "Remote event"},
            "run": {"uuid": "def456"},
            "tickets": [],
            "signups_total": 7,
        }

        response = self.post(payload)

        assert response.status_code == HTTPStatus.OK
        report = LarpManagerEventReport.objects.get(association_uuid="abc123", run_uuid="def456")
        assert report.association_name == "Remote org"
        assert report.event_name == "Remote event"
        saved = json.loads(report.data)
        assert saved["tickets"] == []
        assert "received_at" in saved

        payload["signups_total"] = 9
        assert self.post(payload).status_code == HTTPStatus.OK
        report = LarpManagerEventReport.objects.get(association_uuid="abc123", run_uuid="def456")
        assert json.loads(report.data)["signups_total"] == 9

        log = Log.objects.filter(cls="EventReport", info="abc123_def456").order_by("id").first()
        assert log.element_name == "Remote event"
        assert json.loads(log.dct)["signups_total"] == 7

    def test_unsafe_uuid_is_rejected(self) -> None:
        """Uuids that could escape the reports folder are refused."""
        response = self.post({"association": {"uuid": "../etc"}, "run": {"uuid": "def"}})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert not LarpManagerEventReport.objects.exists()
        assert not Log.objects.filter(cls="EventReport").exists()

    def test_endpoint_disabled_on_sending_installations(self) -> None:
        """Installations that send their reports do not receive any."""
        with override_settings(EVENT_REPORT="https://main.test/event-report/"):
            response = self.post({"association": {"uuid": "abc"}, "run": {"uuid": "def"}})

        assert response.status_code == HTTPStatus.NOT_FOUND
