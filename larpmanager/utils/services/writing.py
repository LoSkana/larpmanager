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
import logging
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
    replace_character_names,
)
from larpmanager.templatetags.show_tags import show_char, show_trait
from larpmanager.utils.core.common import check_field, compute_diff
from larpmanager.utils.core.exceptions import ReturnNowError
from larpmanager.utils.edit.backend import _setup_char_finder
from larpmanager.utils.io.download import download
from larpmanager.utils.services.bulk import handle_bulk_characters, handle_bulk_quest, handle_bulk_trait
from larpmanager.utils.services.character import get_character_relationships, get_character_sheet

logger = logging.getLogger(__name__)


def orga_list_progress_assign(context: dict, typ: type[Model]) -> None:
    """Set up progress and assignment tracking for writing elements.

    Populates the context dictionary with progress steps, assignments, and their
    respective mapping counters based on available features. Counts occurrences
    of each progress step and assignment combination in the provided list.

    Args:
        context: Context dictionary to populate with progress/assignment data.
             Must contain 'features', 'event', and 'list' keys.
        typ: Model type being processed (Character, Plot, etc.)

    Returns:
        None: Function modifies context in-place

    Side Effects:
        Updates context with the following keys:
        - progress_steps: Dict mapping progress step IDs to their string representations
        - progress_steps_map: Counter dict for progress step occurrences
        - assigned: Dict mapping member IDs to their display names
        - assigned_map: Counter dict for assignment occurrences
        - progress_assigned_map: Counter dict for progress/assignment combinations
        - typ: String representation of the model type

    """
    features = context["features"]
    event = context["event"]

    # Initialize progress tracking if feature is enabled
    if "progress" in features:
        context["progress_steps"] = {
            step.id: str(step) for step in ProgressStep.objects.filter(event=event).order_by("order")
        }
        context["progress_steps_map"] = dict.fromkeys(context["progress_steps"], 0)

    # Initialize assignment tracking if feature is enabled
    if "assigned" in features:
        context["assigned"] = {member.id: member.show_nick() for member in get_event_staffers(event)}
        context["assigned_map"] = dict.fromkeys(context["assigned"], 0)

    # Initialize combined progress/assignment tracking if both features enabled
    if "progress" in features and "assigned" in features:
        context["progress_assigned_map"] = {
            f"{progress_id}_{assigned_id}": 0
            for progress_id in context["progress_steps"]
            for assigned_id in context["assigned"]
        }

    # Count occurrences of progress steps and assignments in the list
    for element in context["list"]:
        progress_id = element.progress_id
        assigned_id = element.assigned_id

        # Increment progress step counter
        if "progress" in features and progress_id in context.get("progress_steps_map", {}):
            context["progress_steps_map"][progress_id] += 1

        # Increment assignment counter
        if "assigned" in features and assigned_id in context.get("assigned_map", {}):
            context["assigned_map"][assigned_id] += 1

        # Increment combined progress/assignment counter
        if "progress" in features and "assigned" in features:
            key = f"{progress_id}_{assigned_id}"
            if key in context.get("progress_assigned_map", {}):
                context["progress_assigned_map"][key] += 1

    # Store simplified model type name for template usage
    context["typ"] = str(typ._meta).replace("larpmanager.", "")  # type: ignore[attr-defined]  # noqa: SLF001  # Django model metadata


def writing_popup_question(context: dict, idx: Any, question_idx: Any) -> Any:
    """Get writing question data for popup display.

    Args:
        context: Context dictionary with event and writing element data
        idx (int): Writing element ID
        question_idx (int): Question index

    Returns:
        dict: Question data for popup rendering

    """
    try:
        character = Character.objects.get(pk=idx, event=context["event"].get_class_parent(Character))
        question = WritingQuestion.objects.get(
            pk=question_idx,
            event=context["event"].get_class_parent(WritingQuestion),
        )
        writing_answer = WritingAnswer.objects.get(element_id=character.id, question=question)
        html_text = f"<h2>{character} - {question.name}</h2>" + writing_answer.text
        return JsonResponse({"k": 1, "v": html_text})
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})


def writing_popup(request: HttpRequest, context: dict, typ: type[Model]) -> JsonResponse:
    """Handle writing element popup requests.

    Args:
        request: Django HTTP request object containing POST data with idx and tp parameters
        context: Context dictionary containing event data and cached information
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
    get_event_cache_all(context)

    # Parse and validate the index parameter from POST data
    try:
        element_id = int(request.POST.get("idx", ""))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid idx parameter"}, status=400)

    # Extract the type parameter for attribute lookup
    attribute_type = request.POST.get("tp", "")

    # Check if this is a character question request (numeric tp indicates question)
    try:
        question_id = int(attribute_type)
        return writing_popup_question(context, element_id, question_id)
    except ValueError:
        # Not a question, continue with regular element handling
        pass

    # Retrieve the writing element from database using parent event context
    try:
        writing_element = typ.objects.get(pk=element_id, event=context["event"].get_class_parent(typ))
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    # Verify the requested attribute exists on the element
    if not hasattr(writing_element, attribute_type):
        return JsonResponse({"k": 0})

    # Build HTML response with element title and content
    html_content = f"<h2>{writing_element} - {attribute_type}</h2>"

    # Render content based on element type (traits/quests vs characters)
    if typ in [Trait, Quest]:
        html_content += show_trait(context, getattr(writing_element, attribute_type), context["run"], include_tooltip=1)
    else:
        html_content += show_char(context, getattr(writing_element, attribute_type), context["run"], include_tooltip=1)

    return JsonResponse({"k": 1, "v": html_content})


def writing_example(context: dict, typ: Any) -> Any:
    """Generate example writing content for a given type.

    Args:
        context: Context dictionary with event information
        typ (str): Type of writing element to generate example for

    Returns:
        dict: Example content and structure for the writing type

    """
    example_csv_rows = typ.get_example_csv(context["features"])

    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer, quoting=csv.QUOTE_ALL)
    csv_writer.writerows(example_csv_rows)

    csv_buffer.seek(0)
    response = HttpResponse(csv_buffer, content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=example.csv"

    return response


def writing_post(request: HttpRequest, context: dict, writing_element_type: Any, template_name: Any) -> None:
    """Handle POST requests for writing operations.

    Args:
        request: Django HTTP request object
        context: Context dictionary with event data
        writing_element_type: Writing element type class
        template_name: Template name

    Raises:
        ReturnNowError: When download operation needs to return immediately

    """
    if not request.POST:
        return

    if request.POST.get("download") == "1":
        raise ReturnNowError(download(context, writing_element_type, template_name))

    if request.POST.get("example") == "1":
        raise ReturnNowError(writing_example(context, writing_element_type))

    if request.POST.get("popup") == "1":
        raise ReturnNowError(writing_popup(request, context, writing_element_type))


def writing_list(  # noqa: C901 - Complex writing list building with feature-dependent filtering
    request: HttpRequest,
    context: dict,
    writing_type: type[Model],
    template_name: str,
) -> HttpResponse:
    """Handle writing list display with POST processing and bulk operations.

    Manages writing element lists with form submission processing,
    bulk operations, and proper context preparation for different writing types.

    Args:
        request: The HTTP request object containing user data and parameters
        context: Context dictionary containing event data and other shared state
        writing_type: Model class type for the writing element (Character, Plot, etc.)
        template_name: Name string used for template and URL routing

    Returns:
        HttpResponse: Rendered template response for the writing list page

    Note:
        This function modifies the context dictionary in-place and handles various
        writing types through conditional logic and specialized helper functions.

    """
    # Process any POST data for writing operations
    writing_post(request, context, writing_type, template_name)

    # Handle bulk operations on writing elements
    writing_bulk(context, request, writing_type)

    # Extract event from context for query operations
    event = context["event"]
    context["nm"] = template_name

    # Get text fields configuration and writing query results
    text_fields, writing = writing_list_query(context, event, writing_type)

    # Apply type-specific context modifications based on model type
    if issubclass(writing_type, Character):
        writing_list_char(context)

    if issubclass(writing_type, Plot):
        writing_list_plot(context)

    if issubclass(writing_type, Faction):
        writing_list_faction(context)

    # Handle speed LARP specific context setup
    if issubclass(writing_type, SpeedLarp):
        writing_list_speedlarp(context)

    if issubclass(writing_type, Prologue):
        writing_list_prologue(context)

    # Configure quest and quest type specific contexts
    if issubclass(writing_type, Quest):
        writing_list_quest(context)

    if issubclass(writing_type, QuestType):
        writing_list_questtype(context)

    # Add prerequisites prefetching for ability experience types
    if issubclass(writing_type, AbilityPx):
        context["list"] = context["list"].prefetch_related("prerequisites")

    # Setup writing-specific context if writing elements exist
    if writing:
        # noinspection PyProtectedMember, PyUnresolvedReferences
        context["label_typ"] = writing_type._meta.model_name  # noqa: SLF001  # Django model metadata
        context["writing_typ"] = QuestionApplicable.get_applicable(context["label_typ"])

        # Configure upload/download paths if writing type is applicable
        if context["writing_typ"]:
            context["upload"] = f"{template_name}s"
            context["download"] = f"{template_name}s"

        # Setup progress assignment and text field handling
        orga_list_progress_assign(context, writing_type)  # pyright: ignore[reportArgumentType]
        writing_list_text_fields(context, text_fields, writing_type)

        # Prepare final context elements for rendering
        _prepare_writing_list(context)
        _setup_char_finder(context, writing_type)
        _get_custom_form(context)

    # Render the appropriate template based on the name parameter
    return render(request, "larpmanager/orga/writing/" + template_name + "s.html", context)


def writing_bulk(context: dict, request: HttpRequest, typ: Any) -> None:
    """Handle bulk operations for different writing element types.

    Args:
        context: Context dictionary with event data
        request: Django HTTP request object
        typ: Writing element type class

    Side effects:
        Executes bulk operations through type-specific handlers

    """
    type_to_bulk_handler = {Character: handle_bulk_characters, Quest: handle_bulk_quest, Trait: handle_bulk_trait}

    if typ in type_to_bulk_handler:
        type_to_bulk_handler[typ](request, context)


def _get_custom_form(context: dict) -> None:
    """Set up custom form questions and field names for writing elements.

    Args:
        context: Context dictionary to populate with form data

    Side effects:
        Updates context with form_questions and fields_name dictionaries

    """
    if not context["writing_typ"]:
        return

    # default name for fields
    context["fields_name"] = {WritingQuestionType.NAME.value: _("Name")}

    questions = context["event"].get_elements(WritingQuestion).order_by("order")
    questions = questions.filter(applicable=context["writing_typ"])
    context["form_questions"] = {}
    for question in questions:
        question.basic_typ = question.typ in BaseQuestionType.get_basic_types()
        if question.typ in context["fields_name"]:
            context["fields_name"][question.typ] = question.name
        else:
            context["form_questions"][question.uuid] = question


def writing_list_query(context: dict, event: Any, model_type: Any) -> tuple[list[str], bool]:
    """Build optimized database query for writing element lists.

    Constructs an efficient Django ORM query for retrieving writing elements
    with appropriate select_related and prefetch_related optimizations based
    on the model type and available features.

    Args:
        context: Context dictionary to store query results under 'list' key.
        event: Event instance used to determine the parent event for filtering.
        model_type: Writing element model class to query against.

    Returns:
        A tuple containing:
            - list[str]: Text fields that were deferred from the query
            - bool: Whether the model is a Writing subclass

    """
    # Determine if this is a Writing model and set up basic query structure
    is_writing_model = issubclass(model_type, Writing)
    deferred_text_fields = ["teaser", "text"]
    context["list"] = model_type.objects.filter(event=event.get_class_parent(model_type))

    # Optimize query with select_related for Writing models with progress tracking
    if is_writing_model and hasattr(model_type, "progress"):
        context["list"] = context["list"].select_related("progress", "assigned")

    # Defer large text fields for Writing models to improve performance
    if is_writing_model:
        for field_name in deferred_text_fields:
            context["list"] = context["list"].defer(field_name)

    # Apply ordering based on available fields: order > number > updated
    if check_field(model_type, "order"):
        context["list"] = context["list"].order_by("order")
    elif check_field(model_type, "number"):
        context["list"] = context["list"].order_by("number")
    else:
        context["list"] = context["list"].order_by("-updated")

    return deferred_text_fields, is_writing_model


def writing_list_text_fields(context: dict, text_fields: Any, writing_element_type: Any) -> None:
    """Add editor-type question fields to text fields list and retrieve cached data.

    Args:
        context: Context dictionary with event and writing type information
        text_fields: List of text field names to extend
        writing_element_type: Writing element model class

    """
    # add editor type questions
    writing_questions = context["event"].get_elements(WritingQuestion).filter(applicable=context["writing_typ"])
    text_fields.extend(writing_questions.filter(typ=BaseQuestionType.EDITOR).values_list("uuid", flat=True))

    retrieve_cache_text_field(context, text_fields, writing_element_type)


def retrieve_cache_text_field(context: dict, text_fields: Any, element_type: Any) -> None:
    """Retrieve and attach cached text field data to writing elements.

    Args:
        context: Context dictionary with list of elements
        text_fields: List of text field names to cache
        element_type: Writing element model class

    """
    cached_text_fields = get_cache_text_field(element_type, context["event"])
    for element in context["list"]:
        if element.id not in cached_text_fields:
            continue
        for field_name in text_fields:
            if field_name not in cached_text_fields[element.id]:
                continue
            (rendered_text, line_count) = cached_text_fields[element.id][field_name]
            setattr(element, field_name + "_red", rendered_text)
            setattr(element, field_name + "_ln", line_count)


def _prepare_writing_list(context: dict) -> None:
    """Prepare context data for writing list display and configuration."""
    try:
        name_question = (
            context["event"]
            .get_elements(WritingQuestion)
            .filter(applicable=context["writing_typ"], typ=WritingQuestionType.NAME)
        )
        context["name_que_uuid"] = name_question.values_list("uuid", flat=True)[0]
    except IndexError as e:
        logger.debug("Name question not found for writing type %s: %s", context["writing_typ"], e)

    model_name = context["label_typ"].lower()
    context["default_fields"] = context["member"].get_config(
        f"open_{model_name}_{context['event'].id}", default_value="[]"
    )
    if context["default_fields"] == "[]" and model_name in context["writing_fields"]:
        question_field_list = [
            f"q_{question_uuid}" for name, question_uuid in context["writing_fields"][model_name]["uuids"].items()
        ]
        context["default_fields"] = json.dumps(question_field_list)

    context["auto_save"] = not get_event_config(
        context["event"].id, "writing_disable_auto", default_value=False, context=context
    )

    context["writing_unimportant"] = get_event_config(
        context["event"].id, "writing_unimportant", default_value=False, context=context
    )


def writing_list_plot(context: dict) -> None:
    """Build character associations for plot list display.

    Args:
        context: Context dictionary with list of plots and event data

    Side effects:
        Adds chars dictionary to context and attaches character lists to plot objects

    """
    event_relationships = get_event_rels_cache(context["event"]).get("plots", {})

    for plot in context["list"]:
        plot.character_rels = event_relationships.get(plot.id, {}).get("character_rels", [])


def writing_list_faction(context: dict) -> None:
    """Enriches faction objects with their character relationships from event cache."""
    # Retrieve cached faction relationships for the event
    faction_relationships = get_event_rels_cache(context["event"]).get("factions", {})

    # Attach character relationships to each faction in the list
    for faction in context["list"]:
        faction.character_rels = faction_relationships.get(faction.id, {}).get("character_rels", [])


def writing_list_speedlarp(context: dict) -> None:
    """Enriches speedlarp list items with their character relationships from event cache."""
    # Retrieve speedlarp relationships from cached event data
    speedlarp_relationships = get_event_rels_cache(context["event"]).get("speedlarps", {})

    # Attach character relationships to each speedlarp item
    for speedlarp_item in context["list"]:
        speedlarp_item.character_rels = speedlarp_relationships.get(speedlarp_item.id, {}).get("character_rels", [])


def writing_list_prologue(context: dict) -> None:
    """Enrich prologue list items with character relationships from cache."""
    # Retrieve cached prologue relationships for the event
    prologue_relationships = get_event_rels_cache(context["event"]).get("prologues", {})

    # Attach character relationships to each prologue in the list
    for prologue in context["list"]:
        prologue.character_rels = prologue_relationships.get(prologue.id, {}).get("character_rels", [])


def writing_list_quest(context: dict) -> None:
    """Enrich quest list with trait relationships from cache."""
    # Retrieve cached quest relationships for the event
    quest_relationships = get_event_rels_cache(context["event"]).get("quests", {})

    # Attach trait relationships to each quest in the list
    for quest in context["list"]:
        quest.trait_rels = quest_relationships.get(quest.id, {}).get("trait_rels", [])


def writing_list_questtype(context: dict) -> None:
    """Add quest relationships to each quest type in the context list."""
    # Retrieve cached quest type relationships for the event
    quest_type_relationships = get_event_rels_cache(context["event"]).get("questtypes", {})

    # Attach quest relationships to each quest type element
    for quest_type in context["list"]:
        quest_type.quest_rels = quest_type_relationships.get(quest_type.id, {}).get("quest_rels", [])


def writing_list_char(context: dict) -> None:  # noqa: C901 - Complex character enhancement with multiple feature integrations
    """Enhance character list with feature-specific data and relationships.

    This function modifies the character list in the context by adding feature-specific
    data such as player relationships, registration status, and various relationship types
    based on enabled features.

    Args:
        context: Context dictionary containing:
            - list: QuerySet of characters to enhance
            - features: Dict of enabled features
            - event: Event object for relationship data
            - run: Run object for registration checks (when campaign feature enabled)

    Returns:
        None: Modifies context dictionary in place

    """
    # Add player relationship if user_character feature is enabled
    if "user_character" in context["features"]:
        context["list"] = context["list"].select_related("player")

    # Add registration status annotation for campaign events
    if "campaign" in context["features"] and context["event"].parent:
        # add check if the character is signed up to the event
        context["list"] = context["list"].annotate(
            has_registration=Exists(
                RegistrationCharacterRel.objects.filter(
                    character=OuterRef("pk"),
                    registration__run_id=context["run"].id,
                    registration__cancellation_date__isnull=True,
                ),
            ),
        )

    # Get cached relationship data for the event
    event_relationships = get_event_rels_cache(context["event"]).get("characters", {})

    # Add relationship data based on enabled features
    if "relationships" in context["features"]:
        for character in context["list"]:
            character.relationships_rels = event_relationships.get(character.id, {}).get("relationships_rels", [])

    # Add plot relationship data
    if "plot" in context["features"]:
        for character in context["list"]:
            character.plot_rels = event_relationships.get(character.id, {}).get("plot_rels", [])

    # Add faction relationship data
    if "faction" in context["features"]:
        for character in context["list"]:
            character.faction_rels = event_relationships.get(character.id, {}).get("faction_rels", [])

    # Add speedlarp relationship data
    if "speedlarp" in context["features"]:
        for character in context["list"]:
            character.speedlarp_rels = event_relationships.get(character.id, {}).get("speedlarp_rels", [])

    # Add prologue relationship data
    if "prologue" in context["features"]:
        for character in context["list"]:
            character.prologue_rels = event_relationships.get(character.id, {}).get("prologue_rels", [])

    # add character configs
    char_add_addit(context)


def char_add_addit(context: dict) -> None:
    """Add additional configuration data to all characters in the context list.

    Args:
        context: Context dictionary containing character list and event information

    """
    character_configs_by_id = {}
    event = context["event"].get_class_parent(Character)
    for config in CharacterConfig.objects.filter(character__event=event):
        if config.character_id not in character_configs_by_id:
            character_configs_by_id[config.character_id] = {}
        character_configs_by_id[config.character_id][config.name] = config.value

    for character in context["list"]:
        character.addit = character_configs_by_id.get(character.id, {})


def writing_view(request: HttpRequest, context: dict, element_type_name: str) -> HttpResponse:
    """Display writing element view with character data and relationships.

    Args:
        request: HTTP request object containing user session and request data
        context: Context dictionary containing element data and cached information
        element_type_name: Name of the writing element type (e.g., 'character', 'plot')

    Returns:
        HttpResponse: Rendered writing view template with populated context data

    Note:
        This function handles different writing element types and populates the context
        with appropriate data for rendering. Special handling is provided for character
        and plot elements.

    """
    # Set up base element data and context
    context["el"] = context[element_type_name]
    context["el"].data = context["el"].show_complete()
    context["nm"] = element_type_name

    # Load event cache data for all related elements
    get_event_cache_all(context)

    # Handle character-specific data and relationships
    if element_type_name == "character":
        if context["el"].number in context["chars"]:
            context["char"] = context["chars"][context["el"].number]
        context["character"] = context["el"]

        # Get character sheet and relationship data
        get_character_sheet(context)
        get_character_relationships(context)
    else:
        # Handle non-character writing elements with applicable questions
        applicable_questions = QuestionApplicable.get_applicable(element_type_name)
        if applicable_questions:
            context["element"] = get_writing_element_fields(
                context,
                element_type_name,
                applicable_questions,
                context["el"].id,
                only_visible=False,
            )
        context["sheet_char"] = context["el"].show_complete()

    # Add plot-specific character relationships
    if element_type_name == "plot":
        context["sheet_plots"] = (
            PlotCharacterRel.objects.filter(plot=context["el"])
            .order_by("character__number")
            .select_related("character")
        )

    return render(request, "larpmanager/orga/writing/view.html", context)


def writing_versions(request: HttpRequest, context: dict, element_name: Any, version_type: Any) -> Any:
    """Display text versions with diff comparison for writing elements.

    Args:
        request: HTTP request object
        context: Context dictionary with writing element data
        element_name: Name of the writing element
        version_type: Type identifier for text versions

    Returns:
        HttpResponse: Rendered versions template with diff data

    """
    context["versions"] = (
        TextVersion.objects.filter(tp=version_type, eid=context[element_name].id)
        .order_by("version")
        .select_related("member")
    )
    previous_version = None
    for current_version in context["versions"]:
        if previous_version is not None:
            compute_diff(current_version, previous_version)
        else:
            current_version.diff = current_version.text.replace("\n", "<br />")
        previous_version = current_version
    context["element"] = context[element_name]
    context["typ"] = element_name
    return render(request, "larpmanager/orga/writing/versions.html", context)


def replace_character_names_before_save(instance: object) -> None:
    """Django signal handler to replace character names before saving."""
    if not instance.pk:
        return

    replace_character_names(instance)
