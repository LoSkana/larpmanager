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

from datetime import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.forms import Textarea
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.base import MyForm
from larpmanager.forms.miscellanea import _delete_optionals_inventory
from larpmanager.forms.utils import (
    InventoryAreaS2Widget,
    InventoryContainerS2Widget,
    InventoryItemS2Widget,
    InventoryItemS2WidgetMulti,
    InventoryTagS2WidgetMulti,
)
from larpmanager.models.association import Association
from larpmanager.models.miscellanea import (
    InventoryArea,
    InventoryContainer,
    InventoryItem,
    InventoryItemAssignment,
    InventoryMovement,
    InventoryTag,
)
from larpmanager.utils.miscellanea import get_inventory_optionals


class ExeInventoryItemForm(MyForm):
    page_info = _("This page allows you to add or edit a new item of inventory")

    page_title = _("Inventory items")

    class Meta:
        model = InventoryItem
        exclude = []
        widgets = {
            "description": Textarea(attrs={"rows": 5}),
            "container": InventoryContainerS2Widget,
            "tags": InventoryTagS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["container"].widget.set_assoc(self.params["a_id"])
        self.fields["tags"].widget.set_assoc(self.params["a_id"])

        _delete_optionals_inventory(self)


class ExeInventoryContainerForm(MyForm):
    page_info = _("This page allows you to add or edit a new container of inventory")

    page_title = _("Inventory containers")

    class Meta:
        model = InventoryContainer
        exclude = []
        widgets = {"description": Textarea(attrs={"rows": 5})}


class ExeInventoryTagForm(MyForm):
    page_info = _("This page allows you to add or edit a new tag for inventory items")

    page_title = _("Inventory tags")

    class Meta:
        model = InventoryTag
        exclude = []
        widgets = {
            "description": Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["items"] = forms.ModelMultipleChoiceField(
            queryset=InventoryItem.objects.filter(assoc_id=self.params["a_id"]),
            label=_("Items"),
            widget=InventoryItemS2WidgetMulti,
            required=False,
        )
        if self.instance.pk:
            self.initial["items"] = self.instance.items.values_list("pk", flat=True)
        self.fields["items"].widget.set_assoc(self.params["a_id"])


class ExeInventoryMovementForm(MyForm):
    page_info = _("This page allows you to add or edit a new movement of item inventory, loans or repairs")

    page_title = _("Inventory movements")

    class Meta:
        model = InventoryMovement
        exclude = []
        widgets = {
            "notes": Textarea(attrs={"rows": 5}),
            "item": InventoryItemS2Widget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].widget.set_assoc(self.params["a_id"])

        _delete_optionals_inventory(self)


class OrgaInventoryAreaForm(MyForm):
    page_info = _("This page allows you to add or edit a new event area")

    page_title = _("Event area")

    load_form = ["area-assignments"]

    load_js = ["area-assignments"]

    class Meta:
        model = InventoryArea
        exclude = []
        widgets = {"description": Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.item_all = {}
        self.container_all = {}
        self.assigned = {}
        self.separate_handling = []

        self.prepare()

        self.handle_items()

        if self.inventory_container_manifest:
            self.handle_containers()

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if not instance.pk:
            instance.save()

        self.save_items(instance)
        if self.inventory_container_manifest:
            self.save_containers(instance)

        return instance

    def prepare(self):
        ctx = {"a_id": self.params["request"].assoc["id"]}
        get_inventory_optionals(ctx, [4, 5])
        self.optionals = ctx["optionals"]
        self.no_header_cols = [4, 5]
        if self.optionals["quantity"]:
            self.no_header_cols = [6, 7]
        assoc = Association.objects.get(pk=self.params["request"].assoc["id"])
        self.inventory_container_manifest = assoc.get_config("inventory_container_manifest", True)

    ### ITEMS

    def item_fields(self, item):
        assigned_data = getattr(item, "assigned", {})

        # selected checkbox
        sel_field = f"sel_itm_{item.id}"
        item.selected = bool(assigned_data)
        self.fields[sel_field] = forms.BooleanField(
            required=False,
            initial=item.selected,
        )
        self.separate_handling.append("id_" + sel_field)

        # quantity
        qty_field = f"qty_itm_{item.id}"
        item.quantity_assigned = assigned_data.get("quantity", 0)
        self.fields[qty_field] = forms.IntegerField(
            required=False,
            initial=item.quantity_assigned,
            min_value=min(0, item.available),
            max_value=max(0, item.available),
        )
        self.separate_handling.append("id_" + qty_field)

        # notes
        notes_field = f"notes_itm_{item.id}"
        self.fields[notes_field] = forms.CharField(
            required=False,
            initial=assigned_data.get("notes", ""),
            widget=forms.Textarea(attrs={"rows": 2, "cols": 10}),
        )
        self.separate_handling.append("id_" + notes_field)

    def get_all_items(self):
        for item in InventoryItem.objects.filter(assoc_id=self.params["a_id"]).prefetch_related("tags"):
            item.available = item.quantity or 0
            self.item_all[item.id] = item

        for el in self.params["event"].get_elements(InventoryItemAssignment).filter(event=self.params["event"]):
            item = self.item_all[el.item_id]
            if el.area_id == self.instance.pk:
                item.assigned = {"quantity": el.quantity, "notes": el.notes}
            else:
                item.available -= el.quantity or 0

    def sort_items(self):
        def _assigned_updated(it):
            if getattr(it, "assigned", None):
                return it.assigned.get("updated") or getattr(it, "updated", None) or datetime.min
            return datetime.min

        # items with assigned first; among them, most recently updated first; then by name, then id
        ordered_items = sorted(
            self.item_all.values(),
            key=lambda it: (
                bool(getattr(it, "assigned", None)),  # True first via reverse
                _assigned_updated(it),  # recent first via reverse
                getattr(it, "name", ""),  # alphabetical fallback
                it.id,  # stable tiebreaker
            ),
            reverse=True,
        )

        # rebuild dict preserving the sorted order
        self.item_all = {it.id: it for it in ordered_items}

    def handle_items(self):
        self.get_all_items()

        self.sort_items()

        for item in self.item_all.values():
            self.item_fields(item)

    def save_items(self, instance):
        to_del = []
        for item_id, _item in self.item_all.items():
            sel = self.cleaned_data.get(f"sel_itm_{item_id}", False)

            if not sel:
                to_del.append(item_id)
                continue

            assignment, created = InventoryItemAssignment.objects.get_or_create(
                area=instance, item_id=item_id, event=instance.event
            )
            assignment.quantity = self.cleaned_data.get(f"qty_itm_{item_id}", 0) or 0
            assignment.notes = self.cleaned_data.get(f"notes_itm_{item_id}", "").strip()

            assignment.save()

        InventoryItemAssignment.objects.filter(area=instance, item_id__in=to_del, event=instance.event).delete()


class OrgaInventoryItemAssignmentForm(MyForm):
    page_info = _("This page allows you to add or edit a new assignment of inventory item to event area")

    page_title = _("Inventory assignments")

    class Meta:
        model = InventoryItemAssignment
        exclude = []
        widgets = {
            "description": Textarea(attrs={"rows": 5}),
            "area": InventoryAreaS2Widget,
            "item": InventoryItemS2Widget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["area"].widget.set_event(self.params["event"])
        self.fields["item"].widget.set_assoc(self.params["a_id"])

        _delete_optionals_inventory(self)

    def clean(self):
        cleaned = super().clean()
        area = cleaned.get("area")
        item = cleaned.get("item")
        if not area or not item:
            return cleaned

        qs = InventoryItemAssignment.objects.filter(
            area=area,
            item=item,
        )
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError({"area": _("An assignment for this item and area already exists")})

        return cleaned
