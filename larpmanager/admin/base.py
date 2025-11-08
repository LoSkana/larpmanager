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

from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from larpmanager.models.base import Feature, FeatureModule, PaymentMethod
from larpmanager.models.member import Log


# SET JQUERY
class DefModelAdmin(ImportExportModelAdmin):
    class Media:
        css = {"all": ("larpmanager/assets/css/admin.css",)}

    ordering = ["-updated"]


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
    title = "Association"
    field_name = "association"


class CharacterFilter(AutocompleteFilter):
    title = "Character"
    field_name = "character"


class EventFilter(AutocompleteFilter):
    title = "Event"
    field_name = "event"


class RunFilter(AutocompleteFilter):
    title = "Run"
    field_name = "run"


class MemberFilter(AutocompleteFilter):
    title = "Member"
    field_name = "member"


class TraitFilter(AutocompleteFilter):
    title = "Trait"
    field_name = "trait"


class RegistrationFilter(AutocompleteFilter):
    title = "Registration"
    field_name = "reg"


@admin.register(Log)
class LogAdmin(DefModelAdmin):
    list_display = ("member", "cls", "eid", "created", "dl")
    search_fields = ("member", "cls", "dl")
    autocomplete_fields = ["member"]


@admin.register(FeatureModule)
class FeatureModuleAdmin(DefModelAdmin):
    list_display = ("name", "order")
    search_fields = ["name"]


class FeatureResource(resources.ModelResource):
    class Meta:
        model = Feature


@admin.register(Feature)
class FeatureAdmin(DefModelAdmin):
    list_display = ("name", "overall", "order", "module", "slug", "tutorial", "descr", "placeholder", "after_link")
    list_filter = ("module",)
    autocomplete_fields = ["module", "associations", "events"]
    search_fields = ["name"]
    resource_classes = [FeatureResource]


@admin.register(PaymentMethod)
class PaymentMethodAdmin(DefModelAdmin):
    list_display = ("name", "slug")
    search_fields = ["name"]
