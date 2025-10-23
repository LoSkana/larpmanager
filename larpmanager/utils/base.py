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
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import get_payment_details
from larpmanager.cache.feature import get_assoc_features
from larpmanager.cache.links import cache_event_links
from larpmanager.cache.permission import get_assoc_permission_feature, get_cache_index_permission
from larpmanager.cache.role import get_assoc_roles, has_assoc_permission
from larpmanager.models.association import Association
from larpmanager.models.member import get_user_membership
from larpmanager.utils.auth import get_allowed_managed
from larpmanager.utils.exceptions import FeatureError, MembershipError, PermissionError


def def_user_ctx(request: HttpRequest) -> dict:
    """Build default user context with association data and permissions.

    Constructs a comprehensive context dictionary containing user information,
    association data, permissions, and configuration settings for template rendering.
    Handles cases where users are not authenticated or lack proper membership.

    Args:
        request: HTTP request object containing user and association information.
                Must have 'assoc' attribute with association data including 'id'.

    Returns:
        dict: Context dictionary containing:
            - Association data (id, name, settings, etc.)
            - User membership information and permissions
            - Feature flags and configuration
            - TinyMCE editor settings
            - Request metadata

    Raises:
        MembershipError: When user lacks proper association membership or
                        when accessing home page without valid association.
    """
    # Check if home page reached without valid association, redirect appropriately
    if request.assoc["id"] == 0:
        if hasattr(request, "user") and hasattr(request.user, "member"):
            assocs = [el.assoc for el in request.user.member.memberships.all()]
            raise MembershipError(assocs)
        raise MembershipError()

    # Initialize result dictionary with association ID
    res = {"a_id": request.assoc["id"]}

    # Copy all association data to context
    for s in request.assoc:
        res[s] = request.assoc[s]

    # Add user-specific data if authenticated member exists
    if hasattr(request, "user") and hasattr(request.user, "member"):
        res["member"] = request.user.member
        res["membership"] = get_user_membership(request.user.member, request.assoc["id"])

        # Get association permissions for the user
        get_index_assoc_permissions(res, request, request.assoc["id"], check=False)

        # Add user interface preferences and staff status
        res["interface_collapse_sidebar"] = request.user.member.get_config("interface_collapse_sidebar", False)
        res["is_staff"] = request.user.is_staff

    # Add cached event links to context
    res.update(cache_event_links(request))

    # Set default names for token/credit system if feature enabled
    if "token_credit" in res["features"]:
        if not res["token_name"]:
            res["token_name"] = _("Tokens")
        if not res["credit_name"]:
            res["credit_name"] = _("Credits")

    # Add TinyMCE editor configuration
    res["TINYMCE_DEFAULT_CONFIG"] = conf_settings.TINYMCE_DEFAULT_CONFIG
    res["TINYMCE_JS_URL"] = conf_settings.TINYMCE_JS_URL

    # Add current request function name for debugging/analytics
    if request and request.resolver_match:
        res["request_func_name"] = request.resolver_match.func.__name__

    return res


def is_shuttle(request):
    if not hasattr(request.user, "member"):
        return False
    return "shuttle" in request.assoc and request.user.member.id in request.assoc["shuttle"]


def update_payment_details(request, ctx):
    payment_details = fetch_payment_details(request.assoc["id"])
    ctx.update(payment_details)


def fetch_payment_details(assoc_id):
    assoc = Association.objects.only("slug", "key").get(pk=assoc_id)
    return get_payment_details(assoc)


def check_assoc_permission(request: HttpRequest, slug: str) -> dict:
    """Check and validate association permissions for a request.

    Validates that the user has the required association permission and that
    any necessary features are enabled. Sets up context data for rendering
    the view with proper permission and feature information.

    Args:
        request: HTTP request object containing user and association data
        slug: Permission slug identifier to check against user permissions

    Returns:
        dict: Context dictionary containing:
            - User context data from def_user_ctx
            - manage: Set to 1 to indicate management mode
            - exe_page: Set to 1 to indicate executive page
            - is_sidebar_open: Sidebar state from session
            - tutorial: Tutorial identifier if available
            - config: Configuration URL if user has config permissions

    Raises:
        PermissionError: If user lacks the required association permission
        FeatureError: If required feature is not enabled for the association
    """
    # Get base user context and validate permission
    ctx = def_user_ctx(request)
    if not has_assoc_permission(request, ctx, slug):
        raise PermissionError()

    # Retrieve feature configuration for this permission
    (feature, tutorial, config) = get_assoc_permission_feature(slug)

    # Check if required feature is enabled for this association
    if feature != "def" and feature not in request.assoc["features"]:
        raise FeatureError(path=request.path, feature=feature, run=0)

    # Set management context flags
    ctx["manage"] = 1
    ctx["exe_page"] = 1

    # Load association permissions and sidebar state
    get_index_assoc_permissions(ctx, request, request.assoc["id"])
    ctx["is_sidebar_open"] = request.session.get("is_sidebar_open", True)

    # Add tutorial information if not already present
    if "tutorial" not in ctx:
        ctx["tutorial"] = tutorial

    # Add configuration URL if user has config permissions
    if config and has_assoc_permission(request, ctx, "exe_config"):
        ctx["config"] = reverse("exe_config", args=[config])

    return ctx


def get_index_assoc_permissions(ctx: dict, request: HttpRequest, assoc_id: int, check: bool = True) -> None:
    """Get and set association permissions for index pages.

    Retrieves user roles and permissions for an association, then populates
    the context with permission data and UI state information.

    Args:
        ctx: Context dictionary to populate with permission data
        request: HTTP request object containing user and session data
        assoc_id: ID of the association to get permissions for
        check: Whether to raise PermissionError on access denial

    Raises:
        PermissionError: When user lacks permissions and check=True
    """
    # Get user role information and admin status
    (is_admin, user_assoc_permissions, names) = get_assoc_roles(request)

    # Check if user has any roles or admin privileges
    if not names and not is_admin:
        if check:
            raise PermissionError()
        else:
            return

    # Set role names in context for template rendering
    ctx["role_names"] = names

    # Retrieve available features for the association
    features = get_assoc_features(assoc_id)

    # Generate permission data for index display
    ctx["assoc_pms"] = get_index_permissions(ctx, features, is_admin, user_assoc_permissions, "assoc")

    # Set sidebar state from user session
    ctx["is_sidebar_open"] = request.session.get("is_sidebar_open", True)


def get_index_permissions(
    ctx: dict, features: list[str], has_default: bool, permissions: list[str], typ: str
) -> dict[tuple[str, str], list[dict]]:
    """Build index permissions structure based on user access and features.

    Filters and groups permissions by module based on user's access rights,
    available features, and permission type. Only includes visible permissions
    that the user is allowed to access.

    Args:
        ctx: Context dictionary containing association information
        features: List of available feature slugs for the user
        has_default: Whether user has default permissions (bypasses specific checks)
        permissions: List of specific permission slugs the user has
        typ: Permission type to filter (e.g., 'association', 'event')

    Returns:
        Dictionary mapping module info tuples (name, icon) to lists of
        permission dictionaries for that module
    """
    res = {}

    # Get cached permissions for the specified type
    for ar in get_cache_index_permission(typ):
        # Skip hidden permissions
        if ar["hidden"]:
            continue

        # Check if permission is allowed in current context
        if not is_allowed_managed(ar, ctx):
            continue

        # Check user has specific permission (unless has default access)
        if not has_default and ar["slug"] not in permissions:
            continue

        # Check feature is available (skip placeholder features)
        if not ar["feature__placeholder"] and ar["feature__slug"] not in features:
            continue

        # Group permissions by module
        mod_name = (_(ar["module__name"]), ar["module__icon"])
        if mod_name not in res:
            res[mod_name] = []
        res[mod_name].append(ar)

    return res


def is_allowed_managed(ar: dict, ctx: dict) -> bool:
    """Check if user is allowed to access managed association features."""
    # Check if the association skin is managed and the user is not staff
    if ctx.get("skin_managed", False) and not ctx.get("is_staff", False):
        allowed = get_allowed_managed()

        # If the feature is a placeholder different than the management of events
        if ar["feature__placeholder"] and ar["slug"] not in allowed:
            return False

    return True
