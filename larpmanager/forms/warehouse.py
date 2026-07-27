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
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.forms import Textarea
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.warehouse import update_warehouse_item_cache
from larpmanager.forms.base import BaseModelForm
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


class ExeWarehouseItemForm(BaseModelForm):
    """Form for ExeWarehouseItem."""

    page_info = _("Manage all warehouse items, including their containers, tags, and quantities")

    page_title = _("Warehouse items")

    class Meta:
        model = WarehouseItem
        exclude: ClassVar[list] = []
        widgets: ClassVar[dict] = {
            "description": Textarea(attrs={"rows": 5}),
            "container": WarehouseContainerS2Widget,
            "tags": WarehouseTagS2WidgetMulti,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with association-specific widget configuration.

        Args:
            *args: Variable length argument list passed to parent constructor.
            **kwargs: Arbitrary keyword arguments passed to parent constructor.

        """
        # Initialize parent form
        super().__init__(*args, **kwargs)

        # Configure widgets with association ID for proper filtering
        self.configure_field_association("container", self.params.get("association_id"))
        self.configure_field_association("tags", self.params.get("association_id"))

        # Remove optional warehouse fields based on configuration
        _delete_optionals_warehouse(self)


class ExeWarehouseContainerForm(BaseModelForm):
    """Form for ExeWarehouseContainer."""

    page_info = _("Manage the physical containers used to organize and store warehouse items")

    page_title = _("Warehouse containers")

    class Meta:
        model = WarehouseContainer
        exclude: ClassVar[list] = []
        widgets: ClassVar[dict] = {"description": Textarea(attrs={"rows": 5})}


class ExeWarehouseTagForm(BaseModelForm):
    """Form for ExeWarehouseTag."""

    page_info = _("Manage tags used to categorize and group warehouse items")

    page_title = _("Warehouse tags")

    class Meta:
        model = WarehouseTag
        exclude: ClassVar[list] = []
        widgets: ClassVar[dict] = {
            "description": Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with warehouse items field for the association."""
        super().__init__(*args, **kwargs)

        # Create dynamic items field filtered by association
        self.fields["items"] = forms.ModelMultipleChoiceField(
            queryset=WarehouseItem.objects.filter(association_id=self.params.get("association_id")),
            label=_("Items"),
            widget=WarehouseItemS2WidgetMulti,
            required=False,
        )

        # Set initial selected items if editing existing instance
        if self.instance.pk:
            self.initial["items"] = self.instance.items.values_list("id", flat=True)

        # Configure widget with association context
        self.configure_field_association("items", self.params.get("association_id"))


class ExeWarehouseMovementForm(BaseModelForm):
    """Form for ExeWarehouseMovement."""

    page_info = _("Manage outgoing inventory movements excluded from event preparation")

    page_title = _("Warehouse movements")

    class Meta:
        model = WarehouseMovement
        exclude: ClassVar[list] = []
        widgets: ClassVar[dict] = {
            "notes": Textarea(attrs={"rows": 5}),
            "item": WarehouseItemS2Widget,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure warehouse item field for association."""
        super().__init__(*args, **kwargs)

        # Configure item widget with association ID
        self.configure_field_association("item", self.params.get("association_id"))

        # Remove optional warehouse fields
        _delete_optionals_warehouse(self)


class OrgaWarehouseAreaForm(BaseModelForm):
    """Form for OrgaWarehouseArea."""

    page_info = _("Manage the event areas where warehouse items will be deployed")

    page_title = _("Event area")

    class Meta:
        model = WarehouseArea
        exclude: ClassVar[list] = []
        widgets: ClassVar[dict] = {"description": Textarea(attrs={"rows": 5})}


class OrgaWarehouseItemAssignmentForm(BaseModelForm):
    """Form for OrgaWarehouseItemAssignment."""

    page_info = _("Select and assign warehouse items to this area, setting quantities and notes for each")

    page_title = _("Warehouse assignments")

    class Meta:
        model = WarehouseItemAssignment
        exclude: ClassVar[list] = []
        widgets: ClassVar[dict] = {
            "description": Textarea(attrs={"rows": 5}),
            "area": WarehouseAreaS2Widget,
            "item": WarehouseItemS2Widget,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure event/association-specific widget settings."""
        super().__init__(*args, **kwargs)

        # Configure widget event and association contexts
        self.configure_field_event("area", self.params.get("event"))
        self.configure_field_association("item", self.params.get("association_id"))

        _delete_optionals_warehouse(self)

    def clean(self) -> dict:
        """Validate form to prevent duplicate warehouse item assignments.

        Validates that the combination of area and item does not already exist
        in the database, excluding the current instance if editing an existing
        assignment.

        Returns:
            dict: The cleaned form data containing validated field values.

        Raises:
            ValidationError: If an assignment for the same item and area
                combination already exists in the database.

        """
        # Get cleaned data from parent validation
        cleaned = super().clean()

        # Extract area and item from cleaned data
        area = cleaned.get("area")
        item = cleaned.get("item")

        # Skip validation if either field is missing
        if not area or not item:
            return cleaned

        # Query for existing assignments with same area and item
        qs = WarehouseItemAssignment.objects.filter(
            area=area,
            item=item,
        )

        # Exclude current instance from query if editing existing assignment
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        # Raise validation error if duplicate assignment exists
        if qs.exists():
            raise ValidationError({"area": _("An assignment for this item and area already exists")})

        return cleaned


class OrgaWarehouseItemAreasForm(BaseModelForm):
    """Form to assign a single warehouse item to several areas of an event at once."""

    page_info = _("Assign this warehouse item to one or more areas of the event, setting a quantity for each")

    page_title = _("Item area assignments")

    load_templates: ClassVar[list] = ["warehouse-item"]

    class Meta:
        model = WarehouseItem
        fields: ClassVar[list] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Build the item field (new only) and one quantity field per event area."""
        super().__init__(*args, **kwargs)

        event = self.params.get("event")
        self.event = event
        association_id = self.params.get("association_id")
        editing = bool(self.instance and self.instance.pk)

        if editing:
            self.fields["item"] = forms.ModelChoiceField(
                queryset=WarehouseItem.objects.filter(pk=self.instance.pk),
                initial=self.instance.pk,
                widget=forms.HiddenInput,
                required=True,
            )
            assigned_total = (
                WarehouseItemAssignment.objects.filter(item=self.instance).aggregate(total=Sum("quantity"))["total"]
                or 0
            )
            self.warehouse_item = self.instance
            self.warehouse_item_total = self.instance.quantity
            self.warehouse_item_available = (
                max(self.instance.quantity - assigned_total, 0) if self.instance.quantity is not None else None
            )
        else:
            assigned_item_ids = WarehouseItemAssignment.objects.filter(area__event=event).values_list(
                "item_id",
                flat=True,
            )
            self.fields["item"] = forms.ModelChoiceField(
                queryset=WarehouseItem.objects.filter(association_id=association_id),
                label=_("Item"),
                widget=WarehouseItemS2Widget,
                required=True,
            )
            self.configure_field_association("item", association_id)
            self.fields["item"].widget.set_exclude_ids(list(assigned_item_ids))
            self.fields["item"].queryset = self.fields["item"].queryset.exclude(id__in=assigned_item_ids)

        existing_quantities = {}
        if editing:
            existing_quantities = {
                assignment.area_id: assignment.quantity
                for assignment in WarehouseItemAssignment.objects.filter(item=self.instance, event=event)
            }

        # Field names use the area's uuid
        self.area_fields: dict[str, int] = {}
        for area in event.get_elements(WarehouseArea).order_by("name"):
            field_name = f"area_{area.uuid}"
            self.area_fields[field_name] = area.id
            self.fields[field_name] = forms.IntegerField(
                label=area.name,
                required=False,
                min_value=0,
                initial=existing_quantities.get(area.id),
            )

    def _check_available_stock(self, item: WarehouseItem, current_event_total: int) -> None:
        """Raise ValidationError if current_event_total plus other events' assignments exceeds stock.

        Available stock is the item's total quantity minus whatever is already
        assigned to areas of other events (the item pool is shared association-wide).
        """
        if item.quantity is None:
            return

        other_events_total = (
            WarehouseItemAssignment.objects.filter(item=item)
            .exclude(event=self.event)
            .aggregate(total=Sum("quantity"))["total"]
            or 0
        )

        if other_events_total + current_event_total > item.quantity:
            available = max(item.quantity - other_events_total, 0)
            message = _("Total assigned quantity (%(total)s) exceeds available stock (%(available)s)") % {
                "total": current_event_total,
                "available": available,
            }
            raise ValidationError(message)

    def clean(self) -> dict:
        """Validate that total assigned quantity does not exceed available stock.

        Best-effort check for immediate user feedback; the authoritative check
        happens again under lock in save() to close the race between concurrent
        submissions for the same item across different events.
        """
        cleaned = super().clean()

        item = cleaned.get("item") or (self.instance if self.instance.pk else None)
        if not item:
            return cleaned

        current_event_total = sum(cleaned.get(field_name) or 0 for field_name in self.area_fields)
        try:
            self._check_available_stock(item, current_event_total)
        except ValidationError as error:
            # Attach to a visible area field: the generic edit template only
            # renders errors for form.visible_fields, so a plain non-field
            # ValidationError would never reach the user.
            self.add_error(next(iter(self.area_fields)), error)

        return cleaned

    def save(self, commit: bool = True) -> WarehouseItem:  # noqa: FBT001, FBT002, ARG002
        """Create, update or delete the WarehouseItemAssignment rows for this item/event."""
        item = self.cleaned_data.get("item") or self.instance

        with transaction.atomic():
            item = WarehouseItem.objects.select_for_update().get(pk=item.pk)

            # Re-validate under the lock, to avoid conflicting assignments another transaction
            current_event_total = sum(self.cleaned_data.get(field_name) or 0 for field_name in self.area_fields)
            self._check_available_stock(item, current_event_total)

            for field_name, area_id in self.area_fields.items():
                quantity = self.cleaned_data.get(field_name) or 0
                assignment = WarehouseItemAssignment.objects.filter(
                    item=item,
                    area_id=area_id,
                    event=self.event,
                ).first()

                if quantity <= 0:
                    if assignment:
                        assignment.delete()
                    continue

                if not assignment:
                    assignment = WarehouseItemAssignment(item=item, area_id=area_id, event=self.event)
                assignment.quantity = quantity
                assignment.save()

        update_warehouse_item_cache(item)
        self.instance = item
        return item


class OrgaWarehouseItemCommitRemainingForm(BaseModelForm):
    """Assign all currently available stock of one item to a selected event area."""

    page_info = _("Assign all remaining available stock of this item to an event area")

    page_title = _("Commit remaining warehouse stock")

    load_templates: ClassVar[list] = ["warehouse-item"]

    class Meta:
        model = WarehouseItemAssignment
        fields: ClassVar[list] = ["area"]
        widgets: ClassVar[dict] = {"area": WarehouseAreaS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Configure the fixed item details and event-area selector."""
        super().__init__(*args, **kwargs)
        self.item: WarehouseItem = self.params["commit_item"]
        self.event = self.params["event"]
        self.configure_field_event("area", self.event)
        self.warehouse_item = self.item
        self.warehouse_item_total = self.item.quantity
        self.warehouse_item_available = self._available_quantity()

    def _available_quantity(self, item: WarehouseItem | None = None) -> int:
        item = item or self.item
        assigned = WarehouseItemAssignment.objects.filter(item=item).aggregate(total=Sum("quantity"))["total"] or 0
        return max((item.quantity or 0) - assigned, 0)

    def clean(self) -> dict:
        """Ensure finite stock remains before showing the commit confirmation."""
        cleaned = super().clean()
        if self.item.quantity is None:
            self.add_error("area", _("This item has no finite quantity to commit"))
        elif self._available_quantity() <= 0:
            self.add_error("area", _("No quantity is available to commit"))
        return cleaned

    def save(self, commit: bool = True) -> WarehouseItemAssignment:  # noqa: FBT001, FBT002, ARG002
        """Add the remaining quantity to the selected area under the shared item lock."""
        with transaction.atomic():
            item = WarehouseItem.objects.select_for_update().get(pk=self.item.pk)
            quantity = self._available_quantity(item)
            if quantity <= 0:
                raise ValidationError(_("No quantity is available to commit"))

            assignment, _created = WarehouseItemAssignment.objects.get_or_create(
                item=item,
                area=self.cleaned_data["area"],
                event=self.event,
            )
            assignment.quantity = (assignment.quantity or 0) + quantity
            assignment.save()

        update_warehouse_item_cache(item)
        self.instance = assignment
        return assignment
