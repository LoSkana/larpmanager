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
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_POST

from larpmanager.forms.characterinventory import OrgaPoolTypePxForm, OrgaCharacterInventoryForm
from larpmanager.models.characterinventory import PoolTypeCI, CharacterInventory
from larpmanager.services.ci_transfer import perform_transfer
from larpmanager.utils.edit import orga_edit
from larpmanager.utils.event import check_event_permission


@login_required
def orga_ci_character_inventory(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_ci_character_inventory")
    ctx["list"] = ctx["event"].get_elements(CharacterInventory).order_by("number")
    return render(request, "larpmanager/orga/ci/character_inventories.html", ctx)


@login_required
def orga_ci_character_inventory_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_ci_character_inventory", OrgaCharacterInventoryForm, num)


@login_required
def orga_ci_pool_types(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_ci_pool_types")
    ctx["list"] = ctx["event"].get_elements(PoolTypeCI).order_by("number")
    return render(request, "larpmanager/orga/ci/ci_pool_types.html", ctx)


@login_required
def orga_ci_pool_types_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_ci_pool_types", OrgaPoolTypePxForm, num)

import logging
logger = logging.getLogger(__name__)


@login_required
def orga_ci_character_inventory_view(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_ci_character_inventory")

    ctx["character_inventory"] = CharacterInventory.objects.get(pk=num, event=ctx["event"])

    ctx["pool_balances_list"] = ctx["character_inventory"].get_pool_balances()

    ctx["all_inventories"] = CharacterInventory.objects.filter(event=ctx["event"]).order_by("number")

    return render(request, "larpmanager/orga/ci/character_inventory.html", ctx)


@require_POST
def orga_ci_transfer(request, s, n):
    actor = request.user

    # Get source inventory
    source_inventory_id = request.POST.get("source_inventory")
    source_inventory = None
    if source_inventory_id:
        source_inventory = get_object_or_404(CharacterInventory, id=source_inventory_id)

    # Get target inventory
    target_inventory_id = request.POST.get("target_inventory")
    target_inventory = None
    if target_inventory_id:
        target_inventory = get_object_or_404(CharacterInventory, id=target_inventory_id)

    # Permission enforcement
    if source_inventory is None and not request.user.is_staff:
        messages.error(request, "Only staff can transfer from NPC.")
        redirect_pk = target_inventory.id if target_inventory else 0
        return redirect("orga_ci_character_inventory_view", s=s, n=n, num=redirect_pk)

    # Get pool type and amount
    pool_type = get_object_or_404(PoolTypeCI, id=request.POST.get("pool_type"))
    try:
        amount = int(request.POST.get("amount"))
    except (TypeError, ValueError):
        messages.error(request, "Invalid transfer amount.")
        redirect_pk = source_inventory.id if source_inventory else 0
        return redirect("orga_ci_character_inventory_view", s=s, n=n, num=redirect_pk)

    # Perform the transfer
    try:
        perform_transfer(actor, pool_type, amount, source=source_inventory, target=target_inventory, reason="manual")
        src_name = source_inventory.name if source_inventory else "NPC"
        tgt_name = target_inventory.name if target_inventory else "NPC"
        messages.success(request, f"Transferred {amount} {pool_type.name} from {src_name} to {tgt_name}.")
    except Exception as e:
        messages.error(request, f"Transfer failed: {str(e)}")

    redirect_pk = source_inventory.id if source_inventory else (target_inventory.id if target_inventory else 0)
    return redirect("orga_ci_character_inventory_view", s=s, n=n, num=redirect_pk)
