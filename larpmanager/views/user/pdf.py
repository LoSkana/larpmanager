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

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse

from larpmanager.utils.character import get_char_check
from larpmanager.utils.event import get_event_run
from larpmanager.utils.pdf import (
    print_character,
    print_character_friendly,
    print_character_rel,
    print_gallery,
    print_profiles,
)


def check_print_pdf(context):
    if "show_addit" not in context or "print_pdf" not in context["show_addit"]:
        raise Http404("not ready")


@login_required
def character_pdf_sheet(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Generate PDF character sheet for an event run.

    Args:
        request: HTTP request object
        s: Event slug identifier
        num: Character number

    Returns:
        HTTP response containing the PDF character sheet
    """
    # Get event run context with signup verification
    context = get_event_run(request, s, signup=True)

    # Verify PDF printing permissions
    check_print_pdf(context)

    # Validate character access and retrieve character data
    get_char_check(request, context, num, True)

    # Generate and return the character PDF
    return print_character(context)


@login_required
def character_pdf_sheet_friendly(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Generate a printer-friendly character sheet PDF.

    Args:
        request: The HTTP request object
        s: Event slug identifier
        num: Character number

    Returns:
        HttpResponse containing the printer-friendly character PDF
    """
    # Get event run context and validate signup access
    context = get_event_run(request, s, signup=True)

    # Verify PDF printing permissions
    check_print_pdf(context)

    # Retrieve and validate character access
    get_char_check(request, context, num, True)

    # Generate and return the printer-friendly PDF
    return print_character_friendly(context)


@login_required
def character_pdf_relationships(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Generate PDF with character relationships for a specific character.

    Args:
        request: HTTP request object
        s: Event slug identifier
        num: Character number

    Returns:
        PDF response with character relationships
    """
    # Get event/run context with signup validation
    context = get_event_run(request, s, signup=True)

    # Verify PDF printing permissions
    check_print_pdf(context)

    # Validate character access and retrieve character data
    get_char_check(request, context, num, True)

    # Generate and return the relationships PDF
    return print_character_rel(context)


@login_required
def portraits(request, s):
    context = get_event_run(request, s, signup=True)
    return print_gallery(context)


@login_required
def profiles(request, s):
    context = get_event_run(request, s, signup=True)
    return print_profiles(context)
