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

import background_task.admin
from admin_auto_filters.filters import AutocompleteFilter
from background_task.models import Task, CompletedTask
from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from larpmanager.models.base import FeatureModule, Feature, PaymentMethod
from larpmanager.models.member import Log


# SET JQUERY
class DefModelAdmin(ImportExportModelAdmin):
    class Media:
        css = {"all": ("larpmanager/assets/css/admin.css",)}

    ordering = ["-updated"]


def reduced(v):
    if not v or len(v) < 50:
        return v
    return v[:50] + "[...]"


class AssocFilter(AutocompleteFilter):
    title = "Association"
    field_name = "assoc"


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
    list_display = ("name", "descr", "order")
    search_fields = ["name"]


class FeatureResource(resources.ModelResource):
    class Meta:
        model = Feature


@admin.register(Feature)
class FeatureAdmin(DefModelAdmin):
    list_display = (
        "name",
        "overall",
        "module",
        "slug",
        "link",
        "tutorial",
        "descr",
        "placeholder",
    )
    list_filter = ("module",)
    autocomplete_fields = ["module", "associations", "events"]
    search_fields = ["name"]
    resource_classes = [FeatureResource]


@admin.register(PaymentMethod)
class PaymentMethodAdmin(DefModelAdmin):
    list_display = ("name", "slug")
    search_fields = ["name"]


# TASKS


def is_model_registered_with(model, admin_class):
    return model in admin.site._registry and isinstance(admin.site._registry[model], admin_class)


if is_model_registered_with(Task, background_task.admin.TaskAdmin):
    admin.site.unregister(Task)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("task_name", "short_params", "run_at", "attempts", "locked_by")

    def short_params(self, obj):
        return (obj.task_params[:400] + "...") if len(obj.task_params) > 400 else obj.task_params

    short_params.short_description = "Task Parameters"


if is_model_registered_with(CompletedTask, background_task.admin.CompletedTaskAdmin):
    admin.site.unregister(CompletedTask)


@admin.register(CompletedTask)
class CompletedTaskAdmin(admin.ModelAdmin):
    list_display = ("task_name", "short_params", "run_at", "attempts")

    def short_params(self, obj):
        return (obj.task_params[:400] + "...") if len(obj.task_params) > 400 else obj.task_params

    short_params.short_description = "Task Parameters"
