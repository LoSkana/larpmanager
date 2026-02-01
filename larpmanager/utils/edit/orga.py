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

from typing import Any

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.accounting import (
    OrgaCreditForm,
    OrgaDiscountForm,
    OrgaExpenseForm,
    OrgaInflowForm,
    OrgaOutflowForm,
    OrgaPaymentForm,
    OrgaTokenForm,
)
from larpmanager.forms.character import OrgaCharacterForm, OrgaWritingOptionForm, OrgaWritingQuestionForm
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
    OrgaRegistrationQuestionForm,
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
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    RegistrationOption,
    RegistrationQuestion,
    WritingOption,
    WritingQuestion,
    _get_writing_mapping,
)
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.core.common import exchange_order, get_element
from larpmanager.utils.edit.backend import backend_delete, backend_edit, set_suggestion
from larpmanager.utils.edit.base import Action

# "form": form used for creation / editing
# "can_delete": callback used to check if the element can be deleted
# "redirect_view": view to redirect, if different than permission

alls = {
    "orga_roles": {"form": OrgaEventRoleForm, "can_delete": lambda _context, element: element.number != 1},
    "orga_characters": {"form": OrgaCharacterForm},
    "orga_character_form": {
        "form": OrgaWritingQuestionForm,
        "can_delete": lambda _context, element: len(element.typ) == 1,
    },
    "orga_character_form_option": {
        "form": OrgaWritingOptionForm,
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
        "form": OrgaRegistrationQuestionForm,
        "can_delete": lambda _context, element: len(element.typ) == 1,
    },
    "orga_registration_form_option": {
        "form": OrgaRegistrationOptionForm,
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


def _orga_actions(
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
    if permission.endswith("form_option"):
        permission = permission.replace("form_option", "form")
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


def orga_delete(request: HttpRequest, event_slug: str, permission: str, element_uuid: str) -> HttpResponse:
    """Delete an element from an orga view."""
    return _orga_actions(request, event_slug, permission, Action.DELETE, element_uuid)


def orga_order(
    request: HttpRequest,
    event_slug: str,
    permission: str,
    element_uuid: str,
    additional: int,
) -> HttpResponse:
    """Order an element from an orga view."""
    return _orga_actions(request, event_slug, permission, Action.ORDER, element_uuid, additional)


def form_edit_handler(
    request: HttpRequest,
    event_slug: str,
    permission: str,
    question_uuid: str | None,
    extra_context: dict | None = None,
) -> HttpResponse:
    """Generic handler for question form editing (registration and writing).

    Args:
        request: HTTP request object
        event_slug: Event slug
        permission: Permission type
        question_uuid: Question UUID to edit (None for new questions)
        extra_context: Extra context arguments

    Returns:
        HttpResponse: Rendered template or redirect
    """
    context = check_event_context(request, event_slug, permission)

    option_model = RegistrationOption
    form_class = OrgaRegistrationQuestionForm
    redirect_view_name = "orga_registration_form_edit"
    redirect_list_view_name = "orga_registration_form"
    template_name = "larpmanager/orga/registration/form_edit.html"

    if permission == "orga_character_form":
        option_model = WritingOption
        form_class = OrgaWritingQuestionForm
        redirect_view_name = "orga_writing_form_edit"
        redirect_list_view_name = "orga_writing_form"
        template_name = "larpmanager/orga/characters/form_edit.html"

    writing_type = extra_context.get("writing_type") if extra_context else None
    if writing_type:
        # Validate the writing form type exists and is allowed
        check_writing_form_type(context, writing_type)

    # Check if this is an AJAX request
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    # Process form submission using backend edit utility
    if backend_edit(request, context, form_class, question_uuid, quiet=True):
        # Set permission suggestion for future operations
        set_suggestion(context, permission)

        # If item was deleted, redirect to list view
        if request.POST.get("delete") == "1":
            messages.success(request, _("Operation completed") + "!")
            redirect_kwargs = {"event_slug": context["run"].get_slug(), **(extra_context or {})}
            return redirect(redirect_list_view_name, **redirect_kwargs)

        # If AJAX request, return JSON with question UUID
        if is_ajax:
            return JsonResponse(
                {
                    "success": True,
                    "question_uuid": str(context["saved"].uuid),
                    "message": str(_("Question saved successfully")),
                }
            )

        # Handle "continue editing" button - redirect to new question form
        if "continue" in request.POST:
            messages.success(request, _("Operation completed") + "!")
            if extra_context:  # writing form
                redirect_kwargs = {
                    "event_slug": context["run"].get_slug(),
                    **extra_context,
                }
            else:  # registration form
                redirect_kwargs = {"event_slug": context["run"].get_slug()}
            return redirect(redirect_view_name.replace("_edit", "_new"), **redirect_kwargs)

        # Check if question is single/multiple choice and needs options
        is_choice = context["saved"].typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]
        if is_choice and not option_model.objects.filter(question_id=context["saved"].id).exists():
            messages.warning(
                request,
                _("You must define at least one option before saving a single-choice or multiple-choice question"),
            )

            # Redirect to question page
            redirect_kwargs = {
                "event_slug": context["run"].get_slug(),
                "question_uuid": context["saved"].uuid,
                **(extra_context or {}),
            }
            return redirect(redirect_view_name, **redirect_kwargs)

        messages.success(request, _("Operation completed") + "!")
        redirect_kwargs = {"event_slug": context["run"].get_slug(), **(extra_context or {})}
        return redirect(redirect_list_view_name, **redirect_kwargs)

    return render(request, template_name, context)


def options_edit_handler(
    request: HttpRequest,
    event_slug: str,
    permission: str,
    option_uuid: str | None,
    extra_context: dict | None = None,
) -> HttpResponse:
    """Handler for option form submission (iframe mode).

    Args:
        request: HTTP request object
        event_slug: Event slug
        permission: Permission type
        option_uuid: Option UUID to edit (0 for new options)
        extra_context: Additional context to add to form_context (e.g., {"typ": writing_type})

    Returns:
        HttpResponse with form page (iframe mode)
    """
    context = check_event_context(request, event_slug, permission)
    context["frame"] = 1

    question_model = RegistrationQuestion
    option_model = RegistrationOption
    form_class = OrgaRegistrationOptionForm
    if permission == "orga_character_form":
        question_model = WritingQuestion
        option_model = WritingOption
        form_class = OrgaWritingOptionForm

    writing_type = extra_context.get("writing_type") if extra_context else None
    if writing_type:
        # Validate the writing form type exists and is allowed
        check_writing_form_type(context, writing_type)

    # For new options, get the question_uuid from request
    if not option_uuid:
        question_uuid = request.GET.get("question_uuid") or request.POST.get("question_uuid")
        if question_uuid:
            get_element(context, question_uuid, "question", question_model)
    else:
        # For editing existing option, load the option instance
        get_element(context, option_uuid, "el", option_model)
        context["question"] = context["el"].question

    # Try saving it
    if backend_edit(request, context, form_class, option_uuid):
        return render(request, "elements/options/form_success.html", context)

    # If form validation failed, return form with errors
    form_context = {
        **context,
        "num": option_uuid,
        **(extra_context or {}),
    }

    return render(request, "elements/options/form_frame.html", form_context)


def check_writing_form_type(context: dict, form_type: str) -> None:
    """Validate writing form type and update context with type information.

    Args:
        context: Context dictionary to update with type information
        form_type: Writing form type to validate

    Raises:
        Http404: If the writing form type is not available

    """
    form_type = form_type.lower()
    writing_type_mapping = _get_writing_mapping()

    # Build available types from choices that have corresponding features
    available_types = {
        value: key for key, value in QuestionApplicable.choices if writing_type_mapping[value] in context["features"]
    }

    # Validate the requested type is available
    if form_type not in available_types:
        msg = f"unknown writing form type: {form_type}"
        raise Http404(msg)

    # Update context with type information
    context["typ"] = form_type
    context["writing_typ"] = available_types[form_type]
    context["label_typ"] = form_type.capitalize()
    context["available_typ"] = {key.capitalize(): value for key, value in available_types.items()}
