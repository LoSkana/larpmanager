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
import io
import logging
import os
import os.path
import re
import shutil
import time
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any

import lxml.etree
from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template import Context, Template
from django.template.loader import get_template
from django.utils.translation import gettext_lazy as _
from xhtml2pdf import pisa

from larpmanager.cache.association import get_cache_association
from larpmanager.cache.character import get_event_cache_all, get_writing_element_fields
from larpmanager.cache.config import get_event_config
from larpmanager.models.association import AssociationTextType
from larpmanager.models.casting import AssignmentTrait, Casting, Trait
from larpmanager.models.form import QuestionApplicable
from larpmanager.models.member import Member
from larpmanager.models.miscellanea import Util
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import (
    Character,
    Faction,
    Handout,
)
from larpmanager.utils.base import get_event_context
from larpmanager.utils.character import get_char_check, get_character_relationships, get_character_sheet
from larpmanager.utils.common import get_element, get_handout
from larpmanager.utils.exceptions import NotFoundError
from larpmanager.utils.tasks import background_auto
from larpmanager.utils.text import get_association_text

logger = logging.getLogger(__name__)


def fix_filename(filename):
    """Remove special characters from filename for safe PDF generation.

    Args:
        filename (str): Original filename string

    Returns:
        str: Sanitized filename with only alphanumeric characters and spaces
    """
    return re.sub(r"[^A-Za-z0-9 ]+", "", filename)


# reprint if file not exists, older than 1 day, or debug
def reprint(file_path):
    """Determine if PDF file should be regenerated.

    Args:
        file_path (str): File path to check

    Returns:
        bool: True if file should be regenerated (debug mode, missing, or older than 1 day)
    """
    if conf_settings.DEBUG:
        return True

    if not os.path.isfile(file_path):
        return True

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=1)
    modification_time = datetime.fromtimestamp(os.path.getmtime(file_path), timezone.utc)
    return modification_time < cutoff_date


def return_pdf(file_path, filename):
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
        pdf_file = open(file_path, "rb")
        response = HttpResponse(pdf_file.read(), content_type="application/pdf")
        pdf_file.close()
        response["Content-Disposition"] = f"inline;filename={fix_filename(filename)}.pdf"
        return response
    except FileNotFoundError as err:
        raise Http404("File not found") from err


def link_callback(uri: str, rel: str) -> str:
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
        path = os.path.join(m_root, uri.replace(m_url, ""))
    # Check if URI is a static URL and build corresponding file path
    elif uri.startswith(s_url):
        path = os.path.join(s_root, uri.replace(s_url, ""))
    # Return empty string for unrecognized URI patterns
    else:
        return ""

    # Verify the file actually exists on the filesystem
    if not os.path.isfile(path):
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
            context["event"].id, instruction_key, "", context, bypass_cache=True
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
        logger.debug(f"Processed PDF context for key '{section_key}': {len(context[section_key])} characters")


def xhtml_pdf(context: dict, template_path: str, output_filename: str, html: bool = False) -> None:
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
    with open(output_filename, "wb") as pdf_file:
        # Convert HTML to PDF using xhtml2pdf library
        pdf_result = pisa.CreatePDF(html_content, dest=pdf_file, link_callback=link_callback)

        # Check for PDF generation errors and raise with diagnostic information
        if pdf_result.err:
            raise Http404("We had some errors <pre>" + html_content + "</pre>")


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


def print_character(context: dict, force: bool = False) -> HttpResponse:
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


def print_character_friendly(context: dict, force: bool = False) -> HttpResponse:
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


def print_faction(context: dict, force: bool = False) -> HttpResponse:
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


def print_character_rel(context: dict, force: bool = False) -> HttpResponse:
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


def print_gallery(context: dict, force: bool = False) -> object:
    """
    Generate and return a PDF gallery of character portraits.

    Creates a PDF containing character portraits for characters with first aid
    capabilities. The PDF is cached and only regenerated when forced or when
    the cache is outdated.

    Parameters
    ----------
    context : dict
        Context dictionary containing run information and character data
    force : bool, default False
        Whether to force regeneration of the PDF even if cache is valid

    Returns
    -------
    object
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
        for _character_number, character_element in context["chars"].items():
            if "first_aid" in character_element and character_element["first_aid"] == "y":
                context["first_aid"].append(character_element)

        # Re-get filepath (in case it changed during cache loading)
        filepath = context["run"].get_gallery_filepath()

        # Generate the PDF from the gallery template
        xhtml_pdf(context, "pdf/sheets/gallery.html", filepath)

    # Return the PDF file as a downloadable response
    return return_pdf(filepath, str(context["run"]) + " - " + _("Portraits"))


def print_profiles(context: dict, force: bool = False) -> HttpResponse:
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


def print_handout(context: dict, force: bool = True) -> Any:
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
    fp = os.path.join(conf_settings.MEDIA_ROOT, f"volunteer_registry/{context['association'].slug}.pdf")

    # Generate PDF from template
    xhtml_pdf(context, "pdf/volunteer_registry.html", fp)

    return fp


# ## HANDLE - DELETE FILES WHEN UPDATED


def cleanup_handout_pdfs_before_delete(handout):
    """Handle handout pre-delete PDF cleanup.

    Args:
        handout: Handout instance being deleted
    """
    for event_run in handout.event.runs.all():
        safe_remove(handout.get_filepath(event_run))


def cleanup_handout_pdfs_after_save(instance):
    """Handle handout post-save PDF cleanup.

    Args:
        instance: Handout instance that was saved
    """
    for run in instance.event.runs.all():
        safe_remove(instance.get_filepath(run))


def cleanup_handout_template_pdfs_before_delete(handout_template):
    """Handle handout template pre-delete PDF cleanup.

    Args:
        handout_template: HandoutTemplate instance being deleted
    """
    for event_run in handout_template.event.runs.all():
        safe_remove(handout_template.get_filepath(event_run))


def cleanup_handout_template_pdfs_after_save(instance):
    """Handle handout template post-save PDF cleanup.

    Args:
        instance: HandoutTemplate instance that was saved
    """
    for run in instance.event.runs.all():
        for el in instance.handouts.all():
            safe_remove(el.get_filepath(run))


def safe_remove(file_path):
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass


def remove_run_pdf(event):
    for event_run in event.runs.all():
        safe_remove(event_run.get_profiles_filepath())
        safe_remove(event_run.get_gallery_filepath())


def delete_character_pdf_files(instance, single=None, runs=None) -> None:
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


def cleanup_character_pdfs_before_delete(character):
    """Handle character pre-delete PDF cleanup.

    Args:
        character: Character instance being deleted
    """
    remove_run_pdf(character.event)
    delete_character_pdf_files(character)


def cleanup_character_pdfs_on_save(instance):
    """Handle character post-save PDF cleanup.

    Args:
        instance: Character instance that was saved
    """
    remove_run_pdf(instance.event)
    delete_character_pdf_files(instance)


def cleanup_relationship_pdfs_before_delete(instance):
    """Handle player relationship pre-delete PDF cleanup.

    Args:
        instance: PlayerRelationship instance being deleted
    """
    for relationship_character_run in instance.reg.rcrs.all():
        delete_character_pdf_files(relationship_character_run.character, instance.reg.run)


def cleanup_relationship_pdfs_after_save(instance):
    """Handle player relationship post-save PDF cleanup.

    Args:
        instance: PlayerRelationship instance that was saved
    """
    for el in instance.reg.rcrs.all():
        delete_character_pdf_files(el.character, instance.reg.run)


def cleanup_faction_pdfs_before_delete(instance):
    """Handle faction pre-delete PDF cleanup.

    Args:
        instance: Faction instance being deleted
    """
    for character in instance.event.character_set.all():
        delete_character_pdf_files(character)


def cleanup_faction_pdfs_on_save(instance):
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


def cleanup_pdfs_on_trait_assignment(assignment_trait_instance, is_newly_created):
    """Handle assignment trait post-save PDF cleanup.

    Args:
        assignment_trait_instance: AssignmentTrait instance that was saved
        is_newly_created: Boolean indicating if instance was created
    """
    if not assignment_trait_instance.member or not is_newly_created:
        return

    deactivate_castings_and_remove_pdfs(assignment_trait_instance)


# ## TASKS


def print_handout_go(context: dict, character: Character) -> HttpResponse:
    """Retrieve character handout and generate printable version."""
    get_handout(context, character)
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
def print_handout_bkg(association_slug: str, event_slug: str, c: Character) -> None:
    """Prints character handout by creating a fake request and delegating to print_handout_go."""
    request = get_fake_request(association_slug)
    context = get_event_context(request, event_slug)
    print_handout_go(context, c)


def print_character_go(context, character):
    try:
        get_char_check(None, context, character, False, True)
        print_character(context, True)
        print_character_friendly(context, True)
        print_character_rel(context, True)
    except Http404:
        pass
    except NotFoundError:
        pass


@background_auto(queue="pdf")
def print_character_bkg(association_slug: str, event_slug: str, c: Character) -> None:
    """Print character background for a given association, event slug, and character."""
    request = get_fake_request(association_slug)
    context = get_event_context(request, event_slug)
    print_character_go(context, c)


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
    for ch in context["run"].event.get_elements(Character).values_list("number", flat=True):
        print_character_go(context, ch)

    # Print all handouts associated with the event
    for h in context["run"].event.get_elements(Handout).values_list("number", flat=True):
        print_handout_go(context, h)


# ## OLD PRINTING


def odt_template(context: dict, char: dict, fp: str, template: str, aux_template: str) -> None:
    """Execute ODT template generation with retry mechanism.

    Attempts to execute ODT template generation with automatic retry
    on failure. Logs errors and implements exponential backoff.

    Args:
        context: Context dictionary for template rendering
        char: Character dict data for template processing
        fp: File path for output generation
        template: Primary template identifier
        aux_template: Auxiliary template identifier

    Returns:
        None

    Raises:
        Exception: After maximum retry attempts are exhausted
    """
    attempt = 0
    excepts = []
    max_attempts = 5

    # Retry loop with maximum attempt limit
    while attempt < max_attempts:
        try:
            # Execute the main ODT template processing
            exec_odt_template(context, char, fp, template, aux_template)
            return
        except Exception as e:
            # Log detailed error information for debugging
            logger.error(f"Error in PDF creation: {e}")
            logger.error(f"Character: {char}")
            logger.error(f"Template: {template}")

            # Increment attempt counter and store exception
            attempt += 1
            excepts.append(e)

            # Wait before retry to allow transient issues to resolve
            time.sleep(2)

    # Log final error after all attempts exhausted
    logger.error(f"ERROR IN odt_template: {excepts}")


def exec_odt_template(
    context: dict, character: dict, output_file_path: str, template: object, aux_template: object
) -> None:
    """Process ODT template to generate PDF for character data.

    Args:
        context: Context dictionary containing template rendering data
        character: Character data dictionary with character information
        output_file_path: Output file path where the generated PDF will be saved
        template: ODT template file object with path attribute
        aux_template: Auxiliary template object for content processing

    Returns:
        None: Function writes PDF file to specified path
    """
    # Set up working directory based on character number
    working_dir = os.path.dirname(output_file_path)
    working_dir = os.path.join(working_dir, str(character["number"]))
    logger.debug(f"Character PDF working directory: {working_dir}")

    # Clean up existing output file if present
    if os.path.exists(output_file_path):
        os.remove(output_file_path)

    # Set up temporary working directory for processing
    working_dir += "-work"
    if os.path.exists(working_dir):
        logger.debug(f"Cleaning up existing character directory: {working_dir}")
        shutil.rmtree(working_dir)
    os.makedirs(working_dir)

    # Create subdirectory for unzipped template content
    unzipped_template_dir = os.path.join(working_dir, "zipdd")
    os.makedirs(unzipped_template_dir)

    # Extract ODT template to working directory
    os.chdir(unzipped_template_dir)
    os.system(f"unzip -q {template.path}")

    # Process template content with character data
    update_content(context, working_dir, unzipped_template_dir, character, aux_template)

    # Repackage modified content back into ODT format
    os.chdir(unzipped_template_dir)
    os.system("zip -q -r ../out.odt *")

    # Convert ODT to PDF using unoconv
    os.chdir(working_dir)
    os.system("/usr/bin/unoconv -f pdf out.odt")

    # Move generated PDF to final destination
    os.rename("out.pdf", output_file_path)
    # ## TODO shutil.rmtree(working_dir)
    # if os.path.exists(working_dir):
    # shutil.rmtree(working_dir)


# translate html markup to odt
def get_odt_content(context: dict, working_dir: str, aux_template) -> dict:
    """
    Extract ODT content from HTML template for PDF generation.

    Converts an HTML template to ODT format using LibreOffice, then extracts
    and parses the XML content to retrieve text, automatic styles, and document
    styles for further processing.

    Args:
        context: Template context dictionary containing variables for rendering
        working_dir: Working directory path for temporary file operations
        aux_template: Django template object to be rendered and converted

    Returns:
        Dictionary containing extracted ODT elements:
            - txt: List of text elements from content.xml
            - auto: List of automatic style elements from content.xml
            - styles: List of style elements from styles.xml

    Raises:
        ValueError: If required XML elements are not found in the ODT files
    """
    # Render the Django template with provided context
    html = aux_template.render(context)

    # Write rendered HTML to temporary file for LibreOffice conversion
    o_html = os.path.join(working_dir, "auxiliary.html")
    f = open(o_html, "w")
    f.write(html)
    f.close()

    # Convert HTML to ODT format using LibreOffice headless mode
    os.chdir(working_dir)
    os.system("soffice --headless --convert-to odt auxiliary.html")

    # Prepare extraction directory and clean up any existing content
    aux_dir = os.path.join(working_dir, "aux")
    if os.path.exists(aux_dir):
        shutil.rmtree(aux_dir)
    os.makedirs(aux_dir)

    # Extract ODT file contents (ODT is essentially a ZIP archive)
    os.chdir(aux_dir)
    os.system("unzip -q ../aux.odt")

    # Parse content.xml to extract text and automatic style elements
    doc = lxml.etree.parse("content.xml")
    txt_elements = doc.xpath('//*[local-name()="text"]')
    auto_elements = doc.xpath('//*[local-name()="automatic-styles"]')

    # Validate that required elements exist in content.xml
    if not txt_elements or not auto_elements:
        raise ValueError("Required XML elements not found in content.xml")
    txt = txt_elements[0]
    auto = auto_elements[0]

    # Parse styles.xml to extract document style definitions
    doc = lxml.etree.parse("styles.xml")
    styles_elements = doc.xpath('//*[local-name()="styles"]')

    # Validate that required elements exist in styles.xml
    if not styles_elements:
        raise ValueError("Required XML elements not found in styles.xml")
    styles = styles_elements[0]

    # Return extracted content as dictionary with child elements
    return {
        "txt": txt.getchildren(),
        "auto": auto.getchildren(),
        "styles": styles.getchildren(),
    }


def clean_tag(tag):
    """
    Clean XML tag by removing namespace prefix.

    Args:
        tag: XML tag string to clean

    Returns:
        str: Cleaned tag without namespace prefix
    """
    closing_brace_index = tag.find("}")
    if closing_brace_index >= 0:
        tag = tag[closing_brace_index + 1 :]
    return tag


def replace_data(template_path, character_data):
    """
    Replace character data placeholders in template file.

    Args:
        template_path: Path to template file
        character_data: Character data dictionary with replacement values
    """
    with open(template_path) as template_file:
        file_content = template_file.read()

    for placeholder_key in ["number", "name", "title"]:
        if placeholder_key not in character_data:
            continue
        file_content = file_content.replace(f"#{placeholder_key}#", str(character_data[placeholder_key]))

    # Write the file out again
    with open(template_path, "w") as template_file:
        template_file.write(file_content)


def update_content(context: Any, working_dir: str, zip_dir: str, char: Any, aux_template: str) -> None:
    """Update PDF content for character sheets.

    Modifies LibreOffice document content with character data for PDF
    generation, handling template replacement and content formatting.

    Args:
        context: Context object for processing
        working_dir: Working directory path for temporary files
        zip_dir: Directory containing extracted ODT files
        char: Character object containing data for replacement
        aux_template: Auxiliary template identifier

    Raises:
        ValueError: If required XML elements are not found in document
    """
    # Update content.xml with character data
    content = os.path.join(zip_dir, "content.xml")
    replace_data(content, char)

    # Parse content document and get template elements
    doc = lxml.etree.parse(content)
    elements = get_odt_content(context, working_dir, aux_template)

    # Find and clear automatic styles section
    styles_elements = doc.xpath('//*[local-name()="automatic-styles"]')
    if not styles_elements:
        raise ValueError("automatic-styles element not found in content.xml")

    styles = styles_elements[0]
    # Remove existing child elements from styles
    for ch in styles.getchildren():
        styles.remove(ch)

    # Add new automatic styles, removing master-page-name attributes
    for ch in elements["auto"]:
        master_page = None
        for k in ch.attrib.keys():
            if clean_tag(k) == "master-page-name":
                master_page = k

        # Remove master-page attribute if found
        if master_page is not None:
            del ch.attrib[master_page]
        styles.append(ch)

    # Find and replace content placeholder with actual content
    cnt = doc.xpath('//*[text()="@content@"]')
    if cnt:
        cnt = cnt[0]
        prnt = cnt.getparent()
        prnt.remove(cnt)

        # Append text elements, skipping sequence declarations
        for e in elements["txt"]:
            if clean_tag(e.tag) == "sequence-decls":
                continue
            prnt.append(e)

    # Write updated content back to file
    doc.write(content, pretty_print=True)

    # Update styles.xml with character data
    content = os.path.join(zip_dir, "styles.xml")
    replace_data(content, char)

    # Parse styles document and find styles section
    doc = lxml.etree.parse(content)
    styles_elements = doc.xpath('//*[local-name()="styles"]')
    if not styles_elements:
        raise ValueError("styles element not found in styles.xml")

    styles = styles_elements[0]

    # Add style elements from template
    # Note: Commented code shows previous filtering logic for specific styles
    for ch in elements["styles"]:
        # ~ Skip = false
        # ~ if ch.tag.endswith("default-style"):
        # ~ skip = True
        # ~ for key in ch.attrib:
        # ~ if key.endswith("name") and ch.attrib[key] in ["Footer", "Header", "Title", "Subtitle", "Text_20_body", "Heading_20_1", "Heading_20_2"]:
        # ~ skip = True
        # ~ if skip:
        # ~ continue
        styles.append(ch)

    # Write updated styles back to file
    doc.write(content, pretty_print=True)


def get_trait_character(run, number):
    try:
        trait = Trait.objects.get(event_id=run.event_id, number=number)
        member = AssignmentTrait.objects.get(run=run, trait=trait).member
        registration_character_rels = RegistrationCharacterRel.objects.filter(
            reg__run=run, reg__member=member
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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
                if not os.path.exists(filepath) or reprint(filepath):
                    print_handout(context, True)

                # Add to ZIP if generation succeeded
                if os.path.exists(filepath):
                    zip_file.write(filepath, f"handout_{handout.number}_{handout.name}.pdf")
            except Exception as e:
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
                    context, "faction", QuestionApplicable.FACTION, context["sheet_faction"]["id"], only_visible=True
                )

                filepath = context["faction"].get_sheet_filepath(context["run"])

                # Generate PDF if it doesn't exist or is outdated
                if not os.path.exists(filepath) or reprint(filepath):
                    print_faction(context, True)

                # Add to ZIP if generation succeeded
                if os.path.exists(filepath):
                    zip_file.write(filepath, f"faction_{faction.number}_{faction.name}.pdf")
            except Exception as e:
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
                get_char_check(request, context, character.number, True)
                filepath = context["character"].get_sheet_filepath(context["run"])

                # Generate PDF if it doesn't exist or is outdated
                if not os.path.exists(filepath) or reprint(filepath):
                    print_character(context, True)

                # Add to ZIP if generation succeeded
                if os.path.exists(filepath):
                    zip_file.write(filepath, f"character_{character.number}_{character.name}.pdf")
            except Exception as e:
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
            if not os.path.exists(filepath) or reprint(filepath):
                print_profiles(context, True)

            # Add to ZIP if generation succeeded
            if os.path.exists(filepath):
                zip_file.write(filepath, "profiles.pdf")
        except Exception as e:
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
            if not os.path.exists(filepath) or reprint(filepath):
                print_gallery(context, True)

            # Add to ZIP if generation succeeded
            if os.path.exists(filepath):
                zip_file.write(filepath, "gallery.pdf")
        except Exception as e:
            # Notify user of failure
            messages.warning(request, _("Failed to add gallery") + f": {e}")
