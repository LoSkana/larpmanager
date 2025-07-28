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
    return num % val


@register.filter
def clean_tags(tx):
    tx = tx.replace("<br />", " ")
    return strip_tags(tx)


@register.filter
def get(value, arg):
    if arg is not None and value and arg in value:
        return value[arg]
    return ""


def get_tooltip(context, ch):
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
    if search not in tx:
        return tx

    if "chars" not in context:
        return tx

    if number not in context["chars"]:
        return tx

    ch = context["chars"][number]

    r = get_url(
        reverse("character", args=[run.event.slug, run.number, ch["number"]]),
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


@register.simple_tag(takes_context=True)
def show_char(context, el, run, tooltip):
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

    return mark_safe(tx)


def go_trait(context, search, number, tx, run, go_tooltip, simple=False):
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
            reverse("character", args=[run.event.slug, run.number, ch["number"]]),
            context["slug"],
        )
        lk = (
            f"<span class='has_show_char'><a href='{r}'>{ch['name']}</a></span>"
            f"<span class='hide show_char'>{tooltip}</span>"
        )

    return tx.replace(search, lk)


@register.simple_tag(takes_context=True)
def show_trait(context, tx, run, tooltip):
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
    if name in form:
        return form[name]
    return ""


@register.simple_tag(takes_context=True)
def get_field_show_char(context, form, name, run, tooltip):
    if name in form:
        v = form[name]
        return show_char(context, v, run, tooltip)
    return ""


@register.simple_tag
def get_deep_field(form, key1, key2):
    if key1 in form:
        if key2 in form[key1]:
            return form[key1][key2]
    return ""


@register.simple_tag
def get_form_field(form, name):
    if name in form.fields:
        return form[name]
    return ""


@register.simple_tag
def lookup(obj, prop):
    if hasattr(obj, prop):
        value = getattr(obj, prop)
        if value:
            return value
    return ""


@register.simple_tag
def get_registration_option(reg, number):
    v = getattr(reg, f"option_{number}")
    if v:
        return v.get_form_text()
    return ""


@register.simple_tag
def gt(value, arg):
    return value > int(arg)


@register.simple_tag
def lt(value, arg):
    return value < int(arg)


@register.simple_tag
def gte(value, arg):
    return value >= int(arg)


@register.simple_tag
def lte(value, arg):
    return value <= int(arg)


@register.simple_tag
def length_gt(value, arg):
    return len(value) > int(arg)


@register.simple_tag
def length_lt(value, arg):
    return len(value) < int(arg)


@register.simple_tag
def length_gte(value, arg):
    return len(value) >= int(arg)


@register.simple_tag
def length_lte(value, arg):
    return len(value) <= int(arg)


@register.filter
def hex_to_rgb(value):
    h = value.lstrip("#")
    h = [str(int(h[i : i + 2], 16)) for i in (0, 2, 4)]
    return ",".join(h)


@register.simple_tag
def define(val=None):
    return val


@register.filter(name="template_trans")
def template_trans(text):
    try:
        return _(text)
    except Exception as e:
        print(e)
        return text


@register.simple_tag(takes_context=True)
def get_char_profile(context, char):
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
    return value.replace("_", " ")


@register.filter
def remove(value, args):
    args = args.replace("_", " ")
    txt = re.sub(re.escape(args), "", value, flags=re.IGNORECASE)
    return txt.strip()


@register.simple_tag
def get_character_field(value, options):
    if isinstance(value, str):
        return value
    result = []
    for idx in value:
        try:
            result.append(options[idx]["display"])
        except (IndexError, KeyError, TypeError):
            pass
    return ", ".join(result)


@register.filter
def format_decimal(value):
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
    return {k: v for k, v in vars(obj).items() if not k.startswith("_")}


@register.filter
def not_in(value, arg):
    return value not in arg.split(",")


@register.filter
def abs_value(value):
    try:
        return abs(value)
    except (TypeError, ValueError):
        return value


@register.filter
def concat(val1, val2):
    return f"{val1}{val2}"
