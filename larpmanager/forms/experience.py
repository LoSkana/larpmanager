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
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.base import MyForm
from larpmanager.forms.utils import (
    AbilityS2WidgetMulti,
    EventCharacterS2WidgetMulti,
    EventWritingOptionS2WidgetMulti,
)
from larpmanager.models.experience import AbilityPx, AbilityTypePx, DeliveryPx, ModifierPx, RulePx
from larpmanager.models.form import WritingQuestion, WritingQuestionType


class PxBaseForm(MyForm):
    class Meta:
        abstract = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the instance with variable arguments.

        This constructor passes all provided arguments directly to the parent
        class constructor, enabling flexible initialization while maintaining
        the inheritance chain.

        Args:
            *args: Variable length argument list passed to parent class.
            **kwargs: Arbitrary keyword arguments passed to parent class.

        Returns:
            None: This method does not return a value.

        Example:
            >>> instance = ClassName(arg1, arg2, key1=value1, key2=value2)
        """
        # Call parent class constructor with all provided arguments
        # This ensures proper initialization of the inheritance chain
        super().__init__(*args, **kwargs)


class OrgaDeliveryPxForm(PxBaseForm):
    load_js = ["characters-choices"]

    page_title = _("Delivery")

    page_info = _("Manage experience point deliveries")

    class Meta:
        model = DeliveryPx
        exclude = ("number",)

        widgets = {"characters": EventCharacterS2WidgetMulti}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the instance with variable arguments.

        This constructor acts as a transparent proxy to the parent class constructor,
        forwarding all positional and keyword arguments without modification. This
        pattern ensures proper initialization of the inheritance chain while allowing
        maximum flexibility in the arguments passed to the parent class.

        Args:
            *args: Variable length argument list that will be forwarded to the
                parent class constructor without modification.
            **kwargs: Arbitrary keyword arguments that will be forwarded to the
                parent class constructor without modification.

        Returns:
            None

        Example:
            >>> instance = ClassName(arg1, arg2, key1=value1, key2=value2)
            >>> # All arguments are passed through to parent class
        """
        # Forward all arguments to parent class constructor to maintain
        # proper inheritance chain initialization
        super().__init__(*args, **kwargs)


class OrgaAbilityPxForm(PxBaseForm):
    load_js = ["characters-choices"]

    page_title = _("Ability")

    page_info = _("Manage experience point abilities")

    class Meta:
        model = AbilityPx
        exclude = ("number",)

        widgets = {
            "characters": EventCharacterS2WidgetMulti,
            "prerequisites": AbilityS2WidgetMulti,
            "requirements": EventWritingOptionS2WidgetMulti,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the instance with variable arguments.

        This constructor passes all provided arguments directly to the parent
        class constructor, enabling flexible initialization while maintaining
        the inheritance chain.

        Args:
            *args: Variable length argument list passed to parent class.
            **kwargs: Arbitrary keyword arguments passed to parent class.

        Example:
            >>> instance = ClassName(arg1, arg2, key1=value1, key2=value2)
        """
        # Call parent class constructor with all provided arguments
        # This ensures proper initialization of the inheritance chain
        super().__init__(*args, **kwargs)


class OrgaAbilityTypePxForm(MyForm):
    page_title = _("Ability type")

    page_info = _("Manage experience point ability types")

    class Meta:
        model = AbilityTypePx
        exclude = ("number",)


class OrgaRulePxForm(MyForm):
    page_title = _("Rule")

    page_info = _("Manage rules for computed fields")

    class Meta:
        model = RulePx
        exclude = ("number", "order")
        widgets = {"abilities": AbilityS2WidgetMulti}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.delete_field("name")

        self.fields["abilities"].widget.set_event(self.params["event"])
        qs = WritingQuestion.objects.filter(event=self.params["event"], typ=WritingQuestionType.COMPUTED)
        self.fields["field"].queryset = qs


class OrgaModifierPxForm(MyForm):
    page_title = _("Rule")

    page_info = _(
        "Manage ability modifiers. Modifiers are triggered only if all prerequisites "
        + "and requirements are met. If multiple modifiers apply, only the first is used"
    )

    class Meta:
        model = ModifierPx
        exclude = ("number", "order")
        widgets = {
            "abilities": AbilityS2WidgetMulti,
            "prerequisites": AbilityS2WidgetMulti,
            "requirements": EventWritingOptionS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.delete_field("name")

        for field in ["abilities", "prerequisites", "requirements"]:
            self.fields[field].widget.set_event(self.params["event"])


class SelectNewAbility(forms.Form):
    def __init__(self, *args, **kwargs):
        ctx = self.params = kwargs.pop("ctx")
        super().__init__(*args, **kwargs)
        self.fields["sel"] = forms.ChoiceField(choices=ctx["list"])
