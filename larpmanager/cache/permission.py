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
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from larpmanager.models.access import AssocPermission, EventPermission
from larpmanager.models.base import Feature, FeatureModule


def assoc_permission_feature_key(slug):
    return f"assoc_permission_feature_{slug}"


def update_assoc_permission_feature(slug):
    perm = AssocPermission.objects.select_related("feature").get(slug=slug)
    feature = perm.feature
    if feature.placeholder:
        slug = "def"
    else:
        slug = feature.slug
    tutorial = feature.tutorial or ""
    config = perm.config or ""
    cache.set(assoc_permission_feature_key(slug), (slug, tutorial, config))
    return slug, tutorial, config


def get_assoc_permission_feature(slug):
    res = cache.get(assoc_permission_feature_key(slug))
    if not res:
        res = update_assoc_permission_feature(slug)
    return res


@receiver(post_save, sender=AssocPermission)
def post_save_assoc_permission_reset(sender, instance, **kwargs):
    cache.delete(assoc_permission_feature_key(instance.slug))


@receiver(post_delete, sender=AssocPermission)
def post_delete_assoc_permission_reset(sender, instance, **kwargs):
    cache.delete(assoc_permission_feature_key(instance.slug))


def event_permission_feature_key(slug):
    return f"event_permission_feature_{slug}"


def update_event_permission_feature(slug):
    perm = EventPermission.objects.select_related("feature").get(slug=slug)
    feature = perm.feature
    if feature.placeholder:
        slug = "def"
    else:
        slug = feature.slug
    tutorial = feature.tutorial or ""
    config = perm.config or ""
    cache.set(event_permission_feature_key(slug), (slug, tutorial, config))
    return slug, tutorial, config


def get_event_permission_feature(slug):
    res = cache.get(event_permission_feature_key(slug))
    if not res:
        res = update_event_permission_feature(slug)
    return res


@receiver(post_save, sender=EventPermission)
def post_save_event_permission_reset(sender, instance, **kwargs):
    cache.delete(event_permission_feature_key(instance.slug))


@receiver(post_delete, sender=EventPermission)
def post_delete_event_permission_reset(sender, instance, **kwargs):
    cache.delete(event_permission_feature_key(instance.slug))


def index_permission_key(typ):
    return f"index_permission_key_{typ}"


def update_index_permission(typ):
    mapping = {"event": EventPermission, "assoc": AssocPermission}
    que = mapping[typ].objects.select_related("feature", "feature__module")
    que = que.order_by("feature__module__order", "number")
    return que.values(
        "name",
        "descr",
        "slug",
        "hidden",
        "feature__placeholder",
        "feature__slug",
        "feature__module__name",
        "feature__module__icon",
    )


def get_cache_index_permission(typ):
    res = cache.get(index_permission_key(typ))
    if not res:
        res = update_index_permission(typ)
    return res


def reset_index_permission(typ):
    cache.delete(index_permission_key(typ))


@receiver(post_save, sender=AssocPermission)
def post_save_assoc_permission_index_permission(sender, instance, **kwargs):
    reset_index_permission("assoc")


@receiver(post_delete, sender=AssocPermission)
def post_delete_assoc_permission_index_permission(sender, instance, **kwargs):
    reset_index_permission("assoc")


@receiver(post_save, sender=EventPermission)
def post_save_event_permission_index_permission(sender, instance, **kwargs):
    reset_index_permission("event")


@receiver(post_delete, sender=EventPermission)
def post_delete_event_permission_index_permission(sender, instance, **kwargs):
    reset_index_permission("event")


@receiver(post_save, sender=Feature)
def post_save_feature_index_permission(sender, instance, **kwargs):
    reset_index_permission("event")
    reset_index_permission("assoc")


@receiver(post_delete, sender=Feature)
def post_delete_feature_index_permission(sender, instance, **kwargs):
    reset_index_permission("event")
    reset_index_permission("assoc")


@receiver(post_save, sender=FeatureModule)
def post_save_feature_module_index_permission(sender, instance, **kwargs):
    reset_index_permission("event")
    reset_index_permission("assoc")


@receiver(post_delete, sender=FeatureModule)
def post_delete_feature_module_index_permission(sender, instance, **kwargs):
    reset_index_permission("event")
    reset_index_permission("assoc")
