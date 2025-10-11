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

import logging

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.models.access import AssocPermission, EventPermission

logger = logging.getLogger(__name__)


def assoc_permission_feature_key(slug):
    """Generate cache key for association permission features.

    Args:
        slug (str): Permission slug

    Returns:
        str: Cache key for association permission feature
    """
    return f"assoc_permission_feature_{slug}"


def update_assoc_permission_feature(slug):
    """Update cached association permission feature data.

    Args:
        slug (str): Permission slug

    Returns:
        tuple: (feature_slug, tutorial, config) data
    """
    perm = AssocPermission.objects.select_related("feature").get(slug=slug)
    feature = perm.feature
    if feature.placeholder:
        slug = "def"
    else:
        slug = feature.slug
    tutorial = feature.tutorial or ""
    config = perm.config or ""
    cache.set(assoc_permission_feature_key(slug), (slug, tutorial, config), timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return slug, tutorial, config


def get_assoc_permission_feature(slug):
    """Get cached association permission feature data.

    Args:
        slug (str): Permission slug

    Returns:
        tuple: (feature_slug, tutorial, config) from cache or database
    """
    if not slug:
        return "def", None, None
    res = cache.get(assoc_permission_feature_key(slug))
    if not res:
        res = update_assoc_permission_feature(slug)
    return res


def clear_association_permission_cache(instance):
    cache.delete(assoc_permission_feature_key(instance.slug))


def event_permission_feature_key(slug):
    """Generate cache key for event permission features.

    Args:
        slug (str): Permission slug

    Returns:
        str: Cache key for event permission feature
    """
    return f"event_permission_feature_{slug}"


def update_event_permission_feature(slug):
    try:
        perm = EventPermission.objects.select_related("feature").get(slug=slug)
    except ObjectDoesNotExist:
        logger.warning(f"Permission slug does not exist: {slug}")
        return "", "", ""
    feature = perm.feature
    if feature.placeholder:
        slug = "def"
    else:
        slug = feature.slug
    tutorial = feature.tutorial or ""
    config = perm.config or ""
    cache.set(event_permission_feature_key(slug), (slug, tutorial, config), timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return slug, tutorial, config


def get_event_permission_feature(slug):
    if not slug:
        return "def", None, None
    res = cache.get(event_permission_feature_key(slug))
    if not res:
        res = update_event_permission_feature(slug)
    return res


def clear_event_permission_cache(instance):
    cache.delete(event_permission_feature_key(instance.slug))


def index_permission_key(typ):
    return f"index_permission_key_{typ}"


def update_index_permission(typ):
    mapping = {"event": EventPermission, "assoc": AssocPermission}
    que = mapping[typ].objects.select_related("feature", "module")
    que = que.order_by("module__order", "number")
    res = que.values(
        "name",
        "descr",
        "slug",
        "hidden",
        "feature__placeholder",
        "feature__slug",
        "module__name",
        "module__icon",
    )
    cache.set(index_permission_key(typ), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def get_cache_index_permission(typ):
    res = cache.get(index_permission_key(typ))
    if not res:
        res = update_index_permission(typ)
    return res


def clear_index_permission_cache(typ):
    cache.delete(index_permission_key(typ))
