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
)
from larpmanager.forms.member import (
    ExeProfileForm,
)
from larpmanager.models.access import AssocRole
from larpmanager.models.association import Association, AssocText
from larpmanager.models.base import Feature
from larpmanager.models.event import (
    Run,
)
from larpmanager.utils.base import check_assoc_permission
from larpmanager.utils.common import (
    get_feature,
    get_payment_methods_ids,
)
from larpmanager.utils.edit import backend_edit, exe_edit
from larpmanager.views.larpmanager import get_run_lm_payment


@login_required
def exe_association(request):
    return exe_edit(request, ExeAssociationForm, None, "exe_association", "manage")


@login_required
def exe_roles(request):
    ctx = check_assoc_permission(request, "exe_roles")
    ctx["list"] = list(AssocRole.objects.filter(assoc_id=request.assoc["id"]).order_by("number"))
    if not ctx["list"]:
        ctx["list"].append(AssocRole.objects.create(assoc_id=request.assoc["id"], number=1, name="Admin"))
    return render(request, "larpmanager/exe/roles.html", ctx)


@login_required
def exe_roles_edit(request, num):
    return exe_edit(request, ExeAssocRoleForm, num, "exe_roles")


@login_required
def exe_config(request):
    return exe_edit(request, ExeConfigForm, None, "exe_config", "manage")


@login_required
def exe_profile(request):
    return exe_edit(request, ExeProfileForm, None, "exe_profile", "manage")


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
    ctx = check_assoc_permission(request, "exe_payment_details")
    methods = get_payment_methods_ids(ctx)
    if backend_edit(request, ctx, ExePaymentSettingsForm, None, afield=None, assoc=True):
        if methods == get_payment_methods_ids(ctx):
            return redirect("manage")
        else:
            return redirect("exe_payment_details")
    return render(request, "larpmanager/exe/edit.html", ctx)


@login_required
def exe_appearance(request):
    return exe_edit(request, ExeAppearanceForm, None, "exe_appearance", "manage")


def f_k_exe(f_id, r_id):
    return f"feature_{f_id}_exe_{r_id}_key"


@login_required
def exe_features(request):
    return exe_edit(request, ExeFeatureForm, None, "exe_features", "manage")


def exe_features_go(request, ctx, num, on=True):
    ctx = check_assoc_permission(request, "exe_features")
    get_feature(ctx, num)
    f_id = ctx["feature"].id
    assoc = Association.objects.get(pk=request.assoc["id"])
    if on:
        if ctx["feature"].slug not in request.assoc["features"]:
            assoc.features.add(f_id)
            messages.success(request, _("Feature activated"))
        else:
            messages.success(request, _("Feature already activated"))
    elif ctx["feature"].slug not in request.assoc["features"]:
        messages.success(request, _("Feature already deactivated"))
    else:
        assoc.features.remove(f_id)
        messages.success(request, _("Feature deactivated"))

    assoc.save()


@login_required
def exe_features_on(request, num):
    ctx = check_assoc_permission(request, "exe_features")
    exe_features_go(request, ctx, num, on=True)
    return redirect("manage")


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
        txt += f"""
            <iframe src="{_add_in_iframe_param(feature.tutorial)}" width="100%" height="300"></iframe><br /><br />
        """

    if feature.link:
        txt += f"""
            <iframe width='100%' height='400' frameborder='0' allow='encrypted-media' "
            allowfullscreen src='https://www.youtube.com/embed/{feature.link}'></iframe>"
        """

    return JsonResponse({"res": "ok", "txt": txt})
