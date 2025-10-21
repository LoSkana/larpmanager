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

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.forms.accounting import ExePaymentSettingsForm
from larpmanager.forms.association import (
    ExeAppearanceForm,
    ExeAssociationForm,
    ExeAssocRoleForm,
    ExeAssocTextForm,
    ExeConfigForm,
    ExeFeatureForm,
    ExePreferencesForm,
    ExeQuickSetupForm,
)
from larpmanager.forms.member import ExeProfileForm
from larpmanager.models.access import AssocPermission, AssocRole
from larpmanager.models.association import Association, AssocText
from larpmanager.models.base import Feature
from larpmanager.models.event import Run
from larpmanager.utils.base import check_assoc_permission, get_index_assoc_permissions
from larpmanager.utils.common import clear_messages, get_feature
from larpmanager.utils.edit import backend_edit, exe_edit
from larpmanager.views.larpmanager import get_run_lm_payment
from larpmanager.views.orga.event import prepare_roles_list


@login_required
def exe_association(request):
    return exe_edit(request, ExeAssociationForm, None, "exe_association", "manage", add_ctx={"add_another": False})


@login_required
def exe_roles(request: HttpRequest) -> HttpResponse:
    """Handles organization role management page.

    This view displays and manages roles for an organization, allowing
    administrators to view, create, and modify organizational roles.

    Args:
        request: The HTTP request object containing user and organization context.

    Returns:
        HttpResponse: Rendered roles management page with role list and permissions.
    """
    # Check if user has permission to access organization roles
    ctx = check_assoc_permission(request, "exe_roles")

    def def_callback(ctx):
        # Create default admin role for new organizations
        return AssocRole.objects.create(assoc_id=ctx["a_id"], number=1, name="Admin")

    # Prepare roles list with permissions and existing roles for the organization
    prepare_roles_list(ctx, AssocPermission, AssocRole.objects.filter(assoc_id=request.assoc["id"]), def_callback)

    # Render the roles management template with prepared context
    return render(request, "larpmanager/exe/roles.html", ctx)


@login_required
def exe_roles_edit(request, num):
    return exe_edit(request, ExeAssocRoleForm, num, "exe_roles")


@login_required
def exe_config(request, section=None):
    add_ctx = {"jump_section": section} if section else {}
    add_ctx["add_another"] = False
    return exe_edit(request, ExeConfigForm, None, "exe_config", "manage", add_ctx=add_ctx)


@login_required
def exe_profile(request):
    return exe_edit(request, ExeProfileForm, None, "exe_profile", "manage", add_ctx={"add_another": False})


@login_required
def exe_texts(request):
    ctx = check_assoc_permission(request, "exe_texts")
    ctx["list"] = AssocText.objects.filter(assoc_id=request.assoc["id"]).order_by("typ", "default", "language")
    return render(request, "larpmanager/exe/texts.html", ctx)


@login_required
def exe_texts_edit(request, num):
    return exe_edit(request, ExeAssocTextForm, num, "exe_texts")


@login_required
def exe_methods(request):
    return exe_edit(request, ExePaymentSettingsForm, None, "exe_methods", "manage", add_ctx={"add_another": False})


@login_required
def exe_appearance(request):
    return exe_edit(request, ExeAppearanceForm, None, "exe_appearance", "manage", add_ctx={"add_another": False})


def f_k_exe(f_id, r_id):
    return f"feature_{f_id}_exe_{r_id}_key"


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
    ctx = check_assoc_permission(request, "exe_features")
    ctx["add_another"] = False

    # Process form submission and handle feature activation
    if backend_edit(request, ctx, ExeFeatureForm, None, afield=None, assoc=True):
        # Get newly activated features that have after-links
        ctx["new_features"] = Feature.objects.filter(pk__in=ctx["form"].added_features, after_link__isnull=False)

        # If no features with after-links, redirect to manage page
        if not ctx["new_features"]:
            return redirect("manage")

        # Generate follow links for each activated feature
        for el in ctx["new_features"]:
            el.follow_link = _exe_feature_after_link(el)

        # Handle single feature activation with immediate redirect
        if len(ctx["new_features"]) == 1:
            feature = ctx["new_features"][0]
            msg = _("Feature %(name)s activated") % {"name": feature.name} + "! " + feature.after_text
            clear_messages(request)
            messages.success(request, msg)
            return redirect(feature.follow_link)

        # Handle multiple features - show management page
        get_index_assoc_permissions(ctx, request, request.assoc["id"])
        return render(request, "larpmanager/manage/features.html", ctx)

    # Render edit form for feature selection
    return render(request, "larpmanager/exe/edit.html", ctx)


def exe_features_go(request: HttpRequest, slug: str, on: bool = True) -> Feature:
    """
    Activate or deactivate an overall feature for an association.

    Args:
        request: The HTTP request object containing user and association context
        slug: The unique identifier of the feature to toggle
        on: Whether to activate (True) or deactivate (False) the feature

    Returns:
        Feature: The feature object that was toggled

    Raises:
        Http404: If the feature is not an overall feature
    """
    # Check user permissions and retrieve feature context
    ctx = check_assoc_permission(request, "exe_features")
    get_feature(ctx, slug)

    # Ensure this is an overall feature (organization-wide)
    if not ctx["feature"].overall:
        raise Http404("not overall feature!")

    # Get feature ID and association object
    f_id = ctx["feature"].id
    assoc = Association.objects.get(pk=request.assoc["id"])

    # Handle feature activation
    if on:
        if slug not in request.assoc["features"]:
            assoc.features.add(f_id)
            msg = _("Feature %(name)s activated") + "!"
        else:
            msg = _("Feature %(name)s already activated") + "!"
    # Handle feature deactivation
    elif slug not in request.assoc["features"]:
        msg = _("Feature %(name)s already deactivated") + "!"
    else:
        assoc.features.remove(f_id)
        msg = _("Feature %(name)s deactivated") + "!"

    # Save changes to association
    assoc.save()

    # Format success message with feature name
    msg = msg % {"name": _(ctx["feature"].name)}
    if ctx["feature"].after_text:
        msg += " " + ctx["feature"].after_text
    messages.success(request, msg)

    return ctx["feature"]


def _exe_feature_after_link(feature):
    after_link = feature.after_link
    if after_link and after_link.startswith("exe"):
        return reverse(after_link)
    return reverse("manage") + after_link


@login_required
def exe_features_on(request, slug):
    feature = exe_features_go(request, slug, on=True)
    return redirect(_exe_feature_after_link(feature))


@login_required
def exe_features_off(request, slug):
    exe_features_go(request, slug, on=False)
    return redirect("manage")


@login_required
def exe_larpmanager(request: HttpRequest) -> HttpResponse:
    """Display LarpManager dashboard with run payment information.

    Shows all runs for the current association with their payment status.
    Requires 'exe_association' permission to access.

    Args:
        request: HTTP request object containing user and session data

    Returns:
        Rendered HTML response with runs list and payment information
    """
    # Check user has permission to access association dashboard
    ctx = check_assoc_permission(request, "exe_association")

    # Get all runs for the current association
    que = Run.objects.filter(event__assoc_id=ctx["a_id"])

    # Order runs by start date and optimize queries with select_related
    ctx["list"] = que.select_related("event").order_by("start")

    # Calculate payment information for each run
    for run in ctx["list"]:
        get_run_lm_payment(run)

    return render(request, "larpmanager/exe/larpmanager.html", ctx)


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
    parsed = urlparse(url)

    # Extract existing query parameters and add iframe parameter
    query_params = parse_qs(parsed.query)
    query_params["in_iframe"] = ["1"]

    # Rebuild the query string with all parameters
    new_query = urlencode(query_params, doseq=True)

    # Reconstruct the complete URL with the modified query string
    new_url = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )

    return new_url


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
def exe_quick(request):
    return exe_edit(request, ExeQuickSetupForm, None, "exe_quick", "manage", add_ctx={"add_another": False})


@login_required
def exe_preferences(request):
    return exe_edit(request, ExePreferencesForm, request.user.member.id, None, "manage", add_ctx={"add_another": False})
