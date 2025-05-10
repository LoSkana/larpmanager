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

from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Prefetch
from django.http import Http404
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.button import get_event_button_cache
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.permission import get_event_permission_feature
from larpmanager.cache.role import get_event_roles, get_index_permissions, has_event_permission
from larpmanager.cache.run import get_cache_run
from larpmanager.models.access import EventPermission
from larpmanager.models.event import Event, Run
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import Character, Faction
from larpmanager.utils.base import def_user_ctx
from larpmanager.utils.exceptions import FeatureError, PermissionError, UnknowRunError, check_event_feature
from larpmanager.utils.registration import check_signup, registration_status


def get_event(request, slug, number=None):
    if request:
        ctx = def_user_ctx(request)
    else:
        ctx = {}

    try:
        if number:
            get_run(ctx, slug, number)
        else:
            ctx["event"] = Event.objects.get(slug=slug)

        if "a_id" in ctx:
            if ctx["event"].assoc_id != ctx["a_id"]:
                raise Http404("wrong assoc")
        else:
            ctx["a_id"] = ctx["event"].assoc_id

        ctx["features"] = get_event_features(ctx["event"].id)

        # paste as text tinymce
        if "paste_text" in ctx["features"]:
            conf_settings.TINYMCE_DEFAULT_CONFIG["paste_as_text"] = True

        ctx["show_available_chars"] = _("Show available characters")

        return ctx
    except ObjectDoesNotExist as err:
        raise Http404("Event does not exist") from err


def get_event_run(request, s, n, signup=False, slug=None, status=False):
    ctx = get_event(request, s, number=n)

    if signup:
        check_signup(request, ctx)

    if slug:
        check_event_feature(request, ctx, slug)

    if status:
        registration_status(ctx["run"], request.user)

    if hasattr(request, "assoc"):
        ctx["assoc_slug"] = request.assoc["slug"]
    else:
        ctx["assoc_slug"] = ctx["event"].assoc.slug

    ctx["buttons"] = get_event_button_cache(ctx["event"].id)

    ctx["show_limitations"] = ctx["event"].get_config("show_limitations", False)

    # check if the user has any role
    if has_event_permission(ctx, request, s):
        ctx["manage"] = 1
        get_index_event_permissions(ctx, request, s)
        ctx["is_sidebar_open"] = request.session.get("is_sidebar_open", False)

    if has_event_permission(ctx, request, s, "orga_characters"):
        ctx["staff"] = "1"
        ctx["skip"] = "1"

    for config_name in ["char", "teaser", "preview", "text"]:
        ctx["show_" + config_name] = "staff" in ctx or ctx["run"].get_config("show_" + config_name, False)

    ctx["px_user"] = ctx["event"].get_config("px_user", False)
    if ctx["event"].parent:
        ctx["px_user"] = ctx["event"].parent.get_config("px_user", False)

    ctx["user_character_max"] = ctx["event"].get_config("user_character_max", 0)

    for config_name in [
        "faction",
        "speedlarp",
        "prologue",
        "questbuilder",
        "workshop",
        "print_pdf",
        "co_creation",
        "preview",
    ]:
        if config_name not in ctx["features"]:
            continue

        ctx["show_" + config_name] = "staff" in ctx or ctx["run"].get_config("show_" + config_name, False)

    ctx["cover_orig"] = ctx["event"].get_config("cover_orig", False)

    return ctx


def get_run(ctx, s, n):
    try:
        res = get_cache_run(s, n)
        que = Run.objects.select_related("event")
        fields = [
            "search",
            "balance",
            "event__tagline",
            "event__where",
            "event__authors",
            "event__description_short",
            "event__description",
            "event__genre",
            "event__cover",
            "event__carousel_img",
            "event__carousel_text",
            "event__features",
            "event__background",
            "event__font",
            "event__pri_rgb",
            "event__sec_rgb",
            "event__ter_rgb",
        ]
        que = que.defer(*fields)
        ctx["run"] = que.get(pk=res)
        ctx["event"] = ctx["run"].event
    except Exception as err:
        raise UnknowRunError() from err


def get_character_filter(ch, regs, filters):
    if "free" in filters:
        if ch.id in regs:
            return False
    if "png" in filters and ch.special == Character.PNG:
        return False
    if "filler" in filters and ch.special == Character.FILLER:
        return False
    if "mirror" in filters and ch.mirror_id:
        if ch.mirror_id in regs:
            return False
    return True


def get_event_filter_characters(ctx, filters):
    ctx["factions"] = []

    regs = {}
    for el in RegistrationCharacterRel.objects.filter(
        reg__run=ctx["run"], reg__cancellation_date__isnull=True
    ).select_related("reg", "reg__member"):
        regs[el.character_id] = el.reg

    chars = {}
    for c in ctx["event"].get_elements(Character).filter(hide=False):
        if c.id in regs:
            c.reg = regs[c.id]
            c.member = regs[c.id].member
        chars[c.id] = c

    if "faction" in ctx["features"] and ctx["show_faction"]:
        que = ctx["event"].get_elements(Faction).filter(typ=Faction.PRIM).order_by("order")
        prefetch = Prefetch(
            "characters",
            queryset=Character.objects.filter(hide=False).order_by("number"),
        )
        for f in que.prefetch_related(prefetch):
            f.data = f.show_red()
            f.chars = []
            for ch in f.characters.all():
                if ch.hide:
                    continue
                if not get_character_filter(ch, regs, filters):
                    continue
                ch.data = ch.show_red()
                f.chars.append(ch)
            if len(f.chars) == 0:
                continue
            ctx["factions"].append(f)
    else:
        f = Faction()
        f.number = 0
        f.name = "all"
        f.data = f.show_red()
        f.chars = []
        for _ch_id, ch in chars.items():
            if not get_character_filter(ch, regs, filters):
                continue
            ch.data = ch.show_red()
            f.chars.append(ch)
        ctx["factions"].append(f)


def has_access_character(request, ctx):
    if has_event_permission(ctx, request, ctx["event"].slug, "orga_characters"):
        return True

    member_id = request.user.member.id

    if "owner_id" in ctx["char"] and ctx["char"]["owner_id"] == member_id:
        return True

    if "player_id" in ctx["char"] and ctx["char"]["player_id"] == member_id:
        return True

    return False


def check_event_permission(request, s, n, perm=None):
    ctx = get_event_run(request, s, n)
    if not has_event_permission(ctx, request, s, perm):
        raise PermissionError()
    if perm:
        feature = get_event_permission_feature(perm)
        if feature != "def" and feature not in ctx["features"]:
            raise FeatureError(path=request.path, feature=feature, run=ctx["run"].id)
    get_index_event_permissions(ctx, request, s)
    return ctx


def get_index_event_permissions(ctx, request, slug, check=True):
    (is_organizer, user_event_permissions, names) = get_event_roles(request, slug)
    if "assoc_role" in ctx and 1 in ctx["assoc_role"]:
        is_organizer = True
    if check and not names and not is_organizer:
        raise PermissionError()
    ctx["role_names"] = names
    features = get_event_features(ctx["event"].id)
    ctx["event_pms"] = get_index_permissions(features, is_organizer, user_event_permissions, EventPermission)
