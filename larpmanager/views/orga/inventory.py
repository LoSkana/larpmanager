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
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from larpmanager.forms.inventory import OrgaInventoryForm, OrgaPoolTypePxForm
from larpmanager.models.inventory import Inventory, InventoryTransfer, PoolTypeCI
from larpmanager.utils.auth.permission import has_event_permission
from larpmanager.utils.core.base import check_event_context, get_event_context
from larpmanager.utils.core.common import get_element_event
from larpmanager.utils.services.edit import orga_edit
from larpmanager.utils.services.inventory import perform_transfer

logger = logging.getLogger(__name__)


@login_required
def orga_ci_inventory(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display list of all character inventories for an event."""
    context = check_event_context(request, event_slug, "orga_ci_inventory")
    context["list"] = context["event"].get_elements(Inventory).order_by("number")
    return render(request, "larpmanager/orga/ci/inventories.html", context)


@login_required
def orga_ci_inventory_edit(request: HttpRequest, event_slug: str, inventory_uuid: str) -> HttpResponse:
    """Edit a character inventory."""
    return orga_edit(request, event_slug, "orga_ci_inventory", OrgaInventoryForm, inventory_uuid)


@login_required
def orga_ci_pool_types(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display list of pool types for character inventory."""
    context = check_event_context(request, event_slug, "orga_ci_pool_types")
    context["list"] = context["event"].get_elements(PoolTypeCI).order_by("number")
    return render(request, "larpmanager/orga/ci/pool_types.html", context)


@login_required
def orga_ci_pool_types_edit(request: HttpRequest, event_slug: str, pool_uuid: str) -> HttpResponse:
    """Edit a pool type for character inventory."""
    return orga_edit(request, event_slug, "orga_ci_pool_types", OrgaPoolTypePxForm, pool_uuid)


@login_required
def orga_ci_inventory_view(request: HttpRequest, event_slug: str, inventory_uuid: str) -> HttpResponse:
    """View a specific character inventory with balances and transfer history."""
    context = get_event_context(request, event_slug, signup=True)

    ci = get_element_event(context, inventory_uuid, Inventory)

    if (
        not has_event_permission(request, context, event_slug, "orga_ci_inventory")
        and not ci.owners.filter(player=request.user.member).exists()
    ):
        messages.error(request, "You do not have access to this inventory.")
        return redirect("orga_ci_inventory", event_slug=event_slug)

    context["inventory"] = ci
    context["pool_balances_list"] = ci.get_pool_balances()
    context["all_inventories"] = Inventory.objects.filter(event=context["event"]).order_by("number")

    # All incoming + outgoing transfers
    context["transfers"] = InventoryTransfer.objects.filter(
        models.Q(source_inventory=ci) | models.Q(target_inventory=ci)
    ).select_related("source_inventory", "target_inventory", "pool_type", "actor")

    context["can_edit_from_npc"] = has_event_permission(request, context, event_slug, "orga_ci_inventory")

    return render(request, "larpmanager/orga/ci/inventory.html", context)


@require_POST
def orga_ci_transfer(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Handle inventory resource transfers between characters or from/to NPC bank."""
    context = get_event_context(request, event_slug, signup=True)
    actor = request.user.member

    # Get source inventory
    source_inventory_uuid = request.POST.get("source_inventory")
    source_inventory = None
    if source_inventory_uuid:
        source_inventory = get_object_or_404(Inventory, uuid=source_inventory_uuid)

    # Get target inventory
    target_inventory_uuid = request.POST.get("target_inventory")
    target_inventory = None
    if target_inventory_uuid:
        target_inventory = get_object_or_404(Inventory, uuid=target_inventory_uuid)

    # Permission enforcement
    if source_inventory:
        if not source_inventory.owners.filter(player=request.user.member).exists() and not has_event_permission(
            request, context, event_slug, "orga_ci_inventory"
        ):
            messages.error(request, "Only staff can transfer from this inventory.")
            redirect_pk = target_inventory.uuid if target_inventory else "0"
            return redirect("orga_ci_inventory_view", event_slug=context["run"].get_slug(), inventory_uuid=redirect_pk)
    elif not has_event_permission(request, context, event_slug, "orga_ci_inventory"):
        messages.error(request, "Only staff can transfer from NPC.")
        redirect_pk = target_inventory.uuid if target_inventory else "0"
        return redirect("orga_ci_inventory_view", event_slug=context["run"].get_slug(), inventory_uuid=redirect_pk)

    # Get pool type and amount
    pool_type = get_object_or_404(PoolTypeCI, uuid=request.POST.get("pool_type"))
    try:
        amount = int(request.POST.get("amount"))
    except (TypeError, ValueError):
        messages.error(request, "Invalid transfer amount.")
        redirect_pk = source_inventory.uuid if source_inventory else 0
        return redirect("orga_ci_inventory_view", event_slug=context["run"].get_slug(), inventory_uuid=redirect_pk)

    reason = request.POST.get("reason", "").strip() or "manual"

    # Perform the transfer
    try:
        perform_transfer(actor, pool_type, amount, source=source_inventory, target=target_inventory, reason=reason)
        src_name = source_inventory.name if source_inventory else "NPC"
        tgt_name = target_inventory.name if target_inventory else "NPC"
        messages.success(request, f"Transferred {amount} {pool_type.name} from {src_name} to {tgt_name}.")
    except ValueError as e:
        messages.error(request, f"Transfer failed: {e!s}")

    redirect_pk = source_inventory.uuid if source_inventory else (target_inventory.uuid if target_inventory else "0")
    return redirect("orga_ci_inventory_view", event_slug=context["run"].get_slug(), inventory_uuid=redirect_pk)
