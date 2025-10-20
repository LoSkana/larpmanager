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

import logging
import os.path
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import lxml.etree
import pdfkit
from django.conf import settings as conf_settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template import Context, Template
from django.template.loader import get_template
from django.utils.translation import gettext_lazy as _
from xhtml2pdf import pisa

from larpmanager.cache.association import get_cache_assoc
from larpmanager.cache.character import get_event_cache_all
from larpmanager.cache.config import get_event_config
from larpmanager.models.association import AssocTextType
from larpmanager.models.casting import AssignmentTrait, Casting, Trait
from larpmanager.models.miscellanea import Util
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import (
    Character,
    Handout,
)
from larpmanager.utils.character import get_char_check, get_character_relationships, get_character_sheet
from larpmanager.utils.common import get_handout
from larpmanager.utils.event import get_event_run
from larpmanager.utils.exceptions import NotFoundError
from larpmanager.utils.tasks import background_auto
from larpmanager.utils.text import get_assoc_text

logger = logging.getLogger(__name__)


def fix_filename(s):
    """Remove special characters from filename for safe PDF generation.

    Args:
        s (str): Original filename string

    Returns:
        str: Sanitized filename with only alphanumeric characters and spaces
    """
    return re.sub(r"[^A-Za-z0-9 ]+", "", s)


# reprint if file not exists, older than 1 day, or debug
def reprint(fp):
    """Determine if PDF file should be regenerated.

    Args:
        fp (str): File path to check

    Returns:
        bool: True if file should be regenerated (debug mode, missing, or older than 1 day)
    """
    if conf_settings.DEBUG:
        return True

    if not os.path.isfile(fp):
        return True

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    mtime = datetime.fromtimestamp(os.path.getmtime(fp), timezone.utc)
    return mtime < cutoff


def return_pdf(fp, fn):
    """Return PDF file as HTTP response.

    Args:
        fp (str): File path to PDF file
        fn (str): Filename for download

    Returns:
        HttpResponse: PDF file response with appropriate headers

    Raises:
        Http404: If PDF file is not found
    """
    try:
        f = open(fp, "rb")
        response = HttpResponse(f.read(), content_type="application/pdf")
        f.close()
        response["Content-Disposition"] = f"inline;filename={fix_filename(fn)}.pdf"
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


def add_pdf_instructions(ctx: dict) -> None:
    """Add PDF generation instructions to template context.

    Processes template variables and utility codes for PDF headers,
    footers, and CSS styling. Updates the context dictionary in-place
    with processed PDF styling and content instructions.

    Args:
        ctx: Template context dictionary containing event and character data.
             Must include 'event' and 'sheet_char' keys.

    Returns:
        None: Modifies the context dictionary in-place.

    Side Effects:
        - Updates ctx with 'page_css', 'header_content', 'footer_content' keys
        - Replaces template variables with actual values
        - Replaces utility codes with URLs
    """
    # Extract PDF configuration from event settings
    for instr in ["page_css", "header_content", "footer_content"]:
        ctx[instr] = get_event_config(ctx["event"].id, instr, "", ctx, bypass_cache=True)

    # Build replacement codes dictionary with event and character data
    codes = {
        "<pdf:organization>": ctx["event"].assoc.name,
        "<pdf:event>": ctx["event"].name,
    }

    # Add character-specific replacement codes
    for m in ["number", "name", "title"]:
        codes[f"<pdf:{m}>"] = str(ctx["sheet_char"][m])

    # Replace character info placeholders in header and footer content
    for s in ["header_content", "footer_content"]:
        if s not in ctx:
            continue
        # Apply all code replacements to current section
        for el, value in codes.items():
            if el not in ctx[s]:
                continue
            ctx[s] = ctx[s].replace(el, value)

    # Replace utility codes with actual URLs in all PDF sections
    for s in ["header_content", "footer_content", "page_css"]:
        if s not in ctx:
            continue
        # Find all utility codes in format #code# and replace with URLs
        for x in re.findall(r"(#[\w-]+#)", ctx[s]):
            cod = x.replace("#", "")
            util = get_object_or_404(Util, cod=cod)
            ctx[s] = ctx[s].replace(x, util.util.url)
        logger.debug(f"Processed PDF context for key '{s}': {len(ctx[s])} characters")


def xhtml_pdf(context, template_path, output_filename):
    """Generate PDF from Django template using xhtml2pdf.

    Args:
        context (dict): Template context dictionary
        template_path (str): Path to Django template file
        output_filename (str): Output PDF file path

    Raises:
        Http404: If PDF generation fails with errors
    """
    template = get_template(template_path)

    html = template.render(context)

    with open(output_filename, "wb") as result_file:
        # create a pdf
        result = pisa.CreatePDF(html, dest=result_file, link_callback=link_callback)

        # check result
        if result.err:
            raise Http404("We had some errors <pre>" + html + "</pre>")


def pdf_template(ctx: dict, tmp: str, out: str, small: bool = False, html: bool = False) -> None:
    """Generate PDF from template using pdfkit with configurable options.

    Args:
        ctx: Template context dictionary containing variables for rendering.
        tmp: Template path or HTML string depending on html parameter.
        out: Output PDF file path where the generated PDF will be saved.
        small: Use minimal margins for compact layout. Defaults to False.
        html: If True, treat tmp as HTML string; if False, as template path.
              Defaults to False.

    Raises:
        Exception: PDF generation errors are logged but not re-raised.

    Side Effects:
        Creates PDF file at specified output path.
    """
    # Configure PDF options based on layout preference
    if small:
        # Minimal margins for compact layout
        options = {
            "page-size": "A4",
            "margin-top": "0.1in",
            "margin-right": "0.1in",
            "margin-bottom": "0.1in",
            "margin-left": "0.1in",
            "encoding": "UTF-8",
            "custom-header": [("Accept-Encoding", "gzip")],
            # 'no-outline': None,
            "quiet": "",
        }
    else:
        # Standard margins for normal layout
        options = {
            "page-size": "A4",
            "margin-top": "0.6in",
            "margin-right": "0.6in",
            "margin-bottom": "0.4in",
            "margin-left": "0.4in",
            "encoding": "UTF-8",
            "custom-header": [("Accept-Encoding", "gzip")],
            # 'no-outline': None,
            "quiet": "",
        }

    try:
        # Render HTML content based on input type
        if html:
            # Treat tmp as HTML string and render with context
            t = Template(tmp)
            c = Context(ctx)
            html = t.render(c)
        else:
            # Treat tmp as template path and load template
            template = get_template(tmp)
            html = template.render(ctx)
            logger.debug(f"Generated HTML for PDF: {len(html)} characters")

        # Generate PDF from rendered HTML string
        # html = html.replace(conf_settings.STATIC_URL, request.build_absolute_uri(conf_settings.STATIC_URL))
        # html = html.replace(conf_settings.MEDIA_URL, request.build_absolute_uri(conf_settings.MEDIA_URL))
        pdfkit.from_string(html, out, options)
    except Exception as e:
        # Log PDF generation errors without re-raising
        logger.error(f"PDF generation error: {e}")


# ##print


def get_membership_request(ctx):
    fp = ctx["member"].get_request_filepath()
    temp_ctx = {"member": ctx["member"]}
    template = get_assoc_text(ctx["a_id"], AssocTextType.MEMBERSHIP)
    pdf_template(temp_ctx, template, fp, html=True)
    return return_pdf(fp, _("Membership registration of %(user)s") % {"user": ctx["member"]})


def print_character(ctx, force=False):
    fp = ctx["character"].get_sheet_filepath(ctx["run"])
    ctx["pdf"] = True
    if force or reprint(fp):
        get_character_sheet(ctx)
        add_pdf_instructions(ctx)
        xhtml_pdf(ctx, "pdf/sheets/auxiliary.html", fp)
    return return_pdf(fp, f"{ctx['character']}")


def print_character_friendly(ctx, force=False):
    fp = ctx["character"].get_sheet_friendly_filepath(ctx["run"])
    ctx["pdf"] = True
    if force or reprint(fp):
        get_character_sheet(ctx)
        pdf_template(ctx, "pdf/sheets/friendly.html", fp, True)
    return return_pdf(fp, f"{ctx['character']} - " + _("Lightweight"))


def print_character_rel(ctx, force=False):
    fp = ctx["character"].get_relationships_filepath(ctx["run"])
    if force or reprint(fp):
        get_event_cache_all(ctx)
        get_character_relationships(ctx)
        pdf_template(ctx, "pdf/sheets/relationships.html", fp, True)
    return return_pdf(fp, f"{ctx['character']} - " + _("Relationships"))


def print_gallery(ctx, force=False):
    fp = ctx["run"].get_gallery_filepath()
    if force or reprint(fp):
        get_event_cache_all(ctx)
        ctx["first_aid"] = []
        for _num, el in ctx["chars"].items():
            if "first_aid" in el and el["first_aid"] == "y":
                ctx["first_aid"].append(el)
        fp = ctx["run"].get_gallery_filepath()
        xhtml_pdf(ctx, "pdf/sheets/gallery.html", fp)

    return return_pdf(fp, str(ctx["run"]) + " - " + _("Portraits"))


def print_profiles(ctx, force=False):
    fp = ctx["run"].get_profiles_filepath()
    if force or reprint(fp):
        get_event_cache_all(ctx)
        xhtml_pdf(ctx, "pdf/sheets/profiles.html", fp)
    return return_pdf(fp, str(ctx["run"]) + " - " + _("Profiles"))


def print_handout(ctx, force=True):
    fp = ctx["handout"].get_filepath(ctx["run"])
    if force or reprint(fp):
        ctx["handout"].data = ctx["handout"].show_complete()
        xhtml_pdf(ctx, "pdf/sheets/handout.html", fp)
    return return_pdf(fp, f"{ctx['handout'].data['name']}")


def print_volunteer_registry(ctx):
    fp = os.path.join(conf_settings.MEDIA_ROOT, f"volunteer_registry/{ctx['assoc'].slug}.pdf")
    xhtml_pdf(ctx, "pdf/volunteer_registry.html", fp)
    return fp


# ## HANDLE - DELETE FILES WHEN UPDATED


def cleanup_handout_pdfs_before_delete(instance):
    """Handle handout pre-delete PDF cleanup.

    Args:
        instance: Handout instance being deleted
    """
    for run in instance.event.runs.all():
        safe_remove(instance.get_filepath(run))


def cleanup_handout_pdfs_after_save(instance):
    """Handle handout post-save PDF cleanup.

    Args:
        instance: Handout instance that was saved
    """
    for run in instance.event.runs.all():
        safe_remove(instance.get_filepath(run))


def cleanup_handout_template_pdfs_before_delete(instance):
    """Handle handout template pre-delete PDF cleanup.

    Args:
        instance: HandoutTemplate instance being deleted
    """
    for run in instance.event.runs.all():
        safe_remove(instance.get_filepath(run))


def cleanup_handout_template_pdfs_after_save(instance):
    """Handle handout template post-save PDF cleanup.

    Args:
        instance: HandoutTemplate instance that was saved
    """
    for run in instance.event.runs.all():
        for el in instance.handouts.all():
            safe_remove(el.get_filepath(run))


def safe_remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def remove_run_pdf(event):
    for run in event.runs.all():
        safe_remove(run.get_profiles_filepath())
        safe_remove(run.get_gallery_filepath())


def delete_character_pdf_files(instance, single=None, runs=None):
    if not runs:
        runs = instance.event.runs.all()
    for run in runs:
        if single and run != single:
            continue
        safe_remove(instance.get_sheet_filepath(run))
        safe_remove(instance.get_sheet_friendly_filepath(run))
        safe_remove(instance.get_relationships_filepath(run))


def cleanup_character_pdfs_before_delete(instance):
    """Handle character pre-delete PDF cleanup.

    Args:
        instance: Character instance being deleted
    """
    remove_run_pdf(instance.event)
    delete_character_pdf_files(instance)


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
    for el in instance.reg.rcrs.all():
        delete_character_pdf_files(el.character, instance.reg.run)


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
    for char in instance.event.character_set.all():
        delete_character_pdf_files(char)


def cleanup_faction_pdfs_on_save(instance):
    """Handle faction post-save PDF cleanup.

    Args:
        instance: Faction instance that was saved
    """
    runs = instance.event.runs.all()
    for char in instance.characters.all():
        delete_character_pdf_files(char, runs=runs)


def deactivate_castings_and_remove_pdfs(instance):
    for casting in Casting.objects.filter(member=instance.member, run=instance.run, typ=instance.typ):
        casting.active = False
        casting.save()

    char = get_trait_character(instance.run, instance.trait.number)
    if char:
        delete_character_pdf_files(char, instance.run)


def cleanup_pdfs_on_trait_assignment(instance, created):
    """Handle assignment trait post-save PDF cleanup.

    Args:
        instance: AssignmentTrait instance that was saved
        created: Boolean indicating if instance was created
    """
    if not instance.member or not created:
        return

    deactivate_castings_and_remove_pdfs(instance)


# ## TASKS


def print_handout_go(ctx, c):
    get_handout(ctx, c)
    print_handout(ctx)


def get_fake_request(assoc_slug):
    request = HttpRequest()
    request.assoc = get_cache_assoc(assoc_slug)
    request.user = AnonymousUser()
    return request


@background_auto(queue="pdf")
def print_handout_bkg(a, s, c):
    request = get_fake_request(a)
    ctx = get_event_run(request, s)
    print_handout_go(ctx, c)


def print_character_go(ctx, c):
    try:
        get_char_check(None, ctx, c, False, True)
        print_character(ctx, True)
        print_character_friendly(ctx, True)
        print_character_rel(ctx, True)
    except Http404:
        pass
    except NotFoundError:
        pass


@background_auto(queue="pdf")
def print_character_bkg(a, s, c):
    request = get_fake_request(a)
    ctx = get_event_run(request, s)
    print_character_go(ctx, c)


@background_auto(queue="pdf")
def print_run_bkg(a, s):
    request = get_fake_request(a)
    ctx = get_event_run(request, s)

    print_gallery(ctx)
    print_profiles(ctx)

    for ch in ctx["run"].event.get_elements(Character).values_list("number", flat=True):
        print_character_go(ctx, ch)

    for h in ctx["run"].event.get_elements(Handout).values_list("number", flat=True):
        print_handout_go(ctx, h)


# ## OLD PRINTING


def odt_template(ctx, char, fp, template, aux_template):
    attempt = 0
    excepts = []
    max_attempts = 5
    while attempt < max_attempts:
        try:
            exec_odt_template(ctx, char, fp, template, aux_template)
            return
        except Exception as e:
            logger.error(f"Error in PDF creation: {e}")
            logger.error(f"Character: {char}")
            logger.error(f"Template: {template}")
            attempt += 1
            excepts.append(e)
            time.sleep(2)
    logger.error(f"ERROR IN odt_template: {excepts}")


def exec_odt_template(ctx: dict, char: dict, fp: str, template: object, aux_template: object) -> None:
    """Process ODT template to generate PDF for character data.

    Args:
        ctx: Context dictionary containing template rendering data
        char: Character data dictionary with character information
        fp: Output file path where the generated PDF will be saved
        template: ODT template file object with path attribute
        aux_template: Auxiliary template object for content processing

    Returns:
        None: Function writes PDF file to specified path
    """
    # Set up working directory based on character number
    working_dir = os.path.dirname(fp)
    working_dir = os.path.join(working_dir, str(char["number"]))
    logger.debug(f"Character PDF working directory: {working_dir}")

    # Clean up existing output file if present
    if os.path.exists(fp):
        os.remove(fp)

    # Set up temporary working directory for processing
    working_dir += "-work"
    if os.path.exists(working_dir):
        logger.debug(f"Cleaning up existing character directory: {working_dir}")
        shutil.rmtree(working_dir)
    os.makedirs(working_dir)

    # Create subdirectory for unzipped template content
    zip_dir = os.path.join(working_dir, "zipdd")
    os.makedirs(zip_dir)

    # Extract ODT template to working directory
    os.chdir(zip_dir)
    os.system(f"unzip -q {template.path}")

    # Process template content with character data
    update_content(ctx, working_dir, zip_dir, char, aux_template)

    # Repackage modified content back into ODT format
    os.chdir(zip_dir)
    os.system("zip -q -r ../out.odt *")

    # Convert ODT to PDF using unoconv
    os.chdir(working_dir)
    os.system("/usr/bin/unoconv -f pdf out.odt")

    # Move generated PDF to final destination
    os.rename("out.pdf", fp)
    # ## TODO shutil.rmtree(working_dir)
    # if os.path.exists(working_dir):
    # shutil.rmtree(working_dir)


# translate html markup to odt
def get_odt_content(ctx: dict, working_dir: str, aux_template) -> dict:
    """
    Extract ODT content from HTML template for PDF generation.

    Converts an HTML template to ODT format using LibreOffice, then extracts
    and parses the XML content to retrieve text, automatic styles, and document
    styles for further processing.

    Args:
        ctx: Template context dictionary containing variables for rendering
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
    html = aux_template.render(ctx)

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
    i = tag.find("}")
    if i >= 0:
        tag = tag[i + 1 :]
    return tag


def replace_data(path, char):
    """
    Replace character data placeholders in template file.

    Args:
        path: Path to template file
        char: Character data dictionary with replacement values
    """
    with open(path) as file:
        filedata = file.read()

    for s in ["number", "name", "title"]:
        if s not in char:
            continue
        filedata = filedata.replace(f"#{s}#", str(char[s]))

    # Write the file out again
    with open(path, "w") as file:
        file.write(filedata)


def update_content(ctx: Any, working_dir: str, zip_dir: str, char: Any, aux_template: str) -> None:
    """Update PDF content for character sheets.

    Modifies LibreOffice document content with character data for PDF
    generation, handling template replacement and content formatting.

    Args:
        ctx: Context object for processing
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
    elements = get_odt_content(ctx, working_dir, aux_template)

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
        tr = Trait.objects.get(event_id=run.event_id, number=number)
        mb = AssignmentTrait.objects.get(run=run, trait=tr).member
        rcrs = RegistrationCharacterRel.objects.filter(reg__run=run, reg__member=mb).select_related("character")
        if not rcrs.exists():
            return None
        return rcrs.first().character
    except ObjectDoesNotExist:
        return None
