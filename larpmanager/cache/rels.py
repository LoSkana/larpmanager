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

import logging
from typing import Any

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from larpmanager.cache.feature import get_event_features
from larpmanager.models.event import Event
from larpmanager.models.writing import Character, Faction, Plot, Relationship, SpeedLarp

logger = logging.getLogger(__name__)


def get_event_rels_key(event_id: int) -> str:
    """Generate cache key for event relationships.

    Args:
        event_id: The ID of the event

    Returns:
        str: Cache key in format 'event__rels__{event_id}'
    """
    return f"event__rels__{event_id}"


def reset_event_rels_cache(event_id: int) -> None:
    """Reset event relationships cache for given event ID.

    Args:
        event_id: The ID of the event whose cache should be cleared
    """
    cache_key = get_event_rels_key(event_id)
    cache.delete(cache_key)
    logger.debug(f"Reset cache for event {event_id}")


def build_relationship_dict(items: list) -> dict[str, Any]:
    """Build relationship dictionary with list and count.

    Args:
        items: List of (id, name) tuples

    Returns:
        Dict with "list" and "count" keys
    """
    return {"list": items, "count": len(items)}


def update_cache_section(event_id: int, section_name: str, section_id: int, data: dict[str, Any]) -> None:
    """Update a specific section in the event cache.

    Args:
        event_id: The event ID
        section_name: Name of the cache section (e.g., 'characters', 'factions')
        section_id: ID of the item within the section
        data: Data to store for this item
    """
    try:
        cache_key = get_event_rels_key(event_id)
        res = cache.get(cache_key)

        if res is None:
            logger.debug(f"Cache miss during {section_name} update for event {event_id}, reinitializing")
            # We need to get the event to reinitialize
            event = Event.objects.get(id=event_id)
            init_event_rels_all(event)
            return

        if section_name not in res:
            res[section_name] = {}

        res[section_name][section_id] = data
        cache.set(cache_key, res)
        logger.debug(f"Updated {section_name} {section_id} relationships in cache")

    except Exception as e:
        logger.error(f"Error updating {section_name} {section_id} relationships: {e}")
        reset_event_rels_cache(event_id)


def remove_from_cache_section(event_id: int, section_name: str, section_id: int) -> None:
    """Remove an item from a specific section in the event cache.

    Args:
        event_id: The event ID
        section_name: Name of the cache section (e.g., 'factions', 'plots')
        section_id: ID of the item to remove
    """
    try:
        cache_key = get_event_rels_key(event_id)
        res = cache.get(cache_key)
        if res and section_name in res and section_id in res[section_name]:
            del res[section_name][section_id]
            cache.set(cache_key, res)
            logger.debug(f"Removed {section_name} {section_id} from cache")
    except Exception as e:
        logger.error(f"Error removing {section_name} {section_id} from cache: {e}")
        reset_event_rels_cache(event_id)


def update_character_related_caches(char: Character) -> None:
    """Update all caches that are related to a character.

    Args:
        char: The Character instance
    """
    # Update plots that this character is part of
    for plot_rel in char.get_plot_characters():
        update_event_plot_rels(plot_rel.plot)

    # Update factions that this character is part of
    for faction in char.factions_list.all():
        update_event_faction_rels(faction)

    # Update speedlarps that this character is part of
    for speedlarp in char.speedlarps_list.all():
        update_event_speedlarp_rels(speedlarp)


def update_m2m_related_characters(instance, pk_set, action: str, update_func) -> None:
    """Update character caches for M2M relationship changes.

    Args:
        instance: The instance that changed (Plot, Faction, SpeedLarp)
        pk_set: Set of character primary keys affected
        action: The M2M action type
        update_func: Function to update the instance cache
    """
    if action in ("post_add", "post_remove", "post_clear"):
        # Update the instance cache
        update_func(instance)

        # Update cache for all affected characters
        if pk_set:
            for char_id in pk_set:
                try:
                    char = Character.objects.get(id=char_id)
                    update_event_char_rels(char)
                except ObjectDoesNotExist:
                    logger.warning(f"Character {char_id} not found during relationship update")
        elif action == "post_clear":
            # For post_clear, we need to update all characters that were related
            if hasattr(instance, "characters"):
                for char in instance.characters.all():
                    update_event_char_rels(char)
            elif hasattr(instance, "get_plot_characters"):
                for char_rel in instance.get_plot_characters():
                    update_event_char_rels(char_rel.character)


def get_event_rels_cache(event: Event) -> dict[str, Any]:
    """Get event relationships from cache, initializing if not present.

    Args:
        event: The Event instance to get relationships for

    Returns:
        Dict[str, Any]: Dictionary containing cached relationship data
    """
    cache_key = get_event_rels_key(event.id)
    res = cache.get(cache_key)
    if res is None:
        logger.debug(f"Cache miss for event {event.id}, initializing")
        res = init_event_rels_all(event)
    return res


def init_event_rels_all(event: Event) -> dict[str, Any]:
    """Initialize all relationships for an event and cache the result.

    Builds a complete relationship cache for all characters in the event,
    including plot and faction relationships based on enabled features.

    Args:
        event: The Event instance to initialize relationships for

    Returns:
        Dict[str, Any]: Dictionary with relationship data structure:
            {
                'character': {
                    char_id: {
                        'plot_rels': [(plot_id, plot_name), ...],
                        'faction_rels': [(faction_id, faction_name), ...]
                    }
                }
            }
    """
    res = {}

    try:
        features = get_event_features(event.id)

        if "character" in features:
            res["characters"] = {}
            characters = event.get_elements(Character)
            for char in characters:
                res["characters"][char.id] = get_event_char_rels(char, features)
            logger.debug(f"Initialized {len(characters)} character relationships for event {event.id}")

        if "faction" in features:
            res["factions"] = {}
            factions = event.get_elements(Faction)
            for faction in factions:
                res["factions"][faction.id] = get_event_faction_rels(faction)
            logger.debug(f"Initialized {len(factions)} faction relationships for event {event.id}")

        if "plot" in features:
            res["plots"] = {}
            plots = event.get_elements(Plot)
            for plot in plots:
                res["plots"][plot.id] = get_event_plot_rels(plot)
            logger.debug(f"Initialized {len(plots)} plot relationships for event {event.id}")

        if "speedlarp" in features:
            res["speedlarps"] = {}
            speedlarps = event.get_elements(SpeedLarp)
            for speedlarp in speedlarps:
                res["speedlarps"][speedlarp.id] = get_event_speedlarp_rels(speedlarp)
            logger.debug(f"Initialized {len(speedlarps)} speedlarp relationships for event {event.id}")

        cache_key = get_event_rels_key(event.id)
        cache.set(cache_key, res)
        logger.debug(f"Cached relationships for event {event.id}")

    except Exception as e:
        logger.error(f"Error initializing relationships for event {event.id}: {e}")
        res = {}

    return res


def update_event_char_rels(char: Character) -> None:
    """Update character relationships in cache.

    Updates the cached relationship data for a specific character.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        char: The Character instance to update relationships for
    """
    try:
        cache_key = get_event_rels_key(char.event_id)
        res = cache.get(cache_key)

        if res is None:
            logger.debug(f"Cache miss during character update for event {char.event_id}, reinitializing")
            init_event_rels_all(char.event)
            return

        if "characters" not in res:
            res["characters"] = {}

        res["characters"][char.id] = get_event_char_rels(char)
        cache.set(cache_key, res)
        logger.debug(f"Updated character {char.id} relationships in cache")

    except Exception as e:
        logger.error(f"Error updating character {char.id} relationships: {e}")
        reset_event_rels_cache(char.event_id)


def get_event_char_rels(char: Character, features: dict) -> dict[str, Any]:
    """Get character relationships for a specific character.

    Builds relationship data for a character based on enabled event features.
    Includes plot relationships and faction relationships if those features are enabled.

    Args:
        char: The Character instance to get relationships for
        features: Optional set of enabled features. If None, will be fetched from cache

    Returns:
        Dict[str, Any]: Dictionary containing relationship data:
            {
                'plot_rels': {'list': [(plot_id, plot_name), ...], 'count': int},
                'faction_rels': {'list': [(faction_id, faction_name), ...], 'count': int}
            }
    """
    if features is None:
        features = get_event_features(char.event_id)

    relations = {}

    try:
        if "plot" in features:
            rel_plots = char.get_plot_characters()
            plot_list = [(rel.plot.id, rel.plot.name) for rel in rel_plots]
            relations["plot_rels"] = build_relationship_dict(plot_list)

        if "faction" in features:
            fac_event = char.event.get_class_parent("faction")
            if fac_event:
                factions = char.factions_list.filter(event=fac_event)
                faction_list = [(faction.id, faction.name) for faction in factions]
            else:
                faction_list = []
            relations["faction_rels"] = build_relationship_dict(faction_list)

        if "relationships" in features:
            relationships = Relationship.objects.filter(deleted=None, source=char)
            rel_list = [(rel.target.id, rel.target.name) for rel in relationships]
            relations["relationships_rels"] = build_relationship_dict(rel_list)

        if "speedlarp" in features:
            speedlarps = char.speedlarps_list.all()
            speedlarp_list = [(speedlarp.id, speedlarp.name) for speedlarp in speedlarps]
            relations["speedlarp_rels"] = build_relationship_dict(speedlarp_list)

    except Exception as e:
        logger.error(f"Error getting relationships for character {char.id}: {e}")
        relations = {}

    return relations


def get_event_faction_rels(faction: Faction) -> dict[str, Any]:
    """Get faction relationships for a specific faction.

    Args:
        faction: The Faction instance to get relationships for

    Returns:
        Dict[str, Any]: Dictionary containing relationship data:
            {
                'character_rels': {'list': [(char_id, char_name), ...], 'count': int}
            }
    """
    relations = {}

    try:
        characters = faction.characters.all()
        char_list = [(char.id, char.name) for char in characters]
        relations["character_rels"] = build_relationship_dict(char_list)

    except Exception as e:
        logger.error(f"Error getting relationships for faction {faction.id}: {e}")
        relations = {}

    return relations


def get_event_plot_rels(plot: Plot) -> dict[str, Any]:
    """Get plot relationships for a specific plot.

    Args:
        plot: The Plot instance to get relationships for

    Returns:
        Dict[str, Any]: Dictionary containing relationship data:
            {
                'character_rels': {'list': [(char_id, char_name), ...], 'count': int}
            }
    """
    relations = {}

    try:
        char_rels = plot.get_plot_characters()
        char_list = [(rel.character.id, rel.character.name) for rel in char_rels]
        relations["character_rels"] = build_relationship_dict(char_list)

    except Exception as e:
        logger.error(f"Error getting relationships for plot {plot.id}: {e}")
        relations = {}

    return relations


def get_event_speedlarp_rels(speedlarp: SpeedLarp) -> dict[str, Any]:
    """Get speedlarp relationships for a specific speedlarp.

    Args:
        speedlarp: The SpeedLarp instance to get relationships for

    Returns:
        Dict[str, Any]: Dictionary containing relationship data:
            {
                'character_rels': {'list': [(char_id, char_name), ...], 'count': int}
            }
    """
    relations = {}

    try:
        characters = speedlarp.characters.all()
        char_list = [(char.id, char.name) for char in characters]
        relations["character_rels"] = build_relationship_dict(char_list)

    except Exception as e:
        logger.error(f"Error getting relationships for speedlarp {speedlarp.id}: {e}")
        relations = {}

    return relations


def update_event_faction_rels(faction: Faction) -> None:
    """Update faction relationships in cache.

    Updates the cached relationship data for a specific faction.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        faction: The Faction instance to update relationships for
    """
    faction_data = get_event_faction_rels(faction)
    update_cache_section(faction.event_id, "factions", faction.id, faction_data)


def update_event_plot_rels(plot: Plot) -> None:
    """Update plot relationships in cache.

    Updates the cached relationship data for a specific plot.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        plot: The Plot instance to update relationships for
    """
    plot_data = get_event_plot_rels(plot)
    update_cache_section(plot.event_id, "plots", plot.id, plot_data)


def update_event_speedlarp_rels(speedlarp: SpeedLarp) -> None:
    """Update speedlarp relationships in cache.

    Updates the cached relationship data for a specific speedlarp.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        speedlarp: The SpeedLarp instance to update relationships for
    """
    speedlarp_data = get_event_speedlarp_rels(speedlarp)
    update_cache_section(speedlarp.event_id, "speedlarps", speedlarp.id, speedlarp_data)


@receiver(post_save, sender=Character)
def post_save_character_reset_rels(sender, instance, **kwargs):
    """Handle character save to update cache.

    Args:
        sender: The model class that sent the signal
        instance: The Character instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    update_event_char_rels(instance)
    for rel in Relationship.objects.filter(target=instance):
        update_event_char_rels(rel.source)

    # Update all related caches
    update_character_related_caches(instance)


@receiver(post_delete, sender=Character)
def post_delete_character_reset_rels(sender, instance, **kwargs):
    """Handle character deletion to reset cache.

    Resets the entire event cache when a character is deleted to ensure
    all references to the deleted character are removed.

    Args:
        sender: The model class that sent the signal
        instance: The Character instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update all related caches
    update_character_related_caches(instance)

    reset_event_rels_cache(instance.event_id)
    for rel in Relationship.objects.filter(target=instance):
        update_event_char_rels(rel.source)


@receiver(post_save, sender=Faction)
def post_save_faction_reset_rels(sender, instance, **kwargs):
    """Handle faction save to update related caches.

    Updates both faction cache and related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The Faction instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update faction cache
    update_event_faction_rels(instance)

    # Update cache for all characters in this faction
    for char in instance.characters.all():
        update_event_char_rels(char)


@receiver(post_delete, sender=Faction)
def post_delete_faction_reset_rels(sender, instance, **kwargs):
    """Handle faction deletion to update related caches.

    Removes faction from cache and updates related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The Faction instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update cache for all characters that were in this faction
    for char in instance.characters.all():
        update_event_char_rels(char)

    # Remove faction from cache
    remove_from_cache_section(instance.event_id, "factions", instance.id)


def handle_faction_characters_changed(sender, instance, action, pk_set, **kwargs):
    """Handle faction-character relationship changes.

    Updates both faction cache and character caches when relationships change.

    Args:
        sender: The through model class
        instance: The Faction instance
        action: The type of change ('post_add', 'post_remove', 'post_clear', etc.)
        pk_set: Set of primary keys of the Character objects
        **kwargs: Additional keyword arguments from the signal
    """
    update_m2m_related_characters(instance, pk_set, action, update_event_faction_rels)


def handle_plot_characters_changed(sender, instance, action, pk_set, **kwargs):
    """Handle plot-character relationship changes.

    Updates both plot cache and character caches when relationships change.

    Args:
        sender: The through model class (PlotCharacterRel)
        instance: The Plot instance
        action: The type of change ('post_add', 'post_remove', 'post_clear', etc.)
        pk_set: Set of primary keys of the Character objects
        **kwargs: Additional keyword arguments from the signal
    """
    update_m2m_related_characters(instance, pk_set, action, update_event_plot_rels)


def handle_speedlarp_characters_changed(sender, instance, action, pk_set, **kwargs):
    """Handle speedlarp-character relationship changes.

    Updates both speedlarp cache and character caches when relationships change.

    Args:
        sender: The through model class
        instance: The SpeedLarp instance
        action: The type of change ('post_add', 'post_remove', 'post_clear', etc.)
        pk_set: Set of primary keys of the Character objects
        **kwargs: Additional keyword arguments from the signal
    """
    update_m2m_related_characters(instance, pk_set, action, update_event_speedlarp_rels)


@receiver(post_save, sender=Plot)
def post_save_plot_reset_rels(sender, instance, **kwargs):
    """Handle plot save to update related caches.

    Updates both plot cache and related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The Plot instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update plot cache
    update_event_plot_rels(instance)

    # Update cache for all characters in this plot
    for char_rel in instance.get_plot_characters():
        update_event_char_rels(char_rel.character)


@receiver(post_delete, sender=Plot)
def post_delete_plot_reset_rels(sender, instance, **kwargs):
    """Handle plot deletion to update related caches.

    Removes plot from cache and updates related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The Plot instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update cache for all characters that were in this plot
    for char_rel in instance.get_plot_characters():
        update_event_char_rels(char_rel.character)

    # Remove plot from cache
    remove_from_cache_section(instance.event_id, "plots", instance.id)


@receiver(post_save, sender=SpeedLarp)
def post_save_speedlarp_reset_rels(sender, instance, **kwargs):
    """Handle speedlarp save to update related caches.

    Updates both speedlarp cache and related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The SpeedLarp instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update speedlarp cache
    update_event_speedlarp_rels(instance)

    # Update cache for all characters in this speedlarp
    for char in instance.characters.all():
        update_event_char_rels(char)


@receiver(post_delete, sender=SpeedLarp)
def post_delete_speedlarp_reset_rels(sender, instance, **kwargs):
    """Handle speedlarp deletion to update related caches.

    Removes speedlarp from cache and updates related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The SpeedLarp instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update cache for all characters that were in this speedlarp
    for char in instance.characters.all():
        update_event_char_rels(char)

    # Remove speedlarp from cache
    remove_from_cache_section(instance.event_id, "speedlarps", instance.id)


@receiver(post_save, sender=Relationship)
def post_save_relationship_reset_rels(sender, instance, **kwargs):
    """Handle relationship save to update character caches.

    Updates cache for both source and target characters when relationship changes.

    Args:
        sender: The model class that sent the signal
        instance: The Relationship instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update cache for source character
    update_event_char_rels(instance.source)


@receiver(post_delete, sender=Relationship)
def post_delete_relationship_reset_rels(sender, instance, **kwargs):
    """Handle relationship deletion to update character caches.

    Updates cache for both source and target characters when relationship is deleted.

    Args:
        sender: The model class that sent the signal
        instance: The Relationship instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update cache for source character
    update_event_char_rels(instance.source)


# Connect M2M signals manually for better control
m2m_changed.connect(handle_faction_characters_changed, sender=Faction.characters.through)
m2m_changed.connect(handle_plot_characters_changed, sender=Plot.characters.through)
m2m_changed.connect(handle_speedlarp_characters_changed, sender=SpeedLarp.characters.through)
