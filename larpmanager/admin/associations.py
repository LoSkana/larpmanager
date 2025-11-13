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

from typing import ClassVar

from django.contrib import admin

from larpmanager.admin.base import AssociationFilter, DefModelAdmin
from larpmanager.models.association import (
    Association,
    AssociationConfig,
    AssociationSkin,
    AssociationText,
    AssociationTranslation,
)


@admin.register(Association)
class AssociationAdmin(DefModelAdmin):
    list_display = ("name", "slug", "created")
    search_fields: ClassVar[tuple] = ("name",)

    autocomplete_fields: ClassVar[list] = ["payment_methods", "features", "maintainers"]


@admin.register(AssociationConfig)
class AssociationConfigAdmin(DefModelAdmin):
    list_display = ("association", "name", "value")
    search_fields: ClassVar[tuple] = ("name",)
    list_filter = (AssociationFilter,)
    autocomplete_fields: ClassVar[list] = ["association"]


@admin.register(AssociationText)
class AssociationTextAdmin(DefModelAdmin):
    list_display: ClassVar[tuple] = ("association", "typ", "language", "default")
    list_filter = (AssociationFilter, "typ", "language")
    autocomplete_fields: ClassVar[list] = ["association"]


@admin.register(AssociationTranslation)
class AssociationTranslationAdmin(DefModelAdmin):
    """Django admin interface for managing association-specific translation overrides.

    Provides a user-friendly interface for administrators to create and manage
    custom translations that override the default Django i18n strings on a
    per-organization basis. The list view includes preview columns that truncate
    long text for better readability, and allows quick activation/deactivation.
    """

    list_display = ("association", "language", "msgid_preview", "msgstr_preview", "active")
    list_filter: ClassVar[tuple] = (AssociationFilter, "language", "active")
    search_fields = ("msgid", "msgstr")
    autocomplete_fields: ClassVar[list] = ["association"]
    list_editable = ("active",)

    def msgid_preview(self, obj: AssociationTranslation) -> str:
        """Display a truncated preview of the original text for list view.

        Args:
            obj: The AssociationTranslation instance

        Returns:
            The original text truncated to 50 characters with ellipsis if needed

        """
        max_length = 50
        return obj.msgid[:max_length] + "..." if len(obj.msgid) > max_length else obj.msgid

    msgid_preview.short_description = "Original text"

    def msgstr_preview(self, obj: AssociationTranslation) -> str:
        """Display a truncated preview of the translated text for list view.

        Args:
            obj: The AssociationTranslation instance

        Returns:
            The translated text truncated to 50 characters with ellipsis if needed

        """
        max_length = 50
        return obj.msgstr[:max_length] + "..." if len(obj.msgstr) > max_length else obj.msgstr

    msgstr_preview.short_description = "Translation"


@admin.register(AssociationSkin)
class AssociationSkinAdmin(DefModelAdmin):
    list_display = ("name",)
    search_fields: ClassVar[tuple] = ("name",)

    autocomplete_fields: ClassVar[list] = [
        "default_features",
    ]
