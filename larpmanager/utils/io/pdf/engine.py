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
from urllib.parse import unquote

from django.conf import settings as conf_settings
from django.core.files.storage import default_storage
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.template import Context, Engine
from django.template.loader import get_template
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageDraw
from reportlab.lib import pagesizes
from xhtml2pdf import pisa
from xhtml2pdf.config.resources import ResourceAccessPolicy

from larpmanager.cache.basic import get_run_basic_cache
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


# All the configuration names defining the styling of the generated sheets
PDF_CONFIGS = [
    "page_css",
    "pdf_page_size",
    "pdf_margin",
    "pdf_header",
    "pdf_footer",
    "pdf_background",
    "pdf_font_title",
    "pdf_font_text",
    "pdf_color_title",
    "pdf_color_text",
    "pdf_color_link",
    "pdf_color_bold",
    "pdf_color_border",
    "pdf_size_title",
    "pdf_size_text",
]


def has_pdf_customization(event_id: int) -> bool:
    """Return True if event has any custom PDF styling configured."""
    for key in PDF_CONFIGS:
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

    # The URL is quoted, the file name is not: a file uploaded with a space in the
    # name arrives here as "%20" and would never be found on the filesystem
    uri = unquote(uri)

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


def _resource_policy() -> ResourceAccessPolicy:
    """Return the xhtml2pdf policy allowing local reads of media and static files.

    The default policy confines local reads to the working directory, which
    blocks the uploaded fonts and backgrounds served from the media root.
    """
    return ResourceAccessPolicy(extra_roots=(Path(conf_settings.MEDIA_ROOT), Path(conf_settings.STATIC_ROOT)))


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


# Mime types accepted for the font files uploaded in the event configuration
PDF_FONT_TYPES = ["font/ttf", "font/otf", "font/sfnt", "application/x-font-ttf"]

# Page formats available for the sheets, as (config value, label) choices
PDF_PAGE_SIZE_CHOICES = [
    ("", "A4"),
    ("a4_landscape", _("A4 landscape")),
    ("a5", "A5"),
    ("a5_landscape", _("A5 landscape")),
    ("letter", _("Letter")),
    ("letter_landscape", _("Letter landscape")),
]

# Page dimensions in points, for each available page format
_PDF_PAGE_SIZES = {
    "": pagesizes.A4,
    "a4_landscape": pagesizes.landscape(pagesizes.A4),
    "a5": pagesizes.A5,
    "a5_landscape": pagesizes.landscape(pagesizes.A5),
    "letter": pagesizes.LETTER,
    "letter_landscape": pagesizes.landscape(pagesizes.LETTER),
}

# Font family names used for the fonts uploaded in the event configuration
_PDF_FONT_NAMES = {"pdf_font_title": "lm_title_font", "pdf_font_text": "lm_text_font"}

# Selectors receiving each customizable element: xhtml2pdf does not inherit styles reliably
_PDF_TITLE_SELECTORS = "#char_name, #char_title, .head, h1, h2, h3, h4, h5, h6"
_PDF_TEXT_SELECTORS = "html, body, div, p, span, td, th, li"
_PDF_LINK_SELECTORS = "a"
_PDF_BOLD_SELECTORS = "b, strong"

# Default size of the text in the generated sheets, in points
_PDF_BASE_SIZE = 10

# Default size of each title element, as a ratio of the size of the text
_PDF_TITLE_SCALES = {
    "#char_name, h1": 1.385,
    "#char_title, h2": 1.231,
    ".head, h3": 1.08,
    "h4, h5, h6": 1.0,
}

# Points in a centimeter, to convert the margin set in the event configuration
_PDF_CM = 28.3465

# Vertical space reserved for the header and the footer bands, in points: the content
# is drawn at the top of the band, so anything more is left empty under the footer
_PDF_BAND_HEIGHT = 24

# Space left between the header / footer bands and the content of the page, in points
_PDF_BAND_GAP = 6

# Default page margin, in centimeters
_PDF_DEFAULT_MARGIN = 2.0

# Content of the automatic header: organization, character and event name
_PDF_HEADER_HTML = (
    '<table class="pdf-band"><tr><td class="pdf-left">{organization}</td>'
    '<td class="pdf-center">{character}</td><td class="pdf-right">{event}</td></tr></table>'
)

# Content of the automatic footer: event name, links of the event and page numbers
_PDF_FOOTER_HTML = (
    '<table class="pdf-band"><tr><td class="pdf-left">{event}</td>{links}'
    '<td class="pdf-right"><pdf:pagenumber> / <pdf:pagecount></td></tr></table>'
)

# Content of the footer when only the links of the event are shown
_PDF_LINKS_HTML = '<table class="pdf-band"><tr>{links}</tr></table>'

# Color of the separator lines, when the event does not set one: the default of <hr>
_PDF_BORDER_DEFAULT = "#000000"

# Colors accepted as separator: written in the HTML of every <hr>, so nothing else is allowed
_PDF_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{3,8}$")

# Styling of the automatic header and footer bands: their separator line is drawn over
# the whole width of the frame, so the band is kept inside the margin of the page.
_PDF_BAND_CSS = (
    "#header_content, #footer_content {{ font-size: 80%; }}\n"
    "#header_content {{ border-bottom: 1px solid {border}; padding-bottom: 4pt; }}\n"
    "#footer_content {{ border-top: 1px solid {border}; padding-top: 4pt; }}\n"
    ".pdf-band {{ width: 100%; }}\n"
    ".pdf-band td.pdf-left {{ text-align: left; }}\n"
    ".pdf-band td.pdf-center {{ text-align: center; }}\n"
    ".pdf-band td.pdf-right {{ text-align: right; }}\n"
)


def _pdf_margin(value: str) -> float:
    """Return the page margin in points from the config value, in centimeters."""
    try:
        margin = float(value)
    except (TypeError, ValueError):
        margin = _PDF_DEFAULT_MARGIN
    return margin * _PDF_CM


def _pdf_geometry(configs: dict) -> tuple[float, float, float]:
    """Return the size of the page and its margin, in points.

    The margin is kept sane, so that a large value on a small page still leaves room.
    """
    width, height = _PDF_PAGE_SIZES.get(configs.get("pdf_page_size") or "", pagesizes.A4)
    margin = min(_pdf_margin(configs.get("pdf_margin")), width / 4, height / 4)
    return width, height, margin


def _pdf_frames(bands: dict, width: float, height: float, margin: float) -> dict[str, str]:
    """Build the frame declarations of the @page rule, by frame name.

    The content frame shrinks to leave room for the header and footer bands, that
    are placed inside the top and bottom margin of the page. The bands keep the
    width of the content: xhtml2pdf draws their separator line over the whole
    width of the frame, whatever element the border is declared on.
    """
    inner_width = width - 2 * margin
    top = margin + (_PDF_BAND_HEIGHT + _PDF_BAND_GAP if bands.get("header") else 0)
    bottom = margin + (_PDF_BAND_HEIGHT + _PDF_BAND_GAP if bands.get("footer") else 0)

    frames = {
        "content_frame": (
            f"@frame content_frame {{ left: {margin:g}pt; top: {top:g}pt; "
            f"width: {inner_width:g}pt; height: {height - top - bottom:g}pt; }}"
        ),
    }

    if bands.get("header"):
        frames["header_frame"] = (
            f"@frame header_frame {{ -pdf-frame-content: header_content; left: {margin:g}pt; "
            f"top: {margin:g}pt; width: {inner_width:g}pt; height: {_PDF_BAND_HEIGHT:g}pt; }}"
        )

    if bands.get("footer"):
        frames["footer_frame"] = (
            f"@frame footer_frame {{ -pdf-frame-content: footer_content; left: {margin:g}pt; "
            f"top: {height - margin - _PDF_BAND_HEIGHT:g}pt; "
            f"width: {inner_width:g}pt; height: {_PDF_BAND_HEIGHT:g}pt; }}"
        )

    return frames


def _page_rule_end(page_css: str, start: int) -> int | None:
    """Return the position of the brace closing the @page rule opened at start."""
    depth = 1
    for index in range(start, len(page_css)):
        if page_css[index] == "{":
            depth += 1
        elif page_css[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _pdf_page_rule(configs: dict, page_css: str, bands: dict) -> str:
    """Build the @page rule with size, background and frames, merged with the custom CSS.

    When the custom CSS declares its own @page rule, the generated declarations are
    added inside it: a second @page rule would replace the first one entirely. The
    frames are appended at the end of the rule, so that the ones written by hand come
    first and keep the priority over the generated ones.
    """
    width, height, margin = _pdf_geometry(configs)

    declarations = []
    if not re.search(r"(?<![\w-])size\s*:", page_css):
        declarations.append(f"size: {width:g}pt {height:g}pt;")

    background = configs.get("pdf_background")
    if background:
        declarations.append(
            f"background-image: url('{default_storage.url(background)}'); "
            f"background-width: {width:g}pt; background-height: {height:g}pt; "
            f"background-object-position: 0pt 0pt;",
        )

    frames = list(_pdf_frames(bands, width, height, margin).values())

    # Add the declarations to the custom @page rule, if there is one
    match = re.search(r"@page[^{]*\{", page_css)
    end = _page_rule_end(page_css, match.end()) if match else None
    if match and end is not None:
        return (
            page_css[: match.end()]
            + " "
            + " ".join(declarations)
            + " "
            + page_css[match.end() : end].strip()
            + " "
            + " ".join(frames)
            + " "
            + page_css[end:]
        )

    return "@page { " + " ".join(declarations + frames) + " }\n" + page_css


def _pdf_fonts_css(configs: dict) -> str:
    """Build the @font-face rules for the fonts uploaded in the event configuration."""
    css = ""
    for config_name, selectors in (
        ("pdf_font_title", _PDF_TITLE_SELECTORS),
        ("pdf_font_text", _PDF_TEXT_SELECTORS),
    ):
        font_path = configs.get(config_name)
        if not font_path:
            continue
        font_name = _PDF_FONT_NAMES[config_name]
        css += (
            f"@font-face {{ font-family: '{font_name}'; src: url('{default_storage.url(font_path)}'); }}\n"
            f"{selectors} {{ font-family: '{font_name}'; }}\n"
        )
    return css


def _pdf_size(value: Any) -> float | None:
    """Return the size ratio from the config value, in percent, when it is usable."""
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return None
    return percent / 100 if percent > 0 else None


def _pdf_sizes_css(configs: dict) -> str:
    """Build the font size rules for the sizes set in the event configuration.

    The sizes are written in points: a percentage would be applied again by every
    nested element, so the text of a deep sheet would grow out of the page.
    """
    css = ""

    text = _pdf_size(configs.get("pdf_size_text"))
    if text:
        css += f"{_PDF_TEXT_SELECTORS} {{ font-size: {_PDF_BASE_SIZE * text:g}pt; }}\n"

    # The titles follow the size of the text, unless they are given one of their own
    title = _pdf_size(configs.get("pdf_size_title")) or text
    if title:
        for selectors, scale in _PDF_TITLE_SCALES.items():
            css += f"{selectors} {{ font-size: {_PDF_BASE_SIZE * scale * title:g}pt; }}\n"

    return css


def _pdf_colors_css(configs: dict) -> str:
    """Build the color rules for the colors set in the event configuration."""
    css = ""
    for config_name, selectors in (
        ("pdf_color_text", _PDF_TEXT_SELECTORS),
        ("pdf_color_title", _PDF_TITLE_SELECTORS),
        ("pdf_color_link", _PDF_LINK_SELECTORS),
        ("pdf_color_bold", _PDF_BOLD_SELECTORS),
    ):
        color = configs.get(config_name)
        if color:
            css += f"{selectors} {{ color: {color}; }}\n"
    return css


def _pdf_border(configs: dict) -> str:
    """Return the color of the separator lines set in the event configuration."""
    color = (configs.get("pdf_color_border") or "").strip()
    return color if _PDF_COLOR_RE.match(color) else _PDF_BORDER_DEFAULT


def _pdf_links(context: dict) -> str:
    """Build the footer cells with the links to the gallery, the website and the event buttons."""
    if context.get("light_pdf"):
        return ""

    links = []

    run = context.get("run")
    main_domain = (context.get("association") or {}).get("main_domain")
    if run and main_domain:
        basic = get_run_basic_cache(run.id, context=context)
        gallery = f"https://{basic['association_slug']}.{main_domain}/{basic['slug']}/{basic['number']}"
        links.append((_("Gallery"), gallery))

    website = getattr(context.get("event"), "website", "")
    if website:
        links.append((_("Website"), website))

    links += [(button[0], button[2]) for button in context.get("buttons", [])]

    return "".join(f'<td class="pdf-center"><a href="{escape(url)}">{escape(name)}</a></td>' for name, url in links)


def _pdf_bands(context: dict, configs: dict) -> None:
    """Add to the context the content of the automatic header and footer."""
    sheet_char = context.get("sheet_char") or {}
    event_name = escape(context["event"].name)

    context["header_content"] = ""
    if configs.get("pdf_header"):
        context["header_content"] = _PDF_HEADER_HTML.format(
            organization=escape(context["event"].association.name),
            character=escape(sheet_char.get("name", "")),
            event=event_name,
        )

    links = _pdf_links(context)
    context["footer_content"] = ""
    if configs.get("pdf_footer"):
        context["footer_content"] = _PDF_FOOTER_HTML.format(event=event_name, links=links)
    elif links:
        context["footer_content"] = _PDF_LINKS_HTML.format(links=links)


def _add_pdf_style(context: dict) -> None:
    """Add to the context the PDF styling built from the event configuration.

    The generated rules are placed before the custom CSS code, so that it keeps
    the last word on every element.
    """
    configs = {
        name: get_event_config(context["event"].id, name, context=context, bypass_cache=True) for name in PDF_CONFIGS
    }

    _pdf_bands(context, configs)
    bands = {"header": bool(context["header_content"]), "footer": bool(context["footer_content"])}

    context["pdf_border"] = _pdf_border(configs)

    page_css = configs.get("page_css") or ""
    style = _pdf_fonts_css(configs) + _pdf_sizes_css(configs) + _pdf_colors_css(configs)
    if bands["header"] or bands["footer"]:
        style += _PDF_BAND_CSS.format(border=context["pdf_border"])

    context["page_css"] = style + _pdf_page_rule(configs, page_css, bands)


def add_pdf_instructions(context: dict) -> None:
    """Add PDF generation instructions to template context.

    Builds the styling of the sheet from the PDF options of the event, and the
    content of the automatic header and footer. Updates the context dictionary
    in-place.

    Args:
        context: Template context dictionary containing event and character data.
             Must include 'event' and 'sheet_char' keys.

    Returns:
        None: Modifies the context dictionary in-place.

    Side Effects:
        - Updates context with 'page_css', 'header_content', 'footer_content' keys
        - Replaces utility codes with URLs

    """
    # Build the styling and the header / footer content from the event configuration
    _add_pdf_style(context)

    # Find all utility codes in format #code# in the custom CSS, and replace with URLs
    for utility_code_match in re.findall(r"(#[\w-]+#)", context["page_css"]):
        utility_code = utility_code_match.replace("#", "")
        util = get_object_or_404(Util, cod=utility_code)
        context["page_css"] = context["page_css"].replace(utility_code_match, util.util.url)
    logger.debug("Processed PDF css: %s characters", len(context["page_css"]))


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

    # xhtml2pdf draws every <hr> with the color attribute, ignoring the CSS rules
    border = context.get("pdf_border")
    if border and border != _PDF_BORDER_DEFAULT:
        html_content = re.sub(r"<hr\b(?![^>]*\bcolor=)", f'<hr color="{border}"', html_content)

    # Generate PDF file from rendered HTML
    with Path(output_filename).open("wb") as pdf_file:
        # Convert HTML to PDF using xhtml2pdf library
        pdf_result = pisa.CreatePDF(
            html_content,
            dest=pdf_file,
            link_callback=link_callback,
            resource_policy=_resource_policy(),
        )

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
