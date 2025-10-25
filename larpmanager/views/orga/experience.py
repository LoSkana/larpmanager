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

from larpmanager.cache.config import get_event_config
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
def orga_px_deliveries(request: HttpRequest, s: str) -> HttpResponse:
    """Display list of experience deliveries for an event."""
    # Verify user has permission and retrieve event context
    context = check_event_permission(request, s, "orga_px_deliveries")

    # Get all deliveries ordered by number
    context["list"] = context["event"].get_elements(DeliveryPx).order_by("number")

    return render(request, "larpmanager/orga/px/deliveries.html", context)


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
    context = check_event_permission(request, s, "orga_px_abilities")

    # Handle file export request if download parameter is present
    if request.POST and request.POST.get("download") == "1":
        raise ReturnNowError(zip_exports(context, export_abilities(context), "Abilities"))

    # Process any bulk ability operations from form submission
    handle_bulk_ability(request, context)

    # Configure template context for file upload/download functionality
    context["upload"] = "px_abilities"
    context["download"] = 1

    # Retrieve event configuration for user PX management permissions
    context["px_user"] = get_event_config(context["event"].id, "px_user", False, context)

    # Query and prepare abilities list with optimized database access
    context["list"] = (
        context["event"]
        .get_elements(AbilityPx)
        .order_by("number")
        .select_related("typ")
        .prefetch_related("requirements", "prerequisites")
    )

    # Render the abilities management template with populated context
    return render(request, "larpmanager/orga/px/abilities.html", context)


@login_required
def orga_px_abilities_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit organization PX abilities with validation for ability types.

    Args:
        request: HTTP request object
        s: Event slug identifier
        num: Ability ID number for editing

    Returns:
        HTTP response for ability editing or redirect
    """
    # Check user permissions for PX abilities management
    context = check_event_permission(request, s, "orga_px_abilities")

    # Validate that ability types exist before allowing ability creation
    if not context["event"].get_elements(AbilityTypePx).exists():
        # Warn user and redirect to ability types creation page
        messages.warning(request, _("You must create at least one ability type before you can create abilities"))
        return redirect("orga_px_ability_types_edit", s=s, num=0)

    # Process ability editing with standard organization edit workflow
    return orga_edit(request, s, "orga_px_abilities", OrgaAbilityPxForm, num)


@login_required
def orga_px_ability_types(request: HttpRequest, s: str) -> HttpResponse:
    """Display ability type list for experience management."""
    # Check user has permission to access ability types management
    context = check_event_permission(request, s, "orga_px_ability_types")

    # Retrieve and order ability types by number
    context["list"] = context["event"].get_elements(AbilityTypePx).order_by("number")

    return render(request, "larpmanager/orga/px/ability_types.html", context)


@login_required
def orga_px_ability_types_edit(request, s, num):
    return orga_edit(request, s, "orga_px_ability_types", OrgaAbilityTypePxForm, num)


@login_required
def orga_px_rules(request: HttpRequest, s: str) -> HttpResponse:
    """Display experience rules for an event."""
    # Check permission and get event context
    context = check_event_permission(request, s, "orga_px_rules")
    context["list"] = context["event"].get_elements(RulePx).order_by("order")
    return render(request, "larpmanager/orga/px/rules.html", context)


@login_required
def orga_px_rules_edit(request, s, num):
    return orga_edit(request, s, "orga_px_rules", OrgaRulePxForm, num)


@login_required
def orga_px_rules_order(
    request: HttpRequest,
    s: str,
    num: int,
    order: str,
) -> HttpResponse:
    """Reorder PX rules for an event."""
    # Check permissions and get event context
    context = check_event_permission(request, s, "orga_px_rules")

    # Exchange rule order in database
    exchange_order(context, RulePx, num, order)

    return redirect("orga_px_rules", s=context["run"].get_slug())


@login_required
def orga_px_modifiers(request: HttpRequest, s: str) -> HttpResponse:
    """Display and manage experience modifiers for an event."""
    # Check permissions and get event context
    context = check_event_permission(request, s, "orga_px_modifiers")

    # Retrieve ordered list of experience modifiers
    context["list"] = context["event"].get_elements(ModifierPx).order_by("order")

    return render(request, "larpmanager/orga/px/modifiers.html", context)


@login_required
def orga_px_modifiers_edit(request, s, num):
    return orga_edit(request, s, "orga_px_modifiers", OrgaModifierPxForm, num)


@login_required
def orga_px_modifiers_order(
    request: HttpRequest,
    s: str,
    num: int,
    order: str,
) -> HttpResponse:
    """Reorder experience modifiers in the organizer interface."""
    # Check permissions and get context
    context = check_event_permission(request, s, "orga_px_modifiers")

    # Exchange modifier order
    exchange_order(context, ModifierPx, num, order)

    return redirect("orga_px_modifiers", s=context["run"].get_slug())
