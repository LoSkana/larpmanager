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
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.feature import get_assoc_features
from larpmanager.cache.links import cache_event_links
from larpmanager.cache.permission import get_assoc_permission_feature, get_cache_index_permission
from larpmanager.cache.role import get_assoc_roles, has_assoc_permission
from larpmanager.models.association import Association
from larpmanager.models.member import get_user_membership
from larpmanager.models.utils import get_payment_details
from larpmanager.utils.auth import get_allowed_managed
from larpmanager.utils.exceptions import FeatureError, MembershipError, PermissionError


def def_user_ctx(request):
    """Build default user context with association data and permissions.

    Args:
        request: HTTP request object with user and association information

    Returns:
        Dictionary containing user context, membership, permissions, and settings
    """
    # check the home page has been reached, redirect to the correct organization page
    if request.assoc["id"] == 0:
        if hasattr(request, "user") and hasattr(request.user, "member"):
            assocs = [el.assoc for el in request.user.member.memberships.all()]
            raise MembershipError(assocs)
        raise MembershipError()

    res = {"a_id": request.assoc["id"]}
    for s in request.assoc:
        res[s] = request.assoc[s]

    if hasattr(request, "user") and hasattr(request.user, "member"):
        res["member"] = request.user.member
        res["membership"] = get_user_membership(request.user.member, request.assoc["id"])
        get_index_assoc_permissions(res, request, request.assoc["id"], check=False)
        res["interface_collapse_sidebar"] = request.user.member.get_config("interface_collapse_sidebar", False)
        res["is_staff"] = request.user.is_staff

    res.update(cache_event_links(request))

    if "token_credit" in res["features"]:
        if not res["token_name"]:
            res["token_name"] = _("Tokens")
        if not res["credit_name"]:
            res["credit_name"] = _("Credits")

    res["TINYMCE_DEFAULT_CONFIG"] = conf_settings.TINYMCE_DEFAULT_CONFIG
    res["TINYMCE_JS_URL"] = conf_settings.TINYMCE_JS_URL

    if request and request.resolver_match:
        res["request_func_name"] = request.resolver_match.func.__name__

    return res


def is_shuttle(request):
    if not hasattr(request.user, "member"):
        return False
    return "shuttle" in request.assoc and request.user.member.id in request.assoc["shuttle"]


def update_payment_details(request, ctx):
    assoc = Association.objects.get(pk=request.assoc["id"])
    payment_details = get_payment_details(assoc)
    ctx.update(payment_details)


def check_assoc_permission(request, slug):
    """Check and validate association permissions for a request.

    Args:
        request: HTTP request object
        slug: Permission slug to check

    Returns:
        dict: Context dictionary with permission and feature data

    Raises:
        PermissionError: If user lacks required permissions
        FeatureError: If required feature is not enabled
    """
    ctx = def_user_ctx(request)
    if not has_assoc_permission(request, ctx, slug):
        raise PermissionError()
    (feature, tutorial, config) = get_assoc_permission_feature(slug)
    if feature != "def" and feature not in request.assoc["features"]:
        raise FeatureError(path=request.path, feature=feature, run=0)
    ctx["manage"] = 1
    get_index_assoc_permissions(ctx, request, request.assoc["id"])
    ctx["is_sidebar_open"] = request.session.get("is_sidebar_open", True)
    ctx["exe_page"] = 1
    if "tutorial" not in ctx:
        ctx["tutorial"] = tutorial
    if config and has_assoc_permission(request, ctx, "exe_config"):
        ctx["config"] = reverse("exe_config", args=[config])
    return ctx


def get_index_assoc_permissions(ctx, request, assoc_id, check=True):
    (is_admin, user_assoc_permissions, names) = get_assoc_roles(request)
    if not names and not is_admin:
        if check:
            raise PermissionError()
        else:
            return

    ctx["role_names"] = names
    features = get_assoc_features(assoc_id)
    ctx["assoc_pms"] = get_index_permissions(ctx, features, is_admin, user_assoc_permissions, "assoc")
    ctx["is_sidebar_open"] = request.session.get("is_sidebar_open", True)


def get_index_permissions(ctx, features, has_default, permissions, typ):
    """Build index permissions structure based on user access and features.

    Args:
        ctx: Context dictionary with association information
        features: Available features list
        has_default: Whether user has default permissions
        permissions: User's specific permissions
        typ: Permission type to filter

    Returns:
        Dictionary of grouped permissions by module
    """
    res = {}
    for ar in get_cache_index_permission(typ):
        if ar["hidden"]:
            continue

        if not is_allowed_managed(ar, ctx):
            continue

        if not has_default and ar["slug"] not in permissions:
            continue

        if not ar["feature__placeholder"] and ar["feature__slug"] not in features:
            continue

        mod_name = (_(ar["module__name"]), ar["module__icon"])
        if mod_name not in res:
            res[mod_name] = []
        res[mod_name].append(ar)

    return res


def is_allowed_managed(ar, ctx):
    # check if the association skin is managed and the user is not staff
    if ctx.get("skin_managed", False) and not ctx.get("is_staff", False):
        allowed = get_allowed_managed()
        # if the feature is a placeholder different than the management of events:
        if ar["feature__placeholder"] and ar["slug"] not in allowed:
            return False

    return True
