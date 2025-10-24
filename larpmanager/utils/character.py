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
    cache = {}
    data = {}

    # Process system-defined relationships from the database
    for tg_num, text in Relationship.objects.values_list("target__number", "text").filter(source=ctx["character"]):
        # Check if character data is already cached in context
        if "chars" in ctx and tg_num in ctx["chars"]:
            show = ctx["chars"][tg_num]
        else:
            # Fetch character data from database if not cached
            try:
                ch = Character.objects.select_related("event", "player").get(event=ctx["event"], number=tg_num)
                show = ch.show(ctx["run"])
            except ObjectDoesNotExist:
                continue

        # Build faction list for display purposes
        show["factions_list"] = []
        for fac_num in show["factions"]:
            if not fac_num or fac_num not in ctx["factions"]:
                continue
            fac = ctx["factions"][fac_num]
            # Skip empty names or secret factions
            if not fac["name"] or fac["typ"] == FactionType.SECRET:
                continue
            show["factions_list"].append(fac["name"])

        # Join faction names and store character data
        show["factions_list"] = ", ".join(show["factions_list"])
        data[show["id"]] = show
        cache[show["id"]] = text

    pr = {}
    # Update with player-inputted relationship data
    if "player_id" in ctx["char"]:
        for el in PlayerRelationship.objects.select_related("target", "reg", "reg__member").filter(
            reg__member_id=ctx["char"]["player_id"], reg__run=ctx["run"]
        ):
            pr[el.target_id] = el
            # Player input overrides system relationships
            cache[el.target_id] = el.text

    # Build final relationship list sorted by text length
    ctx["rel"] = []
    for idx in sorted(cache, key=lambda k: len(cache[k]), reverse=True):
        # Skip if character data not found
        if idx not in data:
            logger.debug(f"Character index {idx} not found in data keys: {list(data.keys())[:5]}...")
            continue

        el = data[idx]
        # Filter empty relationships if restrict is enabled
        if restrict and len(cache[idx]) == 0:
            continue

        # Add relationship text and calculate font size based on content length
        el["text"] = cache[idx]
        el["font_size"] = int(100 - ((len(el["text"]) / 50) * 4))
        ctx["rel"].append(el)

    # Store player relationships for additional processing
    ctx["pr"] = pr


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


def get_character_sheet_px(ctx: dict) -> None:
    """
    Populates the character sheet with ability data grouped by type.

    Args:
        ctx: Context dictionary containing character data and features.
             Expected to have 'features' dict and 'character' object with
             px_ability_list attribute.

    Returns:
        None: Modifies ctx dictionary in-place by adding 'sheet_abilities'.
    """
    # Check if px feature is enabled before processing
    if "px" not in ctx["features"]:
        return

    # Initialize abilities dictionary for grouping by type
    ctx["sheet_abilities"] = {}

    # Group abilities by their type name
    for el in ctx["character"].px_ability_list.all():
        # Ensure ability has valid type and name before processing
        if el.typ and el.typ.name and el.typ.name not in ctx["sheet_abilities"]:
            ctx["sheet_abilities"][el.typ.name] = []
        ctx["sheet_abilities"][el.typ.name].append(el)

    # Add additional character data to context
    add_char_addit(ctx["character"])


def get_character_sheet_prologue(ctx: dict) -> None:
    """Adds character prologues to context if prologue feature is enabled."""
    if "prologue" not in ctx["features"]:
        return

    # Initialize empty list for sheet prologues
    ctx["sheet_prologues"] = []

    # Process each prologue in order and add complete data
    for s in ctx["character"].prologues_list.order_by("typ__number"):
        s.data = s.show_complete()
        ctx["sheet_prologues"].append(s)


def get_character_sheet_speedlarp(ctx: dict) -> None:
    """Populates context with speedlarp sheet data if feature is enabled."""
    if "speedlarp" not in ctx["features"]:
        return

    # Initialize speedlarp sheets list
    ctx["sheet_speedlarps"] = []

    # Process each speedlarp ordered by type
    for s in ctx["character"].speedlarps_list.order_by("typ"):
        s.data = s.show_complete()
        ctx["sheet_speedlarps"].append(s)


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
    for tnum in ctx["char"]["traits"]:
        el = ctx["traits"][tnum]
        t = Trait.objects.get(event=ctx["event"], number=el["number"])
        data = t.show_complete()
        data["quest"] = t.quest.show_complete()

        data["rels"] = []
        for snum in el["traits"]:
            if snum not in ctx["traits"]:
                continue
            num = ctx["traits"][snum]["char"]
            data["rels"].append(ctx["chars"][num])

        ctx["sheet_traits"].append(data)


def get_character_sheet_plots(ctx: dict) -> None:
    """Adds character plot information to context if plot feature is enabled."""
    if "plot" not in ctx["features"]:
        return

    ctx["sheet_plots"] = []

    # Get all plot relations for the character ordered by sequence
    que = PlotCharacterRel.objects.filter(character=ctx["character"])

    for el in que.order_by("order"):
        # Start with the base plot text
        tx = el.plot.text

        # Add separator and additional text if both exist
        if tx and el.text:
            tx += "<hr />"
        if el.text:
            tx += el.text

        # Add plot entry to context
        ctx["sheet_plots"].append({"name": el.plot.name, "text": tx})


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
    fac_event = ctx["event"].get_class_parent("faction")
    ctx["sheet_factions"] = []

    # Fetch all factions associated with the character
    factions = list(ctx["character"].factions_list.filter(event=fac_event))

    # Early return if no factions found
    if not factions:
        return

    # Prepare writing fields query data for faction-applicable questions
    visible_writing_fields(ctx, QuestionApplicable.FACTION, only_visible=False)

    # Determine which questions should be visible based on configuration
    question_visible = []
    if "questions" in ctx:
        for question_id in ctx["questions"].keys():
            config = str(question_id)
            # Skip questions that are not configured to show for factions
            if "show_all" not in ctx and config not in ctx.get("show_faction", {}):
                continue
            question_visible.append(question_id)

    # Extract faction IDs for bulk database queries
    faction_ids = [g.id for g in factions]

    # Build comprehensive answer mapping: faction_id -> {question_id -> text/choices}
    answer_map = {}
    if question_visible:
        # Bulk fetch all writing answers for performance
        for element_id, question_id, text in WritingAnswer.objects.filter(
            element_id__in=faction_ids, question_id__in=question_visible
        ).values_list("element_id", "question_id", "text"):
            # Initialize nested dictionary structure as needed
            if element_id not in answer_map:
                answer_map[element_id] = {}
            answer_map[element_id][question_id] = text

        # Bulk fetch all writing choices and group by faction and question
        for element_id, question_id, option_id in WritingChoice.objects.filter(
            element_id__in=faction_ids, question_id__in=question_visible
        ).values_list("element_id", "question_id", "option_id"):
            # Initialize nested dictionary and list structures as needed
            if element_id not in answer_map:
                answer_map[element_id] = {}
            if question_id not in answer_map[element_id]:
                answer_map[element_id][question_id] = []
            answer_map[element_id][question_id].append(option_id)

    # Process each faction and prepare display data
    for g in factions:
        # Get base faction data
        data = g.show_complete()

        # Merge in writing fields from pre-fetched bulk data
        fields = answer_map.get(g.id, {})
        data.update({"questions": ctx.get("questions", {}), "options": ctx.get("options", {}), "fields": fields})

        # Add processed faction data to context
        ctx["sheet_factions"].append(data)


def get_character_sheet_fields(ctx: dict) -> None:
    """Updates character sheet context with character element fields.

    Args:
        ctx: Context dictionary containing features and sheet_char data.
    """
    # Check if character feature is enabled
    if "character" not in ctx["features"]:
        return

    # Update sheet character context with element fields
    ctx["sheet_char"].update(get_character_element_fields(ctx, ctx["character"].id, only_visible=False))


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


def get_chars_relations(text: str, chs_numbers: list[int]) -> tuple[list[int], list[int]]:
    """Retrieve character relationship data from text content.

    Searches for character references in the format '#number' within the provided text
    and categorizes them as either active (existing) or extinct (no longer valid)
    characters based on the provided valid character numbers.

    Args:
        text (str): Text content to search for character references in format '#number'
        chs_numbers (list[int]): List of valid/active character numbers

    Returns:
        tuple[list[int], list[int]]: A tuple containing:
            - active_characters: List of character numbers found in text that exist in chs_numbers
            - extinct_characters: List of character numbers found in text that don't exist in chs_numbers

    Note:
        The function searches from the highest possible number (max + 100) down to 1
        to ensure longer numbers are matched first, preventing partial matches.
    """
    chs = []
    extinct = []

    # Early return if no valid character numbers provided
    if not chs_numbers:
        return chs, extinct

    # Strip HTML tags from text for clean processing
    tx = strip_tags(text)

    # Start search from maximum character number plus buffer to catch any high numbers
    max_number = chs_numbers[0]

    # Search from high to low numbers to avoid partial matching issues
    # (e.g., matching #1 when #10 exists)
    for number in range(max_number + 100, 0, -1):
        k = f"#{number}"

        # Skip if this character reference isn't in the text
        if k not in tx:
            continue

        # Remove found reference to prevent duplicate matches
        tx = tx.replace(k, "")

        # Categorize as active or extinct based on validity
        if number in chs_numbers:
            chs.append(number)
        else:
            extinct.append(number)

    return chs, extinct


def check_missing_mandatory(ctx):
    """Check for missing mandatory character writing fields.

    Args:
        ctx: Context dictionary containing character and event data.
              Updates ctx with 'missing_fields' list.
    """
    ctx["missing_fields"] = []
    aux = []

    models = {
        **{t: WritingAnswer for t in BaseQuestionType.get_answer_types()},
        **{t: WritingChoice for t in BaseQuestionType.get_choice_types()},
    }

    questions = ctx["event"].get_elements(WritingQuestion)
    for que in questions.filter(applicable=QuestionApplicable.CHARACTER, status=QuestionStatus.MANDATORY):
        model = models.get(que.typ)
        if model and not model.objects.filter(element_id=ctx["char"]["id"], question=que).exists():
            aux.append(que.name)

    ctx["missing_fields"] = ", ".join(aux)
