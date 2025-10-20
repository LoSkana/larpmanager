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

from larpmanager.cache.character import reset_event_cache_all
from larpmanager.cache.config import get_event_config
from larpmanager.cache.feature import get_event_features
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import Event, Run
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

    This function clears the cache for the specified event and all its child events
    to ensure data consistency when event relationships change.

    Args:
        event_id: The ID of the event whose cache should be cleared.

    Returns:
        None
    """
    # Clear cache for the main event
    cache_key = get_event_rels_key(event_id)
    cache.delete(cache_key)
    logger.debug(f"Reset cache for event {event_id}")

    # Invalidate cache for all child events to maintain consistency
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

    This function refreshes caches for all entities that have relationships
    with the given character, including plots, factions, speedlarps, and prologues.

    Args:
        char (Character): The Character instance whose related caches need to be refreshed.

    Returns:
        None
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

        # Reset event char for any run of event and child events
        event = instance.event
        events_id = list(Event.objects.filter(parent=event).values_list("pk", flat=True))
        events_id.append(event.id)
        for run in Run.objects.filter(event_id__in=events_id):
            reset_event_cache_all(run)

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

    Retrieves cached relationship data for the specified event. If no cached
    data exists, initializes the cache with fresh relationship data.

    Args:
        event (Event): The Event instance to get relationships for.

    Returns:
        dict[str, Any]: Dictionary containing cached relationship data including
            event associations, permissions, and related objects.

    Note:
        Cache miss will trigger full relationship initialization via
        init_event_rels_all().
    """
    # Generate cache key for this specific event
    cache_key = get_event_rels_key(event.id)

    # Attempt to retrieve cached relationships
    res = cache.get(cache_key)

    # Initialize cache if no data found
    if res is None:
        logger.debug(f"Cache miss for event {event.id}, initializing")
        res = init_event_rels_all(event)

    return res


def init_event_rels_all(event: Event) -> dict[str, dict[int, dict[str, Any]]]:
    """Initialize all relationships for an event and cache the result.

    Builds a complete relationship cache for all characters in the event,
    including plot and faction relationships based on enabled features.

    Args:
        event: The Event instance to initialize relationships for

    Returns:
        Dictionary with relationship data structure organized by element type:
        {
            'characters': {
                char_id: {
                    'plot_rels': [(plot_id, plot_name), ...],
                    'faction_rels': [(faction_id, faction_name), ...]
                }
            },
            'factions': {
                faction_id: relationship_data
            },
            ...
        }

    Raises:
        Exception: Any error during relationship initialization is logged
                  and an empty dict is returned
    """
    res: dict[str, dict[int, dict[str, Any]]] = {}

    try:
        # Get enabled features for this event to determine which relationships to build
        features = get_event_features(event.id)

        # Configuration mapping for each relationship type with their corresponding
        # feature name, cache key, model class, relationship function, and feature flag
        rel_configs = [
            ("character", "characters", Character, get_event_char_rels, True),
            ("faction", "factions", Faction, get_event_faction_rels, False),
            ("plot", "plots", Plot, get_event_plot_rels, False),
            ("speedlarp", "speedlarps", SpeedLarp, get_event_speedlarp_rels, False),
            ("prologue", "prologues", Prologue, get_event_prologue_rels, False),
            ("quest", "quests", Quest, get_event_quest_rels, False),
            ("questtype", "questtypes", QuestType, get_event_questtype_rels, False),
        ]

        # Process each relationship type if the corresponding feature is enabled
        for feature_name, cache_key_plural, model_class, get_rels_func, pass_features in rel_configs:
            if feature_name not in features:
                continue

            # Initialize the cache section for this relationship type
            res[cache_key_plural] = {}

            # Get all elements of this type associated with the event
            elements = event.get_elements(model_class)

            # Build relationships for each element, passing features if required
            for element in elements:
                if pass_features:
                    res[cache_key_plural][element.id] = get_rels_func(element, features, event)
                else:
                    res[cache_key_plural][element.id] = get_rels_func(element)

            logger.debug(f"Initialized {len(elements)} {feature_name} relationships for event {event.id}")

        # Cache the complete relationship data structure
        cache_key = get_event_rels_key(event.id)
        cache.set(cache_key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug(f"Cached relationships for event {event.id}")

    except Exception as e:
        # Log the error with full traceback and return empty result
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

    Updates the cached relationship data for a specific character within an event.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        char: The Character instance to update relationships for.
        event: The Event instance for which we are building the cache.

    Raises:
        Exception: If there's an error updating relationships, the cache is cleared.
    """
    try:
        # Get the cache key for this event's relationships
        cache_key = get_event_rels_key(event.id)
        res = cache.get(cache_key)

        # If cache doesn't exist, initialize it for the entire event
        if res is None:
            logger.debug(f"Cache miss during character update for event {event}, reinitializing")
            init_event_rels_all(event)
            return

        # Ensure characters dictionary exists in cache structure
        if "characters" not in res:
            res["characters"] = {}

        # Get event features and update character relationships
        features = get_event_features(event.id)
        res["characters"][char.id] = get_event_char_rels(char, features, event)

        # Save updated cache with 1-day timeout
        cache.set(cache_key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug(f"Updated character {char.id} relationships in cache")

    except Exception as e:
        # Log error and clear cache to prevent inconsistent state
        logger.error(f"Error updating character {char.id} relationships: {e}", exc_info=True)
        clear_event_relationships_cache(event.id)


def get_event_char_rels(char: Character, features: dict[str, Any], event: Event) -> dict[str, Any]:
    """Get character relationships for a specific character.

    Builds relationship data for a character based on enabled event features.
    Includes plot relationships, faction relationships, character relationships,
    speedlarp relationships, and prologue relationships if those features are enabled.

    Args:
        char: The Character instance to get relationships for.
        features: Dictionary of enabled features for the event.
        event: Optional Event instance for which we are rebuilding the cache.
               Used for faction independence configuration.

    Returns:
        Dictionary containing relationship data with keys:
            - 'plot_rels': Plot relationships with list and counts
            - 'faction_rels': Faction relationships with list and counts
            - 'relationships_rels': Character relationships with list and counts
            - 'speedlarp_rels': Speedlarp relationships with list and counts
            - 'prologue_rels': Prologue relationships with list and counts

        Each relationship type contains:
            - 'list': List of tuples (id, name)
            - 'count': Total count of relationships
            - 'important': Count excluding unimportant items (where applicable)

    Raises:
        Exception: Logs error and returns empty dict if relationship building fails.
    """
    relations: dict[str, Any] = {}

    try:
        # Handle plot relationships if plot feature is enabled
        if "plot" in features:
            rel_plots = char.get_plot_characters()
            plot_list = [(rel.plot_id, rel.plot.name) for rel in rel_plots]
            relations["plot_rels"] = build_relationship_dict(plot_list)

            # Calculate important plot count (excluding $unimportant entries)
            unimportant_count = 0
            if get_event_config(char.event_id, "writing_unimportant", False):
                unimportant_count = sum(
                    1 for rel in rel_plots if strip_tags(rel.text).lstrip().startswith("$unimportant")
                )
            relations["plot_rels"]["important"] = relations["plot_rels"]["count"] - unimportant_count

        # Handle faction relationships if faction feature is enabled
        if "faction" in features:
            cache_event_id = event.id if event else char.event_id
            if get_event_config(cache_event_id, "campaign_faction_indep", False):
                # Use the cache event for independent faction lookup
                fac_event_id = cache_event_id
            else:
                # Use the parent event for inherited faction lookup
                fac_event_id = char.event.get_class_parent("faction").id

            # Build faction list based on determined event
            if fac_event_id:
                factions = char.factions_list.filter(event_id=fac_event_id)
                faction_list = [(faction.id, faction.name) for faction in factions]
            else:
                faction_list = []

            relations["faction_rels"] = build_relationship_dict(faction_list)

        # Handle character-to-character relationships if relationships feature is enabled
        if "relationships" in features:
            relationships = Relationship.objects.filter(deleted=None, source=char)
            rel_list = [(rel.target.id, rel.target.name) for rel in relationships]
            relations["relationships_rels"] = build_relationship_dict(rel_list)

            # Calculate important relationship count (excluding $unimportant entries)
            unimportant_count = 0
            if get_event_config(char.event_id, "writing_unimportant", False):
                unimportant_count = sum(
                    1 for rel in relationships if strip_tags(rel.text).lstrip().startswith("$unimportant")
                )
            relations["relationships_rels"]["important"] = relations["relationships_rels"]["count"] - unimportant_count

        # Handle speedlarp relationships if speedlarp feature is enabled
        if "speedlarp" in features:
            speedlarps = char.speedlarps_list.all()
            speedlarp_list = [(speedlarp.id, speedlarp.name) for speedlarp in speedlarps]
            relations["speedlarp_rels"] = build_relationship_dict(speedlarp_list)

        # Handle prologue relationships if prologue feature is enabled
        if "prologue" in features:
            prologues = char.prologues_list.all()
            prologue_list = [(prologue.id, prologue.name) for prologue in prologues]
            relations["prologue_rels"] = build_relationship_dict(prologue_list)

    except Exception as e:
        # Log the error with full traceback and return empty dict as fallback
        logger.error(f"Error getting relationships for character {char.id}: {e}", exc_info=True)
        relations = {}

    return relations


def get_event_faction_rels(faction: Faction) -> dict[str, Any]:
    """Get faction relationships for a specific faction.

    Retrieves all characters associated with the given faction and formats
    them into a relationship dictionary structure.

    Args:
        faction (Faction): The Faction instance to get relationships for.
            Must be a valid Faction model instance.

    Returns:
        dict[str, Any]: Dictionary containing relationship data with the structure:
            {
                'character_rels': {
                    'list': [(char_id, char_name), ...],
                    'count': int
                }
            }
            Returns empty dict if an error occurs.

    Raises:
        Exception: Logs any database or processing errors and returns empty dict.

    Example:
        >>> faction = Faction.objects.get(id=1)
        >>> rels = get_event_faction_rels(faction)
        >>> print(rels['character_rels']['count'])
        5
    """
    relations = {}

    try:
        # Get all characters associated with this faction
        characters = faction.characters.all()

        # Build list of character ID and name tuples
        char_list = [(char.id, char.name) for char in characters]

        # Structure the relationship data using helper function
        relations["character_rels"] = build_relationship_dict(char_list)

    except Exception as e:
        # Log error with full traceback for debugging
        logger.error(f"Error getting relationships for faction {faction.id}: {e}", exc_info=True)

        # Return empty dict on error to prevent downstream issues
        relations = {}

    return relations


def get_event_plot_rels(plot: Plot) -> dict[str, Any]:
    """Get plot relationships for a specific plot.

    Retrieves all character relationships associated with the given plot
    and formats them into a structured dictionary format.

    Args:
        plot (Plot): The Plot instance to get relationships for

    Returns:
        dict[str, Any]: Dictionary containing relationship data with structure:
            {
                'character_rels': {
                    'list': [(char_id, char_name), ...],
                    'count': int
                }
            }
            Returns empty dict if an error occurs.

    Raises:
        Logs errors but does not raise exceptions, returns empty dict instead.
    """
    relations = {}

    try:
        # Get all character relationships for this plot
        char_rels = plot.get_plot_characters()

        # Extract character ID and name tuples from relationships
        char_list = [(rel.character_id, rel.character.name) for rel in char_rels]

        # Build structured relationship dictionary with list and count
        relations["character_rels"] = build_relationship_dict(char_list)

    except Exception as e:
        # Log error with full traceback for debugging
        logger.error(f"Error getting relationships for plot {plot.id}: {e}", exc_info=True)

        # Return empty dict on any error to maintain consistent return type
        relations = {}

    return relations


def get_event_speedlarp_rels(speedlarp: SpeedLarp) -> dict[str, Any]:
    """Get speedlarp relationships for a specific speedlarp.

    Retrieves all characters associated with the given speedlarp and formats
    them into a structured dictionary containing relationship data.

    Args:
        speedlarp (SpeedLarp): The SpeedLarp instance to get relationships for.

    Returns:
        dict[str, Any]: Dictionary containing relationship data with the structure:
            {
                'character_rels': {
                    'list': [(char_id, char_name), ...],
                    'count': int
                }
            }
            Returns empty dict if an error occurs.

    Raises:
        Logs errors but does not raise exceptions.
    """
    relations = {}

    try:
        # Fetch all characters associated with the speedlarp
        characters = speedlarp.characters.all()

        # Build list of tuples containing character ID and name
        char_list = [(char.id, char.name) for char in characters]

        # Structure the character data using helper function
        relations["character_rels"] = build_relationship_dict(char_list)

    except Exception as e:
        # Log the error with full traceback for debugging
        logger.error(f"Error getting relationships for speedlarp {speedlarp.id}: {e}", exc_info=True)
        relations = {}

    return relations


def get_event_prologue_rels(prologue: Prologue) -> dict[str, Any]:
    """Get prologue relationships for a specific prologue.

    Retrieves all characters associated with the given prologue and formats
    them into a structured relationship dictionary for use in templates
    and API responses.

    Args:
        prologue (Prologue): The Prologue instance to get relationships for.
            Must be a valid Prologue object with accessible characters relationship.

    Returns:
        dict[str, Any]: Dictionary containing relationship data with the following structure:
            {
                'character_rels': {
                    'list': [(char_id, char_name), ...],
                    'count': int
                }
            }
            Returns empty dict if an error occurs during processing.

    Raises:
        Exception: Logs any database or processing errors but returns empty dict
            instead of propagating the exception.

    Example:
        >>> prologue = Prologue.objects.get(id=1)
        >>> rels = get_event_prologue_rels(prologue)
        >>> print(rels['character_rels']['count'])
        3
    """
    relations = {}

    try:
        # Fetch all characters associated with this prologue
        characters = prologue.characters.all()

        # Build list of character ID and name tuples for template rendering
        char_list = [(char.id, char.name) for char in characters]

        # Format character data using helper function to create standardized structure
        relations["character_rels"] = build_relationship_dict(char_list)

    except Exception as e:
        # Log error with full traceback for debugging while preventing crashes
        logger.error(f"Error getting relationships for prologue {prologue.id}: {e}", exc_info=True)
        relations = {}

    return relations


def get_event_quest_rels(quest: Quest) -> dict[str, Any]:
    """Get quest relationships for a specific quest.

    Retrieves all non-deleted traits associated with the given quest and formats
    them into a relationship dictionary structure.

    Args:
        quest (Quest): The Quest instance to get relationships for

    Returns:
        dict[str, Any]: Dictionary containing relationship data with the structure:
            {
                'trait_rels': {
                    'list': [(trait_id, trait_name), ...],
                    'count': int
                }
            }
            Returns empty dict if an error occurs during processing.

    Raises:
        Logs errors but does not raise exceptions - returns empty dict instead.
    """
    relations = {}

    try:
        # Query for all non-deleted traits associated with this quest
        traits = Trait.objects.filter(quest=quest, deleted=None)

        # Build list of tuples containing trait ID and name pairs
        trait_list = [(trait.id, trait.name) for trait in traits]

        # Format trait data into standardized relationship dictionary structure
        relations["trait_rels"] = build_relationship_dict(trait_list)

    except Exception as e:
        # Log error details for debugging while maintaining function stability
        logger.error(f"Error getting relationships for quest {quest.id}: {e}")
        relations = {}

    return relations


def get_event_questtype_rels(questtype: QuestType) -> dict[str, Any]:
    """Get questtype relationships for a specific questtype.

    Retrieves all related quests for the given questtype and formats them
    into a structured dictionary with count information.

    Args:
        questtype (QuestType): The QuestType instance to get relationships for.

    Returns:
        dict[str, Any]: Dictionary containing relationship data with the following structure:
            {
                'quest_rels': {
                    'list': [(quest_id, quest_name), ...],
                    'count': int
                }
            }

    Raises:
        Exception: Logs error if relationship retrieval fails and returns empty dict.
    """
    relations = {}

    try:
        # Retrieve all related quests for the questtype
        quests = questtype.quests.all()

        # Build list of tuples containing quest ID and name
        quest_list = [(quest.id, quest.name) for quest in quests]

        # Format quest relationships using helper function
        relations["quest_rels"] = build_relationship_dict(quest_list)

    except Exception as e:
        # Log error and return empty dict on failure
        logger.error(f"Error getting relationships for questtype {questtype.id}: {e}")
        relations = {}

    return relations


def refresh_event_faction_relationships(faction: Faction) -> None:
    """Update faction relationships in cache.

    Updates the cached relationship data for a specific faction.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        faction (Faction): The Faction instance to update relationships for

    Returns:
        None
    """
    # Get the current faction relationship data from the event
    faction_data = get_event_faction_rels(faction)

    # Update the cache with the faction's relationship data
    update_cache_section(faction.event_id, "factions", faction.id, faction_data)


def refresh_event_plot_relationships(plot: Plot) -> None:
    """Update plot relationships in cache.

    Updates the cached relationship data for a specific plot within an event.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        plot (Plot): The Plot instance to update relationships for.

    Returns:
        None

    Note:
        This function modifies the cache in-place and does not return any value.
        The cache is organized by event_id with a "plots" section containing
        plot-specific relationship data.
    """
    # Retrieve the current plot relationship data from the event
    plot_data = get_event_plot_rels(plot)

    # Update the cache with the new plot relationship data
    # Cache structure: event_id -> "plots" -> plot.id -> plot_data
    update_cache_section(plot.event_id, "plots", plot.id, plot_data)


def refresh_event_speedlarp_relationships(speedlarp: SpeedLarp) -> None:
    """Update speedlarp relationships in cache.

    Updates the cached relationship data for a specific speedlarp by retrieving
    fresh data and updating the cache section. If the cache doesn't exist for
    the event, it will be initialized for the entire event.

    Args:
        speedlarp (SpeedLarp): The SpeedLarp instance to update relationships for.
            Must have a valid event_id and id.

    Returns:
        None: This function performs cache updates and does not return a value.

    Note:
        This function depends on get_event_speedlarp_rels() and update_cache_section()
        being available in the current scope.
    """
    # Retrieve fresh speedlarp relationship data from the database
    speedlarp_data = get_event_speedlarp_rels(speedlarp)

    # Update the cache with the new speedlarp relationship data
    update_cache_section(speedlarp.event_id, "speedlarps", speedlarp.id, speedlarp_data)


def refresh_event_prologue_relationships(prologue: Prologue) -> None:
    """Update prologue relationships in cache.

    Updates the cached relationship data for a specific prologue.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        prologue (Prologue): The Prologue instance to update relationships for

    Returns:
        None
    """
    # Get the prologue relationship data for caching
    prologue_data = get_event_prologue_rels(prologue)

    # Update the cache section with the prologue data
    update_cache_section(prologue.event_id, "prologues", prologue.id, prologue_data)


def refresh_event_quest_relationships(quest: Quest) -> None:
    """Update quest relationships in cache.

    Updates the cached relationship data for a specific quest.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        quest (Quest): The Quest instance to update relationships for

    Returns:
        None
    """
    # Get the current quest relationship data
    quest_data = get_event_quest_rels(quest)

    # Update the cache with the new quest data
    update_cache_section(quest.event_id, "quests", quest.id, quest_data)


def refresh_event_questtype_relationships(questtype: QuestType) -> None:
    """Update questtype relationships in cache.

    Updates the cached relationship data for a specific questtype.
    If the cache doesn't exist, it will be initialized for the entire event.

    Args:
        questtype (QuestType): The QuestType instance to update relationships for.

    Returns:
        None
    """
    # Get the current questtype relationship data from the database
    questtype_data = get_event_questtype_rels(questtype)

    # Update the cache with the refreshed questtype data
    update_cache_section(questtype.event_id, "questtypes", questtype.id, questtype_data)


def on_faction_characters_m2m_changed(
    sender: type, instance: Faction, action: str, pk_set: set[int] | None, **kwargs: dict
) -> None:
    """Handle faction-character relationship changes.

    Updates both faction cache and character caches when relationships change.
    This signal handler is triggered when characters are added to or removed
    from a faction's characters many-to-many relationship.

    Args:
        sender: The through model class that manages the M2M relationship
        instance: The Faction instance whose relationships are changing
        action: The type of change being performed on the relationship.
            Common values include 'post_add', 'post_remove', 'post_clear'
        pk_set: Set of primary keys of the Character objects being affected.
            May be None for certain actions like 'post_clear'
        **kwargs: Additional keyword arguments passed by the Django signal system

    Returns:
        None

    Note:
        This function delegates the actual cache update logic to the generic
        update_m2m_related_characters helper function.
    """
    # Delegate to the generic M2M character update handler
    # This will handle cache invalidation for both the faction and related characters
    update_m2m_related_characters(instance, pk_set, action, refresh_event_faction_relationships)


def on_plot_characters_m2m_changed(
    sender: type, instance: "Plot", action: str, pk_set: set[int] | None, **kwargs
) -> None:
    """Handle plot-character relationship changes.

    Updates both plot cache and character caches when relationships change.
    This signal handler is triggered when characters are added, removed, or
    cleared from a plot's character relationships.

    Parameters
    ----------
    sender : type
        The through model class (PlotCharacterRel)
    instance : Plot
        The Plot instance whose relationships are changing
    action : str
        The type of change ('post_add', 'post_remove', 'post_clear', etc.)
    pk_set : set[int] | None
        Set of primary keys of the Character objects being modified
    **kwargs
        Additional keyword arguments from the signal

    Returns
    -------
    None
    """
    # Delegate to the generic M2M relationship handler for character updates
    # This ensures both plot and character caches are properly invalidated
    update_m2m_related_characters(instance, pk_set, action, refresh_event_plot_relationships)


def on_speedlarp_characters_m2m_changed(
    sender: type, instance: "SpeedLarp", action: str, pk_set: set[int] | None, **kwargs
) -> None:
    """Handle speedlarp-character relationship changes.

    Updates both speedlarp cache and character caches when relationships change.
    This signal handler is triggered when characters are added, removed, or cleared
    from a speedlarp's character relationships.

    Args:
        sender: The through model class for the many-to-many relationship
        instance: The SpeedLarp instance whose relationships are changing
        action: The type of change being performed on the relationship.
            Common values include 'post_add', 'post_remove', 'post_clear'
        pk_set: Set of primary keys of the Character objects being affected.
            May be None for actions like 'post_clear'
        **kwargs: Additional keyword arguments passed by Django's m2m_changed signal

    Returns:
        None

    Note:
        This function delegates the actual cache update logic to the generic
        update_m2m_related_characters function with the speedlarp-specific
        refresh callback.
    """
    # Delegate to the generic M2M relationship handler with speedlarp-specific refresh function
    update_m2m_related_characters(instance, pk_set, action, refresh_event_speedlarp_relationships)


def on_prologue_characters_m2m_changed(
    sender: type, instance: Prologue, action: str, pk_set: set[int] | None, **kwargs
) -> None:
    """Handle prologue-character relationship changes.

    Updates both prologue cache and character caches when relationships change.
    This signal handler is triggered when characters are added, removed, or cleared
    from a prologue's character relationships.

    Parameters
    ----------
    sender : type
        The through model class for the many-to-many relationship
    instance : Prologue
        The Prologue instance whose relationships are changing
    action : str
        The type of change being performed:
        - 'post_add': Characters were added to the prologue
        - 'post_remove': Characters were removed from the prologue
        - 'post_clear': All characters were cleared from the prologue
    pk_set : set[int] | None
        Set of primary keys of the Character objects being affected.
        None when action is 'post_clear'
    **kwargs
        Additional keyword arguments passed by Django's m2m_changed signal

    Returns
    -------
    None
    """
    # Delegate to utility function that handles m2m relationship cache updates
    # This ensures consistent cache invalidation for both prologue and character caches
    update_m2m_related_characters(instance, pk_set, action, refresh_event_prologue_relationships)
