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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class OrgaDeliveryPxForm(PxBaseForm):
    load_js = ["characters-choices"]

    page_title = _("Delivery")

    page_info = _("Manage experience point deliveries")

    class Meta:
        model = DeliveryPx
        exclude = ("number",)

        widgets = {"characters": EventCharacterS2WidgetMulti}

    def __init__(self, *args, **kwargs):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for s in ["prerequisites", "requirements"]:
            self.fields[s].widget.set_event(self.params["event"])

        px_user = self.params["event"].get_config("px_user", False)

        self.fields["typ"].choices = [
            (el[0], el[1]) for el in self.params["event"].get_elements(AbilityTypePx).values_list("id", "name")
        ]

        if not px_user:
            self.delete_field("requirements")
            self.delete_field("prerequisites")
            self.delete_field("visible")


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
