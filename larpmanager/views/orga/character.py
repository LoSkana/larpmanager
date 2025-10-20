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
from typing import Any

from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Max
from django.db.models.functions import Length, Substr
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.cache.character import get_event_cache_all
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
from larpmanager.utils.character import get_chars_relations
from larpmanager.utils.common import (
    exchange_order,
    get_char,
)
from larpmanager.utils.download import orga_character_form_download
from larpmanager.utils.edit import backend_edit, set_suggestion, writing_edit, writing_edit_working_ticket
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.writing import writing_list, writing_versions, writing_view


def get_character_optimized(ctx: dict, num: int) -> None:
    """Get character with optimized queries for editing.

    Builds an optimized database query based on enabled features to minimize
    database hits when retrieving character data for editing contexts.

    Args:
        ctx: Template context dictionary containing event and features data
        num: Character primary key identifier

    Returns:
        None: Modifies ctx dictionary in-place, adding 'character' and 'class_name' keys

    Raises:
        Http404: If character does not exist or is not found for the given event

    Note:
        The function optimizes queries by conditionally adding select_related and
        prefetch_related fields based on the features available in the context.
    """
    try:
        # Get the event class parent for Character model
        ev = ctx["event"].get_class_parent(Character)
        features = ctx.get("features", [])

        # Base select_related fields - always include event
        select_related_fields = ["event"]

        # Conditionally add select_related fields based on enabled features
        # This reduces database queries for related objects
        if "user_character" in features:
            select_related_fields.append("player")
        if "progress" in features:
            select_related_fields.append("progress")
        if "assigned" in features:
            select_related_fields.append("assigned")
        if "mirror" in features:
            select_related_fields.append("mirror")

        # Build the base query with optimized select_related
        query = Character.objects.select_related(*select_related_fields)

        # Build prefetch_related fields for many-to-many relationships
        # Only include if the corresponding features are enabled
        prefetch_fields = []
        if "faction" in features:
            prefetch_fields.append("factions_list")
        if "plot" in features:
            prefetch_fields.append("plots")

        # Apply prefetch_related if any fields were identified
        if prefetch_fields:
            query = query.prefetch_related(*prefetch_fields)

        # Execute the optimized query and update context
        ctx["character"] = query.get(event=ev, pk=num)
        ctx["class_name"] = "character"
    except ObjectDoesNotExist as err:
        raise Http404("character does not exist") from err


@login_required
def orga_characters(request, s):
    ctx = check_event_permission(request, s, "orga_characters")

    get_event_cache_all(ctx)
    for config_name in ["user_character_approval", "writing_external_access"]:
        ctx[config_name] = ctx["event"].get_config(config_name, False)
    if ctx["event"].get_config("show_export", False):
        ctx["export"] = "character"

    return writing_list(request, ctx, Character, "character")


@login_required
def orga_characters_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit characters for event organizers.

    This function handles character editing functionality for event organizers,
    including loading event cache data when needed for relationships or character
    finder features, and delegating to the writing edit system.

    Args:
        request: The HTTP request object containing user and session data
        s: The event slug identifier for accessing the specific event
        num: The character number/ID to edit (0 for new character creation)

    Returns:
        HttpResponse: The rendered character edit page or redirect response
    """
    # Check user permissions for character management in this event
    ctx = check_event_permission(request, s, "orga_characters")

    # Load full event cache only when relationship or finder features are active
    # This optimization avoids expensive cache operations when not needed
    if "relationships" in ctx["features"] or "character_finder" in ctx.get("features", []):
        get_event_cache_all(ctx)

    # Load specific character data when editing existing character (num != 0)
    # Skip character loading for new character creation (num == 0)
    if num != 0:
        get_character_optimized(ctx, num)

    # Initialize character relationships data in the context
    # This sets up relationship mappings needed by the template
    _characters_relationships(ctx)

    # Delegate to the generic writing edit handler with character-specific form
    # Uses CHARACTER text version type for proper content handling
    return writing_edit(request, ctx, OrgaCharacterForm, "character", TextVersionChoices.CHARACTER)


def _characters_relationships(ctx: dict) -> None:
    """Setup character relationships data and widgets for editing.

    This function configures the context dictionary with relationship data,
    tutorial information, TinyMCE configuration, and character selection widgets
    for the relationship editing interface.

    Args:
        ctx: Context dictionary to populate with relationship data. Expected to
            contain 'features', 'event', and optionally 'character' keys.

    Returns:
        None: Modifies the context dictionary in place.

    Note:
        Requires the 'relationships' feature to be enabled in ctx['features'].
        If no character is present in context, only basic setup is performed.
    """
    # Initialize relationships data structure
    ctx["relationships"] = {}

    # Early return if relationships feature is not enabled
    if "relationships" not in ctx["features"]:
        return

    # Attempt to load tutorial content for relationships feature
    try:
        ctx["rel_tutorial"] = Feature.objects.get(slug="relationships").tutorial
    except ObjectDoesNotExist:
        pass

    # Configure TinyMCE editor settings for rich text editing
    ctx["TINYMCE_DEFAULT_CONFIG"] = conf_settings.TINYMCE_DEFAULT_CONFIG

    # Create and configure character selection widget for new relationships
    widget = EventCharacterS2Widget(attrs={"id": "new_rel_select"})
    widget.set_event(ctx["event"])
    ctx["new_rel"] = widget.render(name="new_rel_select", value="")

    # Process existing relationships if character is present in context
    if "character" in ctx:
        rels = {}

        # Fetch direct relationships where current character is the source
        direct_rels = Relationship.objects.filter(source=ctx["character"]).select_related("target")

        # Process direct relationships and populate relationship data
        for rel in direct_rels:
            if rel.target.id not in rels:
                rels[rel.target.id] = {"char": rel.target}
            rels[rel.target.id]["direct"] = rel.text

        # Fetch inverse relationships where current character is the target
        inverse_rels = Relationship.objects.filter(target=ctx["character"]).select_related("source")

        # Process inverse relationships and merge with existing data
        for rel in inverse_rels:
            if rel.source.id not in rels:
                rels[rel.source.id] = {"char": rel.source}
            rels[rel.source.id]["inverse"] = rel.text

        # Sort relationships by total text length (direct + inverse) in descending order
        sorted_rels = sorted(
            rels.items(),
            key=lambda item: len(item[1].get("direct", "")) + len(item[1].get("inverse", "")),
            reverse=True,
        )
        # Update context with sorted relationship data
        ctx["relationships"] = dict(sorted_rels)


def update_relationship(request, ctx, nm, fl):
    for d in ctx[nm]:
        idx = getattr(d, fl).number
        c = request.POST.get(f"{nm}_text_{idx}")
        if c:
            d.text = c
        c = request.POST.get(f"{nm}_text_eng_{idx}")
        if c:
            d.text_eng = c
        d.save()


@login_required
def orga_characters_relationships(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """
    Display character relationships for event organizers.

    Shows both direct relationships (where this character is the source) and
    inverse relationships (where this character is the target).

    Args:
        request: The HTTP request object
        s: Event slug identifier
        num: Character number identifier

    Returns:
        HttpResponse: Rendered template with character relationships data
    """
    # Check event permissions and get base context
    ctx = check_event_permission(request, s, "orga_characters")

    # Retrieve the specific character and add to context
    get_char(ctx, num)

    # Get direct relationships where this character is the source
    # Ordered by text length (shortest first) then by target character number
    ctx["direct"] = (
        Relationship.objects.filter(source=ctx["character"])
        .select_related("target")
        .order_by(Length("text").asc(), "target__number")
    )

    # Get inverse relationships where this character is the target
    # Ordered by text length (shortest first) then by source character number
    ctx["inverse"] = (
        Relationship.objects.filter(target=ctx["character"])
        .select_related("source")
        .order_by(Length("text").asc(), "source__number")
    )

    # Render the relationships template with complete context
    return render(request, "larpmanager/orga/characters/relationships.html", ctx)


@login_required
def orga_characters_view(request, s, num):
    ctx = check_event_permission(request, s, ["orga_reading", "orga_characters"])
    get_char(ctx, num)
    get_event_cache_all(ctx)
    return writing_view(request, ctx, "character")


@login_required
def orga_characters_versions(request, s, num):
    ctx = check_event_permission(request, s, "orga_characters")
    get_char(ctx, num)
    return writing_versions(request, ctx, "character", TextVersionChoices.CHARACTER)


@login_required
def orga_characters_summary(request, s: str, num: int) -> HttpResponse:
    """Display character summary with factions and plots for event organizers.

    Args:
        request: The HTTP request object
        s: Event slug identifier
        num: Character number/ID

    Returns:
        HttpResponse: Rendered character summary template
    """
    # Check permissions and get event context
    ctx = check_event_permission(request, s, "orga_characters")

    # Retrieve character data and add to context
    get_char(ctx, num)

    # Initialize factions list for character
    ctx["factions"] = []

    # Fetch and process all factions associated with character
    for p in ctx["character"].factions_list.all().prefetch_related("characters"):
        ctx["factions"].append(p.show_complete())

    # Initialize plots list for character
    ctx["plots"] = []

    # Fetch and process all plots associated with character
    for p in ctx["character"].plots.all().prefetch_related("characters"):
        ctx["plots"].append(p.show_complete())

    # Render template with complete character context
    return render(request, "larpmanager/orga/characters_summary.html", ctx)


@login_required
def orga_writing_form_list(request: HttpRequest, s: str, typ: str) -> JsonResponse:
    """Generate form list data for writing questions in JSON format.

    Processes writing questions and their answers for display in organizer interface,
    handling different question types (single, multiple choice, text, paragraph).

    Args:
        request: HTTP request object containing POST data with question ID
        s: Event slug identifier
        typ: Question type identifier for filtering applicable questions

    Returns:
        JsonResponse: JSON response containing question results, popup indicators,
                     and question ID for frontend processing

    Raises:
        PermissionDenied: If user lacks required event permissions
        Http404: If question or event not found
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s, "orga_characters")
    check_writing_form_type(ctx, typ)
    event = ctx["event"]

    # Use parent event if current event is a child
    if event.parent:
        event = event.parent

    # Get question ID from POST data
    eid = request.POST.get("num")

    # Determine applicable question type and get related element IDs
    applicable = QuestionApplicable.get_applicable(typ)
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
        for el in WritingChoice.objects.filter(question=question, element_id__in=element_ids).order_by("option__order"):
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
def orga_writing_form_email(request: HttpRequest, s: str, typ: str) -> JsonResponse:
    """Generate email data for writing form options by character choices.

    This function processes writing form questions and returns email data
    organized by the choices characters made for specific question options.

    Args:
        request: The HTTP request object containing POST data
        s: Event or run identifier string
        typ: Writing form type identifier

    Returns:
        JsonResponse containing email data organized by option choices.
        Each option maps to a dict with 'emails' (character names) and
        'names' (player names) lists.

    Raises:
        Http404: If event permission check fails or writing form type is invalid
    """
    # Check event permissions and validate writing form type
    ctx = check_event_permission(request, s, "orga_characters")
    check_writing_form_type(ctx, typ)

    # Get the parent event if this is a child event
    event = ctx["event"]
    if event.parent:
        event = event.parent

    # Retrieve the specific writing question from POST data
    eid = request.POST.get("num")
    q = event.get_elements(WritingQuestion).get(pk=eid)

    # Only process single or multiple choice questions
    if q.typ not in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
        return

    # Build mapping of option IDs to option names
    cho = {}
    for opt in event.get_elements(WritingOption).filter(question=q):
        cho[opt.id] = opt.name

    # Load event cache and create character ID to number mapping
    get_event_cache_all(ctx)
    mapping = {}
    for ch_num, ch in ctx["chars"].items():
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
        char = ctx["chars"][ch_num]
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
def orga_character_form(request, s):
    return redirect("orga_writing_form", s=s, typ="character")


def check_writing_form_type(ctx, typ):
    typ = typ.lower()
    mapping = _get_writing_mapping()
    available = {v: k for k, v in QuestionApplicable.choices if mapping[v] in ctx["features"]}
    if typ not in available:
        raise Http404(f"unknown writing form type: {typ}")
    ctx["typ"] = typ
    ctx["writing_typ"] = available[typ]
    ctx["label_typ"] = typ.capitalize()
    ctx["available_typ"] = {k.capitalize(): v for k, v in available.items()}


@login_required
def orga_writing_form(request, s: str, typ: str) -> HttpResponse:
    """Display and manage writing form questions for character creation.

    This view handles the display of writing form questions for character creation
    and other writing-related forms. It supports downloading form data and manages
    form permissions and configurations.

    Args:
        request: The HTTP request object containing user data and form submissions.
        s: The event slug identifier used to locate the specific event.
        typ: The writing form type identifier (e.g., 'character', 'background').

    Returns:
        HttpResponse: Either a rendered form page template or a file download response
        depending on the request method and parameters.

    Raises:
        PermissionDenied: If user lacks required permissions for the event.
        Http404: If the event or writing form type is not found.
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s, "orga_character_form")

    # Validate the writing form type exists for this event
    check_writing_form_type(ctx, typ)

    # Handle download request for character form data
    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_character_form_download(ctx)

    # Set upload and download configuration for the template
    ctx["upload"] = "character_form"
    ctx["download"] = 1

    # Fetch writing questions for the specified type, ordered and with options
    ctx["list"] = (
        ctx["event"]
        .get_elements(WritingQuestion)
        .filter(applicable=ctx["writing_typ"])
        .order_by("order")
        .prefetch_related("options")
    )

    # Sort options for each question by their display order
    for el in ctx["list"]:
        el.options_list = el.options.order_by("order")

    # Get approval settings and feature status for character forms
    ctx["approval"] = ctx["event"].get_config("user_character_approval", False)
    ctx["status"] = "user_character" in ctx["features"] and typ.lower() == "character"

    return render(request, "larpmanager/orga/characters/form.html", ctx)


@login_required
def orga_writing_form_edit(request: HttpRequest, s: str, typ: str, num: int) -> HttpResponse:
    """Edit writing form questions with validation and option handling.

    Handles the editing of writing form questions for LARP events, including
    validation of question types and automatic redirection to option editing
    for single/multiple choice questions.

    Args:
        request: The HTTP request object containing form data and user info
        s: Event slug identifier for the current event
        typ: Writing form type identifier (e.g., 'character', 'background')
        num: Question number/ID to edit, or 0 for new question

    Returns:
        HttpResponse: Either a rendered form edit template or a redirect to
            options editing or form list depending on form submission result

    Raises:
        PermissionDenied: If user lacks 'orga_character_form' permission
        Http404: If writing form type is invalid for the event
    """
    # Check user permissions for editing character forms
    perm = "orga_character_form"
    ctx = check_event_permission(request, s, perm)

    # Validate the writing form type exists for this event
    check_writing_form_type(ctx, typ)

    # Process form submission using backend edit utility
    if backend_edit(request, ctx, OrgaWritingQuestionForm, num, assoc=False):
        # Set permission suggestion for future operations
        set_suggestion(ctx, perm)

        # Handle "continue editing" button - redirect to new question form
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, s=ctx["run"].get_slug(), typ=typ, num=0)

        # Determine if we need to redirect to option editing
        edit_option = False

        # Check if user explicitly requested new option creation
        if str(request.POST.get("new_option", "")) == "1":
            edit_option = True
        # For choice questions, ensure at least one option exists
        elif ctx["saved"].typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
            if not WritingOption.objects.filter(question_id=ctx["saved"].id).exists():
                edit_option = True
                messages.warning(
                    request,
                    _("You must define at least one option before saving a single-choice or multiple-choice question"),
                )

        # Redirect to option editing if needed, otherwise back to form list
        if edit_option:
            return redirect(orga_writing_options_new, s=ctx["run"].get_slug(), typ=typ, num=ctx["saved"].id)
        return redirect("orga_writing_form", s=ctx["run"].get_slug(), typ=typ)

    # Load existing options for the question being edited
    ctx["list"] = WritingOption.objects.filter(question=ctx["el"], question__applicable=ctx["writing_typ"]).order_by(
        "order"
    )

    # Render the form edit template with context
    return render(request, "larpmanager/orga/characters/form_edit.html", ctx)


@login_required
def orga_writing_form_order(request, s, typ, num, order):
    ctx = check_event_permission(request, s, "orga_character_form")
    check_writing_form_type(ctx, typ)
    exchange_order(ctx, WritingQuestion, num, order)
    return redirect("orga_writing_form", s=ctx["run"].get_slug(), typ=typ)


@login_required
def orga_writing_options_edit(request, s, typ, num):
    ctx = check_event_permission(request, s, "orga_character_form")
    check_writing_form_type(ctx, typ)
    return writing_option_edit(ctx, num, request, typ)


@login_required
def orga_writing_options_new(request, s, typ, num):
    ctx = check_event_permission(request, s, "orga_character_form")
    check_writing_form_type(ctx, typ)
    ctx["question_id"] = num
    return writing_option_edit(ctx, 0, request, typ)


def writing_option_edit(ctx, num, request, typ):
    if backend_edit(request, ctx, OrgaWritingOptionForm, num, assoc=False):
        redirect_target = "orga_writing_form_edit"
        if "continue" in request.POST:
            redirect_target = "orga_writing_options_new"
        return redirect(redirect_target, s=ctx["run"].get_slug(), typ=typ, num=ctx["saved"].question_id)
    return render(request, "larpmanager/orga/edit.html", ctx)


@login_required
def orga_writing_options_order(request, s, typ, num, order):
    ctx = check_event_permission(request, s, "orga_character_form")
    check_writing_form_type(ctx, typ)
    exchange_order(ctx, WritingOption, num, order)
    return redirect("orga_writing_form_edit", s=ctx["run"].get_slug(), typ=typ, num=ctx["current"].question_id)


@login_required
def orga_check(request: HttpRequest, s: str) -> HttpResponse:
    """Perform comprehensive character and writing consistency checks.

    Validates character relationships, writing completeness, speedlarp constraints,
    and plot assignments to identify potential issues in the event setup.

    Args:
        request: The HTTP request object containing user session and data
        s: The event slug identifier for accessing the specific event

    Returns:
        HttpResponse: Rendered template with check results and context data

    Note:
        This function performs multiple validation checks including character
        relationships, writing completeness, and speedlarp constraints to ensure
        event setup integrity.
    """
    # Initialize context and validate user permissions for the event
    ctx = check_event_permission(request, s)

    # Initialize data structures for check results and caching
    checks = {}
    cache = {}

    # Build character data directly from database to include all characters (even hidden ones)
    check_chars = {}
    id_number_map = {}
    number_map = {}

    # Get all characters for the event
    for ch_id, ch_number, ch_name, ch_text in (
        ctx["event"].get_elements(Character).values_list("id", "number", "name", "text")
    ):
        check_chars[ch_number] = {"id": ch_id, "number": ch_number, "name": ch_name, "text": ch_text or ""}
        id_number_map[ch_id] = ch_number
        number_map[ch_number] = ch_id

    chs_numbers = list(check_chars.keys())

    # Append plot-related text content if plot feature is enabled
    if "plot" in ctx["features"]:
        event = ctx["event"].get_class_parent(Character)
        que = PlotCharacterRel.objects.filter(character__event=event).select_related("character")
        que = que.exclude(text__isnull=True).exclude(text__exact="")

        # Concatenate plot text to existing character text
        for el in que.values_list("character__number", "text"):
            if el[0] in check_chars:
                check_chars[el[0]]["text"] += el[1]

    ctx["chars"] = check_chars

    # Validate character relationships and dependencies
    check_relations(cache, checks, chs_numbers, ctx, number_map)

    # Verify writing completeness and identify extinct/missing/interloper characters
    check_writings(cache, checks, chs_numbers, ctx, id_number_map)

    # Validate speedlarp constraints ensuring no player has duplicate assignments
    check_speedlarp(checks, ctx, id_number_map)

    # Store check results in context and render the check template
    ctx["checks"] = checks

    return render(request, "larpmanager/orga/writing/check.html", ctx)


def check_relations(cache: dict, checks: dict, chs_numbers: set, ctx: dict, number_map: dict) -> None:
    """Check character relationships for missing and extinct references.

    This function validates character relationships by checking for:
    1. References to non-existent characters (extinct)
    2. One-way relationships that should be bidirectional (missing)

    Args:
        cache: Dictionary to store relationship data for each character.
            Will be populated with character_id -> (name, relations) mappings.
        checks: Dictionary to accumulate validation errors.
            Will be updated with 'relat_missing' and 'relat_extinct' keys.
        chs_numbers: Set of valid character numbers in the current event.
        ctx: Context dictionary containing character data under 'chars' key.
        number_map: Mapping from character IDs to their numbers.

    Returns:
        None: Function modifies input dictionaries in place.

    Side Effects:
        - Updates checks with relat_missing and relat_extinct validation errors
        - Populates cache with character relationship data for further processing
    """
    # Initialize validation error lists
    checks["relat_missing"] = []
    checks["relat_extinct"] = []

    # First pass: extract relationships and check for extinct references
    for c in ctx["chars"]:
        ch = ctx["chars"][c]
        # Parse character text to find relationships and extinct references
        (from_text, extinct) = get_chars_relations(ch.get("text", ""), chs_numbers)
        name = f"#{ch['number']} {ch['name']}"

        # Collect extinct relationship references
        for e in extinct:
            checks["relat_extinct"].append((name, e))

        # Cache character name and their relationships for second pass
        cache[c] = (name, from_text)

    # Second pass: check for missing bidirectional relationships
    for c, content in cache.items():
        (first, first_rel) = content

        # For each character this one has a relationship with
        for oth in first_rel:
            (second, second_rel) = cache[oth]

            # Check if the relationship is bidirectional
            if c not in second_rel:
                checks["relat_missing"].append(
                    {"f_id": number_map[c], "f_name": first, "s_id": number_map[oth], "s_name": second}
                )


def check_writings(cache: dict, checks: dict, chs_numbers: set, ctx: dict, id_number_map: dict) -> None:
    """Validate writing submissions and requirements for different element types.

    This function checks for inconsistencies between character references in writing
    elements (text content) and their actual character relationships. It identifies
    extinct characters (referenced but not valid), missing relationships, and
    interloper characters (related but not referenced in text).

    Args:
        cache: Dictionary to store validation results for each element type
        checks: Dictionary to store validation issues found during processing
        chs_numbers: Set of valid character numbers for the current event
        ctx: Context dictionary containing event data and available features
        id_number_map: Mapping from character database IDs to character numbers

    Side Effects:
        Updates the checks dictionary with three types of issues for each element:
        - {element}_extinct: Characters referenced in text but not valid
        - {element}_missing: Characters that should be related but aren't
        - {element}_interloper: Characters that are related but not in text
    """
    # Iterate through all writing element types (Faction, Plot, Prologue, SpeedLarp)
    for el in [Faction, Plot, Prologue, SpeedLarp]:
        nm = str(el.__name__).lower()

        # Skip element types not enabled in current context features
        if nm not in ctx["features"]:
            continue

        # Initialize validation tracking structures for this element type
        checks[nm + "_extinct"] = []
        checks[nm + "_missing"] = []
        checks[nm + "_interloper"] = []
        cache[nm] = {}

        # Process all elements of this type for the current event
        # Annotate with character mappings and prefetch relationships for efficiency
        for f in (
            ctx["event"].get_elements(el).annotate(characters_map=ArrayAgg("characters")).prefetch_related("characters")
        ):
            # Extract character references from element text and identify extinct ones
            (from_text, extinct) = get_chars_relations(f.text, chs_numbers)

            # Record any extinct character references found in the text
            for e in extinct:
                checks[nm + "_extinct"].append((f, e))

            # Build set of character numbers from actual database relationships
            from_rels = set()
            for ch_id in f.characters_map:
                # Only include characters that have valid number mappings
                if ch_id not in id_number_map:
                    continue
                from_rels.add(id_number_map[ch_id])

            # Identify missing relationships: characters in text but not in database relations
            for e in list(set(from_text) - set(from_rels)):
                checks[nm + "_missing"].append((f, e))

            # Identify interloper relationships: characters in database but not in text
            for e in list(set(from_rels) - set(from_text)):
                checks[nm + "_interloper"].append((f, e))
                # cache[nm][f.number] = (str(f), from_text)


def check_speedlarp(checks: dict, ctx: dict, id_number_map: dict) -> None:
    """Validate speedlarp character configurations.

    Checks for double assignments and missing configurations in speedlarp
    character assignments across different types.

    Args:
        checks: Dictionary to store validation issues. Will be updated with
            'speed_larps_double' and 'speed_larps_missing' keys.
        ctx: Context dictionary containing:
            - 'features': Available event features
            - 'event': Event object with speedlarp elements
            - 'chars': Character data indexed by character number
        id_number_map: Mapping from character IDs to character numbers.

    Returns:
        None: Function modifies checks dictionary in-place.

    Side Effects:
        Updates checks dictionary with speedlarp validation results:
        - speed_larps_double: List of (type, character) tuples with multiple assignments
        - speed_larps_missing: List of (type, character) tuples with missing assignments
    """
    # Early return if speedlarp feature is not enabled
    if "speedlarp" not in ctx["features"]:
        return

    # Initialize validation result containers
    checks["speed_larps_double"] = []
    checks["speed_larps_missing"] = []

    # Get maximum speedlarp type number from event elements
    max_typ = ctx["event"].get_elements(SpeedLarp).aggregate(Max("typ"))["typ__max"]
    if not max_typ or max_typ == 0:
        return

    # Build speedlarp assignments mapping: character_num -> {type -> [assignments]}
    speeds = {}
    for el in ctx["event"].get_elements(SpeedLarp).annotate(characters_map=ArrayAgg("characters")):
        check_speedlarp_prepare(el, id_number_map, speeds)

    # Validate each character's speedlarp assignments
    for chnum, c in ctx["chars"].items():
        if chnum not in speeds:
            continue

        # Check each speedlarp type for missing or double assignments
        for typ in range(1, max_typ + 1):
            if typ not in speeds[chnum]:
                checks["speed_larps_missing"].append((typ, c))
            if len(speeds[chnum][typ]) > 1:
                checks["speed_larps_double"].append((typ, c))


def check_speedlarp_prepare(el, id_number_map, speeds):
    from_rels = set()
    for ch_id in el.characters_map:
        if ch_id not in id_number_map:
            continue
        from_rels.add(id_number_map[ch_id])
    for ch in from_rels:
        if ch not in speeds:
            speeds[ch] = {}
        if el.typ not in speeds[ch]:
            speeds[ch][el.typ] = []
        speeds[ch][el.typ].append(str(el))


@require_POST
def orga_character_get_number(request, s):
    ctx = check_event_permission(request, s, "orga_characters")
    idx = request.POST.get("idx")
    type = request.POST.get("type")
    try:
        if type.lower() == "trait":
            el = ctx["event"].get_elements(Trait).get(pk=idx)
        else:
            el = ctx["event"].get_elements(Character).get(pk=idx)
        return JsonResponse({"res": "ok", "number": el.number})
    except ObjectDoesNotExist:
        JsonResponse({"res": "ko"})


@require_POST
def orga_writing_excel_edit(request: HttpRequest, s: str, typ: str) -> JsonResponse:
    """Handle Excel-based editing of writing elements.

    Manages bulk editing of character stories and writing content through
    spreadsheet interface, providing AJAX form rendering with TinyMCE
    support and character count validation.

    Args:
        request: HTTP request object containing user session and form data
        s: String identifier for the specific writing element or character
        typ: Type identifier specifying the kind of writing question/element

    Returns:
        JsonResponse: JSON response containing form HTML, editor configuration,
                     and validation parameters. Returns {"k": 0} on error.

    Raises:
        ObjectDoesNotExist: When the requested writing element cannot be found
    """
    # Attempt to retrieve the Excel form context for the specified element
    try:
        ctx = _get_excel_form(request, s, typ)
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    # Determine if TinyMCE rich text editor should be enabled
    # Based on question type requiring formatted text input
    tinymce = False
    if ctx["question"].typ in [WritingQuestionType.TEASER, WritingQuestionType.SHEET, BaseQuestionType.EDITOR]:
        tinymce = True

    # Initialize character counter HTML for length validation
    counter = ""
    if ctx["question"].typ in ["m", "t", "p", "e", "name", "teaser", "text", "title"]:
        if ctx["question"].max_length:
            # Set appropriate label for multiple choice vs text fields
            if ctx["question"].typ == "m":
                name = _("options")
            else:
                name = "text length"
            # Generate counter display with current/max length format
            counter = f'<div class="helptext">{name}: <span class="count"></span> / {ctx["question"].max_length}</div>'

    # Prepare localized labels and form field references
    confirm = _("Confirm")
    field = ctx["form"][ctx["field_key"]]

    # Build complete form HTML with header, input field, and controls
    value = f"""
        <h2>{ctx["question"].name}: {ctx["element"]}</h2>
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
        "typ": ctx["question"].typ,
        "max_length": ctx["question"].max_length,
        "key": field.auto_id,
    }
    return JsonResponse(response)


@require_POST
def orga_writing_excel_submit(request: HttpRequest, s: str, typ: str) -> JsonResponse:
    """Handle Excel submission for writing data with validation.

    Parameters
    ----------
    request : HttpRequest
        HTTP request object containing form data and user information
    s : str
        Event slug identifier for the specific event
    typ : str
        Writing type identifier specifying the category of writing

    Returns
    -------
    JsonResponse
        JSON response containing:
        - Success status (k=1 for success, k=0 for not found, k=2 for validation errors)
        - Element updates for successful submissions
        - Validation errors for failed submissions
        - Warning messages for authorization issues

    Raises
    ------
    ObjectDoesNotExist
        When the specified event or writing type cannot be found
    """
    # Retrieve Excel form context with validation
    try:
        ctx = _get_excel_form(request, s, typ, submit=True)
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    # Handle auto-submission mode with permission checks
    ctx["auto"] = int(request.POST.get("auto"))
    if ctx["auto"]:
        # Allow superusers to bypass working ticket validation
        if request.user.is_superuser:
            return JsonResponse({"k": 1})

        # Validate working ticket for non-superusers
        msg = _check_working_ticket(request, ctx, request.POST["token"])
        if msg:
            return JsonResponse({"warn": msg})

    # Process valid form submissions
    if ctx["form"].is_valid():
        # Save form data and prepare success response
        obj = ctx["form"].save()
        response = {
            "k": 1,
            "qid": ctx["question"].id,
            "eid": ctx["element"].id,
            "update": _get_question_update(ctx, obj),
        }
        return JsonResponse(response)
    else:
        # Return validation errors for invalid forms
        return JsonResponse({"k": 2, "errors": ctx["form"].errors})


def _get_excel_form(request: HttpRequest, s: str, typ: str, submit: bool = False) -> dict[str, Any]:
    """Prepare Excel form context for bulk editing operations.

    Sets up form data and validation for spreadsheet-based content editing,
    filtering forms to show only the requested question field and preparing
    the context for character, faction, plot, trait, or quest editing.

    Args:
        request: HTTP request object containing POST data with question and element IDs
        s: Event slug for permission checking and context setup
        typ: Type of element being edited (character, faction, plot, trait, quest)
        submit: Whether this is a form submission (True) or initial load (False)

    Returns:
        Dict containing form context with filtered fields, question data, and element instance

    Raises:
        DoesNotExist: If question or element with given IDs don't exist
        PermissionDenied: If user lacks required permissions for the operation
    """
    # Check user permissions and setup base context
    ctx = check_event_permission(request, s, f"orga_{typ}s")
    if not submit:
        get_event_cache_all(ctx)

    # Validate writing form type and extract request parameters
    check_writing_form_type(ctx, typ)
    question_id = int(request.POST.get("qid"))
    element_id = int(request.POST.get("eid"))

    # Fetch the writing question with proper filtering
    question = (
        ctx["event"]
        .get_elements(WritingQuestion)
        .select_related("event")
        .filter(applicable=ctx["writing_typ"])
        .get(pk=question_id)
    )

    # Setup applicable type context and fetch target element
    ctx["applicable"] = QuestionApplicable.get_applicable_inverse(ctx["writing_typ"])
    element = ctx["event"].get_elements(ctx["applicable"]).select_related("event").get(pk=element_id)
    ctx["elementTyp"] = ctx["applicable"]

    # Map element types to their corresponding form classes
    form_mapping = {
        "character": OrgaCharacterForm,
        "faction": FactionForm,
        "plot": PlotForm,
        "trait": TraitForm,
        "quest": QuestForm,
    }

    # Initialize form based on submission state
    form_class = form_mapping.get(typ, OrgaCharacterForm)
    if submit:
        form = form_class(request.POST, request.FILES, ctx=ctx, instance=element)
    else:
        form = form_class(ctx=ctx, instance=element)

    # Determine field key based on question type
    keep_key = f"q{question_id}"
    if question.typ not in BaseQuestionType.get_basic_types():
        keep_key = question.typ

    # Filter form to show only the relevant question field
    if keep_key in form.fields:
        form.fields = {keep_key: form.fields[keep_key]}
    else:
        form.fields = {}

    # Finalize context with form and related objects
    ctx["form"] = form
    ctx["question"] = question
    ctx["element"] = element
    ctx["field_key"] = keep_key

    return ctx


def _get_question_update(ctx: dict, el) -> str:
    """Generate question update HTML for different question types.

    Creates appropriate HTML content for updating questions based on their type,
    handling cover questions and other writing question formats.

    Args:
        ctx: Context dictionary containing question, form, event, and element data
        el: Element object with thumb attribute for cover questions

    Returns:
        HTML string for the question update content
    """
    # Handle cover question type - return image thumbnail HTML
    if ctx["question"].typ in [WritingQuestionType.COVER]:
        return f"""
                <a href="{el.thumb.url}">
                    <img src="{el.thumb.url}"
                         class="character-cover"
                         alt="character cover" />
                </a>
            """

    # Determine question key and slug based on question type
    question_key = f"q{ctx['question'].id}"
    question_slug = str(ctx["question"].id)
    if ctx["question"].typ not in BaseQuestionType.get_basic_types():
        question_key = ctx["question"].typ
        question_slug = ctx["question"].typ

    # Extract value from form cleaned data
    value = ctx["form"].cleaned_data[question_key]

    # Strip HTML tags for editor and text-based question types
    if ctx["question"].typ in [WritingQuestionType.TEASER, WritingQuestionType.SHEET, BaseQuestionType.EDITOR]:
        value = strip_tags(str(value))

    # Handle multiple choice and single choice questions
    if ctx["question"].typ in [BaseQuestionType.MULTIPLE, BaseQuestionType.SINGLE]:
        # get option names
        option_ids = [int(val) for val in value]
        query = ctx["event"].get_elements(WritingOption).filter(pk__in=option_ids).order_by("order")
        value = ", ".join([display for display in query.values_list("name", flat=True)])
    else:
        # check if it is over the character limit
        value = str(value)
        limit = conf_settings.FIELD_SNIPPET_LIMIT

        # Truncate long values and add expand link
        if len(value) > limit:
            value = value[:limit]
            value += f"... <a href='#' class='post_popup' pop='{ctx['element'].id}' fie='{question_slug}'><i class='fas fa-eye'></i></a>"

    return value


def _check_working_ticket(request, ctx, token):
    # perform normal check, if somebody else has opened the character to edit it
    msg = writing_edit_working_ticket(request, ctx["typ"], ctx["element"].id, token)

    # perform check if somebody has opened the same field to edit it
    if not msg:
        msg = writing_edit_working_ticket(request, ctx["typ"], f"{ctx['element'].id}_{ctx['question'].id}", token)

    return msg
