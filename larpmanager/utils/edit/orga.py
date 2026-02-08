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

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_all, get_writing_element_fields, reset_event_cache_all
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
from larpmanager.forms.event import (
    OrgaAppearanceForm,
    OrgaConfigForm,
    OrgaEventButtonForm,
    OrgaEventRoleForm,
    OrgaEventTextForm,
    OrgaPreferencesForm,
    OrgaProgressStepForm,
    OrgaQuickSetupForm,
    OrgaRunForm,
)
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
    OrgaRegistrationInstallmentForm,
    OrgaRegistrationOptionForm,
    OrgaRegistrationQuestionForm,
    OrgaRegistrationQuotaForm,
    OrgaRegistrationSectionForm,
    OrgaRegistrationSurchargeForm,
    OrgaRegistrationTicketForm,
)
from larpmanager.forms.warehouse import OrgaWarehouseAreaForm, OrgaWarehouseItemAssignmentForm
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
from larpmanager.models.casting import Quest, QuestType
from larpmanager.models.experience import AbilityTypePx
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    RegistrationOption,
    RegistrationQuestion,
    WritingOption,
    WritingQuestion,
    _get_writing_mapping,
)
from larpmanager.models.writing import HandoutTemplate, PlotCharacterRel, PrologueType, TextVersion, TextVersionChoices
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.core.common import compute_diff, get_element
from larpmanager.utils.core.exceptions import RedirectError
from larpmanager.utils.edit.backend import (
    backend_delete,
    backend_edit,
    backend_get,
    backend_order,
    set_suggestion,
)
from larpmanager.utils.edit.base import Action, prepare_change
from larpmanager.utils.services.character import get_character_relationships, get_character_sheet


def validate_ability_px(request: HttpRequest, context: dict, event_slug: str) -> None:
    """Validate that ability types exist before allowing ability creation."""
    if not context["event"].get_elements(AbilityTypePx).exists():
        # Warn user and redirect to ability types creation page
        messages.warning(request, _("You must create at least one ability type before you can create abilities"))
        msg = "orga_px_ability_types_new"
        raise RedirectError(msg, args=[event_slug])


def validate_quest(request: HttpRequest, context: dict, event_slug: str) -> None:
    """Verify that quest types are available before allowing quest creation."""
    if not context["event"].get_elements(QuestType).exists():
        # Add warning message and redirect to quest types adding page
        messages.warning(request, _("You must create at least one quest type before you can create quests"))
        msg = "orga_quest_types_new"
        raise RedirectError(msg, args=[event_slug])


def validate_trait(request: HttpRequest, context: dict, event_slug: str) -> None:
    """Validate prerequisite: at least one quest must exist."""
    if not context["event"].get_elements(Quest).exists():
        # Add warning message and redirect to quests adding page
        messages.warning(request, _("You must create at least one quest before you can create traits"))
        msg = "orga_quests_new"
        raise RedirectError(msg, args=[event_slug])


def validate_handout(request: HttpRequest, context: dict, event_slug: str) -> None:
    """Validate handout templates exist before allowing handout creation."""
    if not context["event"].get_elements(HandoutTemplate).exists():
        # Display warning and redirect to template creation page
        messages.warning(request, _("You must create at least one handout template before you can create handouts"))
        msg = "orga_handout_templates_new"
        raise RedirectError(msg, args=[event_slug])


def validate_prologue(request: HttpRequest, context: dict, event_slug: str) -> None:
    """Validate prologue type exist before allowing prologue creation."""
    if not context["event"].get_elements(PrologueType).exists():
        # Display warning and redirect to template creation page
        messages.warning(request, _("You must create at least one prologue type before you can create prologues"))
        msg = "orga_prologue_types_new"
        raise RedirectError(msg, args=[event_slug])


class OrgaAction(str, Enum):
    """Enum for organization action types used in edit/create/delete operations."""

    def __new__(cls, value: str, config: dict[str, Any]) -> Any:
        """Create a new enum member with value and config."""
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.config = config
        return obj

    @classmethod
    def from_string(cls, permission: str) -> OrgaAction | None:
        """Look up an OrgaAction by its permission string value."""
        for member in cls:
            if member.value == permission:
                return member
        return None

    # Event configuration
    PREFERENCES = ("", {"form": OrgaPreferencesForm, "member_form": True})
    EVENT = ("orga_event", {"form": OrgaRunForm, "event_form": True})
    CONFIG = ("orga_config", {"form": OrgaConfigForm, "event_form": True})
    QUICK = ("orga_quick", {"form": OrgaQuickSetupForm, "event_form": True})
    APPEARANCE = ("orga_appearance", {"form": OrgaAppearanceForm, "event_form": True})
    ROLES = ("orga_roles", {"form": OrgaEventRoleForm, "can_delete": lambda _context, element: element.number != 1})
    TEXTS = ("orga_texts", {"form": OrgaEventTextForm})
    BUTTONS = ("orga_buttons", {"form": OrgaEventButtonForm})

    # Characters and writing forms
    CHARACTERS = ("orga_characters", {"form": OrgaCharacterForm, "writing": TextVersionChoices.CHARACTER})
    CHARACTER_FORM = (
        "orga_character_form",
        {"form": OrgaWritingQuestionForm, "can_delete": lambda _context, element: len(element.typ) == 1},
    )
    CHARACTER_FORM_OPTION = ("orga_character_form_option", {"form": OrgaWritingOptionForm})

    # Writing elements
    PLOTS = ("orga_plots", {"form": OrgaPlotForm, "writing": TextVersionChoices.PLOT})
    FACTIONS = ("orga_factions", {"form": OrgaFactionForm, "writing": TextVersionChoices.FACTION})
    QUEST_TYPES = ("orga_quest_types", {"form": OrgaQuestTypeForm, "writing": TextVersionChoices.QUEST_TYPE})
    QUESTS = ("orga_quests", {"form": OrgaQuestForm, "writing": TextVersionChoices.QUEST, "check": validate_quest})
    TRAITS = ("orga_traits", {"form": OrgaTraitForm, "writing": TextVersionChoices.TRAIT, "check": validate_trait})
    HANDOUTS = ("orga_handouts", {"form": OrgaHandoutForm, "writing": TextVersionChoices.HANDOUT})
    HANDOUT_TEMPLATES = ("orga_handout_templates", {"form": OrgaHandoutTemplateForm, "check": validate_handout})
    PROLOGUE_TYPES = ("orga_prologue_types", {"form": OrgaPrologueTypeForm})
    PROLOGUES = (
        "orga_prologues",
        {"form": OrgaPrologueForm, "writing": TextVersionChoices.PROLOGUE, "check": validate_prologue},
    )
    SPEEDLARPS = ("orga_speedlarps", {"form": OrgaSpeedLarpForm, "writing": TextVersionChoices.SPEEDLARP})
    PROGRESS_STEPS = ("orga_progress_steps", {"form": OrgaProgressStepForm})

    # Registration
    REGISTRATION_TICKETS = ("orga_registration_tickets", {"form": OrgaRegistrationTicketForm})
    REGISTRATION_SECTIONS = ("orga_registration_sections", {"form": OrgaRegistrationSectionForm})
    REGISTRATION_FORM = (
        "orga_registration_form",
        {"form": OrgaRegistrationQuestionForm, "can_delete": lambda _context, element: len(element.typ) == 1},
    )
    REGISTRATION_FORM_OPTION = ("orga_registration_form_option", {"form": OrgaRegistrationOptionForm})
    REGISTRATION_QUOTAS = ("orga_registration_quotas", {"form": OrgaRegistrationQuotaForm})
    REGISTRATION_INSTALLMENTS = ("orga_registration_installments", {"form": OrgaRegistrationInstallmentForm})
    REGISTRATION_SURCHARGES = ("orga_registration_surcharges", {"form": OrgaRegistrationSurchargeForm})

    # Experience/PX system
    PX_DELIVERIES = ("orga_px_deliveries", {"form": OrgaDeliveryPxForm})
    PX_ABILITIES = ("orga_px_abilities", {"form": OrgaAbilityPxForm, "check": validate_ability_px})
    PX_ABILITY_TYPES = ("orga_px_ability_types", {"form": OrgaAbilityTypePxForm})
    PX_ABILITY_TEMPLATES = ("orga_px_ability_templates", {"form": OrgaAbilityTemplatePxForm})
    PX_RULES = ("orga_px_rules", {"form": OrgaRulePxForm})
    PX_MODIFIERS = ("orga_px_modifiers", {"form": OrgaModifierPxForm})

    # Inventory
    CI_INVENTORY = ("orga_ci_inventory", {"form": OrgaInventoryForm})
    CI_POOL_TYPES = ("orga_ci_pool_types", {"form": OrgaPoolTypePxForm})

    # Miscellaneous
    ALBUMS = ("orga_albums", {"form": OrgaAlbumForm})
    UTILS = ("orga_utils", {"form": UtilForm})
    WORKSHOP_MODULES = ("orga_workshop_modules", {"form": WorkshopModuleForm})
    WORKSHOP_QUESTIONS = ("orga_workshop_questions", {"form": WorkshopQuestionForm})
    WORKSHOP_OPTIONS = ("orga_workshop_options", {"form": WorkshopOptionForm})
    PROBLEMS = ("orga_problems", {"form": OrgaProblemForm})

    # Warehouse
    WAREHOUSE_AREA = ("orga_warehouse_area", {"form": OrgaWarehouseAreaForm})
    WAREHOUSE_MANIFEST = ("orga_warehouse_manifest", {"form": OrgaWarehouseItemAssignmentForm})
    WAREHOUSE_ASSIGNMENT_ITEM = ("orga_warehouse_assignment_item", {})

    # One-time content
    ONETIMES = ("orga_onetimes", {"form": OneTimeContentForm})
    ONETIMES_TOKENS = ("orga_onetimes_tokens", {"form": OneTimeAccessTokenForm})

    # Accounting
    DISCOUNTS = ("orga_discounts", {"form": OrgaDiscountForm})
    TOKENS = ("orga_tokens", {"form": OrgaTokenForm})
    CREDITS = ("orga_credits", {"form": OrgaCreditForm})
    PAYMENTS = ("orga_payments", {"form": OrgaPaymentForm})
    OUTFLOWS = ("orga_outflows", {"form": OrgaOutflowForm})
    INFLOWS = ("orga_inflows", {"form": OrgaInflowForm})
    EXPENSES = ("orga_expenses", {"form": OrgaExpenseForm})


def _action_change(
    request: HttpRequest,
    context: dict,
    event_slug: str,
    permission: str,
    action_data: dict,
    element_uuid: str | None = None,
) -> HttpResponse | None:
    """Handle create/edit actions for organization elements.

    Processes form submissions for creating or editing organization elements.
    Handles validation callbacks, special form types (event/member forms), section navigation,
    and iframe mode rendering.

    Args:
        request: HTTP request object
        context: Context dictionary with event, run, and permission data
        event_slug: Event slug identifier
        permission: Permission string identifying the action type
        action_data: Dictionary from 'alls' containing form class, checks, and metadata
        element_uuid: UUID of element to edit (None for new elements)

    Returns:
        HttpResponse: Rendered template or redirect response, or None
    """
    form_type = action_data.get("form")
    writing = action_data.get("writing")

    check_callback = action_data.get("check")
    if check_callback:
        check_callback(request, context, event_slug)

    redirect_view = prepare_change(request, context, action_data)

    # Check if this is an iframe request
    is_frame = request.GET.get("frame") == "1" or request.POST.get("frame") == "1"

    # Process the edit operation using unified backend_edit handler
    result = backend_edit(request, context, form_type, element_uuid, writing_type=writing)

    return _evaluate_action_result(request, context, permission, result, is_frame, redirect_view)


def _evaluate_action_result(
    request: HttpRequest,
    context: dict,
    permission: str,
    result: bool | HttpResponse,  # noqa: FBT001
    is_frame: bool,  # noqa: FBT001
    redirect_view: str,
) -> HttpResponse | None:
    """Evaluate the result of an action and return appropriate HTTP response.

    Handles the outcome of edit/create operations by either returning AJAX responses,
    rendering templates for failed validations, or redirecting on success. Supports
    both standard and iframe rendering modes, as well as "continue editing" workflow.

    Args:
        request: HTTP request object
        context: Context dictionary with event, run, and form data
        permission: Permission string identifying the action type
        result: Result from backend_edit - either bool (success/failure) or HttpResponse (AJAX)
        is_frame: Whether the request is in iframe mode
        redirect_view: Optional view name to redirect to on success (defaults to permission)

    Returns:
        HttpResponse: AJAX response, rendered template, or redirect response, or None
    """
    # If result is an HttpResponse (AJAX), return it directly
    if isinstance(result, HttpResponse):
        return result

    # If edit was successful
    if result:
        # Set suggestion context for successful edit
        set_suggestion(context, permission)

        # Return success template for iframe mode
        if is_frame:
            return render(request, "elements/dashboard/form_success.html", context)

        # Determine redirect target - use provided or default to permission name
        if not redirect_view:
            redirect_view = permission

        # Handle "continue editing" workflow - redirect to new object form
        if "continue" in request.POST:
            redirect_view += "_new"

        # Redirect to success page with event slug
        return redirect(redirect_view, context["run"].get_slug())

    # Edit operation failed or is initial load - render appropriate template

    # Writing elements use a different template
    if context.get("is_writing"):
        return render(request, "larpmanager/orga/writing/writing.html", context)

    # Standard elements use iframe or standard edit template
    if is_frame:
        return render(request, "elements/dashboard/form_frame.html", context)

    return render(request, "larpmanager/orga/edit.html", context)


def _action_redirect(
    request: HttpRequest,
    context: dict,
    permission: str,
    action: Action,
    action_data: dict,
    element_uuid: str,
    additional: Any = None,
) -> HttpResponse:
    """Handle ORDER and DELETE actions that result in redirects.

    Processes reordering or deletion of organization elements and redirects to
    the permission's list view. For writing elements, clears event cache after reordering.

    Args:
        request: HTTP request object
        context: Context dictionary with event, run, and permission data
        permission: Permission string identifying the action type
        action: Action type (ORDER or DELETE)
        action_data: Dictionary from 'alls' containing form class, checks, and metadata
        element_uuid: UUID of element to operate on
        additional: Position offset for ORDER action (ignored for DELETE)

    Returns:
        HttpResponse: Redirect to permission's list view with event slug
    """
    form_type = action_data.get("form")
    writing = action_data.get("writing")
    model_type = form_type.Meta.model

    if action == Action.ORDER:
        backend_order(context, model_type, element_uuid, additional)
        if writing:
            reset_event_cache_all(context["run"])

    elif action == Action.DELETE:
        backend_delete(request, context, model_type, element_uuid, action_data.get("can_delete"))

    # Redirect to success page with event slug
    return redirect(permission, context["run"].get_slug())


def _action_show(
    request: HttpRequest, context: dict, action: Action, action_data: dict, element_uuid: str
) -> HttpResponse:
    """Handle display actions for organization elements.

    Retrieves an element and renders specialized views. Currently supports VERSIONS action
    to display version history with diff comparison for writing elements.

    Args:
        request: HTTP request object
        context: Context dictionary with event, run, and permission data
        action: Action type (currently supports VERSIONS)
        action_data: Dictionary from 'alls' containing form class, checks, and metadata
        element_uuid: UUID of element to display

    Returns:
        HttpResponse: Rendered template showing element details or version history
    """
    form_type = action_data.get("form")
    writing = action_data.get("writing")
    model_type = form_type.Meta.model
    element_type_name = model_type.__name__.lower()

    # Get the element
    backend_get(context, model_type, element_uuid, is_writing=bool(writing))

    if action == Action.VERSIONS:
        # Collect versions to show
        context["versions"] = (
            TextVersion.objects.filter(tp=writing, eid=context["el"].id).order_by("version").select_related("member")
        )
        previous_version = None
        for current_version in context["versions"]:
            if previous_version is not None:
                compute_diff(current_version, previous_version)
            else:
                current_version.diff = escape(current_version.text).replace("\n", "<br />")
            previous_version = current_version

        context["element"] = context["el"]
        context["typ"] = element_type_name
        return render(request, "larpmanager/orga/writing/versions.html", context)

    # Only type of action is Action.VIEW
    # Set up base element data and context
    context["el"].data = context["el"].show_complete()
    context["nm"] = element_type_name

    # Load event cache data for all related elements
    get_event_cache_all(context)

    # Handle character-specific data and relationships
    if element_type_name == "character":
        if context["el"].number in context["chars"]:
            context["char"] = context["chars"][context["el"].number]
        context["character"] = context["el"]

        # Get character sheet and relationship data
        get_character_sheet(context)
        get_character_relationships(context)
    else:
        # Handle non-character writing elements with applicable questions
        applicable_questions = QuestionApplicable.get_applicable(element_type_name)
        if applicable_questions:
            context["element"] = get_writing_element_fields(
                context,
                element_type_name,
                applicable_questions,
                context["el"].id,
                only_visible=False,
            )
        context["sheet_char"] = context["el"].show_complete()

    # Add plot-specific character relationships
    if element_type_name == "plot":
        context["sheet_plots"] = (
            PlotCharacterRel.objects.filter(plot=context["el"])
            .order_by("character__number")
            .select_related("character")
        )

    return render(request, "larpmanager/orga/writing/view.html", context)


def _orga_actions(
    request: HttpRequest,
    event_slug: str,
    permission: str,
    action: Action,
    element_uuid: str | None = None,
    additional: Any = None,
) -> HttpResponse | None:
    """Unified entry point for all operations on organization elements.

    Routes CRUD operations (create, edit, delete, reorder) to appropriate handlers
    based on the action type. Validates permissions, retrieves action configuration
    from the OrgaAction enum, and delegates to specialized handlers.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        permission: Permission string that maps to an OrgaAction enum member
        action: Action type (EDIT, NEW, DELETE, or ORDER)
        element_uuid: UUID of element to operate on (None for new elements)
        additional: Additional parameter for ORDER action (position offset)

    Returns:
        HttpResponse: Redirect to success page or result from action handler

    Raises:
        Http404: If permission is not found in OrgaAction enum
    """
    # Get permission data from enum
    orga_action = OrgaAction.from_string(permission)
    if orga_action is None:
        msg = f"permission unknown: {permission}"
        raise Http404(msg)

    action_data = orga_action.config

    # Verify user has permission
    if permission.endswith("form_option"):
        permission = permission.replace("form_option", "form")
    if action == Action.VIEW:
        permission = ["orga_reading", permission]
    context = check_event_context(request, event_slug, permission)

    if action in [Action.EDIT, Action.NEW]:
        return _action_change(request, context, event_slug, permission, action_data, element_uuid)

    if action in [Action.ORDER, Action.DELETE]:
        return _action_redirect(request, context, permission, action, action_data, element_uuid, additional)

    return _action_show(request, context, action, action_data, element_uuid)


def orga_new(request: HttpRequest, event_slug: str, permission: str) -> HttpResponse:
    """Create organization event objects through a unified interface."""
    return _orga_actions(request, event_slug, permission, Action.EDIT)


def orga_edit(
    request: HttpRequest,
    event_slug: str,
    permission: str,
    element_uuid: str | None = None,
) -> HttpResponse:
    """Edit organization event objects through a unified interface."""
    return _orga_actions(request, event_slug, permission, Action.EDIT, element_uuid)


def orga_versions(
    request: HttpRequest,
    event_slug: str,
    permission: str,
    element_uuid: str | None = None,
) -> HttpResponse:
    """Display text versions with diff comparison for writing elements."""
    return _orga_actions(request, event_slug, permission, Action.VERSIONS, element_uuid)


def orga_view(
    request: HttpRequest,
    event_slug: str,
    permission: str,
    element_uuid: str | None = None,
) -> HttpResponse:
    """Display writing element view."""
    return _orga_actions(request, event_slug, permission, Action.VIEW, element_uuid)


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
