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
from __future__ import annotations

from enum import Enum
from typing import Any

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect

from larpmanager.forms.accounting import (
    OrgaCreditForm,
    OrgaDiscountForm,
    OrgaExpenseForm,
    OrgaInflowForm,
    OrgaOutflowForm,
    OrgaPaymentForm,
    OrgaTokenForm,
)
from larpmanager.forms.character import OrgaCharacterForm, OrgaWritingOptionForm
from larpmanager.forms.event import OrgaEventButtonForm, OrgaEventRoleForm, OrgaEventTextForm, OrgaProgressStepForm
from larpmanager.forms.experience import (
    OrgaAbilityPxForm,
    OrgaAbilityTemplatePxForm,
    OrgaAbilityTypePxForm,
    OrgaDeliveryPxForm,
    OrgaModifierPxForm,
    OrgaRulePxForm,
)
from larpmanager.forms.inventory import OrgaInventoryForm, OrgaPoolTypePxForm
from larpmanager.forms.miscellanea import (
    OneTimeAccessTokenForm,
    OneTimeContentForm,
    OrgaAlbumForm,
    OrgaProblemForm,
    UtilForm,
    WorkshopModuleForm,
    WorkshopOptionForm,
    WorkshopQuestionForm,
)
from larpmanager.forms.registration import (
    OrgaRegistrationOptionForm,
    OrgaRegistrationQuotaForm,
    OrgaRegistrationSectionForm,
    OrgaRegistrationTicketForm,
)
from larpmanager.forms.warehouse import OrgaWarehouseAreaForm
from larpmanager.forms.writing import (
    OrgaFactionForm,
    OrgaHandoutForm,
    OrgaHandoutTemplateForm,
    OrgaPlotForm,
    OrgaPrologueForm,
    OrgaPrologueTypeForm,
    OrgaQuestForm,
    OrgaQuestTypeForm,
    OrgaSpeedLarpForm,
    OrgaTraitForm,
)
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.core.common import exchange_order
from larpmanager.utils.services.edit import backend_delete

# "form": form used for creation / editing
# "can_delete": callback used to check if the element can be deleted
# "redirect_view": view to redirect, if different than permission

alls = {
    "orga_roles": {"form": OrgaEventRoleForm, "can_delete": lambda _context, element: element.number != 1},
    "orga_characters": {"form": OrgaCharacterForm},
    "orga_character_form": {
        "form": OrgaWritingOptionForm,
        "can_delete": lambda _context, element: len(element.typ) == 1,
    },
    "orga_plots": {"form": OrgaPlotForm},
    "orga_factions": {"form": OrgaFactionForm},
    "orga_quest_types": {"form": OrgaQuestTypeForm},
    "orga_quests": {"form": OrgaQuestForm},
    "orga_traits": {"form": OrgaTraitForm},
    "orga_handouts": {"form": OrgaHandoutForm},
    "orga_handout_templates": {"form": OrgaHandoutTemplateForm},
    "orga_prologue_types": {"form": OrgaPrologueTypeForm},
    "orga_prologues": {"form": OrgaPrologueForm},
    "orga_speedlarps": {"form": OrgaSpeedLarpForm},
    "orga_texts": {"form": OrgaEventTextForm},
    "orga_buttons": {"form": OrgaEventButtonForm},
    "orga_registration_tickets": {"form": OrgaRegistrationTicketForm},
    "orga_registration_sections": {"form": OrgaRegistrationSectionForm},
    "orga_registration_form": {
        "form": OrgaRegistrationOptionForm,
        "can_delete": lambda _context, element: len(element.typ) == 1,
    },
    "orga_registration_quotas": {"form": OrgaRegistrationQuotaForm},
    "orga_px_deliveries": {"form": OrgaDeliveryPxForm},
    "orga_px_abilities": {"form": OrgaAbilityPxForm},
    "orga_px_ability_types": {"form": OrgaAbilityTypePxForm},
    "orga_px_ability_templates": {"form": OrgaAbilityTemplatePxForm},
    "orga_px_rules": {"form": OrgaRulePxForm},
    "orga_px_modifiers": {"form": OrgaModifierPxForm},
    "orga_ci_inventory": {"form": OrgaInventoryForm},
    "orga_ci_pool_types": {"form": OrgaPoolTypePxForm},
    "orga_albums": {"form": OrgaAlbumForm},
    "orga_utils": {"form": UtilForm},
    "orga_workshop_modules": {"form": WorkshopModuleForm},
    "orga_workshop_questions": {"form": WorkshopQuestionForm},
    "orga_workshop_options": {"form": WorkshopOptionForm},
    "orga_problems": {"form": OrgaProblemForm},
    "orga_warehouse_area": {"form": OrgaWarehouseAreaForm},
    "orga_onetimes": {"form": OneTimeContentForm},
    "orga_onetimes_tokens": {"form": OneTimeAccessTokenForm},
    "orga_discounts": {"form": OrgaDiscountForm},
    "orga_tokens": {"form": OrgaTokenForm},
    "orga_credits": {"form": OrgaCreditForm},
    "orga_payments": {"form": OrgaPaymentForm},
    "orga_outflows": {"form": OrgaOutflowForm},
    "orga_inflows": {"form": OrgaInflowForm},
    "orga_expenses": {"form": OrgaExpenseForm},
    "orga_progress_steps": {"form": OrgaProgressStepForm},
}


class Action(Enum):
    """Action to be executed upon element."""

    NEW = "new"
    EDIT = "edit"
    DELETE = "delete"
    VIEW = "view"
    VERSIONS = "versions"
    ORDER = "order"


def unified_orga(
    request: HttpRequest,
    event_slug: str,
    permission: str,
    action: Action,
    element_uuid: str | None = None,
    additional: Any = None,
) -> HttpResponse:
    """Unified entry for operation on elements."""
    if permission not in alls:
        msg = "permission unknown"
        raise Http404(msg)

    action_data = alls[permission]
    form_type = action_data.get("form")

    # Verify user has permission to modify progress steps
    context = check_event_context(request, event_slug, permission)

    model_type = form_type.Meta.model

    if action == Action.ORDER:
        exchange_order(context, model_type, element_uuid, additional)

    if action == Action.DELETE:
        backend_delete(request, context, form_type, element_uuid, action_data.get("can_delete"))

    redirect_view = action_data.get("redirect_view")
    if not redirect_view:
        redirect_view = permission

    # Redirect to success page with event slug
    return redirect(redirect_view, event_slug=context["run"].get_slug())
