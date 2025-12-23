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

import contextlib
from typing import Any

from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Max
from django.db.models.functions import Length, Substr
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.cache.character import get_event_cache_all
from larpmanager.cache.config import get_event_config
from larpmanager.forms.character import (
    OrgaCharacterForm,
    OrgaWritingOptionForm,
    OrgaWritingQuestionForm,
)
from larpmanager.forms.utils import EventCharacterS2Widget
from larpmanager.forms.writing import FactionForm, PlotForm, QuestForm, TraitForm
from larpmanager.models.base import Feature
from larpmanager.models.casting import Trait
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
    WritingQuestionType,
    _get_writing_mapping,
)
from larpmanager.models.utils import strip_tags
from larpmanager.models.writing import (
    Character,
    Faction,
    Plot,
    PlotCharacterRel,
    Prologue,
    Relationship,
    SpeedLarp,
    TextVersionChoices,
)
from larpmanager.utils.auth.admin import is_lm_admin
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.core.common import exchange_order, get_element
from larpmanager.utils.io.download import orga_character_form_download
from larpmanager.utils.services.character import get_chars_relations
from larpmanager.utils.services.edit import backend_edit, set_suggestion, writing_edit, writing_edit_working_ticket
from larpmanager.utils.services.writing import writing_list, writing_versions, writing_view


def get_character_optimized(context: dict, character_uuid: str) -> None:
    """Get character with optimized queries for editing.

    Args:
        context: Template context dictionary
        character_uuid: Character UUID

    Raises:
        Http404: If character does not exist

    """
    try:
        parent_event = context["event"].get_class_parent(Character)
        enabled_features = context.get("features", [])

        select_related_fields = ["event"]

        # Add other select_related fields based on features
        if "user_character" in enabled_features:
            select_related_fields.append("player")
        if "progress" in enabled_features:
            select_related_fields.append("progress")
        if "assigned" in enabled_features:
            select_related_fields.append("assigned")
        if "mirror" in enabled_features:
            select_related_fields.append("mirror")

        character_query = Character.objects.select_related(*select_related_fields)

        # Only prefetch factions and plots if their features are enabled
        prefetch_fields = []
        if "faction" in enabled_features:
            prefetch_fields.append("factions_list")
        if "plot" in enabled_features:
            prefetch_fields.append("plots")

        if prefetch_fields:
            character_query = character_query.prefetch_related(*prefetch_fields)

        context["character"] = character_query.get(event=parent_event, uuid=character_uuid)
        context["class_name"] = "character"
    except ObjectDoesNotExist as err:
        msg = "character does not exist"
        raise Http404(msg) from err


@login_required
def orga_characters(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Return character list view for event organizers.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier

    Returns:
        Rendered character list template

    """
    # Check user permissions for character management
    context = check_event_context(request, event_slug, "orga_characters")

    # Load event data and configuration settings
    get_event_cache_all(context)
    for config_name in ["user_character_approval", "writing_external_access"]:
        context[config_name] = get_event_config(context["event"].id, config_name, default_value=False, context=context)

    # Enable export functionality if configured
    if get_event_config(context["event"].id, "show_export", default_value=False, context=context):
        context["export"] = "character"

    return writing_list(request, context, Character, "character")


@login_required
def orga_characters_edit(request: HttpRequest, event_slug: str, character_uuid: str) -> HttpResponse:
    """Edit character information in organization context.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: The organization/event slug identifier
        character_uuid: The character UUID to edit (0 for new character)

    Returns:
        HttpResponse: Rendered character edit form page

    """
    # Check user permissions for character organization features
    context = check_event_context(request, event_slug, "orga_characters")

    # Load full event cache only when specific features require relationship data
    # This optimization avoids expensive cache operations for basic character editing
    if "relationships" in context["features"] or "character_finder" in context.get("features", []):
        get_event_cache_all(context)

    # Load specific character data when editing existing character (num != 0)
    # Skip character loading for new character creation
    if character_uuid != 0:
        get_character_optimized(context, character_uuid)

    # Process character relationships for display and validation
    _characters_relationships(context)

    # Delegate to writing edit system with character-specific form and version type
    return writing_edit(request, context, OrgaCharacterForm, "character", TextVersionChoices.CHARACTER)


def _characters_relationships(context: dict) -> None:
    """Set up character relationships data and widgets for editing.

    Args:
        context: Context dictionary to populate with relationship data

    """
    context["relationships"] = {}
    if "relationships" not in context["features"]:
        return

    with contextlib.suppress(ObjectDoesNotExist):
        context["rel_tutorial"] = Feature.objects.get(slug="relationships").tutorial

    context["TINYMCE_DEFAULT_CONFIG"] = conf_settings.TINYMCE_DEFAULT_CONFIG
    widget = EventCharacterS2Widget(attrs={"id": "new_rel_select"})
    widget.set_event(context["event"])
    context["new_rel"] = widget.render(name="new_rel_select", value="")

    if "character" in context:
        relationships_by_character_id = {}

        direct_relationships = Relationship.objects.filter(source=context["character"]).select_related("target")

        for relationship in direct_relationships:
            if relationship.target.id not in relationships_by_character_id:
                relationships_by_character_id[relationship.target.id] = {"char": relationship.target}
            relationships_by_character_id[relationship.target.id]["direct"] = relationship.text

        inverse_relationships = Relationship.objects.filter(target=context["character"]).select_related("source")

        for relationship in inverse_relationships:
            if relationship.source.id not in relationships_by_character_id:
                relationships_by_character_id[relationship.source.id] = {"char": relationship.source}
            relationships_by_character_id[relationship.source.id]["inverse"] = relationship.text

        sorted_relationships = sorted(
            relationships_by_character_id.items(),
            key=lambda character_entry: len(character_entry[1].get("direct", ""))
            + len(character_entry[1].get("inverse", "")),
            reverse=True,
        )
        context["relationships"] = dict(sorted_relationships)


def update_relationship(request: HttpRequest, context: dict, nm: str, fl: str) -> None:
    """Update relationship texts from POST data."""
    for d in context[nm]:
        # Get the identifier for this relationship item
        idx = getattr(d, fl).number

        # Update Italian text if provided
        c = request.POST.get(f"{nm}_text_{idx}")
        if c:
            d.text = c

        # Update English text if provided
        c = request.POST.get(f"{nm}_text_eng_{idx}")
        if c:
            d.text_eng = c

        d.save()


@login_required
def orga_characters_relationships(request: HttpRequest, event_slug: str, character_uuid: str) -> HttpResponse:
    """Display character relationships for organization view.

    Shows both direct relationships (where character is source) and inverse
    relationships (where character is target), ordered by text length and
    character number.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        character_uuid: Character uuid

    Returns:
        Rendered HTML response with character relationships

    """
    # Check user permissions for character management
    context = check_event_context(request, event_slug, "orga_characters")

    # Load character data into context
    get_element(context, character_uuid, "character", Character)

    # Get relationships where this character is the source
    # Ordered by text length (ascending) then target character number
    context["direct"] = (
        Relationship.objects.filter(source=context["character"])
        .select_related("target")
        .order_by(Length("text").asc(), "target__number")
    )

    # Get relationships where this character is the target
    # Ordered by text length (ascending) then source character number
    context["inverse"] = (
        Relationship.objects.filter(target=context["character"])
        .select_related("source")
        .order_by(Length("text").asc(), "source__number")
    )

    # Render the relationships template with context data
    return render(request, "larpmanager/orga/characters/relationships.html", context)


@login_required
def orga_characters_view(request: HttpRequest, event_slug: str, character_uuid: str) -> HttpResponse:
    """Display character view for event organizers.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        character_uuid: Character uuid

    Returns:
        Rendered writing view for character

    """
    # Check permissions and initialize context
    context = check_event_context(request, event_slug, ["orga_reading", "orga_characters"])

    # Load character and event cache data
    get_element(context, character_uuid, "character", Character)
    get_event_cache_all(context)

    return writing_view(request, context, "character")


@login_required
def orga_characters_versions(request: HttpRequest, event_slug: str, character_uuid: str) -> HttpResponse:
    """Display version history for a character's writing content."""
    # Check event permission and get context
    context = check_event_context(request, event_slug, "orga_characters")

    # Retrieve the character and render version history
    get_element(context, character_uuid, "character", Character)
    return writing_versions(request, context, "character", TextVersionChoices.CHARACTER)


@login_required
def orga_characters_summary(request: HttpRequest, event_slug: str, character_uuid: str) -> HttpResponse:
    """Display character summary page for organization staff.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        character_uuid: Character uuid

    Returns:
        Rendered HTML response with character summary

    """
    # Check permissions and get base context
    context = check_event_context(request, event_slug, "orga_characters")

    # Load character with prefetched factions and plots
    context["character"] = Character.objects.prefetch_related("factions_list__characters", "plots__characters").get(
        uuid=character_uuid
    )

    # Initialize factions list in context
    context["factions"] = []

    # Process character factions with complete data
    for p in context["character"].factions_list.all():
        context["factions"].append(p.show_complete())

    # Initialize plots list in context
    context["plots"] = []

    # Process character plots with complete data
    for p in context["character"].plots.all():
        context["plots"].append(p.show_complete())

    # Render template with populated context
    return render(request, "larpmanager/orga/characters_summary.html", context)


@login_required
def orga_writing_form_list(request: HttpRequest, event_slug: str, writing_type: str) -> JsonResponse:
    """Generate form list data for writing questions in JSON format.

    Processes writing questions and their answers for display in organizer interface,
    handling different question types (single, multiple choice, text, paragraph).

    Args:
        request: HTTP request object containing POST data with question ID
        event_slug: Event slug identifier
        writing_type: Question type identifier for filtering applicable questions

    Returns:
        JsonResponse: JSON response containing question results, popup indicators,
                     and question ID for frontend processing

    Raises:
        PermissionDenied: If user lacks required event permissions
        Http404: If question or event not found

    """
    # Check user permissions and get event context
    context = check_event_context(request, event_slug, "orga_characters")
    check_writing_form_type(context, writing_type)
    event = context["event"]

    # Use parent event if current event is a child
    if event.parent:
        event = event.parent

    # Get question ID from POST data
    eid = request.POST.get("num")

    # Determine applicable question type and get related element IDs
    applicable = QuestionApplicable.get_applicable(writing_type)
    element_typ = QuestionApplicable.get_applicable_inverse(applicable)
    element_ids = element_typ.objects.filter(event=event).values_list("id", flat=True)

    # Initialize response data structures
    res = {}
    popup = []
    max_length = 100

    # Get the specific question being processed
    question = event.get_elements(WritingQuestion).get(pk=eid, applicable=applicable)

    # Handle single/multiple choice questions
    if question.typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
        # Build choice options dictionary
        cho = {}
        for opt in event.get_elements(WritingOption).filter(question=question):
            cho[opt.id] = opt.name

        # Process choices and group by element ID
        for el in (
            WritingChoice.objects.filter(question=question, element_id__in=element_ids)
            .select_related("option")
            .order_by("option__order")
        ):
            if el.element_id not in res:
                res[el.element_id] = []
            res[el.element_id].append(cho[el.option_id])

    # Handle text, paragraph, and computed questions
    elif question.typ in [BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, WritingQuestionType.COMPUTED]:
        # Query answers with text truncation for preview
        que = WritingAnswer.objects.filter(question=question, element_id__in=element_ids)
        que = que.annotate(short_text=Substr("text", 1, max_length))
        que = que.values("element_id", "short_text")

        # Process each answer and mark long texts for popup display
        for el in que:
            answer = el["short_text"]
            if len(answer) == max_length:
                popup.append(el["element_id"])
            res[el["element_id"]] = answer

    return JsonResponse({"res": res, "popup": popup, "num": question.id})


@login_required
def orga_writing_form_email(request: HttpRequest, event_slug: str, writing_type: str) -> JsonResponse | None:
    """Generate email data for writing form options by character choices.

    This function processes writing form questions and returns email data
    organized by the choices characters made for specific question options.

    Args:
        request: The HTTP request object containing POST data
        event_slug: Event identifier string
        writing_type: Writing form type identifier

    Returns:
        JsonResponse containing email data organized by option choices.
        Each option maps to a dict with 'emails' (character names) and
        'names' (player names) lists.

    Raises:
        Http404: If event permission check fails or writing form type is invalid

    """
    # Check event permissions and validate writing form type
    context = check_event_context(request, event_slug, "orga_characters")
    check_writing_form_type(context, writing_type)

    # Get the parent event if this is a child event
    event = context["event"]
    if event.parent:
        event = event.parent

    # Retrieve the specific writing question from POST data
    eid = request.POST.get("num")
    q = event.get_elements(WritingQuestion).get(pk=eid)

    # Only process single or multiple choice questions
    if q.typ not in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
        return None

    # Build mapping of option IDs to option names
    cho = {}
    for opt in event.get_elements(WritingOption).filter(question=q):
        cho[opt.id] = opt.name

    # Load event cache and create character ID to number mapping
    get_event_cache_all(context)
    mapping = {}
    for ch_num, ch in context["chars"].items():
        mapping[ch["id"]] = ch_num

    # Initialize result dictionary for organizing choices by option
    res = {}

    # Process all character choices for this question
    character_ids = Character.objects.filter(event=event).values_list("id", flat=True)
    for el in WritingChoice.objects.filter(question=q, element_id__in=character_ids):
        # Skip if character not in current event mapping
        if el.element_id not in mapping:
            continue

        # Get character data and initialize option entry if needed
        ch_num = mapping[el.element_id]
        char = context["chars"][ch_num]
        if el.option_id not in res:
            res[el.option_id] = {"emails": [], "names": []}

        # Add character name and player name if available
        res[el.option_id]["emails"].append(char["name"])
        if char["player_id"]:
            res[el.option_id]["names"].append(char["player"])

    # Convert option IDs to option names in final result
    n_res = {}
    for opt_id, value in res.items():
        n_res[cho[opt_id]] = value

    return JsonResponse(n_res)


@login_required
def orga_character_form(request: HttpRequest, event_slug: str) -> HttpResponseRedirect:  # noqa: ARG001
    """Redirect to writing form view with character type."""
    return redirect("orga_writing_form", event_slug=event_slug, writing_type="character")


def check_writing_form_type(context: dict, form_type: str) -> None:
    """Validate writing form type and update context with type information.

    Args:
        context: Context dictionary to update with type information
        form_type: Writing form type to validate

    Raises:
        Http404: If the writing form type is not available

    """
    form_type = form_type.lower()
    writing_type_mapping = _get_writing_mapping()

    # Build available types from choices that have corresponding features
    available_types = {
        value: key for key, value in QuestionApplicable.choices if writing_type_mapping[value] in context["features"]
    }

    # Validate the requested type is available
    if form_type not in available_types:
        msg = f"unknown writing form type: {form_type}"
        raise Http404(msg)

    # Update context with type information
    context["typ"] = form_type
    context["writing_typ"] = available_types[form_type]
    context["label_typ"] = form_type.capitalize()
    context["available_typ"] = {key.capitalize(): value for key, value in available_types.items()}


@login_required
def orga_writing_form(request: HttpRequest, event_slug: str, writing_type: str) -> HttpResponse:
    """Display and manage writing form questions for character creation.

    This view handles both GET requests to display the writing form configuration
    and POST requests to download form data. It manages writing questions that
    are used during character creation and approval processes.

    Args:
        request: The HTTP request object containing user session and form data
        event_slug: Event identifier string used to locate the specific event
        writing_type: The writing form type identifier (e.g., 'character', 'background')

    Returns:
        HttpResponse: Either a rendered HTML template for the form configuration
                     page or a file download response containing form data

    Raises:
        PermissionDenied: If user lacks 'orga_character_form' permission
        Http404: If the writing form type is invalid or event not found

    """
    # Verify user has permission to access character form organization features
    context = check_event_context(request, event_slug, "orga_character_form")

    # Validate the writing form type parameter and add to context
    check_writing_form_type(context, writing_type)

    # Handle POST request for downloading character form data
    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_character_form_download(context)

    # Configure context for template rendering with upload/download settings
    context["upload"] = "character_form"
    context["download"] = 1

    # Retrieve and order writing questions for the specified form type
    context["list"] = (
        context["event"]
        .get_elements(WritingQuestion)
        .filter(applicable=context["writing_typ"])
        .order_by("order")
        .prefetch_related("options")
    )

    # Pre-process question options to ensure proper ordering
    for el in context["list"]:
        el.options_list = el.options.order_by("order")

    # Set approval configuration and status flags for template rendering
    context["approval"] = get_event_config(
        context["event"].id, "user_character_approval", default_value=False, context=context
    )
    context["status"] = "user_character" in context["features"] and writing_type.lower() == "character"

    return render(request, "larpmanager/orga/characters/form.html", context)


@login_required
def orga_writing_form_edit(
    request: HttpRequest, event_slug: str, writing_type: str, question_uuid: str
) -> HttpResponse:
    """Edit writing form questions with validation and option handling.

    Handles the editing of writing form questions for LARP events, including
    validation of question types and automatic redirection to option editing
    for single/multiple choice questions.

    Args:
        request: The HTTP request object containing form data and user info
        event_slug: Event slug identifier for the current event
        writing_type: Writing form type identifier (e.g., 'character', 'background')
        question_uuid: Question uuid to edit, or 0 for new question

    Returns:
        HttpResponse: Either a rendered form edit template or a redirect to
            options editing or form list depending on form submission result

    Raises:
        PermissionDenied: If user lacks 'orga_character_form' permission
        Http404: If writing form type is invalid for the event

    """
    # Check user permissions for editing character forms
    perm = "orga_character_form"
    context = check_event_context(request, event_slug, perm)

    # Validate the writing form type exists for this event
    check_writing_form_type(context, writing_type)

    # Process form submission using backend edit utility
    if backend_edit(request, context, OrgaWritingQuestionForm, question_uuid, is_association=False):
        # Set permission suggestion for future operations
        set_suggestion(context, perm)

        # Handle "continue editing" button - redirect to new question form
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, context["run"].get_slug(), writing_type, "0")

        # Determine if we need to redirect to option editing
        edit_option = False

        # Check if user explicitly requested new option creation
        if str(request.POST.get("new_option", "")) == "1":
            edit_option = True
        # For choice questions, ensure at least one option exists
        elif (
            context["saved"].typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]
            and not WritingOption.objects.filter(question_id=context["saved"].id).exists()
        ):
            edit_option = True
            messages.warning(
                request,
                _("You must define at least one option before saving a single-choice or multiple-choice question"),
            )

        # Redirect to option editing if needed, otherwise back to form list
        if edit_option:
            return redirect(
                orga_writing_options_new,
                event_slug=context["run"].get_slug(),
                writing_type=writing_type,
                question_uuid=context["saved"].uuid,
            )
        return redirect("orga_writing_form", event_slug=context["run"].get_slug(), writing_type=writing_type)

    # Load existing options for the question being edited
    context["list"] = WritingOption.objects.filter(
        question=context["el"],
        question__applicable=context["writing_typ"],
    ).order_by("order")

    # Render the form edit template with context
    return render(request, "larpmanager/orga/characters/form_edit.html", context)


@login_required
def orga_writing_form_order(
    request: HttpRequest,
    event_slug: str,
    writing_type: str,
    question_uuid: str,
    order: int,
) -> HttpResponse:
    """Reorder writing form questions by swapping positions.

    Args:
        request: The HTTP request object.
        event_slug: Event slug identifier.
        writing_type: The writing form type to reorder questions for.
        question_uuid: The question UUID to move.
        order: The direction to move ('up' or 'down').

    Returns:
        Redirect to the writing form page.

    """
    # Verify user has permission to modify character forms
    context = check_event_context(request, event_slug, "orga_character_form")

    # Validate the writing form type exists
    check_writing_form_type(context, writing_type)

    # Exchange the order of questions
    exchange_order(context, WritingQuestion, question_uuid, order)

    # Redirect back to the writing form page
    return redirect("orga_writing_form", event_slug=context["run"].get_slug(), writing_type=writing_type)


@login_required
def orga_writing_options_edit(
    request: HttpRequest, event_slug: str, writing_type: str, option_uuid: str
) -> HttpResponse:
    """Edit writing form option for event organizers.

    Args:
        request: The HTTP request object
        event_slug: Event slug identifier
        writing_type: Writing form type (background, origin, etc.)
        option_uuid: Option uuid to edit

    Returns:
        HTTP response with the option edit form

    """
    # Verify user has character form permissions and get event context
    context = check_event_context(request, event_slug, "orga_character_form")

    # Validate the writing form type exists and is allowed
    check_writing_form_type(context, writing_type)

    # Process the option edit form and return response
    return writing_option_edit(context, option_uuid, request, writing_type)


@login_required
def orga_writing_options_new(
    request: HttpRequest, event_slug: str, writing_type: str, question_uuid: str
) -> HttpResponse:
    """Create new writing option for character form question.

    Validates permissions and creates a new writing option for the specified
    question type and number.
    """
    # Validate user has permission to edit character forms
    context = check_event_context(request, event_slug, "orga_character_form")

    # Ensure the writing form type is valid
    check_writing_form_type(context, writing_type)

    # Set question ID in context and delegate to option editor
    get_element(context, question_uuid, "question", WritingQuestion)
    if "question" in context:
        context["question_uuid"] = context["question"].uuid
    return writing_option_edit(context, "0", request, writing_type)


def writing_option_edit(context: dict, option_uuid: str, request: HttpRequest, option_type: str) -> HttpResponse:
    """Edit a writing option and handle form submission with redirect logic."""
    # Process form submission and save changes
    if backend_edit(request, context, OrgaWritingOptionForm, option_uuid, is_association=False):
        redirect_target = "orga_writing_form_edit"

        # Check if user wants to continue adding more options
        if "continue" in request.POST:
            redirect_target = "orga_writing_options_new"

        # Redirect to appropriate target with context parameters
        return redirect(
            redirect_target,
            event_slug=context["run"].get_slug(),
            writing_type=option_type,
            question_uuid=context["saved"].question.uuid,
        )

    # Render edit form if no successful submission
    return render(request, "larpmanager/orga/edit.html", context)


@login_required
def orga_writing_options_order(
    request: HttpRequest,
    event_slug: str,
    writing_type: str,
    option_uuid: str,
    order: int,
) -> HttpResponseRedirect:
    """Reorder writing options within a writing form question.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        writing_type: Writing form type identifier
        option_uuid: Option UUID
        order: New order position for the option

    Returns:
        Redirect to the writing form edit page

    """
    # Check event permission and initialize context
    context = check_event_context(request, event_slug, "orga_character_form")

    # Validate writing form type exists in context
    check_writing_form_type(context, writing_type)

    # Exchange order positions of WritingOption objects
    exchange_order(context, WritingOption, option_uuid, order)

    # Redirect back to writing form edit view
    return redirect(
        "orga_writing_form_edit",
        event_slug=context["run"].get_slug(),
        writing_type=writing_type,
        question_uuid=context["current"].question.uuid,
    )


@login_required
def orga_check(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Perform comprehensive character and writing consistency checks.

    Validates character relationships, writing completeness, speedlarp constraints,
    and plot assignments to identify potential issues in the event setup.

    Args:
        request: The HTTP request object containing user session and data
        event_slug: Event identifier string for accessing the specific event

    Returns:
        HttpResponse: Rendered template with check results and context data

    Note:
        This function performs multiple validation checks including character
        relationships, writing completeness, and speedlarp constraints to ensure
        event setup integrity.

    """
    # Initialize context and validate user permissions for the event
    context = check_event_context(request, event_slug)

    # Initialize data structures for check results and caching
    checks = {}
    cache = {}

    # Build character data directly from database to include all characters (even hidden ones)
    check_chars = {}
    id_number_map = {}
    number_map = {}

    # Get all characters for the event
    for ch_id, ch_number, ch_name, ch_text in (
        context["event"].get_elements(Character).values_list("id", "number", "name", "text")
    ):
        check_chars[ch_number] = {"id": ch_id, "number": ch_number, "name": ch_name, "text": ch_text or ""}
        id_number_map[ch_id] = ch_number
        number_map[ch_number] = ch_id

    chs_numbers = list(check_chars.keys())

    # Append plot-related text content if plot feature is enabled
    if "plot" in context["features"]:
        event = context["event"].get_class_parent(Character)
        que = PlotCharacterRel.objects.filter(character__event=event).select_related("character")
        que = que.exclude(text__isnull=True).exclude(text__exact="")

        # Concatenate plot text to existing character text
        for el in que.values_list("character__number", "text"):
            if el[0] in check_chars:
                check_chars[el[0]]["text"] += el[1]

    context["chars"] = check_chars

    # Validate character relationships and dependencies
    check_relations(cache, checks, chs_numbers, context, number_map)

    # Verify writing completeness and identify extinct/missing/interloper characters
    check_writings(cache, checks, chs_numbers, context, id_number_map)

    # Validate speedlarp constraints ensuring no player has duplicate assignments
    check_speedlarp(checks, context, id_number_map)

    # Store check results in context and render the check template
    context["checks"] = checks

    return render(request, "larpmanager/orga/writing/check.html", context)


def check_relations(
    character_cache: Any, validation_checks: Any, character_numbers: Any, context: dict, number_to_id_map: Any
) -> None:
    """Check character relationships for missing and extinct references.

    Args:
        character_cache: Dictionary to store relationship data for each character
        validation_checks: Dictionary to accumulate validation errors
        character_numbers: Set of valid character numbers in the event
        context: Context dictionary containing character data
        number_to_id_map: Mapping from character IDs to numbers

    Side effects:
        Updates validation_checks with relat_missing and relat_extinct validation errors
        Populates character_cache with character relationship data

    """
    validation_checks["relat_missing"] = []
    validation_checks["relat_extinct"] = []
    for character_id in context["chars"]:
        character = context["chars"][character_id]
        (referenced_characters, extinct_references) = get_chars_relations(character.get("text", ""), character_numbers)
        character_name = f"#{character['number']} {character['name']}"
        for extinct_reference in extinct_references:
            validation_checks["relat_extinct"].append((character_name, extinct_reference))
        character_cache[character_id] = (character_name, referenced_characters)
    for character_id, cached_data in character_cache.items():
        (first_character_name, first_character_relations) = cached_data
        for other_character_id in first_character_relations:
            (second_character_name, second_character_relations) = character_cache[other_character_id]
            if character_id not in second_character_relations:
                validation_checks["relat_missing"].append(
                    {
                        "f_id": number_to_id_map[character_id],
                        "f_name": first_character_name,
                        "s_id": number_to_id_map[other_character_id],
                        "s_name": second_character_name,
                    },
                )


def check_writings(
    cache: Any, checks: Any, character_numbers: Any, context: dict, character_id_to_number_map: Any
) -> None:
    """Validate writing submissions and requirements for different element types.

    Args:
        cache: Dictionary to store validation results
        checks: Dictionary to store validation issues found
        character_numbers: Set of valid character numbers
        context: Context with event and features data
        character_id_to_number_map: Mapping from character IDs to numbers

    Side effects:
        Updates checks with extinct, missing, and interloper character issues

    """
    for element_type in [Faction, Plot, Prologue, SpeedLarp]:
        element_name = str(element_type.__name__).lower()
        if element_name not in context["features"]:
            continue
        checks[element_name + "_extinct"] = []
        checks[element_name + "_missing"] = []
        checks[element_name + "_interloper"] = []
        cache[element_name] = {}
        # check s: all characters currently listed has
        for element in (
            context["event"]
            .get_elements(element_type)
            .annotate(characters_map=ArrayAgg("characters"))
            .prefetch_related("characters")
        ):
            (characters_from_text, extinct_characters) = get_chars_relations(element.text, character_numbers)
            for extinct_character in extinct_characters:
                checks[element_name + "_extinct"].append((element, extinct_character))

            characters_from_relations = set()
            for character_id in element.characters_map:
                if character_id not in character_id_to_number_map:
                    continue
                characters_from_relations.add(character_id_to_number_map[character_id])

            for missing_character in list(set(characters_from_text) - set(characters_from_relations)):
                checks[element_name + "_missing"].append((element, missing_character))
            for interloper_character in list(set(characters_from_relations) - set(characters_from_text)):
                checks[element_name + "_interloper"].append((element, interloper_character))


def check_speedlarp(checks: Any, context: dict, id_number_map: Any) -> None:
    """Validate speedlarp character configurations.

    Args:
        checks: Dictionary to store validation issues
        context: Context with event features and character data
        id_number_map: Mapping from character IDs to numbers

    Side effects:
        Updates checks with speedlarp double assignments and missing configurations

    """
    if "speedlarp" not in context["features"]:
        return

    checks["speed_larps_double"] = []
    checks["speed_larps_missing"] = []
    max_speedlarp_type = context["event"].get_elements(SpeedLarp).aggregate(Max("typ"))["typ__max"]
    if not max_speedlarp_type or max_speedlarp_type == 0:
        return

    speedlarp_assignments = {}
    for speedlarp_element in context["event"].get_elements(SpeedLarp).annotate(characters_map=ArrayAgg("characters")):
        check_speedlarp_prepare(speedlarp_element, id_number_map, speedlarp_assignments)
    for character_number, character in context["chars"].items():
        if character_number not in speedlarp_assignments:
            continue
        for speedlarp_type in range(1, max_speedlarp_type + 1):
            if speedlarp_type not in speedlarp_assignments[character_number]:
                checks["speed_larps_missing"].append((speedlarp_type, character))
            if len(speedlarp_assignments[character_number][speedlarp_type]) > 1:
                checks["speed_larps_double"].append((speedlarp_type, character))


def check_speedlarp_prepare(
    element: Any,
    character_id_to_number_map: dict[int, int],
    character_speeds: dict[int, dict[str, list[str]]],
) -> None:
    """Prepare speed LARP data by mapping character relationships to speeds structure."""
    # Extract character numbers from element's character map
    character_numbers_from_relationships = set()
    for character_id in element.characters_map:
        if character_id not in character_id_to_number_map:
            continue
        character_numbers_from_relationships.add(character_id_to_number_map[character_id])

    # Update speeds structure for each character
    for character_number in character_numbers_from_relationships:
        if character_number not in character_speeds:
            character_speeds[character_number] = {}
        if element.typ not in character_speeds[character_number]:
            character_speeds[character_number][element.typ] = []
        character_speeds[character_number][element.typ].append(str(element))


@require_POST
def orga_character_get_number(request: HttpRequest, event_slug: str) -> JsonResponse | None:
    """Get the number attribute for a Trait or Character element.

    Args:
        request: The HTTP request containing idx and type in POST data.
        event_slug: Event identifier string.

    Returns:
        JsonResponse with element number or error status.

    """
    # Check user permissions for the event
    context = check_event_context(request, event_slug, "orga_characters")
    idx = request.POST.get("idx")
    element_type = request.POST.get("type")

    try:
        # Get element based on type (Trait or Character)
        if element_type.lower() == "trait":
            el = context["event"].get_elements(Trait).get(pk=idx)
        else:
            el = context["event"].get_elements(Character).get(pk=idx)

        # Return the element's number
        return JsonResponse({"res": "ok", "number": el.number})
    except ObjectDoesNotExist:
        JsonResponse({"res": "ko"})


@require_POST
def orga_writing_excel_edit(request: HttpRequest, event_slug: str, writing_type: str) -> JsonResponse:
    """Handle Excel-based editing of writing elements.

    Manages bulk editing of character stories and writing content through
    spreadsheet interface, providing AJAX form rendering with TinyMCE
    support and character count validation.

    Args:
        request: HTTP request object containing user session and form data
        event_slug: Event slug for permission checking and context setup
        writing_type: Type identifier specifying the kind of writing question/element

    Returns:
        JsonResponse: JSON response containing form HTML, editor configuration,
                     and validation parameters. Returns {"k": 0} on error.

    Raises:
        ObjectDoesNotExist: When the requested writing element cannot be found

    """
    # Attempt to retrieve the Excel form context for the specified element
    try:
        context = _get_excel_form(request, event_slug, writing_type)
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    # Determine if TinyMCE rich text editor should be enabled
    # Based on question type requiring formatted text input
    tinymce = False
    if context["question"].typ in [WritingQuestionType.TEASER, WritingQuestionType.SHEET, BaseQuestionType.EDITOR]:
        tinymce = True

    # Initialize character counter HTML for length validation
    counter = ""
    if (
        context["question"].typ in ["m", "t", "p", "e", "name", "teaser", "text", "title"]
        and context["question"].max_length
    ):
        # Set appropriate label for multiple choice vs text fields
        name = _("options") if context["question"].typ == "m" else "text length"
        # Generate counter display with current/max length format
        counter = f'<div class="helptext">{name}: <span class="count"></span> / {context["question"].max_length}</div>'

    # Prepare localized labels and form field references
    confirm = _("Confirm")
    field = context["form"][context["field_key"]]

    # Build complete form HTML with header, input field, and controls
    value = f"""
        <h2>{context["question"].name}: {context["element"]}</h2>
        <form id='form-excel'>
            <div id='{field.auto_id}_tr'>
                {field.as_widget()}
                {counter}
            </div>
        </form>
        <br />
        <input type='submit' value='{confirm}'>
        <a href="#" class="close"><i class="fa-solid fa-xmark"></i></a>
    """

    # Construct JSON response with form data and editor configuration
    response = {
        "k": 1,
        "v": value,
        "tinymce": tinymce,
        "typ": context["question"].typ,
        "max_length": context["question"].max_length,
        "key": field.auto_id,
    }
    return JsonResponse(response)


@require_POST
def orga_writing_excel_submit(request: HttpRequest, event_slug: str, writing_type: Any) -> Any:
    """Handle Excel submission for writing data with validation.

    Args:
        request: HTTP request with form data
        event_slug: Event slug for permission checking and context setup
        writing_type: Writing type identifier

    Returns:
        JsonResponse: Success status, element updates, or validation errors

    """
    try:
        context = _get_excel_form(request, event_slug, writing_type, is_submit=True)
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    context["auto"] = int(request.POST.get("auto"))
    if context["auto"]:
        if is_lm_admin(request):
            return JsonResponse({"k": 1})
        msg = _check_working_ticket(request, context, request.POST["token"])
        if msg:
            return JsonResponse({"warn": msg})

    if context["form"].is_valid():
        obj = context["form"].save()
        response = {
            "k": 1,
            "qid": context["question"].uuid,
            "eid": context["element"].uuid,
            "update": _get_question_update(context, obj),
        }
        return JsonResponse(response)
    return JsonResponse({"k": 2, "errors": context["form"].errors})


def _get_excel_form(
    request: HttpRequest,
    event_slug: str,
    element_type: str,
    *,
    is_submit: bool = False,
) -> dict[str, Any]:
    """Prepare Excel form context for bulk editing operations.

    Sets up form data and validation for spreadsheet-based content editing,
    filtering forms to show only the requested question field and preparing
    the context for character, faction, plot, trait, or quest editing.

    Args:
        request: HTTP request object containing POST data with question and element IDs
        event_slug: Event slug for permission checking and context setup
        element_type: Type of element being edited (character, faction, plot, trait, quest)
        is_submit: Whether this is a form submission (True) or initial load (False)

    Returns:
        Dict containing form context with filtered fields, question data, and element instance

    Raises:
        DoesNotExist: If question or element with given IDs don't exist
        PermissionDenied: If user lacks required permissions for the operation

    """
    # Check user permissions and setup base context
    context = check_event_context(request, event_slug, f"orga_{element_type}s")
    if not is_submit:
        get_event_cache_all(context)

    # Validate writing form type and extract request parameters
    check_writing_form_type(context, element_type)
    question_uuid = int(request.POST.get("qid"))
    element_uuid = int(request.POST.get("eid"))

    # Fetch the writing question with proper filtering
    question = (
        context["event"]
        .get_elements(WritingQuestion)
        .select_related("event")
        .filter(applicable=context["writing_typ"])
        .get(uuid=question_uuid)
    )

    # Setup applicable type context and fetch target element
    context["applicable"] = QuestionApplicable.get_applicable_inverse(context["writing_typ"])
    element = context["event"].get_elements(context["applicable"]).select_related("event").get(uuid=element_uuid)
    context["elementTyp"] = context["applicable"]

    # Map element types to their corresponding form classes
    form_mapping = {
        "character": OrgaCharacterForm,
        "faction": FactionForm,
        "plot": PlotForm,
        "trait": TraitForm,
        "quest": QuestForm,
    }

    # Initialize form based on submission state
    form_class = form_mapping.get(element_type, OrgaCharacterForm)
    if is_submit:
        form = form_class(request.POST, request.FILES, context=context, instance=element)
    else:
        form = form_class(context=context, instance=element)

    # Determine field key based on question type
    field_key = f"q{question_uuid}"
    if question.typ not in BaseQuestionType.get_basic_types():
        field_key = question.typ

    # Filter form to show only the relevant question field
    if field_key in form.fields:
        form.fields = {field_key: form.fields[field_key]}
    else:
        form.fields = {}

    # Finalize context with form and related objects
    context["form"] = form
    context["question"] = question
    context["element"] = element
    context["field_key"] = field_key

    return context


def _get_question_update(context: dict, element: Any) -> str:
    """Generate question update HTML for different question types.

    Creates appropriate HTML content for updating questions based on their type,
    handling cover questions and other writing question formats.

    Args:
        context: Context dictionary containing question, form, event, and element data
        element: Element object with thumb attribute for cover questions

    Returns:
        HTML string for the question update content

    """
    # Handle cover question type - return image thumbnail HTML
    if context["question"].typ in [WritingQuestionType.COVER]:
        return f"""
                <a href="{element.thumb.url}">
                    <img src="{element.thumb.url}"
                         class="character-cover"
                         alt="character cover" />
                </a>
            """

    # Determine question key and slug based on question type
    question_key = f"q{context['question'].id}"
    question_slug = str(context["question"].id)
    if context["question"].typ not in BaseQuestionType.get_basic_types():
        question_key = context["question"].typ
        question_slug = context["question"].typ

    # Extract value from form cleaned data
    display_value = context["form"].cleaned_data[question_key]

    # Strip HTML tags for editor and text-based question types
    if context["question"].typ in [WritingQuestionType.TEASER, WritingQuestionType.SHEET, BaseQuestionType.EDITOR]:
        display_value = strip_tags(str(display_value))

    # Handle multiple choice and single choice questions
    if context["question"].typ in [BaseQuestionType.MULTIPLE, BaseQuestionType.SINGLE]:
        # get option names
        option_ids = [int(option_value) for option_value in display_value]
        query = context["event"].get_elements(WritingOption).filter(pk__in=option_ids).order_by("order")
        display_value = ", ".join(list(query.values_list("name", flat=True)))
    else:
        # check if it is over the character limit
        display_value = str(display_value)
        character_limit = conf_settings.FIELD_SNIPPET_LIMIT

        # Truncate long values and add expand link
        if len(display_value) > character_limit:
            display_value = display_value[:character_limit]
            display_value += f"... <a href='#' class='post_popup' pop='{context['element'].id}' fie='{question_slug}'><i class='fas fa-eye'></i></a>"

    return display_value


def _check_working_ticket(request: HttpRequest, context: dict, working_ticket_token: str) -> str | None:
    """Check if ticket is being edited by another user.

    Args:
        request: Django HTTP request object
        context: Context dictionary containing 'typ', 'element', and 'question'
        working_ticket_token: Working ticket token

    Returns:
        Error message if ticket is locked, None otherwise

    """
    # Check if somebody else has opened the character to edit it
    error_message = writing_edit_working_ticket(request, context["typ"], context["element"].id, working_ticket_token)

    # Check if somebody has opened the same field to edit it
    if not error_message:
        error_message = writing_edit_working_ticket(
            request,
            context["typ"],
            f"{context['element'].id}_{context['question'].id}",
            working_ticket_token,
        )

    return error_message
