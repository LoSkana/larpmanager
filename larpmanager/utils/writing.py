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
from larpmanager.cache.config import get_event_config
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


def writing_popup_question(ctx, idx, question_idx):
    """Get writing question data for popup display.

    Args:
        ctx: Context dictionary with event and writing element data
        idx (int): Writing element ID
        question_idx (int): Question index

    Returns:
        dict: Question data for popup rendering
    """
    try:
        char = Character.objects.get(pk=idx, event=ctx["event"].get_class_parent(Character))
        question = WritingQuestion.objects.get(pk=question_idx, event=ctx["event"].get_class_parent(WritingQuestion))
        el = WritingAnswer.objects.get(element_id=char.id, question=question)
        tx = f"<h2>{char} - {question.name}</h2>" + el.text
        return JsonResponse({"k": 1, "v": tx})
    except ObjectDoesNotExist:
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


def writing_example(ctx, typ):
    """Generate example writing content for a given type.

    Args:
        ctx: Context dictionary with event information
        typ (str): Type of writing element to generate example for

    Returns:
        dict: Example content and structure for the writing type
    """
    file_rows = typ.get_example_csv(ctx["features"])

    buffer = io.StringIO()
    wr = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    wr.writerows(file_rows)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=example.csv"

    return response


def writing_post(request, ctx, typ, nm):
    """Handle POST requests for writing operations.

    Args:
        request: Django HTTP request object
        ctx: Context dictionary with event data
        typ: Writing element type class
        nm: Template name

    Raises:
        ReturnNowError: When download operation needs to return immediately
    """
    if not request.POST:
        return

    if request.POST.get("download") == "1":
        raise ReturnNowError(download(ctx, typ, nm))

    if request.POST.get("example") == "1":
        raise ReturnNowError(writing_example(ctx, typ))

    if request.POST.get("popup") == "1":
        raise ReturnNowError(writing_popup(request, ctx, typ))


def writing_list(
    request: HttpRequest, ctx: dict[str, Any], writing_type: type[Model], template_name: str
) -> HttpResponse:
    """Handle writing list display with POST processing and bulk operations.

    Manages writing element lists with form submission processing,
    bulk operations, and proper context preparation for different writing types.

    Args:
        request: The HTTP request object containing user data and parameters
        ctx: Context dictionary containing event data and other shared state
        writing_type: Model class type for the writing element (Character, Plot, etc.)
        template_name: Name string used for template and URL routing

    Returns:
        HttpResponse: Rendered template response for the writing list page

    Note:
        This function modifies the ctx dictionary in-place and handles various
        writing types through conditional logic and specialized helper functions.
    """
    # Process any POST data for writing operations
    writing_post(request, ctx, writing_type, template_name)

    # Handle bulk operations on writing elements
    writing_bulk(ctx, request, writing_type)

    # Extract event from context for query operations
    event = ctx["event"]
    ctx["nm"] = template_name

    # Get text fields configuration and writing query results
    text_fields, writing = writing_list_query(ctx, event, writing_type)

    # Apply type-specific context modifications based on model type
    if issubclass(writing_type, Character):
        writing_list_char(ctx)

    if issubclass(writing_type, Plot):
        writing_list_plot(ctx)

    if issubclass(writing_type, Faction):
        writing_list_faction(ctx)

    # Handle speed LARP specific context setup
    if issubclass(writing_type, SpeedLarp):
        writing_list_speedlarp(ctx)

    if issubclass(writing_type, Prologue):
        writing_list_prologue(ctx)

    # Configure quest and quest type specific contexts
    if issubclass(writing_type, Quest):
        writing_list_quest(ctx)

    if issubclass(writing_type, QuestType):
        writing_list_questtype(ctx)

    # Add prerequisites prefetching for ability experience types
    if issubclass(writing_type, AbilityPx):
        ctx["list"] = ctx["list"].prefetch_related("prerequisites")

    # Setup writing-specific context if writing elements exist
    if writing:
        # noinspection PyProtectedMember, PyUnresolvedReferences
        ctx["label_typ"] = writing_type._meta.model_name
        ctx["writing_typ"] = QuestionApplicable.get_applicable(ctx["label_typ"])

        # Configure upload/download paths if writing type is applicable
        if ctx["writing_typ"]:
            ctx["upload"] = f"{template_name}s"
            ctx["download"] = f"{template_name}s"

        # Setup progress assignment and text field handling
        orga_list_progress_assign(ctx, writing_type)  # pyright: ignore[reportArgumentType]
        writing_list_text_fields(ctx, text_fields, writing_type)

        # Prepare final context elements for rendering
        _prepare_writing_list(ctx, request)
        _setup_char_finder(ctx, writing_type)
        _get_custom_form(ctx)

    # Render the appropriate template based on the name parameter
    return render(request, "larpmanager/orga/writing/" + template_name + "s.html", ctx)


def writing_bulk(ctx, request, typ):
    """Handle bulk operations for different writing element types.

    Args:
        ctx: Context dictionary with event data
        request: Django HTTP request object
        typ: Writing element type class

    Side effects:
        Executes bulk operations through type-specific handlers
    """
    bulks = {Character: handle_bulk_characters, Quest: handle_bulk_quest, Trait: handle_bulk_trait}

    if typ in bulks:
        bulks[typ](request, ctx)


def _get_custom_form(ctx):
    """Setup custom form questions and field names for writing elements.

    Args:
        ctx: Context dictionary to populate with form data

    Side effects:
        Updates ctx with form_questions and fields_name dictionaries
    """
    if not ctx["writing_typ"]:
        return

    # default name for fields
    ctx["fields_name"] = {WritingQuestionType.NAME.value: _("Name")}

    que = ctx["event"].get_elements(WritingQuestion).order_by("order")
    que = que.filter(applicable=ctx["writing_typ"])
    ctx["form_questions"] = {}
    for q in que:
        q.basic_typ = q.typ in BaseQuestionType.get_basic_types()
        if q.typ in ctx["fields_name"].keys():
            ctx["fields_name"][q.typ] = q.name
        else:
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


def writing_list_text_fields(ctx, text_fields, typ):
    """
    Add editor-type question fields to text fields list and retrieve cached data.

    Args:
        ctx: Context dictionary with event and writing type information
        text_fields: List of text field names to extend
        typ: Writing element model class
    """
    # add editor type questions
    que = ctx["event"].get_elements(WritingQuestion).filter(applicable=ctx["writing_typ"])
    for que_id in que.filter(typ=BaseQuestionType.EDITOR).values_list("pk", flat=True):
        text_fields.append(str(que_id))

    retrieve_cache_text_field(ctx, text_fields, typ)


def retrieve_cache_text_field(ctx, text_fields, typ):
    """
    Retrieve and attach cached text field data to writing elements.

    Args:
        ctx: Context dictionary with list of elements
        text_fields: List of text field names to cache
        typ: Writing element model class
    """
    gctf = get_cache_text_field(typ, ctx["event"])
    for el in ctx["list"]:
        if el.id not in gctf:
            continue
        for f in text_fields:
            if f not in gctf[el.id]:
                continue
            (red, ln) = gctf[el.id][f]
            setattr(el, f + "_red", red)
            setattr(el, f + "_ln", ln)


def _prepare_writing_list(ctx, request):
    """Prepare context data for writing list display and configuration.

    Args:
        ctx: Template context dictionary to update
        request: HTTP request object with user information
    """
    try:
        name_que = (
            ctx["event"]
            .get_elements(WritingQuestion)
            .filter(applicable=ctx["writing_typ"], typ=WritingQuestionType.NAME)
        )
        ctx["name_que_id"] = name_que.values_list("id", flat=True)[0]
    except Exception:
        pass

    model_name = ctx["label_typ"].lower()
    ctx["default_fields"] = request.user.member.get_config(f"open_{model_name}_{ctx['event'].id}", "[]")
    if ctx["default_fields"] == "[]":
        if model_name in ctx["writing_fields"]:
            lst = [f"q_{el}" for name, el in ctx["writing_fields"][model_name]["ids"].items()]
            ctx["default_fields"] = json.dumps(lst)

    ctx["auto_save"] = not get_event_config(ctx["event"].id, "writing_disable_auto", False, ctx)

    ctx["writing_unimportant"] = get_event_config(ctx["event"].id, "writing_unimportant", False, ctx)


def writing_list_plot(ctx):
    """Build character associations for plot list display.

    Args:
        ctx: Context dictionary with list of plots and event data

    Side effects:
        Adds chars dictionary to context and attaches character lists to plot objects
    """
    rels = get_event_rels_cache(ctx["event"]).get("plots", {})

    for el in ctx["list"]:
        el.character_rels = rels.get(el.id, {}).get("character_rels", [])


def writing_list_faction(ctx: dict) -> None:
    """Enriches faction objects with their character relationships from event cache."""
    # Retrieve cached faction relationships for the event
    rels = get_event_rels_cache(ctx["event"]).get("factions", {})

    # Attach character relationships to each faction in the list
    for el in ctx["list"]:
        el.character_rels = rels.get(el.id, {}).get("character_rels", [])


def writing_list_speedlarp(ctx: dict) -> None:
    """Enriches speedlarp list items with their character relationships from event cache."""
    # Retrieve speedlarp relationships from cached event data
    rels = get_event_rels_cache(ctx["event"]).get("speedlarps", {})

    # Attach character relationships to each speedlarp item
    for el in ctx["list"]:
        el.character_rels = rels.get(el.id, {}).get("character_rels", [])


def writing_list_prologue(ctx: dict) -> None:
    """Enrich prologue list items with character relationships from cache."""
    # Retrieve cached prologue relationships for the event
    rels = get_event_rels_cache(ctx["event"]).get("prologues", {})

    # Attach character relationships to each prologue in the list
    for el in ctx["list"]:
        el.character_rels = rels.get(el.id, {}).get("character_rels", [])


def writing_list_quest(ctx: dict) -> None:
    """Enrich quest list with trait relationships from cache."""
    # Retrieve cached quest relationships for the event
    rels = get_event_rels_cache(ctx["event"]).get("quests", {})

    # Attach trait relationships to each quest in the list
    for el in ctx["list"]:
        el.trait_rels = rels.get(el.id, {}).get("trait_rels", [])


def writing_list_questtype(ctx: dict) -> None:
    """Add quest relationships to each quest type in the context list."""
    # Retrieve cached quest type relationships for the event
    rels = get_event_rels_cache(ctx["event"]).get("questtypes", {})

    # Attach quest relationships to each quest type element
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


def char_add_addit(ctx):
    """
    Add additional configuration data to all characters in the context list.

    Args:
        ctx: Context dictionary containing character list and event information
    """
    addits = {}
    event = ctx["event"].get_class_parent(Character)
    for config in CharacterConfig.objects.filter(character__event=event):
        if config.character_id not in addits:
            addits[config.character_id] = {}
        addits[config.character_id][config.name] = config.value

    for el in ctx["list"]:
        if el.id in addits:
            el.addit = addits[el.id]
        else:
            el.addit = {}


def writing_view(request: HttpRequest, ctx: dict[str, Any], element_type_name: str) -> HttpResponse:
    """
    Display writing element view with character data and relationships.

    Args:
        request: HTTP request object containing user session and request data
        ctx: Context dictionary containing element data and cached information
        element_type_name: Name of the writing element type (e.g., 'character', 'plot')

    Returns:
        HttpResponse: Rendered writing view template with populated context data

    Note:
        This function handles different writing element types and populates the context
        with appropriate data for rendering. Special handling is provided for character
        and plot elements.
    """
    # Set up base element data and context
    ctx["el"] = ctx[element_type_name]
    ctx["el"].data = ctx["el"].show_complete()
    ctx["nm"] = element_type_name

    # Load event cache data for all related elements
    get_event_cache_all(ctx)

    # Handle character-specific data and relationships
    if element_type_name == "character":
        if ctx["el"].number in ctx["chars"]:
            ctx["char"] = ctx["chars"][ctx["el"].number]
        ctx["character"] = ctx["el"]

        # Get character sheet and relationship data
        get_character_sheet(ctx)
        get_character_relationships(ctx)
    else:
        # Handle non-character writing elements with applicable questions
        applicable_questions = QuestionApplicable.get_applicable(element_type_name)
        if applicable_questions:
            ctx["element"] = get_writing_element_fields(
                ctx, element_type_name, applicable_questions, ctx["el"].id, only_visible=False
            )
        ctx["sheet_char"] = ctx["el"].show_complete()

    # Add plot-specific character relationships
    if element_type_name == "plot":
        ctx["sheet_plots"] = (
            PlotCharacterRel.objects.filter(plot=ctx["el"]).order_by("character__number").select_related("character")
        )

    return render(request, "larpmanager/orga/writing/view.html", ctx)


def writing_versions(request, ctx, element_name, version_type):
    """Display text versions with diff comparison for writing elements.

    Args:
        request: HTTP request object
        ctx: Context dictionary with writing element data
        element_name: Name of the writing element
        version_type: Type identifier for text versions

    Returns:
        HttpResponse: Rendered versions template with diff data
    """
    ctx["versions"] = (
        TextVersion.objects.filter(tp=version_type, eid=ctx[element_name].id)
        .order_by("version")
        .select_related("member")
    )
    previous_version = None
    for current_version in ctx["versions"]:
        if previous_version is not None:
            compute_diff(current_version, previous_version)
        else:
            current_version.diff = current_version.text.replace("\n", "<br />")
        previous_version = current_version
    ctx["element"] = ctx[element_name]
    ctx["typ"] = element_name
    return render(request, "larpmanager/orga/writing/versions.html", ctx)


def replace_character_names_before_save(instance):
    """Django signal handler to replace character names before saving.

    Args:
        sender: Model class sending the signal
        instance: Character instance being saved
        *args: Additional positional arguments
        **kwargs: Additional keyword arguments
    """
    if not instance.pk:
        return

    replace_character_names_in_writing(instance)
