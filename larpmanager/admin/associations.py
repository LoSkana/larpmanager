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

from django.contrib import admin

from larpmanager.admin.base import AssociationFilter, DefModelAdmin
from larpmanager.models.association import Association, AssociationConfig, AssociationSkin, AssociationText


@admin.register(Association)
class AssociationAdmin(DefModelAdmin):
    list_display = ("name", "slug", "created")
    search_fields = ("name",)

    autocomplete_fields = [
        "payment_methods",
        "features",
    ]


@admin.register(AssociationConfig)
class AssociationConfigAdmin(DefModelAdmin):
    list_display = ("association", "name", "value")
    search_fields = ("name",)
    list_filter = (AssociationFilter,)
    autocomplete_fields = ["association"]


@admin.register(AssociationText)
class AssociationTextAdmin(DefModelAdmin):
    list_display = ("association", "typ", "language", "default")
    list_filter = (AssociationFilter, "typ", "language")
    autocomplete_fields = ["association"]


@admin.register(AssociationSkin)
class AssociationSkinAdmin(DefModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

    autocomplete_fields = [
        "default_features",
    ]
