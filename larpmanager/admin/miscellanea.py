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

from larpmanager.admin.base import AssocFilter, DefModelAdmin, RunFilter, reduced
from larpmanager.admin.character import TargetFilter
from larpmanager.models.miscellanea import (
    Album,
    AlbumImage,
    AlbumUpload,
    ChatMessage,
    Contact,
    Email,
    HelpQuestion,
    InventoryArea,
    InventoryContainer,
    InventoryContainerAssignment,
    InventoryItem,
    InventoryItemAssignment,
    InventoryTag,
    PlayerRelationship,
    ShuttleService,
    Util,
    WorkshopMemberRel,
    WorkshopModule,
    WorkshopOption,
    WorkshopQuestion,
)


@admin.register(Contact)
class ContactAdmin(DefModelAdmin):
    list_display = ("me", "you", "channel")
    autocomplete_fields = ["me", "you", "assoc"]


@admin.register(ChatMessage)
class ChatMessageAdmin(DefModelAdmin):
    list_display = ("id", "sender", "receiver")
    autocomplete_fields = ("sender", "receiver", "assoc")


@admin.register(Album)
class AlbumAdmin(DefModelAdmin):
    list_display = ("name", "parent", "run", "show_thumb")
    autocomplete_fields = ["parent", "run", "assoc"]
    search_fields = ["name"]


@admin.register(AlbumImage)
class AlbumImageAdmin(DefModelAdmin):
    list_display = ("upload", "show_thumb", "width", "height")


@admin.register(AlbumUpload)
class AlbumUploadAdmin(DefModelAdmin):
    list_display = ("id", "album")
    autocomplete_fields = ["album"]


class WorkshopQuestionInline(admin.TabularInline):
    model = WorkshopQuestion
    exclude = ("search",)
    show_change_link = True


@admin.register(WorkshopModule)
class WorkshopModuleAdmin(DefModelAdmin):
    search_fields = ("search",)
    list_display = ("name", "event", "number", "is_generic")
    inlines = [
        WorkshopQuestionInline,
    ]
    autocomplete_fields = ["event", "members"]


class WorkshopModuleFilter(AutocompleteFilter):
    title = "WorkshopModule"
    field_name = "module"


class WorkshopOptionInline(admin.TabularInline):
    model = WorkshopOption
    exclude = ("search",)


@admin.register(WorkshopQuestion)
class WorkshopQuestionAdmin(DefModelAdmin):
    search_fields = ("search",)
    list_display = ("name", "number", "module")
    autocomplete_fields = ("module", "event")
    list_filter = (WorkshopModuleFilter,)
    inlines = [
        WorkshopOptionInline,
    ]


class WorkshopOptionFilter(AutocompleteFilter):
    title = "WorkshopQuestion"
    field_name = "question"


@admin.register(WorkshopOption)
class WorkshopOptionAdmin(DefModelAdmin):
    list_display = ("name", "question", "is_correct")
    autocomplete_fields = ("question",)
    list_filter = (WorkshopOptionFilter,)


@admin.register(WorkshopMemberRel)
class WorkshopMemberRelAdmin(DefModelAdmin):
    list_display = ("workshop", "member")


@admin.register(HelpQuestion)
class HelpQuestionAdmin(DefModelAdmin):
    list_display = ("member", "is_user", "small_text")
    autocomplete_fields = ["member", "run", "assoc"]


@admin.register(InventoryContainer)
class InventoryContainerAdmin(DefModelAdmin):
    list_display = ("name", "position")
    autocomplete_fields = ["assoc"]
    search_fields = ["name"]


@admin.register(InventoryTag)
class InventoryTagAdmin(DefModelAdmin):
    list_display = ("name", "description")
    search_fields = ["name"]


@admin.register(InventoryItem)
class InventoryItemAdmin(DefModelAdmin):
    list_display = ("name", "quantity", "container", "description")
    autocomplete_fields = ["assoc", "container", "tags"]
    search_fields = ["name"]


@admin.register(InventoryArea)
class InventoryAreaAdmin(DefModelAdmin):
    list_display = ("name", "position", "description")
    search_fields = ["name"]


@admin.register(InventoryItemAssignment)
class InventoryItemAssignmentAdmin(DefModelAdmin):
    list_display = ("area", "quantity", "item", "notes")
    autocomplete_fields = ["event", "item", "area"]


@admin.register(InventoryContainerAssignment)
class InventoryContainerAssignmentAdmin(DefModelAdmin):
    list_display = ("area", "container", "notes")
    autocomplete_fields = ["event", "container", "area"]


@admin.register(ShuttleService)
class ShuttleServiceAdmin(DefModelAdmin):
    list_display = ("member", "passengers", "address", "info", "working")
    autocomplete_fields = ["member", "working", "assoc"]


@admin.register(Util)
class UtilAdmin(DefModelAdmin):
    list_display = ("name", "cod", "event")
    autocomplete_fields = ["event"]


@admin.register(PlayerRelationship)
class PlayerRelationshipAdmin(DefModelAdmin):
    list_display = ("reg_red", "target", "text_red")
    list_filter = (TargetFilter,)
    autocomplete_fields = ["target", "reg"]

    @staticmethod
    def text_red(instance):
        return reduced(instance.text)

    @staticmethod
    def reg_red(instance):
        return f"{instance.reg} ({instance.reg.run.number})"


@admin.register(Email)
class EmailAdmin(DefModelAdmin):
    list_display = ("id", "assoc", "run", "recipient", "sent", "subj", "body_red")
    list_filter = (AssocFilter, RunFilter)
    autocomplete_fields = ["assoc", "run"]
    search_fields = ["subj", "body", "recipient"]

    @staticmethod
    def body_red(instance):
        return reduced(instance.body)
