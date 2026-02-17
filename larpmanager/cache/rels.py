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
from typing import TYPE_CHECKING, Any

from django.conf import settings as conf_settings
from django.core.cache import cache

from larpmanager.cache.character import update_event_cache_all
from larpmanager.cache.config import get_event_config
from larpmanager.cache.dirty import get_has_dirty_key, mark_dirty, refresh_if_dirty, resolve_dirty_section
from larpmanager.cache.feature import get_event_features
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import Event, Run
from larpmanager.models.utils import strip_tags
from larpmanager.models.writing import Character, Faction, Plot, Prologue, Relationship, SpeedLarp
from larpmanager.utils.core.common import _validate_and_fetch_objects
from larpmanager.utils.larpmanager.tasks import background_auto

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

_RELS_NS = "rels"
_get_rels_has_dirty_key = partial(get_has_dirty_key, _RELS_NS)
_mark_rels_dirty = partial(mark_dirty, _RELS_NS)
_refresh_rels_if_dirty = partial(refresh_if_dirty, _RELS_NS)
_resolve_dirty_rels_section = partial(resolve_dirty_section, _RELS_NS)


def get_event_rels_key(event_id: int) -> str:
    """Generate cache key for event relationships."""
    return f"event__rels__{event_id}"


def clear_event_relationships_cache(event_id: int) -> None:
    """Reset event relationships cache for given event ID."""
    # Clear cache for the main event
    cache_key = get_event_rels_key(event_id)
    cache.delete(cache_key)
    logger.debug("Reset cache for event %s", event_id)

    # Invalidate cache for all child events to maintain consistency
    for child_event_id in Event.objects.filter(parent_id=event_id).values_list("pk", flat=True):
        cache_key = get_event_rels_key(child_event_id)
        cache.delete(cache_key)


def build_relationship_dict(relationship_items: list) -> dict[str, Any]:
    """Build relationship dictionary with list and count."""
    return {"list": relationship_items, "count": len(relationship_items)}


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
        cached_event_data = cache.get(cache_key)

        if cached_event_data is None:
            logger.debug("Cache miss during %s update for event %s, reinitializing", section_name, event_id)
            # We need to get the event to reinitialize
            event = Event.objects.get(id=event_id)
            init_event_rels_all(event)
            return

        if section_name not in cached_event_data:
            cached_event_data[section_name] = {}

        cached_event_data[section_name][section_id] = data
        cache.set(cache_key, cached_event_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug("Updated %s %s relationships in cache", section_name, section_id)

    except Exception:
        logger.exception("Error updating %s %s relationships", section_name, section_id)
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
        cached_data = cache.get(cache_key)
        if cached_data and section_name in cached_data and section_id in cached_data[section_name]:
            del cached_data[section_name][section_id]
            cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
            logger.debug("Removed %s %s from cache", section_name, section_id)
    except Exception:
        logger.exception("Error removing %s %s from cache", section_name, section_id)
        clear_event_relationships_cache(event_id)


def _make_char_rels_func(event: Event) -> Callable:
    """Return a closure that computes character rels within a specific event.

    Fetches event features once so the closure can be called for many
    characters without repeating the features lookup.
    """
    features = get_event_features(event.id)
    return lambda char: get_event_char_rels(char, features, event)


def _get_section_rels_dirty_bg_func(section: str) -> Callable:
    """Return the dirty-aware background task for a given section."""
    return {
        "factions": refresh_faction_rels_dirty_background,
        "plots": refresh_plot_rels_dirty_background,
        "speedlarps": refresh_speedlarp_rels_dirty_background,
        "prologues": refresh_prologue_rels_dirty_background,
    }[section]


def refresh_character_related_caches(character: Character) -> None:
    """Update all caches that are related to a character.

    This function schedules background tasks to refresh caches for all entities
    that have relationships with the given character, including plots, factions,
    speedlarps, and prologues.

    Args:
        character (Character): The Character instance whose related caches need to be refreshed.

    Returns:
        None

    """
    # Schedule background task to update all plots that this character is part of
    plot_ids = list(character.get_plot_characters().values_list("plot_id", flat=True))
    if plot_ids:
        refresh_event_plot_relationships_background(plot_ids)

    # Schedule background task to update all factions that this character is part of
    faction_ids = list(character.factions_list.values_list("id", flat=True))
    if faction_ids:
        refresh_event_faction_relationships_background(faction_ids)

    # Schedule background task to update all speedlarps that this character is part of
    speedlarp_ids = list(character.speedlarps_list.values_list("id", flat=True))
    if speedlarp_ids:
        refresh_event_speedlarp_relationships_background(speedlarp_ids)

    # Schedule background task to update all prologues that this character is part of
    prologue_ids = list(character.prologues_list.values_list("id", flat=True))
    if prologue_ids:
        refresh_event_prologue_relationships_background(prologue_ids)


def update_m2m_related_characters(
    instance: Plot | Faction | SpeedLarp | Prologue,
    character_ids: set[int],
    action: str,
    section: str,
) -> None:
    """Update character caches for M2M relationship changes.

    Args:
        instance: The instance that changed (Plot, Faction, SpeedLarp, Prologue)
        character_ids: Set of character primary keys affected
        action: The M2M action type
        section: Cache section name for the instance

    """
    if action in ("post_add", "post_remove", "post_clear"):
        # Collect all affected character IDs
        affected_character_ids = []
        if character_ids:
            affected_character_ids = list(character_ids)
        elif action == "post_clear":
            # For post_clear, get all characters that were related
            if hasattr(instance, "characters"):
                affected_character_ids = list(instance.characters.values_list("id", flat=True))
            elif hasattr(instance, "get_plot_characters"):
                affected_character_ids = [rel.character_id for rel in instance.get_plot_characters()]

        # Get all run IDs to update (event and child events)
        event = instance.event
        events_id = list(Event.objects.filter(parent=event).values_list("pk", flat=True))
        events_id.append(event.id)
        run_ids = list(Run.objects.filter(event_id__in=events_id).values_list("id", flat=True))

        # Mark instance and affected characters dirty, then schedule background tasks
        _mark_rels_dirty(section, [instance.id], event.id)
        _get_section_rels_dirty_bg_func(section)(instance.id)

        if affected_character_ids:
            _mark_rels_dirty("characters", affected_character_ids, event.id)
            refresh_character_rels_dirty_background(affected_character_ids)

            # Update event cache for all runs and characters in background (single task)
            if run_ids:
                update_event_cache_all_background(run_ids, affected_character_ids)


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
    cached_relationships = cache.get(cache_key)

    # Initialize cache if no data found
    if cached_relationships is None:
        logger.debug("Cache miss for event %s, initializing", event.id)
        return init_event_rels_all(event)

    # Resolve any items marked still dirty by M2M signal
    any_resolved = False
    if cache.get(_get_rels_has_dirty_key(event.id)):
        char_rels_func = _make_char_rels_func(event)
        for _section, _model, _rels_func in (
            ("characters", Character, char_rels_func),
            ("factions", Faction, get_event_faction_rels),
            ("plots", Plot, get_event_plot_rels),
            ("speedlarps", SpeedLarp, get_event_speedlarp_rels),
            ("prologues", Prologue, get_event_prologue_rels),
            ("quests", Quest, get_event_quest_rels),
            ("questtypes", QuestType, get_event_questtype_rels),
        ):
            if _resolve_dirty_rels_section(event.id, cached_relationships, _section, _model, _rels_func):
                any_resolved = True
    if any_resolved:
        cache.set(cache_key, cached_relationships, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_relationships


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
    relationship_cache: dict[str, dict[int, dict[str, Any]]] = {}

    try:
        # Get enabled features for this event to determine which relationships to build
        features = get_event_features(event.id)

        # Configuration mapping for each relationship type with their corresponding
        # feature name, cache key, model class, relationship function, and feature flag
        relationship_configs = [
            ("character", "characters", Character, get_event_char_rels, True),
            ("faction", "factions", Faction, get_event_faction_rels, False),
            ("plot", "plots", Plot, get_event_plot_rels, False),
            ("speedlarp", "speedlarps", SpeedLarp, get_event_speedlarp_rels, False),
            ("prologue", "prologues", Prologue, get_event_prologue_rels, False),
            ("quest", "quests", Quest, get_event_quest_rels, False),
            ("questtype", "questtypes", QuestType, get_event_questtype_rels, False),
        ]

        # Process each relationship type if the corresponding feature is enabled
        for (
            feature_name,
            cache_key_plural,
            model_class,
            get_relationships_function,
            should_pass_features,
        ) in relationship_configs:
            if feature_name not in features:
                continue

            # Initialize the cache section for this relationship type
            relationship_cache[cache_key_plural] = {}

            # Get all elements of this type associated with the event
            elements = event.get_elements(model_class)

            # Build relationships for each element, passing features if required
            for element in elements:
                if should_pass_features:
                    relationship_cache[cache_key_plural][element.id] = get_relationships_function(
                        element,
                        features,
                        event,
                    )
                else:
                    relationship_cache[cache_key_plural][element.id] = get_relationships_function(element)

            logger.debug("Initialized %s %s relationships for event %s", len(elements), feature_name, event.id)

        # Cache the complete relationship data structure
        cache_key = get_event_rels_key(event.id)
        cache.set(cache_key, relationship_cache, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug("Cached relationships for event %s", event.id)

    except Exception:
        # Log the error with full traceback and return empty result
        logger.exception("Error initializing relationships for event %s", event.id)
        relationship_cache = {}

    return relationship_cache


def refresh_character_relationships(character: Character) -> None:
    """Refresh character relationships for the character's event and all child events."""
    # Refresh relationships for the character's primary event
    refresh_event_character_relationships(character, character.event)

    # Refresh relationships for all child events if this is a campaign parent
    for child_event in Event.objects.filter(parent_id=character.event_id):
        refresh_event_character_relationships(character, child_event)


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
        cached_relationships = cache.get(cache_key)

        # If cache doesn't exist, initialize it for the entire event
        if cached_relationships is None:
            logger.debug("Cache miss during character update for event %s, reinitializing", event)
            init_event_rels_all(event)
            return

        # Ensure characters dictionary exists in cache structure
        if "characters" not in cached_relationships:
            cached_relationships["characters"] = {}

        # Get event features and update character relationships
        event_features = get_event_features(event.id)
        cached_relationships["characters"][char.id] = get_event_char_rels(char, event_features, event)

        # Save updated cache with 1-day timeout
        cache.set(cache_key, cached_relationships, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
        logger.debug("Updated character %s relationships in cache", char.id)

    except Exception:
        # Log error and clear cache to prevent inconsistent state
        logger.exception("Error updating character %s relationships", char.id)
        clear_event_relationships_cache(event.id)


def _build_plot_relations(char: Character) -> dict[str, Any]:
    """Build plot relationships for a character.

    Args:
        char: Character to build plot relationships for

    Returns:
        Dictionary with plot relationship data including important count
    """
    related_plots = char.get_plot_characters()
    plot_list = [(plot_rel.plot_id, plot_rel.plot.name) for plot_rel in related_plots]
    plot_rels = build_relationship_dict(plot_list)

    # Calculate important plot count (excluding $unimportant entries)
    unimportant_plot_count = 0
    if get_event_config(char.event_id, "writing_unimportant", default_value=False):
        unimportant_plot_count = sum(
            1 for plot_rel in related_plots if strip_tags(plot_rel.text).lstrip().startswith("$unimportant")
        )
    plot_rels["important"] = plot_rels["count"] - unimportant_plot_count
    return plot_rels


def _build_faction_relations(char: Character, event: Event) -> dict[str, Any]:
    """Build faction relationships for a character.

    Args:
        char: Character to build faction relationships for
        event: Event for faction independence configuration

    Returns:
        Dictionary with faction relationship data
    """
    cache_event_id = event.id if event else char.event_id
    if get_event_config(cache_event_id, "campaign_faction_indep", default_value=False):
        # Use the cache event for independent faction lookup
        faction_event_id = cache_event_id
    else:
        # Use the parent event for inherited faction lookup
        faction_event_id = char.event.get_class_parent("faction").id

    # Build faction list based on determined event
    if faction_event_id:
        character_factions = char.factions_list.filter(event_id=faction_event_id)
        faction_list = [(faction.id, faction.name) for faction in character_factions]
    else:
        faction_list = []

    return build_relationship_dict(faction_list)


def _build_character_relations(char: Character) -> dict[str, Any]:
    """Build character-to-character relationships.

    Args:
        char: Character to build relationships for

    Returns:
        Dictionary with character relationship data including important count
    """
    character_relationships = Relationship.objects.filter(deleted=None, source=char)
    relationship_list = [(relationship.target.id, relationship.target.name) for relationship in character_relationships]
    relationships_rels = build_relationship_dict(relationship_list)

    # Calculate important relationship count (excluding $unimportant entries)
    unimportant_relationship_count = 0
    if get_event_config(char.event_id, "writing_unimportant", default_value=False):
        unimportant_relationship_count = sum(
            1
            for relationship in character_relationships
            if strip_tags(relationship.text).lstrip().startswith("$unimportant")
        )
    relationships_rels["important"] = relationships_rels["count"] - unimportant_relationship_count
    return relationships_rels


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
            relations["plot_rels"] = _build_plot_relations(char)

        # Handle faction relationships if faction feature is enabled
        if "faction" in features:
            relations["faction_rels"] = _build_faction_relations(char, event)

        # Handle character-to-character relationships if relationships feature is enabled
        if "relationships" in features:
            relations["relationships_rels"] = _build_character_relations(char)

        # Handle speedlarp relationships if speedlarp feature is enabled
        if "speedlarp" in features:
            character_speedlarps = char.speedlarps_list.all()
            speedlarp_list = [(speedlarp.id, speedlarp.name) for speedlarp in character_speedlarps]
            relations["speedlarp_rels"] = build_relationship_dict(speedlarp_list)

        # Handle prologue relationships if prologue feature is enabled
        if "prologue" in features:
            character_prologues = char.prologues_list.all()
            prologue_list = [(prologue.id, prologue.name) for prologue in character_prologues]
            relations["prologue_rels"] = build_relationship_dict(prologue_list)

    except Exception:
        # Log the error with full traceback and return empty dict as fallback
        logger.exception("Error getting relationships for character %s", char.id)
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
    faction_relations = {}

    try:
        # Get all characters associated with this faction
        faction_characters = faction.characters.all()

        # Build list of character ID and name tuples
        character_id_name_tuples = [(character.id, character.name) for character in faction_characters]

        # Structure the relationship data using helper function
        faction_relations["character_rels"] = build_relationship_dict(character_id_name_tuples)

    except Exception:
        # Log error with full traceback for debugging
        logger.exception("Error getting relationships for faction %s", faction.id)

        # Return empty dict on error to prevent downstream issues
        faction_relations = {}

    return faction_relations


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
    relationships = {}

    try:
        # Get all character relationships for this plot
        character_relationships = plot.get_plot_characters()

        # Extract character ID and name tuples from relationships
        character_id_name_pairs = [
            (relationship.character_id, relationship.character.name) for relationship in character_relationships
        ]

        # Build structured relationship dictionary with list and count
        relationships["character_rels"] = build_relationship_dict(character_id_name_pairs)

    except Exception:
        # Log error with full traceback for debugging
        logger.exception("Error getting relationships for plot %s", plot.id)

        # Return empty dict on any error to maintain consistent return type
        relationships = {}

    return relationships


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
    relationships = {}

    try:
        # Fetch all characters associated with the speedlarp
        speedlarp_characters = speedlarp.characters.all()

        # Build list of tuples containing character ID and name
        character_id_name_pairs = [(character.id, character.name) for character in speedlarp_characters]

        # Structure the character data using helper function
        relationships["character_rels"] = build_relationship_dict(character_id_name_pairs)

    except Exception:
        # Log the error with full traceback for debugging
        logger.exception("Error getting relationships for speedlarp %s", speedlarp.id)
        relationships = {}

    return relationships


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
    relationships = {}

    try:
        # Fetch all characters associated with this prologue
        prologue_characters = prologue.characters.all()

        # Build list of character ID and name tuples for template rendering
        character_id_name_list = [(character.id, character.name) for character in prologue_characters]

        # Format character data using helper function to create standardized structure
        relationships["character_rels"] = build_relationship_dict(character_id_name_list)

    except Exception:
        # Log error with full traceback for debugging while preventing crashes
        logger.exception("Error getting relationships for prologue %s", prologue.id)
        relationships = {}

    return relationships


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
    relationships = {}

    try:
        # Query for all non-deleted traits associated with this quest
        associated_traits = Trait.objects.filter(quest=quest, deleted=None)

        # Build list of tuples containing trait ID and name pairs
        trait_id_name_pairs = [(trait.id, trait.name) for trait in associated_traits]

        # Format trait data into standardized relationship dictionary structure
        relationships["trait_rels"] = build_relationship_dict(trait_id_name_pairs)

    except Exception:
        # Log error details for debugging while maintaining function stability
        logger.exception("Error getting relationships for quest %s", quest.id)
        relationships = {}

    return relationships


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
    relationships = {}

    try:
        # Retrieve all related quests for the questtype
        related_quests = questtype.quests.all()

        # Build list of tuples containing quest ID and name
        quest_id_name_pairs = [(quest.id, quest.name) for quest in related_quests]

        # Format quest relationships using helper function
        relationships["quest_rels"] = build_relationship_dict(quest_id_name_pairs)

    except Exception:
        # Log error and return empty dict on failure
        logger.exception("Error getting relationships for questtype %s", questtype.id)
        relationships = {}

    return relationships


def refresh_event_faction_relationships(faction: Faction) -> None:
    """Update faction relationships in cache."""
    # Get the current faction relationship data from the event
    faction_relationship_data = get_event_faction_rels(faction)

    # Update the cache with the faction's relationship data
    update_cache_section(faction.event_id, "factions", faction.id, faction_relationship_data)


def refresh_event_plot_relationships(plot: Plot) -> None:
    """Update plot relationships in cache."""
    # Retrieve the current plot relationship data from the event
    plot_relationship_data = get_event_plot_rels(plot)

    # Update the cache with the new plot relationship data
    # Cache structure: event_id -> "plots" -> plot.id -> plot_relationship_data
    update_cache_section(plot.event_id, "plots", plot.id, plot_relationship_data)


def refresh_event_speedlarp_relationships(speedlarp: SpeedLarp) -> None:
    """Update speedlarp relationships in cache."""
    # Retrieve fresh speedlarp relationship data from the database
    speedlarp_relationships_data = get_event_speedlarp_rels(speedlarp)

    # Update the cache with the new speedlarp relationship data
    update_cache_section(speedlarp.event_id, "speedlarps", speedlarp.id, speedlarp_relationships_data)


def refresh_event_prologue_relationships(prologue: Prologue) -> None:
    """Update prologue relationships in cache."""
    # Get the prologue relationship data for caching
    prologue_relationship_data = get_event_prologue_rels(prologue)

    # Update the cache section with the prologue data
    update_cache_section(prologue.event_id, "prologues", prologue.id, prologue_relationship_data)


def refresh_event_quest_relationships(quest: Quest) -> None:
    """Update quest relationships in cache."""
    # Get the current quest relationship data
    quest_relationship_data = get_event_quest_rels(quest)

    # Update the cache with the new quest data
    update_cache_section(quest.event_id, "quests", quest.id, quest_relationship_data)


def refresh_event_questtype_relationships(quest_type: QuestType) -> None:
    """Update questtype relationships in cache."""
    # Get the current questtype relationship data from the database
    quest_type_relationship_data = get_event_questtype_rels(quest_type)

    # Update the cache with the refreshed questtype data
    update_cache_section(quest_type.event_id, "questtypes", quest_type.id, quest_type_relationship_data)


# Background tasks for cache updates


@background_auto(queue="cache-rels")
def refresh_character_relationships_background(character_ids: int | list[int]) -> None:
    """Update character relationships in cache (background task).

    Args:
        character_ids: Single ID or list of IDs of Characters to refresh
    """
    characters = _validate_and_fetch_objects(Character, character_ids, "Character")
    for character in characters:
        refresh_character_relationships(character)


@background_auto(queue="cache-rels")
def refresh_event_faction_relationships_background(faction_ids: int | list[int]) -> None:
    """Update faction relationships in cache (background task).

    Args:
        faction_ids: Single ID or list of IDs of Factions to refresh
    """
    factions = _validate_and_fetch_objects(Faction, faction_ids, "Faction")
    for faction in factions:
        refresh_event_faction_relationships(faction)


@background_auto(queue="cache-rels")
def refresh_event_plot_relationships_background(plot_ids: int | list[int]) -> None:
    """Update plot relationships in cache (background task).

    Args:
        plot_ids: Single ID or list of IDs of Plots to refresh
    """
    plots = _validate_and_fetch_objects(Plot, plot_ids, "Plot")
    for plot in plots:
        refresh_event_plot_relationships(plot)


@background_auto(queue="cache-rels")
def refresh_event_speedlarp_relationships_background(speedlarp_ids: int | list[int]) -> None:
    """Update speedlarp relationships in cache (background task).

    Args:
        speedlarp_ids: Single ID or list of IDs of SpeedLarps to refresh
    """
    speedlarps = _validate_and_fetch_objects(SpeedLarp, speedlarp_ids, "SpeedLarp")
    for speedlarp in speedlarps:
        refresh_event_speedlarp_relationships(speedlarp)


@background_auto(queue="cache-rels")
def refresh_event_prologue_relationships_background(prologue_ids: int | list[int]) -> None:
    """Update prologue relationships in cache (background task).

    Args:
        prologue_ids: Single ID or list of IDs of Prologues to refresh
    """
    prologues = _validate_and_fetch_objects(Prologue, prologue_ids, "Prologue")
    for prologue in prologues:
        refresh_event_prologue_relationships(prologue)


@background_auto(queue="cache-rels")
def refresh_event_quest_relationships_background(quest_ids: int | list[int]) -> None:
    """Update quest relationships in cache (background task).

    Args:
        quest_ids: Single ID or list of IDs of Quests to refresh
    """
    quests = _validate_and_fetch_objects(Quest, quest_ids, "Quest")
    for quest in quests:
        refresh_event_quest_relationships(quest)


@background_auto(queue="cache-rels")
def refresh_event_questtype_relationships_background(questtype_ids: int | list[int]) -> None:
    """Update questtype relationships in cache (background task).

    Args:
        questtype_ids: Single ID or list of IDs of QuestTypes to refresh
    """
    questtypes = _validate_and_fetch_objects(QuestType, questtype_ids, "QuestType")
    for questtype in questtypes:
        refresh_event_questtype_relationships(questtype)


@background_auto(queue="cache-rels")
def update_event_cache_all_background(run_ids: int | list[int], character_ids: int | list[int]) -> None:
    """Update event cache for characters and runs (background task).

    Args:
        run_ids: Single ID or list of IDs of Runs
        character_ids: Single ID or list of IDs of Characters
    """
    # Normalize to lists
    if isinstance(run_ids, int):
        run_ids = [run_ids]
    if isinstance(character_ids, int):
        character_ids = [character_ids]

    # Fetch and validate runs
    runs = _validate_and_fetch_objects(Run, run_ids, "Run")

    # Fetch and validate characters
    characters = _validate_and_fetch_objects(Character, character_ids, "Character")

    # Update cache for all combinations
    for run in runs:
        for character in characters:
            update_event_cache_all(run, character)


# Dirty-aware background tasks (skip items already resolved on-demand)


@background_auto(queue="cache-rels")
def refresh_character_rels_dirty_background(character_ids: int | list[int]) -> None:
    """Update character relationships in cache (dirty-aware background task)."""
    characters = _validate_and_fetch_objects(Character, character_ids, "Character")
    _refresh_rels_if_dirty("characters", characters, refresh_character_relationships)


@background_auto(queue="cache-rels")
def refresh_faction_rels_dirty_background(faction_ids: int | list[int]) -> None:
    """Update faction relationships in cache (dirty-aware background task)."""
    factions = _validate_and_fetch_objects(Faction, faction_ids, "Faction")
    _refresh_rels_if_dirty("factions", factions, refresh_event_faction_relationships)


@background_auto(queue="cache-rels")
def refresh_plot_rels_dirty_background(plot_ids: int | list[int]) -> None:
    """Update plot relationships in cache (dirty-aware background task)."""
    plots = _validate_and_fetch_objects(Plot, plot_ids, "Plot")
    _refresh_rels_if_dirty("plots", plots, refresh_event_plot_relationships)


@background_auto(queue="cache-rels")
def refresh_speedlarp_rels_dirty_background(speedlarp_ids: int | list[int]) -> None:
    """Update speedlarp relationships in cache (dirty-aware background task)."""
    speedlarps = _validate_and_fetch_objects(SpeedLarp, speedlarp_ids, "SpeedLarp")
    _refresh_rels_if_dirty("speedlarps", speedlarps, refresh_event_speedlarp_relationships)


@background_auto(queue="cache-rels")
def refresh_prologue_rels_dirty_background(prologue_ids: int | list[int]) -> None:
    """Update prologue relationships in cache (dirty-aware background task)."""
    prologues = _validate_and_fetch_objects(Prologue, prologue_ids, "Prologue")
    _refresh_rels_if_dirty("prologues", prologues, refresh_event_prologue_relationships)


# Signal handlers for M2M changes


def on_faction_characters_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: Faction,
    action: str,
    pk_set: set[int] | None,
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle faction-character relationship changes."""
    # Delegate to the generic M2M character update handler
    # This will schedule background tasks for cache invalidation
    update_m2m_related_characters(instance, pk_set, action, "factions")


def on_plot_characters_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: Plot,
    action: str,
    pk_set: set[int] | None,
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle plot-character relationship changes."""
    # Delegate to the generic M2M relationship handler for character updates
    # This schedules background tasks for both plot and character cache updates
    update_m2m_related_characters(instance, pk_set, action, "plots")


def on_speedlarp_characters_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: SpeedLarp,
    action: str,
    pk_set: set[int] | None,
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle speedlarp-character relationship changes."""
    # Delegate to the generic M2M relationship handler with speedlarp-specific background refresh
    update_m2m_related_characters(instance, pk_set, action, "speedlarps")


def on_prologue_characters_m2m_changed(
    sender: type,  # noqa: ARG001
    instance: Prologue,
    action: str,
    pk_set: set[int] | None,
    **kwargs: object,  # noqa: ARG001
) -> None:
    """Handle prologue-character relationship changes."""
    # Delegate to utility function that schedules background tasks for cache updates
    # This ensures consistent cache invalidation for both prologue and character caches
    update_m2m_related_characters(instance, pk_set, action, "prologues")
