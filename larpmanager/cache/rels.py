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

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.cache.feature import get_event_features
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import Event
from larpmanager.models.utils import strip_tags
from larpmanager.models.writing import Character, Faction, Plot, Prologue, Relationship, SpeedLarp

logger = logging.getLogger(__name__)


def get_event_rels_key(event_id: int) -> str:
    """Generate cache key for event relationships.

    Args:
        event_id: The ID of the event

    Returns:
        str: Cache key in format 'event__rels__{event_id}'
    """
    return f"event__rels__{event_id}"


def clear_event_relationships_cache(event_id: int) -> None:
    """Reset event relationships cache for given event ID.

    Args:
        event_id: The ID of the event whose cache should be cleared
    """
    cache_key = get_event_rels_key(event_id)
    cache.delete(cache_key)
    logger.debug(f"Reset cache for event {event_id}")

    # invalidate also for children events
    for children_id in Event.objects.filter(parent_id=event_id).values_list("pk", flat=True):
        cache_key = get_event_rels_key(children_id)
        cache.delete(cache_key)


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
        cache.set(cache_key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug(f"Updated {section_name} {section_id} relationships in cache")

    except Exception as e:
        logger.error(f"Error updating {section_name} {section_id} relationships: {e}", exc_info=True)
        clear_event_relationships_cache(event_id)


def remove_item_from_cache_section(event_id: int, section_name: str, section_id: int) -> None:
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
            cache.set(cache_key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
            logger.debug(f"Removed {section_name} {section_id} from cache")
    except Exception as e:
        logger.error(f"Error removing {section_name} {section_id} from cache: {e}", exc_info=True)
        clear_event_relationships_cache(event_id)


def refresh_character_related_caches(char: Character) -> None:
    """Update all caches that are related to a character.

    Args:
        char: The Character instance
    """
    # Update plots that this character is part of
    for plot_rel in char.get_plot_characters():
        refresh_event_plot_relationships(plot_rel.plot)

    # Update factions that this character is part of
    for faction in char.factions_list.all():
        refresh_event_faction_relationships(faction)

    # Update speedlarps that this character is part of
    for speedlarp in char.speedlarps_list.all():
        refresh_event_speedlarp_relationships(speedlarp)

    # Update prologues that this character is part of
    for prologue in char.prologues_list.all():
        refresh_event_prologue_relationships(prologue)


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
                    refresh_character_relationships(char)
                except ObjectDoesNotExist:
                    logger.warning(f"Character {char_id} not found during relationship update")
        elif action == "post_clear":
            # For post_clear, we need to update all characters that were related
            if hasattr(instance, "characters"):
                for char in instance.characters.all():
                    refresh_character_relationships(char)
            elif hasattr(instance, "get_plot_characters"):
                for char_rel in instance.get_plot_characters():
                    refresh_character_relationships(char_rel.character)


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

        # Configuration for each relationship type
        rel_configs = [
            ("character", "characters", Character, get_event_char_rels, True),
            ("faction", "factions", Faction, get_event_faction_rels, False),
            ("plot", "plots", Plot, get_event_plot_rels, False),
            ("speedlarp", "speedlarps", SpeedLarp, get_event_speedlarp_rels, False),
            ("prologue", "prologues", Prologue, get_event_prologue_rels, False),
            ("quest", "quests", Quest, get_event_quest_rels, False),
            ("questtype", "questtypes", QuestType, get_event_questtype_rels, False),
        ]

        for feature_name, cache_key_plural, model_class, get_rels_func, pass_features in rel_configs:
            if feature_name not in features:
                continue

            res[cache_key_plural] = {}
            elements = event.get_elements(model_class)
            for element in elements:
                if pass_features:
                    res[cache_key_plural][element.id] = get_rels_func(element, features)
                else:
                    res[cache_key_plural][element.id] = get_rels_func(element)
            logger.debug(f"Initialized {len(elements)} {feature_name} relationships for event {event.id}")

        cache_key = get_event_rels_key(event.id)
        cache.set(cache_key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug(f"Cached relationships for event {event.id}")

    except Exception as e:
        logger.error(f"Error initializing relationships for event {event.id}: {e}", exc_info=True)
        res = {}

    return res


def refresh_character_relationships(char: Character) -> None:
    refresh_event_character_relationships(char, char.event)
    # update char also for children events (if parent of campaign)
    for children in Event.objects.filter(parent_id=char.event_id):
        refresh_event_character_relationships(char, children)


def refresh_event_character_relationships(char: Character, event: Event) -> None:
    """Update character relationships in cache.

    Updates the cached relationship data for a specific character.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        char: The Character instance to update relationships for
        event: The event for which we are building the cache
    """
    try:
        cache_key = get_event_rels_key(event.id)
        res = cache.get(cache_key)

        if res is None:
            logger.debug(f"Cache miss during character update for event {event}, reinitializing")
            init_event_rels_all(event)
            return

        if "characters" not in res:
            res["characters"] = {}

        features = get_event_features(event.id)
        res["characters"][char.id] = get_event_char_rels(char, features, event)
        cache.set(cache_key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug(f"Updated character {char.id} relationships in cache")

    except Exception as e:
        logger.error(f"Error updating character {char.id} relationships: {e}", exc_info=True)
        clear_event_relationships_cache(event.id)


def get_event_char_rels(char: Character, features: dict, event: Event = None) -> dict[str, Any]:
    """Get character relationships for a specific character.

    Builds relationship data for a character based on enabled event features.
    Includes plot relationships and faction relationships if those features are enabled.

    Args:
        char: The Character instance to get relationships for
        features: Set of enabled features
        event: Event for which we are rebuilding the cache

    Returns:
        Dict[str, Any]: Dictionary containing relationship data:
            {
                'plot_rels': {'list': [(plot_id, plot_name), ...], 'count': int},
                'faction_rels': {'list': [(faction_id, faction_name), ...], 'count': int}
            }
    """
    relations = {}

    try:
        if "plot" in features:
            rel_plots = char.get_plot_characters()
            plot_list = [(rel.plot.id, rel.plot.name) for rel in rel_plots]
            relations["plot_rels"] = build_relationship_dict(plot_list)
            unimportant_count = 0
            if char.event.get_config("writing_unimportant", False):
                unimportant_count = sum(
                    1 for rel in rel_plots if strip_tags(rel.text).lstrip().startswith("$unimportant")
                )
            relations["plot_rels"]["important"] = relations["plot_rels"]["count"] - unimportant_count

        if "faction" in features:
            if char.event.get_config("campaign_faction_indep", False):
                fac_event = event
            else:
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
            unimportant_count = 0
            if char.event.get_config("writing_unimportant", False):
                unimportant_count = sum(
                    1 for rel in relationships if strip_tags(rel.text).lstrip().startswith("$unimportant")
                )
            relations["relationships_rels"]["important"] = relations["relationships_rels"]["count"] - unimportant_count

        if "speedlarp" in features:
            speedlarps = char.speedlarps_list.all()
            speedlarp_list = [(speedlarp.id, speedlarp.name) for speedlarp in speedlarps]
            relations["speedlarp_rels"] = build_relationship_dict(speedlarp_list)

        if "prologue" in features:
            prologues = char.prologues_list.all()
            prologue_list = [(prologue.id, prologue.name) for prologue in prologues]
            relations["prologue_rels"] = build_relationship_dict(prologue_list)

    except Exception as e:
        logger.error(f"Error getting relationships for character {char.id}: {e}", exc_info=True)
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
        logger.error(f"Error getting relationships for faction {faction.id}: {e}", exc_info=True)
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
        logger.error(f"Error getting relationships for plot {plot.id}: {e}", exc_info=True)
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
        logger.error(f"Error getting relationships for speedlarp {speedlarp.id}: {e}", exc_info=True)
        relations = {}

    return relations


def get_event_prologue_rels(prologue: Prologue) -> dict[str, Any]:
    """Get prologue relationships for a specific prologue.

    Args:
        prologue: The Prologue instance to get relationships for

    Returns:
        Dict[str, Any]: Dictionary containing relationship data:
            {
                'character_rels': {'list': [(char_id, char_name), ...], 'count': int}
            }
    """
    relations = {}

    try:
        characters = prologue.characters.all()
        char_list = [(char.id, char.name) for char in characters]
        relations["character_rels"] = build_relationship_dict(char_list)

    except Exception as e:
        logger.error(f"Error getting relationships for prologue {prologue.id}: {e}", exc_info=True)
        relations = {}

    return relations


def get_event_quest_rels(quest: Quest) -> dict[str, Any]:
    """Get quest relationships for a specific quest.

    Args:
        quest: The Quest instance to get relationships for

    Returns:
        Dict[str, Any]: Dictionary containing relationship data:
            {
                'trait_rels': {'list': [(trait_id, trait_name), ...], 'count': int}
            }
    """
    relations = {}

    try:
        traits = Trait.objects.filter(quest=quest, deleted=None)
        trait_list = [(trait.id, trait.name) for trait in traits]
        relations["trait_rels"] = build_relationship_dict(trait_list)

    except Exception as e:
        logger.error(f"Error getting relationships for quest {quest.id}: {e}")
        relations = {}

    return relations


def get_event_questtype_rels(questtype: QuestType) -> dict[str, Any]:
    """Get questtype relationships for a specific questtype.

    Args:
        questtype: The QuestType instance to get relationships for

    Returns:
        Dict[str, Any]: Dictionary containing relationship data:
            {
                'quest_rels': {'list': [(quest_id, quest_name), ...], 'count': int}
            }
    """
    relations = {}

    try:
        quests = questtype.quests.all()
        quest_list = [(quest.id, quest.name) for quest in quests]
        relations["quest_rels"] = build_relationship_dict(quest_list)

    except Exception as e:
        logger.error(f"Error getting relationships for questtype {questtype.id}: {e}")
        relations = {}

    return relations


def refresh_event_faction_relationships(faction: Faction) -> None:
    """Update faction relationships in cache.

    Updates the cached relationship data for a specific faction.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        faction: The Faction instance to update relationships for
    """
    faction_data = get_event_faction_rels(faction)
    update_cache_section(faction.event_id, "factions", faction.id, faction_data)


def refresh_event_plot_relationships(plot: Plot) -> None:
    """Update plot relationships in cache.

    Updates the cached relationship data for a specific plot.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        plot: The Plot instance to update relationships for
    """
    plot_data = get_event_plot_rels(plot)
    update_cache_section(plot.event_id, "plots", plot.id, plot_data)


def refresh_event_speedlarp_relationships(speedlarp: SpeedLarp) -> None:
    """Update speedlarp relationships in cache.

    Updates the cached relationship data for a specific speedlarp.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        speedlarp: The SpeedLarp instance to update relationships for
    """
    speedlarp_data = get_event_speedlarp_rels(speedlarp)
    update_cache_section(speedlarp.event_id, "speedlarps", speedlarp.id, speedlarp_data)


def refresh_event_prologue_relationships(prologue: Prologue) -> None:
    """Update prologue relationships in cache.

    Updates the cached relationship data for a specific prologue.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        prologue: The Prologue instance to update relationships for
    """
    prologue_data = get_event_prologue_rels(prologue)
    update_cache_section(prologue.event_id, "prologues", prologue.id, prologue_data)


def refresh_event_quest_relationships(quest: Quest) -> None:
    """Update quest relationships in cache.

    Updates the cached relationship data for a specific quest.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        quest: The Quest instance to update relationships for
    """
    quest_data = get_event_quest_rels(quest)
    update_cache_section(quest.event_id, "quests", quest.id, quest_data)


def refresh_event_questtype_relationships(questtype: QuestType) -> None:
    """Update questtype relationships in cache.

    Updates the cached relationship data for a specific questtype.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        questtype: The QuestType instance to update relationships for
    """
    questtype_data = get_event_questtype_rels(questtype)
    update_cache_section(questtype.event_id, "questtypes", questtype.id, questtype_data)


def on_faction_characters_m2m_changed(sender, instance, action, pk_set, **kwargs):
    """Handle faction-character relationship changes.

    Updates both faction cache and character caches when relationships change.

    Args:
        sender: The through model class
        instance: The Faction instance
        action: The type of change ('post_add', 'post_remove', 'post_clear', etc.)
        pk_set: Set of primary keys of the Character objects
        **kwargs: Additional keyword arguments from the signal
    """
    update_m2m_related_characters(instance, pk_set, action, refresh_event_faction_relationships)


def on_plot_characters_m2m_changed(sender, instance, action, pk_set, **kwargs):
    """Handle plot-character relationship changes.

    Updates both plot cache and character caches when relationships change.

    Args:
        sender: The through model class (PlotCharacterRel)
        instance: The Plot instance
        action: The type of change ('post_add', 'post_remove', 'post_clear', etc.)
        pk_set: Set of primary keys of the Character objects
        **kwargs: Additional keyword arguments from the signal
    """
    update_m2m_related_characters(instance, pk_set, action, refresh_event_plot_relationships)


def on_speedlarp_characters_m2m_changed(sender, instance, action, pk_set, **kwargs):
    """Handle speedlarp-character relationship changes.

    Updates both speedlarp cache and character caches when relationships change.

    Args:
        sender: The through model class
        instance: The SpeedLarp instance
        action: The type of change ('post_add', 'post_remove', 'post_clear', etc.)
        pk_set: Set of primary keys of the Character objects
        **kwargs: Additional keyword arguments from the signal
    """
    update_m2m_related_characters(instance, pk_set, action, refresh_event_speedlarp_relationships)


def on_prologue_characters_m2m_changed(sender, instance, action, pk_set, **kwargs):
    """Handle prologue-character relationship changes.

    Updates both prologue cache and character caches when relationships change.

    Args:
        sender: The through model class
        instance: The Prologue instance
        action: The type of change ('post_add', 'post_remove', 'post_clear', etc.)
        pk_set: Set of primary keys of the Character objects
        **kwargs: Additional keyword arguments from the signal
    """
    update_m2m_related_characters(instance, pk_set, action, refresh_event_prologue_relationships)
