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

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone

from larpmanager.cache.config import save_all_element_configs, save_single_config
from larpmanager.cache.widget import get_widget_cache_key
from larpmanager.forms.event import validate_latitude, validate_longitude
from larpmanager.models.association import Association
from larpmanager.models.event import DevelopStatus, Run
from larpmanager.models.larpmanager import LarpManagerDemoType
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.publication import base, ildb, radar


def radar_response(status: int, body: dict | None = None, headers: dict | None = None) -> MagicMock:
    """Build a fake LARP Radar HTTP response."""
    response = MagicMock(status_code=status, ok=status < 400, text=str(body), headers=headers or {})
    response.json.return_value = body or {}
    return response


@override_settings(LARP_RADAR_API_KEY="secret", LARP_RADAR_ORIGIN="https://partner.test")
@patch("larpmanager.utils.publication.radar.time_module.sleep")
class TestRadarPublication(BaseTestCase):
    """Test the export of runs towards the LARP Radar partner API."""

    def setUp(self) -> None:
        super().setUp()
        self.event = self.get_event()
        self.event.description = "<p>Description</p>"
        self.association = self.event.association
        tomorrow = timezone.localdate() + timedelta(days=1)
        self.run = self.get_run()
        Run.objects.filter(pk=self.run.pk).update(
            development=DevelopStatus.SHOW, start=tomorrow, end=tomorrow + timedelta(days=2)
        )
        self.run.refresh_from_db()
        self.configs = {"pub_lat": "43.46", "pub_lon": "11.87"}
        self.config_patch = patch(
            "larpmanager.utils.publication.radar.get_element_config",
            side_effect=lambda _element, name: self.configs.get(name, ""),
        )
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        cache.delete_many(
            [
                f"rl_radar_duplicate_{self.run.id}",
                f"rl_radar_put_failed_{self.run.id}_400",
                f"rl_radar_no_url_{self.run.id}",
                f"rl_radar_sync_failed_{self.run.id}",
            ]
        )
        self.notify_patch = patch("larpmanager.utils.publication.radar._notify_association")
        self.mock_notify = self.notify_patch.start()
        self.addCleanup(self.notify_patch.stop)

    def stored_url(self) -> str:
        """Return the Radar url stored on a fresh instance, as configs are memoized on the element."""
        return Run.objects.get(pk=self.run.pk).get_config(radar.RADAR_RUN_CONFIG)

    def sync(self) -> None:
        """Run the sync over the test run only, with the integration enabled."""
        with (
            patch("larpmanager.utils.publication.radar.get_association_features", return_value={"publisher": 1}),
            patch("larpmanager.utils.publication.radar.get_association_config", return_value=True),
            patch("larpmanager.utils.publication.radar.get_event_runs", return_value=[self.run]),
        ):
            radar.sync_event(self.event)

    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_first_publication_sends_payload_and_stores_url(self, mock_put: Any, _sleep: Any) -> None:
        mock_put.return_value = radar_response(201, {"url": "/it/event", "created": True})

        self.sync()

        args, kwargs = mock_put.call_args
        assert args[0] == f"https://larp-radar.com/api/partner/v1/events/{self.run.uuid}/"
        assert kwargs["headers"]["X-Api-Key"] == "secret"
        assert kwargs["headers"]["Origin"] == "https://partner.test"
        payload = kwargs["json"]
        assert payload["description"] == "Description"
        assert payload["category"] == "other"
        assert payload["coordinates"] == {"latitude": 43.46, "longitude": 11.87}
        assert payload["status"] == "enabled"
        assert payload["organizer"]["external_id"] == self.association.uuid
        assert payload["organizer"]["name"] == self.association.name
        assert payload["tickets"].endswith(f"/{self.run.get_slug()}/register/")
        assert self.stored_url() == "https://larp-radar.com/it/event"
        self.mock_notify.assert_called_once()

    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_update_does_not_notify_again(self, mock_put: Any, _sleep: Any) -> None:
        save_single_config(self.run, radar.RADAR_RUN_CONFIG, "https://larp-radar.com/it/event")
        mock_put.return_value = radar_response(200, {"url": "/it/event", "created": False})

        self.sync()

        mock_put.assert_called_once()
        self.mock_notify.assert_not_called()

    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_missing_coordinates_skip_the_run(self, mock_put: Any, _sleep: Any) -> None:
        self.configs.clear()

        self.sync()

        mock_put.assert_not_called()

    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_ineligible_runs_are_skipped(self, mock_put: Any, _sleep: Any) -> None:
        for development in (DevelopStatus.START, DevelopStatus.DONE, DevelopStatus.CANC):
            self.run.development = development
            self.sync()
        self.run.development = DevelopStatus.SHOW
        self.run.end = timezone.localdate() - timedelta(days=1)
        self.sync()

        mock_put.assert_not_called()

    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_cancelled_run_already_published_sends_status(self, mock_put: Any, _sleep: Any) -> None:
        save_single_config(self.run, radar.RADAR_RUN_CONFIG, "https://larp-radar.com/it/event")
        self.run.development = DevelopStatus.CANC
        mock_put.return_value = radar_response(200, {"url": "/it/event"})

        self.sync()

        assert mock_put.call_args.kwargs["json"]["status"] == "cancelled"

    @patch("larpmanager.utils.publication.radar.notify_admins")
    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_conflict_is_not_retried_nor_notified(self, mock_put: Any, mock_admins: Any, _sleep: Any) -> None:
        mock_put.return_value = radar_response(409, {"code": "event_locked"})

        self.sync()

        mock_put.assert_called_once()
        mock_admins.assert_not_called()
        assert not self.stored_url()

    @patch("larpmanager.utils.publication.radar.notify_admins")
    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_duplicate_notifies_admins_once_a_day(self, mock_put: Any, mock_admins: Any, _sleep: Any) -> None:
        mock_put.return_value = radar_response(409, {"code": "event_duplicate"})

        self.sync()
        self.sync()

        assert mock_put.call_count == 2  # noqa: PLR2004
        mock_admins.assert_called_once()
        assert not self.stored_url()

    @patch("larpmanager.utils.publication.radar.notify_admins")
    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_invalid_payload_notifies_admins_once_a_day(self, mock_put: Any, mock_admins: Any, _sleep: Any) -> None:
        mock_put.return_value = radar_response(400, {"code": "invalid"})

        self.sync()
        self.sync()

        assert mock_put.call_count == 2  # noqa: PLR2004
        mock_admins.assert_called_once()
        assert str(self.run.id) in mock_admins.call_args.args[0]

    @patch("larpmanager.utils.publication.radar.notify_admins")
    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_sync_errors_notify_admins_once_a_day(self, mock_put: Any, mock_admins: Any, _sleep: Any) -> None:
        mock_put.side_effect = requests.exceptions.ConnectionError()

        self.sync()
        self.sync()

        mock_admins.assert_called_once()

    @patch("larpmanager.utils.publication.radar.notify_admins")
    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_response_without_url_is_not_stored(self, mock_put: Any, mock_admins: Any, _sleep: Any) -> None:
        mock_put.return_value = radar_response(201, {"created": True})

        self.sync()

        mock_admins.assert_called_once()
        self.mock_notify.assert_not_called()
        assert not self.stored_url()

    @patch("larpmanager.models.signals.reset_widgets")
    def test_stored_url_refreshes_dashboard_actions(self, mock_reset: Any, _sleep: Any) -> None:
        save_single_config(self.run, radar.RADAR_RUN_CONFIG, "https://larp-radar.com/it/event")

        mock_reset.assert_called_once()

    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_temporary_failures_are_retried(self, mock_put: Any, _sleep: Any) -> None:
        mock_put.side_effect = [
            requests.exceptions.ConnectionError(),
            radar_response(429),
            radar_response(201, {"url": "/it/event"}),
        ]

        self.sync()

        assert mock_put.call_count == radar.RADAR_MAX_RETRIES
        assert self.stored_url()

    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_retry_after_is_honored_up_to_the_maximum_wait(self, mock_put: Any, mock_sleep: Any) -> None:
        mock_put.side_effect = [
            radar_response(429, headers={"Retry-After": "20"}),
            radar_response(429, headers={"Retry-After": "3600"}),
            radar_response(201, {"url": "/it/event"}),
        ]

        self.sync()

        waits = [call.args[0] for call in mock_sleep.call_args_list if call.args[0] != radar.RADAR_REQUEST_DELAY]
        assert waits == [20, radar.RADAR_MAX_RETRY_WAIT]

    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_hidden_event_is_skipped(self, mock_put: Any, _sleep: Any) -> None:
        self.event.visible = False

        self.sync()

        mock_put.assert_not_called()

    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_cancelled_run_of_hidden_event_sends_status(self, mock_put: Any, _sleep: Any) -> None:
        save_single_config(self.run, radar.RADAR_RUN_CONFIG, "https://larp-radar.com/it/event")
        self.event.visible = False
        self.run.development = DevelopStatus.CANC
        mock_put.return_value = radar_response(200, {"url": "/it/event"})

        self.sync()

        assert mock_put.call_args.kwargs["json"]["status"] == "cancelled"

    def test_publishable_runs_match_the_eligibility_rules(self, _sleep: Any) -> None:
        association_id = self.association.id
        assert self.run in radar.get_publishable_runs(association_id)

        type(self.event).objects.filter(pk=self.event.pk).update(visible=False)
        assert self.run not in radar.get_publishable_runs(association_id)

        type(self.event).objects.filter(pk=self.event.pk).update(visible=True)
        Run.objects.filter(pk=self.run.pk).update(start=None)
        assert self.run not in radar.get_publishable_runs(association_id)

    def test_description_is_plain_text_with_one_line_per_block(self, _sleep: Any) -> None:
        self.event.description = "<p>Citt&agrave; &amp; mare&nbsp;</p><p>Secondo<br />terzo</p><p>&nbsp;</p>"

        assert radar._get_description(self.event) == "Citt\u00e0 & mare\nSecondo\nterzo"  # noqa: SLF001

    def test_invalid_coordinates_are_not_used(self, _sleep: Any) -> None:
        for latitude, longitude in (("nan", "11"), ("inf", "11"), ("145", "11"), ("43", "-181")):
            self.configs.update({"pub_lat": latitude, "pub_lon": longitude})

            assert radar._get_coordinates(self.event) is None  # noqa: SLF001

    def test_unsupported_currency_omits_prices(self, _sleep: Any) -> None:
        with patch.object(type(self.association), "get_payment_currency_display", return_value="JPY"):
            payload = radar._build_event_payload(self.event, self.run)  # noqa: SLF001

        assert "currency" not in payload
        assert "ticket_min_price" not in payload

    def test_settings_map_to_a_single_category(self, _sleep: Any) -> None:
        self.configs["pub_setting"] = "['superheroes', 'science-fiction', 'fantasy']"

        assert radar._get_category(self.event) == "sci-fi"  # noqa: SLF001

    def test_promotion_data_map_to_features(self, _sleep: Any) -> None:
        self.configs.update(
            {
                "pub_language": "['it', 'en']",
                "pub_accommodation": "included",
                "pub_accommodation_type": "['camping', 'other']",
                "pub_meals": "['internal', 'diy']",
            }
        )

        assert radar._get_features(self.event) == [  # noqa: SLF001
            "english-friendly",
            "fully catered",
            "sleeping-place",
            "tent",
        ]

    def test_dates_keep_calendar_day_in_utc(self, _sleep: Any) -> None:
        period = radar._format_period(date(2026, 6, 12), date(2026, 6, 14), "Europe/Rome")  # noqa: SLF001

        assert period == ("2026-06-12T08:00:00Z", "2026-06-14T15:00:00Z")

    def test_dates_fall_back_to_utc_hours_when_day_would_change(self, _sleep: Any) -> None:
        pacific = radar._format_period(date(2026, 6, 12), date(2026, 6, 14), "America/Los_Angeles")  # noqa: SLF001
        sydney = radar._format_period(date(2026, 1, 10), date(2026, 1, 12), "Australia/Sydney")  # noqa: SLF001

        assert pacific == ("2026-06-12T10:00:00Z", "2026-06-14T17:00:00Z")
        assert sydney == ("2026-01-10T10:00:00Z", "2026-01-12T17:00:00Z")

    def test_one_day_run_ends_after_start_in_every_timezone(self, _sleep: Any) -> None:
        for timezone_name in ("America/Los_Angeles", "Australia/Sydney", "Pacific/Auckland", "Europe/Rome"):
            for day in (date(2026, 1, 10), date(2026, 6, 6)):
                start, end = radar._format_period(day, day, timezone_name)  # noqa: SLF001

                assert start < end
                assert start.startswith(day.isoformat())
                assert end.startswith(day.isoformat())


class TestRadarActivation(BaseTestCase):
    """Test the conditions that activate the LARP Radar export."""

    def enable_radar(self) -> Any:
        """Patch the feature and opt-in checks as satisfied."""
        return patch.multiple(
            "larpmanager.utils.publication.radar",
            get_association_features=MagicMock(return_value={"publisher": 1}),
            get_association_config=MagicMock(return_value=True),
        )

    def create_demo_type(self, template_association: Association) -> LarpManagerDemoType:
        """Create a demo type based on the given association."""
        return LarpManagerDemoType.objects.create(
            name="Radar demo", slug="radardemo", template_association=template_association
        )

    def cached_actions_after(self, save_config: Any) -> Any:
        """Return the cached dashboard actions left after saving a config."""
        association = self.get_event().association
        cache_key = get_widget_cache_key("association", association.id, "actions")
        cache.set(cache_key, {"stale": True}, 600)
        save_config(association)
        return cache.get(cache_key)

    @patch("larpmanager.models.signals.publish_association_radar")
    def test_opt_in_publishes_the_association_events(self, mock_publish: Any) -> None:
        association = self.get_event().association

        save_single_config(association, radar.RADAR_ENABLED_CONFIG, "False")
        mock_publish.assert_not_called()

        save_single_config(association, radar.RADAR_ENABLED_CONFIG, "True")
        mock_publish.assert_called_once_with(association.id)

    @patch("larpmanager.utils.publication.base.sync_event_radar")
    def test_opt_in_task_syncs_only_events_with_upcoming_visible_runs(self, mock_sync: Any) -> None:
        run = self.get_run()
        today = timezone.localdate()
        Run.objects.filter(pk=run.pk).update(development=DevelopStatus.SHOW, start=today, end=today)
        mock_sync.reset_mock()  # creating the fixtures already publishes through the signals

        base.publish_association_radar.task_function(run.event.association_id)
        mock_sync.assert_called_once()
        assert mock_sync.call_args.args[0].id == run.event_id

        mock_sync.reset_mock()
        Run.objects.filter(pk=run.pk).update(end=today - timedelta(days=1))
        base.publish_association_radar.task_function(run.event.association_id)
        mock_sync.assert_not_called()

    @patch("larpmanager.utils.publication.base.sync_event_radar")
    @patch("larpmanager.utils.publication.base.sync_event_ildb", side_effect=RuntimeError)
    def test_ildb_failure_does_not_block_radar(self, _ildb: Any, mock_radar: Any) -> None:
        with pytest.raises(RuntimeError):
            base.publish_event.task_function(self.get_event().id)

        mock_radar.assert_called_once()

    @patch("larpmanager.utils.publication.radar.my_send_mail")
    def test_notification_escapes_external_values(self, mock_mail: Any) -> None:
        event = self.get_event()
        event.association.main_mail = "orga@test.it"
        run = self.get_run()
        run.search = "<i>Run</i>"

        radar._notify_association(event, run, "https://larp-radar.com/it/'><script>")  # noqa: SLF001

        body = mock_mail.call_args.args[1]
        assert "<i>" not in body
        assert "<script>" not in body

    def test_publication_configs_clear_dashboard_actions(self) -> None:
        for config_name in (radar.RADAR_ENABLED_CONFIG, ildb.ILDB_CONFIG_KEY, ildb.ILDB_TEAM_CONFIG_KEY):
            assert self.cached_actions_after(lambda a, name=config_name: save_single_config(a, name, "1")) is None

    def test_config_form_save_clears_dashboard_actions(self) -> None:
        configs = {radar.RADAR_ENABLED_CONFIG: "True"}

        assert self.cached_actions_after(lambda a: save_all_element_configs(a, configs)) is None

    def test_run_and_event_saves_clear_dashboard_actions(self) -> None:
        assert self.cached_actions_after(lambda _association: self.get_run().save()) is None
        assert self.cached_actions_after(lambda association: self.get_event().save()) is None

    def test_validators_reject_invalid_coordinates(self) -> None:
        for validator, value in ((validate_latitude, "91"), (validate_longitude, "-181"), (validate_latitude, "nan")):
            with pytest.raises(ValidationError):
                validator(value)

        validate_latitude("-90")
        validate_longitude("180")
        validate_latitude("")

    def test_unrelated_config_keeps_dashboard_actions(self) -> None:
        assert self.cached_actions_after(lambda a: save_single_config(a, "publication_crew", "True")) is not None

    @override_settings(LARP_RADAR_API_KEY="secret")
    def test_enabled_for_real_association(self) -> None:
        with self.enable_radar():
            assert radar.is_radar_enabled(self.get_event().association_id)

    @override_settings(LARP_RADAR_API_KEY="secret")
    def test_not_enabled_for_demo_association(self) -> None:
        association = self.get_event().association
        demo_type = self.create_demo_type(self.create_association(slug="radartemplate"))
        Association.objects.filter(pk=association.pk).update(demo_type=demo_type)

        with self.enable_radar():
            assert not radar.is_radar_enabled(association.id)

    @override_settings(LARP_RADAR_API_KEY="secret")
    def test_not_enabled_for_demo_template(self) -> None:
        association = self.get_event().association
        self.create_demo_type(association)

        with self.enable_radar():
            assert not radar.is_radar_enabled(association.id)
        assert not radar.is_radar_available(association.id)

    @override_settings(LARP_RADAR_API_KEY="secret")
    @patch("larpmanager.utils.publication.radar.get_association_config", return_value=False)
    @patch("larpmanager.utils.publication.radar.get_association_features", return_value={"publisher": 1})
    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_no_request_without_opt_in(self, mock_put: Any, _features: Any, _config: Any) -> None:
        radar.sync_event(self.get_event())

        mock_put.assert_not_called()

    @override_settings(LARP_RADAR_API_KEY=None)
    @patch("larpmanager.utils.publication.radar.get_association_config", return_value=True)
    @patch("larpmanager.utils.publication.radar.get_association_features", return_value={"publisher": 1})
    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_no_request_without_platform_key(self, mock_put: Any, _features: Any, _config: Any) -> None:
        radar.sync_event(self.get_event())

        mock_put.assert_not_called()

    @override_settings(LARP_RADAR_API_KEY="secret")
    @patch("larpmanager.utils.publication.radar.get_association_config", return_value=True)
    @patch("larpmanager.utils.publication.radar.get_association_features", return_value={})
    @patch("larpmanager.utils.publication.radar.requests.put")
    def test_no_request_without_promotion_feature(self, mock_put: Any, _features: Any, _config: Any) -> None:
        radar.sync_event(self.get_event())

        mock_put.assert_not_called()
