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

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.event import EventCharactersPdfForm
from larpmanager.models.event import Run
from larpmanager.models.writing import Character
from larpmanager.utils.character import get_char_check, get_character_relationships, get_character_sheet
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.pdf import (
    add_pdf_instructions,
    print_character,
    print_character_bkg,
    print_character_friendly,
    print_character_rel,
    print_gallery,
    print_profiles,
)


@login_required
def orga_characters_pdf(request: HttpRequest, s: str) -> HttpResponse:
    """Generate PDF view for event characters with form handling.

    This view allows organizers to configure and generate PDF exports of
    character data for a specific event. Handles both GET requests to display
    the form and POST requests to update event settings.

    Args:
        request: The HTTP request object containing user data and form submissions
        s: The event slug identifier used to locate the specific event

    Returns:
        HttpResponse: Rendered template with character list and configuration form

    Raises:
        PermissionDenied: If user lacks 'orga_characters_pdf' permission for event
    """
    # Check user permissions and get event context
    context = check_event_permission(request, s, "orga_characters_pdf")

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
def orga_pdf_regenerate(request: HttpRequest, s: str) -> HttpResponse:
    """Regenerate PDF files for all characters in future event runs.

    Args:
        request: HTTP request object
        s: Event slug string

    Returns:
        Redirect response to characters PDF page
    """
    # Check user permissions for PDF operations
    context = check_event_permission(request, s, "orga_characters_pdf")

    # Get all characters associated with the event
    chs = context["event"].get_elements(Character)

    # Iterate through all future runs of the event
    for run in Run.objects.filter(event=context["event"], end__gte=datetime.now()):
        # Generate PDF for each character in each run
        for ch in chs:
            print_character_bkg(context["event"].assoc.slug, run.get_slug(), ch.number)

    # Show success message and redirect
    messages.success(request, _("Regeneration pdf started") + "!")
    return redirect("orga_characters_pdf", s=context["run"].get_slug())


@login_required
def orga_characters_sheet_pdf(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Generate PDF character sheet for organizers.

    Args:
        request: HTTP request object
        s: Event slug identifier
        num: Character number/ID

    Returns:
        HTTP response containing the generated PDF
    """
    # Check organizer permissions for PDF access
    context = check_event_permission(request, s, "orga_characters_pdf")

    # Retrieve and validate character data
    get_char_check(request, context, num, True)

    # Generate and return the character sheet PDF
    return print_character(context, True)


@login_required
def orga_characters_sheet_test(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Generate a character sheet PDF for testing purposes.

    Args:
        request: The HTTP request object
        s: Event slug identifier
        num: Character number

    Returns:
        Rendered PDF template response
    """
    # Check user permissions for character PDF generation
    context = check_event_permission(request, s, "orga_characters_pdf")

    # Validate and retrieve character data
    get_char_check(request, context, num, True)

    # Configure context for PDF rendering
    context["pdf"] = True
    get_character_sheet(context)
    add_pdf_instructions(context)

    # Render the auxiliary PDF template
    return render(request, "pdf/sheets/auxiliary.html", context)


@login_required
def orga_characters_friendly_pdf(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Generate friendly PDF for a character."""
    # Check permissions for PDF generation
    context = check_event_permission(request, s, "orga_characters_pdf")

    # Validate and retrieve character
    get_char_check(request, context, num, True)

    return print_character_friendly(context, True)


@login_required
def orga_characters_friendly_test(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Generate friendly test character sheet PDF.

    Args:
        request: HTTP request object
        s: Event slug
        num: Character number

    Returns:
        Rendered PDF template for friendly test sheet
    """
    # Verify user has permission to access character PDFs
    context = check_event_permission(request, s, "orga_characters_pdf")

    # Retrieve and validate character, ensuring user has access
    get_char_check(request, context, num, True)

    # Populate context with character sheet data
    get_character_sheet(context)

    return render(request, "pdf/sheets/friendly.html", context)


@login_required
def orga_characters_relationships_pdf(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Generate PDF of character relationships for organization view."""
    # Verify event permissions for PDF generation
    context = check_event_permission(request, s, "orga_characters_pdf")

    # Retrieve and validate character data
    get_char_check(request, context, num, False, True)

    # Generate and return relationship PDF
    return print_character_rel(context, True)


@login_required
def orga_characters_relationships_test(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Generate character relationships test PDF for organization view.

    Args:
        request: HTTP request object
        s: Event slug identifier
        num: Character number

    Returns:
        Rendered relationships template response
    """
    # Check organization permissions for character PDF access
    context = check_event_permission(request, s, "orga_characters_pdf")

    # Validate character access and retrieve character data
    get_char_check(request, context, num, True)

    # Populate context with character sheet and relationship data
    get_character_sheet(context)
    get_character_relationships(context)

    return render(request, "pdf/sheets/relationships.html", context)


@login_required
def orga_gallery_pdf(request, s):
    context = check_event_permission(request, s, "orga_characters_pdf")
    return print_gallery(context, True)


@login_required
def orga_gallery_test(request, s):
    context = check_event_permission(request, s, "orga_characters_pdf")
    return render(request, "pdf/sheets/gallery.html", context)


@login_required
def orga_profiles_pdf(request, s):
    context = check_event_permission(request, s, "orga_characters_pdf")
    return print_profiles(context, True)
