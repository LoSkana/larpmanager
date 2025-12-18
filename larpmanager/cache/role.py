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

from larpmanager.cache.feature import get_association_features, get_event_features
from larpmanager.models.access import AssociationRole, EventRole
from larpmanager.utils.core.exceptions import UserPermissionError


def cache_association_role_key(association_role_id: int) -> str:
    """Generate cache key for association role."""
    return f"association_role_{association_role_id}"


def get_association_role(ar: AssociationRole) -> tuple[str, list[str]]:
    """Get association role name and available permission slugs.

    Args:
        ar: AssociationRole instance to extract permissions from

    Returns:
        Tuple containing role name and list of permission slugs

    """
    permission_slugs = []
    features = get_association_features(ar.association_id)

    # Filter permissions based on feature availability and placeholders
    for permission_slug, feature_slug, is_placeholder in ar.permissions.values_list(
        "slug",
        "feature__slug",
        "feature__placeholder",
    ):
        if not is_placeholder and feature_slug not in features:
            continue
        permission_slugs.append(permission_slug)

    return ar.name, permission_slugs


def get_cache_association_role(ar_id: int) -> dict:
    """Get cached association role data by ID.

    Retrieves association role data from cache if available, otherwise
    fetches from database and caches the result.

    Args:
        ar_id: The association role ID to retrieve.

    Returns:
        Dictionary containing association role data.

    Raises:
        PermissionError: If the association role cannot be found or accessed.

    """
    # Generate cache key for this association role
    cache_key = cache_association_role_key(ar_id)

    # Try to get cached result first
    cached_result = cache.get(cache_key)

    if cached_result is None:
        # Cache miss - fetch from database
        try:
            association_role = AssociationRole.objects.get(pk=ar_id)
        except Exception as err:
            # Convert any database error to permission error
            raise UserPermissionError from err

        # Process the association role data
        cached_result = get_association_role(association_role)

        # Cache the result for future requests
        cache.set(cache_key, cached_result, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_result


def remove_association_role_cache(association_role_id: int) -> None:
    """Delete the cached association role."""
    key = cache_association_role_key(association_role_id)
    cache.delete(key)


def cache_event_role_key(assignment_role_id: int) -> str:
    """Return cache key for event role assignment."""
    return f"event_role_{assignment_role_id}"


def get_event_role(assignment_role: EventRole) -> tuple[str, list[str]]:
    """Get event role name and available permission slugs.

    Args:
        assignment_role: Assignment role object with permissions and event access.

    Returns:
        Tuple of role name and list of available permission slugs.

    """
    available_permission_slugs = []
    event_features = get_event_features(assignment_role.event_id)

    # Filter permissions based on feature availability and placeholder status
    for permission_slug, feature_slug, is_placeholder in assignment_role.permissions.values_list(
        "slug",
        "feature__slug",
        "feature__placeholder",
    ):
        if not is_placeholder and feature_slug not in event_features:
            continue
        available_permission_slugs.append(permission_slug)

    return assignment_role.name, available_permission_slugs


def get_cache_event_role(ev_id: int) -> dict:
    """Retrieve event role data from cache or database.

    Attempts to fetch event role information from cache first. If not found,
    retrieves from database, caches the result, and returns it.

    Args:
        ev_id: The event ID to retrieve role data for.

    Returns:
        Dictionary containing event role information.

    Raises:
        PermissionError: If the event role cannot be found or accessed.

    """
    # Generate cache key for this specific event role
    cache_key = cache_event_role_key(ev_id)
    cached_result = cache.get(cache_key)

    # If not in cache, fetch from database
    if cached_result is None:
        try:
            # Retrieve EventRole object from database
            event_role = EventRole.objects.get(pk=ev_id)
        except Exception as error:
            # Convert any database error to PermissionError
            raise UserPermissionError from error

        # Process the event role data
        cached_result = get_event_role(event_role)

        # Cache the result for future requests
        cache.set(cache_key, cached_result, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_result


def remove_event_role_cache(assignment_role_id: int) -> None:
    """Remove cached event role data for the given assignment role ID."""
    key = cache_event_role_key(assignment_role_id)
    cache.delete(key)
