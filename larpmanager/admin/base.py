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

from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from tinymce.models import HTMLField

from larpmanager.forms.utils import CSRFTinyMCE
from larpmanager.models.base import Feature, FeatureModule, PaymentMethod
from larpmanager.models.member import Log


# SET JQUERY
class DefModelAdmin(ImportExportModelAdmin):
    """Base admin class for LarpManager models with import/export functionality."""

    class Media:
        css: ClassVar[dict] = {"all": ("larpmanager/assets/css/admin.css",)}

    ordering: ClassVar[list] = ["-updated"]


class CSRFTinyMCEModelAdmin(DefModelAdmin):
    """Base admin class that uses CSRF-aware TinyMCE for all HTMLField fields.

    This automatically applies CSRFTinyMCE widget to any HTMLField in the model,
    ensuring proper CSRF token handling for file uploads in TinyMCE editors.

    Use this as the base class for any ModelAdmin that has HTMLField fields.
    """

    def formfield_for_dbfield(self, db_field: Any, request: Any, **kwargs: Any) -> Any:
        """Override formfield to use CSRFTinyMCE for HTMLField fields.

        Args:
            db_field: Database field being rendered
            request: HTTP request object
            **kwargs: Additional keyword arguments

        Returns:
            Form field with CSRFTinyMCE widget for HTMLField, default otherwise

        """
        # Use CSRFTinyMCE for all HTMLField (TinyMCE) fields
        if isinstance(db_field, HTMLField):
            kwargs["widget"] = CSRFTinyMCE()
            return db_field.formfield(**kwargs)
        return super().formfield_for_dbfield(db_field, request, **kwargs)


def reduced(value: str | None) -> str:
    """Truncate string to maximum length with ellipsis.

    Truncates the input string to a maximum of 50 characters. If the string
    is longer than the limit, it's cut off and "[...]" is appended to indicate
    truncation.

    Args:
        value: String to potentially truncate. Can be None or empty.

    Returns:
        Original string if under 50 chars, otherwise truncated with [...] suffix.
        Returns empty string or None as-is if input is falsy.

    Examples:
        >>> reduced("short")
        'short'
        >>> reduced("a" * 60)
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa[...]'
        >>> reduced(None)
        None

    """
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

    list_display: ClassVar[tuple] = ("member", "cls", "eid", "dl")
    search_fields: ClassVar[tuple] = ("id", "member", "cls", "dl")
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
class PaymentMethodAdmin(DefModelAdmin):
    """Admin interface for PaymentMethod model."""

    list_display = ("name", "slug")
    search_fields: ClassVar[list] = ["id", "name"]
