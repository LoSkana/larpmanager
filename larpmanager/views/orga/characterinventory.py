# LarpManager - https://larpmanager.coms
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

from larpmanager.forms.characterinventory import OrgaPoolTypePxForm
from larpmanager.utils.edit import orga_edit
from larpmanager.utils.event import check_event_permission


@login_required
def orga_ci_character_inventory(request, s, n):
    #return HttpResponse("Hello World: orga_ci_character_inventory is wired up correctly.")
    ctx = check_event_permission(request, s, n, "orga_ci_character_inventory")
    #ctx["px_user"] = ctx["event"].get_config("px_user", False)
    #ctx["list"] = ctx["event"].get_elements(AbilityPx).order_by("number")
    return render(request, "larpmanager/orga/ci/character_inventories.html", ctx)


@login_required
def orga_ci_pool_types(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_ci_pool_types")
    return render(request, "larpmanager/orga/ci/ci_pool_types.html", ctx)


@login_required
def orga_ci_pool_types_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_ci_pool_types", OrgaPoolTypePxForm, num)