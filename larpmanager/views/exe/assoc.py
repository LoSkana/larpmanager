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
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.forms.accounting import (
    ExePaymentSettingsForm,
)
from larpmanager.forms.association import (
    ExeAppearanceForm,
    ExeAssociationForm,
    ExeAssocRoleForm,
    ExeAssocTextForm,
    ExeConfigForm,
    ExeFeatureForm,
    ExeQuickSetupForm,
)
from larpmanager.forms.member import (
    ExeProfileForm,
)
from larpmanager.models.access import AssocPermission, AssocRole
from larpmanager.models.association import Association, AssocText
from larpmanager.models.base import Feature
from larpmanager.models.event import (
    Run,
)
from larpmanager.utils.base import check_assoc_permission, get_index_assoc_permissions
from larpmanager.utils.common import (
    clear_messages,
    get_feature,
)
from larpmanager.utils.edit import backend_edit, exe_edit
from larpmanager.views.larpmanager import get_run_lm_payment
from larpmanager.views.orga.event import prepare_roles_list


@login_required
def exe_association(request):
    return exe_edit(request, ExeAssociationForm, None, "exe_association", "manage", add_ctx={"add_another": False})


@login_required
def exe_roles(request):
    ctx = check_assoc_permission(request, "exe_roles")

    def def_callback(ctx):
        return AssocRole.objects.create(assoc_id=ctx["a_id"], number=1, name="Admin")

    prepare_roles_list(ctx, AssocPermission, AssocRole.objects.filter(assoc_id=request.assoc["id"]), def_callback)

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
def exe_payment_details(request):
    return exe_edit(
        request, ExePaymentSettingsForm, None, "exe_payment_details", "manage", add_ctx={"add_another": False}
    )


@login_required
def exe_appearance(request):
    return exe_edit(request, ExeAppearanceForm, None, "exe_appearance", "manage", add_ctx={"add_another": False})


def f_k_exe(f_id, r_id):
    return f"feature_{f_id}_exe_{r_id}_key"


@login_required
def exe_features(request):
    ctx = check_assoc_permission(request, "exe_features")
    ctx["add_another"] = False
    if backend_edit(request, ctx, ExeFeatureForm, None, afield=None, assoc=True):
        ctx["new_features"] = Feature.objects.filter(pk__in=ctx["form"].added_features, after_link__isnull=False)
        if not ctx["new_features"]:
            return redirect("manage")
        for el in ctx["new_features"]:
            el.follow_link = _exe_feature_after_link(el)
        if len(ctx["new_features"]) == 1:
            feature = ctx["new_features"][0]
            msg = _("Feature %(name)s activated") % {"name": feature.name} + "! " + feature.after_text
            clear_messages(request)
            messages.success(request, msg)
            return redirect(feature.follow_link)

        get_index_assoc_permissions(ctx, request, request.assoc["id"])
        return render(request, "larpmanager/manage/features.html", ctx)
    return render(request, "larpmanager/exe/edit.html", ctx)


def exe_features_go(request, ctx, num, on=True):
    ctx = check_assoc_permission(request, "exe_features")
    get_feature(ctx, num)
    f_id = ctx["feature"].id
    assoc = Association.objects.get(pk=request.assoc["id"])
    if on:
        if ctx["feature"].slug not in request.assoc["features"]:
            assoc.features.add(f_id)
            msg = _("Feature %(name)s activated") + "!"
        else:
            msg = _("Feature %(name)s already activated") + "!"
    elif ctx["feature"].slug not in request.assoc["features"]:
        msg = _("Feature %(name)s already deactivated") + "!"
    else:
        assoc.features.remove(f_id)
        msg = _("Feature %(name)s deactivated") + "!"

    assoc.save()

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
def exe_features_on(request, num):
    ctx = check_assoc_permission(request, "exe_features")
    feature = exe_features_go(request, ctx, num, on=True)
    return redirect(_exe_feature_after_link(feature))


@login_required
def exe_features_off(request, num):
    ctx = check_assoc_permission(request, "exe_features")
    exe_features_go(request, ctx, num, on=False)
    return redirect("manage")


@login_required
def exe_larpmanager(request):
    ctx = check_assoc_permission(request, "exe_association")
    que = Run.objects.filter(event__assoc_id=ctx["a_id"])
    ctx["list"] = que.select_related("event").order_by("start")
    for run in ctx["list"]:
        get_run_lm_payment(run)
    return render(request, "larpmanager/exe/larpmanager.html", ctx)


def _add_in_iframe_param(url):
    parsed = urlparse(url)

    query_params = parse_qs(parsed.query)
    query_params["in_iframe"] = ["1"]
    new_query = urlencode(query_params, doseq=True)

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
def feature_description(request):
    fid = request.POST.get("fid")
    try:
        feature = Feature.objects.get(pk=fid)
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko"})

    txt = f"<h2>{feature.name}</h2> {feature.descr}<br /><br />"

    if feature.tutorial:
        tutorial = reverse("tutorials") + feature.tutorial
        txt += f"""
            <iframe src="{_add_in_iframe_param(tutorial)}" width="100%" height="100%"></iframe><br /><br />
        """

    return JsonResponse({"res": "ok", "txt": txt})


@login_required
def exe_quick(request):
    return exe_edit(request, ExeQuickSetupForm, None, "exe_quick", "manage", add_ctx={"add_another": False})
