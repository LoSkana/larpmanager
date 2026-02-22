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
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.cache.feature import get_association_features
from larpmanager.forms.association import (
    ExeFeatureForm,
)
from larpmanager.models.access import AssociationPermission, AssociationRole
from larpmanager.models.association import Association, AssociationText, AssociationTranslation
from larpmanager.models.base import Feature
from larpmanager.models.event import Run
from larpmanager.utils.auth.permission import get_index_association_permissions
from larpmanager.utils.core.base import check_association_context
from larpmanager.utils.core.common import clear_messages, get_feature
from larpmanager.utils.edit.backend import backend_edit
from larpmanager.utils.edit.exe import ExeAction, exe_delete, exe_edit, exe_new
from larpmanager.utils.services.association import _reset_all_association
from larpmanager.views.larpmanager import get_run_lm_payment
from larpmanager.views.orga.event import prepare_roles_list


@login_required
def exe_association(request: HttpRequest) -> Any:
    """Edit association details."""
    return exe_edit(request, ExeAction.ASSOCIATION)


@login_required
def exe_roles(request: HttpRequest) -> HttpResponse:
    """Handle association roles management page."""
    # Check user permissions for role management
    context = check_association_context(request, "exe_roles")

    def def_callback(context: dict) -> AssociationRole:
        """Create default admin role for association."""
        return AssociationRole.objects.create(association_id=context["association_id"], number=1, name="Admin")

    # Prepare roles list with existing association roles
    prepare_roles_list(
        context,
        AssociationPermission,
        AssociationRole.objects.filter(association_id=context["association_id"]),
        def_callback,
    )

    return render(request, "larpmanager/exe/roles.html", context)


@login_required
def exe_roles_new(request: HttpRequest) -> Any:
    """Create a new association role."""
    return exe_new(request, ExeAction.ROLES)


@login_required
def exe_roles_edit(request: HttpRequest, role_uuid: str) -> Any:
    """Edit specific association role."""
    return exe_edit(request, ExeAction.ROLES, role_uuid)


@login_required
def exe_roles_delete(request: HttpRequest, role_uuid: str) -> HttpResponse:
    """Delete role."""
    return exe_delete(request, ExeAction.ROLES, role_uuid)


@login_required
def exe_config(request: HttpRequest, section: str | None = None) -> HttpResponse:  # noqa: ARG001
    """Handle organization configuration editing with optional section jump."""
    return exe_edit(request, ExeAction.CONFIG)


@login_required
def exe_profile(request: HttpRequest) -> Any:
    """Edit user profile settings."""
    return exe_edit(request, ExeAction.PROFILE)


@login_required
def exe_texts(request: HttpRequest) -> HttpResponse:
    """Display list of association texts grouped by type, default flag, and language."""
    # Check permission and get base context
    context = check_association_context(request, "exe_texts")

    # Fetch and order association texts for display
    context["list"] = AssociationText.objects.filter(association_id=context["association_id"]).order_by(
        "typ",
        "default",
        "language",
    )

    return render(request, "larpmanager/exe/texts.html", context)


@login_required
def exe_texts_new(request: HttpRequest) -> HttpResponse:
    """Create a new association text."""
    return exe_new(request, ExeAction.TEXTS)


@login_required
def exe_texts_edit(request: HttpRequest, text_uuid: str) -> HttpResponse:
    """Edit specific association text."""
    return exe_edit(request, ExeAction.TEXTS, text_uuid)


@login_required
def exe_texts_delete(request: HttpRequest, text_uuid: str) -> HttpResponse:
    """Delete text."""
    return exe_delete(request, ExeAction.TEXTS, text_uuid)


@login_required
def exe_translations(request: HttpRequest) -> HttpResponse:
    """Display the list of custom translation overrides for an association."""
    # Verify user has permission to manage translations for this association
    context = check_association_context(request, "exe_translations")

    # Fetch all custom translations for this association (both active and inactive)
    context["list"] = AssociationTranslation.objects.filter(association_id=context["association_id"])

    return render(request, "larpmanager/exe/translations.html", context)


@login_required
def exe_translations_new(request: HttpRequest) -> HttpResponse:
    """Create a new association translation override."""
    return exe_new(request, ExeAction.TRANSLATIONS)


@login_required
def exe_translations_edit(request: HttpRequest, translation_uuid: str) -> HttpResponse:
    """Handle creation and editing of association translation overrides."""
    return exe_edit(request, ExeAction.TRANSLATIONS, translation_uuid)


@login_required
def exe_translations_delete(request: HttpRequest, translation_uuid: str) -> HttpResponse:
    """Delete association translation overrides."""
    return exe_delete(request, ExeAction.TRANSLATIONS, translation_uuid)


@login_required
def exe_methods(request: HttpRequest) -> Any:
    """Edit payment methods settings."""
    return exe_edit(request, ExeAction.METHODS)


@login_required
def exe_appearance(request: HttpRequest) -> Any:
    """Edit association appearance settings."""
    return exe_edit(request, ExeAction.APPEARANCE)


@login_required
def exe_features(request: HttpRequest) -> HttpResponse:
    """Handle executive feature activation for associations.

    This function allows executives to activate new features for their association.
    When features are successfully activated, it either redirects to a single feature's
    after-link or displays a management page for multiple features.

    Args:
        request (HttpRequest): HTTP request object from authenticated executive user

    Returns:
        HttpResponse: Feature management form, redirect to manage page, or redirect
                     to single feature's after-link based on activation results

    """
    # Check user permissions and get initial context
    context = check_association_context(request, "exe_features")
    context["assoc_form"] = True

    # Process form submission and handle feature activation
    if backend_edit(request, context, ExeFeatureForm):
        # Get newly activated features that have after-links
        context["new_features"] = Feature.objects.filter(
            pk__in=context["form"].added_features,
            after_link__isnull=False,
        )

        # If no features with after-links, redirect to manage page
        if not context["new_features"]:
            return redirect("manage")

        # Generate follow links for each activated feature
        for el in context["new_features"]:
            el.follow_link = _exe_feature_after_link(el)

        # Handle single feature activation with immediate redirect
        if len(context["new_features"]) == 1:
            feature = context["new_features"][0]
            msg = _("Feature %(name)s activated") % {"name": feature.name} + "! " + feature.after_text
            clear_messages(request)
            messages.success(request, msg)
            return redirect(feature.follow_link)

        # Handle multiple features - show management page
        context["features"] = get_association_features(context["association_id"])
        get_index_association_permissions(request, context, context["association_id"])
        return render(request, "larpmanager/manage/features.html", context)

    # Render edit form for feature selection
    return render(request, "larpmanager/exe/edit.html", context)


def exe_features_go(request: HttpRequest, slug: str, *, to_active: bool = True) -> Feature:
    """Activate or deactivate an overall feature for an association.

    Args:
        request: The HTTP request object containing user and association context
        slug: The unique identifier of the feature to toggle
        to_active: Whether to activate (True) or deactivate (False) the feature

    Returns:
        Feature: The feature object that was toggled

    Raises:
        Http404: If the feature is not an overall feature

    """
    # Check user permissions and retrieve feature context
    context = check_association_context(request, "exe_features")
    get_feature(context, slug)

    # Ensure this is an overall feature (organization-wide)
    if not context["feature"].overall:
        msg = "not overall feature!"
        raise Http404(msg)

    # Get feature ID and association object
    feature_id = context["feature"].id
    association = Association.objects.get(pk=context["association_id"])

    # Handle feature activation
    if to_active:
        if slug not in context["features"]:
            association.features.add(feature_id)
            message = _("Feature %(name)s activated") + "!"
        else:
            message = _("Feature %(name)s already activated") + "!"
    # Handle feature deactivation
    elif slug not in context["features"]:
        message = _("Feature %(name)s already deactivated") + "!"
    else:
        association.features.remove(feature_id)
        message = _("Feature %(name)s deactivated") + "!"

    # Save changes to association
    association.save()

    # Format success message with feature name
    message = message % {"name": _(context["feature"].name)}
    if context["feature"].after_text:
        message += " " + context["feature"].after_text
    messages.success(request, message)

    return context["feature"]


def _exe_feature_after_link(feature: Feature) -> str:
    """Generate the appropriate redirect URL after feature setup."""
    redirect_url_or_fragment = feature.after_link

    # Check if redirect_url_or_fragment is a named URL pattern starting with "exe"
    if redirect_url_or_fragment and redirect_url_or_fragment.startswith("exe"):
        return reverse(redirect_url_or_fragment)

    # Otherwise append redirect_url_or_fragment as a URL fragment to manage page
    return reverse("manage") + redirect_url_or_fragment


@login_required
def exe_features_on(request: HttpRequest, slug: str) -> HttpResponseRedirect:
    """Enable feature and redirect to the appropriate page."""
    feature = exe_features_go(request, slug, to_active=True)
    return redirect(_exe_feature_after_link(feature))


@login_required
def exe_features_off(request: HttpRequest, slug: str) -> HttpResponse:
    """Disable features and redirect to management page."""
    exe_features_go(request, slug, to_active=False)
    return redirect("manage")


@login_required
def exe_larpmanager(request: HttpRequest) -> HttpResponse:
    """Display association's run list with payment information."""
    # Check user permissions for association management
    context = check_association_context(request, "exe_association")

    # Get all runs for the current association
    que = Run.objects.filter(event__association_id=context["association_id"])
    context["list"] = que.select_related("event").order_by("start")

    # Add payment information to each run
    for run in context["list"]:
        get_run_lm_payment(run)

    return render(request, "larpmanager/exe/larpmanager.html", context)


def _add_in_iframe_param(url: str) -> str:
    """Add 'in_iframe=1' parameter to a URL for iframe rendering.

    This function parses the given URL, adds or updates the 'in_iframe' parameter
    to '1', and returns the modified URL. If the parameter already exists, it will
    be overwritten.

    Args:
        url (str): Original URL string to modify

    Returns:
        str: Modified URL with in_iframe parameter added

    Example:
        >>> _add_in_iframe_param("https://example.com/page")
        "https://example.com/page?in_iframe=1"
        >>> _add_in_iframe_param("https://example.com/page?foo=bar")
        "https://example.com/page?foo=bar&in_iframe=1"

    """
    # Parse the URL into its components
    parsed_url = urlparse(url)

    # Extract existing query parameters and add iframe parameter
    existing_query_params = parse_qs(parsed_url.query)
    existing_query_params["in_iframe"] = ["1"]

    # Rebuild the query string with all parameters
    updated_query_string = urlencode(existing_query_params, doseq=True)

    # Reconstruct the complete URL with the modified query string
    return urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            updated_query_string,
            parsed_url.fragment,
        ),
    )


@require_POST
def feature_description(request: HttpRequest) -> JsonResponse:
    """Get feature description with optional tutorial iframe.

    Args:
        request: HTTP request object containing POST data with 'fid' parameter

    Returns:
        JsonResponse: JSON response with 'res' status and 'txt' content on success,
                     or error response with 'res': 'ko' if feature not found

    """
    # Extract feature ID from POST data
    fid = request.POST.get("fid")

    # Attempt to retrieve feature from database
    try:
        feature = Feature.objects.get(pk=fid)
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko"})

    # Build HTML content with feature name and description
    txt = f"<h2>{feature.name}</h2> {feature.descr}<br /><br />"

    # Add tutorial iframe if feature has tutorial content
    if feature.tutorial:
        tutorial = reverse("tutorials") + feature.tutorial
        txt += f"""
            <iframe src="{_add_in_iframe_param(tutorial)}" width="100%" height="100%"></iframe><br /><br />
        """

    # Return successful response with HTML content
    return JsonResponse({"res": "ok", "txt": txt})


@login_required
def exe_quick(request: HttpRequest) -> Any:
    """Edit quick setup configuration."""
    return exe_edit(request, ExeAction.QUICK)


@login_required
def exe_preferences(request: HttpRequest) -> Any:
    """Edit user preferences."""
    return exe_edit(request, ExeAction.PREFERENCES)


@login_required
def exe_reload_cache(request: HttpRequest) -> HttpResponse:
    """Reset all cache entries for the organization."""
    # Verify user permissions and get association context
    context = check_association_context(request)

    # Get association slug and ID
    association_slug = context["slug"]
    association_id = context["id"]

    _reset_all_association(association_id, association_slug)

    # Notify user of successful cache reset
    messages.success(request, _("Cache reset!"))
    return redirect("manage")
