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

from django.core.cache import cache
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.feature import get_assoc_features, get_event_features
from larpmanager.cache.links import cache_event_links
from larpmanager.cache.permission import get_assoc_permission_feature
from larpmanager.models.access import AssocPermission, AssocRole, EventRole
from larpmanager.utils.base import def_user_ctx
from larpmanager.utils.exceptions import FeatureError, PermissionError


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
        cache.set(key, res)
    return res


def delete_cache_assoc_role(ar_id):
    key = cache_assoc_role_key(ar_id)
    cache.delete(key)


@receiver(post_save, sender=AssocRole)
def post_save_assoc_role_reset(sender, instance, **kwargs):
    delete_cache_assoc_role(instance.pk)


@receiver(pre_delete, sender=AssocRole)
def del_assoc_role_reset(sender, instance, **kwargs):
    delete_cache_assoc_role(instance.pk)


def get_assoc_roles(request):
    pms = {}
    if request.user.is_superuser:
        return True, [], []
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


def has_assoc_permission(request, perm):
    if not hasattr(request.user, "member"):
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
        cache.set(key, res)
    return res


def delete_cache_event_role(ar_id):
    key = cache_event_role_key(ar_id)
    cache.delete(key)


@receiver(post_save, sender=EventRole)
def post_save_event_role_reset(sender, instance, **kwargs):
    delete_cache_event_role(instance.pk)


@receiver(pre_delete, sender=EventRole)
def del_event_role_reset(sender, instance, **kwargs):
    delete_cache_event_role(instance.pk)


def get_event_roles(request, slug):
    pms = {}
    if request.user.is_superuser:
        return True, [], []
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


def has_event_permission(ctx, request, slug, perm=None):
    if not request:
        return False
    if not hasattr(request.user, "member"):
        return False
    if "assoc_role" in ctx and 1 in ctx["assoc_role"]:
        return True
    (organizer, permissions, names) = get_event_roles(request, slug)
    if organizer:
        return True
    if not perm:
        return len(names) > 0
    return perm in permissions


def check_assoc_permission(request, slug):
    ctx = def_user_ctx(request)
    if not has_assoc_permission(request, slug):
        raise PermissionError()
    feature = get_assoc_permission_feature(slug)
    if feature != "def" and feature not in request.assoc["features"]:
        raise FeatureError(path=request.path, feature=feature, run=0)
    ctx["manage"] = 1
    get_index_assoc_permissions(ctx, request, request.assoc["id"])
    ctx["is_sidebar_open"] = request.session.get("is_sidebar_open", False)
    return ctx


def get_index_assoc_permissions(ctx, request, assoc_id, check=True):
    (is_admin, user_assoc_permissions, names) = get_assoc_roles(request)
    if check and not names and not is_admin:
        raise PermissionError()
    ctx["role_names"] = names
    features = get_assoc_features(assoc_id)
    ctx["assoc_pms"] = get_index_permissions(features, is_admin, user_assoc_permissions, AssocPermission)


def get_index_permissions(features, has_default, permissions, typ):
    res = {}
    for ar in typ.objects.select_related("feature", "feature__module").order_by("feature__module__order", "number"):
        if not has_default and ar.slug not in permissions:
            continue
        if not ar.feature.placeholder and ar.feature.slug not in features:
            continue
        mod_name = _(ar.feature.module.name)
        if mod_name not in res:
            res[mod_name] = []
        res[mod_name].append(ar)

    return res
