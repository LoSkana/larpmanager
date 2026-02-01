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

from typing import TYPE_CHECKING

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from larpmanager.forms.accounting import (
    ExeCollectionForm,
    ExeCreditForm,
    ExeDonationForm,
    ExeExpenseForm,
    ExeInflowForm,
    ExeInvoiceForm,
    ExeOutflowForm,
    ExePaymentForm,
    ExePaymentSettingsForm,
    ExeRefundRequestForm,
    ExeTokenForm,
)
from larpmanager.forms.association import (
    ExeAppearanceForm,
    ExeAssociationForm,
    ExeAssociationRoleForm,
    ExeAssociationTextForm,
    ExeAssociationTranslationForm,
    ExeConfigForm,
    ExePreferencesForm,
    ExeQuickSetupForm,
)
from larpmanager.forms.event import (
    ExeTemplateForm,
    OrgaRunForm,
)
from larpmanager.forms.member import ExeBadgeForm, ExeProfileForm, ExeVolunteerRegistryForm
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
from larpmanager.utils.edit.backend import backend_delete, backend_edit, set_suggestion
from larpmanager.utils.edit.base import Action

if TYPE_CHECKING:
    from larpmanager.forms.base import BaseModelForm

# "form": form used for creation / editing
# "can_delete": callback used to check if the element can be deleted
# "redirect_view": view to redirect, if different than permission

alls = {
    "": {"form": ExePreferencesForm, "member_form": True},
    "exe_events": {"form": OrgaRunForm, "additional_field": "event"},
    "exe_methods": {"form": ExePaymentSettingsForm, "assoc_form": True},
    "exe_association": {"form": ExeAssociationForm, "assoc_form": True},
    "exe_config": {"form": ExeConfigForm, "assoc_form": True},
    "exe_profile": {"form": ExeProfileForm, "assoc_form": True},
    "exe_quick": {"form": ExeQuickSetupForm, "assoc_form": True},
    "exe_appearance": {"form": ExeAppearanceForm, "assoc_form": True},
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
    """Unified entry point for all operations on organization-wide (executive) elements.

    Routes CRUD operations (create, edit, delete) to appropriate handlers based on the
    action type. Validates permissions and delegates form processing to the exe_form helper.
    Handles special form types (association, member, event) with appropriate redirects.

    Args:
        request: HTTP request object
        permission: Permission string that maps to an entry in 'alls' dictionary
        action: Action type (EDIT, NEW, or DELETE)
        element_uuid: UUID of element to operate on (None for new elements)

    Returns:
        HttpResponse: Redirect to success page or result from exe_form handler

    Raises:
        Http404: If permission is not found in 'alls' dictionary
    """
    if permission not in alls:
        msg = "permission unknown"
        raise Http404(msg)

    action_data = alls[permission]
    form_type = action_data.get("form")
    model_type = form_type.Meta.model

    # Verify user has permission
    context = check_association_context(request, permission)

    # Perform DELETE
    if action == Action.DELETE:
        backend_delete(request, context, model_type, element_uuid, action_data.get("can_delete"))
        return redirect(permission)

    # Perform NEW and EDIT
    redirect_view = None

    if action_data.get("assoc_form"):
        context["add_another"] = False
        context["assoc_form"] = True
        redirect_view = "manage"

    if action_data.get("member_form"):
        context["add_another"] = False
        context["member_form"] = True
        redirect_view = "manage"

    # Extract section parameter from URL if present (for jump_section in forms)
    if hasattr(request, "resolver_match") and request.resolver_match:
        section = request.resolver_match.kwargs.get("section")
        if section:
            context["jump_section"] = section

    return exe_form(request, context, permission, action_data, form_type, element_uuid, redirect_view)


def exe_form(
    request: HttpRequest,
    context: dict,
    permission: str,
    action_data: dict,
    form_type: type[BaseModelForm],
    element_uuid: str | None = None,
    redirect_view: str | None = None,
) -> HttpResponse:
    """Process form submissions for creating or editing organization-wide elements.

    Handles both standard and iframe rendering modes. Processes form submissions through
    the backend_edit handler and manages success/failure responses including redirects,
    template rendering, and "continue editing" workflow.

    Args:
        request: HTTP request object
        context: Context dictionary with association and permission data
        permission: Permission string identifying the action type
        action_data: Dictionary from 'alls' containing form metadata (e.g., additional_field)
        form_type: Form class to use for validation and saving
        element_uuid: UUID of element to edit (None for new elements)
        redirect_view: Optional view name to redirect to on success (defaults to permission)

    Returns:
        HttpResponse: Rendered template (standard or iframe) or redirect response
    """
    # Check if this is an iframe request
    is_frame = request.GET.get("frame") == "1" or request.POST.get("frame") == "1"

    context["exe"] = True

    additional_field = action_data.get("additional_field")

    # Process the edit operation through backend handler
    if backend_edit(request, context, form_type, element_uuid, additional_field=additional_field):
        # Set permission suggestion for UI feedback
        set_suggestion(context, permission)

        # Return success template for iframe mode
        if is_frame:
            return render(request, "elements/dashboard/form_success.html", context)

        # Handle "continue editing" workflow
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name.replace("_edit", "_new"))

        # Determine redirect target and perform redirect
        if not redirect_view:
            redirect_view = permission
        return redirect(redirect_view)

    # Render appropriate template based on mode
    if is_frame:
        return render(request, "elements/dashboard/form_frame.html", context)

    return render(request, "larpmanager/exe/edit.html", context)


def exe_new(request: HttpRequest, permission: str) -> HttpResponse:
    """Create organization-level entities through a unified interface."""
    return _exe_actions(request, permission, Action.NEW)


def exe_edit(
    request: HttpRequest,
    permission: str,
    element_uuid: str | None = None,
) -> HttpResponse:
    """Edit organization-level entities through a unified interface."""
    return _exe_actions(request, permission, Action.EDIT, element_uuid)


def exe_delete(
    request: HttpRequest,
    permission: str,
    element_uuid: str,
) -> HttpResponse:
    """Delete organization-level entities through a unified interface."""
    return _exe_actions(request, permission, Action.DELETE, element_uuid)
