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

from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404

from larpmanager.cache.character import get_character_element_fields, get_event_cache_all
from larpmanager.cache.fields import visible_writing_fields
from larpmanager.models.casting import Trait
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    WritingAnswer,
    WritingChoice,
    WritingQuestion,
)
from larpmanager.models.miscellanea import PlayerRelationship
from larpmanager.models.utils import strip_tags
from larpmanager.models.writing import Character, FactionType, PlotCharacterRel, Relationship
from larpmanager.utils.common import get_char
from larpmanager.utils.event import has_access_character
from larpmanager.utils.exceptions import NotFoundError
from larpmanager.utils.experience import add_char_addit

logger = logging.getLogger(__name__)


def get_character_relationships(ctx: dict, restrict: bool = True) -> None:
    """Get character relationships with faction and player input data.

    Retrieves and processes character relationships from both system-defined
    relationships and player-inputted relationships. Updates the context with
    formatted relationship data including faction information and text content.

    Args:
        ctx: Context dictionary containing character, event, run, chars, and factions data.
            Must include 'character', 'event', 'run', and may include 'chars', 'factions'.
        restrict: Whether to filter out relationships with empty text content.
            Defaults to True.

    Returns:
        None: Function modifies ctx in-place, adding 'rel' list and 'pr' dict.

    Side Effects:
        - Updates ctx['rel'] with sorted list of relationship data
        - Updates ctx['pr'] with player relationship objects
    """
    relationship_text_by_character_id = {}
    character_data_by_id = {}

    # Process system-defined relationships from the database
    for target_character_number, relationship_text in Relationship.objects.values_list("target__number", "text").filter(
        source=ctx["character"]
    ):
        # Check if character data is already cached in context
        if "chars" in ctx and target_character_number in ctx["chars"]:
            character_display_data = ctx["chars"][target_character_number]
        else:
            # Fetch character data from database if not cached
            try:
                target_character = Character.objects.select_related("event", "player").get(
                    event=ctx["event"], number=target_character_number
                )
                character_display_data = target_character.show(ctx["run"])
            except ObjectDoesNotExist:
                continue

        # Build faction list for display purposes
        character_display_data["factions_list"] = []
        for faction_number in character_display_data["factions"]:
            if not faction_number or faction_number not in ctx["factions"]:
                continue
            faction_data = ctx["factions"][faction_number]
            # Skip empty names or secret factions
            if not faction_data["name"] or faction_data["typ"] == FactionType.SECRET:
                continue
            character_display_data["factions_list"].append(faction_data["name"])

        # Join faction names and store character data
        character_display_data["factions_list"] = ", ".join(character_display_data["factions_list"])
        character_data_by_id[character_display_data["id"]] = character_display_data
        relationship_text_by_character_id[character_display_data["id"]] = relationship_text

    player_relationships_by_target_id = {}
    # Update with player-inputted relationship data
    if "player_id" in ctx["char"]:
        for player_relationship in PlayerRelationship.objects.select_related("target", "reg", "reg__member").filter(
            reg__member_id=ctx["char"]["player_id"], reg__run=ctx["run"]
        ):
            player_relationships_by_target_id[player_relationship.target_id] = player_relationship
            # Player input overrides system relationships
            relationship_text_by_character_id[player_relationship.target_id] = player_relationship.text

    # Build final relationship list sorted by text length
    ctx["rel"] = []
    for character_id in sorted(
        relationship_text_by_character_id, key=lambda k: len(relationship_text_by_character_id[k]), reverse=True
    ):
        # Skip if character data not found
        if character_id not in character_data_by_id:
            logger.debug(
                f"Character index {character_id} not found in data keys: {list(character_data_by_id.keys())[:5]}..."
            )
            continue

        relationship_entry = character_data_by_id[character_id]
        # Filter empty relationships if restrict is enabled
        if restrict and len(relationship_text_by_character_id[character_id]) == 0:
            continue

        # Add relationship text and calculate font size based on content length
        relationship_entry["text"] = relationship_text_by_character_id[character_id]
        relationship_entry["font_size"] = int(100 - ((len(relationship_entry["text"]) / 50) * 4))
        ctx["rel"].append(relationship_entry)

    # Store player relationships for additional processing
    ctx["pr"] = player_relationships_by_target_id


def get_character_sheet(ctx):
    """Build complete character sheet data for display.

    Args:
        ctx: Context dictionary with character data

    Returns:
        dict: Complete character sheet with all sections
    """
    ctx["sheet_char"] = ctx["character"].show_complete()

    get_character_sheet_fields(ctx)

    get_character_sheet_factions(ctx)

    get_character_sheet_plots(ctx)

    get_character_sheet_questbuilder(ctx)

    get_character_sheet_speedlarp(ctx)

    get_character_sheet_prologue(ctx)

    get_character_sheet_px(ctx)


def get_character_sheet_px(context: dict) -> None:
    """
    Populates the character sheet with ability data grouped by type.

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

    # Initialize abilities dictionary for grouping by type
    context["sheet_abilities"] = {}

    # Group abilities by their type name
    for ability in context["character"].px_ability_list.all():
        # Ensure ability has valid type and name before processing
        if ability.typ and ability.typ.name and ability.typ.name not in context["sheet_abilities"]:
            context["sheet_abilities"][ability.typ.name] = []
        context["sheet_abilities"][ability.typ.name].append(ability)

    # Add additional character data to context
    add_char_addit(context["character"])


def get_character_sheet_prologue(context: dict) -> None:
    """Adds character prologues to context if prologue feature is enabled."""
    if "prologue" not in context["features"]:
        return

    # Initialize empty list for sheet prologues
    context["sheet_prologues"] = []

    # Process each prologue in order and add complete data
    for prologue in context["character"].prologues_list.order_by("typ__number"):
        prologue.data = prologue.show_complete()
        context["sheet_prologues"].append(prologue)


def get_character_sheet_speedlarp(context: dict) -> None:
    """Populates context with speedlarp sheet data if feature is enabled."""
    if "speedlarp" not in context["features"]:
        return

    # Initialize speedlarp sheets list
    context["sheet_speedlarps"] = []

    # Process each speedlarp ordered by type
    for speedlarp in context["character"].speedlarps_list.order_by("typ"):
        speedlarp.data = speedlarp.show_complete()
        context["sheet_speedlarps"].append(speedlarp)


def get_character_sheet_questbuilder(ctx):
    """Build character sheet with quest and trait relationships.

    Args:
        ctx: Context dictionary with character, quest, and trait data

    Side effects:
        Updates ctx with sheet_traits containing complete trait and quest information
    """
    if "questbuilder" not in ctx["features"]:
        return

    if "char" not in ctx:
        return

    if "player_id" not in ctx["char"] or "traits" not in ctx["char"]:
        return

    ctx["sheet_traits"] = []
    for trait_number in ctx["char"]["traits"]:
        trait_element = ctx["traits"][trait_number]
        trait_object = Trait.objects.get(event=ctx["event"], number=trait_element["number"])
        trait_data = trait_object.show_complete()
        trait_data["quest"] = trait_object.quest.show_complete()

        trait_data["rels"] = []
        for related_trait_number in trait_element["traits"]:
            if related_trait_number not in ctx["traits"]:
                continue
            character_number = ctx["traits"][related_trait_number]["char"]
            trait_data["rels"].append(ctx["chars"][character_number])

        ctx["sheet_traits"].append(trait_data)


def get_character_sheet_plots(context: dict) -> None:
    """Adds character plot information to context if plot feature is enabled."""
    if "plot" not in context["features"]:
        return

    context["sheet_plots"] = []

    # Get all plot relations for the character ordered by sequence
    plot_relations = PlotCharacterRel.objects.filter(character=context["character"])

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


def get_character_sheet_factions(ctx: dict[str, Any]) -> None:
    """
    Retrieves and processes faction data for character sheet display.

    Fetches factions associated with a character, along with their writing answers
    and choices, then adds the processed data to the context for rendering.

    Args:
        ctx: Context dictionary containing character, event, features, and other
             rendering data. Modified in-place to add 'sheet_factions' key.

    Returns:
        None: Function modifies ctx dictionary in-place.
    """
    # Early return if faction feature is not enabled
    if "faction" not in ctx["features"]:
        return

    # Get the parent event that handles factions
    faction_event = ctx["event"].get_class_parent("faction")
    ctx["sheet_factions"] = []

    # Fetch all factions associated with the character
    factions = list(ctx["character"].factions_list.filter(event=faction_event))

    # Early return if no factions found
    if not factions:
        return

    # Prepare writing fields query data for faction-applicable questions
    visible_writing_fields(ctx, QuestionApplicable.FACTION, only_visible=False)

    # Determine which questions should be visible based on configuration
    visible_question_ids = []
    if "questions" in ctx:
        for question_id in ctx["questions"].keys():
            question_config_key = str(question_id)
            # Skip questions that are not configured to show for factions
            if "show_all" not in ctx and question_config_key not in ctx.get("show_faction", {}):
                continue
            visible_question_ids.append(question_id)

    # Extract faction IDs for bulk database queries
    faction_ids = [faction.id for faction in factions]

    # Build comprehensive answer mapping: faction_id -> {question_id -> text/choices}
    faction_answers_map = {}
    if visible_question_ids:
        # Bulk fetch all writing answers for performance
        for faction_id, question_id, answer_text in WritingAnswer.objects.filter(
            element_id__in=faction_ids, question_id__in=visible_question_ids
        ).values_list("element_id", "question_id", "text"):
            # Initialize nested dictionary structure as needed
            if faction_id not in faction_answers_map:
                faction_answers_map[faction_id] = {}
            faction_answers_map[faction_id][question_id] = answer_text

        # Bulk fetch all writing choices and group by faction and question
        for faction_id, question_id, option_id in WritingChoice.objects.filter(
            element_id__in=faction_ids, question_id__in=visible_question_ids
        ).values_list("element_id", "question_id", "option_id"):
            # Initialize nested dictionary and list structures as needed
            if faction_id not in faction_answers_map:
                faction_answers_map[faction_id] = {}
            if question_id not in faction_answers_map[faction_id]:
                faction_answers_map[faction_id][question_id] = []
            faction_answers_map[faction_id][question_id].append(option_id)

    # Process each faction and prepare display data
    for faction in factions:
        # Get base faction data
        faction_display_data = faction.show_complete()

        # Merge in writing fields from pre-fetched bulk data
        faction_writing_fields = faction_answers_map.get(faction.id, {})
        faction_display_data.update(
            {"questions": ctx.get("questions", {}), "options": ctx.get("options", {}), "fields": faction_writing_fields}
        )

        # Add processed faction data to context
        ctx["sheet_factions"].append(faction_display_data)


def get_character_sheet_fields(context: dict) -> None:
    """Updates character sheet context with character element fields.

    Args:
        context: Context dictionary containing features and sheet_char data.
    """
    # Check if character feature is enabled
    if "character" not in context["features"]:
        return

    # Update sheet character context with element fields
    context["sheet_char"].update(get_character_element_fields(context, context["character"].id, only_visible=False))


def get_char_check(
    request, ctx: dict, character_id: int, restrict_non_owners: bool = False, bypass_access_checks: bool = False
) -> None:
    """Get character with access control checks.

    Retrieves a character from the context and performs various access control
    checks based on user permissions and character visibility settings.

    Args:
        request: Django HTTP request object containing user and session data
        ctx: Context dictionary containing cached character and event data
        character_id: Character number/ID to retrieve from the character cache
        restrict_non_owners: Whether to apply strict visibility restrictions for non-owners
        bypass_access_checks: Whether to bypass all access checks (admin override)

    Returns:
        None: Modifies ctx in-place, adding 'char' and potentially 'check' keys

    Raises:
        NotFoundError: If character not found in cache or is hidden from user
        Http404: If character access is restricted and user lacks permission
    """
    # Load all event and character data into context cache
    get_event_cache_all(ctx)

    # Check if requested character exists in the cached character data
    if character_id not in ctx["chars"]:
        raise NotFoundError()

    # Set the current character in context for further processing
    ctx["char"] = ctx["chars"][character_id]

    # Allow access if bypassing checks or user has character access permissions
    if bypass_access_checks or (request.user.is_authenticated and has_access_character(request, ctx)):
        # Load full character data and mark as having elevated access
        get_char(ctx, character_id, True)
        ctx["check"] = 1
        return

    # Block access to characters marked as hidden from public view
    if ctx["char"].get("hide", False):
        raise NotFoundError()

    # Apply restriction check - deny access if restrict flag is set
    if restrict_non_owners:
        raise Http404("Not your character")


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
    # (e.g., matching #1 when #10 exists)
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


def check_missing_mandatory(ctx):
    """Check for missing mandatory character writing fields.

    Args:
        ctx: Context dictionary containing character and event data.
              Updates ctx with 'missing_fields' list.
    """
    ctx["missing_fields"] = []
    missing_question_names = []

    question_type_to_model = {
        **{question_type: WritingAnswer for question_type in BaseQuestionType.get_answer_types()},
        **{question_type: WritingChoice for question_type in BaseQuestionType.get_choice_types()},
    }

    questions = ctx["event"].get_elements(WritingQuestion)
    for question in questions.filter(applicable=QuestionApplicable.CHARACTER, status=QuestionStatus.MANDATORY):
        model = question_type_to_model.get(question.typ)
        if model and not model.objects.filter(element_id=ctx["char"]["id"], question=question).exists():
            missing_question_names.append(question.name)

    ctx["missing_fields"] = ", ".join(missing_question_names)
