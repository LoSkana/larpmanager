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
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import requests
from django.core.cache import cache
from django.db.models import Max, Min
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _

from larpmanager.cache.config import get_association_config, get_element_config, save_single_config
from larpmanager.forms.event import PublicationEventType, PublicationLanguage
from larpmanager.models.access import EventRole
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration, RegistrationTicket, TicketTier
from larpmanager.utils.core.common import clean_html, parse_multi_config
from larpmanager.utils.larpmanager.tasks import my_send_mail, notify_admins

if TYPE_CHECKING:
    from larpmanager.models.association import Association

logger = logging.getLogger(__name__)

# ---- ILDB API ---- #

ILDB_API_BASE = "https://www.larpdatabase.com/api/v1"
ILDB_CONFIG_KEY = "ildb_api_key"
ILDB_TEAM_CONFIG_KEY = "ildb_team_id"
ILDB_RUN_CONFIG = "ildb"


def _ildb_http(method: str, url: str, api_key: str = "", **kwargs: Any) -> requests.Response:
    """Execute one ILDB API call and sleep 1 s to stay within the 60 req/min limit.

    When api_key is provided, Authorization and Accept headers are injected automatically.
    """
    if api_key:
        headers = kwargs.pop("headers", {})
        headers.setdefault("Authorization", f"Bearer {api_key}")
        headers.setdefault("Accept", "application/json")
        kwargs["headers"] = headers
    response = getattr(requests, method)(url, **kwargs)
    time.sleep(1)
    return response


def _ildb_sync_entry(
    base_url: str,
    api_key: str,
    key: tuple[str, str],
    existing: dict[tuple[str, str], int],
    entry: dict | None,
) -> None:
    """POST, PUT, or DELETE a single entry based on its presence in *existing*.

    entry=None signals a deletion: the remote record is removed if present.
    Otherwise the entry is PUT (update) when the key already exists, or POST (create).
    """
    if entry is None:
        if key in existing:
            _ildb_http("delete", f"{base_url}/{existing[key]}", api_key=api_key, timeout=30).raise_for_status()
    elif key in existing:
        _ildb_http("put", f"{base_url}/{existing[key]}", api_key=api_key, json=entry, timeout=30).raise_for_status()
    else:
        _ildb_http("post", base_url, api_key=api_key, json=entry, timeout=30).raise_for_status()


@dataclass
class IldbCtx:
    """Prepared ILDB context for a ready-to-publish event."""

    api_key: str
    team_id: str
    association: Association
    ildb_event_id: str = field(default="")


def _get_ildb_context(event: Event, run: Run | None = None) -> IldbCtx | None:
    """Return IldbCtx if the event is ready and credentials are set, else None.

    When run is provided, ildb_event_id is the stored ILDB run ID (empty if not yet published).
    """
    association = event.association
    api_key = get_association_config(association.id, ILDB_CONFIG_KEY, default_value="")
    team_id = get_association_config(association.id, ILDB_TEAM_CONFIG_KEY, default_value="")
    if not api_key or not team_id:
        return None
    ildb_event_id = ""
    if run is not None:
        stored = run.get_config(ILDB_RUN_CONFIG, default_value="")
        if stored and stored not in ("True", "False"):
            ildb_event_id = stored
    return IldbCtx(api_key=api_key, team_id=team_id, association=association, ildb_event_id=ildb_event_id)


def _send_request(method: str, url: str, ctx: IldbCtx, payload: dict, locandina: object) -> requests.Response:
    """Send a POST or PUT event request, using multipart when a cover image is present."""
    if locandina:
        data = []
        for k, v in payload.items():
            if isinstance(v, list):
                data.extend((f"{k}[]", item) for item in v)
            else:
                data.append((k, v))
        with locandina.open("rb") as f:
            return _ildb_http(method, url, api_key=ctx.api_key, data=data, files={"locandina": f}, timeout=30)
    return _ildb_http(method, url, api_key=ctx.api_key, json=payload, timeout=30)


# ---- EVENT ---- #


def sync_event(event_id: int) -> None:
    """Create or update the ILDB entry for all eligible runs of an event."""
    event = Event.objects.select_related("association").get(pk=event_id)
    ctx = _get_ildb_context(event)
    if not ctx:
        return
    for run in event.runs.all():
        run_ctx = _get_ildb_context(event, run)
        try:
            _sync_run(run, run_ctx)
        except Exception as exc:
            logger.exception("ILDB sync_event failed for run %s", run.id)
            notify_admins(f"ILDB sync_event failed for run {run.id}", str(run), exc)


def _sync_run(run: Run, ctx: IldbCtx) -> None:
    """Create or update a run on ILDB, then sync crew/cast and notify the association."""
    event = run.event
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

    ctx.ildb_event_id = _find_event_id(run, ctx)
    if ctx.ildb_event_id:
        _update_event(ctx, payload, locandina)
        return

    # Create new event, notify association, save event_id
    ctx.ildb_event_id = _create_event(ctx, payload, locandina)
    save_single_config(run, ILDB_RUN_CONFIG, ctx.ildb_event_id)
    _notify_association(ctx.association, run, ctx.ildb_event_id)


def _find_event_id(run: Run, ctx: IldbCtx) -> str:
    """Return the ILDB event ID for a run, checking local config then the ILDB API.

    If a matching draft event is found via the API, notifies the association by email.
    """
    stored = run.get_config(ILDB_RUN_CONFIG, default_value="")
    if stored and stored not in ("True", "False"):
        return stored

    page = 1
    while True:
        response = _ildb_http(
            "get", f"{ILDB_API_BASE}/teams/{ctx.team_id}/events", api_key=ctx.api_key, params={"page": page}, timeout=30
        )
        response.raise_for_status()
        body = response.json()
        for ev in body.get("data", []):
            if slugify(ev.get("nome")) == slugify(run.search):
                return str(ev["id"])
        meta = body.get("meta", {})
        if page >= meta.get("last_page", 1):
            break
        page += 1
    return ""


def _create_event(ctx: IldbCtx, payload: dict, locandina: object = None) -> str:
    """POST a new event to ILDB and return its ID."""
    url = f"{ILDB_API_BASE}/teams/{ctx.team_id}/events"
    response = _send_request("post", url, ctx, payload, locandina)
    if not response.ok:
        logger.error("ILDB event create failed %s: %s", response.status_code, response.text)
    response.raise_for_status()
    return str(response.json().get("data", {}).get("id", ""))


def _update_event(ctx: IldbCtx, payload: dict, locandina: object = None) -> None:
    """PUT updated fields to an existing ILDB event."""
    url = f"{ILDB_API_BASE}/teams/{ctx.team_id}/events/{ctx.ildb_event_id}"
    response = _send_request("put", url, ctx, payload, locandina)
    if not response.ok:
        logger.error("ILDB event update failed %s: %s", response.status_code, response.text)


PLAYER_TIERS = [
    TicketTier.STANDARD,
    TicketTier.NEW_PLAYER,
    TicketTier.FILLER,
    TicketTier.REDUCED,
    TicketTier.PATRON,
]
_ILDB_GENRES_URL = "https://www.larpdatabase.com/api/v1/genres"
_ILDB_GENRES_CACHE_KEY = "ildb_genre_slug_map"
_ILDB_GENRES_CACHE_TTL = 86400  # 24 hours


def _get_genre_slug_map() -> dict[str, int]:
    """Return a slug -> ID map built from the larpdatabase genres API, cached for 24h."""
    result = cache.get(_ILDB_GENRES_CACHE_KEY)
    if result is not None:
        return result
    try:
        response = _ildb_http("get", _ILDB_GENRES_URL, timeout=10)
        response.raise_for_status()
        res_json = response.json()
        if not res_json.get("success"):
            notify_admins("_get_genre_slug_map", f"Failed genre fetch: {response}")
            return {}
        genres = res_json.get("data", [])
        result = {slugify(g["name_en"]): g["id"] for g in genres}
        cache.set(_ILDB_GENRES_CACHE_KEY, result, _ILDB_GENRES_CACHE_TTL)
    except Exception as err:  # noqa: BLE001
        notify_admins("_get_genre_slug_map", "Failed to fetch ILDB genres", err)
        result = {}
    return result


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
    genre_map = _get_genre_slug_map()
    setting_raw = get_element_config(event, "pub_setting", default_value="")
    mood_raw = get_element_config(event, "pub_mood", default_value="")
    slugs = parse_multi_config(setting_raw) + parse_multi_config(mood_raw)
    genere_ids = {genre_map[s] for s in slugs if s in genre_map}
    genere = sorted(genere_ids) or [genre_map.get("no-genre-specified", 27)]

    lingua_raw = get_element_config(event, "pub_language", default_value="")
    lingua = parse_multi_config(lingua_raw) or [PublicationLanguage.values[0]]

    tipologia_raw = get_element_config(event, "pub_event_type", default_value="") or PublicationEventType.values[0]
    tipologia = _TIPOLOGIA_MAP.get(tipologia_raw, tipologia_raw)

    luogo = get_element_config(event, "pub_place", default_value="") or event.where or None
    nazione = get_element_config(event, "pub_country", default_value="") or None

    accommodation_raw = get_element_config(event, "pub_accommodation", default_value="")
    accommodation = _ACCOMMODATION_MAP.get(accommodation_raw, accommodation_raw) or None

    tipo_accommodation_raw = get_element_config(event, "pub_accommodation_type", default_value="")
    tipo_accommodation = [_ACCOMMODATION_TYPE_MAP.get(v, v) for v in parse_multi_config(tipo_accommodation_raw)] or None

    pasti_raw = get_element_config(event, "pub_meals", default_value="")
    pasti = [_MEALS_MAP.get(v, v) for v in parse_multi_config(pasti_raw)] or None

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


# ---- CREW ---- #


def _member_name_key(member: Member) -> tuple[str, str]:
    if member.nickname:
        return member.nickname, ""
    return member.name, member.surname


def _sync_crew_full(crew: list[dict], ctx: IldbCtx) -> None:
    """Full crew sync: PUT existing, POST new, DELETE removed. Used on initial publish and role metadata changes."""
    if not ctx.ildb_event_id:
        return

    base_url = f"{ILDB_API_BASE}/teams/{ctx.team_id}/events/{ctx.ildb_event_id}/crew"

    response = _ildb_http("get", base_url, api_key=ctx.api_key, timeout=30)
    response.raise_for_status()
    existing = {(e["first_name"], e["last_name"]): e["id"] for e in response.json().get("data", [])}
    local_keys = {(e["first_name"], e["last_name"]) for e in crew}

    for entry in crew:
        _ildb_sync_entry(base_url, ctx.api_key, (entry["first_name"], entry["last_name"]), existing, entry)

    for key in existing:
        if key not in local_keys:
            _ildb_sync_entry(base_url, ctx.api_key, key, existing, None)


def sync_crew_member(event_role_id: int, member_id: int, *, delete: bool = False) -> None:
    """POST/PUT or DELETE a single crew member on ILDB based on their current role state.

    On delete=True, checks if the member still belongs to any role before removing.
    If they remain in another role, their entry is updated instead of deleted.
    """
    role = EventRole.objects.select_related("event__association").get(pk=event_role_id)
    ctx = _get_ildb_context(role.event)
    if not ctx or not get_association_config(ctx.association.id, "publication_crew", default_value=False):
        return

    member = Member.objects.get(pk=member_id)
    key = _member_name_key(member)

    first_remaining = (
        EventRole.objects.filter(event=role.event, members__id=member_id, deleted__isnull=True)
        .order_by("number")
        .first()
    )

    one_month_ago = timezone.now().date() - timedelta(days=30)
    for run in role.event.runs.filter(end__gte=one_month_ago, end__lte=timezone.now().date()):
        stored = run.get_config(ILDB_RUN_CONFIG, default_value="")
        if not stored or stored in ("True", "False"):
            continue
        ctx.ildb_event_id = stored

        base_url = f"{ILDB_API_BASE}/teams/{ctx.team_id}/events/{ctx.ildb_event_id}/crew"
        response = _ildb_http("get", base_url, api_key=ctx.api_key, timeout=30)
        response.raise_for_status()
        existing = {(e["first_name"], e["last_name"]): e["id"] for e in response.json().get("data", [])}

        if delete and first_remaining is None:
            _ildb_sync_entry(base_url, ctx.api_key, key, existing, None)
        elif first_remaining is not None:
            entry = _make_crew_entry(member, is_organizer=first_remaining.number == 1, role_name=first_remaining.name)
            _ildb_sync_entry(base_url, ctx.api_key, key, existing, entry)


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


# ---- CAST ---- #


def sync_cast(registration_id: int, _run_id: int | None = None) -> None:
    """POST/PUT or DELETE the ILDB cast entry for a single registration.

    Decides based on the registration state: if not existing / cancellation_date -> DELETE,
    otherwise POST (new) or PUT (existing).
    """
    try:
        reg = (
            Registration.objects.select_related("run__event__association", "member", "ticket")
            .prefetch_related("rcrs__character")
            .get(pk=registration_id)
        )
    except Registration.DoesNotExist:
        return
    ctx = _get_ildb_context(reg.run.event, reg.run)
    if not ctx or not ctx.ildb_event_id:
        return
    if not get_association_config(ctx.association.id, "publication_cast", default_value=False):
        return

    key = _member_name_key(reg.member)
    base_url = f"{ILDB_API_BASE}/teams/{ctx.team_id}/events/{ctx.ildb_event_id}/cast"
    response = _ildb_http("get", base_url, api_key=ctx.api_key, timeout=30)
    response.raise_for_status()
    existing = {(e["first_name"], e["last_name"]): e["id"] for e in response.json().get("data", [])}

    cancelled = bool(reg.cancellation_date) or reg.ticket.tier == TicketTier.WAITING
    rcr = None if cancelled else reg.rcrs.first()
    entry = (
        None
        if (cancelled or rcr is None)
        else _make_cast_entry(reg.member, rcr.custom_name or rcr.character.name, npc=reg.ticket.tier == TicketTier.NPC)
    )
    _ildb_sync_entry(base_url, ctx.api_key, key, existing, entry)


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


# ---- ASSOCIATION ---- #


def _notify_draft_pending(association: Association, run: Run, ildb_event_id: str) -> None:
    """Notify the association that a matching draft event was found on ILDB and needs review."""
    if not association.main_mail:
        return

    review_url = f"https://www.larpdatabase.com/events/{ildb_event_id}/review"
    subject = f"[{association.name}] " + _("ILDB draft event pending confirmation") + ": " + run.event.name
    body = (
        "<p>"
        + _("A draft event matching <strong>%(event)s</strong> was found on larpdatabase.com.") % {"event": run.search}
        + "</p><p>"
        + _("Please review and confirm it before it can be published")
        + f": <a href='{review_url}'>{review_url}</a>"
        + "</p>"
    )
    my_send_mail(subject, body, association.main_mail, association)


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
