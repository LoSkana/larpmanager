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
from typing import TYPE_CHECKING, Any

from django.contrib import messages
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
from larpmanager.forms.event import (
    OrgaAppearanceForm,
    OrgaConfigForm,
    OrgaEventButtonForm,
    OrgaEventRoleForm,
    OrgaEventTextForm,
    OrgaPreferencesForm,
    OrgaProgressStepForm,
    OrgaPromotionForm,
    OrgaQuickSetupForm,
    OrgaRunForm,
)
from larpmanager.forms.experience import (
    OrgaAbilityExpForm,
    OrgaAbilityTemplateExpForm,
    OrgaAbilityTypeExpForm,
    OrgaCriterionExpForm,
    OrgaDeliveryExpForm,
    OrgaModifierExpForm,
    OrgaRuleExpForm,
    OrgaSystemExpForm,
)
from larpmanager.forms.inventory import (
    OrgaInventoryForm,
    OrgaInventoryTypeForm,
    OrgaPoolLabelForm,
    OrgaPoolTypeForm,
)
from larpmanager.forms.miscellanea import (
    OneTimeAccessTokenForm,
    OneTimeContentForm,
    OrgaAlbumForm,
    OrgaMilestoneForm,
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
from larpmanager.forms.warehouse import (
    OrgaWarehouseAreaForm,
    OrgaWarehouseItemAreasForm,
    OrgaWarehouseItemAssignmentForm,
)
from larpmanager.forms.writing import (
    OrgaFactionForm,
    OrgaGuildForm,
    OrgaHandoutForm,
    OrgaHandoutTemplateForm,
    OrgaPlotForm,
    OrgaPrologueForm,
    OrgaPrologueTypeForm,
    OrgaQuestForm,
    OrgaQuestTypeForm,
    OrgaRelationshipTagForm,
    OrgaSpeedLarpForm,
    OrgaTraitForm,
)
from larpmanager.models.casting import Quest, QuestType
from larpmanager.models.experience import AbilityTypeExp
from larpmanager.models.registration import Registration
from larpmanager.models.writing import HandoutTemplate, PrologueType, TextVersionChoices, get_event_elements
from larpmanager.utils.core.exceptions import RedirectError

if TYPE_CHECKING:
    from django.http import HttpRequest


def validate_ability_exp(request: HttpRequest, context: dict, event_slug: str) -> None:
    """Validate that ability types exist before allowing ability creation."""
    if not get_event_elements(context["event"].id, AbilityTypeExp, context=context).exists():
        # Warn user and redirect to ability types creation page
        messages.warning(request, _("You must create at least one ability type before you can create abilities"))
        msg = "orga_exp_ability_types_new"
        raise RedirectError(msg, args=[event_slug])


def validate_quest(request: HttpRequest, context: dict, event_slug: str) -> None:
    """Verify that quest types are available before allowing quest creation."""
    if not get_event_elements(context["event"].id, QuestType, context=context).exists():
        # Add warning message and redirect to quest types adding page
        messages.warning(request, _("You must create at least one quest type before you can create quests"))
        msg = "orga_quest_types_new"
        raise RedirectError(msg, args=[event_slug])


def validate_trait(request: HttpRequest, context: dict, event_slug: str) -> None:
    """Validate prerequisite: at least one quest must exist."""
    if not get_event_elements(context["event"].id, Quest, context=context).exists():
        # Add warning message and redirect to quests adding page
        messages.warning(request, _("You must create at least one quest before you can create traits"))
        msg = "orga_quests_new"
        raise RedirectError(msg, args=[event_slug])


def validate_handout(request: HttpRequest, context: dict, event_slug: str) -> None:
    """Validate handout templates exist before allowing handout creation."""
    if not get_event_elements(context["event"].id, HandoutTemplate, context=context).exists():
        # Display warning and redirect to template creation page
        messages.warning(request, _("You must create at least one handout template before you can create handouts"))
        msg = "orga_handout_templates_new"
        raise RedirectError(msg, args=[event_slug])


def validate_prologue(request: HttpRequest, context: dict, event_slug: str) -> None:
    """Validate prologue type exist before allowing prologue creation."""
    if not get_event_elements(context["event"].id, PrologueType, context=context).exists():
        # Display warning and redirect to template creation page
        messages.warning(request, _("You must create at least one prologue type before you can create prologues"))
        msg = "orga_prologue_types_new"
        raise RedirectError(msg, args=[event_slug])


def validate_payments(request: HttpRequest, context: dict, event_slug: str) -> None:
    """Validate that at least one active signup exists for the run before allowing payment creation."""
    run = context.get("run")
    if not Registration.objects.filter(run=run, cancellation_date__isnull=True).exists():
        messages.warning(request, _("There are no signups for this event, so no payment can be created."))
        msg = "orga_payments"
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
    PROMOTION = ("orga_publication", {"form": OrgaPromotionForm, "event_form": True})
    QUICK = ("orga_quick", {"form": OrgaQuickSetupForm, "event_form": True})
    APPEARANCE = ("orga_appearance", {"form": OrgaAppearanceForm, "event_form": True})
    ROLES = ("orga_roles", {"form": OrgaEventRoleForm, "can_delete": lambda _context, element: element.number != 1})
    TEXTS = ("orga_texts", {"form": OrgaEventTextForm})
    BUTTONS = ("orga_buttons", {"form": OrgaEventButtonForm, "button": True})

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
    GUILDS = ("orga_guilds", {"form": OrgaGuildForm, "writing": TextVersionChoices.GUILD})
    QUEST_TYPES = ("orga_quest_types", {"form": OrgaQuestTypeForm, "writing": TextVersionChoices.QUEST_TYPE})
    QUESTS = ("orga_quests", {"form": OrgaQuestForm, "writing": TextVersionChoices.QUEST, "check": validate_quest})
    TRAITS = ("orga_traits", {"form": OrgaTraitForm, "writing": TextVersionChoices.TRAIT, "check": validate_trait})
    HANDOUTS = (
        "orga_handouts",
        {"form": OrgaHandoutForm, "writing": TextVersionChoices.HANDOUT, "check": validate_handout},
    )
    HANDOUT_TEMPLATES = ("orga_handout_templates", {"form": OrgaHandoutTemplateForm})
    PROLOGUE_TYPES = ("orga_prologue_types", {"form": OrgaPrologueTypeForm})
    PROLOGUES = (
        "orga_prologues",
        {"form": OrgaPrologueForm, "writing": TextVersionChoices.PROLOGUE, "check": validate_prologue},
    )
    SPEEDLARPS = ("orga_speedlarps", {"form": OrgaSpeedLarpForm, "writing": TextVersionChoices.SPEEDLARP})
    PROGRESS_STEPS = ("orga_progress_steps", {"form": OrgaProgressStepForm})
    RELATIONSHIP_TAGS = ("orga_relationship_tags", {"form": OrgaRelationshipTagForm, "relationship_tags": True})

    # Registration
    REGISTRATION_TICKETS = ("orga_registration_tickets", {"form": OrgaRegistrationTicketForm, "tickets": True})
    REGISTRATION_SECTIONS = ("orga_registration_sections", {"form": OrgaRegistrationSectionForm})
    REGISTRATION_FORM = (
        "orga_registration_form",
        {"form": OrgaRegistrationQuestionForm, "can_delete": lambda _context, element: len(element.typ) == 1},
    )
    REGISTRATION_FORM_OPTION = ("orga_registration_form_option", {"form": OrgaRegistrationOptionForm})
    REGISTRATION_QUOTAS = ("orga_registration_quotas", {"form": OrgaRegistrationQuotaForm})
    REGISTRATION_INSTALLMENTS = ("orga_registration_installments", {"form": OrgaRegistrationInstallmentForm})
    REGISTRATION_SURCHARGES = ("orga_registration_surcharges", {"form": OrgaRegistrationSurchargeForm})

    # Experience Points
    PX_SYSTEMS = ("orga_exp_systems", {"form": OrgaSystemExpForm, "exp": True})
    PX_DELIVERIES = ("orga_exp_deliveries", {"form": OrgaDeliveryExpForm, "exp": True})
    PX_ABILITIES = ("orga_exp_abilities", {"form": OrgaAbilityExpForm, "check": validate_ability_exp, "exp": True})
    PX_ABILITY_TYPES = ("orga_exp_ability_types", {"form": OrgaAbilityTypeExpForm, "exp": True})
    PX_ABILITY_TEMPLATES = ("orga_exp_ability_templates", {"form": OrgaAbilityTemplateExpForm, "exp": True})
    PX_RULES = ("orga_exp_rules", {"form": OrgaRuleExpForm})
    PX_MODIFIERS = ("orga_exp_modifiers", {"form": OrgaModifierExpForm})
    PX_CRITERIONS = ("orga_exp_criterions", {"form": OrgaCriterionExpForm})

    # Inventory
    CI_INVENTORY = ("orga_ci_inventory", {"form": OrgaInventoryForm})
    CI_POOL_TYPES = ("orga_ci_pool_types", {"form": OrgaPoolTypeForm})
    CI_INVENTORY_TYPES = ("orga_ci_inventory_types", {"form": OrgaInventoryTypeForm})
    CI_POOL_LABELS = ("orga_ci_pool_labels", {"form": OrgaPoolLabelForm})

    # Miscellaneous
    ALBUMS = ("orga_albums", {"form": OrgaAlbumForm})
    MILESTONES = ("orga_milestones", {"form": OrgaMilestoneForm})
    UTILS = ("orga_utils", {"form": UtilForm})
    WORKSHOP_MODULES = ("orga_workshop_modules", {"form": WorkshopModuleForm})
    WORKSHOP_QUESTIONS = ("orga_workshop_questions", {"form": WorkshopQuestionForm})
    WORKSHOP_OPTIONS = ("orga_workshop_options", {"form": WorkshopOptionForm})
    PROBLEMS = ("orga_problems", {"form": OrgaProblemForm})

    # Warehouse
    WAREHOUSE_AREA = ("orga_warehouse_area", {"form": OrgaWarehouseAreaForm})
    WAREHOUSE_MANIFEST = ("orga_warehouse_manifest", {"form": OrgaWarehouseItemAssignmentForm})
    WAREHOUSE_ASSIGNMENT_ITEM = ("orga_warehouse_manifest", {})
    WAREHOUSE_ITEM_AREAS = ("orga_warehouse_items", {"form": OrgaWarehouseItemAreasForm})

    # One-time content
    ONETIMES = ("orga_onetimes", {"form": OneTimeContentForm})
    ONETIMES_TOKENS = ("orga_onetimes_tokens", {"form": OneTimeAccessTokenForm})

    # Accounting
    DISCOUNTS = ("orga_discounts", {"form": OrgaDiscountForm})
    TOKENS = ("orga_tokens", {"form": OrgaTokenForm})
    CREDITS = ("orga_credits", {"form": OrgaCreditForm})
    PAYMENTS = ("orga_payments", {"form": OrgaPaymentForm, "check": validate_payments})
    OUTFLOWS = ("orga_outflows", {"form": OrgaOutflowForm})
    INFLOWS = ("orga_inflows", {"form": OrgaInflowForm})
    EXPENSES = ("orga_expenses", {"form": OrgaExpenseForm})
