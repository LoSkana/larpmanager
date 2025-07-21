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
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.feature import get_assoc_features
from larpmanager.cache.links import cache_event_links
from larpmanager.cache.permission import get_assoc_permission_feature
from larpmanager.cache.role import get_assoc_roles, has_assoc_permission
from larpmanager.models.access import AssocPermission
from larpmanager.models.association import Association
from larpmanager.models.member import get_user_membership
from larpmanager.models.utils import get_payment_details
from larpmanager.utils.exceptions import FeatureError, MembershipError, PermissionError


def def_user_ctx(request):
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

    # TODO remove
    assoc = Association.objects.get(pk=request.assoc["id"])
    res["interface_old"] = assoc.get_config("interface_old", False)

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
    ctx = def_user_ctx(request)
    if not has_assoc_permission(request, slug):
        raise PermissionError()
    (feature, tutorial) = get_assoc_permission_feature(slug)
    if feature != "def" and feature not in request.assoc["features"]:
        raise FeatureError(path=request.path, feature=feature, run=0)
    ctx["manage"] = 1
    get_index_assoc_permissions(ctx, request, request.assoc["id"])
    ctx["is_sidebar_open"] = request.session.get("is_sidebar_open", True)
    ctx["exe_page"] = 1
    if "tutorial" not in ctx:
        ctx["tutorial"] = tutorial
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
    ctx["assoc_pms"] = get_index_permissions(features, is_admin, user_assoc_permissions, AssocPermission)
    ctx["is_sidebar_open"] = request.session.get("is_sidebar_open", True)


def get_index_permissions(features, has_default, permissions, typ):
    res = {}
    for ar in typ.objects.select_related("feature", "feature__module").order_by("feature__module__order", "number"):
        if ar.hidden:
            continue
        if not has_default and ar.slug not in permissions:
            continue
        if not ar.feature.placeholder and ar.feature.slug not in features:
            continue
        mod_name = (_(ar.feature.module.name), ar.feature.module.icon)
        if mod_name not in res:
            res[mod_name] = []
        res[mod_name].append(ar)

    return res
