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
import io
import logging
import re
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template import Context, Template
from django.template.loader import get_template
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from xhtml2pdf import pisa

from larpmanager.cache.association import get_cache_association
from larpmanager.cache.association_text import get_association_text
from larpmanager.cache.character import get_event_cache_all, get_writing_element_fields
from larpmanager.cache.config import get_event_config
from larpmanager.models.association import AssociationTextType
from larpmanager.models.casting import AssignmentTrait, Casting, Trait
from larpmanager.models.form import QuestionApplicable
from larpmanager.models.miscellanea import Util
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import (
    Character,
    Faction,
    Handout,
)
from larpmanager.utils.core.base import get_event_context
from larpmanager.utils.core.common import get_element, get_handout, get_now
from larpmanager.utils.core.exceptions import NotFoundError
from larpmanager.utils.larpmanager.tasks import background_auto
from larpmanager.utils.services.character import get_char_check, get_character_relationships, get_character_sheet

if TYPE_CHECKING:
    from larpmanager.models.event import Event, Run
    from larpmanager.models.member import Member

logger = logging.getLogger(__name__)


def fix_filename(filename: Any) -> Any:
    """Remove special characters from filename for safe PDF generation.

    Args:
        filename (str): Original filename string

    Returns:
        str: Sanitized filename with only alphanumeric characters and spaces

    """
    return re.sub(r"[^A-Za-z0-9 ]+", "", filename)


# reprint if file not exists, older than 1 day, or debug
def reprint(file_path: Any) -> Any:
    """Determine if PDF file should be regenerated.

    Args:
        file_path (str): File path to check

    Returns:
        bool: True if file should be regenerated (debug mode, missing, or older than 1 day)

    """
    if conf_settings.DEBUG:
        return True

    path_obj = Path(file_path)
    if not path_obj.is_file():
        return True

    # Use timezone-aware datetimes for comparison to avoid naive/aware mismatch
    cutoff_date = get_now() - timedelta(days=1)
    modification_time = datetime.fromtimestamp(path_obj.stat().st_mtime, tz=UTC)
    return modification_time < cutoff_date


def return_pdf(file_path: Any, filename: Any) -> Any:
    """Return PDF file as HTTP response.

    Args:
        file_path (str): File path to PDF file
        filename (str): Filename for download

    Returns:
        HttpResponse: PDF file response with appropriate headers

    Raises:
        Http404: If PDF file is not found

    """
    try:
        with Path(file_path).open("rb") as pdf_file:
            response = HttpResponse(pdf_file.read(), content_type="application/pdf")
        response["Content-Disposition"] = f"inline;filename={fix_filename(filename)}.pdf"
    except FileNotFoundError as err:
        msg = "File not found"
        raise Http404(msg) from err
    else:
        return response


def link_callback(uri: str, rel: str) -> str:  # noqa: ARG001
    """Convert HTML URIs to absolute system paths for xhtml2pdf.

    Resolves static and media URLs to absolute file paths so the PDF
    generator can access resources like images and stylesheets.

    Args:
        uri: URI from HTML content (e.g., '/static/css/style.css')
        rel: Relative URI reference (currently unused)

    Returns:
        Absolute file path if file exists, empty string otherwise

    Example:
        >>> link_callback('/static/css/style.css', '')
        '/path/to/static/css/style.css'

    """
    # Get Django settings for URL and filesystem paths
    s_url = conf_settings.STATIC_URL
    s_root = conf_settings.STATIC_ROOT
    m_url = conf_settings.MEDIA_URL
    m_root = conf_settings.MEDIA_ROOT

    # Check if URI is a media URL and build corresponding file path
    if uri.startswith(m_url):
        path = str(Path(m_root) / uri.replace(m_url, ""))
    # Check if URI is a static URL and build corresponding file path
    elif uri.startswith(s_url):
        path = str(Path(s_root) / uri.replace(s_url, ""))
    # Return empty string for unrecognized URI patterns
    else:
        return ""

    # Verify the file actually exists on the filesystem
    if not Path(path).is_file():
        return ""

    return path


def add_pdf_instructions(context: dict) -> None:
    """Add PDF generation instructions to template context.

    Processes template variables and utility codes for PDF headers,
    footers, and CSS styling. Updates the context dictionary in-place
    with processed PDF styling and content instructions.

    Args:
        context: Template context dictionary containing event and character data.
             Must include 'event' and 'sheet_char' keys.

    Returns:
        None: Modifies the context dictionary in-place.

    Side Effects:
        - Updates context with 'page_css', 'header_content', 'footer_content' keys
        - Replaces template variables with actual values
        - Replaces utility codes with URLs

    """
    # Extract PDF configuration from event settings
    for instruction_key in ["page_css", "header_content", "footer_content"]:
        context[instruction_key] = get_event_config(
            context["event"].id,
            instruction_key,
            default_value="",
            context=context,
            bypass_cache=True,
        )

    # Build replacement codes dictionary with event and character data
    replacement_codes = {
        "<pdf:organization>": context["event"].association.name,
        "<pdf:event>": context["event"].name,
    }

    # Add character-specific replacement codes
    for character_field in ["number", "name", "title"]:
        replacement_codes[f"<pdf:{character_field}>"] = str(context["sheet_char"][character_field])

    # Replace character info placeholders in header and footer content
    for section_key in ["header_content", "footer_content"]:
        if section_key not in context:
            continue
        # Apply all code replacements to current section
        for placeholder, value in replacement_codes.items():
            if placeholder not in context[section_key]:
                continue
            context[section_key] = context[section_key].replace(placeholder, value)

    # Replace utility codes with actual URLs in all PDF sections
    for section_key in ["header_content", "footer_content", "page_css"]:
        if section_key not in context:
            continue
        # Find all utility codes in format #code# and replace with URLs
        for utility_code_match in re.findall(r"(#[\w-]+#)", context[section_key]):
            utility_code = utility_code_match.replace("#", "")
            util = get_object_or_404(Util, cod=utility_code)
            context[section_key] = context[section_key].replace(utility_code_match, util.util.url)
        logger.debug("Processed PDF context for key '%s': %s characters", section_key, len(context[section_key]))


def xhtml_pdf(context: dict, template_path: str, output_filename: str, *, html: bool = False) -> None:
    """Generate PDF from Django template using xhtml2pdf library.

    This function renders a Django template (or raw HTML string) with the provided
    context and converts it to a PDF file using xhtml2pdf (pisa). It supports both
    template file paths and raw HTML strings as input.

    The generated PDF uses the link_callback for resolving static/media URLs to
    absolute filesystem paths for proper resource embedding.

    Args:
        context: Template context dictionary containing variables for rendering
        template_path: Either a Django template file path (e.g., 'pdf/sheets/character.html')
            or a raw HTML string, depending on the 'html' parameter
        output_filename: Absolute filesystem path where the PDF file will be saved
        html: If True, treat template_path as raw HTML string to render with context;
            if False, treat as Django template path to load. Defaults to False.

    Raises:
        Http404: If PDF generation encounters errors (includes rendered HTML in error)

    Side Effects:
        Creates a PDF file at the specified output_filename path

    """
    # Render HTML content based on input type
    if html:
        # Treat template_path as raw HTML string and render with Django context
        template = Template(template_path)
        django_context = Context(context)
        html_content = template.render(django_context)
    else:
        # Treat template_path as Django template path and load template file
        template = get_template(template_path)
        html_content = template.render(context)

    # Generate PDF file from rendered HTML
    with Path(output_filename).open("wb") as pdf_file:
        # Convert HTML to PDF using xhtml2pdf library
        pdf_result = pisa.CreatePDF(html_content, dest=pdf_file, link_callback=link_callback)

        # Check for PDF generation errors and raise with diagnostic information
        if pdf_result.err:
            msg = "We had some errors <pre>" + html_content + "</pre>"
            raise Http404(msg)


def get_membership_request(context: dict, member: Member) -> HttpResponse:
    """Generate and return a PDF membership registration document."""
    # Get the file path for the member's request document
    file_path = member.get_request_filepath()

    # Prepare template context with member data
    template_context = {"member": member}

    # Retrieve association-specific membership template text
    template = get_association_text(context["association_id"], AssociationTextType.MEMBERSHIP)

    # Generate PDF from template and return as HTTP response
    xhtml_pdf(template_context, template, file_path, html=True)
    return return_pdf(file_path, _("Membership registration of %(user)s") % {"user": member})


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
        get_character_sheet(context)
        add_pdf_instructions(context)
        xhtml_pdf(context, "pdf/sheets/auxiliary.html", file_path)

    # Return the PDF response
    return return_pdf(file_path, f"{context['character']}")


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
        get_character_sheet(context)
        xhtml_pdf(context, "pdf/sheets/friendly.html", file_path)

    # Return the PDF file as HTTP response
    return return_pdf(file_path, f"{context['character']} - " + _("Lightweight"))


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
    return return_pdf(file_path, f"{context['faction']}")


def print_character_rel(context: dict, *, force: bool = False) -> HttpResponse:
    """Generate and return character relationships PDF.

    Args:
        context: Context dictionary containing character and run data
        force: Whether to force regeneration of the PDF

    Returns:
        HTTP response with the relationships PDF

    """
    # Get the filepath for the character relationships PDF
    filepath = context["character"].get_relationships_filepath(context["run"])

    # Generate PDF if forced or if reprint is needed
    if force or reprint(filepath):
        get_event_cache_all(context)
        get_character_relationships(context)
        xhtml_pdf(context, "pdf/sheets/relationships.html", filepath)

    # Return the PDF response with localized filename
    return return_pdf(filepath, f"{context['character']} - " + _("Relationships"))


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
    filepath = context["run"].get_gallery_filepath()

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
        filepath = context["run"].get_gallery_filepath()

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
    filepath = context["run"].get_profiles_filepath()

    # Check if we need to regenerate the PDF
    if force or reprint(filepath):
        # Load all event cache data
        get_event_cache_all(context)
        # Generate PDF from HTML template
        xhtml_pdf(context, "pdf/sheets/profiles.html", filepath)

    # Return the PDF file with appropriate filename
    return return_pdf(filepath, str(context["run"]) + " - " + _("Profiles"))


def print_handout(context: dict, *, force: bool = True) -> Any:
    """Generate and return a PDF handout for the given context.

    Args:
        context: Context dictionary containing handout and run information
        force: Whether to force regeneration of the PDF

    Returns:
        PDF response for the handout

    """
    # Get the file path for the handout PDF
    file_path = context["handout"].get_filepath(context["run"])

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


# ## HANDLE - DELETE FILES WHEN UPDATED


def cleanup_handout_pdfs_before_delete(handout: Any) -> None:
    """Handle handout pre-delete PDF cleanup.

    Args:
        handout: Handout instance being deleted

    """
    for event_run in handout.event.runs.all():
        safe_remove(handout.get_filepath(event_run))


def cleanup_handout_pdfs_after_save(instance: object) -> None:
    """Handle handout post-save PDF cleanup.

    Args:
        instance: Handout instance that was saved

    """
    for run in instance.event.runs.all():
        safe_remove(instance.get_filepath(run))


def cleanup_handout_template_pdfs_before_delete(handout_template: Any) -> None:
    """Handle handout template pre-delete PDF cleanup.

    Args:
        handout_template: HandoutTemplate instance being deleted

    """
    for event_run in handout_template.event.runs.all():
        safe_remove(handout_template.get_filepath(event_run))


def cleanup_handout_template_pdfs_after_save(instance: object) -> None:
    """Handle handout template post-save PDF cleanup.

    Args:
        instance: HandoutTemplate instance that was saved

    """
    for run in instance.event.runs.all():
        for el in instance.handouts.all():
            safe_remove(el.get_filepath(run))


def safe_remove(file_path: str) -> None:
    """Remove a file, ignoring if it doesn't exist."""
    with contextlib.suppress(FileNotFoundError):
        Path(file_path).unlink()


def remove_run_pdf(event: Event) -> None:
    """Remove PDF files for all runs associated with the event."""
    for event_run in event.runs.all():
        # Remove profiles and gallery PDFs for each run
        safe_remove(event_run.get_profiles_filepath())
        safe_remove(event_run.get_gallery_filepath())


def delete_character_pdf_files(instance: object, single: Any = None, runs: Any = None) -> None:
    """Delete PDF files for a character across specified runs.

    Args:
        instance: Character instance whose PDF files should be deleted
        single: Optional specific run to delete files for
        runs: Optional queryset of runs, defaults to all event runs

    """
    # Default to all runs if none specified
    if not runs:
        runs = instance.event.runs.all()

    # Delete PDF files for each run
    for run in runs:
        if single and run != single:
            continue
        safe_remove(instance.get_sheet_filepath(run))
        safe_remove(instance.get_sheet_friendly_filepath(run))
        safe_remove(instance.get_relationships_filepath(run))


def cleanup_character_pdfs_before_delete(character: Any) -> None:
    """Handle character pre-delete PDF cleanup.

    Args:
        character: Character instance being deleted

    """
    remove_run_pdf(character.event)
    delete_character_pdf_files(character)


def cleanup_character_pdfs_on_save(instance: object) -> None:
    """Handle character post-save PDF cleanup.

    Args:
        instance: Character instance that was saved

    """
    remove_run_pdf(instance.event)
    delete_character_pdf_files(instance)


def cleanup_relationship_pdfs_before_delete(instance: object) -> None:
    """Handle player relationship pre-delete PDF cleanup.

    Args:
        instance: PlayerRelationship instance being deleted

    """
    for relationship_character_run in instance.reg.rcrs.all():
        delete_character_pdf_files(relationship_character_run.character, instance.reg.run)


def cleanup_relationship_pdfs_after_save(instance: object) -> None:
    """Handle player relationship post-save PDF cleanup.

    Args:
        instance: PlayerRelationship instance that was saved

    """
    for el in instance.reg.rcrs.all():
        delete_character_pdf_files(el.character, instance.reg.run)


def cleanup_faction_pdfs_before_delete(instance: object) -> None:
    """Handle faction pre-delete PDF cleanup.

    Args:
        instance: Faction instance being deleted

    """
    for character in instance.event.character_set.all():
        delete_character_pdf_files(character)


def cleanup_faction_pdfs_on_save(instance: object) -> None:
    """Handle faction post-save PDF cleanup.

    Args:
        instance: Faction instance that was saved

    """
    runs = instance.event.runs.all()
    for char in instance.characters.all():
        delete_character_pdf_files(char, runs=runs)


def deactivate_castings_and_remove_pdfs(trait_instance: Any) -> None:
    """Deactivate castings and remove PDF files for a trait instance."""
    # Deactivate all matching castings for this member, run, and type
    for casting in Casting.objects.filter(member=trait_instance.member, run=trait_instance.run, typ=trait_instance.typ):
        casting.active = False
        casting.save()

    # Get character associated with this trait and remove PDF files
    character = get_trait_character(trait_instance.run, trait_instance.trait.number)
    if character:
        delete_character_pdf_files(character, trait_instance.run)


def cleanup_pdfs_on_trait_assignment(assignment_trait_instance: Any) -> None:
    """Handle assignment trait post-save PDF cleanup."""
    if not assignment_trait_instance.member:
        return

    deactivate_castings_and_remove_pdfs(assignment_trait_instance)


# ## TASKS


def print_handout_go(context: dict, handout_id: int) -> HttpResponse:
    """Retrieve handout and generate printable version."""
    get_handout(context, handout_id)
    return print_handout(context)


def get_fake_request(association_slug: str) -> HttpRequest:
    """Create a fake HTTP request with association and anonymous user.

    Args:
        association_slug: The association slug to attach to the request.

    Returns:
        HttpRequest object with association and user attributes set.

    """
    request = HttpRequest()
    # Attach association from cache
    request.association = get_cache_association(association_slug)
    # Set anonymous user for the request
    request.user = AnonymousUser()
    return request


@background_auto(queue="pdf")
def print_handout_bkg(association_slug: str, event_slug: str, handout_id: int) -> None:
    """Print handout by creating a fake request and delegating to print_handout_go."""
    request = get_fake_request(association_slug)
    context = get_event_context(request, event_slug)
    print_handout_go(context, handout_id)


def print_character_go(context: dict, character_uuid: str) -> None:
    """Print character information, handling missing character gracefully."""
    try:
        # Validate character access and retrieve character data
        get_char_check(None, context, character_uuid, bypass_access_checks=True)

        # Generate and cache character print outputs
        print_character(context, force=True)
        print_character_friendly(context, force=True)
        print_character_rel(context, force=True)
    except Http404:
        pass
    except NotFoundError:
        pass


@background_auto(queue="pdf")
def print_character_bkg(association_slug: str, event_slug: str, character_uuid: str) -> None:
    """Print character background for a given association, event slug, and character."""
    request = get_fake_request(association_slug)
    context = get_event_context(request, event_slug)
    print_character_go(context, character_uuid)


@background_auto(queue="pdf")
def print_run_bkg(association_slug: str, event_slug: str) -> None:
    """Print all background materials for a run including gallery, profiles, characters, and handouts.

    Args:
        association_slug: The association object containing event data
        event_slug: String identifier for the specific run

    Returns:
        None

    """
    # Create fake request context and get event run data
    request = get_fake_request(association_slug)
    context = get_event_context(request, event_slug)

    # Print gallery and character profiles
    print_gallery(context)
    print_profiles(context)

    # Print individual character sheets for all characters in the event
    for character_number in context["run"].event.get_elements(Character).values_list("number", flat=True):
        print_character_go(context, character_number)

    # Print all handouts associated with the event
    for handout_number in context["run"].event.get_elements(Handout).values_list("number", flat=True):
        print_handout_go(context, handout_number)


def clean_tag(tag: Any) -> Any:
    """Clean XML tag by removing namespace prefix.

    Args:
        tag: XML tag string to clean

    Returns:
        str: Cleaned tag without namespace prefix

    """
    closing_brace_index = tag.find("}")
    if closing_brace_index >= 0:
        tag = tag[closing_brace_index + 1 :]
    return tag


def replace_data(template_path: Any, character_data: Any) -> None:
    """Replace character data placeholders in template file.

    Args:
        template_path: Path to template file
        character_data: Character data dictionary with replacement values

    """
    with Path(template_path).open() as template_file:
        file_content = template_file.read()

    for placeholder_key in ["number", "name", "title"]:
        if placeholder_key not in character_data:
            continue
        file_content = file_content.replace(f"#{placeholder_key}#", str(character_data[placeholder_key]))

    # Write the file out again
    with Path(template_path).open("w") as template_file:
        template_file.write(file_content)


def get_trait_character(run: Run, number: int) -> Character | None:
    """Get the character assigned to a trait number in a specific run.

    Args:
        run: The Run instance to search in.
        number: The trait number to look for.

    Returns:
        The Character assigned to the trait, or None if not found.

    """
    try:
        # Find the trait by event and number
        trait = Trait.objects.get(event_id=run.event_id, number=number)

        # Get the member assigned to this trait in the run
        member = AssignmentTrait.objects.get(run=run, trait=trait).member

        # Find the character registered for this member in the run
        registration_character_rels = RegistrationCharacterRel.objects.filter(
            reg__run=run,
            reg__member=member,
        ).select_related("character")

        if not registration_character_rels.exists():
            return None
        return registration_character_rels.first().character
    except ObjectDoesNotExist:
        return None


def print_bulk(context: dict, request: HttpRequest) -> HttpResponse:
    """Generate and return a ZIP file containing multiple PDFs based on user selection.

    This function creates an in-memory ZIP archive containing selected PDF files for
    an event run. Users can select from gallery, profiles, character sheets, faction
    sheets, and handouts via POST parameters. Each selected item is generated (if needed)
    and added to the ZIP file.

    The function delegates to specialized helper functions for each PDF type, each of
    which handles generation, caching, and error reporting independently.

    Args:
        context: Context dictionary containing:
            - 'run': The Run model instance
            - 'event': The Event model instance
            - Other data required by individual PDF generators
        request: HTTP request object with POST data indicating which PDFs to include.
            Expected POST parameters: 'gallery', 'profiles', 'character_{id}',
            'faction_{id}', 'handout_{id}'

    Returns:
        HttpResponse: ZIP file download response with timestamped filename in format:
            {run_slug}_pdfs_{YYYYMMDD_HHMMSS}.zip

    Side Effects:
        - Generates PDF files in the media directory as needed
        - Displays warning messages to user for any failed PDF generations

    """
    # Create in-memory zip file buffer for PDF collection
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # Process each PDF type via specialized helper functions
        _bulk_gallery(context, request, zip_file)
        _bulk_profiles(context, request, zip_file)
        _bulk_characters(context, request, zip_file)
        _bulk_factions(context, request, zip_file)
        _handle_handouts(context, request, zip_file)

    # Prepare ZIP file for download
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")

    # Generate timestamped filename for download
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    response["Content-Disposition"] = f'attachment; filename="{context["run"].get_slug()}_pdfs_{timestamp}.zip"'

    return response


def _handle_handouts(context: dict, request: HttpRequest, zip_file: zipfile.ZipFile) -> None:
    """Process and add handout PDFs to bulk ZIP file based on user selection.

    Iterates through all handouts for the event, generating PDFs for those selected
    in the POST request, and adding them to the ZIP archive with descriptive filenames.

    Args:
        context: Context dictionary with 'event' and 'run' data
        request: HTTP request with POST parameters like 'handout_{id}'
        zip_file: Open ZipFile object to write PDFs into

    Side Effects:
        - Generates handout PDF files if needed
        - Adds PDFs to zip_file
        - Displays warning messages for failed generations

    """
    # Iterate through all handouts in the event
    for handout in context["event"].get_elements(Handout):
        # Check if this handout was selected by user
        if request.POST.get(f"handout_{handout.id}"):
            try:
                # Load handout data into context
                get_handout(context, handout.number)
                filepath = context["handout"].get_filepath(context["run"])

                # Generate PDF if it doesn't exist or is outdated
                if not Path(filepath).exists() or reprint(filepath):
                    print_handout(context, force=True)

                # Add to ZIP if generation succeeded
                if Path(filepath).exists():
                    zip_file.write(filepath, f"handout_{handout.number}_{handout.name}.pdf")
            except Exception as e:  # noqa: BLE001 - Batch operation must continue on any error (Http404, NotFoundError, OSError, etc.)
                # Notify user of failure but continue processing other handouts
                messages.warning(request, _("Failed to add handout") + f" #{handout.number}: {e}")


def _bulk_factions(context: dict, request: HttpRequest, zip_file: zipfile.ZipFile) -> None:
    """Process and add faction sheet PDFs to bulk ZIP file based on user selection.

    Iterates through all factions for the event, generating faction sheets for those
    selected in the POST request, and adding them to the ZIP archive.

    Args:
        context: Context dictionary with 'event', 'run', and cache data
        request: HTTP request with POST parameters like 'faction_{id}'
        zip_file: Open ZipFile object to write PDFs into

    Side Effects:
        - Loads event cache and faction field data into context
        - Generates faction PDF files if needed
        - Adds PDFs to zip_file
        - Displays warning messages for failed generations

    """
    # Iterate through all factions in the event
    for faction in context["event"].get_elements(Faction):
        # Check if this faction was selected by user
        if request.POST.get(f"faction_{faction.id}"):
            try:
                # Load faction data into context
                get_element(context, faction.number, "faction", Faction)
                get_event_cache_all(context)

                # Verify faction exists in cache
                if faction.number in context["factions"]:
                    context["sheet_faction"] = context["factions"][faction.number]
                else:
                    # Skip if faction not found in cache
                    continue

                # Load custom faction fields for the sheet
                context["fact"] = get_writing_element_fields(
                    context,
                    "faction",
                    QuestionApplicable.FACTION,
                    context["sheet_faction"]["id"],
                    only_visible=True,
                )

                filepath = context["faction"].get_sheet_filepath(context["run"])

                # Generate PDF if it doesn't exist or is outdated
                if not Path(filepath).exists() or reprint(filepath):
                    print_faction(context, force=True)

                # Add to ZIP if generation succeeded
                if Path(filepath).exists():
                    zip_file.write(filepath, f"faction_{faction.number}_{faction.name}.pdf")
            except Exception as e:  # noqa: BLE001 - Batch operation must continue on any error (Http404, NotFoundError, OSError, etc.)
                # Notify user of failure but continue processing other factions
                messages.warning(request, _("Failed to add faction") + f" #{faction.number}: {e}")


def _bulk_characters(context: dict, request: HttpRequest, zip_file: zipfile.ZipFile) -> None:
    """Process and add character sheet PDFs to bulk ZIP file based on user selection.

    Iterates through all characters for the event, generating character sheets for
    those selected in the POST request, and adding them to the ZIP archive.

    Args:
        context: Context dictionary with 'event' and 'run' data
        request: HTTP request with POST parameters like 'character_{id}'
        zip_file: Open ZipFile object to write PDFs into

    Side Effects:
        - Loads character data into context
        - Generates character PDF files if needed
        - Adds PDFs to zip_file
        - Displays warning messages for failed generations

    """
    # Iterate through all characters in the event
    for character in context["event"].get_elements(Character):
        # Check if this character was selected by user
        if request.POST.get(f"character_{character.id}"):
            try:
                # Load and validate character data
                get_char_check(request, context, character.uuid, restrict_non_owners=True)
                filepath = context["character"].get_sheet_filepath(context["run"])

                # Generate PDF if it doesn't exist or is outdated
                if not Path(filepath).exists() or reprint(filepath):
                    print_character(context, force=True)

                # Add to ZIP if generation succeeded
                if Path(filepath).exists():
                    zip_file.write(filepath, f"character_{character.number}_{character.name}.pdf")
            except Exception as e:  # noqa: BLE001 - Batch operation must continue on any error (Http404, NotFoundError, OSError, etc.)
                # Notify user of failure but continue processing other characters
                messages.warning(request, _("Failed to add character") + f" #{character.number}: {e}")


def _bulk_profiles(context: dict, request: HttpRequest, zip_file: zipfile.ZipFile) -> None:
    """Add profiles PDF to bulk ZIP file if selected by user.

    Generates a profiles PDF containing information for all characters in the run
    if the 'profiles' POST parameter is present.

    Args:
        context: Context dictionary with 'run' data
        request: HTTP request with 'profiles' POST parameter
        zip_file: Open ZipFile object to write PDF into

    Side Effects:
        - Generates profiles PDF file if needed
        - Adds PDF to zip_file
        - Displays warning message if generation fails

    """
    # Check if profiles PDF was requested
    if request.POST.get("profiles"):
        try:
            filepath = context["run"].get_profiles_filepath()

            # Generate PDF if it doesn't exist or is outdated
            if not Path(filepath).exists() or reprint(filepath):
                print_profiles(context, force=True)

            # Add to ZIP if generation succeeded
            if Path(filepath).exists():
                zip_file.write(filepath, "profiles.pdf")
        except Exception as e:  # noqa: BLE001 - Batch operation must continue on any error (Http404, NotFoundError, OSError, etc.)
            # Notify user of failure
            messages.warning(request, _("Failed to add profiles") + f": {e}")


def _bulk_gallery(context: dict, request: HttpRequest, zip_file: zipfile.ZipFile) -> None:
    """Add gallery PDF to bulk ZIP file if selected by user.

    Generates a gallery PDF containing character portraits if the 'gallery'
    POST parameter is present.

    Args:
        context: Context dictionary with 'run' data
        request: HTTP request with 'gallery' POST parameter
        zip_file: Open ZipFile object to write PDF into

    Side Effects:
        - Generates gallery PDF file if needed
        - Adds PDF to zip_file
        - Displays warning message if generation fails

    """
    # Check if gallery PDF was requested
    if request.POST.get("gallery"):
        try:
            filepath = context["run"].get_gallery_filepath()

            # Generate PDF if it doesn't exist or is outdated
            if not Path(filepath).exists() or reprint(filepath):
                print_gallery(context, force=True)

            # Add to ZIP if generation succeeded
            if Path(filepath).exists():
                zip_file.write(filepath, "gallery.pdf")
        except Exception as e:  # noqa: BLE001 - Batch operation must continue on any error (Http404, NotFoundError, OSError, etc.)
            # Notify user of failure
            messages.warning(request, _("Failed to add gallery") + f": {e}")
