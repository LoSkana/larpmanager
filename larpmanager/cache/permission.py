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

from larpmanager.models.access import AssocPermission, EventPermission


def assoc_permission_feature_key(slug):
    return f"assoc_permission_feature_{slug}"


def update_assoc_permission_feature(slug):
    feature = AssocPermission.objects.select_related("feature").get(slug=slug).feature
    if feature.placeholder:
        res = "def"
    else:
        res = feature.slug
    cache.set(assoc_permission_feature_key(slug), res)
    return res


def get_assoc_permission_feature(slug):
    res = cache.get(assoc_permission_feature_key(slug))
    if not res:
        res = update_assoc_permission_feature(slug)
    return res


def event_permission_feature_key(slug):
    return f"event_permission_feature_{slug}"


def update_event_permission_feature(slug):
    feature = EventPermission.objects.select_related("feature").get(slug=slug).feature
    if feature.placeholder:
        res = "def"
    else:
        res = feature.slug
    cache.set(event_permission_feature_key(slug), res)
    return res


def get_event_permission_feature(slug):
    res = cache.get(event_permission_feature_key(slug))
    if not res:
        res = update_event_permission_feature(slug)
    return res
