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

import os
import shutil
from typing import Optional

from django.conf import settings as conf_settings
from django.core.cache import cache

from larpmanager.cache.config import get_event_config
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.fields import visible_writing_fields
from larpmanager.cache.registration import search_player
from larpmanager.models.base import BaseModel
from larpmanager.models.casting import AssignmentTrait, Quest, QuestType, Trait
from larpmanager.models.event import Event, Run
from larpmanager.models.form import (
    QuestionApplicable,
    WritingAnswer,
    WritingChoice,
)
from larpmanager.models.member import Member
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import Character, Faction, FactionType


def delete_all_in_path(path):
    """Recursively delete all contents within a directory path.

    Args:
        path (str): Directory path to clean
    """
    if os.path.exists(path):
        # Remove all contents inside the path
        for entry_name in os.listdir(path):
            entry_path = os.path.join(path, entry_name)
            if os.path.isfile(entry_path) or os.path.islink(entry_path):
                os.remove(entry_path)
            elif os.path.isdir(entry_path):
                shutil.rmtree(entry_path)


def get_event_cache_all_key(event_run):
    """Generate cache key for event data.

    Args:
        event_run: Run instance

    Returns:
        str: Cache key for event factions and characters
    """
    return f"event_factions_characters_{event_run.event.slug}_{event_run.number}"


def init_event_cache_all(context: dict) -> dict:
    """Initialize complete event cache with characters, factions, and traits.

    Builds a comprehensive cache for event data by sequentially loading
    characters, factions, and conditionally traits based on available features.

    Args:
        context: Context dictionary containing event and feature data.
             Must include 'features' key for feature availability checks.

    Returns:
        dict: Cached event data including characters, factions, and
              optionally traits if questbuilder feature is enabled.
    """
    # Initialize empty result dictionary for cache storage
    cached_event_data = {}

    # Load character data into cache
    get_event_cache_characters(context, cached_event_data)

    # Load faction data into cache
    get_event_cache_factions(context, cached_event_data)

    # Conditionally load traits if questbuilder feature is available
    if "questbuilder" in context["features"]:
        get_event_cache_traits(context, cached_event_data)

    return cached_event_data


def get_event_cache_characters(context: dict, cache_result: dict) -> dict:
    """Cache character data for an event including assignments and registrations.

    This function populates the results dictionary with character data for caching purposes.
    It handles character assignments, player data retrieval, and applies filtering based on
    event configuration and mirror functionality.

    Args:
        context: Context dictionary containing event data, features, run information, and event config.
        cache_result: Results dictionary to populate with character data and metadata.

    Returns:
        The updated results dictionary with character data, assignments, and max character number.
    """
    cache_result["chars"] = {}

    # Check if mirror feature is enabled for character filtering
    is_mirror_enabled = "mirror" in context["features"]

    # Build assignments mapping from character number to registration relation
    context["assignments"] = {}
    registration_query = RegistrationCharacterRel.objects.filter(reg__run=context["run"])
    for registration_character_rel in registration_query.select_related("character", "reg", "reg__member"):
        context["assignments"][registration_character_rel.character.number] = registration_character_rel

    # Get event configuration for hiding uncasted characters
    hide_uncasted_characters = get_event_config(context["event"].id, "gallery_hide_uncasted_characters", False, context)

    # Get list of assigned character IDs for mirror filtering
    assigned_character_ids = RegistrationCharacterRel.objects.filter(reg__run=context["run"]).values_list(
        "character_id", flat=True
    )

    # Process each character for the event cache
    characters_query = context["event"].get_elements(Character).filter(hide=False).order_by("number")
    for character in characters_query.prefetch_related("factions_list"):
        # Skip mirror characters that are already assigned
        if is_mirror_enabled and character.mirror_id in assigned_character_ids:
            continue

        # Build character data and search for player information
        character_data = character.show(context["run"])
        character_data["fields"] = {}
        search_player(character, character_data, context)

        # Hide uncasted characters if configuration is enabled
        if hide_uncasted_characters and character_data["player_id"] == 0:
            character_data["hide"] = True

        cache_result["chars"][int(character_data["number"])] = character_data

    # Add field data to the cache
    get_event_cache_fields(context, cache_result)

    # Set the maximum character number for reference
    if cache_result["chars"]:
        cache_result["max_ch_number"] = max(cache_result["chars"], key=int)
    else:
        cache_result["max_ch_number"] = 0

    return cache_result


def get_event_cache_fields(context: dict, res: dict, only_visible: bool = True) -> None:
    """
    Retrieve and cache writing fields for characters in an event.

    This function populates character data with their associated writing field
    responses, including both multiple choice selections and text answers.

    Args:
        context: Context dictionary containing features and questions data
        res: Result dictionary with character data under 'chars' key
        only_visible: Whether to include only visible fields. Defaults to True.

    Returns:
        None: Modifies res dictionary in-place by adding field data to characters

    Note:
        Function returns early if 'character' feature is not enabled or if
        no questions are available in the context.
    """
    # Early return if character feature is not enabled
    if "character" not in context["features"]:
        return

    # Retrieve visible question IDs and populate context with questions
    visible_writing_fields(context, QuestionApplicable.CHARACTER, only_visible=only_visible)
    if "questions" not in context:
        return

    # Extract question IDs from context for database filtering
    question_ids = context["questions"].keys()

    # Create mapping from character IDs to their position numbers in results
    character_id_to_position = {}
    for character_position, character_data in res["chars"].items():
        character_id_to_position[character_data["id"]] = character_position

    # Retrieve and process multiple choice answers for characters
    # Each choice can have multiple options selected per question
    choice_answers = WritingChoice.objects.filter(question_id__in=question_ids)
    for element_id, question_id, option_id in choice_answers.values_list("element_id", "question_id", "option_id"):
        # Skip if character not in current event mapping
        if element_id not in character_id_to_position:
            continue

        # Map database values to result structure
        character_position = character_id_to_position[element_id]
        question = question_id
        value = option_id

        # Initialize fields list for question if not exists, then append choice
        fields = res["chars"][character_position]["fields"]
        if question not in fields:
            fields[question] = []
        fields[question].append(value)

    # Retrieve and process text answers for characters
    # Each text answer is a single value per question
    text_answers = WritingAnswer.objects.filter(question_id__in=question_ids)
    for element_id, question_id, text_value in text_answers.values_list("element_id", "question_id", "text"):
        # Skip if character not in current event mapping
        if element_id not in character_id_to_position:
            continue

        # Map database values to result structure
        character_position = character_id_to_position[element_id]
        question = question_id
        value = text_value

        # Set text answer directly (single value, not list)
        res["chars"][character_position]["fields"][question] = value


def get_character_element_fields(context, character_id, only_visible=True):
    return get_writing_element_fields(
        context, "character", QuestionApplicable.CHARACTER, character_id, only_visible=only_visible
    )


def get_writing_element_fields(
    context: dict, feature_name: str, applicable, element_id: int, only_visible: bool = True
) -> dict:
    """
    Get writing fields for a specific element with visibility filtering.

    Retrieves writing questions, options, and field values for a given element,
    applying visibility filters based on context configuration.

    Args:
        context: Context dictionary containing event and configuration data including
             'questions', 'options', and visibility settings
        feature_name: Name of the feature (e.g., 'character', 'faction') used
                     for determining visibility key
        applicable: QuestionApplicable enum value defining question scope
        element_id: Unique identifier of the element to retrieve fields for
        only_visible: Whether to include only visible fields. Defaults to True

    Returns:
        Dictionary containing:
            - questions: Available questions from context
            - options: Available options from context
            - fields: Mapping of question_id to field values (text or list of option_ids)
    """
    # Apply visibility filtering to populate context with visible fields
    visible_writing_fields(context, applicable, only_visible=only_visible)

    # Filter questions based on visibility configuration
    # Only include questions that are explicitly shown or when show_all is enabled
    visible_question_ids = []
    for question_id in context["questions"].keys():
        question_config_key = str(question_id)
        # Skip questions not marked as visible unless showing all
        if "show_all" not in context and question_config_key not in context[f"show_{feature_name}"]:
            continue
        visible_question_ids.append(question_id)

    # Retrieve text answers for visible questions
    # Store direct text responses in fields dictionary
    question_id_to_value = {}

    # Retrieve text answers for visible questions
    # Query WritingAnswer model for text-based responses
    text_answers_query = WritingAnswer.objects.filter(element_id=element_id, question_id__in=visible_question_ids)
    for question_id, answer_text in text_answers_query.values_list("question_id", "text"):
        question_id_to_value[question_id] = answer_text

    # Retrieve choice answers for visible questions
    # Group multiple choice options into lists per question
    choice_answers_query = WritingChoice.objects.filter(element_id=element_id, question_id__in=visible_question_ids)
    for question_id, option_id in choice_answers_query.values_list("question_id", "option_id"):
        # Initialize list if question not yet in fields
        if question_id not in question_id_to_value:
            question_id_to_value[question_id] = []
        question_id_to_value[question_id].append(option_id)

    return {"questions": context["questions"], "options": context["options"], "fields": question_id_to_value}


def get_event_cache_factions(context: dict, result: dict) -> None:
    """Build cached faction data for events.

    Organizes faction information by type and prepares faction selection options,
    handling characters without primary factions and creating faction-character
    mappings for the event cache.

    Args:
        context: Context dictionary containing event information with 'event' key
        result: Result dictionary to be populated with faction data, modified in-place

    Returns:
        None: Function modifies result in-place, adding 'factions' and 'factions_typ' keys

    Note:
        - Creates a fake faction (number 0) for characters without primary factions
        - Only includes factions that have associated characters
        - Organizes factions by type for easy lookup
    """
    # Initialize faction data structures
    result["factions"] = {}
    result["factions_typ"] = {}

    # If faction feature is not enabled, create single default faction with all characters
    if "faction" not in get_event_features(context["event"].id):
        result["factions"][0] = {
            "name": "",
            "number": 0,
            "typ": FactionType.PRIM,
            "teaser": "",
            "characters": list(result["chars"].keys()),
        }
        result["factions_typ"][FactionType.PRIM] = [0]
        return

    # Find characters without a primary faction (faction 0)
    characters_without_primary_faction = []
    for character_number, character_data in result["chars"].items():
        if "factions" in character_data and 0 in character_data["factions"]:
            characters_without_primary_faction.append(character_number)

    # Create fake faction for characters without primary faction
    if characters_without_primary_faction:
        result["factions"][0] = {
            "name": "",
            "number": 0,
            "typ": FactionType.PRIM,
            "teaser": "",
            "characters": characters_without_primary_faction,
        }
        result["factions_typ"][FactionType.PRIM] = [0]

    # Process real factions from the event
    for faction in context["event"].get_elements(Faction).order_by("number"):
        # Get faction display data
        faction_data = faction.show_red()
        faction_data["characters"] = []

        # Find characters belonging to this faction
        for character_number, character_data in result["chars"].items():
            if faction_data["number"] in character_data["factions"]:
                faction_data["characters"].append(character_number)

        # Skip factions with no characters
        if not faction_data["characters"]:
            continue

        # Add faction to results and organize by type
        result["factions"][faction.number] = faction_data
        if faction.typ not in result["factions_typ"]:
            result["factions_typ"][faction.typ] = []
        result["factions_typ"][faction.typ].append(faction.number)


def get_event_cache_traits(context: dict, res: dict) -> None:
    """Build cached trait and quest data for events.

    Organizes character traits, quest types, and related game mechanics data,
    including trait relationships, character assignments, and quest type
    mappings for efficient event cache operations.

    Args:
        context: Context dictionary containing event information with 'event' and 'run' keys
        res: Result dictionary to be populated with trait and quest data, must contain 'chars' key

    Returns:
        None: Function modifies res in-place, adding quest types, traits, and relationships

    Side Effects:
        Modifies res dictionary by adding:
        - quest_types: Mapping of quest type numbers to their display data
        - quests: Mapping of quest numbers to their display data
        - traits: Mapping of trait numbers to enhanced trait data with relationships
        - max_tr_number: Maximum trait number or 0 if no traits exist
    """
    # Build quest types mapping ordered by number
    res["quest_types"] = {}
    for quest_type in QuestType.objects.filter(event=context["event"]).order_by("number"):
        res["quest_types"][quest_type.number] = quest_type.show()

    # Build quests mapping with type relationships
    res["quests"] = {}
    for quest in Quest.objects.filter(event=context["event"]).order_by("number").select_related("typ"):
        res["quests"][quest.number] = quest.show()

    # Build trait relationships mapping (traits that reference other traits)
    trait_relationships = {}
    for trait in Trait.objects.filter(event=context["event"]).prefetch_related("traits"):
        trait_relationships[trait.number] = []
        # Add related trait numbers, excluding self-references
        for associated_trait in trait.traits.all():
            if associated_trait.number == trait.number:
                continue
            trait_relationships[trait.number].append(associated_trait.number)

    # Build main traits mapping with character assignments
    res["traits"] = {}
    assignment_traits_query = AssignmentTrait.objects.filter(run=context["run"]).order_by("typ")

    # Process each assigned trait and link to character
    for assignment_trait in assignment_traits_query.select_related("trait", "trait__quest", "trait__quest__typ"):
        trait_data = assignment_trait.trait.show()
        trait_data["quest"] = assignment_trait.trait.quest.number
        trait_data["typ"] = assignment_trait.trait.quest.typ.number
        trait_data["traits"] = trait_relationships[assignment_trait.trait.number]

        # Find the character this trait is assigned to
        found_character = None
        for _number, character in res["chars"].items():
            if "player_id" in character and character["player_id"] == assignment_trait.member_id:
                found_character = character
                break

        # Skip if character not found in cache
        if not found_character:
            continue

        # Initialize character traits list if needed
        if "traits" not in found_character:
            found_character["traits"] = []

        # Link trait to character and vice versa
        found_character["traits"].append(trait_data["number"])
        trait_data["char"] = found_character["number"]
        res["traits"][trait_data["number"]] = trait_data

    # Set maximum trait number for cache optimization
    if res["traits"]:
        res["max_tr_number"] = max(res["traits"], key=int)
    else:
        res["max_tr_number"] = 0


def get_event_cache_all(context: dict) -> None:
    """Get and update event cache data for the given context.

    Args:
        context: Context dictionary containing run information.
    """
    # Get cache key for the current run
    cache_key = get_event_cache_all_key(context["run"])

    # Try to retrieve cached result
    cached_result = cache.get(cache_key)
    if cached_result is None:
        # Initialize cache if not found
        cached_result = init_event_cache_all(context)
        cache.set(cache_key, cached_result, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    # Update context with cached data
    context.update(cached_result)


def clear_run_cache_and_media(run: Run) -> None:
    """Clear cache and delete all media files for a run."""
    reset_event_cache_all(run)
    media_directory_path = run.get_media_filepath()
    delete_all_in_path(media_directory_path)


def reset_event_cache_all(run):
    cache_key = get_event_cache_all_key(run)
    cache.delete(cache_key)


def update_character_fields(instance, character_data: dict) -> None:
    """Updates character fields with event-specific data if character features are enabled.

    Args:
        instance: Event instance with event_id attribute
        character_data: Dictionary to update with character element fields
    """
    # Check if character features are enabled for this event
    enabled_features = get_event_features(instance.event_id)
    if "character" not in enabled_features:
        return

    # Build context and update data with character element fields
    template_context = {"features": enabled_features, "event": instance.event}
    character_data.update(get_character_element_fields(template_context, instance.pk, only_visible=False))


def update_event_cache_all(run: Run, instance: BaseModel) -> None:
    """Update the event cache for all data based on the instance type.

    This function updates cached event data by checking the instance type
    and calling the appropriate update function. It handles Faction, Character,
    and RegistrationCharacterRel instances.

    Args:
        run: The event run object containing event information
        instance: The model instance that triggered the cache update

    Returns:
        None
    """
    # Get the cache key for the event and retrieve cached data
    cache_key = get_event_cache_all_key(run)
    cached_result = cache.get(cache_key)

    # Exit early if no cached data exists
    if cached_result is None:
        return

    # Update cache based on instance type - Faction updates
    if isinstance(instance, Faction):
        update_event_cache_all_faction(instance, cached_result)

    # Character updates include both character data and faction refresh
    if isinstance(instance, Character):
        update_event_cache_all_character(instance, cached_result, run)
        get_event_cache_factions({"event": run.event}, cached_result)

    # Registration-character relationship updates
    if isinstance(instance, RegistrationCharacterRel):
        update_event_cache_all_character_reg(instance, cached_result, run)

    # Save the updated cache data with 1-day timeout
    cache.set(cache_key, cached_result, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


def update_event_cache_all_character_reg(character_registration, cache_result: dict, event_run) -> None:
    """Updates character registration cache data for an event.

    Args:
        character_registration: Character registration instance
        cache_result: Result dictionary to update with character data
        event_run: Event run instance
    """
    # Get character from registration instance
    character = character_registration.character

    # Generate character display data
    character_display_data = character.show()

    # Search and update player information
    search_player(
        character, character_display_data, {"run": event_run, "assignments": {character.number: character_registration}}
    )

    # Initialize character entry if not exists
    if character.number not in cache_result["chars"]:
        cache_result["chars"][character.number] = {}

    # Update character data in result
    cache_result["chars"][character.number].update(character_display_data)


def update_event_cache_all_character(instance: Character, res: dict, run: Run) -> None:
    """Update character cache data for event display.

    Args:
        instance: Character instance to update
        res: Result dictionary to store character data
        run: Event run context
    """
    # Generate character display data for the specific run
    character_display_data = instance.show(run)

    # Update character fields with the generated data
    update_character_fields(instance, character_display_data)

    # Search and update player information
    search_player(instance, character_display_data, {"run": run})

    # Initialize character entry in results if not exists
    if instance.number not in res["chars"]:
        res["chars"][instance.number] = {}

    # Update the character data in results
    res["chars"][instance.number].update(character_display_data)


def update_event_cache_all_faction(instance, res):
    faction_data = instance.show()
    if instance.number in res["factions"]:
        res["factions"][instance.number].update(faction_data)
    else:
        res["factions"][instance.number] = faction_data


def has_different_cache_values(instance: object, previous_instance: object, attributes_to_check: list) -> bool:
    """Check if any attributes in attributes_to_check have different values between instance and previous_instance.

    Args:
        instance: Current object instance
        previous_instance: Previous object instance
        attributes_to_check: List of attribute names to compare

    Returns:
        True if any attribute differs, False otherwise
    """
    for attribute_name in attributes_to_check:
        # Get attribute values from both instances
        previous_value = getattr(previous_instance, attribute_name)
        current_value = getattr(instance, attribute_name)

        # Return immediately if values differ
        if previous_value != current_value:
            return True

    return False


def update_member_event_character_cache(instance: Member) -> None:
    """Update event cache for all active character registrations of a member."""
    # Get all active character registrations for this member
    active_character_registrations = RegistrationCharacterRel.objects.filter(
        reg__member_id=instance.id, reg__cancellation_date__isnull=True
    )
    active_character_registrations = active_character_registrations.select_related("character", "reg", "reg__run")

    # Update cache for each character registration
    for registration_character_rel in active_character_registrations:
        update_event_cache_all(registration_character_rel.reg.run, registration_character_rel)


def on_character_pre_save_update_cache(char: Character) -> None:
    """Update or clear character cache before save based on changed fields."""
    # Clear cache for new characters (no primary key yet)
    if not char.pk:
        clear_event_cache_all_runs(char.event)
        return

    try:
        # Get previous version to compare changes
        prev = Character.objects.get(pk=char.pk)

        # Check if cache-affecting fields changed
        lst = ["player_id", "mirror_id"]
        if has_different_cache_values(char, prev, lst):
            clear_event_cache_all_runs(char.event)
        else:
            # Update cache with new character data
            update_event_cache_all_runs(char.event, char)
    except Exception:
        # Fallback: clear cache on any error
        clear_event_cache_all_runs(char.event)


def on_character_factions_m2m_changed(sender, **kwargs) -> None:
    """Clear event cache when character factions change."""
    # Check if action is one that affects the relationship
    action = kwargs.pop("action", None)
    if action not in ["post_add", "post_remove", "post_clear"]:
        return

    # Get the faction instance and clear related event cache
    instance: Optional[Faction] = kwargs.pop("instance", None)
    clear_event_cache_all_runs(instance.event)


def on_faction_pre_save_update_cache(instance: Faction) -> None:
    """Handle faction pre-save signal to update related caches.

    Clears or updates event caches based on which faction fields have changed.
    For new factions or type changes, clears all event caches. For name/teaser
    changes, updates caches with the modified faction data.

    Args:
        instance: The Faction instance being saved.
    """
    # Handle new faction creation - clear all event caches
    if not instance.pk:
        clear_event_cache_all_runs(instance.event)
        return

    # Get the previous version from database for comparison
    prev = Faction.objects.get(pk=instance.pk)

    # Check if faction type changed - requires full cache clear
    lst = ["typ"]
    if has_different_cache_values(instance, prev, lst):
        clear_event_cache_all_runs(instance.event)

    # Check if display fields changed - update caches with new data
    lst = ["name", "teaser"]
    if has_different_cache_values(instance, prev, lst):
        update_event_cache_all_runs(instance.event, instance)


def on_quest_type_pre_save_update_cache(instance: QuestType) -> None:
    """Clear event cache when QuestType changes that affect caching."""
    # Handle new QuestType creation
    if not instance.pk:
        clear_event_cache_all_runs(instance.event)
        return

    # Check if cache-affecting fields have changed
    lst = ["name"]
    prev = QuestType.objects.get(pk=instance.pk)
    if has_different_cache_values(instance, prev, lst):
        clear_event_cache_all_runs(instance.event)


def on_quest_pre_save_update_cache(instance: Quest) -> None:
    """Clear event cache when quest fields change."""
    # Clear cache for new quests
    if not instance.pk:
        clear_event_cache_all_runs(instance.event)
        return

    # Check if cache-relevant fields have changed
    lst = ["name", "teaser", "typ_id"]
    prev = Quest.objects.get(pk=instance.pk)
    if has_different_cache_values(instance, prev, lst):
        clear_event_cache_all_runs(instance.event)


def on_trait_pre_save_update_cache(instance: Trait) -> None:
    """Clear event cache when trait changes affect cached data.

    Args:
        instance: The trait instance being saved.
    """
    # Clear cache for new traits
    if not instance.pk:
        clear_event_cache_all_runs(instance.event)
        return

    # Check if cache-relevant fields have changed
    lst = ["name", "teaser", "quest_id"]
    prev = Trait.objects.get(pk=instance.pk)
    if has_different_cache_values(instance, prev, lst):
        clear_event_cache_all_runs(instance.event)


def update_event_cache_all_runs(event, instance):
    for run in event.runs.all():
        update_event_cache_all(run, instance)


def reset_character_registration_cache(character) -> None:
    """Reset cache for character's registration and run."""
    # Save registration to trigger cache invalidation
    if character.reg:
        character.reg.save()
    # Clear run-level cache and media
    clear_run_cache_and_media(character.reg.run)


def clear_event_cache_all_runs(event: Event) -> None:
    """Clear cache and media for all runs of event, children, siblings, and parent."""
    # Clear cache for all runs of the current event
    for run in event.runs.all():
        clear_run_cache_and_media(run)

    # Clear cache for runs of child events
    for child_event in Event.objects.filter(parent=event).prefetch_related("runs"):
        for run in child_event.runs.all():
            clear_run_cache_and_media(run)

    if event.parent:
        # Clear cache for runs of sibling events
        for sibling_event in Event.objects.filter(parent=event.parent).prefetch_related("runs"):
            for run in sibling_event.runs.all():
                clear_run_cache_and_media(run)

        # Clear cache for runs of parent event
        for run in event.parent.runs.all():
            clear_run_cache_and_media(run)
