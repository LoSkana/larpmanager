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

from larpmanager.forms.accounting import (
    ExeCollectionForm,
    ExeCreditForm,
    ExeDonationForm,
    ExeExpenseForm,
    ExeInflowForm,
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


class ExeAction(str, Enum):
    """Enum for executive action types used in edit/create/delete operations.

    Each enum member has a string value (the permission string) and a config attribute
    containing the form class and optional metadata.
    """

    def __new__(cls, value: str, config: dict[str, Any]) -> Any:
        """Create a new enum member with value and config."""
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.config = config
        return obj

    @classmethod
    def from_string(cls, permission: str) -> ExeAction | None:
        """Look up an ExeAction by its permission string value."""
        for member in cls:
            if member.value == permission:
                return member
        return None

    # User preferences and association settings
    PREFERENCES = ("", {"form": ExePreferencesForm, "member_form": True})
    METHODS = ("exe_methods", {"form": ExePaymentSettingsForm, "assoc_form": True})
    ASSOCIATION = ("exe_association", {"form": ExeAssociationForm, "assoc_form": True})
    ROLES = ("exe_roles", {"form": ExeAssociationRoleForm, "can_delete": lambda _context, element: element.number != 1})
    CONFIG = ("exe_config", {"form": ExeConfigForm, "assoc_form": True})
    PROFILE = ("exe_profile", {"form": ExeProfileForm, "assoc_form": True})
    QUICK = ("exe_quick", {"form": ExeQuickSetupForm, "assoc_form": True})

    # Appearance
    APPEARANCE = ("exe_appearance", {"form": ExeAppearanceForm, "assoc_form": True})
    TEXTS = ("exe_texts", {"form": ExeAssociationTextForm})
    TRANSLATIONS = ("exe_translations", {"form": ExeAssociationTranslationForm})

    # Event
    EVENTS = ("exe_events", {"form": OrgaRunForm, "additional_field": "event"})
    TEMPLATES = ("exe_templates", {"form": ExeTemplateForm})

    # Member management
    VOLUNTEER_REGISTRY = ("exe_volunteer_registry", {"form": ExeVolunteerRegistryForm})
    BADGES = ("exe_badges", {"form": ExeBadgeForm})

    # Warehouse management
    WAREHOUSE_CONTAINERS = ("exe_warehouse_containers", {"form": ExeWarehouseContainerForm})
    WAREHOUSE_TAGS = ("exe_warehouse_tags", {"form": ExeWarehouseTagForm})
    WAREHOUSE_ITEMS = ("exe_warehouse_items", {"form": ExeWarehouseItemForm})
    WAREHOUSE_MOVEMENTS = ("exe_warehouse_movements", {"form": ExeWarehouseMovementForm})

    # Accounting
    OUTFLOWS = ("exe_outflows", {"form": ExeOutflowForm})
    INFLOWS = ("exe_inflows", {"form": ExeInflowForm})
    DONATIONS = ("exe_donations", {"form": ExeDonationForm})
    CREDITS = ("exe_credits", {"form": ExeCreditForm})
    TOKENS = ("exe_tokens", {"form": ExeTokenForm})
    EXPENSES = ("exe_expenses", {"form": ExeExpenseForm})
    PAYMENTS = ("exe_payments", {"form": ExePaymentForm})
    COLLECTIONS = ("exe_collections", {"form": ExeCollectionForm})
    REFUNDS = ("exe_refunds", {"form": ExeRefundRequestForm})

    # Miscellaneous
    URLSHORTNER = ("exe_urlshortner", {"form": ExeUrlShortnerForm})
