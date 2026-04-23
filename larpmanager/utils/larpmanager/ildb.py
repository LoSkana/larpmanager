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

import ast
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import requests
from django.db.models import Max, Min
from django.utils import timezone
from django.utils.translation import gettext as _

from larpmanager.cache.config import get_association_config, get_element_config, save_single_config
from larpmanager.forms.event import PublicationEventType, PublicationGenre, PublicationLanguage
from larpmanager.models.access import EventRole
from larpmanager.models.event import Run
from larpmanager.models.registration import Registration, RegistrationTicket, TicketTier
from larpmanager.utils.core.common import clean_html
from larpmanager.utils.larpmanager.tasks import my_send_mail, notify_admins

if TYPE_CHECKING:
    from larpmanager.models.association import Association
    from larpmanager.models.event import Event

logger = logging.getLogger(__name__)

ILDB_API_BASE = "https://www.larpdatabase.com/api/v1"
ILDB_CONFIG_KEY = "ildb_api_key"
ILDB_TEAM_CONFIG_KEY = "ildb_team_id"
ILDB_RUN_CONFIG = "ildb"


def upload_ildb(association: Association, *, skip_check: bool = False) -> None:
    """Upload past runs to larpdatabase.com (ILDB) as draft events.

    Checks all runs whose end date is more than one month ago. For each run
    not yet uploaded (no RunConfig "ildb" = True), calls the ILDB API to
    create a draft event with crew data, then marks the run as uploaded and
    notifies the association via email.

    Args:
        association: Association instance.
        skip_check: If check already uploaded needs to be skipped.

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
        if not skip_check and run.get_config(ILDB_RUN_CONFIG, default_value=False):
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
    payload, locandina = _build_event_payload(event, run)

    required = [
        "nome",
        "genere",
        "tipologia",
        "run",
        "lingua",
        "data_inizio",
        "data_fine",
        "durata",
        "tipo_durata",
        "numero_partecipanti",
    ]
    missing = [f for f in required if f not in payload]
    if missing:
        notify_admins(f"ILDB: skipping run {run.id} - missing required fields: {missing}", str(run))
        return

    ildb_event_id = _upload_event(api_key, payload, team_id, locandina)

    upload_staff = get_association_config(association.id, "ildb_crew_staff", default_value=False)
    if upload_staff:
        crew = _build_crew(event)
        _upload_crew(crew, api_key, team_id, ildb_event_id)

    upload_players = get_association_config(association.id, "ildb_crew_players", default_value=False)
    if upload_players:
        cast = _build_cast(run)
        _upload_cast(cast, api_key, team_id, ildb_event_id)

    # Mark as processed
    save_single_config(run, ILDB_RUN_CONFIG, "True")

    # Notify association
    _notify_association(association, run, ildb_event_id)


def _upload_event(api_key: str, payload: dict, team_id: str, locandina: object = None) -> str:
    """Upload event payload to the API.

    Sends as multipart/form-data when a cover image (locandina) is provided,
    otherwise sends as JSON.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    url = f"{ILDB_API_BASE}/teams/{team_id}/events"

    if locandina:
        # Flatten payload for multipart (arrays become repeated fields)
        data = []
        for k, v in payload.items():
            if isinstance(v, list):
                data.extend((f"{k}[]", item) for item in v)
            else:
                data.append((k, v))
        with locandina.open("rb") as f:
            response = requests.post(url, data=data, files={"locandina": f}, headers=headers, timeout=30)
    else:
        headers["Content-Type"] = "application/json"
        response = requests.post(url, json=payload, headers=headers, timeout=30)

    if not response.ok:
        logger.error("ILDB event upload failed %s: %s", response.status_code, response.text)
    response.raise_for_status()
    json_res = response.json()
    return json_res.get("data", {}).get("id", "")


PLAYER_TIERS = [
    TicketTier.STANDARD,
    TicketTier.NEW_PLAYER,
    TicketTier.FILLER,
    TicketTier.REDUCED,
    TicketTier.PATRON,
]

# Maps internal stored values to ILDB Italian API values
_TIPOLOGIA_MAP = {
    "one_shot": "one shot",
    "serie": "serie",
    "campaign": "campagna",
    "edu_larp": "edu larp",
    "convention": "convention",
    "other": "altro",
    "chamber": "chamber larp",
    "laog": "laog",
}

_ACCOMMODATION_MAP = {
    "included": "compresa",
    "nope": "non compresa",
    "nonres": "non residenziale",
}

_ACCOMMODATION_TYPE_MAP = {
    "camping": "campeggio",
    "agritourism": "agriturismo",
    "historical": "residenza d'epoca",
    "hotel": "hotel",
    "other": "altro",
}

_MEALS_MAP = {
    "nope": "non compresi",
    "restaurant": "ristorante",
    "diy": "fai da te",
    "internal": "catering interno",
    "external": "catering esterno",
}


def _parse_multi_config(value: str) -> list:
    """Parse a MULTI_BOOL config string (stored as Python list repr) into a list."""
    if not value:
        return []
    try:
        result = ast.literal_eval(value)
        return result if isinstance(result, list) else []
    except (ValueError, SyntaxError):
        return []


def _build_event_payload(event: Event, run: Run) -> tuple[dict, Any | None]:
    """Build the payload with the event data."""
    days = (run.end - run.start).days + 1 if run.start and run.end else None

    player_count = Registration.objects.filter(
        run=run, cancellation_date__isnull=True, ticket__tier__in=PLAYER_TIERS
    ).count()

    ticket_prices = RegistrationTicket.objects.filter(
        event=run.event, tier__in=PLAYER_TIERS, deleted__isnull=True
    ).aggregate(costo=Min("price"), costo_max=Max("price"))

    # Load publication metadata from EventConfig
    genere_raw = get_element_config(event, "pub_genre", default_value="")
    genere = [int(g) for g in _parse_multi_config(genere_raw) if g.isdigit()] or [int(PublicationGenre.values[0])]

    lingua_raw = get_element_config(event, "pub_language", default_value="")
    lingua = _parse_multi_config(lingua_raw) or [PublicationLanguage.values[0]]

    tipologia_raw = get_element_config(event, "pub_event_type", default_value="") or PublicationEventType.values[0]
    tipologia = _TIPOLOGIA_MAP.get(tipologia_raw, tipologia_raw)

    luogo = get_element_config(event, "pub_place", default_value="") or event.where or None
    nazione = get_element_config(event, "pub_country", default_value="") or None

    accommodation_raw = get_element_config(event, "pub_accommodation", default_value="")
    accommodation = _ACCOMMODATION_MAP.get(accommodation_raw, accommodation_raw) or None

    tipo_accommodation_raw = get_element_config(event, "pub_accommodation_type", default_value="")
    tipo_accommodation = [
        _ACCOMMODATION_TYPE_MAP.get(v, v) for v in _parse_multi_config(tipo_accommodation_raw)
    ] or None

    pasti_raw = get_element_config(event, "pub_meals", default_value="")
    pasti = [_MEALS_MAP.get(v, v) for v in _parse_multi_config(pasti_raw)] or None

    lat = get_element_config(event, "pub_lat", default_value="").strip()
    lon = get_element_config(event, "pub_lon", default_value="").strip()
    location = f"{lat},{lon}" if lat and lon else None

    locandina = event.cover if event.cover else None

    payload = {
        "nome": event.name,
        "abstract": clean_html(event.description) or "",
        "data_inizio": run.start.isoformat() if run.start else None,
        "data_fine": run.end.isoformat() if run.end else None,
        "run": str(run.number) if run.number else None,
        "durata": days,
        "tipo_durata": "giorni" if days else None,
        "luogo": luogo,
        "nazione": nazione,
        "accommodation": accommodation,
        "tipo_accommodation": tipo_accommodation,
        "pasti": pasti,
        "sito_evento": event.website or None,
        "numero_partecipanti": player_count if player_count >= 1 else None,
        "costo": float(ticket_prices["costo"]) if ticket_prices["costo"] is not None else None,
        "costo_max": float(ticket_prices["costo_max"]) if ticket_prices["costo_max"] is not None else None,
        "tipologia": tipologia,
        "genere": genere,
        "lingua": lingua,
        "location": location,
    }
    return {k: v for k, v in payload.items() if v is not None}, locandina


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


def _build_crew(event: object) -> list[dict]:
    """Build the crew list (staff/organizers) for the ILDB event payload.

    Collects all EventRole members, de-duplicating by member.
    is_organizer is True only for members of the role with number=1.

    Args:
        event: Event instance.

    Returns:
        List of crew dictionaries ready for the ILDB crew API.

    """
    crew: list[dict] = []
    processed_member_ids: set[int] = set()

    roles = list(
        EventRole.objects.filter(event=event, deleted__isnull=True).prefetch_related("members").order_by("number")
    )
    member_first_role = _build_member_first_role(roles)

    for role in roles:
        is_organizer = role.number == 1
        for member in role.members.all():
            if member.id in processed_member_ids:
                continue
            processed_member_ids.add(member.id)
            crew.append(_make_crew_entry(member, is_organizer=is_organizer, role_name=member_first_role[member.id]))

    return crew


def _make_cast_entry(member: object, character_name: str, *, npc: bool) -> dict:
    """Build a single cast entry dict for the ILDB cast API.

    Args:
        member: Member instance.
        character_name: Name of the character played.
        npc: Whether this is an NPC.

    Returns:
        Cast entry dict ready for POST /teams/{team}/events/{event}/cast.

    """
    if member.nickname:  # type: ignore[attr-defined]
        first_name = member.nickname  # type: ignore[attr-defined]
        last_name = ""
    else:
        first_name = member.name  # type: ignore[attr-defined]
        last_name = member.surname  # type: ignore[attr-defined]

    return {
        "first_name": first_name,
        "last_name": last_name,
        "character": character_name,
        "npc": npc,
    }


def _build_cast(run: Run) -> list[dict]:
    """Build the cast list (players) for the ILDB event payload.

    Collects all non-cancelled, non-waiting registrations that have an
    assigned character, de-duplicating by member.

    Args:
        run: Run instance.

    Returns:
        List of cast dictionaries ready for the ILDB cast API.

    """
    cast: list[dict] = []
    processed_member_ids: set[int] = set()

    registrations = (
        Registration.objects.filter(run=run, cancellation_date__isnull=True)
        .exclude(ticket__tier=TicketTier.WAITING)
        .select_related("member", "ticket")
        .prefetch_related("rcrs__character")
    )
    for reg in registrations:
        member = reg.member
        if member.id in processed_member_ids:
            continue

        rcr = reg.rcrs.first()
        if rcr is None:
            continue

        processed_member_ids.add(member.id)
        character_name = rcr.custom_name or rcr.character.name
        npc = reg.ticket.tier == TicketTier.NPC
        cast.append(_make_cast_entry(member, character_name, npc=npc))

    return cast


def _upload_cast(cast: list[dict], api_key: str, team_id: str, event_id: str) -> None:
    """POST each cast member to the ILDB cast endpoint.

    Args:
        cast: List of cast entry dicts.
        api_key: ILDB API authentication token.
        team_id: ILDB team ID.
        event_id: ILDB event ID returned by event creation.

    """
    if not event_id:
        return

    url = f"{ILDB_API_BASE}/teams/{team_id}/events/{event_id}/cast"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    for entry in cast:
        response = requests.post(url, json=entry, headers=headers, timeout=30)
        response.raise_for_status()


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

    subject = f"[{association.name}] " + _("Event added to ILDB") + ": " + run.event.name
    body = (
        "<p>"
        + _("The event <strong>%(event)s</strong> has been automatically added to larpdatabase.com as a draft.")
        % {"event": run.search}
        + "</p><p>"
        + _("Please review and submit it for publication")
        + f": <a href='{review_url}'>{review_url}</a>"
        + "</p>"
    )

    my_send_mail(subject, body, association.main_mail, association)
