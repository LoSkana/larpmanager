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

from datetime import datetime
from typing import TYPE_CHECKING

from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

from larpmanager.cache.config import get_event_config

if TYPE_CHECKING:
    from django.http import HttpRequest, QueryDict

    from larpmanager.models.base import BaseModel
    from larpmanager.models.member import Member

# Tolerance in seconds when comparing the version stamp of the loaded form with the saved one,
# to absorb the rounding of the stamp sent to the browser and back
STALE_TOLERANCE = 0.001

# How long an unsaved draft survives in redis before it is dropped
DRAFT_TTL = 7 * 24 * 60 * 60

# Control fields posted by the auto-save JS that must never be replayed verbatim on restore
DRAFT_EXCLUDED_FIELDS = ("ajax", "csrfmiddlewaretoken", "base_updated")


def set_auto_save(context: dict, config_name: str = "writing_disable_auto") -> None:
    """Activate the background auto-save of a player-facing writing form, unless disabled for the event."""
    context["auto_save"] = not get_event_config(
        context["event"].id,
        config_name,
        context=context,
    )


def init_auto_save(context: dict, instance: BaseModel | None) -> None:
    """Seed the auto-save context with the version stamp of the loaded element.

    Used by the browser to detect, on the next auto-save, whether the element was
    saved elsewhere in the meantime. No-op when auto-save is not active for the form.
    """
    if not context.get("auto_save"):
        return

    context["base_updated"] = ""
    if instance is not None and instance.pk:
        context["base_updated"] = f"{instance.updated.timestamp():.6f}"


def is_stale(context: dict, request: HttpRequest, instance: BaseModel | None) -> bool:
    """Check if the element was saved elsewhere after the form currently posted was loaded."""
    if not context.get("auto_save") or instance is None or not instance.pk:
        return False

    posted = request.POST.get("base_updated")
    if not posted:
        return False

    try:
        base_updated = float(posted)
    except ValueError:
        return False

    # The instance is loaded fresh in this request, so its stamp is the current one
    return instance.updated.timestamp() - base_updated > STALE_TOLERANCE


def draft_element_key(context: dict, kind: str, instance: BaseModel | None) -> str:
    """Build the staging key identifying an editable element, scoped by event when available."""
    scope = context["event"].slug if context.get("event") else "assoc"
    element_id = instance.uuid if instance is not None and instance.pk else "new"
    return f"{scope}:{kind}:{element_id}"


def _draft_cache_key(member: Member, element_key: str) -> str:
    return f"autosave:draft:{member.uuid}:{element_key}"


def draft_data_from_post(post: QueryDict) -> str:
    """Serialize posted form data for staging, dropping control fields that must not be replayed."""
    data = post.copy()
    for field in DRAFT_EXCLUDED_FIELDS:
        data.pop(field, None)
    return data.urlencode()


def save_draft(member: Member, element_key: str, data: str) -> None:
    """Stash the serialized form as a staging draft in redis, replacing any previous one for this key."""
    cache.set(
        _draft_cache_key(member, element_key),
        {"data": data, "saved_at": timezone.now().isoformat()},
        timeout=DRAFT_TTL,
    )


def clear_draft(member: Member, element_key: str) -> None:
    """Drop the staging draft. Called on an explicit real save, so a stale draft never resurfaces."""
    cache.delete(_draft_cache_key(member, element_key))


def save_draft_from_request(request: HttpRequest, context: dict, kind: str, instance: BaseModel | None) -> JsonResponse:
    """Stash the posted form as a staging draft, without touching the real record.

    Shared body of every auto-save ajax endpoint: builds the element key, stashes the draft,
    and answers with the same trivial payload (the real record is never validated nor saved).
    """
    element_key = draft_element_key(context, kind, instance)
    save_draft(context["member"], element_key, draft_data_from_post(request.POST))
    return JsonResponse({"res": "ok"})


def pop_draft(member: Member, element_key: str, instance_updated: datetime | None) -> str | None:
    """Return and consume the staging draft, if it postdates the element's last real save.

    The draft is removed from redis either way: once shown to the player it must not resurface
    on a later reload, and one that predates the current record is stale and must be discarded.
    """
    draft_key = _draft_cache_key(member, element_key)
    draft = cache.get(draft_key)
    if not draft:
        return None

    cache.delete(draft_key)

    if instance_updated is not None:
        saved_at = datetime.fromisoformat(draft["saved_at"])
        if saved_at <= instance_updated:
            return None

    return draft["data"]
