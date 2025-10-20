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

import os
import re
from typing import Union

from allauth.utils import get_request_param
from django import template
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.db.models import Max
from django.templatetags.static import static
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.registration import round_to_nearest_cent
from larpmanager.models.association import get_url
from larpmanager.models.casting import Trait
from larpmanager.models.event import Run
from larpmanager.models.registration import Registration
from larpmanager.models.utils import strip_tags
from larpmanager.models.writing import Character, FactionType
from larpmanager.utils.common import html_clean
from larpmanager.utils.pdf import get_trait_character

register = template.Library()


@register.filter
def modulo(num: int, val: int) -> int:
    """Template filter to calculate modulo operation.

    Calculates the remainder when num is divided by val using the modulo operator.
    This function is typically used as a Django template filter to perform
    modulo operations in templates.

    Args:
        num: The dividend (number to be divided).
        val: The divisor (number to divide by).

    Returns:
        The remainder of the division operation.

    Raises:
        ZeroDivisionError: If val is zero.

    Examples:
        >>> modulo(10, 3)
        1
        >>> modulo(15, 4)
        3
    """
    # Perform modulo operation and return the remainder
    return num % val


@register.filter
def basename(value: str | None) -> str:
    """Template filter to extract basename from file path.

    Args:
        value: File path string or None.

    Returns:
        Basename of the file path (filename without directory),
        or empty string if value is None/empty.

    Example:
        >>> basename('/path/to/file.txt')
        'file.txt'
        >>> basename('')
        ''
        >>> basename(None)
        ''
    """
    # Handle None or empty string cases
    if not value:
        return ""

    # Extract and return the basename from the file path
    return os.path.basename(value)


@register.filter
def clean_tags(tx: str) -> str:
    """Template filter to clean HTML tags from text.

    Removes all HTML tags from the input text and replaces HTML line breaks
    with spaces for better readability in plain text contexts.

    Args:
        tx: Text string that may contain HTML tags and formatting.

    Returns:
        Clean text string with all HTML tags removed and line breaks
        converted to spaces.

    Example:
        >>> clean_tags("Hello<br />world<p>test</p>")
        "Hello world test"
    """
    # Replace HTML line breaks with spaces to maintain readability
    tx = tx.replace("<br />", " ")

    # Strip all remaining HTML tags from the text
    return strip_tags(tx)


@register.filter
def get(value: dict, arg: str) -> any:
    """Template filter to get dictionary value by key.

    Args:
        value: Dictionary to look up
        arg: Key to retrieve

    Returns:
        Dictionary value for key, or empty string if not found

    Examples:
        >>> get({'a': 1, 'b': 2}, 'a')
        1
        >>> get({'a': 1}, 'c')
        ''
        >>> get(None, 'a')
        ''
    """
    # Check if arg is provided and value is a valid dictionary
    if arg is not None and value and arg in value:
        return value[arg]

    # Return empty string if key not found or invalid input
    return ""


def get_tooltip(context: dict, ch: dict) -> str:
    """Generate HTML tooltip for character display.

    Creates an HTML tooltip containing character avatar and details for use in
    character display components. The tooltip includes the character's profile
    image (or default avatar), faction information, and teaser text if available.

    Args:
        context (dict): Template context containing rendering data and utilities
        ch (dict): Character data dictionary containing player info, faction data,
                  teaser text, and other character details

    Returns:
        str: Complete HTML string for character tooltip with avatar image,
             faction details, and teaser text formatted for display
    """
    # Set default avatar or use player profile image if available
    avat = static("larpmanager/assets/blank-avatar.svg")
    if "player_id" in ch and ch["player_id"] > 0 and ch["player_prof"]:
        avat = ch["player_prof"]

    # Initialize tooltip with avatar image
    tooltip = f"<img src='{avat}'>"

    # Add character field information to tooltip
    tooltip = tooltip_fields(ch, tooltip)

    # Add faction information with context processing
    tooltip = tooltip_factions(ch, context, tooltip)

    # Append teaser text if present, with character replacement
    if ch["teaser"]:
        tooltip += "<span class='teaser'>" + replace_chars(context, ch["teaser"]) + " (...)</span>"

    return tooltip


def tooltip_fields(ch: dict, tooltip: str) -> str:
    """Add character name, title, and player information to tooltip.

    Builds an HTML tooltip by appending character information including name,
    title, pronouns, and player details to an existing tooltip string.

    Args:
        ch: Character data dictionary containing name, title, pronoun,
            player_id, and player_full fields
        tooltip: Current tooltip HTML string to append to

    Returns:
        Updated tooltip HTML string with character fields appended

    Example:
        >>> ch = {'name': 'John', 'title': 'Knight', 'pronoun': 'he/him'}
        >>> tooltip_fields(ch, '<div>')
        '<div><span><b class="name">John</b> - <b class="title">Knight</b> (he/him)</span>'
    """
    # Start building character name section with bold formatting
    tooltip += f"<span><b class='name'>{ch['name']}</b>"

    # Add character title if present
    if ch["title"]:
        tooltip += " - <b class='title'>" + ch["title"] + "</b>"

    # Add pronouns in parentheses if available
    if "pronoun" in ch and ch["pronoun"]:
        tooltip += " (" + ch["pronoun"] + ")"

    tooltip += "</span>"

    # Add player information if player_id exists and is valid
    if "player_id" in ch and ch["player_id"] > 0:
        tooltip += "<span>" + _("Player") + ": <b>" + ch["player_full"] + "</b></span>"

    return tooltip


def tooltip_factions(ch: dict, context: dict, tooltip: str) -> str:
    """Add faction information to character tooltip.

    Processes faction data from context and appends visible faction names
    to the character tooltip. Secret factions are excluded from display.

    Args:
        ch: Character data dictionary containing faction memberships
        context: Template context containing faction data indexed by faction number
        tooltip: Current tooltip HTML string to be extended

    Returns:
        Updated tooltip HTML string with faction information appended
    """
    factions = ""

    # Iterate through all available factions in context
    for fnum in context["factions"]:
        el = context["factions"][fnum]

        # Skip secret factions - they should not be visible in tooltips
        if el["typ"] == FactionType.SECRET:
            continue

        # Check if character belongs to this faction
        if fnum in ch["factions"]:
            # Add comma separator between multiple factions
            if factions:
                factions += ", "
            factions += el["name"]

    # Append faction information to tooltip if any factions found
    if factions:
        tooltip += "<span>" + _("Factions") + ": " + factions + "</span>"

    return tooltip


@register.simple_tag(takes_context=True)
def replace_chars(context: dict, el: str, limit: int = 200) -> str:
    """Template tag to replace character number references with names.

    Replaces character references in text using the following patterns:
    - #XX: Full character name
    - @XX: Full character name
    - ^XX: First name only

    Args:
        context: Template context dictionary containing:
            - max_ch_number: Maximum character number to check
            - chars: Dictionary mapping character numbers to character data
        el: Input text containing character references to replace
        limit: Maximum length of returned text after replacements

    Returns:
        Processed text with character references replaced by names,
        truncated to the specified limit
    """
    # Clean HTML from input text
    el = html_clean(el)

    # Iterate through character numbers from highest to lowest
    # This prevents issues with overlapping replacements (e.g., #1 and #10)
    for number in range(context["max_ch_number"], 0, -1):
        # Skip if character number doesn't exist in context
        if number not in context["chars"]:
            continue

        # Get full character name for replacements
        lk = context["chars"][number]["name"]

        # Replace # and @ patterns with full character name
        el = el.replace(f"#{number}", lk)
        el = el.replace(f"@{number}", lk)

        # Extract first name for ^ pattern replacement
        lk = lk.split()
        if lk:
            lk = lk[0]
            el = el.replace(f"^{number}", lk)

    # Return truncated result
    return el[:limit]


def go_character(context: dict, search: str, number: int, tx: str, run, go_tooltip: bool, simple: bool = False) -> str:
    """Replace character reference with formatted link or name.

    Processes text containing character references (like '#1', '@1', '^1') and replaces
    them with either formatted HTML links or simple bold names, depending on the simple
    parameter. Optionally includes tooltips for character information.

    Args:
        context: Template context dictionary containing character data under 'chars' key.
        search: Pattern to search for in the text (e.g., '#1', '@1', '^1').
        number: Character number/ID to look up in the context chars dictionary.
        tx: Input text that may contain the search pattern to be replaced.
        run: Run instance used for generating character URLs via get_slug() method.
        go_tooltip: If True, includes hover tooltip with character information.
        simple: If True, returns character name in bold; if False, returns clickable link.

    Returns:
        The input text with character references replaced by formatted HTML, or
        unchanged text if search pattern not found or character data unavailable.

    Example:
        >>> go_character(ctx, '#1', 1, 'See character #1', run_obj, True, False)
        'See character <a class="link_show_char" href="/run/char/1">John Doe</a>'
    """
    # Early return if search pattern not in text
    if search not in tx:
        return tx

    # Check if character data exists in context
    if "chars" not in context:
        return tx

    # Verify specific character number exists
    if number not in context["chars"]:
        return tx

    # Get character data from context
    ch = context["chars"][number]

    # Generate character URL using run slug and character number
    r = get_url(
        reverse("character", args=[run.get_slug(), ch["number"]]),
        context["assoc_slug"],
    ).replace('"', "")

    # Create either simple bold name or full link based on simple flag
    if simple:
        lk = f"<b>{ch['name'].split()[0]}</b>"
    else:
        lk = f"<a class='link_show_char' href='{r}'>{ch['name']}</a>"

        # Add tooltip wrapper if tooltips are enabled
        if go_tooltip:
            tooltip = get_tooltip(context, ch)
            lk = "<span class='has_show_char'>" + lk + f"</span><span class='hide show_char'>{tooltip}</span>"

    # Replace search pattern with generated link/name
    return tx.replace(search, lk)


def _remove_unimportant_prefix(text: str) -> str:
    """Remove first occurrence of $unimportant from text and clean up empty HTML tags at start.

    This function removes the first occurrence of the '$unimportant' marker from the input text.
    If the marker was found and removed, it additionally cleans up any empty HTML tags
    that appear at the beginning of the resulting text.

    Args:
        text: Text that may contain $unimportant prefix to be removed.

    Returns:
        Text with first occurrence of $unimportant removed and empty HTML tags cleaned up.
        Returns the original text unchanged if it's empty or None.

    Example:
        >>> _remove_unimportant_prefix("$unimportant<p></p>Hello")
        "Hello"
        >>> _remove_unimportant_prefix("Normal text")
        "Normal text"
    """
    # Early return for empty or None input
    if not text:
        return text

    # Store original text to check if replacement occurred
    original_text = text

    # Remove first occurrence of the $unimportant marker
    text = text.replace("$unimportant", "", 1)

    # Only clean up empty HTML tags if $unimportant was actually removed
    if text != original_text:
        # Iteratively remove empty HTML tags and whitespace from the beginning
        while True:
            # Strip leading whitespace for pattern matching
            stripped = text.lstrip()

            # Match empty HTML tags like <p></p>, <div></div>, <span></span>, etc.
            # Also handles whitespace, &nbsp;, \r, \n inside the tags
            match = re.match(r"^<(\w+)(?:\s[^>]*)?>(?:\s|&nbsp;|\r|\n)*</\1>", stripped)

            if match:
                # Remove the matched empty tag and continue searching
                text = stripped[match.end() :]
            else:
                # No more empty tags found, use stripped text and exit loop
                text = stripped
                break

    return text


@register.simple_tag(takes_context=True)
def show_char(context: dict, el: Union[dict, str, None], run: Run, tooltip: bool) -> str:
    """Template tag to process text and convert character references to links.

    Processes text content and converts character reference patterns (#XX, @XX, ^XX)
    into clickable links. Handles both string and dictionary inputs, and manages
    character number context for efficient processing.

    Args:
        context: Template rendering context dictionary containing shared state
        el: Text element to process - can be string, dict with 'text' key, or None
        run: Run instance used for character lookup and event access
        tooltip: Whether to include interactive character tooltips in generated links

    Returns:
        Safe HTML string with character references converted to clickable links
    """
    # Extract text content from input element
    if isinstance(el, dict) and "text" in el:
        tx = el["text"] + " "
    elif el is not None:
        tx = str(el) + " "
    else:
        tx = ""

    # Cache maximum character number for efficient range processing
    if "max_ch_number" not in context:
        context["max_ch_number"] = run.event.get_elements(Character).aggregate(Max("number"))["number__max"]

    # Handle case where no characters exist in the event
    if not context["max_ch_number"]:
        context["max_ch_number"] = 0

    # Process character references in descending order to avoid conflicts
    # #XX creates relationships/counts as character in faction/plot
    # @XX creates standard character references
    # ^XX creates simple character references without full processing
    for number in range(context["max_ch_number"], 0, -1):
        tx = go_character(context, f"#{number}", number, tx, run, tooltip)
        tx = go_character(context, f"@{number}", number, tx, run, tooltip)
        tx = go_character(context, f"^{number}", number, tx, run, tooltip, simple=True)

    # Clean up unimportant tags by removing $unimportant prefix
    tx = _remove_unimportant_prefix(tx)

    return mark_safe(tx)


def go_trait(context: dict, search: str, number: int, tx: str, run, go_tooltip: bool, simple: bool = False) -> str:
    """Replace trait reference with character link.

    Searches for a pattern in text and replaces it with either a character name
    or a clickable link to the character page, depending on the simple flag.

    Args:
        context: Template context dictionary containing trait and character data
        search: Pattern string to search for in the text
        number: Trait number identifier to look up the associated character
        tx: Input text containing the search pattern to be replaced
        run: Run instance used for character lookup operations
        go_tooltip: Whether to include hover tooltip in the generated link
        simple: If True, returns bold character name; if False, returns full HTML link

    Returns:
        Modified text string with trait reference replaced by character link or name,
        or original text if pattern not found or character data unavailable
    """
    # Early return if search pattern not found in text
    if search not in tx:
        return tx

    # Initialize traits cache if not present in context
    if "traits" not in context:
        context["traits"] = {}

    # Get character number from cached traits or fetch from database
    if number in context["traits"]:
        ch_number = context["traits"][number]["char"]
    else:
        char = get_trait_character(run, number)
        if not char:
            return tx
        ch_number = char.number

    # Verify character exists in context data
    if ch_number not in context["chars"]:
        return tx

    # Get character data from context
    ch = context["chars"][ch_number]

    # Generate appropriate output based on simple flag
    if simple:
        # Simple mode: return bold first name only
        lk = f"<b>{ch['name'].split()[0]}</b>"
    else:
        # Full mode: generate clickable link with optional tooltip
        tooltip = ""
        if go_tooltip:
            tooltip = get_tooltip(context, ch)

        # Build character page URL
        r = get_url(
            reverse("character", args=[run.get_slug(), ch["number"]]),
            context["slug"],
        )

        # Create HTML link with hover functionality
        lk = (
            f"<span class='has_show_char'><a href='{r}'>{ch['name']}</a></span>"
            f"<span class='hide show_char'>{tooltip}</span>"
        )

    # Replace search pattern with generated link/name
    return tx.replace(search, lk)


@register.simple_tag(takes_context=True)
def show_trait(context: dict, tx: str, run, tooltip: bool) -> str:
    """Template tag to process text and convert trait references to character links.

    Processes text containing trait references (marked with #, @, or ^ prefixes) and
    converts them to HTML links pointing to character pages. The function handles
    three types of trait references with different formatting options.

    Args:
        context (dict): Template context containing cached trait data
        tx (str): Text containing trait references to be processed
        run: Run instance used for trait lookup and character resolution
        tooltip (bool): Whether to include character tooltips in generated links

    Returns:
        str: Safe HTML string with trait references converted to character links
    """
    # Initialize max_trait in context if not already present
    if "max_trait" not in context:
        context["max_trait"] = Trait.objects.filter(event_id=run.event_id).aggregate(Max("number"))["number__max"]

    # Set default value if no traits exist
    if not context["max_trait"]:
        context["max_trait"] = 0

    # Process trait references in descending order to avoid partial replacements
    # replace #XX (create relationships / count as character in faction / plot)
    for number in range(context["max_trait"], 0, -1):
        # Process standard trait reference (#XX)
        tx = go_trait(context, f"#{number}", number, tx, run, tooltip)

        # Process alternate trait reference (@XX)
        tx = go_trait(context, f"@{number}", number, tx, run, tooltip)

        # Process simple trait reference (^XX) with simplified formatting
        tx = go_trait(context, f"^{number}", number, tx, run, tooltip, simple=True)

    return mark_safe(tx)


@register.simple_tag
def key(d: dict, key_name: any, s_key_name: any = None) -> any:
    """Template tag to safely get dictionary value by key.

    Safely retrieves a value from a dictionary using a primary key and an optional
    secondary key. If the secondary key is provided, it's concatenated with the
    primary key using an underscore separator.

    Args:
        d: Dictionary to look up values from.
        key_name: Primary key name to search for in the dictionary.
        s_key_name: Optional secondary key to append to the primary key
            with underscore separator. Defaults to None.

    Returns:
        The value associated with the key if found, otherwise an empty string.

    Examples:
        >>> data = {'user_id': 123, 'name': 'John'}
        >>> key(data, 'user', 'id')
        123
        >>> key(data, 'name')
        'John'
        >>> key(data, 'missing')
        ''
    """
    # Return empty string if no primary key provided
    if not key_name:
        return ""

    # Concatenate primary and secondary keys if both exist
    if s_key_name:
        key_name = str(key_name) + "_" + str(s_key_name)

    # Try direct key lookup first (preserves original key type)
    if key_name in d:
        return d[key_name]

    # Fallback to string conversion of key for lookup
    key_name = str(key_name)
    if key_name in d:
        return d[key_name]
    else:
        return ""


@register.simple_tag
def get_field(form: object, name: str) -> object:
    """Template tag to safely get form field by name.

    This function provides safe access to Django form fields by name,
    returning an empty string if the field doesn't exist to prevent
    template rendering errors.

    Args:
        form: Django form instance containing the fields to search
        name: The name of the field to retrieve from the form

    Returns:
        The form field object if found, otherwise an empty string

    Example:
        >>> field = get_field(my_form, 'username')
        >>> if field:
        ...     # Field exists and can be rendered
        ...     pass
    """
    # Check if the requested field name exists in the form
    if name in form:
        # Return the field object for template rendering
        return form[name]

    # Return empty string to prevent template errors when field doesn't exist
    return ""


@register.simple_tag(takes_context=True)
def get_field_show_char(context: dict, form: object, name: str, run: object, tooltip: bool) -> str:
    """Template tag to get form field and process character references.

    Retrieves a form field by name and processes it through the show_char
    function to generate character links with optional tooltips.

    Args:
        context: Template context dictionary containing request and other data
        form: Django form instance containing the field to retrieve
        name: Field name to retrieve from the form
        run: Run instance used for character processing and link generation
        tooltip: Whether to include tooltips in the generated character links

    Returns:
        Processed field value with character links as HTML string, or empty
        string if field not found in form

    Example:
        >>> get_field_show_char(context, form, 'description', run, True)
        '<a href="/character/1">John Doe</a>'
    """
    # Check if the requested field exists in the form
    if name in form:
        # Retrieve the form field value
        v = form[name]

        # Process the field value through show_char to generate character links
        return show_char(context, v, run, tooltip)

    # Return empty string if field is not found in the form
    return ""


@register.simple_tag
def get_deep_field(form: dict | object, key1: str, key2: str) -> str:
    """Template tag to get nested form field value.

    Safely retrieves a nested value from a form dictionary or object
    using two-level key access. Returns empty string if any key is missing.

    Args:
        form: Form dictionary or object containing nested data
        key1: First level key to access in the form
        key2: Second level key to access within the first level

    Returns:
        The nested value if found, otherwise empty string

    Example:
        >>> form_data = {'field1': {'subfield': 'value'}}
        >>> get_deep_field(form_data, 'field1', 'subfield')
        'value'
        >>> get_deep_field(form_data, 'missing', 'key')
        ''
    """
    # Check if first level key exists in form
    if key1 in form:
        # Check if second level key exists within first level
        if key2 in form[key1]:
            return form[key1][key2]

    # Return empty string if any key is missing
    return ""


@register.filter
def get_form_field(form: object, name: str) -> object:
    """Template filter to get form field by name.

    This function safely retrieves a field from a Django form by name,
    returning an empty string if the field doesn't exist to prevent
    template rendering errors.

    Args:
        form: Django form instance containing the fields
        name: Field name to retrieve from the form

    Returns:
        Form field object if found, empty string otherwise

    Example:
        >>> field = get_form_field(my_form, 'username')
        >>> if field:
        ...     # Field exists and can be rendered
        ...     pass
    """
    # Check if the requested field name exists in the form's fields
    if name in form.fields:
        # Return the bound field which can be rendered in templates
        return form[name]

    # Return empty string to prevent template errors when field doesn't exist
    return ""


@register.simple_tag
def lookup(obj: object, prop: str) -> any:
    """Template tag to safely get object attribute.

    Safely retrieves an attribute from an object, returning the value if it exists
    and is truthy, otherwise returns an empty string. This is commonly used in
    Django templates to avoid AttributeError exceptions.

    Args:
        obj: The object to inspect for the specified attribute.
        prop: The name of the property/attribute to retrieve from the object.

    Returns:
        The value of the attribute if it exists and is truthy, otherwise an
        empty string.

    Example:
        >>> class MyObj:
        ...     def __init__(self):
        ...         self.name = "test"
        >>> obj = MyObj()
        >>> lookup(obj, "name")
        'test'
        >>> lookup(obj, "nonexistent")
        ''
    """
    # Check if the object has the requested attribute
    if hasattr(obj, prop):
        # Get the attribute value using getattr
        value = getattr(obj, prop)

        # Return value only if it's truthy (not None, empty string, etc.)
        if value:
            return value

    # Return empty string as fallback for missing or falsy attributes
    return ""


@register.simple_tag
def get_registration_option(reg: Registration, number: int) -> str:
    """Template tag to get registration option form text.

    Retrieves the form text for a specific registration option by its number.
    If the option exists and has form text, returns it; otherwise returns empty string.

    Args:
        reg: Registration instance containing the options
        number: Option number to retrieve (1-based indexing)

    Returns:
        Option form text if available, empty string otherwise

    Example:
        >>> get_registration_option(registration, 1)
        'Please select your meal preference'
    """
    # Get the option attribute dynamically using the number
    v = getattr(reg, f"option_{number}")

    # Check if option exists and return its form text
    if v:
        return v.get_form_text()

    # Return empty string if option doesn't exist
    return ""


@register.simple_tag
def gt(value: int | float, arg: str) -> bool:
    """Template tag for greater than comparison.

    Args:
        value: The numeric value to compare against the argument.
        arg: The comparison value as a string that will be converted to integer.

    Returns:
        True if value is greater than the integer conversion of arg, False otherwise.

    Example:
        >>> gt(5, "3")
        True
        >>> gt(2, "5")
        False
    """
    # Convert string argument to integer for comparison
    return value > int(arg)


@register.simple_tag
def lt(value: int | float, arg: str) -> bool:
    """Template tag for less than comparison.

    Compares a numeric value with a string representation of a number
    to determine if the value is less than the converted argument.

    Args:
        value (int | float): The numeric value to compare.
        arg (str): String representation of the comparison value.

    Returns:
        bool: True if value is less than the integer conversion of arg,
              False otherwise.

    Example:
        >>> lt(5, "10")
        True
        >>> lt(15, "10")
        False
    """
    # Convert string argument to integer for comparison
    comparison_value = int(arg)

    # Perform less than comparison
    return value < comparison_value


@register.simple_tag
def gte(value: int | float, arg: str) -> bool:
    """Template tag for greater than or equal comparison.

    Compares a numeric value against a string argument that represents an integer.
    The argument is converted to an integer before comparison.

    Args:
        value (int | float): The numeric value to compare.
        arg (str): String representation of the comparison value that will be
                  converted to an integer.

    Returns:
        bool: True if value is greater than or equal to the integer conversion
              of arg, False otherwise.

    Example:
        >>> gte(5, "3")
        True
        >>> gte(2, "5")
        False
    """
    # Convert string argument to integer for comparison
    comparison_value = int(arg)

    # Return the result of greater than or equal comparison
    return value >= comparison_value


@register.simple_tag
def lte(value, arg) -> bool:
    """Template tag for less than or equal comparison.

    Compares two values using the less than or equal operator. The second
    argument is automatically converted to an integer for comparison.

    Args:
        value: The left operand value to compare (can be any numeric type)
        arg: The right operand value to compare (will be converted to int)

    Returns:
        True if value is less than or equal to the integer conversion of arg,
        False otherwise

    Example:
        >>> lte(5, "10")
        True
        >>> lte(15, "10")
        False
    """
    # Convert the comparison argument to integer for consistent comparison
    comparison_value = int(arg)

    # Perform the less than or equal comparison
    return value <= comparison_value


@register.simple_tag
def length_gt(value: object, arg: str) -> bool:
    """Template tag for length greater than comparison.

    Compares the length of a collection against a specified threshold value.
    Used in Django templates to check if a collection has more items than
    a given number.

    Args:
        value: Collection to check length (list, tuple, string, etc.)
        arg: String representation of the length to compare against

    Returns:
        True if len(value) > arg, False otherwise

    Examples:
        >>> length_gt([1, 2, 3], "2")
        True
        >>> length_gt("hello", "10")
        False
    """
    # Convert string argument to integer for comparison
    threshold = int(arg)

    # Compare collection length against threshold
    return len(value) > threshold


@register.simple_tag
def length_lt(value, arg):
    """Template tag for length less than comparison.

    Compares the length of a collection against a specified threshold value.
    Used in Django templates to conditionally display content based on
    collection size.

    Args:
        value: Collection to check length (list, tuple, string, etc.)
        arg: Length threshold to compare against (string or integer)

    Returns:
        bool: True if len(value) < arg, False otherwise

    Example:
        >>> length_lt([1, 2, 3], "5")
        True
        >>> length_lt("hello", "3")
        False
    """
    # Convert the argument to integer for comparison
    threshold = int(arg)

    # Compare collection length against threshold
    return len(value) < threshold


@register.simple_tag
def length_gte(value, arg) -> bool:
    """Template tag for length greater than or equal comparison.

    Args:
        value: Collection to check length (any object with __len__ method)
        arg: Length to compare against (string or integer)

    Returns:
        True if len(value) >= arg, False otherwise

    Raises:
        TypeError: If value doesn't have __len__ method
        ValueError: If arg cannot be converted to integer
    """
    # Convert argument to integer for comparison
    threshold = int(arg)

    # Compare collection length against threshold
    return len(value) >= threshold


@register.simple_tag
def length_lte(value, arg) -> bool:
    """Template tag for length less than or equal comparison.

    Compares the length of a collection against a numeric threshold value.
    Useful in Django templates for conditional rendering based on collection size.

    Args:
        value: Collection object (list, tuple, string, etc.) to check length of.
            Must support len() function.
        arg: Length threshold to compare against. Will be converted to integer.

    Returns:
        bool: True if the length of value is less than or equal to arg,
            False otherwise.

    Example:
        >>> length_lte([1, 2, 3], 5)
        True
        >>> length_lte("hello", 3)
        False
    """
    # Convert argument to integer for comparison
    threshold = int(arg)

    # Compare collection length against threshold
    return len(value) <= threshold


@register.filter
def hex_to_rgb(value: str) -> str:
    """Template filter to convert hex color to RGB values.

    Converts a hexadecimal color string to comma-separated RGB values.
    Handles colors with or without the '#' prefix.

    Args:
        value: Hex color string (e.g., '#FF0000' or 'FF0000')

    Returns:
        Comma-separated RGB values as string (e.g., '255,0,0')

    Example:
        >>> hex_to_rgb('#FF0000')
        '255,0,0'
        >>> hex_to_rgb('00FF00')
        '0,255,0'
    """
    # Remove the '#' prefix if present
    h = value.lstrip("#")

    # Convert each pair of hex digits to decimal and format as string
    # Extract pairs at positions 0-1, 2-3, 4-5 for R, G, B respectively
    h = [str(int(h[i : i + 2], 16)) for i in (0, 2, 4)]

    # Join RGB values with commas
    return ",".join(h)


@register.simple_tag
def define(val: any = None) -> any:
    """Template tag to define/store a value in templates.

    This function serves as a simple passthrough utility for Django templates,
    allowing template authors to store and reference values within template context.

    Args:
        val: The value to store and return. Can be of any type.
            Defaults to None if not provided.

    Returns:
        The input value unchanged, maintaining its original type and content.

    Example:
        In Django templates:
        {% define "some_value" as stored_val %}
        {{ stored_val }}  <!-- outputs: some_value -->
    """
    # Return the input value without any modification
    return val


@register.filter(name="template_trans")
def template_trans(text: str) -> str:
    """Template filter for safe translation of text.

    This function safely translates text using Django's translation system.
    If translation fails, it returns the original text unchanged to prevent
    template rendering errors.

    Args:
        text: The text string to be translated.

    Returns:
        The translated text if successful, otherwise the original text.

    Example:
        >>> template_trans("Hello")
        "Ciao"  # If Italian is the active language
    """
    try:
        # Attempt to translate the text using Django's translation function
        return _(text)
    except Exception as e:
        # Log the exception for debugging purposes
        print(e)
        # Return original text if translation fails to prevent template errors
        return text


@register.simple_tag(takes_context=True)
def get_char_profile(context: dict, char: dict) -> str:
    """Template tag to get character profile image URL.

    Args:
        context: Template context dictionary containing features and other data
        char: Character data dictionary with profile and image information

    Returns:
        URL string to character profile image or default avatar if none found

    Note:
        Priority order: player_prof -> cover (if feature enabled) -> thumb -> default avatar
    """
    # Check if player profile image is available and set
    if "player_prof" in char and char["player_prof"]:
        return char["player_prof"]

    # Check if cover feature is enabled in context
    if "cover" in context["features"]:
        # Prefer original cover if available in context and character
        if "cover_orig" in context and "cover" in char:
            return char["cover"]
        # Fall back to thumbnail if available
        elif "thumb" in char:
            return char["thumb"]

    # Return default avatar as final fallback
    return "/static/larpmanager/assets/blank-avatar.svg"


@register.simple_tag(takes_context=True)
def get_login_url(context: dict, provider: str, **params) -> str:
    """Template tag to generate OAuth login URL with parameters.

    Generates a complete OAuth login URL for the specified provider, handling
    query parameters, redirects, and authentication scope configuration.

    Args:
        context: Template context dictionary containing the request object
        provider: OAuth provider name (e.g., 'google', 'facebook')
        **params: Additional URL parameters including:
            - auth_params: Authentication parameters string
            - scope: OAuth scope specification
            - process: Process type ('redirect' for auto-redirect)

    Returns:
        Complete login URL with properly encoded query parameters

    Example:
        >>> get_login_url({'request': request}, 'google', scope='email')
        '/auth/google/login/?scope=email&next=/dashboard/'
    """
    # Extract request object from template context
    request = context.get("request")
    query = dict(params)

    # Extract and validate OAuth-specific parameters
    auth_params = query.get("auth_params", None)
    scope = query.get("scope", None)
    process = query.get("process", None)

    # Clean up empty OAuth parameters to avoid malformed URLs
    if scope == "":
        del query["scope"]
    if auth_params == "":
        del query["auth_params"]

    # Handle redirect URL configuration based on request context
    if REDIRECT_FIELD_NAME not in query:
        # Try to get redirect from request parameters first
        redirect = get_request_param(request, REDIRECT_FIELD_NAME)
        if redirect:
            query[REDIRECT_FIELD_NAME] = redirect
        # For redirect process, use current page as redirect target
        elif process == "redirect":
            query[REDIRECT_FIELD_NAME] = request.get_full_path()
    # Remove empty redirect parameters to clean up URL
    elif not query[REDIRECT_FIELD_NAME]:
        del query[REDIRECT_FIELD_NAME]

    # Build final URL with provider endpoint and encoded query parameters
    url = reverse(provider + "_login")
    url = url + "?" + urlencode(query)
    return url


@register.filter
def replace_underscore(value: str) -> str:
    """Template filter to replace underscores with spaces.

    This function is typically used as a Django template filter to convert
    underscore-separated strings into human-readable format by replacing
    all underscore characters with spaces.

    Args:
        value: The input string containing underscores to be replaced.

    Returns:
        A new string with all underscore characters replaced by spaces.

    Example:
        >>> replace_underscore("hello_world_test")
        "hello world test"
    """
    # Replace all underscore characters with spaces
    return value.replace("_", " ")


@register.filter
def remove(value: str, args: str) -> str:
    """Template filter to remove specific text from string.

    This filter performs case-insensitive removal of specified text from a source
    string. Underscores in the removal argument are automatically converted to spaces
    to allow for more flexible template usage.

    Args:
        value: The source string from which text will be removed.
        args: The text pattern to remove. Underscores are replaced with spaces
              before matching.

    Returns:
        The source string with all occurrences of the specified text removed,
        with leading/trailing whitespace stripped.

    Example:
        >>> remove("Hello World Test", "world")
        "Hello  Test"
        >>> remove("Remove_this_text", "this_text")
        "Remove_"
    """
    # Convert underscores to spaces for more flexible matching
    args = args.replace("_", " ")

    # Remove all occurrences of the specified text (case-insensitive)
    txt = re.sub(re.escape(args), "", value, flags=re.IGNORECASE)

    # Strip leading/trailing whitespace and return result
    return txt.strip()


@register.simple_tag
def get_character_field(value: str | list[int], options: dict[int, dict[str, str]]) -> str:
    """Template tag to format character field values using options.

    This function handles both string values (returned as-is) and lists of indices
    that are mapped to option names from the provided options dictionary.

    Args:
        value: Field value, either a string to return directly or a list of
               integer indices to map to option names
        options: Dictionary mapping integer indices to option data dictionaries,
                where each option dict contains at least a 'name' key

    Returns:
        Formatted field value as a string. For string inputs, returns the input
        unchanged. For list inputs, returns comma-separated option names.

    Example:
        >>> options = {0: {"name": "Option A"}, 1: {"name": "Option B"}}
        >>> get_character_field([0, 1], options)
        'Option A, Option B'
        >>> get_character_field("Simple text", options)
        'Simple text'
    """
    # Return string values unchanged
    if isinstance(value, str):
        return value

    # Process list of indices to extract option names
    result = []
    for idx in value:
        try:
            # Attempt to get option name from the options dictionary
            result.append(options[idx]["name"])
        except (IndexError, KeyError, TypeError):
            # Skip invalid indices or malformed option entries
            pass

    # Join all valid option names with commas
    return ", ".join(result)


@register.filter
def format_decimal(value) -> str:
    """Template filter to format decimal values for display.

    Formats numeric values by rounding to nearest cent, removing trailing zeros,
    and handling special cases for zero values and integers.

    Args:
        value: Numeric value to format (int, float, Decimal, or string convertible to float)

    Returns:
        str: Formatted decimal string. Returns empty string for zero values,
             integer format when decimal part is zero, otherwise formatted
             with up to 2 decimal places with trailing zeros removed.

    Examples:
        >>> format_decimal(0)
        ''
        >>> format_decimal(5.0)
        '5'
        >>> format_decimal(5.50)
        '5.5'
        >>> format_decimal(5.123)
        '5.12'
    """
    try:
        # Round to nearest cent using existing utility function
        rounded = round_to_nearest_cent(float(value))

        # Return empty string for zero values
        if rounded == 0:
            return ""

        # Return integer format if no decimal part
        if rounded == int(rounded):
            return str(int(rounded))

        # Format with 2 decimals and strip trailing zeros and decimal point
        return f"{rounded:.2f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        # Return original value if conversion fails
        return value


@register.filter
def get_attributes(obj: object) -> dict[str, any]:
    """Template filter to get object attributes as dictionary.

    Extracts all non-private attributes from an object and returns them
    as a dictionary. Private attributes (those starting with underscore)
    are excluded from the result.

    Args:
        obj: The object to inspect for attributes.

    Returns:
        A dictionary mapping attribute names to their values, excluding
        private attributes (those starting with '_').

    Example:
        >>> class Example:
        ...     def __init__(self):
        ...         self.public = 'value'
        ...         self._private = 'hidden'
        >>> get_attributes(Example())
        {'public': 'value'}
    """
    # Extract all object attributes and filter out private ones
    return {k: v for k, v in vars(obj).items() if not k.startswith("_")}


@register.filter
def not_in(value: any, arg: str) -> bool:
    """Template filter to check if value is not in comma-separated list.

    Args:
        value: Value to check for presence in the list
        arg: Comma-separated string of values to check against

    Returns:
        True if value is not found in the comma-separated list, False otherwise

    Example:
        >>> not_in('apple', 'banana,orange,grape')
        True
        >>> not_in('banana', 'banana,orange,grape')
        False
    """
    # Split the comma-separated string into individual values
    values_list = arg.split(",")

    # Check if the input value is not present in the list
    return value not in values_list


@register.filter
def abs_value(value: float | int) -> float | int:
    """Template filter to get absolute value.

    Args:
        value: Numeric value to get absolute value of.

    Returns:
        The absolute value of the input if it's numeric, otherwise returns
        the original value unchanged.

    Raises:
        None: Errors are caught and handled gracefully by returning the
        original value.
    """
    try:
        # Attempt to calculate absolute value for numeric types
        return abs(value)
    except (TypeError, ValueError):
        # Return original value if conversion fails (non-numeric types)
        return value


@register.filter
def concat(val1: str, val2: str) -> str:
    """Template filter to concatenate two values.

    Args:
        val1: First value to concatenate.
        val2: Second value to concatenate.

    Returns:
        Concatenated string of val1 and val2.

    Example:
        >>> concat("hello", "world")
        'helloworld'
    """
    # Concatenate the two values using f-string formatting
    return f"{val1}{val2}"
