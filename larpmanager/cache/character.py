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

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.cache.config import get_event_config
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.fields import visible_writing_fields
from larpmanager.cache.registration import search_player
from larpmanager.models.casting import AssignmentTrait, Quest, QuestType, Trait
from larpmanager.models.event import Event, Run
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    WritingAnswer,
    WritingChoice,
)
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import Character, Faction, FactionType

if TYPE_CHECKING:
    from larpmanager.models.base import BaseModel
    from larpmanager.models.member import Member


def delete_all_in_path(path: str) -> None:
    """Recursively delete all contents within a directory path.

    Args:
        path (str): Directory path to clean

    """
    path_obj = Path(path)
    if path_obj.exists():
        # Remove all contents inside the path
        for entry in path_obj.iterdir():
            if entry.is_file() or entry.is_symlink():
                entry.unlink()
            elif entry.is_dir():
                shutil.rmtree(entry)


def get_event_cache_all_key(event_run: Run) -> str:
    """Generate cache key for event data."""
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
    # Character number to character id mapping
    cache_result["char_mapping"] = {}

    # Check if mirror feature is enabled for character filtering
    is_mirror_enabled = "mirror" in context["features"]

    # Build assignments mapping from character number to registration relation
    context["assignments"] = {}
    registration_query = RegistrationCharacterRel.objects.filter(registration__run=context["run"])
    for relation in registration_query.select_related("character", "registration", "registration__member"):
        context["assignments"][relation.character.number] = relation

    # Get event configuration for hiding uncasted characters
    hide_uncasted_characters = get_event_config(
        context["event"].id, "gallery_hide_uncasted_characters", default_value=False, context=context
    )

    # Get list of assigned character IDs for mirror filtering
    assigned_character_ids = RegistrationCharacterRel.objects.filter(registration__run=context["run"]).values_list(
        "character_id",
        flat=True,
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
        if hide_uncasted_characters and not character_data["player_uuid"]:
            character_data["hide"] = True

        character_number = int(character_data["number"])
        cache_result["chars"][character_number] = character_data
        cache_result["char_mapping"][character_number] = character.id

    # Add field data to the cache
    get_event_cache_fields(context, cache_result)

    # Set the maximum character number for reference
    if cache_result["chars"]:
        cache_result["max_ch_number"] = max(cache_result["chars"], key=int)
    else:
        cache_result["max_ch_number"] = 0

    return cache_result


def get_event_cache_fields(context: dict, res: dict, *, only_visible: bool = True) -> None:
    """Retrieve and cache writing fields for characters in an event.

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
    fields_data = visible_writing_fields(context, QuestionApplicable.CHARACTER, only_visible=only_visible)
    if "questions" not in fields_data:
        return

    # Extract question IDs from context for database filtering
    question_uuids = fields_data["questions"].keys()

    # Query the Character table to get id -> number mapping for the event
    character_id_mapping = dict(context["event"].get_elements(Character).values_list("id", "number"))

    # Retrieve and process multiple choice answers for characters
    # Each choice can have multiple options selected per question
    choice_answers = WritingChoice.objects.filter(question__uuid__in=question_uuids)
    for element_id, question_uuid, option_uuid in choice_answers.values_list(
        "element_id", "question__uuid", "option__uuid"
    ).order_by("question__order", "option__order"):
        # Skip if character not in current event mapping
        if element_id not in character_id_mapping:
            continue

        # Map database values to result structure
        character_index = character_id_mapping[element_id]
        question = str(question_uuid)
        value = str(option_uuid)

        # Initialize fields list for question if not exists, then append choice
        if character_index not in res["chars"]:
            continue

        fields = res["chars"][character_index]["fields"]
        if question not in fields:
            fields[question] = []
        fields[question].append(value)

    # Retrieve and process text answers for characters
    # Each text answer is a single value per question
    text_answers = WritingAnswer.objects.filter(question__uuid__in=question_uuids)
    for element_id, question_uuid, text_value in text_answers.values_list("element_id", "question__uuid", "text"):
        # Skip if character not in current event mapping
        if element_id not in character_id_mapping:
            continue

        # Map database values to result structure
        character_index = character_id_mapping[element_id]

        question = str(question_uuid)
        value = text_value

        # Set text answer directly (single value, not list)
        if character_index not in res["chars"]:
            continue
        res["chars"][character_index]["fields"][question] = value


def get_character_element_fields(
    context: dict,
    character_id: int,
    *,
    only_visible: bool = True,
) -> dict:
    """Get writing element fields for a character."""
    return get_writing_element_fields(
        context,
        "character",
        QuestionApplicable.CHARACTER,
        character_id,
        only_visible=only_visible,
    )


def get_writing_element_fields(
    context: dict,
    feature_name: str,
    applicable: str,
    element_id: int,
    *,
    only_visible: bool = True,
) -> dict[str, dict]:
    """Get writing fields for a specific element with visibility filtering."""
    batch_results = get_writing_element_fields_batch(
        context,
        feature_name,
        applicable,
        [element_id],
        only_visible=only_visible,
    )
    return batch_results.get(
        element_id, {"questions": context.get("questions", {}), "options": context.get("options", {}), "fields": {}}
    )


def get_writing_element_fields_batch(
    context: dict,
    feature_name: str,
    applicable: str,
    element_ids: list[int],
    *,
    only_visible: bool = True,
) -> dict[int, dict[str, dict]]:
    """Get writing fields for multiple elements with visibility filtering.

    Args:
        context: Context dictionary containing event and configuration data including
             'questions', 'options', and visibility settings
        feature_name: Name of the feature (e.g., 'character', 'faction') used
                     for determining visibility key
        applicable: QuestionApplicable enum value defining question scope
        element_ids: List of element IDs to retrieve fields for
        only_visible: Whether to include only visible fields. Defaults to True

    Returns:
        Dictionary mapping element_id to:
            - questions: Available questions from context
            - options: Available options from context
            - fields: Mapping of question_id to field values (text or list of option_ids)

    """
    # Apply visibility filtering to populate context with visible fields
    fields_data = visible_writing_fields(context, applicable, only_visible=only_visible)

    # Filter questions based on visibility configuration
    # Only include questions that are explicitly shown or when show_all is enabled
    visible_question_ids = []
    for question_uuid in fields_data["questions"]:
        question_config_key = str(question_uuid)
        # Skip questions not marked as visible unless showing all
        if "show_all" not in context and question_config_key not in context.get(f"show_{feature_name}", {}):
            continue
        visible_question_ids.append(question_uuid)

    # Initialize results dictionary for all elements
    results = {element_id: {} for element_id in element_ids}

    # Retrieve text answers for all elements
    # Query WritingAnswer model for text-based responses
    text_answers_query = WritingAnswer.objects.filter(
        element_id__in=element_ids,
        question__uuid__in=visible_question_ids,
        question__typ__in=[BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, BaseQuestionType.EDITOR],
    ).select_related("question")
    for element_id, question_uuid, text in text_answers_query.values_list("element_id", "question__uuid", "text"):
        results[element_id][question_uuid] = text

    # Retrieve choice answers for all elements
    # Group multiple choice options into lists per question
    choice_answers_query = WritingChoice.objects.filter(
        element_id__in=element_ids,
        question__uuid__in=visible_question_ids,
        question__typ__in=[BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE],
    ).select_related("question", "option")
    for element_id, question_uuid, option_uuid in choice_answers_query.values_list(
        "element_id", "question__uuid", "option__uuid"
    ):
        # Initialize list if question not yet in fields
        if question_uuid not in results[element_id]:
            results[element_id][question_uuid] = []
        results[element_id][question_uuid].append(option_uuid)

    # Return full format for each element
    return {
        element_id: {
            "questions": fields_data["questions"],
            "options": fields_data["options"],
            "fields": fields,
        }
        for element_id, fields in results.items()
    }


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

    result["fac_mapping"] = {}

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
        if character_data["hide"]:
            continue

        if 0 in character_data.get("factions", {}):
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
    for faction in context["event"].get_elements(Faction).order_by("order"):
        _process_faction_cache(faction, result)


def _process_faction_cache(faction: Faction, result: dict) -> None:
    """Process a faction adding its values into the result cache."""
    # Get faction display data
    faction_data = faction.show_red()
    faction_data["characters"] = []
    # Find characters belonging to this faction
    for character_number, character_data in result["chars"].items():
        if character_data["hide"]:
            continue

        if faction_data["number"] in character_data["factions"]:
            faction_data["characters"].append(character_number)

    # Skip factions with no characters
    if not faction_data["characters"]:
        return

    # Add faction to results and organize by type
    result["factions"][faction.number] = faction_data
    if faction.typ not in result["factions_typ"]:
        result["factions_typ"][faction.typ] = []
    result["factions_typ"][faction.typ].append(faction.number)
    result["fac_mapping"][faction.number] = faction.id


def _build_trait_relationships(event: Event) -> dict:
    """Build mapping of trait relationships (traits that reference other traits).

    Args:
        event: Event to get traits for

    Returns:
        Dictionary mapping trait numbers to lists of related trait numbers
    """
    trait_relationships = {}
    for trait in Trait.objects.filter(event=event).prefetch_related("traits"):
        trait_relationships[trait.number] = []
        # Add related trait numbers, excluding self-references
        for associated_trait in trait.traits.all():
            if associated_trait.number == trait.number:
                continue
            trait_relationships[trait.number].append(associated_trait.number)
    return trait_relationships


def _find_character(chars: dict, member_uuid: str) -> dict | None:
    """Find a character in the cache by member UUID."""
    for character in chars.values():
        if character.get("player_uuid") == member_uuid:
            return character
    return None


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
    trait_relationships = _build_trait_relationships(context["event"])

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
        found_character = _find_character(res["chars"], assignment_trait.member.uuid)

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


def reset_event_cache_all(run: Run) -> None:
    """Delete the event cache for the given run."""
    cache_key = get_event_cache_all_key(run)
    cache.delete(cache_key)


def update_character_fields(character: Character, character_data: dict) -> None:
    """Update character fields with event-specific data if character features are enabled."""
    # Check if character features are enabled for this event
    enabled_features = get_event_features(character.event_id)
    if "character" not in enabled_features:
        return

    # Build context and update data with character element fields
    template_context = {"features": enabled_features, "event": character.event}
    character_data.update(get_character_element_fields(template_context, character.pk, only_visible=False))


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


def update_event_cache_all_character_reg(
    relation: RegistrationCharacterRel, cache_result: dict, event_run: Any
) -> None:
    """Update character registration cache data for an event.

    Args:
        relation: Character registration relation
        cache_result: Result dictionary to update with character data
        event_run: Event run instance

    """
    # Get character from relation instance
    character = relation.character

    # Only update cache if character belongs to this event
    if character.event_id != event_run.event_id:
        return

    # Generate character display data
    character_display_data = character.show()

    # Search and update player information
    search_player(
        character,
        character_display_data,
        {"run": event_run, "assignments": {character.number: relation}},
    )

    # Initialize character entry if not exists
    if character.number not in cache_result["chars"]:
        cache_result["chars"][character.number] = {}

    # Update character data in result
    cache_result["chars"][character.number].update(character_display_data)

    # Update char_mapping to keep character number -> id mapping in sync
    if "char_mapping" not in cache_result:
        cache_result["char_mapping"] = {}
    cache_result["char_mapping"][character.number] = character.id


def update_event_cache_all_character(instance: Character, res: dict, run: Run) -> None:
    """Update character cache data for event display.

    Args:
        instance: Character instance to update
        res: Result dictionary to store character data
        run: Event run context

    """
    # Only update cache if character belongs to this event
    if instance.event_id != run.event_id:
        return

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

    # Update char_mapping to keep character number -> id mapping in sync
    if "char_mapping" not in res:
        res["char_mapping"] = {}
    res["char_mapping"][instance.number] = instance.id


def update_event_cache_all_faction(instance: Faction, res: dict[str, dict]) -> None:
    """Update or add faction data in the cache result dictionary."""
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
        registration__member_id=instance.id,
        registration__cancellation_date__isnull=True,
    )
    active_character_registrations = active_character_registrations.select_related(
        "character", "registration", "registration__run"
    )

    # Update cache for each character registration
    for relation in active_character_registrations:
        update_event_cache_all(relation.registration.run, relation)


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
        # Note: number is included because char_mapping uses number as key
        lst = ["player_id", "mirror_id", "number"]
        if has_different_cache_values(char, prev, lst):
            clear_event_cache_all_runs(char.event)
        else:
            # Update cache with new character data
            update_event_cache_all_runs(char.event, char)
    except ObjectDoesNotExist:
        # Fallback: clear cache if character not found
        clear_event_cache_all_runs(char.event)


def on_character_factions_m2m_changed(sender: type, **kwargs: Any) -> None:  # noqa: ARG001
    """Clear event cache when character factions change."""
    # Check if action is one that affects the relationship
    action = kwargs.pop("action", None)
    if action not in ["post_add", "post_remove", "post_clear"]:
        return

    # Get the faction instance and clear related event cache
    instance: Faction | None = kwargs.pop("instance", None)
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


def update_event_cache_all_runs(event: Event, instance: BaseModel) -> None:
    """Update event cache for all runs of the given event."""
    for run in event.runs.all():
        update_event_cache_all(run, instance)


def reset_character_registration_cache(rcr: RegistrationCharacterRel) -> None:
    """Reset cache for character's registration and run."""
    # Save registration to trigger cache invalidation
    if rcr.registration:
        rcr.registration.save()
    # Clear run-level cache and media
    clear_run_cache_and_media(rcr.registration.run)


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
