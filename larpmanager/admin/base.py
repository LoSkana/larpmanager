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

from typing import TYPE_CHECKING, Any, ClassVar

from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from tinymce.models import HTMLField

from larpmanager.forms.utils import CSRFTinyMCE
from larpmanager.models.base import Feature, FeatureModule, PaymentMethod
from larpmanager.models.member import Log

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


class DefModelAdmin(ImportExportModelAdmin):
    """Base admin class for LarpManager models with import/export and association filtering.

    For non-superuser users, this admin class:
    1. Checks if the user is a maintainer of any associations
    2. Filters the queryset to only show objects from their authorized associations
    3. Detects the association relationship field automatically:
       - Direct: association
       - Through event: event__association
       - Through run: run__event__association
    4. Denies access if the model has no association relationship

    For models without association relationships (global models), the filtering is bypassed
    for superusers only.
    """

    class Media:
        css: ClassVar[dict] = {"all": ("larpmanager/assets/css/admin.css",)}

    ordering: ClassVar[list] = ["-updated"]

    def _get_association_field(self) -> str | None:
        """Detect which association-related field exists in the model."""
        model_fields = {f.name for f in self.model._meta.get_fields()}  # noqa: SLF001

        # Check in priority order
        for field in ("association", "event", "run"):
            if field in model_fields:
                return field

        return None

    def _is_user_maintainer(self, request: HttpRequest) -> bool:
        """Check if user is a maintainer of any association."""
        return hasattr(request.user, "member") and request.user.member.maintained_associations.exists()

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Filter queryset based on user's association access.

        Args:
            request: HTTP request object

        Returns:
            Filtered queryset containing only objects the user can access

        """
        qs = super().get_queryset(request)

        # Superusers see everything
        if request.user.is_superuser:
            return qs

        # Non-maintainers see nothing
        if not self._is_user_maintainer(request):
            return qs.none()

        # Get association IDs
        association_ids = list(request.user.member.maintained_associations.values_list("id", flat=True))

        # Filter based on detected field
        association_field = self._get_association_field()

        if association_field == "association":
            return qs.filter(association_id__in=association_ids)
        if association_field == "event":
            return qs.filter(event__association_id__in=association_ids)
        if association_field == "run":
            return qs.filter(run__event__association_id__in=association_ids)

        # No association relationship found - deny access
        return qs.none()

    def has_module_permission(self, request: HttpRequest) -> bool:
        """Determine if user can see this admin module.

        Args:
            request: HTTP request object

        Returns:
            True if user has permission to see this module

        """
        # Superusers always have permission
        if request.user.is_superuser:
            return super().has_module_permission(request)

        # Only maintainers with association-related models can access
        if not self._is_user_maintainer(request):
            return False

        # Model must have association relationship
        if not self._get_association_field():
            return False

        return super().has_module_permission(request)


class CSRFTinyMCEModelAdmin(DefModelAdmin):
    """Admin class with CSRF-aware TinyMCE and association filtering.

    This class provides:
    - Association filtering: Filters queryset based on user's maintained associations
    - CSRF-aware TinyMCE: Proper CSRF token handling for file uploads in TinyMCE editors

    Use this as the base class for any ModelAdmin that:
    1. Has HTMLField fields requiring TinyMCE editor
    2. Has an association relationship (association, event__association, or run__event__association)

    For models with HTMLField but NO association relationship (rare cases like global settings),
    you can override get_queryset() to bypass filtering or create a custom admin class.
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
    field_name = "reg"


@admin.register(Log)
class LogAdmin(DefModelAdmin):
    """Admin interface for Log model."""

    list_display: ClassVar[tuple] = ("member", "cls", "eid", "created", "dl")
    search_fields = ("member", "cls", "dl")
    autocomplete_fields: ClassVar[list] = ["member"]


@admin.register(FeatureModule)
class FeatureModuleAdmin(DefModelAdmin):
    """Admin interface for FeatureModule model."""

    list_display = ("name", "order")
    search_fields: ClassVar[list] = ["name"]


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
    search_fields: ClassVar[list] = ["name"]
    resource_classes: ClassVar[list] = [FeatureResource]


@admin.register(PaymentMethod)
class PaymentMethodAdmin(DefModelAdmin):
    """Admin interface for PaymentMethod model."""

    list_display = ("name", "slug")
    search_fields: ClassVar[list] = ["name"]
