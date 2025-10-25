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
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import get_payment_details
from larpmanager.cache.links import cache_event_links
from larpmanager.cache.role import get_index_assoc_permissions
from larpmanager.models.association import Association
from larpmanager.models.member import get_user_membership
from larpmanager.utils.exceptions import MembershipError


def def_user_context(request: HttpRequest) -> dict:
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
            user_associations = [membership.assoc for membership in request.user.member.memberships.all()]
            raise MembershipError(user_associations)
        raise MembershipError()

    # Initialize result dictionary with association ID
    context = {"association_id": request.assoc["id"]}

    # Copy all association data to context
    for assoc_key in request.assoc:
        context[assoc_key] = request.assoc[assoc_key]

    # Add user-specific data if authenticated member exists
    if hasattr(request, "user") and hasattr(request.user, "member"):
        context["member"] = request.user.member
        context["membership"] = get_user_membership(request.user.member, context["association_id"])

        # Get association permissions for the user
        get_index_assoc_permissions(context, request, context["association_id"], check=False)

        # Add user interface preferences and staff status
        context["interface_collapse_sidebar"] = request.user.member.get_config("interface_collapse_sidebar", False)
        context["is_staff"] = request.user.is_staff

    # Add cached event links to context
    cache_event_links(request, context)

    # Set default names for token/credit system if feature enabled
    if "token_credit" in context["features"]:
        if not context["token_name"]:
            context["token_name"] = _("Tokens")
        if not context["credit_name"]:
            context["credit_name"] = _("Credits")

    # Add TinyMCE editor configuration
    context["TINYMCE_DEFAULT_CONFIG"] = conf_settings.TINYMCE_DEFAULT_CONFIG
    context["TINYMCE_JS_URL"] = conf_settings.TINYMCE_JS_URL

    # Add current request function name for debugging/analytics
    if request and request.resolver_match:
        context["request_func_name"] = request.resolver_match.func.__name__

    return context


def is_shuttle(request: HttpRequest) -> bool:
    """Check if the requesting user is a shuttle operator for the association."""
    # Check if user has an associated member profile
    if not hasattr(request.user, "member"):
        return False

    # Verify user is in association's shuttle operators list
    return "shuttle" in request.assoc and request.user.member.id in request.assoc["shuttle"]


def update_payment_details(request, context: dict) -> None:
    """Update context with payment details for the association."""
    payment_details = fetch_payment_details(context["association_id"])
    context.update(payment_details)


def fetch_payment_details(association_id: int) -> dict:
    """Retrieve payment configuration details for an association.

    Args:
        association_id: Primary key of the association

    Returns:
        Dictionary containing payment gateway configuration
    """
    # Fetch association with only required fields for efficiency
    association = Association.objects.only("slug", "key").get(pk=association_id)
    return get_payment_details(association)
