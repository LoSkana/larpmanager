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

import inflection
from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_all
from larpmanager.forms.event import OrgaProgressStepForm
from larpmanager.forms.writing import (
    FactionForm,
    HandoutForm,
    HandoutTemplateForm,
    PlotForm,
    PrologueForm,
    PrologueTypeForm,
    QuestForm,
    QuestTypeForm,
    SpeedLarpForm,
    TraitForm,
)
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import ProgressStep
from larpmanager.models.form import _get_writing_mapping
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import (
    Character,
    Faction,
    Handout,
    HandoutTemplate,
    Plot,
    PlotCharacterRel,
    Prologue,
    PrologueType,
    SpeedLarp,
    TextVersion,
    TextVersionChoices,
)
from larpmanager.utils.common import (
    exchange_order,
    get_element,
    get_handout,
    get_handout_template,
    get_plot,
    get_prologue,
    get_prologue_type,
    get_quest,
    get_quest_type,
    get_speedlarp,
    get_trait,
)
from larpmanager.utils.download import export_data
from larpmanager.utils.edit import orga_edit, writing_edit
from larpmanager.utils.event import check_event_permission, get_event_run
from larpmanager.utils.pdf import print_handout, return_pdf
from larpmanager.utils.writing import retrieve_cache_text_field, writing_list, writing_versions, writing_view


@login_required
def orga_plots(request, s):
    ctx = check_event_permission(request, s, "orga_plots")
    return writing_list(request, ctx, Plot, "plot")


@login_required
def orga_plots_view(request, s, num):
    ctx = check_event_permission(request, s, ["orga_reading", "orga_plots"])
    get_plot(ctx, num)
    return writing_view(request, ctx, "plot")


@login_required
def orga_plots_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit or create a plot for an event.

    Args:
        request: The HTTP request object
        s: The event slug identifier
        num: Plot ID (0 for new plot creation)

    Returns:
        HTTP response with the plot editing form
    """
    # Check user has permission to edit plots for this event
    ctx = check_event_permission(request, s, "orga_plots")

    # Load existing plot if editing (num != 0)
    if num != 0:
        get_element(ctx, num, "plot", Plot)

    # Render the plot editing form
    return writing_edit(request, ctx, PlotForm, "plot", TextVersionChoices.PLOT)


@login_required
def orga_plots_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_plots")
    exchange_order(ctx, Plot, num, order)
    return redirect("orga_plots", s=ctx["run"].get_slug())


@login_required
def orga_plots_rels_order(request: HttpRequest, s: str, num: int, order: str) -> HttpResponse:
    """
    Reorder plot character relationships for event organization.

    Args:
        request: HTTP request object containing user and session data
        s: Event slug identifier for URL routing
        num: Primary key of the PlotCharacterRel to reorder
        order: Direction of reordering ('up' or 'down')

    Returns:
        HttpResponse: Redirect to character edit page

    Raises:
        Http404: If plot relationship not found or belongs to wrong event
    """
    # Check user permissions for plot management
    ctx = check_event_permission(request, s, "orga_plots")

    # Retrieve the specific plot-character relationship
    try:
        rel = PlotCharacterRel.objects.get(pk=num)
    except ObjectDoesNotExist as err:
        raise Http404("plot rel not found") from err

    # Validate relationship belongs to current event
    if rel.character.event != ctx["event"]:
        raise Http404("plot rel wrong event")

    # Get all relationships for the same character to reorder within
    elements = PlotCharacterRel.objects.filter(character_id=rel.character_id)

    # Execute the order exchange operation
    exchange_order(ctx, PlotCharacterRel, num, order, elements)

    # Redirect back to character edit page
    return redirect("orga_characters_edit", s=ctx["run"].get_slug(), num=rel.character_id)


@login_required
def orga_plots_versions(request, s, num):
    ctx = check_event_permission(request, s, "orga_plots")
    get_plot(ctx, num)
    return writing_versions(request, ctx, "plot", TextVersionChoices.PLOT)


@login_required
def orga_factions(request, s):
    ctx = check_event_permission(request, s, "orga_factions")
    return writing_list(request, ctx, Faction, "faction")


@login_required
def orga_factions_view(request, s, num):
    ctx = check_event_permission(request, s, ["orga_reading", "orga_factions"])
    get_element(ctx, num, "faction", Faction)
    return writing_view(request, ctx, "faction")


@login_required
def orga_factions_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Handle faction editing for event organizers.

    Args:
        request: HTTP request object
        s: Event slug identifier
        num: Faction ID (0 for new faction)

    Returns:
        Rendered faction editing page
    """
    # Check permissions and initialize context
    ctx = check_event_permission(request, s, "orga_factions")

    # Load existing faction if editing (num != 0)
    if num != 0:
        get_element(ctx, num, "faction", Faction)

    # Delegate to generic writing edit view
    return writing_edit(request, ctx, FactionForm, "faction", TextVersionChoices.FACTION)


@login_required
def orga_factions_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_factions")
    exchange_order(ctx, Faction, num, order)
    return redirect("orga_factions", s=ctx["run"].get_slug())


@login_required
def orga_factions_versions(request, s, num):
    ctx = check_event_permission(request, s, "orga_factions")
    get_element(ctx, num, "faction", Faction)
    return writing_versions(request, ctx, "faction", TextVersionChoices.FACTION)


@login_required
def orga_quest_types(request, s):
    ctx = check_event_permission(request, s, "orga_quest_types")
    return writing_list(request, ctx, QuestType, "quest_type")


@login_required
def orga_quest_types_view(request, s, num):
    ctx = check_event_permission(request, s, ["orga_reading", "orga_quest_types"])
    get_quest_type(ctx, num)
    return writing_view(request, ctx, "quest_type")


@login_required
def orga_quest_types_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit or create quest types for an event.

    Args:
        request: HTTP request object
        s: Event slug identifier
        num: Quest type ID (0 for new quest type)

    Returns:
        Rendered writing edit form response
    """
    # Check user permissions for quest type management
    ctx = check_event_permission(request, s, "orga_quest_types")

    # Load existing quest type if editing (num != 0)
    if num != 0:
        get_quest_type(ctx, num)

    # Render the writing edit form with quest type configuration
    return writing_edit(request, ctx, QuestTypeForm, "quest_type", TextVersionChoices.QUEST_TYPE)


@login_required
def orga_quest_types_versions(request, s, num):
    ctx = check_event_permission(request, s, "orga_quest_types")
    get_quest_type(ctx, num)
    return writing_versions(request, ctx, "quest_type", TextVersionChoices.QUEST_TYPE)


@login_required
def orga_quests(request, s):
    ctx = check_event_permission(request, s, "orga_quests")
    return writing_list(request, ctx, Quest, "quest")


@login_required
def orga_quests_view(request, s, num):
    ctx = check_event_permission(request, s, ["orga_reading", "orga_quests"])
    get_quest(ctx, num)
    return writing_view(request, ctx, "quest")


@login_required
def orga_quests_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit or create a quest for an organization event.

    Args:
        request: The HTTP request object containing user and session data
        s: The event slug identifier used to locate the specific event
        num: The quest ID to edit (0 for creating a new quest)

    Returns:
        HttpResponse: Redirect to quest types page if no quest types exist,
                     otherwise returns the quest editing form response

    Raises:
        PermissionDenied: If user lacks 'orga_quests' permission for the event
        Http404: If the specified quest number doesn't exist when num > 0
    """
    # Check user permissions for quest management on this event
    ctx = check_event_permission(request, s, "orga_quests")

    # Verify that quest types are available before allowing quest creation
    if not ctx["event"].get_elements(QuestType).exists():
        # Add warning message and redirect to quest types adding page
        messages.warning(request, _("You must create at least one quest type before you can create quests"))
        return redirect("orga_quest_types_edit", s=s, num=0)

    # Load existing quest data if editing (num > 0), otherwise prepare for new quest
    if num != 0:
        get_element(ctx, num, "quest", Quest)

    # Delegate to the generic writing edit handler with quest-specific parameters
    return writing_edit(request, ctx, QuestForm, "quest", TextVersionChoices.QUEST)


@login_required
def orga_quests_versions(request, s, num):
    ctx = check_event_permission(request, s, "orga_quests")
    get_quest(ctx, num)
    return writing_versions(request, ctx, "quest", TextVersionChoices.QUEST)


@login_required
def orga_traits(request, s):
    ctx = check_event_permission(request, s, "orga_traits")
    return writing_list(request, ctx, Trait, "trait")


@login_required
def orga_traits_view(request, s, num):
    ctx = check_event_permission(request, s, ["orga_reading", "orga_traits"])
    get_trait(ctx, num)
    return writing_view(request, ctx, "trait")


@login_required
def orga_traits_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """
    Handle editing of trait objects for organization events.

    Validates that quests exist before allowing trait creation, then delegates
    to the generic writing_edit function for trait-specific form handling.

    Args:
        request: The HTTP request object containing user and session data
        s: The event slug identifier for URL routing
        num: The trait ID number (0 for creating new trait)

    Returns:
        HttpResponse: Either a redirect to quest creation or the trait edit form

    Raises:
        PermissionDenied: If user lacks orga_traits permission for the event
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s, "orga_traits")

    # Validate prerequisite: at least one quest must exist
    if not ctx["event"].get_elements(Quest).exists():
        # Add warning message and redirect to quests adding page
        messages.warning(request, _("You must create at least one quest before you can create traits"))
        return redirect("orga_quests_edit", s=s, num=0)

    # Load existing trait data if editing (num != 0)
    if num != 0:
        get_trait(ctx, num)

    # Delegate to generic writing edit handler for trait processing
    return writing_edit(request, ctx, TraitForm, "trait", TextVersionChoices.TRAIT)


@login_required
def orga_traits_versions(request, s, num):
    ctx = check_event_permission(request, s, "orga_traits")
    get_trait(ctx, num)
    return writing_versions(request, ctx, "trait", TextVersionChoices.TRAIT)


@login_required
def orga_handouts(request, s):
    ctx = check_event_permission(request, s, "orga_handouts")
    return writing_list(request, ctx, Handout, "handout")


@login_required
def orga_handouts_test(request, s, num):
    ctx = check_event_permission(request, s, "orga_handouts")
    get_handout(ctx, num)
    return render(request, "pdf/sheets/handout.html", ctx)


@login_required
def orga_handouts_print(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Generate and return a PDF for a specific handout."""
    # Check permissions and initialize event context
    ctx = check_event_permission(request, s, "orga_handouts")

    # Retrieve handout data and add to context
    get_handout(ctx, num)

    # Generate PDF file path
    fp = print_handout(ctx)

    # Return PDF response
    return return_pdf(fp, str(ctx["handout"]))


@login_required
def orga_handouts_view(request, s, num):
    ctx = check_event_permission(request, s, "orga_handouts")
    get_handout(ctx, num)
    return print_handout(ctx)


@login_required
def orga_handouts_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit handouts for an organization event.

    Handles the editing of handouts for a specific event. Validates that handout
    templates exist before allowing handout creation, and redirects to template
    creation if none are found.

    Args:
        request: The HTTP request object containing user and session data
        s: The event slug identifier for URL routing
        num: The handout number to edit (0 for new handout creation)

    Returns:
        HttpResponse: Rendered handout edit page or redirect response

    Raises:
        PermissionDenied: If user lacks required event permissions
    """
    # Check user permissions for handout management
    ctx = check_event_permission(request, s, "orga_handouts")

    # Validate handout templates exist before allowing handout creation
    if not ctx["event"].get_elements(HandoutTemplate).exists():
        # Display warning and redirect to template creation page
        messages.warning(request, _("You must create at least one handout template before you can create handouts"))
        return redirect("orga_handout_templates_edit", s=s, num=0)

    # Load existing handout if editing (num > 0)
    if num != 0:
        get_handout(ctx, num)

    # Delegate to generic writing edit handler with handout-specific parameters
    return writing_edit(request, ctx, HandoutForm, "handout", TextVersionChoices.HANDOUT)


@login_required
def orga_handouts_versions(request, s, num):
    ctx = check_event_permission(request, s, "orga_handouts")
    get_handout(ctx, num)
    return writing_versions(request, ctx, "handout", TextVersionChoices.HANDOUT)


@login_required
def orga_handout_templates(request, s):
    ctx = check_event_permission(request, s, "orga_handout_templates")
    return writing_list(request, ctx, HandoutTemplate, "handout_template")


@login_required
def orga_handout_templates_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit handout template for an event.

    Args:
        request: HTTP request object
        s: Event slug
        num: Handout template ID (0 for new template)

    Returns:
        Rendered handout template edit page
    """
    # Check user has permission to manage handout templates
    ctx = check_event_permission(request, s, "orga_handout_templates")

    # Load existing template if num is not 0 (new template)
    if num != 0:
        get_handout_template(ctx, num)

    return writing_edit(request, ctx, HandoutTemplateForm, "handout_template", None)


@login_required
def orga_prologue_types(request, s):
    ctx = check_event_permission(request, s, "orga_prologue_types")
    return writing_list(request, ctx, PrologueType, "prologue_type")


@login_required
def orga_prologue_types_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit or create a prologue type for an event.

    Args:
        request: HTTP request object
        s: Event slug identifier
        num: Prologue type ID (0 for new, otherwise existing ID)

    Returns:
        HTTP response with prologue type edit form
    """
    # Check user has permission to manage prologue types
    ctx = check_event_permission(request, s, "orga_prologue_types")

    # Load existing prologue type if editing (num != 0)
    if num != 0:
        get_prologue_type(ctx, num)

    # Render edit form using generic writing_edit handler
    return writing_edit(request, ctx, PrologueTypeForm, "prologue_type", None)


@login_required
def orga_prologues(request, s):
    ctx = check_event_permission(request, s, "orga_prologues")
    return writing_list(request, ctx, Prologue, "prologue")


@login_required
def orga_prologues_view(request, s, num):
    ctx = check_event_permission(request, s, ["orga_reading", "orga_prologues"])
    get_prologue(ctx, num)
    return writing_view(request, ctx, "prologue")


@login_required
def orga_prologues_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit or create prologues for an event.

    Args:
        request: The HTTP request object
        s: The event slug identifier
        num: The prologue number (0 for new prologue, >0 for existing)

    Returns:
        HttpResponse: Redirect to prologue types page if no types exist,
                     otherwise renders the prologue edit form
    """
    # Check user permissions for prologue management
    ctx = check_event_permission(request, s, "orga_prologues")

    # Verify that prologue types are configured before allowing prologue creation
    if not ctx["event"].get_elements(PrologueType).exists():
        # Inform user that prologue types must be created first
        messages.warning(request, _("You must create at least one prologue type before you can create prologues"))
        return redirect("orga_prologue_types_edit", s=s, num=0)

    # Load existing prologue data if editing (num > 0)
    if num != 0:
        get_prologue(ctx, num)

    # Render the prologue editing form with appropriate configuration
    return writing_edit(request, ctx, PrologueForm, "prologue", TextVersionChoices.PROLOGUE)


@login_required
def orga_prologues_versions(request, s, num):
    ctx = check_event_permission(request, s, "orga_prologues")
    get_prologue(ctx, num)
    return writing_versions(request, ctx, "prologue", TextVersionChoices.PROLOGUE)


@login_required
def orga_speedlarps(request, s):
    ctx = check_event_permission(request, s, "orga_speedlarps")
    return writing_list(request, ctx, SpeedLarp, "speedlarp")


@login_required
def orga_speedlarps_view(request, s, num):
    ctx = check_event_permission(request, s, ["orga_reading", "orga_speedlarps"])
    get_speedlarp(ctx, num)
    return writing_view(request, ctx, "speedlarp")


@login_required
def orga_speedlarps_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit speedlarp writing content for an event."""
    # Check permissions and initialize context
    ctx = check_event_permission(request, s, "orga_speedlarps")

    # Load existing speedlarp if editing (num != 0 means edit mode)
    if num != 0:
        get_speedlarp(ctx, num)

    # Render writing edit form
    return writing_edit(request, ctx, SpeedLarpForm, "speedlarp", TextVersionChoices.SPEEDLARP)


@login_required
def orga_speedlarps_versions(request, s, num):
    ctx = check_event_permission(request, s, "orga_speedlarps")
    get_speedlarp(ctx, num)
    return writing_versions(request, ctx, "speedlarp", TextVersionChoices.SPEEDLARP)


@login_required
def orga_assignments(request, s):
    ctx = check_event_permission(request, s, "orga_assignments")
    get_event_cache_all(ctx)
    return render(request, "larpmanager/orga/writing/assignments.html", ctx)


@login_required
def orga_progress_steps(request, s):
    ctx = check_event_permission(request, s, "orga_progress_steps")
    return writing_list(request, ctx, ProgressStep, "progress_step")


@login_required
def orga_progress_steps_edit(request, s, num):
    return orga_edit(request, s, "orga_progress_steps", OrgaProgressStepForm, num)


@login_required
def orga_progress_steps_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_progress_steps")
    exchange_order(ctx, ProgressStep, num, order)
    return redirect("orga_progress_steps", s=ctx["run"].get_slug())


@login_required
def orga_multichoice_available(request: HttpRequest, s: str) -> JsonResponse:
    """
    Handle AJAX requests for available multichoice options for organizers.

    This function processes POST requests to retrieve character options that are
    available for selection, excluding those already taken based on the specified
    type (registrations, abilities, etc.).

    Parameters
    ----------
    request : HttpRequest
        HTTP request object containing POST data with 'type' and optional 'eid'
    s : str
        Event slug identifier

    Returns
    -------
    JsonResponse
        JSON response containing available character options as list of tuples
        with format: {"res": [(character_id, character_str), ...]}

    Raises
    ------
    Http404
        If request method is not POST
    """
    # Validate request method
    if not request.method == "POST":
        return Http404()

    # Extract class name from POST data
    class_name = request.POST.get("type", "")
    taken_characters = set()

    # Handle registration-specific character filtering
    if class_name == "registrations":
        ctx = check_event_permission(request, s, "orga_registrations")
        # Get characters already assigned to registrations in this run
        taken_characters = RegistrationCharacterRel.objects.filter(reg__run_id=ctx["run"].id).values_list(
            "character_id", flat=True
        )
    else:
        # Handle other class types (abilities, etc.)
        eid = request.POST.get("eid", "")
        perms = {"abilitypx": "orga_px_abilities"}

        # Determine permission based on class name
        if class_name in perms:
            perm = perms[class_name]
        else:
            perm = "orga_" + class_name + "s"

        # Check permissions for the event
        ctx = check_event_permission(request, s, perm)

        # Get characters already assigned to the specific entity
        if eid:
            model_class = apps.get_model("larpmanager", inflection.camelize(class_name))
            taken_characters = model_class.objects.get(pk=int(eid)).characters.values_list("id", flat=True)

    # Get all characters for the event, ordered by number
    ctx["list"] = ctx["event"].get_elements(Character).order_by("number")

    # Exclude already taken characters
    ctx["list"] = ctx["list"].exclude(pk__in=taken_characters)

    # Format response as list of tuples (id, string representation)
    res = [(el.id, str(el)) for el in ctx["list"]]
    return JsonResponse({"res": res})


@login_required
def orga_factions_available(request: HttpRequest, s: str) -> JsonResponse:
    """Return available factions for character assignment via AJAX.

    Args:
        request: HTTP POST request containing orga and eid parameters
        s: Event slug string identifying the event

    Returns:
        JsonResponse: JSON response with available factions list or error status
            - Success: {"res": [[faction_id, faction_name], ...]}
            - Error: {"res": "ko"}

    Raises:
        Http404: If request method is not POST
    """
    # Validate request method - only POST allowed
    if not request.method == "POST":
        return Http404()

    # Get event context from slug
    ctx = get_event_run(request, s)

    # Get all factions for this event, ordered by number
    ctx["list"] = ctx["event"].get_elements(Faction).order_by("number")

    # Filter by selectable factions if not orga user
    orga = int(request.POST.get("orga", "0"))
    if not orga:
        ctx["list"] = ctx["list"].filter(selectable=True)

    # Exclude factions already assigned to character if eid provided
    eid = int(request.POST.get("eid", "0"))
    if eid:
        # Get character by ID and validate existence
        chars = ctx["event"].get_elements(Character).filter(pk=int(eid))
        if not chars:
            return JsonResponse({"res": "ko"})

        # Get list of faction IDs already assigned to this character
        taken_factions = chars.first().factions_list.values_list("id", flat=True)
        ctx["list"] = ctx["list"].exclude(pk__in=taken_factions)

    # Convert queryset to list of tuples (id, name) for JSON response
    res = [(el.id, str(el)) for el in ctx["list"]]
    return JsonResponse({"res": res})


@login_required
def orga_export(request: HttpRequest, s: str, nm: str) -> HttpResponse:
    """Export data for a specific model in organization context.

    Args:
        request: HTTP request object
        s: Event slug
        nm: Model name (lowercase)

    Returns:
        Rendered export template with model data
    """
    # Check permissions for the specific model
    perm = f"orga_{nm}s"
    ctx = check_event_permission(request, s, perm)

    # Get the model class dynamically
    model = apps.get_model("larpmanager", nm.capitalize())

    # Export model data and prepare context
    ctx["nm"] = nm
    export = export_data(ctx, model, True)[0]
    _model, ctx["key"], ctx["vals"] = export

    return render(request, "larpmanager/orga/export.html", ctx)


@login_required
def orga_version(request: HttpRequest, s: str, nm: str, num: int) -> HttpResponse:
    """Render version details for organization text content.

    Args:
        request: The HTTP request object
        s: Event slug identifier
        nm: Text type name (e.g., 'chronicle', 'story')
        num: Version primary key

    Returns:
        Rendered HTML response with version details
    """
    # Check organization permissions for text type access
    perm = f"orga_{nm}s"
    ctx = check_event_permission(request, s, perm)

    # Find text type code matching the provided name
    tp = next(code for code, label in TextVersionChoices.choices if label.lower() == nm)

    # Retrieve specific version and format text for HTML display
    ctx["version"] = TextVersion.objects.get(tp=tp, pk=num)
    ctx["text"] = ctx["version"].text.replace("\n", "<br />")

    return render(request, "larpmanager/orga/version.html", ctx)


@login_required
def orga_reading(request: HttpRequest, s: str) -> HttpResponse:
    """Display all writing elements for organizer reading/review.

    This function retrieves and displays all writing elements (characters, plots,
    factions, etc.) for an event organizer to read and review. It checks permissions
    and filters elements based on enabled features.

    Args:
        request (HttpRequest): The HTTP request object containing user and session data
        s (str): Event slug string used to identify the specific event

    Returns:
        HttpResponse: Rendered reading.html template with context containing all
                     writing elements available for review

    Raises:
        PermissionDenied: If user lacks organizer reading permissions for the event
    """
    # Check user permissions for organizer reading access
    ctx = check_event_permission(request, s, "orga_reading")

    # Define text fields that need cache retrieval for performance
    text_fields = ["teaser", "text"]

    # Initialize list to store all writing elements
    ctx["alls"] = []

    # Get mapping of model names to their corresponding features
    mapping = _get_writing_mapping()

    # Iterate through all writing element types to collect enabled ones
    for typ in [Character, Plot, Faction, Quest, Trait, Prologue, SpeedLarp]:
        # Get model name from Django model metadata
        # noinspection PyUnresolvedReferences, PyProtectedMember
        model_name = typ._meta.model_name

        # Skip this type if its feature is not enabled for the event
        if mapping.get(model_name) not in ctx["features"]:
            continue

        # Retrieve all elements of this type for the current event
        ctx["list"] = ctx["event"].get_elements(typ)

        # Cache text fields for performance optimization
        retrieve_cache_text_field(ctx, text_fields, typ)

        # Process each element: set display type and generate view URL
        for el in ctx["list"]:
            el.type = _(model_name)
            el.url = reverse(f"orga_{model_name}s_view", args=[ctx["run"].get_slug(), el.id])

        # Add all elements of this type to the combined list
        ctx["alls"].extend(ctx["list"])

    return render(request, "larpmanager/orga/reading.html", ctx)
