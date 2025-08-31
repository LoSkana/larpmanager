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
from django.core.exceptions import ValidationError
from django.forms import Textarea
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.base import MyForm
from larpmanager.forms.miscellanea import _delete_optionals_warehouse
from larpmanager.forms.utils import (
    WarehouseAreaS2Widget,
    WarehouseContainerS2Widget,
    WarehouseItemS2Widget,
    WarehouseItemS2WidgetMulti,
    WarehouseTagS2WidgetMulti,
)
from larpmanager.models.miscellanea import (
    WarehouseArea,
    WarehouseContainer,
    WarehouseItem,
    WarehouseItemAssignment,
    WarehouseMovement,
    WarehouseTag,
)


class ExeWarehouseItemForm(MyForm):
    page_info = _("This page allows you to add or edit a new item of inventory")

    page_title = _("Warehouse items")

    class Meta:
        model = WarehouseItem
        exclude = []
        widgets = {
            "description": Textarea(attrs={"rows": 5}),
            "container": WarehouseContainerS2Widget,
            "tags": WarehouseTagS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["container"].widget.set_assoc(self.params["a_id"])
        self.fields["tags"].widget.set_assoc(self.params["a_id"])

        _delete_optionals_warehouse(self)


class ExeWarehouseContainerForm(MyForm):
    page_info = _("This page allows you to add or edit a new container of inventory")

    page_title = _("Warehouse containers")

    class Meta:
        model = WarehouseContainer
        exclude = []
        widgets = {"description": Textarea(attrs={"rows": 5})}


class ExeWarehouseTagForm(MyForm):
    page_info = _("This page allows you to add or edit a new tag for inventory items")

    page_title = _("Warehouse tags")

    class Meta:
        model = WarehouseTag
        exclude = []
        widgets = {
            "description": Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["items"] = forms.ModelMultipleChoiceField(
            queryset=WarehouseItem.objects.filter(assoc_id=self.params["a_id"]),
            label=_("Items"),
            widget=WarehouseItemS2WidgetMulti,
            required=False,
        )
        if self.instance.pk:
            self.initial["items"] = self.instance.items.values_list("pk", flat=True)
        self.fields["items"].widget.set_assoc(self.params["a_id"])


class ExeWarehouseMovementForm(MyForm):
    page_info = _("This page allows you to add or edit a new movement of item inventory, loans or repairs")

    page_title = _("Warehouse movements")

    class Meta:
        model = WarehouseMovement
        exclude = []
        widgets = {
            "notes": Textarea(attrs={"rows": 5}),
            "item": WarehouseItemS2Widget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].widget.set_assoc(self.params["a_id"])

        _delete_optionals_warehouse(self)


class OrgaWarehouseAreaForm(MyForm):
    page_info = _("This page allows you to add or edit a new event area")

    page_title = _("Event area")

    class Meta:
        model = WarehouseArea
        exclude = []
        widgets = {"description": Textarea(attrs={"rows": 5})}


class OrgaWarehouseItemAssignmentForm(MyForm):
    page_info = _("This page allows you to add or edit a new assignment of inventory item to event area")

    page_title = _("Warehouse assignments")

    class Meta:
        model = WarehouseItemAssignment
        exclude = []
        widgets = {
            "description": Textarea(attrs={"rows": 5}),
            "area": WarehouseAreaS2Widget,
            "item": WarehouseItemS2Widget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["area"].widget.set_event(self.params["event"])
        self.fields["item"].widget.set_assoc(self.params["a_id"])

        _delete_optionals_warehouse(self)

    def clean(self):
        cleaned = super().clean()
        area = cleaned.get("area")
        item = cleaned.get("item")
        if not area or not item:
            return cleaned

        qs = WarehouseItemAssignment.objects.filter(
            area=area,
            item=item,
        )
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError({"area": _("An assignment for this item and area already exists")})

        return cleaned
