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
from larpmanager.models.utils import strip_tags
from larpmanager.models.writing import Character, FactionType
from larpmanager.utils.common import html_clean
from larpmanager.utils.pdf import get_trait_character

register = template.Library()


@register.filter
def modulo(num, val):
    """Template filter to calculate modulo operation.

    Args:
        num (int): Number to divide
        val (int): Divisor

    Returns:
        int: Remainder of num divided by val
    """
    return num % val


@register.filter
def basename(value):
    """Template filter to extract basename from file path.

    Args:
        value (str): File path

    Returns:
        str: Basename of the file path (filename without directory)
    """
    if not value:
        return ""
    return os.path.basename(value)


@register.filter
def clean_tags(tx):
    """Template filter to clean HTML tags from text.

    Args:
        tx (str): Text containing HTML tags

    Returns:
        str: Text with HTML tags removed and br tags replaced with spaces
    """
    tx = tx.replace("<br />", " ")
    return strip_tags(tx)


@register.filter
def get(value, arg):
    """Template filter to get dictionary value by key.

    Args:
        value (dict): Dictionary to look up
        arg (str): Key to retrieve

    Returns:
        any: Dictionary value for key, or empty string if not found
    """
    if arg is not None and value and arg in value:
        return value[arg]
    return ""


def get_tooltip(context, ch):
    """Generate HTML tooltip for character display.

    Args:
        context: Template context
        ch (dict): Character data dictionary

    Returns:
        str: HTML string for character tooltip with avatar and details
    """
    avat = static("larpmanager/assets/blank-avatar.svg")
    if "player_id" in ch and ch["player_id"] > 0 and ch["player_prof"]:
        avat = ch["player_prof"]
    tooltip = f"<img src='{avat}'>"

    tooltip = tooltip_fields(ch, tooltip)

    tooltip = tooltip_factions(ch, context, tooltip)

    if ch["teaser"]:
        tooltip += "<span class='teaser'>" + replace_chars(context, ch["teaser"]) + " (...)</span>"

    return tooltip


def tooltip_fields(ch, tooltip):
    """Add character name, title, and player information to tooltip.

    Args:
        ch (dict): Character data dictionary
        tooltip (str): Current tooltip HTML string

    Returns:
        str: Updated tooltip HTML with character fields
    """
    tooltip += f"<span><b class='name'>{ch['name']}</b>"

    if ch["title"]:
        tooltip += " - <b class='title'>" + ch["title"] + "</b>"

    if "pronoun" in ch and ch["pronoun"]:
        tooltip += " (" + ch["pronoun"] + ")"

    tooltip += "</span>"

    if "player_id" in ch and ch["player_id"] > 0:
        tooltip += "<span>" + _("Player") + ": <b>" + ch["player_full"] + "</b></span>"

    return tooltip


def tooltip_factions(ch, context, tooltip):
    """Add faction information to character tooltip.

    Args:
        ch (dict): Character data dictionary
        context: Template context with faction data
        tooltip (str): Current tooltip HTML string

    Returns:
        str: Updated tooltip HTML with faction information
    """
    factions = ""
    for fnum in context["factions"]:
        el = context["factions"][fnum]
        if el["typ"] == FactionType.SECRET:
            continue
        if fnum in ch["factions"]:
            if factions:
                factions += ", "
            factions += el["name"]
    if factions:
        tooltip += "<span>" + _("Factions") + ": " + factions + "</span>"
    return tooltip


@register.simple_tag(takes_context=True)
def replace_chars(context, el, limit=200):
    """Template tag to replace character number references with names.

    Replaces #XX, @XX, and ^XX patterns with character names in text.

    Args:
        context: Template context containing character data
        el (str): Text containing character references
        limit (int): Maximum length of returned text

    Returns:
        str: Text with character references replaced by names
    """
    el = html_clean(el)
    for number in range(context["max_ch_number"], 0, -1):
        if number not in context["chars"]:
            continue
        lk = context["chars"][number]["name"]
        el = el.replace(f"#{number}", lk)
        el = el.replace(f"@{number}", lk)

        lk = lk.split()
        if lk:
            lk = lk[0]
            el = el.replace(f"^{number}", lk)
    return el[:limit]


def go_character(context, search, number, tx, run, go_tooltip, simple=False):
    """Replace character reference with formatted link or name.

    Args:
        context: Template context with character data
        search (str): Pattern to search for (e.g., '#1', '@1', '^1')
        number (int): Character number to replace
        tx (str): Text containing the search pattern
        run: Run instance for URL generation
        go_tooltip (bool): Whether to include tooltip
        simple (bool): If True, return simple name; if False, return link

    Returns:
        str: Text with character reference replaced
    """
    if search not in tx:
        return tx

    if "chars" not in context:
        return tx

    if number not in context["chars"]:
        return tx

    ch = context["chars"][number]

    r = get_url(
        reverse("character", args=[run.get_slug(), ch["number"]]),
        context["assoc_slug"],
    ).replace('"', "")

    if simple:
        lk = f"<b>{ch['name'].split()[0]}</b>"
    else:
        lk = f"<a class='link_show_char' href='{r}'>{ch['name']}</a>"
        if go_tooltip:
            tooltip = get_tooltip(context, ch)
            lk = "<span class='has_show_char'>" + lk + f"</span><span class='hide show_char'>{tooltip}</span>"

    return tx.replace(search, lk)


def _remove_unimportant_prefix(text):
    """Remove first occurrence of $unimportant from text and clean up empty HTML tags at start.

    Args:
        text (str): Text that may contain $unimportant prefix

    Returns:
        str: Text with first occurrence of $unimportant removed and empty HTML tags cleaned up
    """
    if not text:
        return text

    original_text = text
    text = text.replace("$unimportant", "", 1)

    # If $unimportant was replaced, remove empty HTML tags at the start
    if text != original_text:
        # Remove empty HTML tags and whitespace from the beginning
        while True:
            stripped = text.lstrip()
            # Match empty HTML tags like <p></p>, <div></div>, <span></span>, etc.
            # Also match \r, \n, &nbsp; and other whitespace characters inside tags
            match = re.match(r"^<(\w+)(?:\s[^>]*)?>(?:\s|&nbsp;|\r|\n)*</\1>", stripped)
            if match:
                # Remove the empty tag and continue
                text = stripped[match.end() :]
            else:
                text = stripped
                break

    return text


@register.simple_tag(takes_context=True)
def show_char(context, el, run, tooltip):
    """Template tag to process text and convert character references to links.

    Args:
        context: Template context
        el: Text element to process (string or dict with 'text' key)
        run: Run instance for character lookup
        tooltip (bool): Whether to include character tooltips

    Returns:
        str: Safe HTML with character references converted to links
    """
    if isinstance(el, dict) and "text" in el:
        tx = el["text"] + " "
    elif el is not None:
        tx = str(el) + " "
    else:
        tx = ""

    if "max_ch_number" not in context:
        context["max_ch_number"] = run.event.get_elements(Character).aggregate(Max("number"))["number__max"]

    if not context["max_ch_number"]:
        context["max_ch_number"] = 0

    # replace #XX (create relationships / count as character in faction / plot)
    for number in range(context["max_ch_number"], 0, -1):
        tx = go_character(context, f"#{number}", number, tx, run, tooltip)
        tx = go_character(context, f"@{number}", number, tx, run, tooltip)
        tx = go_character(context, f"^{number}", number, tx, run, tooltip, simple=True)

    # replace unimportant tag - remove $unimportant prefix and clean up empty tags
    tx = _remove_unimportant_prefix(tx)

    return mark_safe(tx)


def go_trait(context, search, number, tx, run, go_tooltip, simple=False):
    """Replace trait reference with character link.

    Args:
        context: Template context with trait and character data
        search (str): Pattern to search for
        number (int): Trait number to replace
        tx (str): Text containing the search pattern
        run: Run instance for character lookup
        go_tooltip (bool): Whether to include tooltip
        simple (bool): If True, return simple name; if False, return link

    Returns:
        str: Text with trait reference replaced by character link
    """
    if search not in tx:
        return tx

    if "traits" not in context:
        context["traits"] = {}

    if number in context["traits"]:
        ch_number = context["traits"][number]["char"]
    else:
        char = get_trait_character(run, number)
        if not char:
            return tx
        ch_number = char.number

    if ch_number not in context["chars"]:
        return tx

    ch = context["chars"][ch_number]

    if simple:
        lk = f"<b>{ch['name'].split()[0]}</b>"
    else:
        tooltip = ""
        if go_tooltip:
            tooltip = get_tooltip(context, ch)
        r = get_url(
            reverse("character", args=[run.get_slug(), ch["number"]]),
            context["slug"],
        )
        lk = (
            f"<span class='has_show_char'><a href='{r}'>{ch['name']}</a></span>"
            f"<span class='hide show_char'>{tooltip}</span>"
        )

    return tx.replace(search, lk)


@register.simple_tag(takes_context=True)
def show_trait(context, tx, run, tooltip):
    """Template tag to process text and convert trait references to character links.

    Args:
        context: Template context
        tx (str): Text containing trait references
        run: Run instance for trait lookup
        tooltip (bool): Whether to include character tooltips

    Returns:
        str: Safe HTML with trait references converted to character links
    """
    if "max_trait" not in context:
        context["max_trait"] = Trait.objects.filter(event=run.event).aggregate(Max("number"))["number__max"]

    if not context["max_trait"]:
        context["max_trait"] = 0

    # replace #XX (create relationships / count as character in faction / plot)
    for number in range(context["max_trait"], 0, -1):
        tx = go_trait(context, f"#{number}", number, tx, run, tooltip)
        tx = go_trait(context, f"@{number}", number, tx, run, tooltip)
        tx = go_trait(context, f"^{number}", number, tx, run, tooltip, simple=True)

    return mark_safe(tx)


@register.simple_tag
def key(d, key_name, s_key_name=None):
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
    else:
        return ""


@register.simple_tag
def get_field(form, name):
    """Template tag to safely get form field by name.

    Args:
        form: Django form instance
        name (str): Field name to retrieve

    Returns:
        Field: Form field or empty string if not found
    """
    if name in form:
        return form[name]
    return ""


@register.simple_tag(takes_context=True)
def get_field_show_char(context, form, name, run, tooltip):
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
        return show_char(context, v, run, tooltip)
    return ""


@register.simple_tag
def get_deep_field(form, key1, key2):
    """Template tag to get nested form field value.

    Args:
        form: Form or dictionary
        key1: First level key
        key2: Second level key

    Returns:
        any: Nested value or empty string if not found
    """
    if key1 in form:
        if key2 in form[key1]:
            return form[key1][key2]
    return ""


@register.filter
def get_form_field(form, name):
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
def lookup(obj, prop):
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
def get_registration_option(reg, number):
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
def gt(value, arg):
    """Template tag for greater than comparison.

    Args:
        value: Value to compare
        arg: Comparison value

    Returns:
        bool: True if value > arg
    """
    return value > int(arg)


@register.simple_tag
def lt(value, arg):
    """Template tag for less than comparison.

    Args:
        value: Value to compare
        arg: Comparison value

    Returns:
        bool: True if value < arg
    """
    return value < int(arg)


@register.simple_tag
def gte(value, arg):
    """Template tag for greater than or equal comparison.

    Args:
        value: Value to compare
        arg: Comparison value

    Returns:
        bool: True if value >= arg
    """
    return value >= int(arg)


@register.simple_tag
def lte(value, arg):
    """Template tag for less than or equal comparison.

    Args:
        value: Value to compare
        arg: Comparison value

    Returns:
        bool: True if value <= arg
    """
    return value <= int(arg)


@register.simple_tag
def length_gt(value, arg):
    """Template tag for length greater than comparison.

    Args:
        value: Collection to check length
        arg: Length to compare against

    Returns:
        bool: True if len(value) > arg
    """
    return len(value) > int(arg)


@register.simple_tag
def length_lt(value, arg):
    """Template tag for length less than comparison.

    Args:
        value: Collection to check length
        arg: Length to compare against

    Returns:
        bool: True if len(value) < arg
    """
    return len(value) < int(arg)


@register.simple_tag
def length_gte(value, arg):
    """Template tag for length greater than or equal comparison.

    Args:
        value: Collection to check length
        arg: Length to compare against

    Returns:
        bool: True if len(value) >= arg
    """
    return len(value) >= int(arg)


@register.simple_tag
def length_lte(value, arg):
    """Template tag for length less than or equal comparison.

    Args:
        value: Collection to check length
        arg: Length to compare against

    Returns:
        bool: True if len(value) <= arg
    """
    return len(value) <= int(arg)


@register.filter
def hex_to_rgb(value):
    """Template filter to convert hex color to RGB values.

    Args:
        value (str): Hex color string (e.g., '#FF0000')

    Returns:
        str: Comma-separated RGB values (e.g., '255,0,0')
    """
    h = value.lstrip("#")
    h = [str(int(h[i : i + 2], 16)) for i in (0, 2, 4)]
    return ",".join(h)


@register.simple_tag
def define(val=None):
    """Template tag to define/store a value in templates.

    Args:
        val: Value to store

    Returns:
        any: The input value unchanged
    """
    return val


@register.filter(name="template_trans")
def template_trans(text):
    """Template filter for safe translation of text.

    Args:
        text (str): Text to translate

    Returns:
        str: Translated text or original text if translation fails
    """
    try:
        return _(text)
    except Exception as e:
        print(e)
        return text


@register.simple_tag(takes_context=True)
def get_char_profile(context, char):
    """Template tag to get character profile image URL.

    Args:
        context: Template context with features
        char (dict): Character data dictionary

    Returns:
        str: URL to character profile image or default avatar
    """
    if "player_prof" in char and char["player_prof"]:
        return char["player_prof"]
    if "cover" in context["features"]:
        if "cover_orig" in context and "cover" in char:
            return char["cover"]
        elif "thumb" in char:
            return char["thumb"]
    return "/static/larpmanager/assets/blank-avatar.svg"


@register.simple_tag(takes_context=True)
def get_login_url(context, provider, **params):
    """Template tag to generate OAuth login URL with parameters.

    Args:
        context: Template context with request
        provider (str): OAuth provider name
        **params: Additional URL parameters

    Returns:
        str: Complete login URL with query parameters
    """
    request = context.get("request")
    query = dict(params)
    auth_params = query.get("auth_params", None)
    scope = query.get("scope", None)
    process = query.get("process", None)
    if scope == "":
        del query["scope"]
    if auth_params == "":
        del query["auth_params"]
    if REDIRECT_FIELD_NAME not in query:
        redirect = get_request_param(request, REDIRECT_FIELD_NAME)
        if redirect:
            query[REDIRECT_FIELD_NAME] = redirect
        elif process == "redirect":
            query[REDIRECT_FIELD_NAME] = request.get_full_path()
    elif not query[REDIRECT_FIELD_NAME]:
        del query[REDIRECT_FIELD_NAME]

    url = reverse(provider + "_login")
    url = url + "?" + urlencode(query)
    return url


@register.filter
def replace_underscore(value):
    """Template filter to replace underscores with spaces.

    Args:
        value (str): String to process

    Returns:
        str: String with underscores replaced by spaces
    """
    return value.replace("_", " ")


@register.filter
def remove(value, args):
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
def get_character_field(value, options):
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
        try:
            result.append(options[idx]["name"])
        except (IndexError, KeyError, TypeError):
            pass
    return ", ".join(result)


@register.filter
def format_decimal(value):
    """Template filter to format decimal values for display.

    Args:
        value: Numeric value to format

    Returns:
        str: Formatted decimal string, empty for zero, integer format when possible
    """
    try:
        rounded = round_to_nearest_cent(float(value))
        if rounded == 0:
            return ""
        if rounded == int(rounded):
            return str(int(rounded))
        return f"{rounded:.2f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return value


@register.filter
def get_attributes(obj):
    """Template filter to get object attributes as dictionary.

    Args:
        obj: Object to inspect

    Returns:
        dict: Dictionary of non-private attributes
    """
    return {k: v for k, v in vars(obj).items() if not k.startswith("_")}


@register.filter
def not_in(value, arg):
    """Template filter to check if value is not in comma-separated list.

    Args:
        value: Value to check
        arg (str): Comma-separated list of values

    Returns:
        bool: True if value not in the list
    """
    return value not in arg.split(",")


@register.filter
def abs_value(value):
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
def concat(val1, val2):
    """Template filter to concatenate two values.

    Args:
        val1: First value to concatenate
        val2: Second value to concatenate

    Returns:
        str: Concatenated string
    """
    return f"{val1}{val2}"
