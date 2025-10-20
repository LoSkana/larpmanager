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

from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest

from larpmanager.cache.character import get_character_element_fields, get_event_cache_all, get_writing_element_fields
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


def get_character_sheet(ctx: dict) -> None:
    """Build complete character sheet data for display.

    Constructs a comprehensive character sheet by gathering data from multiple
    sources including basic character information, custom fields, factions,
    plots, questbuilder content, speedlarp data, prologue, and experience points.

    Args:
        ctx: Context dictionary containing character data and other relevant
            information. Must include 'character' key with character object.

    Returns:
        None: Function modifies the ctx dictionary in place by adding
            character sheet data under various keys.

    Note:
        This function modifies the input dictionary in place, adding multiple
        keys with character sheet sections.
    """
    # Get the complete character display data
    ctx["sheet_char"] = ctx["character"].show_complete()

    # Build custom character fields section
    get_character_sheet_fields(ctx)

    # Add faction information and relationships
    get_character_sheet_factions(ctx)

    # Include plot hooks and story elements
    get_character_sheet_plots(ctx)

    # Add questbuilder-specific content
    get_character_sheet_questbuilder(ctx)

    # Include speedlarp game mechanics data
    get_character_sheet_speedlarp(ctx)

    # Add character prologue and background
    get_character_sheet_prologue(ctx)

    # Calculate and add experience points data
    get_character_sheet_px(ctx)


def get_character_sheet_px(ctx: dict) -> None:
    """Add character sheet abilities data to the context dictionary.

    Processes the character's ability list and groups abilities by type name,
    then adds the grouped data to the context for sheet rendering.

    Args:
        ctx: Context dictionary containing character and features data.
             Must have 'features' and 'character' keys.

    Returns:
        None: Modifies the ctx dictionary in place.
    """
    # Early return if px feature is not enabled
    if "px" not in ctx["features"]:
        return

    # Initialize abilities dictionary for sheet rendering
    ctx["sheet_abilities"] = {}

    # Group abilities by their type name
    for el in ctx["character"].px_ability_list.all():
        # Check if ability has a valid type and name
        if el.typ and el.typ.name and el.typ.name not in ctx["sheet_abilities"]:
            ctx["sheet_abilities"][el.typ.name] = []

        # Add ability to the appropriate type group
        ctx["sheet_abilities"][el.typ.name].append(el)

    # Add additional character data to context
    add_char_addit(ctx["character"])


def get_character_sheet_prologue(ctx):
    if "prologue" not in ctx["features"]:
        return

    ctx["sheet_prologues"] = []
    for s in ctx["character"].prologues_list.order_by("typ__number"):
        s.data = s.show_complete()
        ctx["sheet_prologues"].append(s)


def get_character_sheet_speedlarp(ctx):
    if "speedlarp" not in ctx["features"]:
        return

    ctx["sheet_speedlarps"] = []
    for s in ctx["character"].speedlarps_list.order_by("typ"):
        s.data = s.show_complete()
        ctx["sheet_speedlarps"].append(s)


def get_character_sheet_questbuilder(ctx: dict) -> None:
    """Build character sheet with quest and trait relationships.

    Constructs a complete character sheet by processing trait data and their
    associated quest relationships. Updates the context with enriched trait
    information including quest details and character relationships.

    Args:
        ctx: Context dictionary containing:
            - features: Available features list
            - char: Character data with player_id and traits
            - traits: Trait definitions indexed by number
            - chars: Character data indexed by number
            - event: Event object for trait queries

    Returns:
        None: Function modifies ctx in place

    Side Effects:
        Updates ctx['sheet_traits'] with list of enriched trait dictionaries
        containing complete trait data, quest information, and relationships.
    """
    # Early return if questbuilder feature is not available
    if "questbuilder" not in ctx["features"]:
        return

    # Validate required character data exists
    if "char" not in ctx:
        return

    # Ensure character has required player_id and traits fields
    if "player_id" not in ctx["char"] or "traits" not in ctx["char"]:
        return

    # Initialize the sheet traits list for processed data
    ctx["sheet_traits"] = []

    # Process each trait number associated with the character
    for tnum in ctx["char"]["traits"]:
        # Get trait element from context traits dictionary
        el = ctx["traits"][tnum]

        # Fetch complete trait object from database
        t = Trait.objects.get(event=ctx["event"], number=el["number"])
        data = t.show_complete()

        # Add associated quest information to trait data
        data["quest"] = t.quest.show_complete()

        # Initialize relationships list for this trait
        data["rels"] = []

        # Process trait relationships and add character data
        for snum in el["traits"]:
            # Skip if related trait not found in context
            if snum not in ctx["traits"]:
                continue

            # Get character number and add character data to relationships
            num = ctx["traits"][snum]["char"]
            data["rels"].append(ctx["chars"][num])

        # Add completed trait data to sheet traits list
        ctx["sheet_traits"].append(data)


def get_character_sheet_plots(ctx):
    if "plot" not in ctx["features"]:
        return

    ctx["sheet_plots"] = []
    que = PlotCharacterRel.objects.filter(character=ctx["character"])
    for el in que.order_by("order"):
        tx = el.plot.text
        if tx and el.text:
            tx += "<hr />"
        if el.text:
            tx += el.text
        ctx["sheet_plots"].append({"name": el.plot.name, "text": tx})


def get_character_sheet_factions(ctx):
    if "faction" not in ctx["features"]:
        return

    fac_event = ctx["event"].get_class_parent("faction")
    ctx["sheet_factions"] = []
    for g in ctx["character"].factions_list.filter(event=fac_event):
        data = g.show_complete()
        data.update(get_writing_element_fields(ctx, "faction", QuestionApplicable.FACTION, g.id, only_visible=False))
        ctx["sheet_factions"].append(data)


def get_character_sheet_fields(ctx):
    if "character" not in ctx["features"]:
        return

    ctx["sheet_char"].update(get_character_element_fields(ctx, ctx["character"].id, only_visible=False))


def get_char_check(request: HttpRequest, ctx: dict, num: int, restrict: bool = False, bypass: bool = False) -> None:
    """Get character with access control checks.

    Retrieves a character from the cache and applies appropriate access control
    based on user permissions and character visibility settings.

    Args:
        request: Django HTTP request object containing user information
        ctx: Context dictionary containing cached character data
        num: Character number/identifier to retrieve
        restrict: If True, raises Http404 for unauthorized access instead of
                 allowing restricted view
        bypass: If True, skips all access control checks

    Returns:
        None: Modifies ctx in place with character data and check status

    Raises:
        NotFoundError: If character number not found in cache
        Http404: If character is hidden or access is restricted
    """
    # Load all cached event data including characters
    get_event_cache_all(ctx)

    # Check if character exists in cache
    if num not in ctx["chars"]:
        raise NotFoundError()

    # Set current character in context
    ctx["char"] = ctx["chars"][num]

    # Handle bypass mode or authenticated users with character access
    if bypass or (request.user.is_authenticated and has_access_character(request, ctx)):
        get_char(ctx, num, True)
        ctx["check"] = 1
        return

    # Check if character is marked as hidden
    if ctx["char"].get("hide", False):
        raise NotFoundError()

    # Apply restriction policy for unauthorized access
    if restrict:
        raise Http404("Not your character")


def get_chars_relations(text: str, chs_numbers: list[int]) -> tuple[list[int], list[int]]:
    """Retrieve character relationship data from text content.

    Searches through the provided text for character references in the format
    '#number' and categorizes them as either active or extinct based on whether
    the character number exists in the provided valid character numbers list.

    Args:
        text: Text content to search for character references in '#number' format.
        chs_numbers: List of valid/active character numbers to check against.

    Returns:
        A tuple containing two lists:
        - active_characters: List of character numbers found in text that exist
          in chs_numbers
        - extinct_characters: List of character numbers found in text that don't
          exist in chs_numbers

    Note:
        The function searches from max_number + 100 down to 1 to ensure longer
        numbers are matched before shorter ones (e.g., #123 before #12).
    """
    chs = []
    extinct = []

    # Early return if no character numbers provided
    if not chs_numbers:
        return chs, extinct

    # Strip HTML tags from text for clean processing
    tx = strip_tags(text)

    # Start search from highest number + buffer to avoid partial matches
    max_number = chs_numbers[0]
    for number in range(max_number + 100, 0, -1):
        # Format character reference pattern
        k = f"#{number}"
        if k not in tx:
            continue

        # Remove found reference to prevent duplicate matches
        tx = tx.replace(k, "")

        # Categorize character as active or extinct
        if number in chs_numbers:
            chs.append(number)
        else:
            extinct.append(number)

    return chs, extinct


def check_missing_mandatory(ctx: dict) -> None:
    """Check for missing mandatory character writing fields.

    Examines the event's writing questions that are mandatory for characters
    and identifies which ones the character hasn't answered yet. Updates the
    context with a comma-separated string of missing field names.

    Args:
        ctx: Context dictionary containing character and event data.
             Must include 'char' dict with 'id' key and 'event' object.
             Gets updated with 'missing_fields' key containing comma-separated
             string of missing mandatory field names.
    """
    ctx["missing_fields"] = []
    aux = []

    # Map question types to their corresponding model classes
    # Answer types handle text/number inputs, choice types handle selections
    models = {
        **{t: WritingAnswer for t in BaseQuestionType.get_answer_types()},
        **{t: WritingChoice for t in BaseQuestionType.get_choice_types()},
    }

    # Get all writing questions for this event
    questions = ctx["event"].get_elements(WritingQuestion)

    # Filter for mandatory character-applicable questions only
    for que in questions.filter(applicable=QuestionApplicable.CHARACTER, status=QuestionStatus.MANDATORY):
        # Get the appropriate model class for this question type
        model = models.get(que.typ)

        # Check if character has answered this mandatory question
        if model and not model.objects.filter(element_id=ctx["char"]["id"], question=que).exists():
            aux.append(que.name)

    # Convert list of missing field names to comma-separated string
    ctx["missing_fields"] = ", ".join(aux)
