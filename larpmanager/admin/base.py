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

from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from tinymce.models import HTMLField

from larpmanager.forms.utils import CSRFTinyMCE
from larpmanager.models.base import Feature, FeatureModule, PaymentMethod
from larpmanager.models.miscellanea import Log


# SET JQUERY
class DefModelAdmin(ImportExportModelAdmin):
    """Base admin class for LarpManager models with import/export functionality."""

    class Media:
        css: ClassVar[dict] = {"all": ("larpmanager/assets/css/admin.css",)}

    ordering: ClassVar[list] = ["-updated"]

    def changelist_view(self, request: Any, extra_context: dict | None = None) -> Any:
        """Render the changelist, adding the assets required by autocomplete list filters."""
        response = super().changelist_view(request, extra_context)
        context = getattr(response, "context_data", None)
        if context and "cl" in context:
            for spec in context["cl"].filter_specs:
                if isinstance(spec, AutocompleteFilter):
                    context["media"] += spec.media
        return response


class AutocompleteFilter(admin.SimpleListFilter):
    """List filter on a foreign key, rendered as an admin autocomplete select.

    Subclasses set `title` and `field_name`; the related model admin must define `search_fields`.
    """

    template = "admin/autocomplete_filter.html"
    field_name = ""

    def __init__(self, request: Any, params: dict, model: Any, model_admin: Any) -> None:
        """Build the autocomplete widget for the filtered foreign key."""
        self.parameter_name = f"{self.field_name}__pk__exact"
        super().__init__(request, params, model, model_admin)

        field = model._meta.get_field(self.field_name)  # noqa: SLF001
        form_field = forms.ModelChoiceField(
            queryset=field.remote_field.model._default_manager.all(),  # noqa: SLF001
            widget=AutocompleteSelect(field, model_admin.admin_site),
            required=False,
        )
        self.media = form_field.widget.media + forms.Media(js=("larpmanager/assets/js/admin-autocomplete-filter.js",))
        self.rendered_widget = form_field.widget.render(
            name=self.parameter_name,
            value=self.value() or "",
            attrs={"id": f"id-{self.parameter_name}-filter"},
        )

    def has_output(self) -> bool:
        """Always show the filter, as its choices are loaded on demand."""
        return True

    def lookups(self, request: Any, model_admin: Any) -> tuple:  # noqa: ARG002
        """Return no static choices; the widget queries the admin autocomplete view."""
        return ()

    def queryset(self, request: Any, queryset: Any) -> Any:  # noqa: ARG002
        """Filter the queryset by the selected related object."""
        if self.value():
            return queryset.filter(**{self.parameter_name: self.value()})
        return queryset


class CSRFTinyMCEModelAdmin(DefModelAdmin):
    """Base admin class that uses CSRF-aware TinyMCE for all HTMLField fields.

    This automatically applies CSRFTinyMCE widget to any HTMLField in the model,
    ensuring proper CSRF token handling for file uploads in TinyMCE editors.

    Use this as the base class for any ModelAdmin that has HTMLField fields.
    """

    def formfield_for_dbfield(self, db_field: Any, request: Any, **kwargs: Any) -> Any:
        """Override formfield to use CSRFTinyMCE for HTMLField fields."""
        # Use CSRFTinyMCE for all HTMLField (TinyMCE) fields
        if isinstance(db_field, HTMLField):
            kwargs["widget"] = CSRFTinyMCE()
            return db_field.formfield(**kwargs)
        return super().formfield_for_dbfield(db_field, request, **kwargs)


def reduced(value: str | None) -> str:
    """Truncate string to maximum length with ellipsis."""
    # Define maximum allowed length before truncation
    max_length = 50

    # Return early if string is None, empty, or under limit
    if not value or len(value) < max_length:
        return value

    # Truncate and append ellipsis indicator
    return value[:max_length] + "[...]"


class AssociationFilter(AutocompleteFilter):
    """Admin filter for Association autocomplete."""

    title = "Association"
    field_name = "association"


class CharacterFilter(AutocompleteFilter):
    """Admin filter for Character autocomplete."""

    title = "Character"
    field_name = "character"


class EventFilter(AutocompleteFilter):
    """Admin filter for Event autocomplete."""

    title = "Event"
    field_name = "event"


class RunFilter(AutocompleteFilter):
    """Admin filter for Run autocomplete."""

    title = "Run"
    field_name = "run"


class MemberFilter(AutocompleteFilter):
    """Admin filter for Member autocomplete."""

    title = "Member"
    field_name = "member"


class TraitFilter(AutocompleteFilter):
    """Admin filter for Trait autocomplete."""

    title = "Trait"
    field_name = "trait"


class RegistrationFilter(AutocompleteFilter):
    """Admin filter for Registration autocomplete."""

    title = "Registration"
    field_name = "registration"


@admin.register(Log)
class LogAdmin(DefModelAdmin):
    """Admin interface for Log model."""

    list_display: ClassVar[tuple] = ("member", "cls", "eid", "operation_type", "element_name", "info")
    search_fields: ClassVar[tuple] = ("id", "member__name", "member__surname", "cls", "operation_type", "element_name")
    list_filter: ClassVar[tuple] = ("operation_type", MemberFilter, RunFilter, AssociationFilter)
    autocomplete_fields: ClassVar[list] = ["member"]


@admin.register(FeatureModule)
class FeatureModuleAdmin(DefModelAdmin):
    """Admin interface for FeatureModule model."""

    list_display = ("name", "order")
    search_fields: ClassVar[list] = ["id", "name"]


class FeatureResource(resources.ModelResource):
    """Import/export resource for Feature model."""

    class Meta:
        model = Feature


@admin.register(Feature)
class FeatureAdmin(DefModelAdmin):
    """Admin interface for Feature model."""

    list_display: ClassVar[tuple] = (
        "name",
        "overall",
        "order",
        "module",
        "slug",
        "tutorial",
        "descr",
        "placeholder",
        "after_link",
    )
    list_filter: ClassVar[tuple] = ("module",)
    autocomplete_fields: ClassVar[list] = ["module", "associations", "events"]
    search_fields: ClassVar[list] = ["id", "name"]
    resource_classes: ClassVar[list] = [FeatureResource]


@admin.register(PaymentMethod)
class PaymentMethodAdmin(CSRFTinyMCEModelAdmin):
    """Admin interface for PaymentMethod model."""

    list_display = ("name", "slug")
    search_fields: ClassVar[list] = ["id", "name"]
