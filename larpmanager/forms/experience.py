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
from typing import Any, ClassVar

from django import forms
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_event_config
from larpmanager.forms.base import BaseForm, BaseModelForm
from larpmanager.forms.utils import (
    AbilityS2WidgetMulti,
    AbilityTemplateS2WidgetMulti,
    AbilityTypePxS2Widget,
    ComputedFieldS2Widget,
    EventCharacterS2WidgetMulti,
    EventWritingOptionS2WidgetMulti,
    RunCampaignS2Widget,
)
from larpmanager.models.event import Run
from larpmanager.models.experience import AbilityPx, AbilityTemplatePx, AbilityTypePx, DeliveryPx, ModifierPx, RulePx


class PxBaseForm(BaseModelForm):
    """Form for PxBase."""

    class Meta:
        abstract = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the instance with variable arguments."""
        super().__init__(*args, **kwargs)


class OrgaDeliveryPxForm(PxBaseForm):
    """Form for OrgaDeliveryPx."""

    load_js: ClassVar[list] = ["characters-choices"]

    page_title = _("Delivery")

    page_info = _("Manage experience point deliveries")

    auto_populate_run = forms.ModelChoiceField(
        queryset=Run.objects.none(),
        required=False,
        label=_("Load from event"),
        help_text=_(
            "If you select an event, all characters from that event's registrations will be automatically loaded"
        ),
        widget=RunCampaignS2Widget,
    )

    class Meta:
        model = DeliveryPx
        exclude = ("number",)

        widgets: ClassVar[dict] = {"characters": EventCharacterS2WidgetMulti}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with event configuration."""
        super().__init__(*args, **kwargs)

        self.configure_field_event("auto_populate_run", self.params.get("event"))


class OrgaAbilityTemplatePxForm(BaseModelForm):
    """Form for OrgaAbilityTemplatePx."""

    page_title = _("Ability Template")

    page_info = _("This page allows you to add or edit an ability template")

    class Meta:
        model = AbilityTemplatePx
        exclude = ("number",)


class OrgaAbilityPxForm(PxBaseForm):
    """Form for OrgaAbilityPx."""

    load_js: ClassVar[list] = ["characters-choices"]

    page_title = _("Ability")

    page_info = _("Manage experience point abilities")

    class Meta:
        model = AbilityPx
        exclude = ("number",)

        widgets: ClassVar[dict] = {
            "typ": AbilityTypePxS2Widget,
            "characters": EventCharacterS2WidgetMulti,
            "prerequisites": AbilityS2WidgetMulti,
            "requirements": EventWritingOptionS2WidgetMulti,
            "template": AbilityTemplateS2WidgetMulti,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with event-specific ability configuration."""
        super().__init__(*args, **kwargs)

        # Configure event-specific widgets
        for field_name in ["typ", "characters", "prerequisites", "requirements", "template", "dependents"]:
            if field_name in self.fields and hasattr(self.fields[field_name].widget, "set_event"):
                self.configure_field_event(field_name, self.params.get("event"))

        px_user = get_event_config(self.params.get("event").id, "px_user", default_value=False, context=self.params)
        px_templates = get_event_config(
            self.params.get("event").id, "px_templates", default_value=False, context=self.params
        )

        # Remove template field if px_templates is disabled
        if not px_templates:
            self.delete_field("template")

        # Remove user-experience fields if px_user is disabled
        if not px_user:
            self.delete_field("visible")

    def clean(self) -> dict:
        """Validate that the ability is not listed as its own prerequisite."""
        cleaned_data = super().clean()
        prerequisites = cleaned_data.get("prerequisites")
        if prerequisites and self.instance and self.instance.pk and self.instance in prerequisites:
            self.add_error("prerequisites", _("An ability cannot be a prerequisite of itself."))
        return cleaned_data


class OrgaAbilityTypePxForm(BaseModelForm):
    """Form for OrgaAbilityTypePx."""

    page_title = _("Ability type")

    page_info = _("Manage experience point ability types")

    class Meta:
        model = AbilityTypePx
        exclude = ("number",)


class OrgaRulePxForm(BaseModelForm):
    """Form for OrgaRulePx."""

    page_title = _("Rule")

    page_info = _("Manage rules for computed fields")

    class Meta:
        model = RulePx
        exclude = ("number", "order")
        widgets: ClassVar[dict] = {"abilities": AbilityS2WidgetMulti, "field": ComputedFieldS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form, configure fields for abilities and writing questions."""
        super().__init__(*args, **kwargs)
        self.delete_field("name")

        for field in ["abilities", "field"]:
            # Configure abilities widget with event context
            self.configure_field_event(field, self.params.get("event"))


class OrgaModifierPxForm(BaseModelForm):
    """Form for OrgaModifierPx."""

    page_title = _("Rule")

    page_info = _(
        "Manage ability modifiers. Modifiers are triggered only if all prerequisites "
        "and requirements are met. If multiple modifiers apply, only the first is used",
    )

    class Meta:
        model = ModifierPx
        exclude = ("number", "order")
        widgets: ClassVar[dict] = {
            "abilities": AbilityS2WidgetMulti,
            "prerequisites": AbilityS2WidgetMulti,
            "requirements": EventWritingOptionS2WidgetMulti,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure event-related fields."""
        super().__init__(*args, **kwargs)
        self.delete_field("name")

        # Configure event-specific widgets
        for field in ["abilities", "prerequisites", "requirements"]:
            self.configure_field_event(field, self.params.get("event"))


class SelectNewAbility(BaseForm):
    """Represents SelectNewAbility model."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with dynamic choice field from context."""
        # Extract context parameters from kwargs
        context = self.params = kwargs.pop("context")
        super().__init__(*args, **kwargs)

        # Add selection field with choices from context
        self.fields["sel"] = forms.ChoiceField(choices=context["list"])
