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
from django.core.cache import cache

from larpmanager.cache.feature import get_assoc_features, get_event_features
from larpmanager.cache.links import cache_event_links
from larpmanager.cache.permission import get_assoc_permission_feature, get_event_permission_feature
from larpmanager.models.access import AssocRole, EventRole
from larpmanager.utils.auth import get_allowed_managed
from larpmanager.utils.exceptions import PermissionError


def cache_assoc_role_key(ar_id):
    return f"assoc_role_{ar_id}"


def get_assoc_role(ar):
    ls = []
    features = get_assoc_features(ar.assoc_id)
    for el in ar.permissions.values_list("slug", "feature__slug", "feature__placeholder"):
        if not el[2] and el[1] not in features:
            continue
        ls.append(el[0])
    return ar.name, ls


def get_cache_assoc_role(ar_id):
    key = cache_assoc_role_key(ar_id)
    res = cache.get(key)
    if not res:
        try:
            ar = AssocRole.objects.get(pk=ar_id)
        except Exception as err:
            raise PermissionError() from err
        res = get_assoc_role(ar)
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def remove_association_role_cache(ar_id):
    key = cache_assoc_role_key(ar_id)
    cache.delete(key)


def get_assoc_roles(request):
    pms = {}
    if request.user.is_superuser:
        return True, [], ["superuser"]
    ctx = cache_event_links(request)
    is_admin = False
    names = []
    for num, el in ctx["assoc_role"].items():
        if num == 1:
            is_admin = True
        (name, slugs) = get_cache_assoc_role(el)
        names.append(name)
        for slug in slugs:
            pms[slug] = 1
    return is_admin, pms, names


def has_assoc_permission(request, ctx, perm):
    if not hasattr(request.user, "member"):
        return False
    if check_managed(ctx, perm):
        return False
    (admin, permissions, names) = get_assoc_roles(request)
    if admin:
        return True
    if not perm:
        return True
    return perm in permissions


def cache_event_role_key(ar_id):
    return f"event_role_{ar_id}"


def get_event_role(ar):
    ls = []
    features = get_event_features(ar.event_id)
    for el in ar.permissions.values_list("slug", "feature__slug", "feature__placeholder"):
        if not el[2] and el[1] not in features:
            continue
        ls.append(el[0])
    return ar.name, ls


def get_cache_event_role(ev_id):
    key = cache_event_role_key(ev_id)
    res = cache.get(key)
    if not res:
        try:
            ar = EventRole.objects.get(pk=ev_id)
        except Exception as err:
            raise PermissionError() from err
        res = get_event_role(ar)
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def remove_event_role_cache(ar_id):
    key = cache_event_role_key(ar_id)
    cache.delete(key)


def get_event_roles(request, slug):
    """Get user's event roles and permissions for a specific event slug.

    Args:
        request: Django HTTP request object with authenticated user
        slug: Event slug identifier

    Returns:
        tuple: (is_organizer, permissions_dict, role_names_list)
    """
    pms = {}
    # split if provided slug from session
    slug = slug.split("-", 1)[0]
    if request.user.is_superuser:
        return True, [], ["superuser"]
    ctx = cache_event_links(request)
    if slug not in ctx["event_role"]:
        return False, [], []
    is_organizer = False
    names = []
    for num, el in ctx["event_role"][slug].items():
        if num == 1:
            is_organizer = True
        (name, slugs) = get_cache_event_role(el)
        names.append(name)
        for pm_slug in slugs:
            pms[pm_slug] = 1
    return is_organizer, pms, names


def has_event_permission(request, ctx, slug, perm=None):
    if not request or not hasattr(request.user, "member") or check_managed(ctx, perm, assoc=False):
        return False
    if "assoc_role" in ctx and 1 in ctx["assoc_role"]:
        return True
    (organizer, permissions, names) = get_event_roles(request, slug)
    if organizer:
        return True
    if not perm:
        return len(names) > 0
    if isinstance(perm, list):
        return any(p in permissions for p in perm)
    return perm in permissions


def check_managed(ctx, perm, assoc=True):
    """Check if permission is restricted for managed association skins.

    Args:
        ctx: Context dictionary with skin_managed and is_staff flags
        perm: Permission string to check
        assoc: Whether to check association permissions (True) or event permissions (False)

    Returns:
        bool: True if permission is restricted due to managed skin, False otherwise
    """
    # check if the association skin is managed and the user is not staff
    if not ctx.get("skin_managed", False) or ctx.get("is_staff", False):
        return False

    if perm in get_allowed_managed():
        return False

    if assoc:
        placeholder, _, _ = get_assoc_permission_feature(perm)
    else:
        placeholder, _, _ = get_event_permission_feature(perm)

    if placeholder != "def":
        return False

    return True
