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
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_event_config
from larpmanager.cache.px import get_event_px_cache
from larpmanager.forms.experience import (
    OrgaAbilityPxForm,
    OrgaAbilityTemplatePxForm,
    OrgaAbilityTypePxForm,
    OrgaDeliveryPxForm,
    OrgaModifierPxForm,
    OrgaRulePxForm,
)
from larpmanager.models.event import Run
from larpmanager.models.experience import AbilityPx, AbilityTemplatePx, AbilityTypePx, DeliveryPx, ModifierPx, RulePx
from larpmanager.models.registration import Registration
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.core.common import exchange_order, get_object_uuid
from larpmanager.utils.core.exceptions import ReturnNowError
from larpmanager.utils.io.download import export_abilities, zip_exports
from larpmanager.utils.services.bulk import handle_bulk_ability
from larpmanager.utils.services.edit import orga_delete, orga_edit


@login_required
def orga_px_deliveries(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display list of experience deliveries for an event."""
    # Verify user has permission and retrieve event context
    context = check_event_context(request, event_slug, "orga_px_deliveries")

    # Get all deliveries ordered by number
    deliveries = list(context["event"].get_elements(DeliveryPx).order_by("number"))

    # Get cached PX relationship data and enrich delivery objects
    px_cache = get_event_px_cache(context["event"])
    for delivery in deliveries:
        if "deliveries" in px_cache and delivery.id in px_cache["deliveries"]:
            delivery.cached_rels = px_cache["deliveries"][delivery.id]

    context["list"] = deliveries

    return render(request, "larpmanager/orga/px/deliveries.html", context)


@login_required
def orga_px_deliveries_edit(request: HttpRequest, event_slug: str, delivery_uuid: str) -> HttpResponse:
    """Edit a delivery for an event.

    When creating a new delivery (delivery_uuid == "0"), if a run is selected via the
    auto_populate_run field, the form will be reloaded with characters from that run's
    registrations pre-populated in the characters field.
    """
    # Check user permissions and get base context for the event
    context = check_event_context(request, event_slug, "orga_px_deliveries")

    # Handle auto-population from run selection
    if request.method == "POST" and delivery_uuid == "0":
        run_uuid = request.POST.get("auto_populate_run")

        # If a run was selected, get all characters from that run's registrations
        if run_uuid:
            try:
                run = get_object_uuid(Run, run_uuid)

                # Get all characters assigned to registrations for this run
                character_ids = (
                    Registration.objects.filter(run=run, cancellation_date__isnull=True)
                    .values_list("characters__id", flat=True)
                    .distinct()
                )

                # Filter registrations without characters
                character_ids = [cid for cid in character_ids if cid is not None]

                # Pass the POST data but override the characters field
                form_data = request.POST.copy()
                form_data.setlist("characters", [str(cid) for cid in character_ids])

                # Create the form with pre-populated data
                form = OrgaDeliveryPxForm(form_data, instance=None, context=context)

                # Hide the auto_populate_run field now that characters are loaded
                form.fields.pop("auto_populate_run", None)

                # Set up context for rendering
                context["form"] = form
                context["num"] = "0"
                context["add_another"] = True
                context["continue_add"] = False
                context["elementTyp"] = DeliveryPx

                # Add success message to inform user
                messages.info(
                    request,
                    _("Characters from event '{run}' have been loaded. Review and confirm to save.").format(run=run),
                )

                return render(request, "larpmanager/orga/edit.html", context)

            except (ValueError, ObjectDoesNotExist):
                # If run retrieval fails, continue with normal flow
                pass

    # Use standard orga_edit for all other cases
    return orga_edit(request, event_slug, "orga_px_deliveries", OrgaDeliveryPxForm, delivery_uuid)


@login_required
def orga_px_deliveries_delete(request: HttpRequest, event_slug: str, delivery_uuid: str) -> HttpResponse:
    """Delete delivery for event."""
    return orga_delete(request, event_slug, "orga_px_deliveries", OrgaDeliveryPxForm, delivery_uuid)


@login_required
def orga_px_abilities(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage PX (experience) abilities for organizers.

    This view handles the display of abilities available for purchase with experience points,
    allowing organizers to manage the ability catalog for their events. It supports both
    viewing the abilities list and exporting abilities data as a downloadable file.

    Args:
        request: Django HTTP request object containing user session and POST data
        event_slug: Event slug identifier used to identify the specific event

    Returns:
        HttpResponse: Rendered abilities management page template or file export response

    Raises:
        ReturnNowError: When file download is requested, triggers immediate file response

    """
    # Check user permissions and retrieve event context
    context = check_event_context(request, event_slug, "orga_px_abilities")

    # Handle file export request if download parameter is present
    if request.POST and request.POST.get("download") == "1":
        raise ReturnNowError(zip_exports(context, export_abilities(context), "Abilities"))

    # Process any bulk ability operations from form submission
    handle_bulk_ability(request, context)

    # Configure template context for file upload/download functionality
    context["upload"] = "px_abilities"
    context["download"] = 1

    # Retrieve event configuration for user PX management permissions
    context["px_user"] = get_event_config(context["event"].id, "px_user", default_value=False, context=context)
    context["px_templates"] = get_event_config(
        context["event"].id, "px_templates", default_value=False, context=context
    )

    # Query and prepare abilities list with optimized database access
    abilities = list(context["event"].get_elements(AbilityPx).order_by("number").select_related("typ"))

    # Get cached PX relationship data and enrich ability objects
    px_cache = get_event_px_cache(context["event"])
    for ability in abilities:
        if "abilities" in px_cache and ability.id in px_cache["abilities"]:
            ability.cached_rels = px_cache["abilities"][ability.id]

    context["list"] = abilities

    # Render the abilities management template with populated context
    return render(request, "larpmanager/orga/px/abilities.html", context)


@login_required
def orga_px_abilities_edit(request: HttpRequest, event_slug: str, ability_uuid: str) -> HttpResponse:
    """Edit organization PX abilities with validation for ability types.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        ability_uuid: Ability UUID for editing

    Returns:
        HTTP response for ability editing or redirect

    """
    # Check user permissions for PX abilities management
    context = check_event_context(request, event_slug, "orga_px_abilities")

    # Validate that ability types exist before allowing ability creation
    if not context["event"].get_elements(AbilityTypePx).exists():
        # Warn user and redirect to ability types creation page
        messages.warning(request, _("You must create at least one ability type before you can create abilities"))
        return redirect("orga_px_ability_types_edit", event_slug=event_slug, type_uuid="0")

    # Process ability editing with standard organization edit workflow
    return orga_edit(request, event_slug, "orga_px_abilities", OrgaAbilityPxForm, ability_uuid)


@login_required
def orga_px_abilities_delete(request: HttpRequest, event_slug: str, ability_uuid: str) -> HttpResponse:
    """Delete ability for event."""
    return orga_delete(request, event_slug, "orga_px_abilities", OrgaAbilityPxForm, ability_uuid)


@login_required
def orga_px_ability_types(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display ability type list for experience management."""
    # Check user has permission to access ability types management
    context = check_event_context(request, event_slug, "orga_px_ability_types")

    # Retrieve and order ability types by number
    context["list"] = context["event"].get_elements(AbilityTypePx).order_by("number")

    return render(request, "larpmanager/orga/px/ability_types.html", context)


@login_required
def orga_px_ability_types_edit(request: HttpRequest, event_slug: str, type_uuid: str) -> HttpResponse:
    """Edit ability type for PX system."""
    return orga_edit(request, event_slug, "orga_px_ability_types", OrgaAbilityTypePxForm, type_uuid)


@login_required
def orga_px_ability_types_delete(request: HttpRequest, event_slug: str, type_uuid: str) -> HttpResponse:
    """Delete type for event."""
    return orga_delete(request, event_slug, "orga_px_ability_types", OrgaAbilityTypePxForm, type_uuid)


@login_required
def orga_px_rules(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display experience rules for an event."""
    context = check_event_context(request, event_slug, "orga_px_rules")
    # Get all rules ordered
    rules = list(context["event"].get_elements(RulePx).order_by("order"))
    # Get cached PX relationship data and enrich rule objects
    px_cache = get_event_px_cache(context["event"])
    for rule in rules:
        if "rules" in px_cache and rule.id in px_cache["rules"]:
            rule.cached_rels = px_cache["rules"][rule.id]
    context["list"] = rules
    return render(request, "larpmanager/orga/px/rules.html", context)


@login_required
def orga_px_ability_templates(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display list of ability templates for an event."""
    context = check_event_context(request, event_slug, "orga_px_ability_templates")
    context["list"] = context["event"].get_elements(AbilityTemplatePx).order_by("number")
    return render(request, "larpmanager/orga/px/ability_templates.html", context)


@login_required
def orga_px_ability_templates_edit(request: HttpRequest, event_slug: str, template_uuid: str) -> HttpResponse:
    """Edit a specific rule for an event."""
    return orga_edit(request, event_slug, "orga_px_ability_templates", OrgaAbilityTemplatePxForm, template_uuid)


@login_required
def orga_px_ability_templates_delete(request: HttpRequest, event_slug: str, template_uuid: str) -> HttpResponse:
    """Delete template for event."""
    return orga_delete(request, event_slug, "orga_px_ability_templates", OrgaAbilityTemplatePxForm, template_uuid)


@login_required
def orga_px_rules_edit(request: HttpRequest, event_slug: str, rule_uuid: str) -> HttpResponse:
    """Edit a specific rule for an event."""
    return orga_edit(request, event_slug, "orga_px_rules", OrgaRulePxForm, rule_uuid)


@login_required
def orga_px_rules_delete(request: HttpRequest, event_slug: str, rule_uuid: str) -> HttpResponse:
    """Delete rule for event."""
    return orga_delete(request, event_slug, "orga_px_rules", OrgaRulePxForm, rule_uuid)


@login_required
def orga_px_rules_order(
    request: HttpRequest,
    event_slug: str,
    rule_uuid: str,
    order: int,
) -> HttpResponse:
    """Reorder PX rules for an event."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_px_rules")

    # Exchange rule order in database
    exchange_order(context, RulePx, rule_uuid, order)

    return redirect("orga_px_rules", event_slug=context["run"].get_slug())


@login_required
def orga_px_modifiers(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage experience modifiers for an event."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_px_modifiers")

    # Retrieve ordered list of experience modifiers
    modifiers = list(context["event"].get_elements(ModifierPx).order_by("order"))

    # Get cached PX relationship data and enrich modifier objects
    px_cache = get_event_px_cache(context["event"])
    for modifier in modifiers:
        if "modifiers" in px_cache and modifier.id in px_cache["modifiers"]:
            modifier.cached_rels = px_cache["modifiers"][modifier.id]

    context["list"] = modifiers

    return render(request, "larpmanager/orga/px/modifiers.html", context)


@login_required
def orga_px_modifiers_edit(request: HttpRequest, event_slug: str, modifier_uuid: str) -> HttpResponse:
    """Edit experience modifier for an event."""
    return orga_edit(request, event_slug, "orga_px_modifiers", OrgaModifierPxForm, modifier_uuid)


@login_required
def orga_px_modifiers_delete(request: HttpRequest, event_slug: str, modifier_uuid: str) -> HttpResponse:
    """Delete modifier for event."""
    return orga_delete(request, event_slug, "orga_px_modifiers", OrgaModifierPxForm, modifier_uuid)


@login_required
def orga_px_modifiers_order(
    request: HttpRequest,
    event_slug: str,
    modifier_uuid: str,
    order: int,
) -> HttpResponse:
    """Reorder experience modifiers in the organizer interface."""
    # Check permissions and get context
    context = check_event_context(request, event_slug, "orga_px_modifiers")

    # Exchange modifier order
    exchange_order(context, ModifierPx, modifier_uuid, order)

    return redirect("orga_px_modifiers", event_slug=context["run"].get_slug())
