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
from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

from larpmanager.cache.permission import get_association_permission_feature, get_event_permission_feature
from larpmanager.utils.auth.permission import (
    get_index_association_permissions,
    get_index_event_permissions,
    has_association_permission,
    has_event_permission,
)
from larpmanager.utils.core.base import get_context, get_event_context
from larpmanager.utils.core.dashboard import set_sidebar_badges
from larpmanager.utils.core.exceptions import FeatureError, UserPermissionError
from larpmanager.utils.edit.exe_action import ExeAction
from larpmanager.utils.edit.orga_action import OrgaAction

if TYPE_CHECKING:
    from django.http import HttpRequest


def check_association_context(request: HttpRequest, permission_slug: str | list[str] | None = None) -> dict:
    """Check and validate association permissions for a request.

    Validates that the user has the required association permission and that
    any necessary features are enabled. Sets up context data for rendering
    the view with proper permission and feature information.

    Args:
        request: HTTP request object containing user and association data
        permission_slug: Required permission(s). Can be a single permission slug or list of permission slugs.

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
    context = get_context(request)
    if not has_association_permission(request, context, permission_slug):
        raise UserPermissionError

    # Retrieve feature configuration for this permission
    (required_feature, tutorial_slug, config_slug) = get_association_permission_feature(permission_slug)

    # Check if required feature is enabled for this association
    if required_feature != "def" and required_feature not in context["features"]:
        raise FeatureError(path=request.path, feature=required_feature, run=0)

    # Set management context flags
    context["manage"] = 1
    context["exe_page"] = 1

    # Load association permissions
    get_index_association_permissions(request, context, context["association_id"])

    # Add tutorial information if not already present
    if "tutorial" not in context:
        context["tutorial"] = tutorial_slug

    # Add configuration URL if user has config permissions
    if config_slug and has_association_permission(request, context, "exe_config"):
        context["config"] = reverse("exe_config", args=[config_slug])

    # Inject page_info from the corresponding form class if available.
    if permission_slug and isinstance(permission_slug, str):
        action = ExeAction.from_string(permission_slug)
        if action and "form" in action.config and hasattr(action.config["form"], "page_info"):
            context["page_info"] = action.config["form"].page_info

    # Compute pending-work counts shown as badges on the sidebar links
    set_sidebar_badges(request, context)

    return context


def check_event_context(request: HttpRequest, event_slug: str, permission_slug: str | list[str] | None = None) -> dict:
    """Check event permissions and prepare management context.

    Validates user permissions for event management operations and prepares
    the necessary context including features, tutorials, and configuration links.

    Args:
        request: Django HTTP request object containing user and session data
        event_slug: Event slug identifier for the target event
        permission_slug: Required permission(s). Can be a single permission slug or list of permission slugs.

    Returns:
        Dictionary containing event context with management permissions including:
            - Event and run objects
            - Available features
            - Tutorial information
            - Configuration links
            - Management flags

    Raises:
        PermissionError: If user lacks required permissions for the event
        FeatureError: If required feature is not enabled for the event

    """
    # Get basic event context and run information
    context = get_event_context(request, event_slug)

    # Verify user has the required permissions for this event
    if not has_event_permission(request, context, event_slug, permission_slug):
        raise UserPermissionError

    # Process permission-specific features and configuration
    if permission_slug:
        # Handle permission lists by taking the first permission
        if isinstance(permission_slug, list):
            permission_slug = permission_slug[0]

        # Get feature configuration for this permission
        (feature_name, tutorial_slug, config_section) = get_event_permission_feature(permission_slug)

        # Add tutorial information if not already present
        if "tutorial" not in context:
            context["tutorial"] = tutorial_slug

        # Add configuration link if user has config permissions
        if config_section and has_event_permission(request, context, event_slug, "orga_config"):
            context["config"] = reverse("orga_config", args=[context["run"].get_slug(), config_section])

        # Verify required feature is enabled for this event
        if feature_name != "def" and feature_name not in context["features"]:
            raise FeatureError(path=request.path, feature=feature_name, run=context["run"].id)

        # Mark active sidebar entry for redirect-style views
        context["sidebar_active"] = permission_slug

        # Inject page_info from the corresponding form class if available.
        action = OrgaAction.from_string(permission_slug)
        if action and "form" in action.config and hasattr(action.config["form"], "page_info"):
            context["page_info"] = action.config["form"].page_info

    # Load additional event permissions and management context
    get_index_event_permissions(request, context, event_slug)

    # Set management page flags
    context["orga_page"] = 1
    context["manage"] = 1

    # Compute pending-work counts shown as badges on the sidebar links
    set_sidebar_badges(request, context)

    return context
