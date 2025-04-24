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

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from larpmanager.cache.role import check_assoc_permission
from larpmanager.forms.miscellanea import (
    ExeInventoryBoxForm,
    ExeUrlShortnerForm,
)
from larpmanager.models.miscellanea import (
    Inventory,
    InventoryBox,
    InventoryBoxHistory,
    UrlShortner,
)
from larpmanager.utils.common import (
    check_diff,
)
from larpmanager.utils.edit import backend_get, exe_edit


@login_required
def exe_urlshortner(request):
    ctx = check_assoc_permission(request, "exe_urlshortner")
    ctx["list"] = UrlShortner.objects.filter(assoc_id=request.assoc["id"])
    return render(request, "larpmanager/exe/url_shortner.html", ctx)


@login_required
def exe_urlshortner_edit(request, num):
    return exe_edit(request, ExeUrlShortnerForm, num, "exe_urlshortner")


@login_required
def exe_inventory(request):
    ctx = check_assoc_permission(request, "exe_inventory")
    ctx["list"] = InventoryBox.objects.filter(assoc_id=request.assoc["id"])
    ctx["inv_fields"] = get_inventory_fields()
    return render(request, "larpmanager/exe/inventory.html", ctx)


def get_inventory_fields():
    aux = [f.name for f in Inventory._meta.get_fields()]
    aux.remove("deleted")
    aux.remove("deleted_by_cascade")
    aux.remove("created")
    aux.remove("updated")
    aux.remove("photo")
    return aux


@login_required
def exe_inventory_edit(request, num):
    return exe_edit(request, ExeInventoryBoxForm, num, "exe_inventory")
    # if "saved" in ctx:
    # hist = InventoryBoxHistory(box=ctx["saved"], member=request.user.member)
    # for f in get_inventory_fields():
    # setattr(hist, f, getattr(ctx["saved"], f))
    # hist.save()
    # return res


@login_required
def exe_inventory_history(request, num):
    ctx = check_assoc_permission(request, "exe_inventory")
    backend_get(ctx, InventoryBox, num)
    ctx["list"] = InventoryBoxHistory.objects.filter(box=ctx["el"]).order_by("created")
    last = None
    for v in ctx["list"]:
        aux = []
        for f in get_inventory_fields():
            aux.append(f"{f}: {getattr(v, f)}")
        val = ", ".join(aux)
        if last is not None:
            check_diff(v, last, val)
        last = val

    return render(request, "larpmanager/exe/inventory_history.html", ctx)
