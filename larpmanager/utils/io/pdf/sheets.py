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

from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings as conf_settings
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.association_text import get_association_text
from larpmanager.cache.character import get_event_cache_all
from larpmanager.cache.media import get_run_gallery_filepath, get_run_profiles_filepath
from larpmanager.models.association import AssociationTextType
from larpmanager.models.writing import FactionType
from larpmanager.utils.io.pdf.engine import (
    _PrintableDict,
    _round_image_data_uri,
    add_pdf_instructions,
    reprint,
    return_pdf,
    xhtml_pdf,
)
from larpmanager.utils.services.character import get_character_relationships, get_character_sheet

if TYPE_CHECKING:
    from django.http import HttpResponse

    from larpmanager.models.member import Member


def get_membership_request(context: dict, member: Member) -> HttpResponse:
    """Generate and return a PDF membership registration document."""
    # Get the file path for the member's request document
    file_path = member.get_request_filepath()

    # Prepare template context with member data as plain strings
    member_data = {field.name: str(getattr(member, field.name) or "") for field in member._meta.fields}  # noqa: SLF001
    member_data["display_member"] = member.display_member()
    member_data["display_real"] = member.display_real()
    member_data["get_residence"] = member.get_residence()

    # Expose safe user fields, keeping direct printing of `member.user` unchanged
    user = member.user
    member_data["user"] = _PrintableDict(
        str(user),
        {name: str(getattr(user, name, "") or "") for name in ("username", "email", "first_name", "last_name")},
    )

    template_context = {"member": member_data}

    # Retrieve association-specific membership template text
    template = get_association_text(context["association_id"], AssociationTextType.MEMBERSHIP)

    # Generate PDF from template and return as HTTP response
    xhtml_pdf(template_context, template, file_path, html=True)
    return return_pdf(file_path, _("Membership application form for %(user)s") % {"user": member})


def print_character(context: dict, *, force: bool = False) -> HttpResponse:
    """Generate character sheet PDF with optional force regeneration.

    Args:
        context: Context dictionary containing character and run data
        force: Whether to force PDF regeneration regardless of existing file

    Returns:
        PDF response dictionary for character sheet

    """
    # Get the file path for the character sheet PDF
    file_path = context["character"].get_sheet_filepath(context["run"])
    context["pdf"] = True

    # Generate PDF if forced or if reprint is needed
    if force or reprint(file_path):
        _get_character_pdf_data(context)
        add_pdf_instructions(context)
        xhtml_pdf(context, "pdf/sheets/auxiliary.html", file_path)

    # Return the PDF response
    return return_pdf(file_path, context["character"].name)


def _process_rel_images(context: dict) -> None:
    blank_avatar_url = conf_settings.STATIC_URL + "larpmanager/assets/blank-avatar.png"
    blank_avatar_uri = _round_image_data_uri(blank_avatar_url)
    for rel_entry in context.get("rel", []):
        url = rel_entry.get("player_prof") or blank_avatar_url
        rounded = _round_image_data_uri(url)
        rel_entry["player_prof"] = rounded or blank_avatar_uri


def _get_character_pdf_data(context: dict) -> None:
    """Add to context the data needed for pdf write of character."""
    if context.get("writing_field_visibility"):
        context.pop("show_all", None)
    get_character_sheet(context)
    get_event_cache_all(context)
    get_character_relationships(context)
    _process_rel_images(context)


def print_character_friendly(context: dict, *, force: bool = False) -> HttpResponse:
    """Generate and return a lightweight character sheet PDF.

    Args:
        context: Context dictionary containing character and run data
        force: Whether to force regeneration of the PDF file

    Returns:
        HTTP response containing the PDF file

    """
    # Get the file path for the friendly character sheet
    file_path = context["character"].get_sheet_friendly_filepath(context["run"])
    context["pdf"] = True

    # Generate PDF if forced or if file needs reprinting
    if force or reprint(file_path):
        context["light_pdf"] = True
        _get_character_pdf_data(context)
        xhtml_pdf(context, "pdf/sheets/friendly.html", file_path)

    # Return the PDF file as HTTP response
    return return_pdf(file_path, f"{context['character'].name} - " + _("Lightweight"))


def print_faction(context: dict, *, force: bool = False) -> HttpResponse:
    """Generate and return a faction sheet PDF with optional force regeneration.

    Creates a PDF document containing the faction sheet using the xhtml2pdf engine.
    The PDF includes faction details, custom fields, and formatting specified in the
    faction template. The generated PDF is cached and only regenerated when forced
    or when the cache is outdated.

    Args:
        context: Context dictionary that must contain:
            - 'faction': The Faction model instance
            - 'run': The Run model instance for file path generation
            - Additional faction-specific data for template rendering
        force: If True, regenerate the PDF even if a cached version exists;
            if False, use cached version if available and up-to-date. Defaults to False.

    Returns:
        HttpResponse: PDF file response configured for download with the faction name
            as the filename

    Side Effects:
        - Sets context["pdf"] = True for template rendering flags
        - Creates/updates faction PDF file in the media directory

    """
    # Get the file path for the faction sheet PDF
    file_path = context["faction"].get_sheet_filepath(context["run"])

    # Set PDF flag for template conditional rendering
    context["pdf"] = True

    # Generate PDF if forced or if file needs reprinting (outdated/missing)
    if force or reprint(file_path):
        xhtml_pdf(context, "pdf/sheets/faction.html", file_path)

    # Return the PDF file as HTTP response with faction name in filename
    return return_pdf(file_path, context["faction"].name)


def print_gallery(context: dict, *, force: bool = False) -> HttpResponse:
    """Generate and return a PDF gallery of character portraits.

    Creates a PDF containing character portraits for characters with first aid
    capabilities. The PDF is cached and only regenerated when forced or when
    the cache is outdated.

    Args:
        context: Context dictionary containing run information and character data
        force: Whether to force regeneration of the PDF even if cache is valid

    Returns:
        PDF response object for download/display

    """
    # Get the filepath where the gallery PDF should be stored
    filepath = get_run_gallery_filepath(context["run"].id)

    # Check if we need to regenerate the PDF (forced or cache outdated)
    if force or reprint(filepath):
        # Load all event cache data into context
        get_event_cache_all(context)

        # Initialize list to store characters with first aid capability
        context["first_aid"] = []

        # Iterate through all characters to find those with first aid
        for character_element in context["chars"].values():
            if "first_aid" in character_element and character_element["first_aid"] == "y":
                context["first_aid"].append(character_element)

        # Re-get filepath (in case it changed during cache loading)
        filepath = get_run_gallery_filepath(context["run"].id)

        # Generate the PDF from the gallery template
        xhtml_pdf(context, "pdf/sheets/gallery.html", filepath)

    # Return the PDF file as a downloadable response
    return return_pdf(filepath, str(context["run"]) + " - " + _("Portraits"))


def print_profiles(context: dict, *, force: bool = False) -> HttpResponse:
    """Generate and return PDF profiles for the event run.

    Args:
        context: Context dictionary containing run and event data
        force: If True, regenerate PDF even if it exists

    Returns:
        Tuple containing PDF response and filename

    """
    # Get the filepath for the profiles PDF
    filepath = get_run_profiles_filepath(context["run"].id)

    # Check if we need to regenerate the PDF
    if force or reprint(filepath):
        # Load all event cache data
        get_event_cache_all(context)
        for character_data in context["chars"].values():
            names = []
            for faction_number in character_data.get("factions", []):
                if not faction_number or faction_number not in context["factions"]:
                    continue
                faction_data = context["factions"][faction_number]
                if not faction_data["name"] or faction_data["typ"] == FactionType.SECRET:
                    continue
                names.append(faction_data["name"])
            character_data["factions_list"] = ", ".join(names)
        # Generate PDF from HTML template
        xhtml_pdf(context, "pdf/sheets/profiles.html", filepath)

    # Return the PDF file with appropriate filename
    return return_pdf(filepath, str(context["run"]) + " - " + _("Profiles"))


def print_handout(context: dict, *, force: bool = True) -> HttpResponse:
    """Generate and return a PDF handout for the given context."""
    # Get the file path for the handout PDF
    file_path = context["handout"].get_filepath()

    # Generate PDF if forced or if reprint is needed
    if force or reprint(file_path):
        context["handout"].data = context["handout"].show_complete()
        xhtml_pdf(context, "pdf/sheets/handout.html", file_path)

    # Return the PDF file response
    return return_pdf(file_path, f"{context['handout'].data['name']}")


def print_volunteer_registry(context: dict) -> str:
    """Generate volunteer registry PDF and return file path."""
    # Build file path for volunteer registry PDF
    file_path = str(Path(conf_settings.MEDIA_ROOT) / f"volunteer_registry/{context['association'].slug}.pdf")

    # Generate PDF from template
    xhtml_pdf(context, "pdf/volunteer_registry.html", file_path)

    return file_path
