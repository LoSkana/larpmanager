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
    SystemExpS2Widget,
)
from larpmanager.models.event import Run
from larpmanager.models.experience import (
    AbilityExp,
    AbilityTemplateExp,
    AbilityTypeExp,
    DeliveryExp,
    ModifierExp,
    RuleExp,
    SystemExp,
)


class OrgaSystemExpForm(BaseModelForm):
    """Form for OrgaSystemPx."""

    page_title = _("Experience System")

    page_info = _("Manage experience point systems")

    class Meta:
        model = SystemExp
        exclude = ("number",)


class ExpBaseForm(BaseModelForm):
    """Form for PxBase."""

    class Meta:
        abstract = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the instance with variable arguments."""
        super().__init__(*args, **kwargs)

    def save(self, commit: bool = True) -> Any:  # noqa: FBT001, FBT002
        """Save instance, applying the default system when field is hidden."""
        instance = super().save(commit=False)
        if hasattr(instance, "_default_system") and not instance.system_id:
            instance.system = instance._default_system  # noqa: SLF001
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class OrgaDeliveryExpForm(ExpBaseForm):
    """Form for OrgaDeliveryExp."""

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
        model = DeliveryExp
        exclude = ("number",)

        widgets: ClassVar[dict] = {"characters": EventCharacterS2WidgetMulti, "system": SystemExpS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with event configuration."""
        super().__init__(*args, **kwargs)

        self.configure_field_event("auto_populate_run", self.params.get("event"))

        event = self.params.get("event")
        systems = list(event.get_elements(SystemExp)) if event else []
        if len(systems) == 1:
            self.delete_field("system")
            self.instance._default_system = systems[0]  # noqa: SLF001
        elif "system" in self.fields:
            self.configure_field_event("system", event)


class OrgaAbilityTemplateExpForm(BaseModelForm):
    """Form for OrgaAbilityTemplatePx."""

    page_title = _("Ability Template")

    page_info = _("This page allows you to add or edit an ability template")

    class Meta:
        model = AbilityTemplateExp
        exclude = ("number",)


class OrgaAbilityExpForm(ExpBaseForm):
    """Form for OrgaAbilityExp."""

    load_js: ClassVar[list] = ["characters-choices"]

    page_title = _("Ability")

    page_info = _("Manage experience point abilities")

    class Meta:
        model = AbilityExp
        exclude = ("number",)

        widgets: ClassVar[dict] = {
            "system": SystemExpS2Widget,
            "typ": AbilityTypePxS2Widget,
            "characters": EventCharacterS2WidgetMulti,
            "prerequisites": AbilityS2WidgetMulti,
            "requirements": EventWritingOptionS2WidgetMulti,
            "template": AbilityTemplateS2WidgetMulti,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with event-specific ability configuration."""
        super().__init__(*args, **kwargs)

        event = self.params.get("event")

        # Handle system field visibility
        systems = list(event.get_elements(SystemExp)) if event else []
        if len(systems) == 1:
            self.delete_field("system")
            self.instance._default_system = systems[0]  # noqa: SLF001
        elif "system" in self.fields:
            self.configure_field_event("system", event)

        # Configure event-specific widgets
        for field_name in ["typ", "characters", "prerequisites", "requirements", "template", "dependents"]:
            if field_name in self.fields and hasattr(self.fields[field_name].widget, "set_event"):
                self.configure_field_event(field_name, event)

        exp_user = get_event_config(event.id, "exp_user", default_value=False, context=self.params)
        exp_templates = get_event_config(event.id, "exp_templates", default_value=False, context=self.params)

        # Remove template field if exp_templates is disabled
        if not exp_templates:
            self.delete_field("template")

        # Remove user-experience fields if exp_user is disabled
        if not exp_user:
            self.delete_field("visible")

    def clean(self) -> dict:
        """Validate that the ability is not listed as its own prerequisite."""
        cleaned_data = super().clean()
        prerequisites = cleaned_data.get("prerequisites")
        if prerequisites and self.instance and self.instance.pk and self.instance in prerequisites:
            self.add_error("prerequisites", _("An ability cannot be a prerequisite of itself."))
        return cleaned_data


class OrgaAbilityTypeExpForm(BaseModelForm):
    """Form for OrgaAbilityTypePx."""

    page_title = _("Ability type")

    page_info = _("Manage experience point ability types")

    class Meta:
        model = AbilityTypeExp
        exclude = ("number",)


class OrgaRuleExpForm(BaseModelForm):
    """Form for OrgaRuleExp."""

    page_title = _("Rule")

    page_info = _("Manage rules for computed fields")

    class Meta:
        model = RuleExp
        exclude = ("number", "order")
        widgets: ClassVar[dict] = {"abilities": AbilityS2WidgetMulti, "field": ComputedFieldS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form, configure fields for abilities and writing questions."""
        super().__init__(*args, **kwargs)
        self.delete_field("name")

        for field in ["abilities", "field"]:
            # Configure abilities widget with event context
            self.configure_field_event(field, self.params.get("event"))


class OrgaModifierExpForm(BaseModelForm):
    """Form for OrgaModifierExp."""

    page_title = _("Rule")

    page_info = _(
        "Manage ability modifiers. Modifiers are triggered only if all prerequisites "
        "and requirements are met. If multiple modifiers apply, only the first is used",
    )

    class Meta:
        model = ModifierExp
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
