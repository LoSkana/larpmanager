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
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_event_config
from larpmanager.forms.base import BaseForm, BaseModelForm, MultichoiceMixin
from larpmanager.forms.utils import (
    AbilityS2WidgetMulti,
    AbilityTemplateS2WidgetMulti,
    AbilityTypePxS2Widget,
    ComputedFieldS2Widget,
    EventCharacterS2WidgetMulti,
    EventWritingOptionS2WidgetMulti,
    RunCampaignS2Widget,
    SystemExpS2Widget,
    WritingTinyMCE,
)
from larpmanager.models.event import Run
from larpmanager.models.experience import (
    AbilityExp,
    AbilityTemplateExp,
    AbilityTypeExp,
    CriterionExp,
    DeliveryExp,
    ModifierExp,
    RuleExp,
    SystemExp,
)


class OrgaSystemExpForm(BaseModelForm):
    """Form for OrgaSystemPx."""

    page_title = _("Experience System")

    page_info = _("Manage the experience point systems available for this event")

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
            self.save_select2_m2m(instance)
        return instance


class OrgaDeliveryExpForm(MultichoiceMixin, ExpBaseForm):
    """Form for OrgaDeliveryExp."""

    load_js: ClassVar[list] = ["multichoice"]

    page_title = _("Delivery")

    page_info = _("Manage experience point deliveries awarded to characters")

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

        run = self.params.get("run")
        if run:
            self.add_multichoice_config(
                field_id="characters",
                link_id="characters_available",
                label=str(_("Show available characters")),
                url=reverse("orga_multichoice_available", args=[run.get_slug()]),
                data={"type": self._meta.model.__name__.lower()},
                ctx_edit_uuid=True,
            )


class OrgaAbilityTemplateExpForm(BaseModelForm):
    """Form for OrgaAbilityTemplatePx."""

    page_title = _("Ability Template")

    page_info = _("Define reusable ability templates that can be assigned to individual abilities")

    class Meta:
        model = AbilityTemplateExp
        exclude = ("number",)

        widgets: ClassVar[dict] = {"descr": WritingTinyMCE()}


class OrgaAbilityExpForm(MultichoiceMixin, ExpBaseForm):
    """Form for OrgaAbilityExp."""

    load_js: ClassVar[list] = ["multichoice"]

    page_title = _("Ability")

    page_info = _("Manage the abilities participants can purchase with experience points for this event")

    class Meta:
        model = AbilityExp
        exclude = ("number",)

        widgets: ClassVar[dict] = {
            "descr": WritingTinyMCE(),
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

        run = self.params.get("run")
        if run:
            self.add_multichoice_config(
                field_id="characters",
                link_id="characters_available",
                label=str(_("Show available characters")),
                url=reverse("orga_multichoice_available", args=[run.get_slug()]),
                data={"type": self._meta.model.__name__.lower()},
                ctx_edit_uuid=True,
            )
            if "prerequisites" in self.fields:
                self.add_multichoice_config(
                    field_id="prerequisites",
                    link_id="prerequisites_available",
                    label=str(_("Show available abilities")),
                    url=reverse("orga_exp_available", args=[run.get_slug()]),
                    data={"type": "ability", "filter_context": "ability"},
                    form_edit_uuid=True,
                )
            if "requirements" in self.fields:
                self.add_multichoice_config(
                    field_id="requirements",
                    link_id="ability_requirements_available",
                    label=str(_("Show available options")),
                    url=reverse("orga_form_available", args=[run.get_slug()]),
                    data={"type": "writing_option", "owner": "abilityexp", "field": "requirements"},
                    form_edit_uuid=True,
                )

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

    page_info = _("Organize purchasable abilities into categories by managing ability types")

    class Meta:
        model = AbilityTypeExp
        exclude = ("number",)


class OrgaRuleExpForm(MultichoiceMixin, BaseModelForm):
    """Form for OrgaRuleExp."""

    load_js: ClassVar[list] = ["multichoice"]

    page_title = _("Rule")

    page_info = _("Define rules that determine how abilities modify computed character fields")

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

        run = self.params.get("run")
        if run and "abilities" in self.fields:
            self.add_multichoice_config(
                field_id="abilities",
                link_id="rule_abilities_available",
                label=str(_("Show available abilities")),
                url=reverse("orga_exp_available", args=[run.get_slug()]),
                data={"type": "ability"},
            )


class OrgaModifierExpForm(MultichoiceMixin, BaseModelForm):
    """Form for OrgaModifierExp."""

    load_js: ClassVar[list] = ["multichoice"]

    page_title = _("Rule")

    page_info = _("Configure cost modifiers that adjust ability prices based on prerequisites or character fields")

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

        run = self.params.get("run")
        if run:
            if "abilities" in self.fields:
                self.add_multichoice_config(
                    field_id="abilities",
                    link_id="modifier_abilities_available",
                    label=str(_("Show available abilities")),
                    url=reverse("orga_exp_available", args=[run.get_slug()]),
                    data={"type": "ability"},
                )
            if "prerequisites" in self.fields:
                self.add_multichoice_config(
                    field_id="prerequisites",
                    link_id="modifier_prerequisites_available",
                    label=str(_("Show available abilities")),
                    url=reverse("orga_exp_available", args=[run.get_slug()]),
                    data={"type": "ability"},
                )
            if "requirements" in self.fields:
                self.add_multichoice_config(
                    field_id="requirements",
                    link_id="modifier_requirements_available",
                    label=str(_("Show available options")),
                    url=reverse("orga_form_available", args=[run.get_slug()]),
                    data={"type": "writing_option", "owner": "modifierexp", "field": "requirements"},
                    form_edit_uuid=True,
                )


class OrgaCriterionExpForm(MultichoiceMixin, ExpBaseForm):
    """Form for OrgaCriterionExp."""

    load_js: ClassVar[list] = ["multichoice"]

    page_title = _("Criterion")

    page_info = _(
        "Define criteria that conditionally modify experience point totals based on prerequisites or character options"
    )

    class Meta:
        model = CriterionExp
        exclude = ("number", "order")
        widgets: ClassVar[dict] = {
            "system": SystemExpS2Widget,
            "prerequisites": AbilityS2WidgetMulti,
            "requirements": EventWritingOptionS2WidgetMulti,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure event-related fields."""
        super().__init__(*args, **kwargs)
        self.delete_field("name")

        event = self.params.get("event")
        systems = list(event.get_elements(SystemExp)) if event else []
        if len(systems) == 1:
            self.delete_field("system")
            self.instance._default_system = systems[0]  # noqa: SLF001
        elif "system" in self.fields:
            self.configure_field_event("system", event)

        for field in ["prerequisites", "requirements"]:
            self.configure_field_event(field, event)

        run = self.params.get("run")
        if run:
            if "prerequisites" in self.fields:
                self.add_multichoice_config(
                    field_id="prerequisites",
                    link_id="criterion_prerequisites_available",
                    label=str(_("Show available abilities")),
                    url=reverse("orga_exp_available", args=[run.get_slug()]),
                    data={"type": "ability"},
                )
            if "requirements" in self.fields:
                self.add_multichoice_config(
                    field_id="requirements",
                    link_id="criterion_requirements_available",
                    label=str(_("Show available options")),
                    url=reverse("orga_form_available", args=[run.get_slug()]),
                    data={"type": "writing_option", "owner": "criterionexp", "field": "requirements"},
                    form_edit_uuid=True,
                )


class SelectNewAbility(BaseForm):
    """Represents SelectNewAbility model."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with dynamic choice field from context."""
        # Extract context parameters from kwargs
        context = self.params = kwargs.pop("context")
        super().__init__(*args, **kwargs)

        # Add selection field with choices from context
        self.fields["sel"] = forms.ChoiceField(choices=context["list"])
