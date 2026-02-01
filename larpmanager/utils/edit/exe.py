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

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect

from larpmanager.forms.accounting import (
    ExeCollectionForm,
    ExeCreditForm,
    ExeDonationForm,
    ExeExpenseForm,
    ExeInflowForm,
    ExeInvoiceForm,
    ExeOutflowForm,
    ExePaymentForm,
    ExeRefundRequestForm,
    ExeTokenForm,
)
from larpmanager.forms.association import ExeAssociationRoleForm, ExeAssociationTextForm, ExeAssociationTranslationForm
from larpmanager.forms.event import (
    ExeTemplateForm,
)
from larpmanager.forms.member import ExeBadgeForm, ExeVolunteerRegistryForm
from larpmanager.forms.miscellanea import (
    ExeUrlShortnerForm,
)
from larpmanager.forms.warehouse import (
    ExeWarehouseContainerForm,
    ExeWarehouseItemForm,
    ExeWarehouseMovementForm,
    ExeWarehouseTagForm,
)
from larpmanager.utils.core.base import check_association_context
from larpmanager.utils.edit.backend import backend_delete
from larpmanager.utils.edit.base import Action

# "form": form used for creation / editing
# "can_delete": callback used to check if the element can be deleted
# "redirect_view": view to redirect, if different than permission

alls = {
    "exe_roles": {"form": ExeAssociationRoleForm, "can_delete": lambda _context, element: element.number != 1},
    "exe_texts": {"form": ExeAssociationTextForm},
    "exe_translations": {"form": ExeAssociationTranslationForm},
    "exe_volunteer_registry": {"form": ExeVolunteerRegistryForm},
    "exe_badges": {"form": ExeBadgeForm},
    "exe_templates": {"form": ExeTemplateForm},
    "exe_urlshortner": {"form": ExeUrlShortnerForm},
    "exe_warehouse_containers": {"form": ExeWarehouseContainerForm},
    "exe_warehouse_tags": {"form": ExeWarehouseTagForm},
    "exe_warehouse_items": {"form": ExeWarehouseItemForm},
    "exe_warehouse_movements": {"form": ExeWarehouseMovementForm},
    "exe_outflows": {"form": ExeOutflowForm},
    "exe_inflows": {"form": ExeInflowForm},
    "exe_donations": {"form": ExeDonationForm},
    "exe_credits": {"form": ExeCreditForm},
    "exe_tokens": {"form": ExeTokenForm},
    "exe_expenses": {"form": ExeExpenseForm},
    "exe_payments": {"form": ExePaymentForm},
    "exe_invoices": {"form": ExeInvoiceForm},
    "exe_collections": {"form": ExeCollectionForm},
    "exe_refunds": {"form": ExeRefundRequestForm},
}


def _exe_actions(
    request: HttpRequest,
    permission: str,
    action: Action,
    element_uuid: str | None = None,
) -> HttpResponse:
    """Unified entry for operation on exe elements."""
    if permission not in alls:
        msg = "permission unknown"
        raise Http404(msg)

    action_data = alls[permission]
    form_type = action_data.get("form")

    # Verify user has permission
    context = check_association_context(request, permission)

    if action == Action.DELETE:
        backend_delete(request, context, form_type, element_uuid, action_data.get("can_delete"))

    redirect_view = action_data.get("redirect_view")
    if not redirect_view:
        redirect_view = permission

    # Redirect to success page
    return redirect(redirect_view)


def exe_delete(
    request: HttpRequest,
    permission: str,
    element_uuid: str,
) -> HttpResponse:
    """Delete organization-level entities through a unified interface."""
    return _exe_actions(request, permission, Action.DELETE, element_uuid)
