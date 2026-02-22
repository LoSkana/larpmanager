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


from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_all, get_writing_element_fields
from larpmanager.forms.event import EventCharactersPdfForm
from larpmanager.models.event import Run
from larpmanager.models.form import QuestionApplicable
from larpmanager.models.writing import Character, Faction, Handout
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.core.common import get_element
from larpmanager.utils.io.pdf import (
    add_pdf_instructions,
    print_bulk,
    print_character,
    print_character_bkg,
    print_character_friendly,
    print_character_rel,
    print_faction,
    print_gallery,
    print_profiles,
)
from larpmanager.utils.services.character import get_char_check, get_character_relationships, get_character_sheet


@login_required
def orga_characters_pdf(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Generate PDF view for event characters with form handling.

    This view allows organizers to configure and generate PDF exports of
    character data for a specific event. Handles both GET requests to display
    the form and POST requests to update event settings.

    Args:
        request: The HTTP request object containing user data and form submissions
        event_slug: Event identifier string used to locate the specific event

    Returns:
        HttpResponse: Rendered template with character list and configuration form

    Raises:
        PermissionDenied: If user lacks 'orga_characters_pdf' permission for event

    """
    # Check user permissions and get event context
    context = check_event_context(request, event_slug, "orga_characters_pdf")

    # Handle form submission for PDF configuration updates
    if request.method == "POST":
        form = EventCharactersPdfForm(request.POST, request.FILES, instance=context["event"])

        # Validate and save form data, then redirect to prevent resubmission
        if form.is_valid():
            form.save()
            messages.success(request, _("Updated") + "!")
            return redirect(request.path_info)
    else:
        # Initialize form with current event data for GET requests
        form = EventCharactersPdfForm(instance=context["event"])

    # Retrieve ordered character list for the event
    context["list"] = context["event"].get_elements(Character).order_by("number")

    # Add form to context for template rendering
    context["form"] = form

    # Render the PDF configuration template with character data
    return render(request, "larpmanager/orga/characters/pdf.html", context)


@login_required
def orga_characters_pdf_bulk(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Generate and download a bulk ZIP file of selected PDFs for an event.

    This view provides both a selection interface (GET) and bulk PDF generation (POST).
    On GET requests, displays a form where organizers can select which PDFs to include
    in the bulk download. On POST requests, generates all selected PDFs and returns them
    as a timestamped ZIP file.

    Available PDF types:
    - Gallery: Character portraits
    - Profiles: Character profile sheets
    - Character sheets: Individual character sheets
    - Faction sheets: Individual faction sheets
    - Handouts: Event handouts

    Args:
        request: HTTP request object (GET for form, POST for generation)
        event_slug: Event slug identifier

    Returns:
        GET: Rendered selection form with list of available PDFs
        POST: ZIP file download containing all selected PDFs

    Raises:
        PermissionDenied: If user lacks orga_characters_pdf permission

    """
    # Verify organizer permissions for PDF access
    context = check_event_context(request, event_slug, "orga_characters_pdf")

    # Handle POST request - generate and return bulk ZIP file
    if request.method == "POST":
        return print_bulk(context, request)

    # Build list of available PDF options for selection form
    context["list"] = {
        "gallery": {"name": _("Gallery")},
        "profiles": {"name": _("Profiles")},
    }

    # Add all characters, factions, and handouts to selection list
    mappings = {
        "character": Character,
        "faction": Faction,
        "handout": Handout,
    }
    for key_name, value_type in mappings.items():
        for element in context["event"].get_elements(value_type):
            # Create dict entry with name and type for template rendering
            context["list"][f"{key_name}_{element.id}"] = {"name": element.name, "type": value_type._meta.model_name}  # noqa: SLF001  # Django model metadata

    # Render selection form
    return render(request, "larpmanager/orga/characters/pdf_bulk.html", context)


@login_required
def orga_pdf_regenerate(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Regenerate PDF files for all characters in future event runs.

    Args:
        request: HTTP request object
        event_slug: Event slug string

    Returns:
        Redirect response to characters PDF page

    """
    # Check user permissions for PDF operations
    context = check_event_context(request, event_slug, "orga_characters_pdf")

    # Get all characters associated with the event
    chs = context["event"].get_elements(Character)

    # Iterate through all future runs of the event
    for run in Run.objects.filter(event=context["event"], end__gte=timezone.now()):
        # Generate PDF for each character in each run
        for ch in chs:
            print_character_bkg(context["event"].association.slug, run.get_slug(), ch.uuid)

    # Show success message and redirect
    messages.success(request, _("Regeneration pdf started") + "!")
    return redirect("orga_characters_pdf", event_slug=context["run"].get_slug())


@login_required
def orga_characters_sheet_pdf(request: HttpRequest, event_slug: str, character_uuid: str) -> HttpResponse:
    """Generate PDF character sheet for organizers."""
    # Check organizer permissions for PDF access
    context = check_event_context(request, event_slug, "orga_characters_pdf")

    # Retrieve and validate character data
    get_char_check(request, context, character_uuid, restrict_non_owners=True)

    # Generate and return the character sheet PDF
    return print_character(context, force=True)


@login_required
def orga_characters_sheet_test(request: HttpRequest, event_slug: str, character_uuid: str) -> HttpResponse:
    """Generate a character sheet PDF for testing purposes.

    Args:
        request: The HTTP request object
        event_slug: Event slug identifier
        character_uuid: Character uuid

    Returns:
        Rendered PDF template response

    """
    # Check user permissions for character PDF generation
    context = check_event_context(request, event_slug, "orga_characters_pdf")

    # Validate and retrieve character data
    get_char_check(request, context, character_uuid, restrict_non_owners=True)

    # Configure context for PDF rendering
    context["pdf"] = True
    get_character_sheet(context)
    add_pdf_instructions(context)

    # Render the auxiliary PDF template
    return render(request, "pdf/sheets/auxiliary.html", context)


@login_required
def orga_characters_friendly_pdf(request: HttpRequest, event_slug: str, character_uuid: str) -> HttpResponse:
    """Generate friendly PDF for a character."""
    # Check permissions for PDF generation
    context = check_event_context(request, event_slug, "orga_characters_pdf")

    # Validate and retrieve character
    get_char_check(request, context, character_uuid, restrict_non_owners=True)

    return print_character_friendly(context, force=True)


@login_required
def orga_characters_friendly_test(request: HttpRequest, event_slug: str, character_uuid: str) -> HttpResponse:
    """Generate friendly test character sheet PDF."""
    # Verify user has permission to access character PDFs
    context = check_event_context(request, event_slug, "orga_characters_pdf")

    # Retrieve and validate character, ensuring user has access
    get_char_check(request, context, character_uuid, restrict_non_owners=True)

    # Populate context with character sheet data
    get_character_sheet(context)

    return render(request, "pdf/sheets/friendly.html", context)


@login_required
def orga_characters_relationships_pdf(request: HttpRequest, event_slug: str, character_uuid: str) -> HttpResponse:
    """Generate PDF of character relationships for organization view."""
    # Verify event permissions for PDF generation
    context = check_event_context(request, event_slug, "orga_characters_pdf")

    # Retrieve and validate character data
    get_char_check(request, context, character_uuid, bypass_access_checks=True)

    # Generate and return relationship PDF
    return print_character_rel(context, force=True)


@login_required
def orga_characters_relationships_test(request: HttpRequest, event_slug: str, character_uuid: str) -> HttpResponse:
    """Generate character relationships test PDF for organization view.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        character_uuid: Character uuid

    Returns:
        Rendered relationships template response

    """
    # Check organization permissions for character PDF access
    context = check_event_context(request, event_slug, "orga_characters_pdf")

    # Validate character access and retrieve character data
    get_char_check(request, context, character_uuid, restrict_non_owners=True)

    # Populate context with character sheet and relationship data
    get_character_sheet(context)
    get_character_relationships(context)

    return render(request, "pdf/sheets/relationships.html", context)


@login_required
def orga_gallery_pdf(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Generate PDF version of event character gallery for organizers."""
    context = check_event_context(request, event_slug, "orga_characters_pdf")
    return print_gallery(context, force=True)


@login_required
def orga_gallery_test(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render gallery template for character sheets in PDF format."""
    context = check_event_context(request, event_slug, "orga_characters_pdf")
    return render(request, "pdf/sheets/gallery.html", context)


@login_required
def orga_profiles_pdf(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Generate PDF export of character profiles for an event."""
    # Verify permissions and retrieve event context
    context = check_event_context(request, event_slug, "orga_characters_pdf")

    # Generate and return the profiles PDF
    return print_profiles(context, force=True)


@login_required
def orga_factions_sheet_pdf(request: HttpRequest, event_slug: str, faction_uuid: str) -> HttpResponse:
    """Generate and download a faction sheet PDF for organizers.

    This view generates a comprehensive PDF document for a specific faction, including
    faction details, custom fields configured for the event, and all relevant faction
    information formatted for organizer use or distribution to players.

    The PDF is always force-generated (not cached) to ensure the most up-to-date
    information is included.

    Args:
        request: HTTP request object containing user authentication
        event_slug: Event slug identifier for the specific event
        faction_uuid: Faction uuid to generate the sheet for

    Returns:
        HttpResponse: PDF file download response with the faction sheet

    Raises:
        PermissionDenied: If user lacks orga_characters_pdf permission
        Http404: If faction with the specified number doesn't exist or isn't in cache

    """
    # Verify organizer permissions for PDF generation
    context = check_event_context(request, event_slug, "orga_characters_pdf")

    # Load faction data into context by faction number
    get_element(context, faction_uuid, "faction", Faction)

    # Load all event cache data for faction sheet rendering
    get_event_cache_all(context)

    for faction in context["factions"].values():
        if faction.get("uuid", "") == faction_uuid:
            context["sheet_faction"] = faction

    if "sheet_faction" not in context:
        # Faction number not found in cache
        msg = "Faction does not exist"
        raise Http404(msg)

    # Load custom faction fields configured for this event
    # Only visible fields are included in the PDF
    context["fact"] = get_writing_element_fields(
        context,
        "faction",
        QuestionApplicable.FACTION,
        context["faction"].id,
        only_visible=True,
    )

    # Generate and return the faction sheet PDF (force=True for fresh generation)
    return print_faction(context, force=True)
