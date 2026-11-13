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

import logging
import re
import time as time_module
from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from django.conf import settings as conf_settings
from django.utils import timezone, translation
from django.utils.html import escape
from django.utils.translation import gettext as _

from larpmanager.cache.basic import get_association_basic_cache
from larpmanager.cache.config import get_association_config, get_element_config, save_single_config
from larpmanager.cache.feature import get_association_features
from larpmanager.cache.run import get_event_runs
from larpmanager.models.association import Association
from larpmanager.models.event import DevelopStatus, Event, Run
from larpmanager.utils.core.common import get_exec_language, html_clean, is_rate_limited, parse_multi_config
from larpmanager.utils.core.headers import get_association_url
from larpmanager.utils.larpmanager.tasks import my_send_mail, notify_admins
from larpmanager.utils.publication.ildb import (
    MAX_LATITUDE,
    MAX_LONGITUDE,
    PromotionAccommodation,
    PromotionAccommodationType,
    PromotionLanguage,
    PromotionMeals,
    PromotionSetting,
    get_player_ticket_prices,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)

RADAR_SITE = "https://larp-radar.com"
RADAR_API_BASE = f"{RADAR_SITE}/api/partner/v1"
RADAR_RUN_CONFIG = "radar"
RADAR_ENABLED_CONFIG = "radar_enabled"

RADAR_MAX_RETRIES = 3
RADAR_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
RADAR_REQUEST_DELAY = 0.6  # stay within the 120 req/min limit
RADAR_RETRY_BACKOFF = 5
RADAR_MAX_RETRY_WAIT = 60
HTTP_CONFLICT = 409
RADAR_ADMIN_NOTICE_TIMEOUT = conf_settings.CACHE_TIMEOUT_1_DAY

RADAR_CURRENCIES = frozenset({"EUR", "USD", "GBP"})
RADAR_DEFAULT_CATEGORY = "other"

# Runs only store dates: conventional local hours, see _format_period for the calendar day handling
RADAR_START_TIME = time(10)
RADAR_END_TIME = time(17)

_BLOCK_END_RE = re.compile(r"</(?:p|div|li|h[1-6])>|<br\s*/?>", re.IGNORECASE)

_CATEGORY_MAP = {
    PromotionSetting.FANTASY: "fantasy",
    PromotionSetting.HORROR: "horror",
    PromotionSetting.SCI_FI: "sci-fi",
    PromotionSetting.HISTORICAL: "historical",
    PromotionSetting.CONTEMPORARY: "modern",
    PromotionSetting.POST_APOCALYPTIC: "post-apocalyptic",
    PromotionSetting.CYBERPUNK: "futuristic",
    PromotionSetting.STEAMPUNK: "futuristic",
    PromotionSetting.GOTHIC: "gothic",
    PromotionSetting.WESTERN: "western",
}
_ACCOMMODATION_FEATURES = {
    PromotionAccommodation.INCLUDED: "sleeping-place",
    PromotionAccommodation.NON_RESIDENTIAL: "no-need-sleep",
}
_ACCOMMODATION_TYPE_FEATURES = {
    PromotionAccommodationType.CAMPING: "tent",
    PromotionAccommodationType.FARM_STAY: "sleeping-place",
    PromotionAccommodationType.HISTORIC_RESIDENCE: "sleeping-place",
    PromotionAccommodationType.HOTEL: "sleeping-place",
}
_MEALS_FEATURES = {
    PromotionMeals.NOT_INCLUDED: "no-ristoration",
    PromotionMeals.INTERNAL_CATERING: "fully catered",
    PromotionMeals.EXTERNAL_CATERING: "fully catered",
}


def _radar_put(external_id: str, payload: dict) -> requests.Response:
    """Create or update an event, retrying on network errors, rate limit and server errors."""
    url = f"{RADAR_API_BASE}/events/{quote(external_id, safe='')}/"
    headers = {
        "X-Api-Key": conf_settings.LARP_RADAR_API_KEY,
        "Origin": conf_settings.LARP_RADAR_ORIGIN,
        "Accept": "application/json",
    }

    def send() -> requests.Response:
        response = requests.put(url, json=payload, headers=headers, timeout=30)
        time_module.sleep(RADAR_REQUEST_DELAY)
        return response

    for attempt in range(1, RADAR_MAX_RETRIES):
        retry_after = None
        try:
            response = send()
            if response.status_code not in RADAR_RETRY_STATUSES:
                return response
            retry_after = response.headers.get("Retry-After")
        except requests.exceptions.RequestException as exc:
            logger.warning("LARP Radar: attempt %s failed for %s: %s", attempt, external_id, exc)
        time_module.sleep(_get_retry_wait(attempt, retry_after))
    return send()


def _get_retry_wait(attempt: int, retry_after: str | None) -> int:
    """Return the seconds to wait before a new attempt, honoring Retry-After up to the maximum wait."""
    backoff = attempt * RADAR_RETRY_BACKOFF
    try:
        return min(max(int(retry_after), backoff), RADAR_MAX_RETRY_WAIT)
    except (TypeError, ValueError):
        return backoff


def is_radar_available(association_id: int) -> bool:
    """Return True if the platform key is set and the association is neither a demo nor a demo template."""
    return bool(
        conf_settings.LARP_RADAR_API_KEY
        and Association.objects.filter(pk=association_id, demo_type__isnull=True, demo_types__isnull=True).exists()
    )


def is_radar_enabled(association_id: int) -> bool:
    """Return True if an available association has the promotion feature and opted in."""
    return bool(
        "publisher" in get_association_features(association_id)
        and get_association_config(association_id, RADAR_ENABLED_CONFIG)
        and is_radar_available(association_id)
    )


def get_publishable_runs(association_id: int) -> QuerySet[Run]:
    """Return the upcoming runs of an association shown to the public, the same ones accepted by _is_publishable."""
    return Run.objects.filter(
        event__association_id=association_id,
        event__template=False,
        event__visible=True,
        event__deleted__isnull=True,
        development=DevelopStatus.SHOW,
        start__isnull=False,
        end__gte=timezone.localdate(),
    )


def sync_event(event: Event) -> None:
    """Create or update the LARP Radar entry of each eligible run of an event."""
    if not is_radar_enabled(event.association_id):
        return
    for run in get_event_runs(event.id):
        if not _is_publishable(event, run):
            continue
        try:
            _sync_run(event, run)
        except Exception as exc:
            logger.exception("LARP Radar sync failed for run %s", run.id)
            _notify_admins_daily(
                f"radar_sync_failed_{run.id}", f"LARP Radar sync failed for run {run.id}", str(run), exc
            )


def _notify_admins_daily(key: str, subject: str, message: str, exception: Exception | None = None) -> None:
    """Notify the admins at most once a day per key, as a failing run is synced again on every save."""
    if not is_rate_limited(key, RADAR_ADMIN_NOTICE_TIMEOUT):
        notify_admins(subject, message, exception)


def _is_publishable(event: Event, run: Run) -> bool:
    """Return True for upcoming runs of visible events, or cancelled ones already published."""
    if event.template or not run.start or not run.end or run.end < timezone.localdate():
        return False
    if run.development == DevelopStatus.SHOW:
        return event.visible
    return run.development == DevelopStatus.CANC and bool(run.get_config(RADAR_RUN_CONFIG))


def _sync_run(event: Event, run: Run) -> None:
    """Send a run to LARP Radar; the first successful publication is stored and notified."""
    run.event = event
    payload = _build_event_payload(event, run)
    missing = [key for key in ("description", "coordinates") if key not in payload]
    if missing:
        logger.warning("LARP Radar: skipping run %s - missing required fields: %s", run.id, missing)
        return

    response = _radar_put(run.uuid, payload)
    if response.status_code == HTTP_CONFLICT:
        # Not fixable by a new attempt
        logger.warning("LARP Radar: conflict on run %s: %s", run.id, response.text)
        if "event_duplicate" in response.text:
            _notify_admins_daily(
                f"radar_duplicate_{run.id}",
                f"LARP Radar duplicate event for run {run.id}",
                f"Run: {run.search}\n{response.text}",
            )
        return
    if not response.ok:
        _notify_admins_daily(
            f"radar_put_failed_{run.id}_{response.status_code}",
            f"LARP Radar PUT failed {response.status_code} for run {run.id}",
            f"Run: {run.id}\nPayload: {payload}\nResponse: {response.text}",
        )
        return

    if run.get_config(RADAR_RUN_CONFIG):
        return

    radar_path = response.json().get("url")
    if not radar_path:
        _notify_admins_daily(
            f"radar_no_url_{run.id}", f"LARP Radar response without url for run {run.id}", response.text
        )
        return

    radar_url = f"{RADAR_SITE}{radar_path}"
    save_single_config(run, RADAR_RUN_CONFIG, radar_url)
    _notify_association(event, run, radar_url)


def _get_title(event: Event, run: Run) -> str:
    """Return the full event name, followed by the run number if not the first one."""
    return f"{event.name} #{run.number}" if run.number and run.number > 1 else event.name


def _format_period(start: date, end: date, timezone_name: str) -> tuple[str, str]:
    """Return start and end as ISO 8601 UTC at the conventional hours, using UTC hours if the day of either changes."""
    zone = ZoneInfo(timezone_name)
    start_moment = datetime.combine(start, RADAR_START_TIME, tzinfo=zone).astimezone(UTC)
    end_moment = datetime.combine(end, RADAR_END_TIME, tzinfo=zone).astimezone(UTC)
    if start_moment.date() != start or end_moment.date() != end:
        start_moment = datetime.combine(start, RADAR_START_TIME, tzinfo=UTC)
        end_moment = datetime.combine(end, RADAR_END_TIME, tzinfo=UTC)
    return start_moment.strftime("%Y-%m-%dT%H:%M:%SZ"), end_moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_category(event: Event) -> str:
    """Return the Radar category of the first event setting that has one."""
    for setting in parse_multi_config(get_element_config(event, "pub_setting")):
        if setting in _CATEGORY_MAP:
            return _CATEGORY_MAP[setting]
    return RADAR_DEFAULT_CATEGORY


def _get_coordinates(event: Event) -> dict[str, float] | None:
    """Return the event coordinates, or None if they are not set or not valid."""
    try:
        latitude = float(get_element_config(event, "pub_lat"))
        longitude = float(get_element_config(event, "pub_lon"))
    except ValueError:
        return None
    # These comparisons are also False for nan
    if abs(latitude) <= MAX_LATITUDE and abs(longitude) <= MAX_LONGITUDE:
        return {"latitude": latitude, "longitude": longitude}
    return None


def _get_description(event: Event) -> str | None:
    """Return the event description as plain text, one line per block, or None if empty."""
    text = html_clean(_BLOCK_END_RE.sub("\n", event.description or ""))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line) or None


def _get_features(event: Event) -> list[str]:
    """Return the sorted Radar feature slugs matching the event promotion data."""
    features = set()

    languages = parse_multi_config(get_element_config(event, "pub_language"))
    if PromotionLanguage.ENGLISH in languages:
        features.add("full-english" if len(languages) == 1 else "english-friendly")

    accommodation = get_element_config(event, "pub_accommodation")
    if accommodation in _ACCOMMODATION_FEATURES:
        features.add(_ACCOMMODATION_FEATURES[accommodation])

    for config_name, feature_map in (
        ("pub_accommodation_type", _ACCOMMODATION_TYPE_FEATURES),
        ("pub_meals", _MEALS_FEATURES),
    ):
        for value in parse_multi_config(get_element_config(event, config_name)):
            if value in feature_map:
                features.add(feature_map[value])

    return sorted(features)


def _get_image_url(event: Event) -> str | None:
    """Return the public URL of the event cover, or None if unavailable."""
    if not event.cover:
        return None
    try:
        return get_association_url(event.cover_full.url, event.association_id)
    except (ValueError, OSError):
        logger.warning("LARP Radar: cover not available for event %s", event.id)
        return None


def _build_event_payload(event: Event, run: Run) -> dict[str, Any]:
    """Build the partner API payload of a run, omitting the fields without a value."""
    association = event.association
    association_timezone = get_association_basic_cache(event.association_id)["timezone"]
    start_time, end_time = _format_period(run.start, run.end, association_timezone)

    payload = {
        "title": _get_title(event, run),
        "start_time": start_time,
        "end_time": end_time,
        "description": _get_description(event),
        "category": _get_category(event),
        "coordinates": _get_coordinates(event),
        "tickets": get_association_url(f"{run.get_slug()}/register/", event.association_id),
        "image": _get_image_url(event),
        "features": _get_features(event) or None,
        "status": "cancelled" if run.development == DevelopStatus.CANC else "enabled",
        "organizer": {
            "external_id": association.uuid,
            "name": association.name,
            **({"email": association.main_mail} if association.main_mail else {}),
        },
    }

    # Prices are meaningless without a currency supported by Radar
    currency = association.get_payment_currency_display()
    if currency in RADAR_CURRENCIES:
        prices = get_player_ticket_prices(event.id)
        payload["currency"] = currency
        payload["ticket_min_price"] = float(prices["costo"]) if prices["costo"] is not None else None
        payload["ticket_max_price"] = float(prices["costo_max"]) if prices["costo_max"] is not None else None

    return {key: value for key, value in payload.items() if value is not None}


def _notify_association(event: Event, run: Run, radar_url: str) -> None:
    """Send an email to the association main address with the published event link."""
    association = event.association
    if not association.main_mail:
        return

    with translation.override(get_exec_language(association)):
        subject = f"[{association.name}] " + _("Event published on LARP Radar:") + " " + event.name
        link = escape(radar_url)
        body = (
            "<p>"
            + _("The event <strong>%(event)s</strong> has been automatically published on LARP Radar.")
            % {"event": escape(run.search)}
            + f"</p><p><a href='{link}'>{link}</a></p>"
        )

    my_send_mail(subject, body, association.main_mail, association)
