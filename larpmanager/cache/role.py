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
from django.http import HttpRequest

from larpmanager.cache.feature import get_assoc_features, get_event_features
from larpmanager.cache.links import cache_event_links
from larpmanager.cache.permission import get_assoc_permission_feature, get_event_permission_feature
from larpmanager.models.access import AssocRole, EventRole
from larpmanager.utils.auth import get_allowed_managed
from larpmanager.utils.exceptions import PermissionError


def cache_assoc_role_key(ar_id):
    return f"assoc_role_{ar_id}"


def get_assoc_role(ar: AssocRole) -> tuple[str, list[str]]:
    """Get association role name and available permission slugs.

    Args:
        ar: AssocRole instance to extract permissions from

    Returns:
        Tuple containing role name and list of permission slugs
    """
    ls = []
    features = get_assoc_features(ar.assoc_id)

    # Filter permissions based on feature availability and placeholders
    for el in ar.permissions.values_list("slug", "feature__slug", "feature__placeholder"):
        if not el[2] and el[1] not in features:
            continue
        ls.append(el[0])

    return ar.name, ls


def get_cache_assoc_role(ar_id: int) -> dict:
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
    key = cache_assoc_role_key(ar_id)

    # Try to get cached result first
    res = cache.get(key)

    if res is None:
        # Cache miss - fetch from database
        try:
            ar = AssocRole.objects.get(pk=ar_id)
        except Exception as err:
            # Convert any database error to permission error
            raise PermissionError() from err

        # Process the association role data
        res = get_assoc_role(ar)

        # Cache the result for future requests
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def remove_association_role_cache(ar_id):
    key = cache_assoc_role_key(ar_id)
    cache.delete(key)


def get_assoc_roles(request: HttpRequest) -> tuple[bool, dict[str, int], list[str]]:
    """Get association roles and permissions for the current user.

    Args:
        request: Django HTTP request object containing user information

    Returns:
        tuple: A 3-tuple containing:
            - bool: True if user is admin (role 1) or superuser, False otherwise
            - dict: Mapping of permission slugs to integer values (1 for granted)
            - list: List of role names assigned to the user
    """
    pms = {}

    # Superusers have all permissions automatically
    if request.user.is_superuser:
        return True, [], ["superuser"]

    # Get cached event context and role information
    ctx = cache_event_links(request)
    is_admin = False
    names = []

    # Process each association role assigned to the user
    for num, el in ctx["assoc_role"].items():
        # Role number 1 indicates admin privileges
        if num == 1:
            is_admin = True

        # Extract role name and associated permission slugs
        (name, slugs) = get_cache_assoc_role(el)
        names.append(name)

        # Grant all permissions associated with this role
        for slug in slugs:
            pms[slug] = 1

    return is_admin, pms, names


def has_assoc_permission(request: HttpRequest, ctx: dict, perm: str) -> bool:
    """Check if the user has the specified association permission.

    Args:
        request: The HTTP request object containing user information
        ctx: Context dictionary containing association and permission data
        perm: The permission string to check for

    Returns:
        bool: True if user has the permission, False otherwise

    Note:
        Returns True for admin users regardless of specific permissions.
        Returns False if user has no member attribute or permission is managed.
    """
    # Check if user has a member attribute (is authenticated member)
    if not hasattr(request.user, "member"):
        return False

    # Check if the permission is managed (restricted)
    if check_managed(ctx, perm):
        return False

    # Get user's association roles and permissions
    (admin, permissions, names) = get_assoc_roles(request)

    # Admin users have all permissions
    if admin:
        return True

    # If no specific permission required, allow access
    if not perm:
        return True

    # Check if user has the specific permission
    return perm in permissions


def cache_event_role_key(ar_id):
    return f"event_role_{ar_id}"


def get_event_role(ar) -> tuple[str, list[str]]:
    """Get event role name and available permission slugs.

    Args:
        ar: Assignment role object with permissions and event access.

    Returns:
        Tuple of role name and list of available permission slugs.
    """
    ls = []
    features = get_event_features(ar.event_id)

    # Filter permissions based on feature availability and placeholder status
    for el in ar.permissions.values_list("slug", "feature__slug", "feature__placeholder"):
        if not el[2] and el[1] not in features:
            continue
        ls.append(el[0])

    return ar.name, ls


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
    key = cache_event_role_key(ev_id)
    res = cache.get(key)

    # If not in cache, fetch from database
    if res is None:
        try:
            # Retrieve EventRole object from database
            ar = EventRole.objects.get(pk=ev_id)
        except Exception as err:
            # Convert any database error to PermissionError
            raise PermissionError() from err

        # Process the event role data
        res = get_event_role(ar)

        # Cache the result for future requests
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def remove_event_role_cache(ar_id):
    key = cache_event_role_key(ar_id)
    cache.delete(key)


def get_event_roles(request: HttpRequest, slug: str) -> tuple[bool, dict[str, int], list[str]]:
    """Get user's event roles and permissions for a specific event slug.

    Args:
        request: Django HTTP request object with authenticated user
        slug: Event slug identifier

    Returns:
        tuple: A tuple containing:
            - is_organizer (bool): True if user is an organizer for this event
            - permissions_dict (dict[str, int]): Dictionary mapping permission slugs to values
            - role_names_list (list[str]): List of role names the user has for this event
    """
    pms = {}

    # Extract base slug by splitting on hyphen and taking first part
    slug = slug.split("-", 1)[0]

    # Superusers have full access to all events
    if request.user.is_superuser:
        return True, [], ["superuser"]

    # Get cached event context and check if user has roles for this event
    ctx = cache_event_links(request)
    if slug not in ctx["event_role"]:
        return False, [], []

    # Initialize tracking variables for user's roles in this event
    is_organizer = False
    names = []

    # Process each role the user has for this event
    for num, el in ctx["event_role"][slug].items():
        # Role number 1 indicates organizer status
        if num == 1:
            is_organizer = True

        # Extract role name and permission slugs from cached role data
        (name, slugs) = get_cache_event_role(el)
        names.append(name)

        # Add all permission slugs for this role to permissions dictionary
        for pm_slug in slugs:
            pms[pm_slug] = 1

    return is_organizer, pms, names


def has_event_permission(request: HttpRequest, ctx: dict, event_slug: str, permission_name=None) -> bool:
    """Check if user has permission for a specific event.

    Args:
        request: Django HTTP request object containing user information
        ctx: Context dictionary containing association role information
        event_slug: Event slug identifier
        permission_name: Permission name(s) to check. Can be string, list, or None

    Returns:
        bool: True if user has the required event permission, False otherwise

    Note:
        If permission_name is None, returns True if user has any event role.
        If permission_name is a list, returns True if user has any of the permissions.
    """
    # Early return if request is invalid or user lacks member attribute
    if not request or not hasattr(request.user, "member") or check_managed(ctx, permission_name, assoc=False):
        return False

    # Check if user has admin role in association (role 1)
    if "assoc_role" in ctx and 1 in ctx["assoc_role"]:
        return True

    # Get event-specific roles and permissions for the user
    (is_organizer, user_permissions, role_names) = get_event_roles(request, event_slug)

    # Organizer has all permissions
    if is_organizer:
        return True

    # If no specific permission requested, check if user has any event role
    if not permission_name:
        return len(role_names) > 0

    # Handle multiple permissions (list)
    if isinstance(permission_name, list):
        return any(permission in user_permissions for permission in permission_name)

    # Check single permission
    return permission_name in user_permissions


def check_managed(ctx: dict, perm: str, assoc: bool = True) -> bool:
    """Check if permission is restricted for managed association skins.

    This function determines whether a permission should be restricted based on
    whether the association skin is managed and the user's staff status.

    Args:
        ctx: Context dictionary containing skin_managed and is_staff flags
        perm: Permission string to check for restrictions
        assoc: Whether to check association permissions (True) or event
               permissions (False). Defaults to True.

    Returns:
        True if permission is restricted due to managed skin, False otherwise.

    Note:
        Returns False if skin is not managed, user is staff, permission is
        allowed for managed skins, or permission placeholder is not "def".
    """
    # Check if the association skin is managed and the user is not staff
    # If skin is not managed or user is staff, no restrictions apply
    if not ctx.get("skin_managed", False) or ctx.get("is_staff", False):
        return False

    # Check if this permission is explicitly allowed for managed skins
    # Some permissions may bypass managed skin restrictions
    if perm in get_allowed_managed():
        return False

    # Get permission feature information based on association or event context
    # This determines the permission's configuration and restrictions
    if assoc:
        placeholder, _, _ = get_assoc_permission_feature(perm)
    else:
        placeholder, _, _ = get_event_permission_feature(perm)

    # Only restrict permissions with "def" placeholder
    # Other placeholder types may have different restriction rules
    if placeholder != "def":
        return False

    # Permission should be restricted for managed skins
    return True
