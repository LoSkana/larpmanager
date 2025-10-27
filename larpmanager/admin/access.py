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
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from larpmanager.admin.base import DefModelAdmin
from larpmanager.models.access import (
    AssociationPermission,
    AssociationRole,
    EventPermission,
    EventRole,
    PermissionModule,
)


class PermissionModuleResource(resources.ModelResource):
    class Meta:
        model = PermissionModule


@admin.register(PermissionModule)
class PermissionModuleAdmin(ImportExportModelAdmin):
    resource_classes = [PermissionModuleResource]
    list_display = ("name", "icon")
    search_fields = ("name",)


@admin.register(AssociationRole)
class AssocRoleAdmin(DefModelAdmin):
    list_display = ("name", "association", "number")
    autocomplete_fields = ["members", "association", "permissions"]
    search_fields = ("name",)


class AssocPermissionResource(resources.ModelResource):
    class Meta:
        model = AssociationPermission


@admin.register(AssociationPermission)
class AssocPermissionAdmin(ImportExportModelAdmin):
    resource_classes = [AssocPermissionResource]
    list_display = ("name", "slug", "number", "descr", "module", "feature")
    search_fields = ("name",)
    autocomplete_fields = ["feature", "module"]


@admin.register(EventRole)
class EventRoleAdmin(DefModelAdmin):
    list_display = ("name", "event", "number")
    autocomplete_fields = ["members", "event", "permissions"]
    search_fields = ("name",)


class EventPermissionResource(resources.ModelResource):
    class Meta:
        model = EventPermission


@admin.register(EventPermission)
class EventPermissionAdmin(ImportExportModelAdmin):
    resource_classes = [EventPermissionResource]
    autocomplete_fields = ["feature", "module"]
    list_display = ("name", "slug", "number", "descr", "module", "feature")
    search_fields = ("name",)
