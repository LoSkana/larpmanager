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
from datetime import timedelta
from typing import TYPE_CHECKING

import requests
from django.db.models import Max, Min
from django.utils import timezone

from larpmanager.cache.config import get_association_config, save_single_config
from larpmanager.models.access import EventRole
from larpmanager.models.event import Run
from larpmanager.models.registration import Registration, RegistrationTicket, TicketTier
from larpmanager.utils.larpmanager.tasks import my_send_mail, notify_admins

if TYPE_CHECKING:
    from larpmanager.models.association import Association
    from larpmanager.models.event import Event

logger = logging.getLogger(__name__)

ILDB_API_BASE = "https://www.larpdatabase.com/api/v1"
ILDB_CONFIG_KEY = "ildb_api_key"
ILDB_TEAM_CONFIG_KEY = "ildb_team_id"
ILDB_RUN_CONFIG = "ildb"


def upload_ildb(association: Association) -> None:
    """Upload past runs to larpdatabase.com (ILDB) as draft events.

    Checks all runs whose end date is more than one month ago. For each run
    not yet uploaded (no RunConfig "ildb" = True), calls the ILDB API to
    create a draft event with crew data, then marks the run as uploaded and
    notifies the association via email.

    Args:
        association: Association instance with ILDB API key configured.

    """
    api_key = get_association_config(association.id, ILDB_CONFIG_KEY, default_value="")
    team_id = get_association_config(association.id, ILDB_TEAM_CONFIG_KEY, default_value="")
    if not api_key or not team_id:
        return

    one_month_ago = timezone.now().date() - timedelta(days=30)
    runs = Run.objects.filter(
        event__association=association,
        end__lt=one_month_ago,
    ).select_related("event", "event__association")

    for run in runs:
        if run.get_config(ILDB_RUN_CONFIG, default_value=False):
            continue

        try:
            _process_run(run, api_key, team_id, association)
        except Exception as exc:
            logger.exception("ILDB upload failed for run %s", run.id)
            notify_admins(f"ILDB upload failed for run {run.id}", str(run), exc)


def _process_run(run: Run, api_key: str, team_id: str, association: Association) -> None:
    """Process a single run, uploading event and crew data to ILDB as a draft, and notify the association.

    Args:
        run: Run instance to upload.
        api_key: ILDB API authentication token.
        team_id: ILDB team ID that owns the event.
        association: Association instance owning the run.

    """
    event = run.event

    # Load event
    payload = _build_event_payload(event, run)
    ildb_event_id = _upload_event(api_key, payload, team_id)

    # Load crew
    crew = _build_crew(run, event)
    _upload_crew(crew, api_key, team_id, ildb_event_id)

    # Mark as processed
    save_single_config(run, ILDB_RUN_CONFIG, "True")

    # Notify association
    _notify_association(association, run, ildb_event_id)


def _upload_event(api_key: str, payload: dict, team_id: str) -> str:
    """Upload event paylod to the API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    response = requests.post(
        f"{ILDB_API_BASE}/teams/{team_id}/events",
        json=payload,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("id", "")


PLAYER_TIERS = [
    TicketTier.STANDARD,
    TicketTier.NEW_PLAYER,
    TicketTier.FILLER,
    TicketTier.REDUCED,
    TicketTier.PATRON,
]


def _build_event_payload(event: Event, run: Run) -> dict:
    """Build the payload with the event data."""
    days = (run.end - run.start).days + 1 if run.start and run.end else None

    player_count = Registration.objects.filter(
        run=run, cancellation_date__isnull=True, ticket__tier__in=PLAYER_TIERS
    ).count()

    ticket_prices = RegistrationTicket.objects.filter(
        event=run.event, tier__in=PLAYER_TIERS, deleted__isnull=True
    ).aggregate(costo=Min("price"), costo_max=Max("price"))

    return {
        "nome": event.name,
        "abstract": event.description or "",
        "data_inizio": run.start.isoformat() if run.start else None,
        "data_fine": run.end.isoformat() if run.end else None,
        "run": str(run.number) if run.number else None,
        "durata": days,
        "tipo_durata": "giorni" if days else None,
        "luogo": event.where or None,
        "sito_evento": event.website or None,
        "numero_partecipanti": player_count or None,
        "costo": ticket_prices["costo"],
        "costo_max": ticket_prices["costo_max"],
    }


def _upload_crew(crew: list[dict], api_key: str, team_id: str, event_id: str) -> None:
    """POST each crew member to the ILDB crew endpoint.

    Args:
        crew: List of crew entry dicts.
        api_key: ILDB API authentication token.
        team_id: ILDB team ID.
        event_id: ILDB event ID returned by event creation.

    """
    if not event_id:
        return

    url = f"{ILDB_API_BASE}/teams/{team_id}/events/{event_id}/crew"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    for entry in crew:
        response = requests.post(url, json=entry, headers=headers, timeout=30)
        response.raise_for_status()


def _build_member_first_role(roles: list) -> dict[int, str]:
    """Return a mapping of member id to the name of their first (lowest-number) event role.

    Args:
        roles: EventRole instances ordered by number ascending.

    Returns:
        Dict mapping member id to role name.

    """
    member_first_role: dict[int, str] = {}
    for role in roles:
        for member in role.members.all():
            if member.id not in member_first_role:
                member_first_role[member.id] = role.name
    return member_first_role


def _make_crew_entry(member: object, *, is_organizer: bool, role_name: str) -> dict:
    """Build a single crew entry dict for the ILDB crew API.

    Uses nickname as first_name (empty last_name) when set, otherwise the
    member's real name and surname.

    Args:
        member: Member instance.
        is_organizer: Whether the member is an organizer.
        role_name: Role name string (empty for players without an event role).

    Returns:
        Crew entry dict ready for POST /teams/{team}/events/{event}/crew.

    """
    if member.nickname:  # type: ignore[attr-defined]
        first_name = member.nickname  # type: ignore[attr-defined]
        last_name = ""
    else:
        first_name = member.name  # type: ignore[attr-defined]
        last_name = member.surname  # type: ignore[attr-defined]

    return {
        "entity_type": "person",
        "first_name": first_name,
        "last_name": last_name,
        "role": role_name,
        "is_organizer": is_organizer,
    }


def _build_crew(run: Run, event: object) -> list[dict]:
    """Build the crew list for the ILDB event payload.

    Collects all EventRole members (staff/organizers) and player registrations,
    de-duplicating by member. For each person:
    - first_name/last_name are set from nickname if the member has one
    - is_organizer is True if the member has any EventRole for this event
    - role is the name of their first EventRole (lowest number order),
      or empty for players without a role

    Args:
        run: Run instance.
        event: Event instance linked to the run.

    Returns:
        List of crew dictionaries ready for the ILDB API payload.

    """
    crew: list[dict] = []
    processed_member_ids: set[int] = set()

    # Fetch all event roles ordered by number; build member -> first role name map
    roles = list(
        EventRole.objects.filter(event=event, deleted__isnull=True).prefetch_related("members").order_by("number")
    )
    member_first_role = _build_member_first_role(roles)

    # Add EventRole members first (staff / organisers)
    for role in roles:
        for member in role.members.all():
            if member.id in processed_member_ids:
                continue
            processed_member_ids.add(member.id)
            crew.append(_make_crew_entry(member, is_organizer=True, role_name=member_first_role[member.id]))

    # Add registered players (all non-waiting, non-cancelled registrations)
    registrations = (
        Registration.objects.filter(run=run, cancellation_date__isnull=True)
        .exclude(ticket__tier=TicketTier.WAITING)
        .select_related("member", "ticket")
    )
    for reg in registrations:
        member = reg.member
        if member.id in processed_member_ids:
            continue
        processed_member_ids.add(member.id)
        is_organizer = member.id in member_first_role
        role_name = member_first_role.get(member.id, "")
        crew.append(_make_crew_entry(member, is_organizer=is_organizer, role_name=role_name))

    return crew


def _notify_association(association: Association, run: Run, ildb_event_id: str) -> None:
    """Send an email to the association's main address notifying of the ILDB draft.

    Args:
        association: Association instance to notify.
        run: Run instance that was uploaded.
        ildb_event_id: The event ID returned by the ILDB API.

    """
    if not association.main_mail:
        return

    review_url = f"https://www.larpdatabase.com/events/{ildb_event_id}/review"

    subject = f"[{association.name}] Event added to ILDB: {run.event.name}"
    body = (
        f"<p>The event <strong>{run.event.name}</strong> (run #{run.number}) "
        f"has been automatically added to larpdatabase.com as a draft.</p>"
        f"<p>Please review and submit it for publication: "
        f"<a href='{review_url}'>{review_url}</a></p>"
    )

    my_send_mail(subject, body, association.main_mail, association)
