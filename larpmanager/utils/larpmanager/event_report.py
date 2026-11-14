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
"""Event report: summaries of the runs of every installation, sent to the LarpManager main installation.

When EVENT_REPORT is set, every save of an event or run, and every automate, sends the summary of each
run to that endpoint. The main installation has EVENT_REPORT set to None, and stores each received
summary in LarpManagerEventReport, one per association and run uuids.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from http import HTTPStatus
from typing import Any

import requests
from django.conf import settings as conf_settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, QuerySet
from django.utils import timezone

from larpmanager.cache.registration_lookup import get_active_registrations
from larpmanager.models.event import DevelopStatus, Run
from larpmanager.models.larpmanager import LarpManagerEventReport
from larpmanager.models.miscellanea import Log
from larpmanager.utils.core.headers import get_association_url
from larpmanager.utils.larpmanager.tasks import background_auto
from larpmanager.utils.users.member import get_system_member

logger = logging.getLogger(__name__)

EVENT_REPORT_QUEUE = "event_report"
EVENT_REPORT_TIMEOUT = 30
EVENT_REPORT_USERNAME = "event_report_system"
MAX_EVENT_REPORT_SIZE = 128 * 1024
EVENT_REPORT_TOKEN_HEADER = "X-Event-Report-Token"  # noqa: S105 - header name, not a secret
MAX_EVENT_REPORT_TOKEN_LENGTH = 128
# New associations accepted from a single IP address in a day
MAX_NEW_ASSOCIATIONS_PER_IP = 20
NEW_ASSOCIATIONS_WINDOW = 24 * 60 * 60

_UUID_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")


def is_event_report_sender() -> bool:
    """Return True if this installation sends its event reports to the main installation."""
    return bool(conf_settings.EVENT_REPORT)


def is_event_report_receiver() -> bool:
    """Return True if this installation is the main one, storing the reports received."""
    return not conf_settings.EVENT_REPORT


def get_event_report_token() -> str:
    """Return the secret of this installation, derived from its SECRET_KEY, authenticating its reports."""
    return hmac.new(conf_settings.SECRET_KEY.encode(), b"event-report", hashlib.sha256).hexdigest()


def _hash_token(token: str) -> str:
    """Return the hash of a report token, as stored by the main installation."""
    return hashlib.sha256(token.encode()).hexdigest()


def build_run_report(run: Run) -> dict[str, Any]:
    """Return the public data of a run, of its event and association, with the signups count by ticket."""
    event = run.event
    association = event.association

    signups = dict(
        get_active_registrations(run.id)
        .order_by()
        .values("ticket_id")
        .annotate(total=Count("id"))
        .values_list("ticket_id", "total")
    )
    tickets = [
        {
            "name": ticket.name,
            "tier": ticket.tier,
            "price": str(ticket.price) if ticket.price is not None else None,
            "max_available": ticket.max_available,
            "signups": signups.pop(ticket.id, 0),
        }
        for ticket in event.tickets.order_by("number")
    ]

    return {
        "sent_at": timezone.now().isoformat(),
        "association": {
            "uuid": association.uuid,
            "slug": association.slug,
            "name": association.name,
            "url": get_association_url("", association.id),
            "currency": association.get_payment_currency_display(),
        },
        "event": {
            "uuid": event.uuid,
            "slug": event.slug,
            "name": event.name,
            "tagline": event.tagline,
            "description": event.description,
            "website": event.website,
            "genre": event.genre,
            "where": event.where,
            "authors": event.authors,
            "visible": event.visible,
            "cover": get_association_url(event.cover.url, association.id) if event.cover else None,
            "max_pg": event.max_pg,
            "max_filler": event.max_filler,
            "max_waiting": event.max_waiting,
        },
        "run": {
            "uuid": run.uuid,
            "number": run.number,
            "start": run.start.isoformat() if run.start else None,
            "end": run.end.isoformat() if run.end else None,
            "development": run.development,
            "registration_status": run.registration_status,
            "registration_open": run.registration_open.isoformat() if run.registration_open else None,
            "url": get_association_url(f"{run.get_slug()}/", association.id),
        },
        "tickets": tickets,
        # Registrations without a ticket, or with a ticket of another event
        "signups_without_ticket": sum(signups.values()),
        "signups_total": sum(ticket["signups"] for ticket in tickets) + sum(signups.values()),
    }


@background_auto(queue=EVENT_REPORT_QUEUE, skip_duplicates=True)
def _send_run_report_task(run_id: int) -> None:
    """Background task: post the report of a run to the main installation."""
    try:
        run = Run.objects.select_related("event__association").get(pk=run_id)
        if run.event.template or run.event.deleted:
            return
        requests.post(
            conf_settings.EVENT_REPORT,
            json=build_run_report(run),
            headers={EVENT_REPORT_TOKEN_HEADER: get_event_report_token()},
            timeout=EVENT_REPORT_TIMEOUT,
        )
    except Exception:
        logger.debug("Event report: sending run %s failed", run_id, exc_info=True)


def send_run_report(run_id: int) -> None:
    """Schedule the sending of the report of a run, ignoring any error."""
    if not is_event_report_sender():
        return
    try:
        # Savepoint, so a failed scheduling does not break the caller transaction
        with transaction.atomic():
            _send_run_report_task(run_id)
    except Exception:
        logger.debug("Event report: scheduling run %s failed", run_id, exc_info=True)


def _send_runs_reports(runs: QuerySet[Run]) -> None:
    """Schedule the sending of the reports of the given runs, ignoring any error."""
    if not is_event_report_sender():
        return
    try:
        run_ids = list(runs.values_list("id", flat=True))
    except Exception:
        logger.debug("Event report: listing runs failed", exc_info=True)
        return
    for run_id in run_ids:
        send_run_report(run_id)


def send_event_reports(event_id: int) -> None:
    """Send the reports of all the runs of an event."""
    _send_runs_reports(Run.objects.filter(event_id=event_id))


def send_all_run_reports() -> None:
    """Send the reports of the runs still in progress."""
    _send_runs_reports(
        Run.objects.filter(event__template=False).exclude(development__in=[DevelopStatus.DONE, DevelopStatus.CANC])
    )


def _allow_new_association(ip_address: str) -> bool:
    """Count a new association reported from an IP address; return False over the daily limit."""
    key = f"event_report_new_association_{ip_address}"
    cache.add(key, 0, NEW_ASSOCIATIONS_WINDOW)
    try:
        return cache.incr(key) <= MAX_NEW_ASSOCIATIONS_PER_IP
    except ValueError:
        return True


def _check_report_token(association_uuid: str, token: str, ip_address: str) -> tuple[HTTPStatus | None, str]:
    """Check the token against the one of the first report of the association.

    Returns an error status (or None if accepted) and the token hash to store.
    """
    if not isinstance(token, str) or not token or len(token) > MAX_EVENT_REPORT_TOKEN_LENGTH:
        return HTTPStatus.FORBIDDEN, ""
    token_hash = _hash_token(token)

    stored_hash = (
        LarpManagerEventReport.objects.filter(association_uuid=association_uuid)
        .exclude(token_hash="")
        .values_list("token_hash", flat=True)
        .first()
    )
    if stored_hash is None:
        if not _allow_new_association(ip_address):
            return HTTPStatus.TOO_MANY_REQUESTS, token_hash
    elif not hmac.compare_digest(stored_hash, token_hash):
        return HTTPStatus.FORBIDDEN, token_hash
    return None, token_hash


def save_run_report(payload: Any, token: str, ip_address: str = "") -> HTTPStatus:
    """Store a received report, replacing the previous one of the same run.

    The first report of an association binds its token: later reports of the same association
    are accepted only with the same token. Returns the HTTP status of the response.
    """
    try:
        association_uuid = payload["association"]["uuid"]
        run_uuid = payload["run"]["uuid"]
    except (KeyError, TypeError):
        return HTTPStatus.BAD_REQUEST
    if not all(isinstance(value, str) and _UUID_RE.match(value) for value in (association_uuid, run_uuid)):
        return HTTPStatus.BAD_REQUEST

    error_status, token_hash = _check_report_token(association_uuid, token, ip_address)
    if error_status:
        return error_status

    payload["received_at"] = timezone.now().isoformat()
    association_name = payload["association"].get("name")
    event_data = payload.get("event")
    event_name = event_data.get("name") if isinstance(event_data, dict) else None
    LarpManagerEventReport.objects.update_or_create(
        association_uuid=association_uuid,
        run_uuid=run_uuid,
        defaults={
            "token_hash": token_hash,
            "association_name": str(association_name or "")[:150],
            "event_name": str(event_name or "")[:150],
            "data": json.dumps(payload, indent=2, ensure_ascii=False),
        },
    )

    _log_received_report(payload, association_uuid, run_uuid, ip_address)
    return HTTPStatus.OK


def _log_received_report(payload: dict, association_uuid: str, run_uuid: str, ip_address: str) -> None:
    """Record the reception of a report in the Log, ignoring any error."""
    try:
        system_member = get_system_member(EVENT_REPORT_USERNAME, "Event", "Report")
        event_data = payload.get("event") if isinstance(payload.get("event"), dict) else {}
        association_data = payload["association"]
        log_data = {
            "association_uuid": association_uuid,
            "association_name": association_data.get("name"),
            "association_url": association_data.get("url"),
            "run_uuid": run_uuid,
            "event_name": event_data.get("name"),
            "signups_total": payload.get("signups_total"),
            "sent_at": payload.get("sent_at"),
            "received_at": payload["received_at"],
            "ip_address": ip_address,
        }
        Log.objects.create(
            member=system_member,
            eid=0,
            cls="EventReport",
            dct=json.dumps(log_data),
            element_name=str(event_data.get("name") or "")[:500],
            info=f"{association_uuid}_{run_uuid}",
        )
    except Exception:
        logger.exception("Event report: logging reception of %s_%s failed", association_uuid, run_uuid)
