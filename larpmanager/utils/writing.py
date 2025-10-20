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

import csv
import io
import json
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Exists, Model, OuterRef
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_all, get_writing_element_fields
from larpmanager.cache.rels import get_event_rels_cache
from larpmanager.cache.text_fields import get_cache_text_field
from larpmanager.models.access import get_event_staffers
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import ProgressStep
from larpmanager.models.experience import AbilityPx
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    WritingAnswer,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import (
    Character,
    CharacterConfig,
    Faction,
    Plot,
    PlotCharacterRel,
    Prologue,
    SpeedLarp,
    TextVersion,
    Writing,
    replace_character_names_in_writing,
)
from larpmanager.templatetags.show_tags import show_char, show_trait
from larpmanager.utils.bulk import handle_bulk_characters, handle_bulk_quest, handle_bulk_trait
from larpmanager.utils.character import get_character_relationships, get_character_sheet
from larpmanager.utils.common import check_field, compute_diff
from larpmanager.utils.download import download
from larpmanager.utils.edit import _setup_char_finder
from larpmanager.utils.exceptions import ReturnNowError


def orga_list_progress_assign(ctx: dict, typ: type[Model]) -> None:
    """Setup progress and assignment tracking for writing elements.

    Populates the context dictionary with progress steps, assignments, and their
    respective mapping counters based on available features. Counts occurrences
    of each progress step and assignment combination in the provided list.

    Args:
        ctx: Context dictionary to populate with progress/assignment data.
             Must contain 'features', 'event', and 'list' keys.
        typ: Model type being processed (Character, Plot, etc.)

    Returns:
        None: Function modifies ctx in-place

    Side Effects:
        Updates ctx with the following keys:
        - progress_steps: Dict mapping progress step IDs to their string representations
        - progress_steps_map: Counter dict for progress step occurrences
        - assigned: Dict mapping member IDs to their display names
        - assigned_map: Counter dict for assignment occurrences
        - progress_assigned_map: Counter dict for progress/assignment combinations
        - typ: String representation of the model type
    """
    features = ctx["features"]
    event = ctx["event"]

    # Initialize progress tracking if feature is enabled
    if "progress" in features:
        ctx["progress_steps"] = {el.id: str(el) for el in ProgressStep.objects.filter(event=event).order_by("order")}
        ctx["progress_steps_map"] = {el_id: 0 for el_id in ctx["progress_steps"]}

    # Initialize assignment tracking if feature is enabled
    if "assigned" in features:
        ctx["assigned"] = {m.id: m.show_nick() for m in get_event_staffers(event)}
        ctx["assigned_map"] = {m_id: 0 for m_id in ctx["assigned"]}

    # Initialize combined progress/assignment tracking if both features enabled
    if "progress" in features and "assigned" in features:
        ctx["progress_assigned_map"] = {f"{p}_{a}": 0 for p in ctx["progress_steps"] for a in ctx["assigned"]}

    # Count occurrences of progress steps and assignments in the list
    for el in ctx["list"]:
        pid = el.progress_id
        aid = el.assigned_id

        # Increment progress step counter
        if "progress" in features and pid in ctx.get("progress_steps_map", {}):
            ctx["progress_steps_map"][pid] += 1

        # Increment assignment counter
        if "assigned" in features and aid in ctx.get("assigned_map", {}):
            ctx["assigned_map"][aid] += 1

        # Increment combined progress/assignment counter
        if "progress" in features and "assigned" in features:
            key = f"{pid}_{aid}"
            if key in ctx.get("progress_assigned_map", {}):
                ctx["progress_assigned_map"][key] += 1

    # Store simplified model type name for template usage
    ctx["typ"] = str(typ._meta).replace("larpmanager.", "")  # type: ignore[attr-defined]


def writing_popup_question(ctx: dict, idx: int, question_idx: int) -> JsonResponse:
    """Get writing question data for popup display.

    This function retrieves a character's writing answer for a specific question
    and formats it for display in a popup window.

    Args:
        ctx: Context dictionary containing event and writing element data.
            Must include 'event' key with event object.
        idx: Character ID to retrieve the writing answer for.
        question_idx: Writing question ID to retrieve the answer for.

    Returns:
        JsonResponse containing either:
            - Success response with formatted HTML content (k=1, v=html_string)
            - Error response for missing objects (k=0)

    Raises:
        ObjectDoesNotExist: When character, question, or answer cannot be found.
    """
    try:
        # Get the character from the event's parent class
        char = Character.objects.get(pk=idx, event=ctx["event"].get_class_parent(Character))

        # Get the writing question from the event's parent class
        question = WritingQuestion.objects.get(pk=question_idx, event=ctx["event"].get_class_parent(WritingQuestion))

        # Retrieve the writing answer for this character and question
        el = WritingAnswer.objects.get(element_id=char.id, question=question)

        # Format the response with character name, question name, and answer text
        tx = f"<h2>{char} - {question.name}</h2>" + el.text
        return JsonResponse({"k": 1, "v": tx})
    except ObjectDoesNotExist:
        # Return error response when any required object is not found
        return JsonResponse({"k": 0})


def writing_popup(request: HttpRequest, ctx: dict[str, Any], typ: type[Model]) -> JsonResponse:
    """Handle writing element popup requests.

    Args:
        request: Django HTTP request object containing POST data with idx and tp parameters
        ctx: Context dictionary containing event data and cached information
        typ: Django model class for the writing element type (Character, Plot, etc.)

    Returns:
        JsonResponse containing either:
            - Error response with 400 status for invalid parameters
            - Success response with k=1 and HTML content in v field
            - Not found response with k=0 for missing objects or attributes

    Raises:
        ObjectDoesNotExist: When the requested writing element is not found
    """
    # Load all cached event data into context
    get_event_cache_all(ctx)

    # Parse and validate the index parameter from POST data
    try:
        idx = int(request.POST.get("idx", ""))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid idx parameter"}, status=400)

    # Extract the type parameter for attribute lookup
    tp = request.POST.get("tp", "")

    # Check if this is a character question request (numeric tp indicates question)
    try:
        question_idx = int(tp)
        return writing_popup_question(ctx, idx, question_idx)
    except ValueError:
        # Not a question, continue with regular element handling
        pass

    # Retrieve the writing element from database using parent event context
    try:
        el = typ.objects.get(pk=idx, event=ctx["event"].get_class_parent(typ))
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    # Verify the requested attribute exists on the element
    if not hasattr(el, tp):
        return JsonResponse({"k": 0})

    # Build HTML response with element title and content
    tx = f"<h2>{el} - {tp}</h2>"

    # Render content based on element type (traits/quests vs characters)
    if typ in [Trait, Quest]:
        tx += show_trait(ctx, getattr(el, tp), ctx["run"], 1)
    else:
        tx += show_char(ctx, getattr(el, tp), ctx["run"], 1)

    return JsonResponse({"k": 1, "v": tx})


def writing_example(ctx: dict, typ) -> HttpResponse:
    """Generate example writing content for a given type.

    Args:
        ctx: Context dictionary containing event information and features
        typ: Writing type object that provides example CSV generation methods

    Returns:
        HttpResponse: CSV file download response with example content for the writing type
    """
    # Get example CSV rows based on available features
    file_rows = typ.get_example_csv(ctx["features"])

    # Create in-memory string buffer for CSV content
    buffer = io.StringIO()
    wr = csv.writer(buffer, quoting=csv.QUOTE_ALL)

    # Write all example rows to CSV buffer
    wr.writerows(file_rows)

    # Reset buffer position to beginning for reading
    buffer.seek(0)

    # Create HTTP response with CSV content type
    response = HttpResponse(buffer, content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=example.csv"

    return response


def writing_post(request: HttpRequest, ctx: dict, typ: type, nm: str) -> None:
    """Handle POST requests for writing operations.

    Processes POST requests for writing-related operations including downloads,
    examples, and popup displays. Uses early returns and exceptions for control flow.

    Args:
        request: Django HTTP request object containing POST data
        ctx: Context dictionary containing event data and configuration
        typ: Writing element type class for processing operations
        nm: Template name string for rendering operations

    Raises:
        ReturnNowError: When download, example, or popup operations need to
                       return immediately with their respective responses

    Returns:
        None: Function returns early if no POST data is present
    """
    # Early return if no POST data is present
    if not request.POST:
        return

    # Handle download request - triggers file download response
    if request.POST.get("download") == "1":
        raise ReturnNowError(download(ctx, typ, nm))

    # Handle example request - generates example content
    if request.POST.get("example") == "1":
        raise ReturnNowError(writing_example(ctx, typ))

    # Handle popup request - displays popup interface
    if request.POST.get("popup") == "1":
        raise ReturnNowError(writing_popup(request, ctx, typ))


def writing_list(request: HttpRequest, ctx: dict[str, Any], typ: type[Model], nm: str) -> HttpResponse:
    """Handle writing list display with POST processing and bulk operations.

    Manages writing element lists with form submission processing,
    bulk operations, and proper context preparation for different writing types.

    Args:
        request: The HTTP request object containing user data and parameters
        ctx: Context dictionary containing event data and other shared state
        typ: Model class type for the writing element (Character, Plot, etc.)
        nm: Name string used for template and URL routing

    Returns:
        HttpResponse: Rendered template response for the writing list page

    Note:
        This function modifies the ctx dictionary in-place and handles various
        writing types through conditional logic and specialized helper functions.
    """
    # Process any POST data for writing operations
    writing_post(request, ctx, typ, nm)

    # Handle bulk operations on writing elements
    writing_bulk(ctx, request, typ)

    # Extract event from context for query operations
    ev = ctx["event"]
    ctx["nm"] = nm

    # Get text fields configuration and writing query results
    text_fields, writing = writing_list_query(ctx, ev, typ)

    # Apply type-specific context modifications based on model type
    if issubclass(typ, Character):
        writing_list_char(ctx)

    if issubclass(typ, Plot):
        writing_list_plot(ctx)

    if issubclass(typ, Faction):
        writing_list_faction(ctx)

    # Handle speed LARP specific context setup
    if issubclass(typ, SpeedLarp):
        writing_list_speedlarp(ctx)

    if issubclass(typ, Prologue):
        writing_list_prologue(ctx)

    # Configure quest and quest type specific contexts
    if issubclass(typ, Quest):
        writing_list_quest(ctx)

    if issubclass(typ, QuestType):
        writing_list_questtype(ctx)

    # Add prerequisites prefetching for ability experience types
    if issubclass(typ, AbilityPx):
        ctx["list"] = ctx["list"].prefetch_related("prerequisites")

    # Setup writing-specific context if writing elements exist
    if writing:
        # noinspection PyProtectedMember, PyUnresolvedReferences
        ctx["label_typ"] = typ._meta.model_name
        ctx["writing_typ"] = QuestionApplicable.get_applicable(ctx["label_typ"])

        # Configure upload/download paths if writing type is applicable
        if ctx["writing_typ"]:
            ctx["upload"] = f"{nm}s"
            ctx["download"] = f"{nm}s"

        # Setup progress assignment and text field handling
        orga_list_progress_assign(ctx, typ)  # pyright: ignore[reportArgumentType]
        writing_list_text_fields(ctx, text_fields, typ)

        # Prepare final context elements for rendering
        _prepare_writing_list(ctx, request)
        _setup_char_finder(ctx, typ)
        _get_custom_form(ctx)

    # Render the appropriate template based on the name parameter
    return render(request, "larpmanager/orga/writing/" + nm + "s.html", ctx)


def writing_bulk(ctx: dict, request: HttpRequest, typ: type) -> None:
    """Handle bulk operations for different writing element types.

    This function serves as a dispatcher that routes bulk operations to
    type-specific handlers based on the writing element type provided.

    Args:
        ctx: Context dictionary containing event data and related information
        request: Django HTTP request object containing bulk operation parameters
        typ: Writing element type class (Character, Quest, or Trait)

    Returns:
        None

    Side Effects:
        Executes bulk operations through type-specific handlers which may
        modify database records, update context, or perform other mutations.
    """
    # Define mapping of element types to their corresponding bulk handlers
    bulks = {Character: handle_bulk_characters, Quest: handle_bulk_quest, Trait: handle_bulk_trait}

    # Execute the appropriate handler if the type is supported
    if typ in bulks:
        bulks[typ](request, ctx)


def _get_custom_form(ctx: dict) -> None:
    """Setup custom form questions and field names for writing elements.

    This function configures form questions and field names for writing elements
    based on the writing type specified in the context. It filters questions
    by applicability and categorizes them into basic types and custom form questions.

    Parameters
    ----------
    ctx : dict
        Context dictionary containing 'writing_typ' and 'event' keys.
        Must include:
        - writing_typ: The type of writing element
        - event: Event object with get_elements method

    Returns
    -------
    None
        Function modifies ctx in place, adding 'form_questions' and 'fields_name' keys.

    Side Effects
    ------------
    Updates ctx with:
    - form_questions: Dictionary mapping question IDs to question objects
    - fields_name: Dictionary mapping question types to display names
    """
    # Early return if no writing type is specified
    if not ctx["writing_typ"]:
        return

    # Initialize default field names with the NAME type
    # This provides a base mapping for standard question types
    ctx["fields_name"] = {WritingQuestionType.NAME.value: _("Name")}

    # Retrieve and filter questions for the current event and writing type
    # Questions are ordered by their 'order' field for consistent display
    que = ctx["event"].get_elements(WritingQuestion).order_by("order")
    que = que.filter(applicable=ctx["writing_typ"])

    # Initialize the form questions dictionary for custom questions
    ctx["form_questions"] = {}

    # Process each question to categorize and configure display
    for q in que:
        # Mark whether this question uses a basic input type
        # Basic types are handled differently in form rendering
        q.basic_typ = q.typ in BaseQuestionType.get_basic_types()

        # Handle field name mapping for recognized question types
        # If the question type already exists in fields_name, update its display name
        if q.typ in ctx["fields_name"].keys():
            ctx["fields_name"][q.typ] = q.name
        else:
            # For custom question types, add to form_questions for special handling
            ctx["form_questions"][q.id] = q


def writing_list_query(ctx: dict, ev, typ) -> tuple[list[str], bool]:
    """
    Build optimized database query for writing element lists.

    Constructs an efficient Django ORM query for retrieving writing elements
    with appropriate select_related and prefetch_related optimizations based
    on the model type and available features.

    Args:
        ctx: Context dictionary to store query results under 'list' key.
        ev: Event instance used to determine the parent event for filtering.
        typ: Writing element model class to query against.

    Returns:
        A tuple containing:
            - list[str]: Text fields that were deferred from the query
            - bool: Whether the model is a Writing subclass
    """
    # Determine if this is a Writing model and set up basic query structure
    writing = issubclass(typ, Writing)
    text_fields = ["teaser", "text"]
    ctx["list"] = typ.objects.filter(event=ev.get_class_parent(typ))

    # Optimize query with select_related for Writing models with progress tracking
    if writing and hasattr(typ, "progress"):
        ctx["list"] = ctx["list"].select_related("progress", "assigned")

    # Defer large text fields for Writing models to improve performance
    if writing:
        for f in text_fields:
            ctx["list"] = ctx["list"].defer(f)

    # Apply ordering based on available fields: order > number > updated (newest first)
    if check_field(typ, "order"):
        ctx["list"] = ctx["list"].order_by("order")
    elif check_field(typ, "number"):
        ctx["list"] = ctx["list"].order_by("number")
    else:
        ctx["list"] = ctx["list"].order_by("-updated")

    return text_fields, writing


def writing_list_text_fields(ctx: dict, text_fields: list[str], typ: type) -> None:
    """
    Add editor-type question fields to text fields list and retrieve cached data.

    Extends the provided text fields list with editor-type questions from the event's
    writing questions, then retrieves cached text field data for the specified type.

    Args:
        ctx: Context dictionary containing event and writing type information.
             Must include 'event' and 'writing_typ' keys.
        text_fields: List of text field names to extend with question IDs.
        typ: Writing element model class used for cache retrieval.

    Returns:
        None: Modifies text_fields list in-place and updates context cache.
    """
    # Get writing questions applicable to the current writing type
    que = ctx["event"].get_elements(WritingQuestion).filter(applicable=ctx["writing_typ"])

    # Filter for editor-type questions and extract their primary keys
    for que_id in que.filter(typ=BaseQuestionType.EDITOR).values_list("pk", flat=True):
        # Convert question ID to string and add to text fields list
        text_fields.append(str(que_id))

    # Retrieve and cache text field data for the specified type
    retrieve_cache_text_field(ctx, text_fields, typ)


def retrieve_cache_text_field(ctx: dict, text_fields: list[str], typ: type) -> None:
    """
    Retrieve and attach cached text field data to writing elements.

    This function fetches cached text field data for writing elements and attaches
    the processed content (reduced text and line numbers) as new attributes to each
    element in the context list.

    Args:
        ctx: Context dictionary containing a 'list' key with writing elements
             and an 'event' key for the current event
        text_fields: List of text field names to process and cache
        typ: Writing element model class used for cache retrieval

    Returns:
        None: Modifies elements in ctx['list'] in-place by adding new attributes
    """
    # Get cached text field data for the specified type and event
    gctf = get_cache_text_field(typ, ctx["event"])

    # Process each element in the context list
    for el in ctx["list"]:
        # Skip elements that don't have cached data
        if el.id not in gctf:
            continue

        # Process each requested text field for this element
        for f in text_fields:
            # Skip fields that don't exist in the cached data
            if f not in gctf[el.id]:
                continue

            # Extract reduced text and line number from cached data
            (red, ln) = gctf[el.id][f]

            # Attach processed data as new attributes to the element
            setattr(el, f + "_red", red)
            setattr(el, f + "_ln", ln)


def _prepare_writing_list(ctx: dict, request: HttpRequest) -> None:
    """Prepare context data for writing list display and configuration.

    This function configures the context dictionary with necessary data for
    displaying and managing writing lists, including question IDs, default
    fields configuration, auto-save settings, and importance flags.

    Args:
        ctx: Template context dictionary to update with writing list data.
            Expected to contain 'event', 'writing_typ', and 'label_typ' keys.
        request: HTTP request object containing user information and member data.

    Returns:
        None: Modifies the ctx dictionary in-place.

    Note:
        Silently handles exceptions when retrieving name question ID to avoid
        breaking the flow if no applicable writing questions are found.
    """
    # Try to get the name question ID for the current writing type
    # This may fail if no applicable questions exist, which is handled gracefully
    try:
        name_que = (
            ctx["event"]
            .get_elements(WritingQuestion)
            .filter(applicable=ctx["writing_typ"], typ=WritingQuestionType.NAME)
        )
        ctx["name_que_id"] = name_que.values_list("id", flat=True)[0]
    except Exception:
        pass

    # Get user's saved field configuration or use default if none exists
    model_name = ctx["label_typ"].lower()
    ctx["default_fields"] = request.user.member.get_config(f"open_{model_name}_{ctx['event'].id}", "[]")

    # If no user configuration exists, build default from writing_fields
    if ctx["default_fields"] == "[]":
        if model_name in ctx["writing_fields"]:
            lst = [f"q_{el}" for name, el in ctx["writing_fields"][model_name]["ids"].items()]
            ctx["default_fields"] = json.dumps(lst)

    # Configure auto-save behavior based on event settings
    ctx["auto_save"] = not ctx["event"].get_config("writing_disable_auto", False)

    # Set writing importance flag from event configuration
    ctx["writing_unimportant"] = ctx["event"].get_config("writing_unimportant", False)


def writing_list_plot(ctx: dict) -> None:
    """Build character associations for plot list display.

    This function enriches plot objects in the context with their associated
    character relationships by fetching cached event relationship data.

    Args:
        ctx: Context dictionary containing:
            - list: List of plot objects to enrich
            - event: Event object used to retrieve cached relationships

    Returns:
        None: Function modifies the context dictionary in place

    Side Effects:
        - Adds character_rels attribute to each plot object in ctx["list"]
        - character_rels contains list of character relationships for each plot
    """
    # Retrieve cached relationship data for the event
    rels = get_event_rels_cache(ctx["event"]).get("plots", {})

    # Iterate through each plot in the context list
    for el in ctx["list"]:
        # Attach character relationships to each plot object
        # Use empty list as fallback if no relationships exist
        el.character_rels = rels.get(el.id, {}).get("character_rels", [])


def writing_list_faction(ctx):
    rels = get_event_rels_cache(ctx["event"]).get("factions", {})

    for el in ctx["list"]:
        el.character_rels = rels.get(el.id, {}).get("character_rels", [])


def writing_list_speedlarp(ctx):
    rels = get_event_rels_cache(ctx["event"]).get("speedlarps", {})

    for el in ctx["list"]:
        el.character_rels = rels.get(el.id, {}).get("character_rels", [])


def writing_list_prologue(ctx):
    rels = get_event_rels_cache(ctx["event"]).get("prologues", {})

    for el in ctx["list"]:
        el.character_rels = rels.get(el.id, {}).get("character_rels", [])


def writing_list_quest(ctx):
    rels = get_event_rels_cache(ctx["event"]).get("quests", {})

    for el in ctx["list"]:
        el.trait_rels = rels.get(el.id, {}).get("trait_rels", [])


def writing_list_questtype(ctx):
    rels = get_event_rels_cache(ctx["event"]).get("questtypes", {})

    for el in ctx["list"]:
        el.quest_rels = rels.get(el.id, {}).get("quest_rels", [])


def writing_list_char(ctx: dict) -> None:
    """Enhance character list with feature-specific data and relationships.

    This function modifies the character list in the context by adding feature-specific
    data such as player relationships, registration status, and various relationship types
    based on enabled features.

    Args:
        ctx: Context dictionary containing:
            - list: QuerySet of characters to enhance
            - features: Dict of enabled features
            - event: Event object for relationship data
            - run: Run object for registration checks (when campaign feature enabled)

    Returns:
        None: Modifies ctx dictionary in place
    """
    # Add player relationship if user_character feature is enabled
    if "user_character" in ctx["features"]:
        ctx["list"] = ctx["list"].select_related("player")

    # Add registration status annotation for campaign events
    if "campaign" in ctx["features"] and ctx["event"].parent:
        # add check if the character is signed up to the event
        ctx["list"] = ctx["list"].annotate(
            has_registration=Exists(
                RegistrationCharacterRel.objects.filter(
                    character=OuterRef("pk"), reg__run_id=ctx["run"].id, reg__cancellation_date__isnull=True
                )
            )
        )

    # Get cached relationship data for the event
    rels = get_event_rels_cache(ctx["event"]).get("characters", {})

    # Add relationship data based on enabled features
    if "relationships" in ctx["features"]:
        for el in ctx["list"]:
            el.relationships_rels = rels.get(el.id, {}).get("relationships_rels", [])

    # Add plot relationship data
    if "plot" in ctx["features"]:
        for el in ctx["list"]:
            el.plot_rels = rels.get(el.id, {}).get("plot_rels", [])

    # Add faction relationship data
    if "faction" in ctx["features"]:
        for el in ctx["list"]:
            el.faction_rels = rels.get(el.id, {}).get("faction_rels", [])

    # Add speedlarp relationship data
    if "speedlarp" in ctx["features"]:
        for el in ctx["list"]:
            el.speedlarp_rels = rels.get(el.id, {}).get("speedlarp_rels", [])

    # Add prologue relationship data
    if "prologue" in ctx["features"]:
        for el in ctx["list"]:
            el.prologue_rels = rels.get(el.id, {}).get("prologue_rels", [])

    # add character configs
    char_add_addit(ctx)


def char_add_addit(ctx: dict) -> None:
    """
    Add additional configuration data to all characters in the context list.

    This function retrieves character configuration data for all characters in an event
    and attaches it as an 'addit' attribute to each character object in the context list.

    Args:
        ctx (dict): Context dictionary containing:
            - 'event': Event object with character relationships
            - 'list': List of character objects to enhance with additional data

    Returns:
        None: Modifies character objects in-place by adding 'addit' attribute
    """
    # Initialize dictionary to store additional configuration data by character ID
    addits = {}

    # Get the event class parent for Character model to filter configurations
    event = ctx["event"].get_class_parent(Character)

    # Retrieve all character configurations for characters in this event
    for config in CharacterConfig.objects.filter(character__event=event):
        # Initialize character's config dictionary if not exists
        if config.character_id not in addits:
            addits[config.character_id] = {}

        # Store configuration value by name for this character
        addits[config.character_id][config.name] = config.value

    # Attach additional configuration data to each character in the list
    for el in ctx["list"]:
        # Add character's configuration data if available, otherwise empty dict
        if el.id in addits:
            el.addit = addits[el.id]
        else:
            el.addit = {}


def writing_view(request: HttpRequest, ctx: dict[str, Any], nm: str) -> HttpResponse:
    """
    Display writing element view with character data and relationships.

    Parameters
    ----------
    request : HttpRequest
        Django HTTP request object containing user session and request data
    ctx : dict[str, Any]
        Context dictionary containing element data and view-specific information
    nm : str
        Name of the writing element type (e.g., 'character', 'plot', etc.)

    Returns
    -------
    HttpResponse
        Rendered writing view template with populated context data

    Notes
    -----
    This function handles different writing element types with specialized logic
    for character elements including sheet data and relationship information.
    """
    # Set up base element data and retrieve complete element information
    ctx["el"] = ctx[nm]
    ctx["el"].data = ctx["el"].show_complete()
    ctx["nm"] = nm

    # Load cached event data for performance optimization
    get_event_cache_all(ctx)

    # Handle character-specific logic with sheet and relationship data
    if nm == "character":
        if ctx["el"].number in ctx["chars"]:
            ctx["char"] = ctx["chars"][ctx["el"].number]
        ctx["character"] = ctx["el"]

        # Retrieve character sheet and relationship information
        get_character_sheet(ctx)
        get_character_relationships(ctx)
    else:
        # Process non-character elements with applicable questions
        applicable = QuestionApplicable.get_applicable(nm)
        if applicable:
            ctx["element"] = get_writing_element_fields(ctx, nm, applicable, ctx["el"].id, only_visible=False)

        # Set sheet data for non-character elements
        ctx["sheet_char"] = ctx["el"].show_complete()

    # Add plot-specific character relationships if element is a plot
    if nm == "plot":
        ctx["sheet_plots"] = (
            PlotCharacterRel.objects.filter(plot=ctx["el"]).order_by("character__number").select_related("character")
        )

    return render(request, "larpmanager/orga/writing/view.html", ctx)


def writing_versions(request: HttpRequest, ctx: dict, nm: str, tp: str) -> HttpResponse:
    """Display text versions with diff comparison for writing elements.

    This function retrieves all text versions for a specific writing element,
    computes diffs between consecutive versions, and renders them in a template.

    Args:
        request: The HTTP request object containing user and session data.
        ctx: Context dictionary containing writing element data and template variables.
        nm: Name/key of the writing element in the context dictionary.
        tp: Type identifier used to filter text versions from the database.

    Returns:
        HttpResponse: Rendered HTML response using the versions template with
                     diff data and version history.
    """
    # Retrieve all text versions for the specified element, ordered by version number
    ctx["versions"] = TextVersion.objects.filter(tp=tp, eid=ctx[nm].id).order_by("version").select_related("member")

    # Initialize variable to track the previous version for diff computation
    last = None

    # Iterate through versions to compute diffs between consecutive versions
    for v in ctx["versions"]:
        if last is not None:
            # Compute diff between current and previous version
            compute_diff(v, last)
        else:
            # For the first version, just format text with line breaks
            v.diff = v.text.replace("\n", "<br />")
        last = v

    # Set template context variables for rendering
    ctx["element"] = ctx[nm]
    ctx["typ"] = nm

    # Render and return the versions template with populated context
    return render(request, "larpmanager/orga/writing/versions.html", ctx)


def replace_character_names_before_save(instance: Character) -> None:
    """Django signal handler to replace character names before saving.

    This function is called before a Character instance is saved to the database.
    It replaces character names in writing content only for existing characters
    (those with a primary key).

    Args:
        instance: Character instance being saved to the database.

    Returns:
        None

    Note:
        This function is designed to be used as a Django signal handler.
        It skips processing for new character instances without a primary key.
    """
    # Skip processing for new character instances without a primary key
    if not instance.pk:
        return

    # Replace character names in all associated writing content
    replace_character_names_in_writing(instance)
