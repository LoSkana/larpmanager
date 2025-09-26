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
from django.http import JsonResponse
from django.shortcuts import redirect, render

from larpmanager.forms.experience import OrgaAbilityPxForm, OrgaAbilityTypePxForm, OrgaDeliveryPxForm, OrgaRulePxForm, \
    OrgaAbilityTemplatePxForm
from larpmanager.models.experience import AbilityPx, AbilityTypePx, DeliveryPx, RulePx, AbilityTemplatePx
from larpmanager.utils.common import exchange_order
from larpmanager.utils.edit import orga_edit
from larpmanager.utils.event import check_event_permission


@login_required
def orga_px_deliveries(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_px_deliveries")
    ctx["list"] = ctx["event"].get_elements(DeliveryPx).order_by("number")
    return render(request, "larpmanager/orga/px/deliveries.html", ctx)


@login_required
def orga_px_deliveries_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_px_deliveries", OrgaDeliveryPxForm, num)


@login_required
def orga_px_abilities(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_px_abilities")
    ctx["px_user"] = ctx["event"].get_config("px_user", False)
    ctx["list"] = ctx["event"].get_elements(AbilityPx).order_by("number")
    return render(request, "larpmanager/orga/px/abilities.html", ctx)


@login_required
def orga_px_abilities_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_px_abilities", OrgaAbilityPxForm, num)


@login_required
def orga_px_ability_types(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_px_ability_types")
    ctx["list"] = ctx["event"].get_elements(AbilityTypePx).order_by("number")
    return render(request, "larpmanager/orga/px/ability_types.html", ctx)


@login_required
def orga_px_ability_types_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_px_ability_types", OrgaAbilityTypePxForm, num)


@login_required
def orga_px_ability_templates(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_px_ability_templates")
    ctx["list"] = ctx["event"].get_elements(AbilityTemplatePx).order_by("number")
    return render(request, "larpmanager/orga/px/ability_templates.html", ctx)


@login_required
def orga_px_ability_templates_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_px_ability_templates", OrgaAbilityTemplatePxForm, num)


@login_required
def orga_px_rules(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_px_rules")
    ctx["list"] = ctx["event"].get_elements(RulePx).order_by("order")
    return render(request, "larpmanager/orga/px/rules.html", ctx)


@login_required
def orga_px_rules_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_px_rules", OrgaRulePxForm, num)


@login_required
def orga_px_rules_order(request, s, n, num, order):
    ctx = check_event_permission(request, s, n, "orga_px_rules")
    exchange_order(ctx, RulePx, num, order)
    return redirect("orga_px_rules", s=ctx["event"].slug, n=ctx["run"].number)

@login_required
def orga_api_px_abilities(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_px_abilities")
    ctx["px_user"] = ctx["event"].get_config("px_user", False)
    ctx["list"] = ctx["event"].get_elements(AbilityPx).order_by("number")

    parsed_abilities = []
    for ability in ctx["list"]:
        if ability.template == None:
            ability_template = {}
        else:
            ability_template = {"id": ability.template.pk, "name": ability.template.name}
        parsed_abilities.append({"id": ability.pk, "name": ability.name, "type": {"id": ability.typ.pk, "name": ability.typ.name}, "template": ability_template})
    return JsonResponse(parsed_abilities, safe=False)
