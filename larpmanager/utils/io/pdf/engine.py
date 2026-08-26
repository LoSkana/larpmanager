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

import base64
import io
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from django.conf import settings as conf_settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.template import Context, Engine
from django.template.loader import get_template
from PIL import Image, ImageDraw
from xhtml2pdf import pisa

from larpmanager.cache.config import get_event_config
from larpmanager.models.miscellanea import Util
from larpmanager.utils.core.common import get_now

# Restricted engine for rendering untrusted database templates
_RESTRICTED_ENGINE = Engine(
    libraries={},
    builtins=["django.template.defaulttags", "django.template.defaultfilters"],
    autoescape=True,
)

logger = logging.getLogger(__name__)


def fix_filename(filename: Any) -> Any:
    """Remove special characters from filename for safe PDF generation."""
    return re.sub(r"[^A-Za-z0-9 ]+", "", filename)


def has_pdf_customization(event_id: int) -> bool:
    """Return True if event has any custom PDF styling configured."""
    for key in ["page_css", "header_content", "footer_content"]:
        value = get_event_config(event_id, key)
        if value and str(value).strip():
            return True
    return False


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
    """Return PDF file as HTTP response."""
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
        root = Path(m_root)
        resolved = (root / uri.replace(m_url, "")).resolve()
    # Check if URI is a static URL and build corresponding file path
    elif uri.startswith(s_url):
        root = Path(s_root)
        resolved = (root / uri.replace(s_url, "")).resolve()
    # Return empty string for unrecognized URI patterns
    else:
        return ""

    # Confine to the media/static root: org-authored HTML must not reach
    # arbitrary filesystem paths via "../" traversal
    if not resolved.is_relative_to(root.resolve()):
        return ""

    # Verify the file actually exists on the filesystem
    if not resolved.is_file():
        return ""

    return str(resolved)


_REL_IMAGE_SIZE = 400


def _round_image_data_uri(url: str, radius: int = _REL_IMAGE_SIZE // 6) -> str | None:
    """Convert image URL to fixed-size square data URI with rounded corners via Pillow mask."""
    file_path = link_callback(url, "")
    if not file_path:
        return None
    try:
        img = Image.open(file_path).convert("RGBA")
        # Crop to square from center
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((_REL_IMAGE_SIZE, _REL_IMAGE_SIZE), Image.LANCZOS)
        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        s = _REL_IMAGE_SIZE - 1
        draw.rounded_rectangle([0, 0, s, s], radius=radius, fill=255)
        img.putalpha(mask)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001
        return None


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
        # Render database-stored template with a restricted engine
        template = _RESTRICTED_ENGINE.from_string(template_path)
        django_context = Context(context)
        html_content = template.render(django_context)
    else:
        # Treat template_path as Django template path and load template file
        template = get_template(template_path)
        html_content = template.render(context)

    # xhtml2pdf ignores unitless line-height values (e.g. "2"); convert to percentage
    html_content = re.sub(
        r"line-height:\s*([0-9]+(?:\.[0-9]+)?)\s*;",
        lambda matched: f"line-height: {float(matched.group(1)) * 100:g}%;",
        html_content,
    )

    # Generate PDF file from rendered HTML
    with Path(output_filename).open("wb") as pdf_file:
        # Convert HTML to PDF using xhtml2pdf library
        pdf_result = pisa.CreatePDF(html_content, dest=pdf_file, link_callback=link_callback)

        # Check for PDF generation errors; log details, don't leak rendered HTML
        if pdf_result.err:
            logger.error("PDF generation failed for %s", output_filename)
            msg = "We had some errors generating the PDF"
            raise Http404(msg)


class _PrintableDict(dict):
    """Dict that renders as a given string when printed directly in a template."""

    def __init__(self, label: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._label = label

    def __str__(self) -> str:
        return self._label
