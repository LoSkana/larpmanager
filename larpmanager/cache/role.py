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

from larpmanager.cache.feature import get_assoc_features, get_event_features
from larpmanager.cache.links import cache_event_links
from larpmanager.models.access import AssocRole, EventRole
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


def has_event_permission(ctx, request, slug, perm=None):
    if not request or not hasattr(request.user, "member"):
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
