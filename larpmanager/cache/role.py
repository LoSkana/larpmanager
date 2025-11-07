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
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.feature import get_association_features, get_event_features
from larpmanager.cache.permission import (
    get_association_permission_feature,
    get_cache_index_permission,
    get_event_permission_feature,
)
from larpmanager.models.access import AssociationRole, EventRole
from larpmanager.utils.auth import get_allowed_managed, is_lm_admin
from larpmanager.utils.exceptions import UserPermissionError


def cache_association_role_key(association_role_id):
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
        "slug", "feature__slug", "feature__placeholder"
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
            raise UserPermissionError() from err

        # Process the association role data
        cached_result = get_association_role(association_role)

        # Cache the result for future requests
        cache.set(cache_key, cached_result, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_result


def remove_association_role_cache(association_role_id: int) -> None:
    # Delete the cached association role
    key = cache_association_role_key(association_role_id)
    cache.delete(key)


def get_association_roles(request: HttpRequest, context: dict) -> tuple[bool, dict[str, int], list[str]]:
    """Get association roles and permissions for the current user.

    Args:
        request: Django HTTP request object containing user information
        context: Dict with context informations

    Returns:
        tuple: A 3-tuple containing:
            - bool: True if user is admin (role 1) or superuser, False otherwise
            - dict: Mapping of permission slugs to integer values (1 for granted)
            - list: List of role names assigned to the user
    """
    permissions = {}

    # Superusers have all permissions automatically
    if is_lm_admin(request):
        return True, {}, ["superuser"]

    # Get cached event context and role information
    is_admin = False
    role_names = []

    # Process each association role assigned to the user
    for role_number, role_data in context["association_role"].items():
        # Role number 1 indicates admin privileges
        if role_number == 1:
            is_admin = True

        # Extract role name and associated permission slugs
        (role_name, permission_slugs) = get_cache_association_role(role_data)
        role_names.append(role_name)

        # Grant all permissions associated with this role
        for permission_slug in permission_slugs:
            permissions[permission_slug] = 1

    return is_admin, permissions, role_names


def has_association_permission(request: HttpRequest, context: dict, permission: str) -> bool:
    """Check if the user has the specified association permission.

    Args:
        request: The HTTP request object containing user information
        context: Context dictionary containing association and permission data
        permission: The permission string to check for

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
    if check_managed(context, permission):
        return False

    # Get user's association roles and permissions
    (is_admin, user_permissions, role_names) = get_association_roles(request, context)

    # Admin users have all permissions
    if is_admin:
        return True

    # If no specific permission required, allow access
    if not permission:
        return True

    # Check if user has the specific permission
    return permission in user_permissions


def get_index_association_permissions(
    context: dict, request: HttpRequest, association_id: int, check: bool = True
) -> None:
    """Get and set association permissions for index pages.

    Retrieves user roles and permissions for an association, then populates
    the context with permission data and UI state information.

    Args:
        context: Context dictionary to populate with permission data
        request: HTTP request object containing user and session data
        association_id: ID of the association to get permissions for
        check: Whether to raise PermissionError on access denial

    Raises:
        PermissionError: When user lacks permissions and check=True
    """
    # Get user role information and admin status
    (is_admin, user_association_permissions, role_names) = get_association_roles(request, context)

    # Check if user has any roles or admin privileges
    if not role_names and not is_admin:
        if check:
            raise UserPermissionError()
        else:
            return

    # Set role names in context for template rendering
    context["role_names"] = role_names

    # Retrieve available features for the association
    features = context.get("features") or get_association_features(association_id)

    # Generate permission data for index display
    context["association_pms"] = get_index_permissions(
        context, features, is_admin, user_association_permissions, "association"
    )

    # Set sidebar state from user session
    context["is_sidebar_open"] = request.session.get("is_sidebar_open", True)


def cache_event_role_key(assignment_role_id: int) -> str:
    """Return cache key for event role assignment."""
    return f"event_role_{assignment_role_id}"


def get_event_role(assignment_role) -> tuple[str, list[str]]:
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
        "slug", "feature__slug", "feature__placeholder"
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
            raise UserPermissionError() from error

        # Process the event role data
        cached_result = get_event_role(event_role)

        # Cache the result for future requests
        cache.set(cache_key, cached_result, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_result


def remove_event_role_cache(assignment_role_id: int) -> None:
    """Remove cached event role data for the given assignment role ID."""
    key = cache_event_role_key(assignment_role_id)
    cache.delete(key)


def get_event_roles(request: HttpRequest, context, slug: str) -> tuple[bool, dict[str, int], list[str]]:
    """Get user's event roles and permissions for a specific event slug.

    Args:
        request: Django HTTP request object with authenticated user
        context: Dict with context informations
        slug: Event slug identifier

    Returns:
        tuple: A tuple containing:
            - is_organizer (bool): True if user is an organizer for this event
            - permissions_dict (dict[str, int]): Dictionary mapping permission slugs to values
            - role_names_list (list[str]): List of role names the user has for this event
    """
    permission_slugs = {}

    # Extract base slug by splitting on hyphen and taking first part
    slug = slug.split("-", 1)[0]

    # Superusers have full access to all events
    if is_lm_admin(request):
        return True, {}, ["superuser"]

    # Get cached event context and check if user has roles for this event
    if slug not in context["event_role"]:
        return False, {}, []

    # Initialize tracking variables for user's roles in this event
    is_organizer = False
    role_names = []

    # Process each role the user has for this event
    for role_number, role_element in context["event_role"][slug].items():
        # Role number 1 indicates organizer status
        if role_number == 1:
            is_organizer = True

        # Extract role name and permission slugs from cached role data
        (role_name, permission_slug_list) = get_cache_event_role(role_element)
        role_names.append(role_name)

        # Add all permission slugs for this role to permissions dictionary
        for permission_slug in permission_slug_list:
            permission_slugs[permission_slug] = 1

    return is_organizer, permission_slugs, role_names


def has_event_permission(request: HttpRequest, context: dict, event_slug: str, permission_name=None) -> bool:
    """Check if user has permission for a specific event.

    Args:
        request: Django HTTP request object containing user information
        context: Context dictionary containing association role information
        event_slug: Event slug identifier
        permission_name: Permission name(s) to check. Can be string, list, or None

    Returns:
        bool: True if user has the required event permission, False otherwise

    Note:
        If permission_name is None, returns True if user has any event role.
        If permission_name is a list, returns True if user has any of the permissions.
    """
    # Early return if request is invalid or user lacks member attribute
    if (
        not request
        or not hasattr(request.user, "member")
        or check_managed(context, permission_name, is_association=False)
    ):
        return False

    # Check if user has admin role in association (role 1)
    if "association_role" in context and 1 in context["association_role"]:
        return True

    # Get event-specific roles and permissions for the user
    (is_organizer, user_permissions, role_names) = get_event_roles(request, context, event_slug)

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


def get_index_event_permissions(request: HttpRequest, context: dict, event_slug: str, enforce_check: bool = True):
    """Load event permissions and roles for management interface.

    Args:
        context (dict): Context dictionary to update
        request: Django HTTP request object
        event_slug (str): Event slug
        enforce_check (bool): Whether to enforce permission requirements

    Side effects:
        Updates context with role names and event permissions

    Raises:
        PermissionError: If enforce_check=True and user has no permissions
    """
    (is_organizer, user_event_permissions, role_names) = get_event_roles(request, context, event_slug)
    if "association_role" in context and 1 in context["association_role"]:
        is_organizer = True
    if enforce_check and not role_names and not is_organizer:
        raise UserPermissionError()
    if role_names:
        context["role_names"] = role_names
    event_features = context.get("features") or get_event_features(context["event"].id)
    context["event_pms"] = get_index_permissions(context, event_features, is_organizer, user_event_permissions, "event")


def check_managed(context: dict, permission: str, is_association: bool = True) -> bool:
    """Check if permission is restricted for managed association skins.

    This function determines whether a permission should be restricted based on
    whether the association skin is managed and the user's staff status.

    Args:
        context: Context dictionary containing skin_managed and is_staff flags
        permission: Permission string to check for restrictions
        is_association: Whether to check association permissions (True) or event
               permissions (False). Defaults to True.

    Returns:
        True if permission is restricted due to managed skin, False otherwise.

    Note:
        Returns False if skin is not managed, user is staff, permission is
        allowed for managed skins, or permission placeholder is not "def".
    """
    # Check if the association skin is managed and the user is not staff
    # If skin is not managed or user is staff, no restrictions apply
    if not context.get("skin_managed", False) or context.get("is_staff", False):
        return False

    # Check if this permission is explicitly allowed for managed skins
    # Some permissions may bypass managed skin restrictions
    if permission in get_allowed_managed():
        return False

    # Get permission feature information based on association or event context
    # This determines the permission's configuration and restrictions
    if is_association:
        placeholder, _, _ = get_association_permission_feature(permission)
    else:
        placeholder, _, _ = get_event_permission_feature(permission)

    # Only restrict permissions with "def" placeholder
    # Other placeholder types may have different restriction rules
    if placeholder != "def":
        return False

    # Permission should be restricted for managed skins
    return True


def get_index_permissions(
    context: dict, features: dict, has_default: bool, permissions: dict, permission_type: str
) -> dict[tuple[str, str], list[dict]]:
    """Build index permissions structure based on user access and features.

    Filters and groups permissions by module based on user's access rights,
    available features, and permission type. Only includes visible permissions
    that the user is allowed to access.

    Args:
        context: Context dictionary containing association information
        features: Dict of available feature slugs for the user
        has_default: Whether user has default permissions (bypasses specific checks)
        permissions: Dict of specific permission slugs the user has
        permission_type: Permission type to filter (e.g., 'association', 'event')

    Returns:
        Dictionary mapping module info tuples (name, icon) to lists of
        permission dictionaries for that module
    """
    permissions_by_module = {}

    # Get cached permissions for the specified type
    for permission_record in get_cache_index_permission(permission_type):
        # Skip hidden permissions
        if permission_record["hidden"]:
            continue

        # Check if permission is allowed in current context
        if not is_allowed_managed(permission_record, context):
            continue

        # Check user has specific permission (unless has default access)
        if not has_default and permission_record["slug"] not in permissions:
            continue

        # Check feature is available (skip placeholder features)
        if not permission_record["feature__placeholder"] and permission_record["feature__slug"] not in features:
            continue

        # Group permissions by module
        module_key = (_(permission_record["module__name"]), permission_record["module__icon"])
        if module_key not in permissions_by_module:
            permissions_by_module[module_key] = []
        permissions_by_module[module_key].append(permission_record)

    return permissions_by_module


def is_allowed_managed(ar: dict, context: dict) -> bool:
    """Check if user is allowed to access managed association features."""
    # Check if the association skin is managed and the user is not staff
    if context.get("skin_managed", False) and not context.get("is_staff", False):
        allowed = get_allowed_managed()

        # If the feature is a placeholder different than the management of events
        if ar["feature__placeholder"] and ar["slug"] not in allowed:
            return False

    return True
