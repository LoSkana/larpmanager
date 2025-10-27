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

from larpmanager.models.access import AssociationPermission, EventPermission

logger = logging.getLogger(__name__)


def association_permission_feature_key(permission_slug):
    """Generate cache key for association permission features.

    Args:
        permission_slug (str): Permission slug

    Returns:
        str: Cache key for association permission feature
    """
    return f"association_permission_feature_{permission_slug}"


def update_association_permission_feature(slug: str) -> tuple[str, str, str]:
    """Update cached association permission feature data.

    Retrieves association permission data by slug, processes the feature information,
    and updates the cache with the processed data.

    Args:
        slug: Permission slug to look up

    Returns:
        A tuple containing (feature_slug, tutorial, config) where:
            - feature_slug: The feature slug or 'def' if placeholder
            - tutorial: Feature tutorial text or empty string
            - config: Permission config text or empty string
    """
    # Fetch permission with related feature data to minimize queries
    perm = AssociationPermission.objects.select_related("feature").get(slug=slug)
    feature = perm.feature

    # Use default slug for placeholder features, otherwise use actual feature slug
    if feature.placeholder:
        slug = "def"
    else:
        slug = feature.slug

    # Extract tutorial and config data with fallback to empty strings
    tutorial = feature.tutorial or ""
    config = perm.config or ""

    # Cache the processed data for future requests
    cache.set(
        association_permission_feature_key(slug), (slug, tutorial, config), timeout=conf_settings.CACHE_TIMEOUT_1_DAY
    )
    return slug, tutorial, config


def get_association_permission_feature(slug: str) -> tuple[str, str | None, dict | None]:
    """Get cached association permission feature data.

    Retrieves feature data for an association permission from cache first,
    falling back to database if not cached.

    Args:
        slug: Permission slug identifier

    Returns:
        A tuple containing:
            - feature_slug (str): The feature slug, defaults to "def" if slug is empty
            - tutorial (str | None): Tutorial content if available
            - config (dict | None): Configuration data if available
    """
    # Return default values if no slug provided
    if not slug:
        return "def", None, None

    # Attempt to retrieve from cache first
    cached_feature_data = cache.get(association_permission_feature_key(slug))

    # If cache miss, update cache and return fresh data
    if cached_feature_data is None:
        cached_feature_data = update_association_permission_feature(slug)

    return cached_feature_data


def clear_association_permission_cache(association):
    cache.delete(association_permission_feature_key(association.slug))


def event_permission_feature_key(permission_slug):
    """Generate cache key for event permission features.

    Args:
        permission_slug (str): Permission slug

    Returns:
        str: Cache key for event permission feature
    """
    return f"event_permission_feature_{permission_slug}"


def update_event_permission_feature(slug: str) -> tuple[str, str, str]:
    """Update event permission feature cache with slug, tutorial, and config data.

    Args:
        slug: The permission slug to look up

    Returns:
        A tuple containing (feature_slug, tutorial, config):
            - feature_slug: The feature slug or "def" if placeholder
            - tutorial: The feature tutorial text or empty string
            - config: The permission config or empty string
    """
    try:
        # Fetch permission with related feature to avoid additional queries
        perm = EventPermission.objects.select_related("feature").get(slug=slug)
    except ObjectDoesNotExist:
        logger.warning(f"Permission slug does not exist: {slug}")
        return "", "", ""

    # Extract feature from permission
    feature = perm.feature

    # Determine the appropriate slug based on feature type
    if feature.placeholder:
        slug = "def"
    else:
        slug = feature.slug

    # Extract tutorial and config with fallback to empty strings
    tutorial = feature.tutorial or ""
    config = perm.config or ""

    # Cache the result for 1 day to improve performance
    cache.set(event_permission_feature_key(slug), (slug, tutorial, config), timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return slug, tutorial, config


def get_event_permission_feature(slug: str | None) -> tuple[str, None, None]:
    """Get event permission feature from cache or update if not cached.

    Args:
        slug: Event slug identifier

    Returns:
        Tuple containing permission feature data
    """
    # Return default values if no slug provided
    if not slug:
        return "def", None, None

    # Attempt to retrieve from cache first
    cached_feature = cache.get(event_permission_feature_key(slug))

    # Update cache if no cached result found
    if cached_feature is None:
        cached_feature = update_event_permission_feature(slug)

    return cached_feature


def clear_event_permission_cache(event_permission):
    cache.delete(event_permission_feature_key(event_permission.slug))


def index_permission_key(permission_type):
    return f"index_permission_key_{permission_type}"


def update_index_permission(typ: str) -> list[dict]:
    """Update and cache permission index for given type.

    Retrieves permissions from database, orders them by module and number,
    then caches the result for efficient access.

    Args:
        typ: Permission type, either 'event' or 'association'

    Returns:
        List of permission dictionaries with feature and module information

    Raises:
        KeyError: If typ is not 'event' or 'association'
    """
    # Map permission type to corresponding model class
    mapping = {"event": EventPermission, "association": AssociationPermission}

    # Get queryset with related feature and module data
    que = mapping[typ].objects.select_related("feature", "module")

    # Order by module priority and permission number
    que = que.order_by("module__order", "number")

    # Extract required fields for caching
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

    # Cache result with 1-day timeout
    cache.set(index_permission_key(typ), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def get_cache_index_permission(permission_type: str) -> list:
    """Get or update cached permission index for a given type.

    Args:
        permission_type: The permission type to retrieve from cache.

    Returns:
        The cached or freshly updated permission index.
    """
    # Attempt to retrieve from cache
    cached_result = cache.get(index_permission_key(permission_type))

    # Update cache if not found
    if cached_result is None:
        cached_result = update_index_permission(permission_type)

    return cached_result


def clear_index_permission_cache(permission_type):
    cache.delete(index_permission_key(permission_type))
