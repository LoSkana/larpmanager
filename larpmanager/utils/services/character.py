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

from django.http import Http404

from larpmanager.cache.character import get_character_element_fields, get_event_cache_all
from larpmanager.cache.config import get_event_config
from larpmanager.cache.fields import visible_writing_fields
from larpmanager.cache.question import get_cached_writing_questions
from larpmanager.models.casting import Trait
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    WritingAnswer,
    WritingChoice,
)
from larpmanager.models.miscellanea import PlayerRelationship
from larpmanager.models.utils import strip_tags
from larpmanager.models.writing import Character, FactionType, PlotCharacterRel, Relationship
from larpmanager.utils.core.common import get_element
from larpmanager.utils.core.exceptions import NotFoundError
from larpmanager.utils.services.event import has_access_character
from larpmanager.utils.services.experience import add_char_addit

logger = logging.getLogger(__name__)


def get_character_relationships(context: dict, *, restrict: bool = True) -> None:
    """Get character relationships with faction and player input data.

    Retrieves and processes character relationships from both system-defined
    relationships and player-inputted relationships. Updates the context with
    formatted relationship data including faction information and text content.

    Args:
        context: Context dictionary containing character, event, run, chars, and factions data.
            Must include 'character', 'event', 'run', and may include 'chars', 'factions'.
        restrict: Whether to filter out relationships with empty text content.
            Defaults to True.

    Returns:
        None: Function modifies context in-place, adding 'rel' list and 'pr' dict.

    Side Effects:
        - Updates context['rel'] with sorted list of relationship data
        - Updates context['pr'] with player relationship objects

    """
    relationship_text_mapping = {}
    character_data_mapping = {}

    _build_relationships_mappings(context, character_data_mapping, relationship_text_mapping)

    _build_player_relationships_mappings(context, character_data_mapping, relationship_text_mapping)

    # Build final relationship list sorted by text length
    context["rel"] = []
    for character_uuid in sorted(
        relationship_text_mapping,
        key=lambda k: len(relationship_text_mapping[k]),
        reverse=True,
    ):
        # Skip if character data not found
        if character_uuid not in character_data_mapping:
            logger.debug(
                "Character UUID %s not found in data keys: %s...",
                character_uuid,
                list(character_data_mapping.keys())[:5],
            )
            continue

        relationship_entry = character_data_mapping[character_uuid]
        # Filter empty relationships if restrict is enabled
        if restrict and len(relationship_text_mapping[character_uuid]) == 0:
            continue

        # Add relationship text and calculate font size based on content length
        relationship_entry["text"] = relationship_text_mapping[character_uuid]
        relationship_entry["font_size"] = int(100 - ((len(relationship_entry["text"]) / 50) * 4))
        context["rel"].append(relationship_entry)


def _build_player_relationships_mappings(
    context: dict, character_data_mapping: dict, relationship_text_mapping: dict
) -> None:
    """Build mappings for player-inputted relationships and store in context.

    Processes PlayerRelationship objects for the current player's character,
    overriding system relationships where applicable and adding character data
    for relationships that don't exist in the system.

    Args:
        context: Context dictionary containing character, run, and factions data.
            Must include 'char' with 'player_id', and 'run'. Updates context['pr']
            with player relationship objects.
        character_data_mapping: Dictionary mapping character UUIDs to character data.
            Updated in-place with character data for any new relationships.
        relationship_text_mapping: Dictionary mapping character UUIDs to relationship
            text. Updated in-place, overriding system relationships with player input.

    Side Effects:
        - Updates character_data_mapping with new character data if needed
        - Updates relationship_text_mapping with player-inputted text
        - Sets context['pr'] with player relationships mapping by UUID

    """
    player_relationships_mapping = {}
    # Update with player-inputted relationship data
    if "player_id" in context["char"]:
        for player_relationship in PlayerRelationship.objects.select_related(
            "target", "registration", "registration__member"
        ).filter(
            registration__member_id=context["char"]["player_id"],
            registration__run=context["run"],
        ):
            target_uuid = str(player_relationship.target.uuid)
            player_relationships_mapping[target_uuid] = player_relationship
            # Player input overrides system relationships
            relationship_text_mapping[target_uuid] = player_relationship.text

            # Add character data if not already present (fixes bug where player relationships
            # with characters that don't have system relationships are lost)
            if target_uuid not in character_data_mapping:
                character_data = player_relationship.target.show(context["run"])
                # Build faction list for display purposes
                character_data["factions_list"] = []
                for faction_number in character_data["factions"]:
                    if not faction_number or faction_number not in context["factions"]:
                        continue
                    faction_data = context["factions"][faction_number]
                    # Skip empty names or secret factions
                    if not faction_data["name"] or faction_data["typ"] == FactionType.SECRET:
                        continue
                    character_data["factions_list"].append(faction_data["name"])
                character_data["factions_list"] = ", ".join(character_data["factions_list"])
                character_data_mapping[target_uuid] = character_data

    # Store player relationships for additional processing
    context["pr"] = player_relationships_mapping


def _build_relationships_mappings(context: dict, character_data_mapping: dict, relationship_text_mapping: dict) -> None:
    """Build mappings for system-defined character relationships.

    Processes Relationship objects for the source character, retrieves target
    character data with faction information, and populates the mapping dictionaries.
    Uses character UUIDs as keys for security.

    Args:
        context: Context dictionary containing character, event, run, and factions data.
            Must include 'character' (source), 'event', 'run', and may include cached
            'chars' data and 'factions' for faction lookups.
        character_data_mapping: Dictionary to populate with character UUID to character
            data mappings. Updated in-place.
        relationship_text_mapping: Dictionary to populate with character UUID to
            relationship text mappings. Updated in-place.

    Side Effects:
        - Updates character_data_mapping with character data for all relationship targets
        - Updates relationship_text_mapping with relationship text for all targets
        - Each character data includes a 'factions_list' field with comma-separated
          faction names (excluding secret factions)

    """
    # Process character relationships from the source
    queryset = Relationship.objects.values_list("target__number", "text").filter(source=context["character"])
    relationship_rows = list(queryset)

    # Collect numbers of characters not already in cache
    cached_chars = context.get("chars", {})
    missing_numbers = [num for num, _ in relationship_rows if num not in cached_chars]

    # Bulk fetch missing characters
    bulk_fetched: dict = {}
    if missing_numbers:
        for target_character in Character.objects.select_related("event", "player").filter(
            event=context["event"],
            number__in=missing_numbers,
        ):
            bulk_fetched[target_character.number] = target_character

    for target_character_number, relationship_text in relationship_rows:
        # Check if character data is already cached in context
        if target_character_number in cached_chars:
            character_data = cached_chars[target_character_number]
        elif target_character_number in bulk_fetched:
            character_data = bulk_fetched[target_character_number].show(context["run"])
        else:
            continue

        # Build faction list for display purposes
        character_data["factions_list"] = []
        for faction_number in character_data["factions"]:
            if not faction_number or faction_number not in context["factions"]:
                continue
            faction_data = context["factions"][faction_number]
            # Skip empty names or secret factions
            if not faction_data["name"] or faction_data["typ"] == FactionType.SECRET:
                continue
            character_data["factions_list"].append(faction_data["name"])

        # Join faction names and store character data
        character_data["factions_list"] = ", ".join(character_data["factions_list"])
        character_data_mapping[character_data["uuid"]] = character_data
        relationship_text_mapping[character_data["uuid"]] = relationship_text


def get_character_sheet(context: dict) -> None:
    """Build complete character sheet data for display."""
    context["sheet_char"] = context["character"].show_complete()

    get_character_sheet_fields(context)

    get_character_sheet_factions(context)

    get_character_sheet_plots(context)

    get_character_sheet_questbuilder(context)

    get_character_sheet_speedlarp(context)

    get_character_sheet_prologue(context)

    get_character_sheet_px(context)

    get_character_sheet_inventory(context)


def get_character_sheet_inventory(context: dict) -> None:
    """Populate the character sheet with inventory summary data."""
    if "inventory" not in context["features"]:
        return

    context["sheet_inventory"] = context["character"].inventory.all()


def get_character_sheet_px(context: dict) -> None:
    """Populate the character sheet with ability data grouped by type.

    Args:
        context: Context dictionary containing character data and features.
             Expected to have 'features' dict and 'character' object with
             px_ability_list attribute.

    Returns:
        None: Modifies context dictionary in-place by adding 'sheet_abilities'.

    """
    # Check if px feature is enabled before processing
    if "px" not in context["features"]:
        return

    event_id = context["character"].event_id
    context["px_auto_buy"] = get_event_config(event_id, "px_auto_buy", default_value=False)

    # Initialize abilities dictionary for grouping by type
    context["sheet_abilities"] = {}

    # Group abilities by their type name
    for ability in context["character"].px_ability_list.select_related("typ").all():
        # Ensure ability has valid type and name before processing
        if ability.typ and ability.typ.name and ability.typ.name not in context["sheet_abilities"]:
            context["sheet_abilities"][ability.typ.name] = []
        context["sheet_abilities"][ability.typ.name].append(ability)

    # Add additional character data to context
    add_char_addit(context["character"])


def get_character_sheet_prologue(context: dict) -> None:
    """Add character prologues to context if prologue feature is enabled."""
    if "prologue" not in context["features"]:
        return

    # Initialize empty list for sheet prologues
    context["sheet_prologues"] = []

    # Process each prologue in order and add complete data
    for prologue in context["character"].prologues_list.order_by("typ__number"):
        prologue.data = prologue.show_complete()
        context["sheet_prologues"].append(prologue)


def get_character_sheet_speedlarp(context: dict) -> None:
    """Populate context with speedlarp sheet data if feature is enabled."""
    if "speedlarp" not in context["features"]:
        return

    # Initialize speedlarp sheets list
    context["sheet_speedlarps"] = []

    # Process each speedlarp ordered by type
    for speedlarp in context["character"].speedlarps_list.order_by("typ"):
        speedlarp.data = speedlarp.show_complete()
        context["sheet_speedlarps"].append(speedlarp)


def get_character_sheet_questbuilder(context: dict) -> None:
    """Build character sheet with quest and trait relationships.

    Args:
        context: Context dictionary with character, quest, and trait data

    Side effects:
        Updates context with sheet_traits containing complete trait and quest information

    """
    if "questbuilder" not in context["features"]:
        return

    if "char" not in context:
        return

    if "player_uuid" not in context["char"] or "traits" not in context["char"]:
        return

    context["sheet_traits"] = []
    trait_numbers = [context["traits"][tn]["number"] for tn in context["char"]["traits"]]

    # Bulk fetch all needed traits
    trait_objects_by_number = {
        t.number: t
        for t in Trait.objects.select_related("quest").filter(
            event=context["event"],
            number__in=trait_numbers,
        )
    }

    for trait_number in context["char"]["traits"]:
        trait_element = context["traits"][trait_number]
        trait_object = trait_objects_by_number.get(trait_element["number"])
        if not trait_object:
            continue
        trait_data = trait_object.show_complete()
        trait_data["quest"] = trait_object.quest.show_complete()

        trait_data["rels"] = []
        for related_trait_number in trait_element["traits"]:
            if related_trait_number not in context["traits"]:
                continue
            character_number = context["traits"][related_trait_number]["char"]
            trait_data["rels"].append(context["chars"][character_number])

        context["sheet_traits"].append(trait_data)


def get_character_sheet_plots(context: dict) -> None:
    """Add character plot information to context if plot feature is enabled."""
    if "plot" not in context["features"]:
        return

    context["sheet_plots"] = []

    # Get all plot relations for the character ordered by sequence
    plot_relations = PlotCharacterRel.objects.select_related("plot").filter(character=context["character"])

    for plot_relation in plot_relations.order_by("order"):
        # Start with the base plot text
        combined_text = plot_relation.plot.text

        # Add separator and additional text if both exist
        if combined_text and plot_relation.text:
            combined_text += "<hr />"
        if plot_relation.text:
            combined_text += plot_relation.text

        # Add plot entry to context
        context["sheet_plots"].append({"name": plot_relation.plot.name, "text": combined_text})


def get_character_sheet_factions(context: dict, *, only_visible: bool = False) -> None:
    """Retrieve and process faction data for character sheet display.

    Fetches factions associated with a character, along with their writing answers
    and choices, then adds the processed data to the context for rendering.

    Args:
        context: Context dictionary containing character, event, features, and other
             rendering data. Modified in-place to add 'sheet_factions' key.
        only_visible: Whether to include only visible fields. Defaults to False.

    Returns:
        None: Function modifies context dictionary in-place.

    """
    # Early return if faction feature is not enabled
    if "faction" not in context["features"]:
        return

    # If we show all the factions (player / staffer)
    all_factions = {}
    if not only_visible:
        faction_event = context["event"].get_class_parent("faction")
        faction_ids = []
        for faction in context["character"].factions_list.filter(event=faction_event).order_by("order"):
            all_factions[faction.id] = faction.show_complete()
    # Show only public
    else:
        faction_numbers = context["char"].get("factions")
        for faction_number in faction_numbers:
            faction_id = context.get("fac_mapping", {}).get(faction_number)
            all_factions[faction_id] = context["factions"].get(faction_number)

    context["sheet_factions"] = []

    # Prepare writing fields query data for faction-applicable questions
    fields_data = visible_writing_fields(context, QuestionApplicable.FACTION, only_visible=only_visible)

    # Build comprehensive answer mapping: faction_id -> {question_id -> text/choices}
    faction_ids = list(all_factions.keys())
    faction_answers_map = _get_factions_answers_choices(context, fields_data, faction_ids)

    # Process each faction and prepare display data
    for faction_id, faction_data in all_factions.items():
        if not faction_data:
            continue

        # Merge in writing fields from pre-fetched bulk data
        faction_writing_fields = faction_answers_map.get(faction_id, {})
        faction_data.update(
            {
                "questions": fields_data.get("questions", {}),
                "options": fields_data.get("options", {}),
                "fields": faction_writing_fields,
            },
        )

        # Add processed faction data to context
        context["sheet_factions"].append(faction_data)


def _get_factions_answers_choices(context: dict, fields_data: dict, faction_ids: list) -> dict:
    """Build comprehensive answer mapping: faction_id -> {question_id -> text/choices}."""
    # Determine which questions should be visible based on configuration
    visible_question_ids = []
    if "questions" in fields_data:
        for question_id in fields_data["questions"]:
            question_config_key = str(question_id)
            # Skip questions that are not configured to show for factions
            if "show_all" not in context and question_config_key not in context.get("show_faction", {}):
                continue
            visible_question_ids.append(question_id)

    faction_answers_map = {}
    if visible_question_ids:
        # Bulk fetch all writing answers for performance
        for faction_id, question__uuid, answer_text in WritingAnswer.objects.filter(
            element_id__in=faction_ids,
            question__uuid__in=visible_question_ids,
        ).values_list("element_id", "question__uuid", "text"):
            # Initialize nested dictionary structure as needed
            if faction_id not in faction_answers_map:
                faction_answers_map[faction_id] = {}
            faction_answers_map[faction_id][question__uuid] = answer_text

        # Bulk fetch all writing choices and group by faction and question
        for faction_id, question__uuid, option_id in WritingChoice.objects.filter(
            element_id__in=faction_ids,
            question__uuid__in=visible_question_ids,
        ).values_list("element_id", "question__uuid", "option_id"):
            # Initialize nested dictionary and list structures as needed
            if faction_id not in faction_answers_map:
                faction_answers_map[faction_id] = {}
            if question__uuid not in faction_answers_map[faction_id]:
                faction_answers_map[faction_id][question__uuid] = []
            faction_answers_map[faction_id][question__uuid].append(option_id)
    return faction_answers_map


def get_character_sheet_fields(context: dict) -> None:
    """Update character sheet context with character element fields."""
    # Check if character feature is enabled
    if "character" not in context["features"]:
        return

    # Update sheet character context with element fields
    character_id = _get_character_cache_id(context)
    context["sheet_char"].update(get_character_element_fields(context, character_id, only_visible=False))


def get_char_check(
    request: Any,
    context: dict,
    character_uuid: str,
    *,
    restrict_non_owners: bool = False,
    bypass_access_checks: bool = False,
) -> None:
    """Get character with access control checks.

    Retrieves a character from the context and performs various access control
    checks based on user permissions and character visibility settings.

    Args:
        request: Django HTTP request object containing user and session data
        context: Context dictionary containing cached character and event data
        character_uuid: Character uuid to retrieve from the character cache
        restrict_non_owners: Whether to apply strict visibility restrictions for non-owners
        bypass_access_checks: Whether to bypass all access checks (admin override)

    Returns:
        None: Modifies context in-place, adding 'char' and potentially 'check' keys

    Raises:
        NotFoundError: If character not found in cache or is hidden from user
        Http404: If character access is restricted and user lacks permission

    """
    # Load all event and character data into context cache
    get_event_cache_all(context)

    # Set the current character in context for further processing
    for char in context["chars"].values():
        if char.get("uuid", "") == character_uuid:
            context["char"] = char
            break

    if "char" not in context:
        raise NotFoundError

    # Allow access if bypassing checks or user has character access permissions
    if bypass_access_checks or (request.user.is_authenticated and has_access_character(request, context)):
        # Load full character data and mark as having elevated access
        get_element(context, character_uuid, "character", Character)
        context["check"] = 1
        return

    # Block access to characters marked as hidden from public view
    if context["char"].get("hide", False):
        raise NotFoundError

    # Apply restriction check - deny access if restrict flag is set
    if restrict_non_owners:
        msg = "Not your character"
        raise Http404(msg)


def get_chars_relations(text: str, character_numbers: list[int]) -> tuple[list[int], list[int]]:
    """Retrieve character relationship data from text content.

    Searches for character references in the format '#number' within the provided text
    and categorizes them as either active (existing) or extinct (no longer valid)
    characters based on the provided valid character numbers.

    Args:
        text (str): Text content to search for character references in format '#number'
        character_numbers (list[int]): List of valid/active character numbers

    Returns:
        tuple[list[int], list[int]]: A tuple containing:
            - active_characters: List of character numbers found in text that exist in character_numbers
            - extinct_characters: List of character numbers found in text that don't exist in character_numbers

    Note:
        The function searches from the highest possible number (max + 100) down to 1
        to ensure longer numbers are matched first, preventing partial matches.

    """
    active_characters = []
    extinct_characters = []

    # Early return if no valid character numbers provided
    if not character_numbers:
        return active_characters, extinct_characters

    # Strip HTML tags from text for clean processing
    cleaned_text = strip_tags(text)

    # Start search from maximum character number plus buffer to catch any high numbers
    max_character_number = character_numbers[0]

    # Search from high to low numbers to avoid partial matching issues
    for number in range(max_character_number + 100, 0, -1):
        character_reference = f"#{number}"

        # Skip if this character reference isn't in the text
        if character_reference not in cleaned_text:
            continue

        # Remove found reference to prevent duplicate matches
        cleaned_text = cleaned_text.replace(character_reference, "")

        # Categorize as active or extinct based on validity
        if number in character_numbers:
            active_characters.append(number)
        else:
            extinct_characters.append(number)

    return active_characters, extinct_characters


def check_missing_mandatory(context: dict) -> None:
    """Check for missing mandatory character writing fields."""
    context["missing_fields"] = []
    missing_question_names = []

    question_type_to_model = {
        **dict.fromkeys(BaseQuestionType.get_answer_types(), WritingAnswer),
        **dict.fromkeys(BaseQuestionType.get_choice_types(), WritingChoice),
    }

    questions = get_cached_writing_questions(context["event"], QuestionApplicable.CHARACTER)
    character_id = _get_character_cache_id(context)

    # Collect mandatory questions grouped by model
    mandatory_by_model: dict = {WritingAnswer: [], WritingChoice: []}
    mandatory_question_names: dict = {}
    for question in questions:
        if question["status"] != QuestionStatus.MANDATORY:
            continue
        model = question_type_to_model.get(question["typ"])
        if model:
            mandatory_by_model[model].append(question["id"])
            mandatory_question_names[question["id"]] = question["name"]

    # Bulk fetch answered question ids for each model
    answered_ids: set = set()
    for model, question_ids in mandatory_by_model.items():
        if question_ids:
            answered_ids.update(
                model.objects.filter(
                    element_id=character_id,
                    question_id__in=question_ids,
                ).values_list("question_id", flat=True)
            )

    for question_id, question_name in mandatory_question_names.items():
        if question_id not in answered_ids:
            missing_question_names.append(question_name)

    context["missing_fields"] = ", ".join(missing_question_names)


def _get_character_cache_id(context: dict) -> int:
    """Get id of loaded character in context."""
    character_number = context["char"]["number"]
    return context["char_mapping"][character_number]
