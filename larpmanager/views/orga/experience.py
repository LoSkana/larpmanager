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
import contextlib
import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from larpmanager.cache.config import get_event_config
from larpmanager.cache.experience import get_event_exp_cache, get_event_exp_systems
from larpmanager.forms.experience import (
    OrgaDeliveryExpForm,
    OrgaDeliveryExpLoadForm,
)
from larpmanager.models.event import Run
from larpmanager.models.experience import (
    AbilityExp,
    AbilityTemplateExp,
    AbilityTypeExp,
    CriterionExp,
    DeliveryExp,
    ModifierExp,
    RuleExp,
    SystemExp,
)
from larpmanager.models.registration import Registration
from larpmanager.models.writing import Character
from larpmanager.utils.core.base import check_event_context, get_event_context
from larpmanager.utils.core.exceptions import FeatureError, ReturnNowError, UserPermissionError
from larpmanager.utils.edit.base import render_frame_or_fallback
from larpmanager.utils.edit.orga import OrgaAction, orga_delete, orga_edit, orga_new
from larpmanager.utils.io.download import export_abilities, export_modifiers, export_rules, zip_exports
from larpmanager.utils.services.bulk import handle_bulk_ability

logger = logging.getLogger(__name__)


@login_required
def orga_exp_systems(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display list of experience systems for an event."""
    context = check_event_context(request, event_slug, "orga_exp_systems")
    context["list"] = context["event"].get_elements(SystemExp).order_by("order")
    return render(request, "larpmanager/orga/experience/systems.html", context)


@login_required
def orga_exp_systems_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new experience system for an event."""
    return orga_new(request, event_slug, OrgaAction.PX_SYSTEMS)


@login_required
def orga_exp_systems_edit(request: HttpRequest, event_slug: str, system_uuid: str) -> HttpResponse:
    """Edit an experience system for an event."""
    return orga_edit(request, event_slug, OrgaAction.PX_SYSTEMS, system_uuid)


@login_required
def orga_exp_deliveries(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display list of experience deliveries for an event."""
    # Verify user has permission and retrieve event context
    context = check_event_context(request, event_slug, "orga_exp_deliveries")

    # Expose system column only when multiple systems are configured
    context["multiple_systems"] = len(get_event_exp_systems(context["event"])) > 1

    # Get all deliveries ordered by number
    deliveries = list(context["event"].get_elements(DeliveryExp).order_by("order").select_related("system"))

    # Get cached EXP relationship data and enrich delivery objects
    px_cache = get_event_exp_cache(context["event"])
    for delivery in deliveries:
        if delivery.id in px_cache.get("deliveries", {}):
            delivery.cached_rels = px_cache["deliveries"][delivery.id]

    context["list"] = deliveries

    return render(request, "larpmanager/orga/experience/deliveries.html", context)


@login_required
def orga_exp_deliveries_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new delivery of experience points.

    If ?run_id=<id> is present on GET, characters from that run's registrations are pre-populated.
    """
    run_id = request.GET.get("run_id")
    if request.method == "GET" and run_id:
        context = check_event_context(request, event_slug, "orga_exp_deliveries")
        try:
            run = Run.objects.get(uuid=run_id, event__slug=event_slug)
            character_ids = (
                Registration.objects.filter(run=run, cancellation_date__isnull=True)
                .values_list("characters__id", flat=True)
                .distinct()
            )
            character_ids = [cid for cid in character_ids if cid is not None]
            character_uuids = list(Character.objects.filter(id__in=character_ids).values_list("uuid", flat=True))
            form = OrgaDeliveryExpForm(
                instance=None,
                context=context,
                initial={"characters": [str(u) for u in character_uuids]},
            )
            context["form"] = form
            context["num"] = None
            context["add_another"] = True
            context["continue_add"] = False
            context["elementTyp"] = DeliveryExp
            is_frame = request.GET.get("frame") == "1"
            return render_frame_or_fallback(request, context, is_frame, "larpmanager/orga/edit.html")
        except (ValueError, ObjectDoesNotExist) as err:
            logger.warning("Pre-populate run failed: %s", err)

    return orga_new(request, event_slug, OrgaAction.PX_DELIVERIES)


@login_required
def orga_exp_deliveries_load(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Show a modal form to select a run; on submit redirect to new delivery with characters pre-loaded."""
    context = check_event_context(request, event_slug, "orga_exp_deliveries")
    is_frame = request.GET.get("frame") == "1" or request.POST.get("frame") == "1"

    if request.method == "POST":
        form = OrgaDeliveryExpLoadForm(request.POST, context=context)
        if form.is_valid():
            run = form.cleaned_data["run"]
            new_url = reverse("orga_exp_deliveries_new", args=[event_slug]) + f"?run_id={run.uuid}&frame=1"
            return redirect(new_url)
        context["form"] = form
    else:
        context["form"] = OrgaDeliveryExpLoadForm(context=context)

    context["elementTyp"] = DeliveryExp
    return render_frame_or_fallback(request, context, is_frame, "larpmanager/orga/experience/deliveries_load.html")


@login_required
def orga_exp_deliveries_edit(request: HttpRequest, event_slug: str, delivery_uuid: str) -> HttpResponse:
    """Edit a delivery for an event."""
    return orga_edit(request, event_slug, OrgaAction.PX_DELIVERIES, delivery_uuid)


@login_required
def orga_exp_deliveries_delete(request: HttpRequest, event_slug: str, delivery_uuid: str) -> HttpResponse:
    """Delete delivery for event."""
    return orga_delete(request, event_slug, OrgaAction.PX_DELIVERIES, delivery_uuid)


@login_required
def orga_exp_abilities(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage EXP (experience) abilities for organizers.

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
    context = check_event_context(request, event_slug, "orga_exp_abilities")

    # Handle file export request if download parameter is present
    if request.POST and request.POST.get("download") == "1":
        raise ReturnNowError(zip_exports(context, export_abilities(context), "Abilities"))

    # Process any bulk ability operations from form submission
    handle_bulk_ability(request, context)

    # Configure template context for file upload/download functionality
    context["upload"] = "exp_abilities"
    context["download"] = 1

    # Retrieve event configuration for user EXP management permissions
    context["exp_user"] = get_event_config(context["event"].id, "exp_user", default_value=False, context=context)
    context["exp_templates"] = get_event_config(
        context["event"].id, "exp_templates", default_value=False, context=context
    )

    # Expose system column only when multiple systems are configured
    context["multiple_systems"] = len(get_event_exp_systems(context["event"])) > 1

    # Query and prepare abilities list with optimized database access
    abilities = list(context["event"].get_elements(AbilityExp).order_by("order").select_related("typ", "system"))

    # Get cached EXP relationship data and enrich ability objects
    px_cache = get_event_exp_cache(context["event"])
    for ability in abilities:
        ability.cached_rels = px_cache.get("abilities", {}).get(ability.id, [])

    context["list"] = abilities

    # Render the abilities management template with populated context
    return render(request, "larpmanager/orga/experience/abilities.html", context)


@login_required
def orga_exp_abilities_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create organization EXP abilities."""
    return orga_new(request, event_slug, OrgaAction.PX_ABILITIES)


@login_required
def orga_exp_abilities_edit(request: HttpRequest, event_slug: str, ability_uuid: str) -> HttpResponse:
    """Edit organization EXP abilities."""
    return orga_edit(request, event_slug, OrgaAction.PX_ABILITIES, ability_uuid)


@login_required
def orga_exp_abilities_delete(request: HttpRequest, event_slug: str, ability_uuid: str) -> HttpResponse:
    """Delete ability for event."""
    return orga_delete(request, event_slug, OrgaAction.PX_ABILITIES, ability_uuid)


@login_required
def orga_exp_ability_types(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display ability type list for experience management."""
    # Check user has permission to access ability types management
    context = check_event_context(request, event_slug, "orga_exp_ability_types")

    # Retrieve and order ability types by number
    context["list"] = context["event"].get_elements(AbilityTypeExp).order_by("order")

    return render(request, "larpmanager/orga/experience/ability_types.html", context)


@login_required
def orga_exp_ability_types_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create ability type for EXP system."""
    return orga_new(request, event_slug, OrgaAction.PX_ABILITY_TYPES)


@login_required
def orga_exp_ability_types_edit(request: HttpRequest, event_slug: str, type_uuid: str) -> HttpResponse:
    """Edit ability type for EXP system."""
    return orga_edit(request, event_slug, OrgaAction.PX_ABILITY_TYPES, type_uuid)


@login_required
def orga_exp_ability_types_delete(request: HttpRequest, event_slug: str, type_uuid: str) -> HttpResponse:
    """Delete type for event."""
    return orga_delete(request, event_slug, OrgaAction.PX_ABILITY_TYPES, type_uuid)


@login_required
def orga_exp_rules(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display experience rules for an event."""
    context = check_event_context(request, event_slug, "orga_exp_rules")

    if request.POST and request.POST.get("download") == "1":
        raise ReturnNowError(zip_exports(context, export_rules(context), "Rules"))

    context["upload"] = "exp_rules"
    context["download"] = 1

    # Get all rules ordered
    rules = list(context["event"].get_elements(RuleExp).order_by("order"))
    # Get cached EXP relationship data and enrich rule objects
    px_cache = get_event_exp_cache(context["event"])
    for rule in rules:
        if rule.id in px_cache.get("rules", {}):
            rule.cached_rels = px_cache["rules"][rule.id]
    context["list"] = rules
    return render(request, "larpmanager/orga/experience/rules.html", context)


@login_required
def orga_exp_ability_templates(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display list of ability templates for an event."""
    context = check_event_context(request, event_slug, "orga_exp_ability_templates")
    context["list"] = context["event"].get_elements(AbilityTemplateExp).order_by("order")
    return render(request, "larpmanager/orga/experience/ability_templates.html", context)


@login_required
def orga_exp_ability_templates_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a specific rule for an event."""
    return orga_new(request, event_slug, OrgaAction.PX_ABILITY_TEMPLATES)


@login_required
def orga_exp_ability_templates_edit(request: HttpRequest, event_slug: str, template_uuid: str) -> HttpResponse:
    """Edit a specific rule for an event."""
    return orga_edit(request, event_slug, OrgaAction.PX_ABILITY_TEMPLATES, template_uuid)


@login_required
def orga_exp_ability_templates_delete(request: HttpRequest, event_slug: str, template_uuid: str) -> HttpResponse:
    """Delete template for event."""
    return orga_delete(request, event_slug, OrgaAction.PX_ABILITY_TEMPLATES, template_uuid)


@login_required
def orga_exp_rules_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a specific rule for an event."""
    return orga_new(request, event_slug, OrgaAction.PX_RULES)


@login_required
def orga_exp_rules_edit(request: HttpRequest, event_slug: str, rule_uuid: str) -> HttpResponse:
    """Edit a specific rule for an event."""
    return orga_edit(request, event_slug, OrgaAction.PX_RULES, rule_uuid)


@login_required
def orga_exp_rules_delete(request: HttpRequest, event_slug: str, rule_uuid: str) -> HttpResponse:
    """Delete rule for event."""
    return orga_delete(request, event_slug, OrgaAction.PX_RULES, rule_uuid)


@login_required
def orga_exp_modifiers(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage experience modifiers for an event."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_exp_modifiers")

    if request.POST and request.POST.get("download") == "1":
        raise ReturnNowError(zip_exports(context, export_modifiers(context), "Modifiers"))

    context["upload"] = "exp_modifiers"
    context["download"] = 1

    # Retrieve ordered list of experience modifiers
    modifiers = list(context["event"].get_elements(ModifierExp).order_by("order"))

    # Get cached EXP relationship data and enrich modifier objects
    px_cache = get_event_exp_cache(context["event"])
    for modifier in modifiers:
        if modifier.id in px_cache.get("modifiers", {}):
            modifier.cached_rels = px_cache["modifiers"][modifier.id]

    context["list"] = modifiers

    return render(request, "larpmanager/orga/experience/modifiers.html", context)


@login_required
def orga_exp_modifiers_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create experience modifier for an event."""
    return orga_new(request, event_slug, OrgaAction.PX_MODIFIERS)


@login_required
def orga_exp_modifiers_edit(request: HttpRequest, event_slug: str, modifier_uuid: str) -> HttpResponse:
    """Edit experience modifier for an event."""
    return orga_edit(request, event_slug, OrgaAction.PX_MODIFIERS, modifier_uuid)


@login_required
def orga_exp_modifiers_delete(request: HttpRequest, event_slug: str, modifier_uuid: str) -> HttpResponse:
    """Delete modifier for event."""
    return orga_delete(request, event_slug, OrgaAction.PX_MODIFIERS, modifier_uuid)


@login_required
def orga_exp_criterions(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage experience criterions for an event."""
    context = check_event_context(request, event_slug, "orga_exp_criterions")

    criterions = list(context["event"].get_elements(CriterionExp).order_by("order").select_related("system"))

    px_cache = get_event_exp_cache(context["event"])
    for criterion in criterions:
        if criterion.id in px_cache.get("criterions", {}):
            criterion.cached_rels = px_cache["criterions"][criterion.id]

    context["list"] = criterions
    context["multiple_systems"] = len(get_event_exp_systems(context["event"])) > 1

    return render(request, "larpmanager/orga/experience/criterions.html", context)


@login_required
def orga_exp_criterions_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create experience criterion for an event."""
    return orga_new(request, event_slug, OrgaAction.PX_CRITERIONS)


@login_required
def orga_exp_criterions_edit(request: HttpRequest, event_slug: str, criterion_uuid: str) -> HttpResponse:
    """Edit experience criterion for an event."""
    return orga_edit(request, event_slug, OrgaAction.PX_CRITERIONS, criterion_uuid)


@login_required
def orga_exp_criterions_delete(request: HttpRequest, event_slug: str, criterion_uuid: str) -> HttpResponse:
    """Delete criterion for event."""
    return orga_delete(request, event_slug, OrgaAction.PX_CRITERIONS, criterion_uuid)


@login_required
def orga_character_search(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Return up to 25 characters matching a search term for the dual-list widget."""
    if request.method != "POST":
        return JsonResponse({"res": []})

    try:
        context = get_event_context(request, event_slug)
    except (Http404, PermissionDenied, UserPermissionError, FeatureError):
        return JsonResponse({"res": []}, status=403)

    term = request.POST.get("term", "").strip()
    exclude_raw = request.POST.get("exclude", "")
    exclude_uuids = [u.strip() for u in exclude_raw.split(",") if u.strip()]

    qs = context["event"].get_elements(Character).only("id", "uuid", "name", "number")

    if term:
        qs = qs.filter(
            Q(number__icontains=term) | Q(name__icontains=term) | Q(teaser__icontains=term) | Q(title__icontains=term)
        )

    if exclude_uuids:
        qs = qs.exclude(uuid__in=exclude_uuids)

    show_number = get_event_config(context["event"].id, "writing_number", default_value=False, context=context)

    qs = qs.order_by("name")[:25]
    res = [(str(ch.uuid), f"#{ch.number} {ch.name}" if show_number else ch.name, ch.pk) for ch in qs]
    return JsonResponse({"res": res})


@login_required
def orga_exp_available(request: HttpRequest, event_slug: str) -> JsonResponse | Http404:
    """Return available abilities or deliveries for multichoice popups via AJAX."""
    if request.method != "POST":
        return Http404()

    context = get_event_context(request, event_slug)
    kind = request.POST.get("type", "ability")
    filter_context = request.POST.get("filter_context", "")
    edit_uuid = request.POST.get("edit_uuid", "")

    if kind == "delivery":
        queryset = context["event"].get_elements(DeliveryExp).order_by("number")
        if filter_context == "character" and edit_uuid:
            try:
                character = context["event"].get_elements(Character).get(uuid=edit_uuid)
                taken = character.exp_delivery_list.values_list("id", flat=True)
                queryset = queryset.exclude(pk__in=taken)
            except ObjectDoesNotExist:
                return JsonResponse({"res": "ko"})
    else:
        queryset = context["event"].get_elements(AbilityExp).order_by("number")
        if filter_context == "character" and edit_uuid:
            try:
                character = context["event"].get_elements(Character).get(uuid=edit_uuid)
                taken = character.exp_ability_list.values_list("id", flat=True)
                queryset = queryset.exclude(pk__in=taken)
            except ObjectDoesNotExist:
                return JsonResponse({"res": "ko"})
        elif filter_context == "ability" and edit_uuid:
            with contextlib.suppress(ObjectDoesNotExist):
                ability = context["event"].get_elements(AbilityExp).get(uuid=edit_uuid)
                queryset = queryset.exclude(pk=ability.pk)

    res = [(str(el.uuid), str(el)) for el in queryset]
    return JsonResponse({"res": res})
