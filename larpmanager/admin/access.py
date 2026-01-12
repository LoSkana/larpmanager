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
"""Django admin configuration for access control models."""

from typing import ClassVar

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
    """Import/export resource for PermissionModule model."""

    class Meta:
        """Meta configuration for PermissionModule resource."""

        model = PermissionModule


@admin.register(PermissionModule)
class PermissionModuleAdmin(ImportExportModelAdmin):
    """Django admin for PermissionModule model."""

    resource_classes: ClassVar[list] = [PermissionModuleResource]
    list_display = ("name", "icon")
    search_fields: ClassVar[tuple] = ("id", "name")


@admin.register(AssociationRole)
class AssociationRoleAdmin(DefModelAdmin):
    """Django admin for AssociationRole model."""

    list_display = ("id", "name", "association", "number", "uuid")
    autocomplete_fields: ClassVar[list] = ["members", "association", "permissions"]
    search_fields: ClassVar[tuple] = ("id", "name", "uuid")


class AssociationPermissionResource(resources.ModelResource):
    """Import/export resource for AssociationPermission model."""

    class Meta:
        """Meta configuration for AssociationPermission resource."""

        model = AssociationPermission


@admin.register(AssociationPermission)
class AssociationPermissionAdmin(ImportExportModelAdmin):
    """Django admin for AssociationPermission model."""

    resource_classes: ClassVar[list] = [AssociationPermissionResource]
    list_display = ("id", "name", "slug", "number", "descr", "module", "feature")
    search_fields: ClassVar[tuple] = ("id", "name")
    autocomplete_fields: ClassVar[list] = ["feature", "module"]


@admin.register(EventRole)
class EventRoleAdmin(DefModelAdmin):
    """Django admin for EventRole model."""

    list_display = ("id", "name", "event", "number", "uuid")
    autocomplete_fields: ClassVar[list] = ["members", "event", "permissions"]
    search_fields: ClassVar[tuple] = ("id", "name", "uuid")


class EventPermissionResource(resources.ModelResource):
    """Import/export resource for EventPermission model."""

    class Meta:
        """Meta configuration for EventPermission resource."""

        model = EventPermission


@admin.register(EventPermission)
class EventPermissionAdmin(ImportExportModelAdmin):
    """Django admin for EventPermission model."""

    resource_classes: ClassVar[list] = [EventPermissionResource]
    autocomplete_fields: ClassVar[list] = ["feature", "module"]
    list_display = ("id", "name", "slug", "number", "descr", "module", "feature")
    search_fields: ClassVar[tuple] = ("id", "name")
