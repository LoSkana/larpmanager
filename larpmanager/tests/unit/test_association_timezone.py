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

"""Tests for the association timezone: activation, day boundaries, background tasks and data migration."""

from __future__ import annotations

import importlib
from collections import defaultdict
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

from background_task.models import Task
from django.apps import apps
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, override_settings
from django.utils import timezone

from larpmanager.cache.basic import get_association_basic_cache
from larpmanager.middleware.association import AssociationIdentifyMiddleware
from larpmanager.models.association import DEFAULT_TIMEZONE
from larpmanager.models.event import Run
from larpmanager.models.member import MembershipStatus
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.core.common import ensure_timezone_aware, local_day_start
from larpmanager.utils.larpmanager.tasks import TIMEZONE_KWARG, background_auto
from larpmanager.utils.users.deadlines import deadlines_membership

ROME = ZoneInfo("Europe/Rome")

timezone_migration = importlib.import_module("larpmanager.migrations.0198_association_timezone")


@background_auto(queue="test-timezone", skip_duplicates=True)
def _record_timezone(key: str) -> str:
    """Return the timezone active while the task runs."""
    return f"{key}:{timezone.get_current_timezone_name()}"


class TestTimezoneHelpers:
    """Test the day boundary and aware conversion helpers."""

    def test_local_day_start_uses_current_timezone(self) -> None:
        """Midnight is computed in the active timezone, not in UTC."""
        with timezone.override("Europe/Rome"):
            assert local_day_start(date(2026, 1, 1)) == datetime(2025, 12, 31, 23, 0, tzinfo=UTC)
        with timezone.override("America/New_York"):
            assert local_day_start(date(2026, 7, 1)) == datetime(2026, 7, 1, 4, 0, tzinfo=UTC)

    def test_local_day_start_year_edge(self) -> None:
        """A late New Year's Eve instant in UTC belongs to the next local year."""
        with timezone.override("Europe/Rome"):
            new_year_eve_utc = datetime(2025, 12, 31, 23, 30, tzinfo=UTC)
            assert new_year_eve_utc >= local_day_start(date(2026, 1, 1))
            assert timezone.localtime(new_year_eve_utc).year == 2026

    def test_ensure_timezone_aware_treats_naive_as_utc(self) -> None:
        """Naive values are stored legacy UTC timestamps, whatever the active timezone."""
        with timezone.override("Europe/Rome"):
            converted = ensure_timezone_aware(datetime(2026, 5, 1, 10, 0))  # noqa: DTZ001
        assert converted == datetime(2026, 5, 1, 10, 0, tzinfo=UTC)

    def test_ensure_timezone_aware_keeps_aware(self) -> None:
        """Aware values are returned unchanged."""
        aware = datetime(2026, 5, 1, 10, 0, tzinfo=ROME)
        assert ensure_timezone_aware(aware) is aware


class TestAssociationTimezoneMiddleware:
    """Test the middleware activates the association timezone during the request."""

    @staticmethod
    def _call(association: dict | None) -> tuple[HttpResponse, list[str]]:
        seen = []

        def get_response(_request: HttpRequest) -> HttpResponse:
            seen.append(timezone.get_current_timezone_name())
            return HttpResponse("ok")

        def fake_info(request: HttpRequest) -> None:
            if association is not None:
                request.association = association

        middleware = AssociationIdentifyMiddleware(get_response=get_response)
        with patch.object(AssociationIdentifyMiddleware, "get_association_info", side_effect=fake_info):
            response = middleware(RequestFactory().get("/"))
        return response, seen

    def test_association_timezone_is_active(self) -> None:
        """The view runs under the association timezone."""
        response, seen = self._call({"timezone": "Asia/Tokyo"})
        assert response.status_code == 200
        assert seen == ["Asia/Tokyo"]

    def test_default_timezone_without_association(self) -> None:
        """Without an association the default timezone is used."""
        _response, seen = self._call(None)
        assert seen == [DEFAULT_TIMEZONE]

    def test_default_timezone_with_stale_cache(self) -> None:
        """Association data cached before the timezone field falls back to the default."""
        _response, seen = self._call({"slug": "test"})
        assert seen == [DEFAULT_TIMEZONE]

    def test_timezone_restored_after_request(self) -> None:
        """The association timezone does not leak past the request."""
        before = timezone.get_current_timezone_name()
        self._call({"timezone": "Asia/Tokyo"})
        assert timezone.get_current_timezone_name() == before


@override_settings(AUTO_BACKGROUND_TASKS=False)
class TestBackgroundTaskTimezone(BaseTestCase):
    """Test background tasks run under the timezone active when scheduled."""

    def _pending(self) -> Any:
        return Task.objects.filter(task_name=_record_timezone.task.name)

    def test_scheduling_stores_active_timezone(self) -> None:
        """The scheduled task carries the active timezone as kwarg."""
        with timezone.override("Asia/Tokyo"):
            _record_timezone("a")
        task = self._pending().get()
        _args, kwargs = task.params()
        assert kwargs[TIMEZONE_KWARG] == "Asia/Tokyo"

    def test_skip_duplicates_same_timezone(self) -> None:
        """An identical pending task in the same timezone is not scheduled twice."""
        with timezone.override("Asia/Tokyo"):
            _record_timezone("a")
            _record_timezone("a")
            _record_timezone("b")
        assert self._pending().count() == 2

    def test_task_runs_in_scheduled_timezone(self) -> None:
        """The task body runs under the stored timezone."""
        with timezone.override("Asia/Tokyo"):
            _record_timezone("a")
        args, kwargs = self._pending().get().params()
        with timezone.override("Europe/Rome"):
            assert _record_timezone.task.task_function(*args, **kwargs) == "a:Asia/Tokyo"

    def test_legacy_task_without_timezone(self) -> None:
        """Tasks queued before the timezone kwarg run under the default timezone."""
        assert _record_timezone.task.task_function("a") == f"a:{timezone.get_default_timezone_name()}"


class TestAssociationTimezoneCache(BaseTestCase):
    """Test the association timezone is exposed by the basic cache."""

    def test_basic_cache_follows_timezone_change(self) -> None:
        """Saving a new timezone refreshes the cached value."""
        association = self.get_association()
        assert get_association_basic_cache(association.id)["timezone"] == association.timezone

        association.timezone = "America/New_York"
        association.save()
        assert get_association_basic_cache(association.id)["timezone"] == "America/New_York"


class TestRegistrationOpenMigration(BaseTestCase):
    """Test the data migration reinterpreting registration_open as Italian wall-clock time."""

    def test_shift_and_revert(self) -> None:
        """Wall-clock 10:00 stored as UTC becomes 10:00 Rome, and reverts back."""
        run = self.get_run()
        stored = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
        Run.objects.filter(pk=run.pk).update(registration_open=stored)

        timezone_migration.registration_open_to_local(apps, None)
        run.refresh_from_db()
        assert run.registration_open == datetime(2026, 3, 1, 10, 0, tzinfo=ROME)
        assert run.registration_open == datetime(2026, 3, 1, 9, 0, tzinfo=UTC)

        timezone_migration.registration_open_to_utc(apps, None)
        run.refresh_from_db()
        assert run.registration_open == stored

    def test_summer_time_shift(self) -> None:
        """During daylight saving the shift is two hours."""
        run = self.get_run()
        Run.objects.filter(pk=run.pk).update(registration_open=datetime(2026, 7, 1, 10, 0, tzinfo=UTC))

        timezone_migration.registration_open_to_local(apps, None)
        run.refresh_from_db()
        assert run.registration_open == datetime(2026, 7, 1, 8, 0, tzinfo=UTC)


class TestDeadlinesLocalDate:
    """Test membership deadlines count days in the active timezone."""

    @staticmethod
    def _violations(registration_created: datetime, now: datetime, tolerance: int) -> dict:
        violations = defaultdict(list)
        deadlines_membership(
            violations,
            {"laog": 1},
            set(),
            {1: SimpleNamespace(status=MembershipStatus.EMPTY)},
            now,
            (1, registration_created),
            SimpleNamespace(start=date(2026, 9, 1)),
            tolerance,
        )
        return violations

    def test_registration_after_local_midnight(self) -> None:
        """A registration at 00:30 Rome counts from the local day, not the previous UTC day."""
        with timezone.override("Europe/Rome"):
            now = timezone.localtime(datetime(2026, 5, 12, 8, 0, tzinfo=UTC))
            registration_created = datetime(2026, 5, 9, 22, 30, tzinfo=UTC)
            violations = self._violations(registration_created, now, tolerance=2)
        assert violations["memb"] == [1]
        assert violations["memb_del"] == []

    def test_registration_past_tolerance(self) -> None:
        """Beyond the tolerance the membership is flagged as delayed."""
        with timezone.override("Europe/Rome"):
            now = timezone.localtime(datetime(2026, 5, 12, 8, 0, tzinfo=UTC))
            registration_created = datetime(2026, 5, 9, 22, 30, tzinfo=UTC)
            violations = self._violations(registration_created, now, tolerance=1)
        assert violations["memb_del"] == [1]
