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
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from allauth.utils import get_request_param
from django import template
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.db.models import Max
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import escape, format_html, mark_safe
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.registration import round_to_nearest_cent
from larpmanager.models.association import get_url
from larpmanager.models.casting import Trait
from larpmanager.models.utils import strip_tags
from larpmanager.models.writing import Character, FactionType
from larpmanager.utils.core.common import html_clean
from larpmanager.utils.io.pdf import get_trait_character

if TYPE_CHECKING:
    from django.forms import BoundField, Form

    from larpmanager.models.event import Run

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter
def modulo(num: int, val: int) -> int:
    """Template filter to calculate modulo operation.

    Args:
        num (int): Number to divide
        val (int): Divisor

    Returns:
        int: Remainder of num divided by val

    """
    return num % val


@register.filter
def basename(file_path: str | Path) -> str:
    """Template filter to extract basename from file path.

    Args:
        file_path (str): File path

    Returns:
        str: Basename of the file path (filename without directory)

    """
    if not file_path:
        return ""
    return Path(file_path).name


@register.filter
def clean_tags(tx: str) -> str:
    """Template filter to clean HTML tags from text.

    Args:
        tx (str): Text containing HTML tags

    Returns:
        str: Text with HTML tags removed and br tags replaced with spaces

    """
    tx = tx.replace("<br />", " ")
    return strip_tags(tx)


@register.filter
def get(value: dict[str, Any], arg: str) -> Any:
    """Template filter to get dictionary value by key.

    Args:
        value (dict): Dictionary to look up
        arg (str): Key to retrieve

    Returns:
        any: Dictionary value for key, or empty string if not found

    """
    if arg is not None and value:
        try:
            if arg in value:
                return value[arg]
        except TypeError:
            # arg is not hashable (e.g., dict), cannot be used as dict key
            # This can happen when iterating over cached data with dict keys
            return ""
    return ""


def get_tooltip(context: dict, character: dict[str, Any]) -> str:
    """Generate HTML tooltip for character display.

    Args:
        context: Template context
        character (dict): Character data dictionary

    Returns:
        str: HTML string for character tooltip with avatar and details

    """
    avatar_url = static("larpmanager/assets/blank-avatar.svg")
    if character.get("player_uuid") and character["player_prof"]:
        avatar_url = character["player_prof"]
    tooltip = f"<img src='{escape(avatar_url)}'>"

    tooltip = tooltip_fields(character, tooltip)

    tooltip = tooltip_factions(character, context, tooltip)

    if character["teaser"]:
        tooltip += "<span class='teaser'>" + escape(replace_chars(context, character["teaser"])) + " (...)</span>"

    return tooltip


def tooltip_fields(character: dict[str, Any], tooltip: str) -> str:
    """Add character name, title, and player information to tooltip.

    Args:
        character (dict): Character data dictionary
        tooltip (str): Current tooltip HTML string

    Returns:
        str: Updated tooltip HTML with character fields

    """
    tooltip += f"<span><b class='name'>{escape(character['name'])}</b>"

    if character["title"]:
        tooltip += " - <b class='title'>" + escape(character["title"]) + "</b>"

    if character.get("pronoun"):
        tooltip += " (" + escape(character["pronoun"]) + ")"

    tooltip += "</span>"

    if character.get("player_uuid"):
        tooltip += "<span>" + str(_("Player")) + ": <b>" + escape(character["player_full"]) + "</b></span>"

    return tooltip


def tooltip_factions(character: dict[str, Any], context: dict, tooltip: str) -> str:
    """Add faction information to character tooltip.

    Args:
        character (dict): Character data dictionary
        context: Template context with faction data
        tooltip (str): Current tooltip HTML string

    Returns:
        str: Updated tooltip HTML with faction information

    """
    faction_names = ""
    for faction_number in context["factions"]:
        faction_element = context["factions"][faction_number]
        if faction_element["typ"] == FactionType.SECRET:
            continue
        if faction_number in character["factions"]:
            if faction_names:
                faction_names += ", "
            faction_names += escape(faction_element["name"])
    if faction_names:
        tooltip += "<span>" + str(_("Factions")) + ": " + faction_names + "</span>"
    return tooltip


@register.simple_tag(takes_context=True)
def replace_chars(context: dict, text: str, limit: int = 200) -> str:
    """Template tag to replace character number references with names.

    Replaces #XX, @XX, and ^XX patterns with character names in text.

    Args:
        context: Template context containing character data
        text (str): Text containing character references
        limit (int): Maximum length of returned text

    Returns:
        str: Text with character references replaced by names

    """
    text = html_clean(text)
    for character_number in range(context["max_ch_number"], 0, -1):
        if character_number not in context["chars"]:
            continue
        character_name = context["chars"][character_number]["name"]
        text = text.replace(f"#{character_number}", character_name)
        text = text.replace(f"@{character_number}", character_name)

        first_name_parts = character_name.split()
        if first_name_parts:
            first_name = first_name_parts[0]
            text = text.replace(f"^{character_number}", first_name)
    return text[:limit]


def go_character(
    context: dict,
    search_pattern: str,
    character_number: int,
    text: str,
    run: Run,
    *,
    include_tooltip: bool,
    simple: bool = False,
) -> str:
    """Replace character reference with formatted link or name.

    Processes text containing character references (like '#1', '@1', '^1') and replaces
    them with either formatted HTML links or simple bold names, depending on the simple
    parameter. Optionally includes tooltips for character information.

    Args:
        context: Template context dictionary containing character data under 'chars' key.
        search_pattern: Pattern to search for in the text (e.g., '#1', '@1', '^1').
        character_number: Character number/ID to look up in the context chars dictionary.
        text: Input text that may contain the search pattern to be replaced.
        run: Run instance used for generating character URLs via get_slug() method.
        include_tooltip: If True, includes hover tooltip with character information.
        simple: If True, returns character name in bold; if False, returns clickable link.

    Returns:
        The input text with character references replaced by formatted HTML, or
        unchanged text if search pattern not found or character data unavailable.

    Example:
        >>> go_character(context, '#1', 1, 'See character #1', run_obj, True, False)
        'See character <a class="link_show_char" href="/run/char/1">John Doe</a>'

    """
    # Early return if search pattern not in text
    if search_pattern not in text:
        return text

    # Check if character data exists in context
    if "chars" not in context:
        return text

    # Verify specific character number exists
    if character_number not in context["chars"]:
        return text

    # Get character data from context
    character_data = context["chars"][character_number]

    # Generate character URL using run slug and character uuid
    character_url = get_url(
        reverse("character", args=[run.get_slug(), character_data["uuid"]]),
        context["association_slug"],
    ).replace('"', "")

    # Create either simple bold name or full link based on simple flag
    if simple:
        name_parts = character_data["name"].split()
        first_name = name_parts[0] if name_parts else ""
        formatted_link = f"<b>{escape(first_name)}</b>"
    else:
        formatted_link = (
            f"<a class='link_show_char' href='{escape(character_url)}'>{escape(character_data['name'])}</a>"
        )

        # Add tooltip wrapper if tooltips are enabled
        if include_tooltip:
            tooltip_content = get_tooltip(context, character_data)
            formatted_link = (
                "<span class='has_show_char'>"
                + formatted_link
                + f"</span><span class='hide show_char'>{tooltip_content}</span>"
            )

    # Replace search pattern with generated link/name
    return text.replace(search_pattern, formatted_link)


def _remove_unimportant_prefix(text: str) -> str:
    """Remove first occurrence of $unimportant from text and clean up empty HTML tags at start.

    This function removes the first occurrence of the '$unimportant' marker from the input text.
    If the marker was found and removed, it then proceeds to clean up any empty HTML tags
    and whitespace characters that appear at the beginning of the resulting text.

    Args:
        text: Text that may contain $unimportant prefix. Can be None or empty string.

    Returns:
        The processed text with $unimportant removed and empty HTML tags cleaned up.
        Returns the original text if it's None or empty, or if no $unimportant marker was found.

    Example:
        >>> _remove_unimportant_prefix("$unimportant<p></p>Hello world")
        "Hello world"
        >>> _remove_unimportant_prefix("Regular text")
        "Regular text"

    """
    # Return early if text is None or empty
    if not text:
        return text

    # Store original text to check if replacement occurred
    original_text = text
    # Remove first occurrence of $unimportant marker
    text = text.replace("$unimportant", "", 1)

    # Only clean up empty tags if $unimportant was actually replaced
    if text != original_text:
        # Iteratively remove empty HTML tags and whitespace from the beginning
        while True:
            # Remove leading whitespace before checking for empty tags
            text_without_leading_whitespace = text.lstrip()

            # Match empty HTML tags like <p></p>, <div></div>, <span></span>, etc.
            # Also match \r, \n, &nbsp; and other whitespace characters inside tags
            empty_tag_match = re.match(
                r"^<(\w+)(?:\s[^>]*)?>(?:\s|&nbsp;|\r|\n)*</\1>",
                text_without_leading_whitespace,
            )

            # If empty tag found, remove it and continue loop
            if empty_tag_match:
                text = text_without_leading_whitespace[empty_tag_match.end() :]
            else:
                # No more empty tags found, use stripped text and exit loop
                text = text_without_leading_whitespace
                break

    return text


@register.simple_tag(takes_context=True)
def show_char(context: dict, element: dict | str | None, run: Run, include_tooltip: int) -> str:
    """Template tag to process text and convert character references to links.

    This function processes text content and converts character references (prefixed with
    #, @, or ^) into clickable links. It also handles character tooltips and removes
    unimportant tags from the processed text.

    Args:
        context: Template context dictionary containing rendering state
        element: Text element to process - can be a string, dict with 'text' key, or None
        run: Run instance used for character lookup and event context
        include_tooltip: Whether to include character tooltips in generated links

    Returns:
        Safe HTML string with character references converted to links and unimportant
        tags removed

    """
    # Extract text content from various input types
    if isinstance(element, dict) and "text" in element:
        text = element["text"] + " "
    elif element is not None:
        text = str(element) + " "
    else:
        text = ""

    # Cache the maximum character number for this run's event to avoid repeated queries
    if "max_ch_number" not in context:
        context["max_ch_number"] = run.event.get_elements(Character).aggregate(Max("number"))["number__max"]

    # Handle case where no characters exist in the event
    if not context["max_ch_number"]:
        context["max_ch_number"] = 0

    # Process character references in descending order to avoid partial matches
    # #XX creates relationships, @XX counts as character in faction/plot, ^XX is simple reference
    for character_number in range(context["max_ch_number"], 0, -1):
        text = go_character(
            context, f"#{character_number}", character_number, text, run, include_tooltip=include_tooltip
        )
        text = go_character(
            context, f"@{character_number}", character_number, text, run, include_tooltip=include_tooltip
        )
        text = go_character(
            context, f"^{character_number}", character_number, text, run, include_tooltip=include_tooltip, simple=True
        )

    # Clean up unimportant tags by removing $unimportant prefix and empty tags
    text = _remove_unimportant_prefix(text)

    # Text is already HTML-safe from character link processing, so we can mark it as such
    return format_html("{}", mark_safe(text))  # noqa: S308


def go_trait(
    context: dict,
    search: str,
    trait_number: int,
    text: str,
    run: Run,
    *,
    include_tooltip: bool,
    simple: bool = False,
) -> str:
    """Replace trait reference with character link.

    Searches for a pattern in text and replaces it with either a character name
    or a clickable link to the character page, depending on the simple flag.

    Args:
        context: Template context dictionary containing trait and character data
        search: Pattern string to search for in the text
        trait_number: Trait number identifier to look up the associated character
        text: Input text containing the search pattern to be replaced
        run: Run instance used for character lookup operations
        include_tooltip: Whether to include hover tooltip in the generated link
        simple: If True, returns bold character name; if False, returns full HTML link

    Returns:
        Modified text string with trait reference replaced by character link or name,
        or original text if pattern not found or character data unavailable

    """
    # Early return if search pattern not found in text
    if search not in text:
        return text

    # Initialize traits cache if not present in context
    if "traits" not in context:
        context["traits"] = {}

    # Get character number from cached traits or fetch from database
    if trait_number in context["traits"]:
        character_number = context["traits"][trait_number]["char"]
    else:
        character = get_trait_character(run, trait_number)
        if not character:
            return text
        character_number = character.number

    # Verify character exists in context data
    if character_number not in context["chars"]:
        return text

    # Get character data from context
    character_data = context["chars"][character_number]

    # Generate appropriate output based on simple flag
    if simple:
        # Simple mode: return bold first name only
        name_parts = character_data["name"].split()
        first_name = name_parts[0] if name_parts else ""
        link = f"<b>{escape(first_name)}</b>"
    else:
        # Full mode: generate clickable link with optional tooltip
        tooltip = ""
        if include_tooltip:
            tooltip = get_tooltip(context, character_data)

        # Build character page URL
        character_url = get_url(
            reverse("character", args=[run.get_slug(), character_data["uuid"]]),
            context["slug"],
        )

        # Create HTML link with hover functionality
        link = (
            f"<span class='has_show_char'><a href='{escape(character_url)}'>{escape(character_data['name'])}</a></span>"
            f"<span class='hide show_char'>{tooltip}</span>"
        )

    # Replace search pattern with generated link/name
    return text.replace(search, link)


@register.simple_tag(takes_context=True)
def show_trait(context: dict, text: str, run: Run, tooltip: bool) -> str:  # noqa: FBT001
    """Template tag to process text and convert trait references to character links.

    Args:
        context: Template context
        text (str): Text containing trait references
        run: Run instance for trait lookup
        tooltip (bool): Whether to include character tooltips

    Returns:
        str: Safe HTML with trait references converted to character links

    """
    if "max_trait" not in context:
        context["max_trait"] = Trait.objects.filter(event_id=run.event_id).aggregate(Max("number"))["number__max"]

    if not context["max_trait"]:
        context["max_trait"] = 0

    for trait_number in range(context["max_trait"], 0, -1):
        text = go_trait(context, f"#{trait_number}", trait_number, text, run, include_tooltip=tooltip)
        text = go_trait(context, f"@{trait_number}", trait_number, text, run, include_tooltip=tooltip)
        text = go_trait(context, f"^{trait_number}", trait_number, text, run, include_tooltip=tooltip, simple=True)

    # Text is already HTML-safe from trait link processing, so we can mark it as such
    return format_html("{}", mark_safe(text))  # noqa: S308


@register.simple_tag
def key(d: Any, key_name: Any, s_key_name: Any = None) -> Any:
    """Template tag to safely get dictionary value by key.

    Args:
        d (dict): Dictionary to look up
        key_name: Primary key name
        s_key_name: Optional secondary key to append

    Returns:
        any: Dictionary value or empty string if not found

    """
    if not key_name:
        return ""
    if s_key_name:
        key_name = str(key_name) + "_" + str(s_key_name)
    if key_name in d:
        return d[key_name]
    key_name = str(key_name)
    if key_name in d:
        return d[key_name]
    return ""


@register.simple_tag
def get_field(form: Form, field_name: str) -> BoundField | str:
    """Template tag to safely get form field by name.

    Args:
        form: Django form instance
        field_name (str): Field name to retrieve

    Returns:
        Field: Form field or empty string if not found

    """
    if field_name in form:
        return form[field_name]
    return ""


@register.simple_tag(takes_context=True)
def get_field_show_char(context: dict, form: Form, name: str, run: Run, tooltip: bool) -> str:  # noqa: FBT001
    """Template tag to get form field and process character references.

    Args:
        context: Template context
        form: Django form instance
        name (str): Field name to retrieve
        run: Run instance for character processing
        tooltip (bool): Whether to include tooltips

    Returns:
        str: Processed field value with character links

    """
    if name in form:
        v = form[name]
        return show_char(context, v, run, include_tooltip=tooltip)
    return ""


@register.simple_tag
def get_deep_field(form: Form | dict, key1: str, key2: str) -> Any:
    """Template tag to get nested form field value.

    Args:
        form: Form or dictionary
        key1: First level key
        key2: Second level key

    Returns:
        any: Nested value or empty string if not found

    """
    if key1 in form and key2 in form[key1]:
        return form[key1][key2]
    return ""


@register.filter
def get_form_field(form: Form, name: str) -> BoundField | str:
    """Template filter to get form field by name.

    Args:
        form: Django form instance
        name (str): Field name

    Returns:
        Field: Form field or empty string if not found

    """
    if name in form.fields:
        return form[name]
    return ""


@register.simple_tag
def lookup(obj: Any, prop: str) -> Any:
    """Template tag to safely get object attribute.

    Args:
        obj: Object to inspect
        prop (str): Property name to retrieve

    Returns:
        any: Property value or empty string if not found

    """
    if hasattr(obj, prop):
        value = getattr(obj, prop)
        if value:
            return value
    return ""


@register.simple_tag
def get_registration_option(reg: Any, number: Any) -> Any:
    """Template tag to get registration option form text.

    Args:
        reg: Registration instance
        number (int): Option number

    Returns:
        str: Option form text or empty string

    """
    v = getattr(reg, f"option_{number}")
    if v:
        return v.get_form_text()
    return ""


@register.simple_tag
def gt(value: Any, arg: Any) -> Any:
    """Template tag for greater than comparison.

    Args:
        value: Value to compare
        arg: Comparison value

    Returns:
        bool: True if value > arg

    """
    return value > int(arg)


@register.simple_tag
def lt(value: Any, arg: Any) -> Any:
    """Template tag for less than comparison.

    Args:
        value: Value to compare
        arg: Comparison value

    Returns:
        bool: True if value < arg

    """
    return value < int(arg)


@register.simple_tag
def gte(value: Any, arg: Any) -> Any:
    """Template tag for greater than or equal comparison.

    Args:
        value: Value to compare
        arg: Comparison value

    Returns:
        bool: True if value >= arg

    """
    return value >= int(arg)


@register.simple_tag
def lte(value: Any, arg: Any) -> Any:
    """Template tag for less than or equal comparison.

    Args:
        value: Value to compare
        arg: Comparison value

    Returns:
        bool: True if value <= arg

    """
    return value <= int(arg)


@register.simple_tag
def length_gt(value: Any, arg: Any) -> Any:
    """Template tag for length greater than comparison.

    Args:
        value: Collection to check length
        arg: Length to compare against

    Returns:
        bool: True if len(value) > arg

    """
    return len(value) > int(arg)


@register.simple_tag
def length_lt(value: Any, arg: Any) -> Any:
    """Template tag for length less than comparison.

    Args:
        value: Collection to check length
        arg: Length to compare against

    Returns:
        bool: True if len(value) < arg

    """
    return len(value) < int(arg)


@register.simple_tag
def length_gte(value: Any, arg: Any) -> Any:
    """Template tag for length greater than or equal comparison.

    Args:
        value: Collection to check length
        arg: Length to compare against

    Returns:
        bool: True if len(value) >= arg

    """
    return len(value) >= int(arg)


@register.simple_tag
def length_lte(value: Any, arg: Any) -> Any:
    """Template tag for length less than or equal comparison.

    Args:
        value: Collection to check length
        arg: Length to compare against

    Returns:
        bool: True if len(value) <= arg

    """
    return len(value) <= int(arg)


@register.filter
def hex_to_rgb(hex_color: Any) -> Any:
    """Template filter to convert hex color to RGB values.

    Args:
        hex_color (str): Hex color string (e.g., '#FF0000')

    Returns:
        str: Comma-separated RGB values (e.g., '255,0,0'), or original value if invalid format

    """
    if not hex_color:
        return ""

    hex_without_hash = str(hex_color).lstrip("#")

    # Validate hex format: exactly 6 hexadecimal characters
    if not re.match(r"^[0-9A-Fa-f]{6}$", hex_without_hash):
        return hex_color  # Return original value if invalid format

    try:
        rgb_values = [str(int(hex_without_hash[i : i + 2], 16)) for i in (0, 2, 4)]
        return ",".join(rgb_values)
    except (ValueError, IndexError):
        return hex_color  # Return original value if conversion fails


@register.simple_tag
def define(val: Any = None) -> Any:
    """Template tag to define/store a value in templates.

    Args:
        val: Value to store

    Returns:
        any: The input value unchanged

    """
    return val


@register.filter(name="template_trans")
def template_trans(text: Any) -> Any:
    """Template filter for safe translation of text.

    Args:
        text (str): Text to translate

    Returns:
        str: Translated text or original text if translation fails

    """
    try:
        return _(text)
    except (TypeError, ValueError, AttributeError) as e:
        logger.debug("Translation failed for text: %s", e)
        return text


@register.simple_tag(takes_context=True)
def get_char_profile(context: Any, char: Any) -> Any:
    """Template tag to get character profile image URL.

    Args:
        context: Template context with features
        char (dict): Character data dictionary

    Returns:
        str: URL to character profile image or default avatar

    """
    if char.get("player_prof"):
        return char["player_prof"]
    if "cover" in context["features"]:
        if "cover_orig" in context and "cover" in char:
            return char["cover"]
        if "thumb" in char:
            return char["thumb"]
    return "/static/larpmanager/assets/blank-avatar.svg"


@register.simple_tag(takes_context=True)
def get_login_url(context: dict, provider: str, **params: Any) -> str:
    """Template tag to generate OAuth login URL with parameters.

    This function constructs a complete OAuth login URL by combining the provider's
    login endpoint with query parameters. It handles redirect URLs, scope, and
    authentication parameters while cleaning up empty values.

    Args:
        context: Template context dictionary containing the request object
        provider: OAuth provider name (e.g., 'google', 'facebook')
        **params: Additional URL parameters to include in the login URL

    Returns:
        Complete login URL with properly encoded query parameters

    Example:
        >>> get_login_url(context, 'google', scope='email', process='redirect')
        '/accounts/google/login/?scope=email&process=redirect&next=%2Fdashboard%2F'

    """
    request = context.get("request")
    query = dict(params)

    # Extract and validate authentication-specific parameters
    auth_params = query.get("auth_params")
    scope = query.get("scope")
    process = query.get("process")

    # Clean up empty string parameters to avoid cluttering the URL
    if scope == "":
        del query["scope"]
    if auth_params == "":
        del query["auth_params"]

    # Handle redirect URL logic based on current request and process type
    if REDIRECT_FIELD_NAME not in query:
        redirect = get_request_param(request, REDIRECT_FIELD_NAME)
        if redirect:
            query[REDIRECT_FIELD_NAME] = redirect
        elif process == "redirect":
            # Use current page as redirect target for redirect process
            query[REDIRECT_FIELD_NAME] = request.get_full_path()
    elif not query[REDIRECT_FIELD_NAME]:
        # Remove redirect field if it exists but is empty
        del query[REDIRECT_FIELD_NAME]

    # Construct the final URL with provider endpoint and encoded parameters
    url = reverse(provider + "_login")
    return url + "?" + urlencode(query)


@register.filter
def replace_underscore(value: Any) -> Any:
    """Template filter to replace underscores with spaces.

    Args:
        value (str): String to process

    Returns:
        str: String with underscores replaced by spaces

    """
    return value.replace("_", " ")


@register.filter
def remove(value: Any, args: Any) -> Any:
    """Template filter to remove specific text from string.

    Args:
        value (str): Source string
        args (str): Text to remove (underscores replaced with spaces)

    Returns:
        str: String with specified text removed (case-insensitive)

    """
    args = args.replace("_", " ")
    txt = re.sub(re.escape(args), "", value, flags=re.IGNORECASE)
    return txt.strip()


@register.simple_tag
def get_character_field(value: Any, options: Any) -> Any:
    """Template tag to format character field values using options.

    Args:
        value: Field value (string or list of indices)
        options (dict): Options mapping indices to data

    Returns:
        str: Formatted field value or comma-separated option names

    """
    if isinstance(value, str):
        return value
    result = []
    for idx in value:
        with contextlib.suppress(IndexError, KeyError, TypeError):
            result.append(options[idx]["name"])
    return ", ".join(result)


@register.filter
def format_decimal(decimal_value: Any) -> Any:
    """Template filter to format decimal values for display.

    Args:
        decimal_value: Numeric value to format

    Returns:
        str: Formatted decimal string, empty for zero, integer format when possible

    """
    try:
        rounded_value = round_to_nearest_cent(float(decimal_value))
        if rounded_value == 0:
            return ""
        if rounded_value == int(rounded_value):
            return str(int(rounded_value))
        return f"{rounded_value:.2f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return decimal_value


@register.filter
def get_attributes(obj: Any) -> dict[str, Any]:
    """Template filter to get object attributes as dictionary.

    Args:
        obj: Object to inspect

    Returns:
        dict: Dictionary of non-private attributes

    """
    return {k: v for k, v in vars(obj).items() if not k.startswith("_")}


@register.filter
def not_in(value: Any, arg: Any) -> Any:
    """Template filter to check if value is not in comma-separated list.

    Args:
        value: Value to check
        arg (str): Comma-separated list of values

    Returns:
        bool: True if value not in the list

    """
    return value not in arg.split(",")


@register.filter
def abs_value(value: Any) -> Any:
    """Template filter to get absolute value.

    Args:
        value: Numeric value

    Returns:
        Absolute value or original value if conversion fails

    """
    try:
        return abs(value)
    except (TypeError, ValueError):
        return value


@register.filter
def concat(val1: Any, val2: Any) -> str:
    """Template filter to concatenate two values.

    Args:
        val1: First value to concatenate
        val2: Second value to concatenate

    Returns:
        str: Concatenated string

    """
    return f"{val1}{val2}"
