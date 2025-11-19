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

import inflection
from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
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
from larpmanager.utils.base import check_event_context, get_event_context
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
from larpmanager.utils.pdf import print_handout
from larpmanager.utils.writing import retrieve_cache_text_field, writing_list, writing_versions, writing_view


@login_required
def orga_plots(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display plots list for event organizers."""
    context = check_event_context(request, event_slug, "orga_plots")
    return writing_list(request, context, Plot, "plot")


@login_required
def orga_plots_view(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """View for displaying a specific plot in the organizer interface."""
    # Check user permissions for reading/managing plots
    context = check_event_context(request, event_slug, ["orga_reading", "orga_plots"])
    get_plot(context, num)

    # Render the plot view with the retrieved context
    return writing_view(request, context, "plot")


@login_required
def orga_plots_edit(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Edit or create a plot for an event.

    Args:
        request: The HTTP request object
        event_slug: Event identifier string
        num: Plot ID (0 for new plot creation)

    Returns:
        HTTP response with the plot editing form

    """
    # Check user has permission to edit plots for this event
    context = check_event_context(request, event_slug, "orga_plots")

    # Load existing plot if editing (num != 0)
    if num != 0:
        get_element(context, num, "plot", Plot)

    # Render the plot editing form
    return writing_edit(request, context, PlotForm, "plot", TextVersionChoices.PLOT)


@login_required
def orga_plots_order(request: HttpRequest, event_slug: str, num: int, order: int) -> HttpResponseRedirect:
    """Reorder plots in event's plot list."""
    # Verify user has permission to manage plots
    context = check_event_context(request, event_slug, "orga_plots")

    # Swap plot order positions
    exchange_order(context, Plot, num, order)

    return redirect("orga_plots", event_slug=context["run"].get_slug())


@login_required
def orga_plots_rels_order(request: HttpRequest, event_slug: str, num: int, order: int) -> HttpResponse:
    """Reorder plot character relationships for event organization.

    Args:
        request: HTTP request object containing user and session data
        event_slug: Event slug identifier for URL routing
        num: Primary key of the PlotCharacterRel to reorder
        order: Direction of reordering ('up' or 'down')

    Returns:
        HttpResponse: Redirect to character edit page

    Raises:
        Http404: If plot relationship not found or belongs to wrong event

    """
    # Check user permissions for plot management
    context = check_event_context(request, event_slug, "orga_plots")

    # Retrieve the specific plot-character relationship
    try:
        rel = PlotCharacterRel.objects.get(pk=num)
    except ObjectDoesNotExist as err:
        msg = "plot rel not found"
        raise Http404(msg) from err

    # Validate relationship belongs to current event
    if rel.character.event != context["event"]:
        msg = "plot rel wrong event"
        raise Http404(msg)

    # Get all relationships for the same character to reorder within
    elements = PlotCharacterRel.objects.filter(character_id=rel.character_id)

    # Execute the order exchange operation
    exchange_order(context, PlotCharacterRel, num, order, elements)

    # Redirect back to character edit page
    return redirect("orga_characters_edit", event_slug=context["run"].get_slug(), num=rel.character_id)


@login_required
def orga_plots_versions(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """View for managing plot versions.

    Args:
        request: HTTP request object
        event_slug: Event slug
        num: Plot number

    Returns:
        HttpResponse: Rendered versions page

    """
    # Check event permissions and get event context
    context = check_event_context(request, event_slug, "orga_plots")

    # Retrieve the specific plot
    get_plot(context, num)

    # Display text versions for the plot
    return writing_versions(request, context, "plot", TextVersionChoices.PLOT)


@login_required
def orga_factions(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Delegate faction management to writing_list view in event context."""
    # Validate event context and permissions
    context = check_event_context(request, event_slug, "orga_factions")
    return writing_list(request, context, Faction, "faction")


@login_required
def orga_factions_view(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """View displaying a specific faction for organizers."""
    # Check permissions and setup context
    context = check_event_context(request, event_slug, ["orga_reading", "orga_factions"])

    # Retrieve the faction element
    get_element(context, num, "faction", Faction)

    return writing_view(request, context, "faction")


@login_required
def orga_factions_edit(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Handle faction editing for event organizers.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        num: Faction ID (0 for new faction)

    Returns:
        Rendered faction editing page

    """
    # Check permissions and initialize context
    context = check_event_context(request, event_slug, "orga_factions")

    # Load existing faction if editing (num != 0)
    if num != 0:
        get_element(context, num, "faction", Faction)

    # Delegate to generic writing edit view
    return writing_edit(request, context, FactionForm, "faction", TextVersionChoices.FACTION)


@login_required
def orga_factions_order(request: HttpRequest, event_slug: str, num: int, order: int) -> HttpResponseRedirect:
    """Reorder factions within an event run."""
    # Verify event access and permissions
    context = check_event_context(request, event_slug, "orga_factions")

    # Exchange faction positions
    exchange_order(context, Faction, num, order)

    return redirect("orga_factions", event_slug=context["run"].get_slug())


@login_required
def orga_factions_versions(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Display version history for a faction's description.

    Args:
        request: HTTP request object
        event_slug: Event slug
        num: Faction ID

    Returns:
        Rendered template showing faction text version history

    """
    # Check user has permission to manage factions for this event
    context = check_event_context(request, event_slug, "orga_factions")

    # Load the faction object into context
    get_element(context, num, "faction", Faction)

    # Render the version history for this faction's text
    return writing_versions(request, context, "faction", TextVersionChoices.FACTION)


@login_required
def orga_quest_types(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage quest types for an event."""
    # Check event context and permissions for quest types management
    context = check_event_context(request, event_slug, "orga_quest_types")
    return writing_list(request, context, QuestType, "quest_type")


@login_required
def orga_quest_types_view(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """View quest type details for organizers."""
    # Check permissions and get base context
    context = check_event_context(request, event_slug, ["orga_reading", "orga_quest_types"])

    # Load specific quest type into context
    get_quest_type(context, num)

    return writing_view(request, context, "quest_type")


@login_required
def orga_quest_types_edit(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Edit or create quest types for an event.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        num: Quest type ID (0 for new quest type)

    Returns:
        Rendered writing edit form response

    """
    # Check user permissions for quest type management
    context = check_event_context(request, event_slug, "orga_quest_types")

    # Load existing quest type if editing (num != 0)
    if num != 0:
        get_quest_type(context, num)

    # Render the writing edit form with quest type configuration
    return writing_edit(request, context, QuestTypeForm, "quest_type", TextVersionChoices.QUEST_TYPE)


@login_required
def orga_quest_types_versions(
    request: HttpRequest,
    event_slug: str,
    num: int,
) -> HttpResponse:
    """Display version history for a quest type.

    Args:
        request: The HTTP request object
        event_slug: Event slug identifier
        num: Quest type ID

    Returns:
        Rendered template with quest type version history

    """
    # Verify user has permission to access quest types for this event
    context = check_event_context(request, event_slug, "orga_quest_types")

    # Load the quest type and add it to context
    get_quest_type(context, num)

    # Render version history using the generic writing versions view
    return writing_versions(request, context, "quest_type", TextVersionChoices.QUEST_TYPE)


@login_required
def orga_quests(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display event quests list for organizers."""
    # Validate event access and permissions
    context = check_event_context(request, event_slug, "orga_quests")
    return writing_list(request, context, Quest, "quest")


@login_required
def orga_quests_view(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """View for managing quest content in the organization interface."""
    # Check permissions and prepare context
    context = check_event_context(request, event_slug, ["orga_reading", "orga_quests"])

    # Load specific quest data
    get_quest(context, num)

    return writing_view(request, context, "quest")


@login_required
def orga_quests_edit(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Edit or create a quest for an organization event.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: Event identifier string used to locate the specific event
        num: The quest ID to edit (0 for creating a new quest)

    Returns:
        HttpResponse: Redirect to quest types page if no quest types exist,
                     otherwise returns the quest editing form response

    Raises:
        PermissionDenied: If user lacks 'orga_quests' permission for the event
        Http404: If the specified quest number doesn't exist when num > 0

    """
    # Check user permissions for quest management on this event
    context = check_event_context(request, event_slug, "orga_quests")

    # Verify that quest types are available before allowing quest creation
    if not context["event"].get_elements(QuestType).exists():
        # Add warning message and redirect to quest types adding page
        messages.warning(request, _("You must create at least one quest type before you can create quests"))
        return redirect("orga_quest_types_edit", event_slug=event_slug, num=0)

    # Load existing quest data if editing (num > 0), otherwise prepare for new quest
    if num != 0:
        get_element(context, num, "quest", Quest)

    # Delegate to the generic writing edit handler with quest-specific parameters
    return writing_edit(request, context, QuestForm, "quest", TextVersionChoices.QUEST)


@login_required
def orga_quests_versions(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Display version history for a quest."""
    # Check user has permission to access quest versions
    context = check_event_context(request, event_slug, "orga_quests")
    get_quest(context, num)
    # Render versions page with quest-specific template
    return writing_versions(request, context, "quest", TextVersionChoices.QUEST)


@login_required
def orga_traits(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display traits management page for event organizers."""
    context = check_event_context(request, event_slug, "orga_traits")
    return writing_list(request, context, Trait, "trait")


@login_required
def orga_traits_view(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Display and manage trait details for event organizers."""
    context = check_event_context(request, event_slug, ["orga_reading", "orga_traits"])
    get_trait(context, num)
    return writing_view(request, context, "trait")


@login_required
def orga_traits_edit(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Handle editing of trait objects for organization events.

    Validates that quests exist before allowing trait creation, then delegates
    to the generic writing_edit function for trait-specific form handling.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: Event identifier string for URL routing
        num: The trait ID number (0 for creating new trait)

    Returns:
        HttpResponse: Either a redirect to quest creation or the trait edit form

    Raises:
        PermissionDenied: If user lacks orga_traits permission for the event

    """
    # Check user permissions and get event context
    context = check_event_context(request, event_slug, "orga_traits")

    # Validate prerequisite: at least one quest must exist
    if not context["event"].get_elements(Quest).exists():
        # Add warning message and redirect to quests adding page
        messages.warning(request, _("You must create at least one quest before you can create traits"))
        return redirect("orga_quests_edit", event_slug=event_slug, num=0)

    # Load existing trait data if editing (num != 0)
    if num != 0:
        get_trait(context, num)

    # Delegate to generic writing edit handler for trait processing
    return writing_edit(request, context, TraitForm, "trait", TextVersionChoices.TRAIT)


@login_required
def orga_traits_versions(
    request: HttpRequest,
    event_slug: str,
    num: int,
) -> HttpResponse:
    """Display version history for a specific trait."""
    context = check_event_context(request, event_slug, "orga_traits")
    get_trait(context, num)
    return writing_versions(request, context, "trait", TextVersionChoices.TRAIT)


@login_required
def orga_handouts(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display handouts list for event organizers."""
    # Check permissions and get event context for handouts feature
    context = check_event_context(request, event_slug, "orga_handouts")
    return writing_list(request, context, Handout, "handout")


@login_required
def orga_handouts_test(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Render a test preview of a handout PDF."""
    context = check_event_context(request, event_slug, "orga_handouts")
    get_handout(context, num)
    return render(request, "pdf/sheets/handout.html", context)


@login_required
def orga_handouts_print(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Generate and return a PDF for a specific handout."""
    # Check permissions and initialize event context
    context = check_event_context(request, event_slug, "orga_handouts")

    # Retrieve handout data and add to context
    get_handout(context, num)

    # Return PDF response
    return print_handout(context)


@login_required
def orga_handouts_view(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """View for displaying a specific handout document for organizers.

    Args:
        request: The HTTP request object
        event_slug: Event slug identifier
        num: Handout number to retrieve

    Returns:
        HTTP response with the rendered handout

    """
    # Check organizer permissions for handouts feature
    context = check_event_context(request, event_slug, "orga_handouts")

    # Fetch the requested handout and add to context
    get_handout(context, num)

    # Render and return the handout document
    return print_handout(context)


@login_required
def orga_handouts_edit(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Edit handouts for an organization event.

    Handles the editing of handouts for a specific event. Validates that handout
    templates exist before allowing handout creation, and redirects to template
    creation if none are found.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: Event identifier string for URL routing
        num: The handout number to edit (0 for new handout creation)

    Returns:
        HttpResponse: Rendered handout edit page or redirect response

    Raises:
        PermissionDenied: If user lacks required event permissions

    """
    # Check user permissions for handout management
    context = check_event_context(request, event_slug, "orga_handouts")

    # Validate handout templates exist before allowing handout creation
    if not context["event"].get_elements(HandoutTemplate).exists():
        # Display warning and redirect to template creation page
        messages.warning(request, _("You must create at least one handout template before you can create handouts"))
        return redirect("orga_handout_templates_edit", event_slug=event_slug, num=0)

    # Load existing handout if editing (num > 0)
    if num != 0:
        get_handout(context, num)

    # Delegate to generic writing edit handler with handout-specific parameters
    return writing_edit(request, context, HandoutForm, "handout", TextVersionChoices.HANDOUT)


@login_required
def orga_handouts_versions(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Get version history for a specific handout."""
    context = check_event_context(request, event_slug, "orga_handouts")
    get_handout(context, num)
    return writing_versions(request, context, "handout", TextVersionChoices.HANDOUT)


@login_required
def orga_handout_templates(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display handout template list for event organizers."""
    # Check permissions and retrieve event context
    context = check_event_context(request, event_slug, "orga_handout_templates")
    return writing_list(request, context, HandoutTemplate, "handout_template")


@login_required
def orga_handout_templates_edit(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Edit handout template for an event.

    Args:
        request: HTTP request object
        event_slug: Event slug
        num: Handout template ID (0 for new template)

    Returns:
        Rendered handout template edit page

    """
    # Check user has permission to manage handout templates
    context = check_event_context(request, event_slug, "orga_handout_templates")

    # Load existing template if num is not 0 (new template)
    if num != 0:
        get_handout_template(context, num)

    return writing_edit(request, context, HandoutTemplateForm, "handout_template", None)


@login_required
def orga_prologue_types(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display prologue types list for event organizers."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_prologue_types")
    return writing_list(request, context, PrologueType, "prologue_type")


@login_required
def orga_prologue_types_edit(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Edit or create a prologue type for an event.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        num: Prologue type ID (0 for new, otherwise existing ID)

    Returns:
        HTTP response with prologue type edit form

    """
    # Check user has permission to manage prologue types
    context = check_event_context(request, event_slug, "orga_prologue_types")

    # Load existing prologue type if editing (num != 0)
    if num != 0:
        get_prologue_type(context, num)

    # Render edit form using generic writing_edit handler
    return writing_edit(request, context, PrologueTypeForm, "prologue_type", None)


@login_required
def orga_prologues(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display the list of prologues for an event."""
    context = check_event_context(request, event_slug, "orga_prologues")
    return writing_list(request, context, Prologue, "prologue")


@login_required
def orga_prologues_view(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Render prologue view for event organizers."""
    # Check organizer permissions for prologue/reading access
    context = check_event_context(request, event_slug, ["orga_reading", "orga_prologues"])

    # Load specific prologue into context
    get_prologue(context, num)

    return writing_view(request, context, "prologue")


@login_required
def orga_prologues_edit(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Edit or create prologues for an event.

    Args:
        request: The HTTP request object
        event_slug: Event identifier string
        num: The prologue number (0 for new prologue, >0 for existing)

    Returns:
        HttpResponse: Redirect to prologue types page if no types exist,
                     otherwise renders the prologue edit form

    """
    # Check user permissions for prologue management
    context = check_event_context(request, event_slug, "orga_prologues")

    # Verify that prologue types are configured before allowing prologue creation
    if not context["event"].get_elements(PrologueType).exists():
        # Inform user that prologue types must be created first
        messages.warning(request, _("You must create at least one prologue type before you can create prologues"))
        return redirect("orga_prologue_types_edit", event_slug=event_slug, num=0)

    # Load existing prologue data if editing (num > 0)
    if num != 0:
        get_prologue(context, num)

    # Render the prologue editing form with appropriate configuration
    return writing_edit(request, context, PrologueForm, "prologue", TextVersionChoices.PROLOGUE)


@login_required
def orga_prologues_versions(
    request: HttpRequest,
    event_slug: str,
    num: int,
) -> HttpResponse:
    """Display version history for a specific prologue.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        num: Prologue number

    Returns:
        HTTP response with prologue version history

    """
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_prologues")

    # Retrieve the prologue and add to context
    get_prologue(context, num)

    # Display version history for the prologue
    return writing_versions(request, context, "prologue", TextVersionChoices.PROLOGUE)


@login_required
def orga_speedlarps(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display list of speed LARPs for an event."""
    context = check_event_context(request, event_slug, "orga_speedlarps")
    return writing_list(request, context, SpeedLarp, "speedlarp")


@login_required
def orga_speedlarps_view(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """View a specific speedlarp for organizers."""
    context = check_event_context(request, event_slug, ["orga_reading", "orga_speedlarps"])
    get_speedlarp(context, num)
    return writing_view(request, context, "speedlarp")


@login_required
def orga_speedlarps_edit(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Edit speedlarp writing content for an event."""
    # Check permissions and initialize context
    context = check_event_context(request, event_slug, "orga_speedlarps")

    # Load existing speedlarp if editing (num != 0 means edit mode)
    if num != 0:
        get_speedlarp(context, num)

    # Render writing edit form
    return writing_edit(request, context, SpeedLarpForm, "speedlarp", TextVersionChoices.SPEEDLARP)


@login_required
def orga_speedlarps_versions(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Display version history for a speedlarp."""
    # Check permissions and load speedlarp
    context = check_event_context(request, event_slug, "orga_speedlarps")
    get_speedlarp(context, num)

    # Return version history view
    return writing_versions(request, context, "speedlarp", TextVersionChoices.SPEEDLARP)


@login_required
def orga_assignments(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render the character assignments page for event organizers."""
    # Check event permissions and populate context with event cache data
    context = check_event_context(request, event_slug, "orga_assignments")
    get_event_cache_all(context)
    return render(request, "larpmanager/orga/writing/assignments.html", context)


@login_required
def orga_progress_steps(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Return progress steps list for event organization."""
    # Check permissions and get event context, then return progress steps list
    context = check_event_context(request, event_slug, "orga_progress_steps")
    return writing_list(request, context, ProgressStep, "progress_step")


@login_required
def orga_progress_steps_edit(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Edit a progress step for an event."""
    return orga_edit(request, event_slug, "orga_progress_steps", OrgaProgressStepForm, num)


@login_required
def orga_progress_steps_order(
    request: HttpRequest,
    event_slug: str,
    num: int,
    order: int,
) -> HttpResponse:
    """Reorder progress steps for an event."""
    # Verify user has permission to modify progress steps
    context = check_event_context(request, event_slug, "orga_progress_steps")

    # Update the display order of the specified step
    exchange_order(context, ProgressStep, num, order)

    return redirect("orga_progress_steps", event_slug=context["run"].get_slug())


@login_required
def orga_multichoice_available(request: HttpRequest, event_slug: str) -> JsonResponse | Http404:
    """Handle AJAX requests for available multichoice options for organizers.

    This function processes POST requests to retrieve character options that are
    available for selection, excluding those already taken based on the specified
    type (registrations, abilities, etc.).

    Args:
        request: HTTP request object containing POST data with 'type' and optional 'eid'
        event_slug: Event slug identifier

    Returns:
        JSON response containing available character options as list of tuples
        with format: {"res": [(character_id, character_str), ...]}

    Raises:
        Http404, if request method is not POST

    """
    # Validate request method
    if request.method != "POST":
        return Http404()

    # Extract class name from POST data
    class_name = request.POST.get("type", "")
    taken_characters = set()

    # Handle registration-specific character filtering
    if class_name == "registrations":
        context = check_event_context(request, event_slug, "orga_registrations")
        # Get characters already assigned to registrations in this run
        taken_characters = RegistrationCharacterRel.objects.filter(reg__run_id=context["run"].id).values_list(
            "character_id",
            flat=True,
        )
    else:
        # Handle other class types (abilities, etc.)
        eid = request.POST.get("eid", "")
        perms = {"abilitypx": "orga_px_abilities"}

        # Determine permission based on class name
        perm = perms[class_name] if class_name in perms else "orga_" + class_name + "s"

        # Check permissions for the event
        context = check_event_context(request, event_slug, perm)

        # Get characters already assigned to the specific entity
        if eid:
            model_class = apps.get_model("larpmanager", inflection.camelize(class_name))
            taken_characters = model_class.objects.get(pk=int(eid)).characters.values_list("id", flat=True)

    # Get all characters for the event, ordered by number
    context["list"] = context["event"].get_elements(Character).order_by("number")

    # Exclude already taken characters
    context["list"] = context["list"].exclude(pk__in=taken_characters)

    # Format response as list of tuples (id, string representation)
    res = [(el.id, str(el)) for el in context["list"]]
    return JsonResponse({"res": res})


@login_required
def orga_factions_available(request: HttpRequest, event_slug: str) -> JsonResponse | Http404:
    """Return available factions for character assignment via AJAX.

    Args:
        request: HTTP POST request containing orga and eid parameters
        event_slug: Event slug string identifying the event

    Returns:
        JsonResponse: JSON response with available factions list or error status
            - Success: {"res": [[faction_id, faction_name], ...]}
            - Error: {"res": "ko"}

    Raises:
        Http404: If request method is not POST

    """
    # Validate request method - only POST allowed
    if request.method != "POST":
        return Http404()

    # Get event context from slug
    context = get_event_context(request, event_slug)

    # Get all factions for this event, ordered by number
    context["list"] = context["event"].get_elements(Faction).order_by("number")

    # Filter by selectable factions if not orga user
    orga = int(request.POST.get("orga", "0"))
    if not orga:
        context["list"] = context["list"].filter(selectable=True)

    # Exclude factions already assigned to character if eid provided
    eid = int(request.POST.get("eid", "0"))
    if eid:
        # Get character by ID and validate existence
        try:
            character = context["event"].get_elements(Character).prefetch_related("factions_list").get(pk=int(eid))
            # Get list of faction IDs already assigned to this character
            taken_factions = character.factions_list.values_list("id", flat=True)
            context["list"] = context["list"].exclude(pk__in=taken_factions)
        except ObjectDoesNotExist:
            return JsonResponse({"res": "ko"})

    # Convert queryset to list of tuples (id, name) for JSON response
    res = [(el.id, str(el)) for el in context["list"]]
    return JsonResponse({"res": res})


@login_required
def orga_export(request: HttpRequest, event_slug: str, export_name: str) -> HttpResponse:
    """Export data for a specific model in organization context.

    Args:
        request: HTTP request object
        event_slug: Event slug
        export_name: Model name (lowercase)

    Returns:
        Rendered export template with model data

    """
    # Check permissions for the specific model
    perm = f"orga_{export_name}s"
    context = check_event_context(request, event_slug, perm)

    # Get the model class dynamically
    model = apps.get_model("larpmanager", export_name.capitalize())

    # Export model data and prepare context
    context["nm"] = export_name
    export = export_data(context, model, member_cover=True)[0]
    _model, context["key"], context["vals"] = export

    return render(request, "larpmanager/orga/export.html", context)


@login_required
def orga_version(request: HttpRequest, event_slug: str, name: str, num: int) -> HttpResponse:
    """Render version details for organization text content.

    Args:
        request: The HTTP request object
        event_slug: Event slug identifier
        name: Text type name (e.g., 'chronicle', 'story')
        num: Version primary key

    Returns:
        Rendered HTML response with version details

    """
    # Check organization permissions for text type access
    perm = f"orga_{name}s"
    context = check_event_context(request, event_slug, perm)

    # Find text type code matching the provided name
    tp = next(code for code, label in TextVersionChoices.choices if label.lower() == name)

    # Retrieve specific version and format text for HTML display
    context["version"] = TextVersion.objects.get(tp=tp, pk=num)
    context["text"] = context["version"].text.replace("\n", "<br />")

    return render(request, "larpmanager/orga/version.html", context)


@login_required
def orga_reading(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display all writing elements for organizer reading/review.

    This function retrieves and displays all writing elements (characters, plots,
    factions, etc.) for an event organizer to read and review. It checks permissions
    and filters elements based on enabled features.

    Args:
        request (HttpRequest): The HTTP request object containing user and session data
        event_slug (str): Event slug string used to identify the specific event

    Returns:
        HttpResponse: Rendered reading.html template with context containing all
                     writing elements available for review

    Raises:
        PermissionDenied: If user lacks organizer reading permissions for the event

    """
    # Check user permissions for organizer reading access
    context = check_event_context(request, event_slug, "orga_reading")

    # Define text fields that need cache retrieval for performance
    text_fields = ["teaser", "text"]

    # Initialize list to store all writing elements
    context["alls"] = []

    # Get mapping of model names to their corresponding features
    mapping = _get_writing_mapping()

    # Iterate through all writing element types to collect enabled ones
    for typ in [Character, Plot, Faction, Quest, Trait, Prologue, SpeedLarp]:
        # Get model name from Django model metadata
        # noinspection PyUnresolvedReferences, PyProtectedMember
        model_name = typ._meta.model_name  # noqa: SLF001  # Django model metadata

        # Skip this type if its feature is not enabled for the event
        if mapping.get(model_name) not in context["features"]:
            continue

        # Retrieve all elements of this type for the current event
        context["list"] = context["event"].get_elements(typ)

        # Cache text fields for performance optimization
        retrieve_cache_text_field(context, text_fields, typ)

        # Process each element: set display type and generate view URL
        for el in context["list"]:
            el.type = _(model_name)
            el.url = reverse(f"orga_{model_name}s_view", args=[context["run"].get_slug(), el.id])

        # Add all elements of this type to the combined list
        context["alls"].extend(context["list"])

    return render(request, "larpmanager/orga/reading.html", context)
