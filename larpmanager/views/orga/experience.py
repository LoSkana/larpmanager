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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.experience import (
    OrgaAbilityPxForm,
    OrgaAbilityTypePxForm,
    OrgaDeliveryPxForm,
    OrgaModifierPxForm,
    OrgaRulePxForm,
)
from larpmanager.models.experience import AbilityPx, AbilityTypePx, DeliveryPx, ModifierPx, RulePx
from larpmanager.utils.bulk import handle_bulk_ability
from larpmanager.utils.common import exchange_order
from larpmanager.utils.download import export_abilities, zip_exports
from larpmanager.utils.edit import orga_edit
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.exceptions import ReturnNowError


@login_required
def orga_px_deliveries(request, s):
    ctx = check_event_permission(request, s, "orga_px_deliveries")
    ctx["list"] = ctx["event"].get_elements(DeliveryPx).order_by("number")
    return render(request, "larpmanager/orga/px/deliveries.html", ctx)


@login_required
def orga_px_deliveries_edit(request, s, num):
    return orga_edit(request, s, "orga_px_deliveries", OrgaDeliveryPxForm, num)


@login_required
def orga_px_abilities(request: HttpRequest, s: str) -> HttpResponse:
    """Display and manage PX (experience) abilities for organizers.

    This view handles the display of abilities available for purchase with experience points,
    allowing organizers to manage the ability catalog for their events. It supports both
    viewing the abilities list and exporting abilities data as a downloadable file.

    Args:
        request: Django HTTP request object containing user session and POST data
        s: Event slug identifier used to identify the specific event

    Returns:
        HttpResponse: Rendered abilities management page template or file export response

    Raises:
        ReturnNowError: When file download is requested, triggers immediate file response
    """
    # Check user permissions and retrieve event context
    ctx = check_event_permission(request, s, "orga_px_abilities")

    # Handle file export request if download parameter is present
    if request.POST and request.POST.get("download") == "1":
        raise ReturnNowError(zip_exports(ctx, export_abilities(ctx), "Abilities"))

    # Process any bulk ability operations from form submission
    handle_bulk_ability(request, ctx)

    # Configure template context for file upload/download functionality
    ctx["upload"] = "px_abilities"
    ctx["download"] = 1

    # Retrieve event configuration for user PX management permissions
    ctx["px_user"] = ctx["event"].get_config("px_user", False)

    # Query and prepare abilities list with optimized database access
    ctx["list"] = (
        ctx["event"]
        .get_elements(AbilityPx)
        .order_by("number")
        .select_related("typ")
        .prefetch_related("requirements", "prerequisites")
    )

    # Render the abilities management template with populated context
    return render(request, "larpmanager/orga/px/abilities.html", ctx)


@login_required
def orga_px_abilities_edit(request, s, num):
    ctx = check_event_permission(request, s, "orga_px_abilities")

    # Check if ability types exist
    if not ctx["event"].get_elements(AbilityTypePx).exists():
        # Add warning message and redirect to ability types adding page
        messages.warning(request, _("You must create at least one ability type before you can create abilities"))
        return redirect("orga_px_ability_types_edit", s=s, num=0)

    return orga_edit(request, s, "orga_px_abilities", OrgaAbilityPxForm, num)


@login_required
def orga_px_ability_types(request, s):
    ctx = check_event_permission(request, s, "orga_px_ability_types")
    ctx["list"] = ctx["event"].get_elements(AbilityTypePx).order_by("number")
    return render(request, "larpmanager/orga/px/ability_types.html", ctx)


@login_required
def orga_px_ability_types_edit(request, s, num):
    return orga_edit(request, s, "orga_px_ability_types", OrgaAbilityTypePxForm, num)


@login_required
def orga_px_rules(request, s):
    ctx = check_event_permission(request, s, "orga_px_rules")
    ctx["list"] = ctx["event"].get_elements(RulePx).order_by("order")
    return render(request, "larpmanager/orga/px/rules.html", ctx)


@login_required
def orga_px_rules_edit(request, s, num):
    return orga_edit(request, s, "orga_px_rules", OrgaRulePxForm, num)


@login_required
def orga_px_rules_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_px_rules")
    exchange_order(ctx, RulePx, num, order)
    return redirect("orga_px_rules", s=ctx["run"].get_slug())


@login_required
def orga_px_modifiers(request, s):
    ctx = check_event_permission(request, s, "orga_px_modifiers")
    ctx["list"] = ctx["event"].get_elements(ModifierPx).order_by("order")
    return render(request, "larpmanager/orga/px/modifiers.html", ctx)


@login_required
def orga_px_modifiers_edit(request, s, num):
    return orga_edit(request, s, "orga_px_modifiers", OrgaModifierPxForm, num)


@login_required
def orga_px_modifiers_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_px_modifiers")
    exchange_order(ctx, ModifierPx, num, order)
    return redirect("orga_px_modifiers", s=ctx["run"].get_slug())
