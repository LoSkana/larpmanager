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

from typing import Any

from django.conf import settings as conf_settings
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import get_payment_details
from larpmanager.cache.config import get_event_config
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.fields import get_event_fields_cache
from larpmanager.cache.links import cache_event_links
from larpmanager.cache.permission import get_association_permission_feature, get_event_permission_feature
from larpmanager.cache.run import get_cache_config_run, get_cache_run
from larpmanager.models.association import Association
from larpmanager.models.event import Run
from larpmanager.models.member import get_user_membership
from larpmanager.utils.auth.permission import (
    get_index_association_permissions,
    get_index_event_permissions,
    has_association_permission,
    has_event_permission,
)
from larpmanager.utils.core.exceptions import (
    FeatureError,
    MainPageError,
    MembershipError,
    RedirectError,
    UnknowRunError,
    UserPermissionError,
    check_event_feature,
)
from larpmanager.utils.users.registration import check_signup, get_player_signup, registration_status


def get_context(request: HttpRequest, *, check_main_site: bool = False) -> dict:  # noqa: C901 - Complex context building with feature checks
    """Build context with commonly used elements.

    Constructs a comprehensive context dictionary containing user information,
    association data, permissions, and configuration settings for template rendering.
    Handles cases where users are not authenticated or lack proper membership.

    Args:
        request: HTTP request object containing user and association information.
                Must have 'association' attribute with association data including 'id'.
        check_main_site: If this page is supposed to be accessible only on the main site

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
    # Initialize result dictionary with association ID
    context = {"association_id": request.association["id"]}

    # Copy all association data to context
    for association_key in request.association:
        context[association_key] = request.association[association_key]

    # Add member data
    context["member"] = None
    context["membership"] = None
    if hasattr(request, "user") and hasattr(request.user, "member"):
        context["member"] = request.user.member

    if context["association_id"] == 0:
        if not check_main_site:
            if context["member"]:
                user_associations = [membership.association for membership in context["member"].memberships.all()]
                raise MembershipError(user_associations)
            raise MembershipError
        return context

    if check_main_site:
        raise MainPageError(request)

    # Add cached event links to context
    cache_event_links(request, context)

    if context["member"]:
        # Get membership info
        context["membership"] = get_user_membership(context["member"], context["association_id"])

        # Get association permissions for the user
        get_index_association_permissions(context, request, context["association_id"], enforce_check=False)

        # Add user interface preferences and staff status
        context["interface_collapse_sidebar"] = context["member"].get_config(
            "interface_collapse_sidebar", default_value=False
        )
        context["is_staff"] = request.user.is_staff

    # Set default names for token/credit system if feature enabled
    for feature, default_name in [("tokens", _("Tokens")), ("credits", _("Credits"))]:
        name_key = f"{feature}_name"
        if feature in context["features"] and not context.get(name_key):
            context[name_key] = default_name

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
    return "shuttle" in request.association and request.user.member.id in request.association["shuttle"]


def update_payment_details(context: dict) -> None:
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


def check_association_context(request: HttpRequest, permission_slug: str = "") -> dict:
    """Check and validate association permissions for a request.

    Validates that the user has the required association permission and that
    any necessary features are enabled. Sets up context data for rendering
    the view with proper permission and feature information.

    Args:
        request: HTTP request object containing user and association data
        permission_slug: Permission slug identifier to check against user permissions

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

    # Load association permissions and sidebar state
    get_index_association_permissions(context, request, context["association_id"])
    context["is_sidebar_open"] = request.session.get("is_sidebar_open", True)

    # Add tutorial information if not already present
    if "tutorial" not in context:
        context["tutorial"] = tutorial_slug

    # Add configuration URL if user has config permissions
    if config_slug and has_association_permission(request, context, "exe_config"):
        context["config"] = reverse("exe_config", args=[config_slug])

    return context


def check_event_context(request: HttpRequest, event_slug: str, permission_slug: str | list[str] | None = None) -> dict:
    """Check event permissions and prepare management context.

    Validates user permissions for event management operations and prepares
    the necessary context including features, tutorials, and configuration links.

    Args:
        request: Django HTTP request object containing user and session data
        event_slug: Event slug identifier for the target event
        permission_slug: Required permission(s). Can be a single permission slug or list of permission slugs.
            If None, only basic event access is checked.

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

    # Load additional event permissions and management context
    get_index_event_permissions(request, context, event_slug)

    # Set management page flags
    context["orga_page"] = 1
    context["manage"] = 1

    return context


def get_event(request: HttpRequest, event_slug: str, run_number: Any = None) -> Any:
    """Get event context from slug and number.

    Args:
        request: Django HTTP request object or None
        event_slug (str): Event slug identifier
        run_number (int, optional): Run number to append to slug

    Returns:
        dict: Event context with run, event, and features

    Raises:
        Http404: If event doesn't exist or belongs to wrong association

    """
    context = get_context(request) if request else {}

    try:
        if run_number:
            event_slug += f"-{run_number}"

        get_run(context, event_slug)

        if "association_id" in context:
            if context["event"].association_id != context["association_id"]:
                msg = "wrong association"
                raise Http404(msg)
        else:
            context["association_id"] = context["event"].association_id

        context["features"] = get_event_features(context["event"].id)

        # paste as text tinymce
        if "paste_text" in context["features"]:
            conf_settings.TINYMCE_DEFAULT_CONFIG["paste_as_text"] = True

        context["show_available_chars"] = _("Show available characters")

    except ObjectDoesNotExist as error:
        msg = "Event does not exist"
        raise Http404(msg) from error
    else:
        return context


def get_event_context(
    request: Any,
    event_slug: str,
    feature_slug: str | None = None,
    *,
    signup: bool = False,
    include_status: bool = False,
    check_visibility: bool = True,
) -> dict:
    """Get comprehensive event run context with permissions and features.

    Retrieves event context and enhances it with user permissions, feature access,
    and registration status based on the provided parameters.

    Args:
        request: Django HTTP request object containing user and session data
        event_slug: Event slug identifier for the target event
        signup: Whether to check and validate signup eligibility for the user
        feature_slug: Optional feature slug to verify user access permissions
        include_status: Whether to include detailed registration status information
        check_visibility: Whether to enforce visibility restrictions

    Returns:
        Complete event context dictionary containing:
            - Event and run objects
            - User permissions and roles
            - Feature access flags
            - Registration status (if requested)
            - Association configuration
            - Staff permissions and sidebar state

    Raises:
        Http404: If event is not found or user lacks required permissions
        PermissionDenied: If user cannot access requested features

    """
    # Get base event context with run information
    context = get_event(request, event_slug)

    # Validate user signup eligibility if requested
    if signup:
        check_signup(context)

    # Verify feature access permissions for specific functionality
    if feature_slug:
        check_event_feature(request, context, feature_slug)

    # Add registration status details to context
    if include_status:
        registration_status(context["run"], context["member"], context)

    # Configure user permissions and sidebar for authorized users
    if has_event_permission(request, context, event_slug):
        get_index_event_permissions(request, context, event_slug)
        context["is_sidebar_open"] = request.session.get("is_sidebar_open", True)

    # Set association slug from request or event object
    if hasattr(request, "association"):
        context["association_slug"] = request.association["slug"]
    else:
        context["association_slug"] = context["event"].association.slug

    # Configure staff permissions for character management access
    if has_event_permission(request, context, event_slug, "orga_characters"):
        context["staff"] = "1"
        context["skip"] = "1"

    # Finalize run context preparation and return complete context
    prepare_run(context)

    # Check character visibility restrictions if requested (skip for users with event permissions)
    if check_visibility and not has_event_permission(request, context, event_slug):
        event_url = reverse("register", kwargs={"event_slug": context["run"].get_slug()})
        # Check if gallery is hidden for non-authenticated users
        hide_gallery_for_non_login = get_event_config(
            context["event"].id, "gallery_hide_login", default_value=False, context=context
        )
        if hide_gallery_for_non_login and not request.user.is_authenticated:
            messages.warning(request, _("You must be logged in to view this page"))
            raise RedirectError(event_url)

        # Check if gallery is hidden for non-registered users
        hide_gallery_for_non_signup = get_event_config(
            context["event"].id, "gallery_hide_signup", default_value=False, context=context
        )
        if hide_gallery_for_non_signup and not get_player_signup(context):
            messages.warning(request, _("You must be registered to view this page"))
            raise RedirectError(event_url)

    return context


def prepare_run(context: Any) -> None:
    """Prepare run context with visibility and field configurations.

    Args:
        context (dict): Event context to update

    Side effects:
        Updates context with run configuration, visibility settings, and writing fields

    """
    run_configuration = get_cache_config_run(context["run"])

    if "staff" in context or not get_event_config(
        context["event"].id, "writing_field_visibility", default_value=False, context=context
    ):
        context["show_all"] = "1"

        for writing_element in ["character", "faction", "quest", "trait"]:
            visibility_config_name = f"show_{writing_element}"
            if visibility_config_name not in run_configuration:
                run_configuration[visibility_config_name] = {}
            run_configuration[visibility_config_name].update({"name": 1, "teaser": 1, "text": 1})

        for additional_feature in ["plot", "relationships", "speedlarp", "prologue", "workshop", "print_pdf"]:
            additional_config_name = "show_addit"
            if additional_config_name not in run_configuration:
                run_configuration[additional_config_name] = {}
            if additional_feature in context["features"]:
                run_configuration[additional_config_name][additional_feature] = True

    context.update(run_configuration)

    context["writing_fields"] = get_event_fields_cache(context["event"].id)

    # Check if there are visible factions with characters for nav display
    context["has_visible_factions"] = False
    if "faction" in context.get("features", {}) and "factions" in context:
        for faction_data in context["factions"].values():
            # Check if faction has a name and has characters
            if faction_data.get("name") and faction_data.get("characters"):
                context["has_visible_factions"] = True
                break


def get_run(context: Any, event_slug: Any) -> None:
    """Load run and event data from cache and database.

    Args:
        context (dict): Context dictionary to update
        event_slug (str): Event slug identifier

    Side effects:
        Updates context with run and event objects

    Raises:
        UnknowRunError: If run cannot be found

    """
    try:
        run_id = get_cache_run(context["association_id"], event_slug)
        que = Run.objects.select_related("event")
        fields = [
            "search",
            "balance",
            "event__tagline",
            "event__where",
            "event__authors",
            "event__description",
            "event__genre",
            "event__cover",
            "event__carousel_img",
            "event__carousel_text",
            "event__features",
            "event__background",
            "event__font",
            "event__pri_rgb",
            "event__sec_rgb",
            "event__ter_rgb",
        ]
        que = que.defer(*fields)
        context["run"] = que.get(pk=run_id)
        context["event"] = context["run"].event
    except Exception as err:
        raise UnknowRunError from err
