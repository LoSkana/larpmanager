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
from functools import partial
from typing import Any

from django.conf import settings as conf_settings
from django.core.cache import cache

from larpmanager.cache.dirty import get_has_dirty_key, mark_dirty, refresh_if_dirty, resolve_dirty_section
from larpmanager.models.event import Event
from larpmanager.models.experience import AbilityPx, DeliveryPx, ModifierPx, RulePx
from larpmanager.utils.core.common import _validate_and_fetch_objects
from larpmanager.utils.larpmanager.tasks import background_auto

logger = logging.getLogger(__name__)

_PX_NS = "px"
_get_px_has_dirty_key = partial(get_has_dirty_key, _PX_NS)
_mark_px_dirty = partial(mark_dirty, _PX_NS)
_refresh_px_if_dirty = partial(refresh_if_dirty, _PX_NS)
_resolve_dirty_px_section = partial(resolve_dirty_section, _PX_NS)


def get_event_px_key(event_id: int) -> str:
    """Generate cache key for event PX relationships."""
    return f"event__px__{event_id}"


def clear_event_px_cache(event_id: int) -> None:
    """Reset event PX cache for given event ID."""
    # Clear cache for the main event
    cache_key = get_event_px_key(event_id)
    cache.delete(cache_key)
    logger.debug("Reset PX cache for event %s", event_id)

    # Invalidate cache for all child events to maintain consistency
    for child_event_id in Event.objects.filter(parent_id=event_id).values_list("pk", flat=True):
        cache_key = get_event_px_key(child_event_id)
        cache.delete(cache_key)


def build_relationship_dict(relationship_items: list) -> dict[str, Any]:
    """Build relationship dictionary with list and count."""
    return {"list": relationship_items, "count": len(relationship_items)}


def get_ability_rels(ability: AbilityPx) -> dict[str, Any]:
    """Get ability relationships (characters, prerequisites, and requirements).

    Args:
        ability: The AbilityPx instance to get relationships for

    Returns:
        Dictionary containing relationship data with the structure:
            {
                'character_rels': {
                    'list': [(char_id, char_name), ...],
                    'count': int
                },
                'prerequisite_rels': {
                    'list': [(ability_id, ability_name), ...],
                    'count': int
                },
                'requirement_rels': {
                    'list': [(option_id, option_name), ...],
                    'count': int
                }
            }

    """
    relationships = {}

    try:
        # Get all characters that have this ability
        ability_characters = ability.characters.all()
        character_list = [(character.uuid, character.name) for character in ability_characters]
        relationships["character_rels"] = build_relationship_dict(character_list)

        # Get all prerequisite abilities
        prerequisites = ability.prerequisites.all()
        prerequisite_list = [(prereq.uuid, prereq.name) for prereq in prerequisites]
        relationships["prerequisite_rels"] = build_relationship_dict(prerequisite_list)

        # Get all requirement options
        requirements = ability.requirements.all()
        requirement_list = [(req.uuid, req.name) for req in requirements]
        relationships["requirement_rels"] = build_relationship_dict(requirement_list)

    except Exception:
        logger.exception("Error getting relationships for ability %s", ability.id)
        relationships = {}

    return relationships


def get_delivery_rels(delivery: DeliveryPx) -> dict[str, Any]:
    """Get delivery relationships (characters).

    Args:
        delivery: The DeliveryPx instance to get relationships for

    Returns:
        Dictionary containing relationship data with the structure:
            {
                'character_rels': {
                    'list': [(char_id, char_name), ...],
                    'count': int
                }
            }

    """
    relationships = {}

    try:
        # Get all characters associated with this delivery
        delivery_characters = delivery.characters.all()
        character_list = [(character.uuid, character.name) for character in delivery_characters]
        relationships["character_rels"] = build_relationship_dict(character_list)

    except Exception:
        logger.exception("Error getting relationships for delivery %s", delivery.id)
        relationships = {}

    return relationships


def get_modifier_rels(modifier: ModifierPx) -> dict[str, Any]:
    """Get modifier relationships (abilities, prerequisites, and requirements).

    Args:
        modifier: The ModifierPx instance to get relationships for

    Returns:
        Dictionary containing relationship data with the structure:
            {
                'ability_rels': {
                    'list': [(ability_id, ability_name), ...],
                    'count': int
                },
                'prerequisite_rels': {
                    'list': [(ability_id, ability_name), ...],
                    'count': int
                },
                'requirement_rels': {
                    'list': [(option_id, option_name), ...],
                    'count': int
                }
            }

    """
    relationships = {}

    try:
        # Get all abilities this modifier applies to
        modifier_abilities = modifier.abilities.all()
        ability_list = [(ability.uuid, ability.name) for ability in modifier_abilities]
        relationships["ability_rels"] = build_relationship_dict(ability_list)

        # Get all prerequisite abilities
        prerequisites = modifier.prerequisites.all()
        prerequisite_list = [(prereq.uuid, prereq.name) for prereq in prerequisites]
        relationships["prerequisite_rels"] = build_relationship_dict(prerequisite_list)

        # Get all requirement options
        requirements = modifier.requirements.all()
        requirement_list = [(req.uuid, req.name) for req in requirements]
        relationships["requirement_rels"] = build_relationship_dict(requirement_list)

    except Exception:
        logger.exception("Error getting relationships for modifier %s", modifier.id)
        relationships = {}

    return relationships


def get_rule_rels(rule: RulePx) -> dict[str, Any]:
    """Get rule relationships (abilities).

    Args:
        rule: The RulePx instance to get relationships for

    Returns:
        Dictionary containing relationship data with the structure:
            {
                'ability_rels': {
                    'list': [(ability_id, ability_name), ...],
                    'count': int
                }
            }

    """
    relationships = {}

    try:
        # Get all abilities this rule applies to
        rule_abilities = rule.abilities.all()
        ability_list = [(ability.uuid, ability.name) for ability in rule_abilities]
        relationships["ability_rels"] = build_relationship_dict(ability_list)

    except Exception:
        logger.exception("Error getting relationships for rule %s", rule.id)
        relationships = {}

    return relationships


def init_event_px_all(event: Event) -> dict[str, dict[int, dict[str, Any]]]:
    """Initialize all PX relationships for an event and cache the result.

    Builds a complete relationship cache for all PX elements in the event,
    including abilities, deliveries, modifiers, and rules.

    Args:
        event: The Event instance to initialize PX relationships for

    Returns:
        Dictionary with relationship data structure organized by element type:
        {
            'abilities': {
                ability_id: {
                    'character_rels': {...},
                    'prerequisite_rels': {...},
                    'requirement_rels': {...}
                }
            },
            'deliveries': {
                delivery_id: relationship_data
            },
            'modifiers': {
                modifier_id: relationship_data
            },
            'rules': {
                rule_id: relationship_data
            }
        }

    """
    px_cache: dict[str, dict[int, dict[str, Any]]] = {}

    try:
        # Configuration mapping for each PX type
        px_configs = [
            ("abilities", AbilityPx, get_ability_rels),
            ("deliveries", DeliveryPx, get_delivery_rels),
            ("modifiers", ModifierPx, get_modifier_rels),
            ("rules", RulePx, get_rule_rels),
        ]

        # Process each PX type
        for cache_key_plural, model_class, get_relationships_function in px_configs:
            # Initialize the cache section for this type
            px_cache[cache_key_plural] = {}

            # Get all elements of this type associated with the event
            elements = event.get_elements(model_class)

            # Build relationships for each element
            for element in elements:
                px_cache[cache_key_plural][element.id] = get_relationships_function(element)

            logger.debug("Initialized %s %s for event %s", len(elements), cache_key_plural, event.id)

        # Cache the complete relationship data structure
        cache_key = get_event_px_key(event.id)
        cache.set(cache_key, px_cache, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug("Cached PX relationships for event %s", event.id)

    except Exception:
        # Log the error with full traceback and return empty result
        logger.exception("Error initializing PX relationships for event %s", event.id)
        px_cache = {}

    return px_cache


def get_event_px_cache(event: Event) -> dict[str, Any]:
    """Get event PX relationships from cache, initializing if not present.

    Retrieves cached PX relationship data for the specified event. If no cached
    data exists, initializes the cache with fresh relationship data.

    Args:
        event: The Event instance to get PX relationships for

    Returns:
        Dictionary containing cached PX relationship data

    """
    # Generate cache key for this specific event
    cache_key = get_event_px_key(event.id)

    # Attempt to retrieve cached relationships
    cached_relationships = cache.get(cache_key)

    # Initialize cache if no data found
    if cached_relationships is None:
        logger.debug("PX cache miss for event %s, initializing", event.id)
        return init_event_px_all(event)

    # Resolve any items still marked as dirty (not yet cleaned by background job)
    any_resolved = False
    if cache.get(_get_px_has_dirty_key(event.id)):
        for _section, _model, _get_rels in (
            ("abilities", AbilityPx, get_ability_rels),
            ("deliveries", DeliveryPx, get_delivery_rels),
            ("modifiers", ModifierPx, get_modifier_rels),
            ("rules", RulePx, get_rule_rels),
        ):
            if _resolve_dirty_px_section(event.id, cached_relationships, _section, _model, _get_rels):
                any_resolved = True
    if any_resolved:
        cache.set(get_event_px_key(event.id), cached_relationships, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_relationships


def update_cache_section(event_id: int, section_name: str, section_id: int, data: dict[str, Any]) -> None:
    """Update a specific section in the event PX cache.

    Args:
        event_id: The event ID
        section_name: Name of the cache section (e.g., 'abilities', 'deliveries')
        section_id: ID of the item within the section
        data: Data to store for this item

    """
    try:
        cache_key = get_event_px_key(event_id)
        cached_event_data = cache.get(cache_key)

        if cached_event_data is None:
            logger.debug("Cache miss during %s update for event %s, reinitializing", section_name, event_id)
            # We need to get the event to reinitialize
            event = Event.objects.get(id=event_id)
            init_event_px_all(event)
            return

        if section_name not in cached_event_data:
            cached_event_data[section_name] = {}

        cached_event_data[section_name][section_id] = data
        cache.set(cache_key, cached_event_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug("Updated %s %s PX relationships in cache", section_name, section_id)

    except Exception:
        logger.exception("Error updating %s %s PX relationships", section_name, section_id)
        clear_event_px_cache(event_id)


def remove_item_from_cache_section(event_id: int, section_name: str, section_id: int) -> None:
    """Remove an item from a specific section in the event PX cache.

    Args:
        event_id: The event ID
        section_name: Name of the cache section (e.g., 'abilities', 'deliveries')
        section_id: ID of the item to remove

    """
    try:
        cache_key = get_event_px_key(event_id)
        cached_data = cache.get(cache_key)
        if cached_data and section_name in cached_data and section_id in cached_data[section_name]:
            del cached_data[section_name][section_id]
            cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
            logger.debug("Removed %s %s from PX cache", section_name, section_id)
    except Exception:
        logger.exception("Error removing %s %s from PX cache", section_name, section_id)
        clear_event_px_cache(event_id)


def refresh_ability_relationships(ability: AbilityPx) -> None:
    """Update ability relationships in cache."""
    ability_relationship_data = get_ability_rels(ability)
    update_cache_section(ability.event_id, "abilities", ability.id, ability_relationship_data)


def refresh_delivery_relationships(delivery: DeliveryPx) -> None:
    """Update delivery relationships in cache."""
    delivery_relationship_data = get_delivery_rels(delivery)
    update_cache_section(delivery.event_id, "deliveries", delivery.id, delivery_relationship_data)


def refresh_modifier_relationships(modifier: ModifierPx) -> None:
    """Update modifier relationships in cache."""
    modifier_relationship_data = get_modifier_rels(modifier)
    update_cache_section(modifier.event_id, "modifiers", modifier.id, modifier_relationship_data)


def refresh_rule_relationships(rule: RulePx) -> None:
    """Update rule relationships in cache."""
    rule_relationship_data = get_rule_rels(rule)
    update_cache_section(rule.event_id, "rules", rule.id, rule_relationship_data)


# Background tasks for cache updates


@background_auto(queue="cache-px")
def refresh_ability_character_rels_background(ability_ids: int | list[int]) -> None:
    """Update ability relationships in cache (dirty-aware background task)."""
    abilities = _validate_and_fetch_objects(AbilityPx, ability_ids, "AbilityPx")
    _refresh_px_if_dirty("abilities", abilities, refresh_ability_relationships)


@background_auto(queue="cache-px")
def refresh_delivery_rels_dirty_background(delivery_ids: int | list[int]) -> None:
    """Update delivery relationships in cache (dirty-aware background task)."""
    deliveries = _validate_and_fetch_objects(DeliveryPx, delivery_ids, "DeliveryPx")
    _refresh_px_if_dirty("deliveries", deliveries, refresh_delivery_relationships)


@background_auto(queue="cache-px")
def refresh_modifier_rels_dirty_background(modifier_ids: int | list[int]) -> None:
    """Update modifier relationships in cache (dirty-aware background task)."""
    modifiers = _validate_and_fetch_objects(ModifierPx, modifier_ids, "ModifierPx")
    _refresh_px_if_dirty("modifiers", modifiers, refresh_modifier_relationships)


@background_auto(queue="cache-px")
def refresh_rule_rels_dirty_background(rule_ids: int | list[int]) -> None:
    """Update rule relationships in cache (dirty-aware background task)."""
    rules = _validate_and_fetch_objects(RulePx, rule_ids, "RulePx")
    _refresh_px_if_dirty("rules", rules, refresh_rule_relationships)


# Signal handlers for M2M changes
def on_ability_characters_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: AbilityPx,
    action: str,
    pk_set: set[int] | None,
    reverse: bool = False,  # noqa: FBT001, FBT002
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle ability-character relationship changes.

    Updates ability cache when characters are added or removed.

    Args:
        sender: The M2M through model
        instance: The AbilityPx (if reverse=False) or Character (if reverse=True)
        action: The M2M action (pre_add, post_add, etc.)
        pk_set: Set of related object IDs
        reverse: True if signal was triggered from Character.px_ability_list
        **kwargs: Additional keyword arguments

    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    if reverse:
        # Signal came from Character.px_ability_list - instance is a Character
        # pk_set contains ability IDs, so refresh each ability
        if pk_set:
            ability_ids = list(pk_set)
        elif action == "post_clear":
            # Clear was called - need to refresh all abilities for this character
            ability_ids = list(AbilityPx.objects.filter(characters=instance).values_list("id", flat=True))
        else:
            ability_ids = []
    else:
        # Signal came from AbilityPx.characters - instance is an AbilityPx
        ability_ids = [instance.id]

    if not ability_ids:
        return

    _mark_px_dirty("abilities", ability_ids, instance.event_id)
    refresh_ability_character_rels_background(ability_ids)


def on_ability_prerequisites_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: AbilityPx,
    action: str,
    pk_set: set[int] | None,
    reverse: bool = False,  # noqa: FBT001, FBT002
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle ability-prerequisite relationship changes.

    Updates ability cache when prerequisites are added or removed.

    Args:
        sender: The M2M through model
        instance: The AbilityPx being modified
        action: The M2M action (pre_add, post_add, etc.)
        pk_set: Set of prerequisite ability IDs
        reverse: True if signal was triggered from px_ability_unlock
        **kwargs: Additional keyword arguments

    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    if reverse:
        # Signal came from px_ability_unlock reverse relation
        # instance is an AbilityPx that is a prerequisite for others
        # pk_set contains ability IDs that require this prerequisite
        if pk_set:
            ability_ids = list(pk_set)
        elif action == "post_clear":
            ability_ids = list(AbilityPx.objects.filter(prerequisites=instance).values_list("id", flat=True))
        else:
            ability_ids = []
    else:
        # Signal came from AbilityPx.prerequisites - instance is the ability being modified
        ability_ids = [instance.id]

    if not ability_ids:
        return

    _mark_px_dirty("abilities", ability_ids, instance.event_id)
    refresh_ability_character_rels_background(ability_ids)


def on_ability_requirements_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: AbilityPx,
    action: str,
    pk_set: set[int] | None,
    reverse: bool = False,  # noqa: FBT001, FBT002
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle ability-requirement relationship changes.

    Updates ability cache when requirements are added or removed.

    Args:
        sender: The M2M through model
        instance: The AbilityPx (if reverse=False) or WritingOption (if reverse=True)
        action: The M2M action (pre_add, post_add, etc.)
        pk_set: Set of related object IDs
        reverse: True if signal was triggered from WritingOption.abilities
        **kwargs: Additional keyword arguments

    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    if reverse:
        # Signal came from WritingOption.abilities - instance is a WritingOption
        # pk_set contains ability IDs, so refresh each ability
        if pk_set:
            ability_ids = list(pk_set)
        elif action == "post_clear":
            ability_ids = list(AbilityPx.objects.filter(requirements=instance).values_list("id", flat=True))
        else:
            ability_ids = []
        # WritingOption has no event_id; derive it from the affected abilities
        event_id = (
            AbilityPx.objects.filter(id__in=ability_ids).values_list("event_id", flat=True).first()
            if ability_ids
            else None
        )
    else:
        # Signal came from AbilityPx.requirements - instance is an AbilityPx
        ability_ids = [instance.id]
        event_id = instance.event_id

    if not ability_ids:
        return

    _mark_px_dirty("abilities", ability_ids, event_id)
    refresh_ability_character_rels_background(ability_ids)


def on_delivery_characters_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: DeliveryPx,
    action: str,
    pk_set: set[int] | None,
    reverse: bool = False,  # noqa: FBT001, FBT002
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle delivery-character relationship changes.

    Updates delivery cache when characters are added or removed.

    Args:
        sender: The M2M through model
        instance: The DeliveryPx (if reverse=False) or Character (if reverse=True)
        action: The M2M action (pre_add, post_add, etc.)
        pk_set: Set of related object IDs
        reverse: True if signal was triggered from Character side
        **kwargs: Additional keyword arguments

    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    if reverse:
        # Signal came from Character - instance is a Character
        # pk_set contains delivery IDs, so refresh each delivery
        if pk_set:
            delivery_ids = list(pk_set)
        elif action == "post_clear":
            delivery_ids = list(DeliveryPx.objects.filter(characters=instance).values_list("id", flat=True))
        else:
            delivery_ids = []
    else:
        # Signal came from DeliveryPx.characters - instance is a DeliveryPx
        delivery_ids = [instance.id]

    if not delivery_ids:
        return

    _mark_px_dirty("deliveries", delivery_ids, instance.event_id)
    refresh_delivery_rels_dirty_background(delivery_ids)


def on_modifier_abilities_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: ModifierPx,
    action: str,
    pk_set: set[int] | None,
    reverse: bool = False,  # noqa: FBT001, FBT002
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle modifier-ability relationship changes.

    Updates modifier cache when abilities are added or removed.

    Args:
        sender: The M2M through model
        instance: The ModifierPx (if reverse=False) or AbilityPx (if reverse=True)
        action: The M2M action (pre_add, post_add, etc.)
        pk_set: Set of related object IDs
        reverse: True if signal was triggered from AbilityPx side
        **kwargs: Additional keyword arguments

    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    if reverse:
        # Signal came from AbilityPx - instance is an AbilityPx
        # pk_set contains modifier IDs, so refresh each modifier
        if pk_set:
            modifier_ids = list(pk_set)
        elif action == "post_clear":
            modifier_ids = list(ModifierPx.objects.filter(abilities=instance).values_list("id", flat=True))
        else:
            modifier_ids = []
    else:
        # Signal came from ModifierPx.abilities - instance is a ModifierPx
        modifier_ids = [instance.id]

    if not modifier_ids:
        return

    _mark_px_dirty("modifiers", modifier_ids, instance.event_id)
    refresh_modifier_rels_dirty_background(modifier_ids)


def on_modifier_prerequisites_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: ModifierPx,
    action: str,
    pk_set: set[int] | None,
    reverse: bool = False,  # noqa: FBT001, FBT002
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle modifier-prerequisite relationship changes.

    Updates modifier cache when prerequisites are added or removed.

    Args:
        sender: The M2M through model
        instance: The ModifierPx (if reverse=False) or AbilityPx (if reverse=True)
        action: The M2M action (pre_add, post_add, etc.)
        pk_set: Set of related object IDs
        reverse: True if signal was triggered from AbilityPx side
        **kwargs: Additional keyword arguments

    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    if reverse:
        # Signal came from AbilityPx - instance is an AbilityPx that is a prerequisite
        # pk_set contains modifier IDs, so refresh each modifier
        if pk_set:
            modifier_ids = list(pk_set)
        elif action == "post_clear":
            modifier_ids = list(ModifierPx.objects.filter(prerequisites=instance).values_list("id", flat=True))
        else:
            modifier_ids = []
    else:
        # Signal came from ModifierPx.prerequisites - instance is a ModifierPx
        modifier_ids = [instance.id]

    if not modifier_ids:
        return

    _mark_px_dirty("modifiers", modifier_ids, instance.event_id)
    refresh_modifier_rels_dirty_background(modifier_ids)


def on_modifier_requirements_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: ModifierPx,
    action: str,
    pk_set: set[int] | None,
    reverse: bool = False,  # noqa: FBT001, FBT002
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle modifier-requirement relationship changes.

    Updates modifier cache when requirements are added or removed.

    Args:
        sender: The M2M through model
        instance: The ModifierPx (if reverse=False) or WritingOption (if reverse=True)
        action: The M2M action (pre_add, post_add, etc.)
        pk_set: Set of related object IDs
        reverse: True if signal was triggered from WritingOption side
        **kwargs: Additional keyword arguments

    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    if reverse:
        # Signal came from WritingOption - instance is a WritingOption
        # pk_set contains modifier IDs, so refresh each modifier
        if pk_set:
            modifier_ids = list(pk_set)
        elif action == "post_clear":
            modifier_ids = list(ModifierPx.objects.filter(requirements=instance).values_list("id", flat=True))
        else:
            modifier_ids = []
        # WritingOption has no event_id; derive it from the affected modifiers
        event_id = (
            ModifierPx.objects.filter(id__in=modifier_ids).values_list("event_id", flat=True).first()
            if modifier_ids
            else None
        )
    else:
        # Signal came from ModifierPx.requirements - instance is a ModifierPx
        modifier_ids = [instance.id]
        event_id = instance.event_id

    if not modifier_ids:
        return

    _mark_px_dirty("modifiers", modifier_ids, event_id)
    refresh_modifier_rels_dirty_background(modifier_ids)


def on_rule_abilities_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: RulePx,
    action: str,
    pk_set: set[int] | None,
    reverse: bool = False,  # noqa: FBT001, FBT002
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle rule-ability relationship changes.

    Updates rule cache when abilities are added or removed.

    Args:
        sender: The M2M through model
        instance: The RulePx (if reverse=False) or AbilityPx (if reverse=True)
        action: The M2M action (pre_add, post_add, etc.)
        pk_set: Set of related object IDs
        reverse: True if signal was triggered from AbilityPx side
        **kwargs: Additional keyword arguments

    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    if reverse:
        # Signal came from AbilityPx - instance is an AbilityPx
        # pk_set contains rule IDs, so refresh each rule
        if pk_set:
            rule_ids = list(pk_set)
        elif action == "post_clear":
            rule_ids = list(RulePx.objects.filter(abilities=instance).values_list("id", flat=True))
        else:
            rule_ids = []
    else:
        # Signal came from RulePx.abilities - instance is a RulePx
        rule_ids = [instance.id]

    if not rule_ids:
        return

    _mark_px_dirty("rules", rule_ids, instance.event_id)
    refresh_rule_rels_dirty_background(rule_ids)
