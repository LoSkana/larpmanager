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

from typing import TYPE_CHECKING, Any

from django.conf import settings as conf_settings
from django.core.cache import cache

from larpmanager.models.access import EventRole, get_event_staffers
from larpmanager.models.casting import Quest, QuestType
from larpmanager.models.event import ProgressStep
from larpmanager.models.experience import AbilityTypeExp, DeliveryExp
from larpmanager.models.writing import Character, Faction, Plot, Prologue

if TYPE_CHECKING:
    from larpmanager.models.event import Event

# Maps each cache key to its (model_class, order_field)
BULK_CACHE_CONFIG: dict[str, tuple[type, str]] = {
    "characters": (Character, "name"),
    "plots": (Plot, "name"),
    "factions": (Faction, "name"),
    "prologues": (Prologue, "name"),
    "progress_steps": (ProgressStep, "order"),
    "deliveries": (DeliveryExp, "name"),
    "quest_types": (QuestType, "name"),
    "quests": (Quest, "name"),
    "ability_types": (AbilityTypeExp, "name"),
}

# Maps model class to the cache key it invalidates
MODEL_TO_BULK_KEY: dict[type, str] = {model: key for key, (model, _) in BULK_CACHE_CONFIG.items()}


def get_bulk_cache_key(event_id: int, key: str) -> str:
    """Generate per-type, per-event cache key."""
    return f"event_bulk_{key}_{event_id}"


def reset_bulk_cache(event_id: int, key: str) -> None:
    """Delete one specific bulk options cache entry."""
    cache.delete(get_bulk_cache_key(event_id, key))


def reset_bulk_options_cache(event_id: int) -> None:
    """Delete all bulk options caches for an event."""
    for key in BULK_CACHE_CONFIG:
        reset_bulk_cache(event_id, key)
    reset_bulk_cache(event_id, "staffers")


def _init_bulk_key(event: Event, key: str) -> list[dict[str, Any]]:
    """Build the list for a single cache key."""
    if key == "staffers":
        return [{"uuid": m.uuid, "name": m.show_nick()} for m in get_event_staffers(event)]
    model, order = BULK_CACHE_CONFIG[key]
    return list(event.get_elements(model).values("uuid", "name").order_by(order))


def get_bulk_options_cache(event: Event, key: str) -> list[dict[str, Any]]:
    """Return cached list for key, building it on first access."""
    cache_key = get_bulk_cache_key(event.id, key)
    cached = cache.get(cache_key)
    if cached is None:
        cached = _init_bulk_key(event, key)
        cache.set(cache_key, cached, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return cached


# --- Signal handlers ---


def on_bulk_model_changed(sender: type, instance: Any, **kwargs: Any) -> None:  # noqa: ARG001
    """Clear the bulk cache for the model's type on save or delete."""
    key = MODEL_TO_BULK_KEY.get(type(instance))
    if key and hasattr(instance, "event_id") and instance.event_id:
        reset_bulk_cache(instance.event_id, key)


def on_event_role_deleted(sender: type, instance: Any, **kwargs: Any) -> None:  # noqa: ARG001
    """Clear staffers cache when an EventRole is deleted."""
    if instance.event_id:
        reset_bulk_cache(instance.event_id, "staffers")


def on_event_role_members_changed(sender: type, instance: Any, **kwargs: Any) -> None:  # noqa: ARG001
    """Clear staffers cache when EventRole members change."""
    action = kwargs.get("action", "")
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    # Forward: instance is the EventRole
    if isinstance(instance, EventRole) and instance.event_id:
        reset_bulk_cache(instance.event_id, "staffers")
        return
    # Reverse: instance is a Member; resolve event_ids from the affected EventRoles
    pk_set = kwargs.get("pk_set") or set()
    if pk_set:
        event_ids = EventRole.objects.filter(pk__in=pk_set).values_list("event_id", flat=True).distinct()
        for event_id in event_ids:
            if event_id:
                reset_bulk_cache(event_id, "staffers")
