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
    OneTimeAccessToken,
    OneTimeContent,
    PlayerRelationship,
    ShuttleService,
    Util,
    WarehouseArea,
    WarehouseContainer,
    WarehouseItem,
    WarehouseItemAssignment,
    WarehouseTag,
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


@admin.register(WarehouseContainer)
class WarehouseContainerAdmin(DefModelAdmin):
    list_display = ("name", "position")
    autocomplete_fields = ["assoc"]
    search_fields = ["name"]


@admin.register(WarehouseTag)
class WarehouseTagAdmin(DefModelAdmin):
    list_display = ("name", "description")
    search_fields = ["name"]


@admin.register(WarehouseItem)
class WarehouseItemAdmin(DefModelAdmin):
    list_display = ("name", "quantity", "container", "description")
    autocomplete_fields = ["assoc", "container", "tags"]
    search_fields = ["name"]


@admin.register(WarehouseArea)
class WarehouseAreaAdmin(DefModelAdmin):
    list_display = ("name", "position", "description")
    search_fields = ["name"]


@admin.register(WarehouseItemAssignment)
class WarehouseItemAssignmentAdmin(DefModelAdmin):
    list_display = ("area", "quantity", "item", "notes")
    autocomplete_fields = ["event", "item", "area"]


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


class OneTimeAccessTokenInline(admin.TabularInline):
    """Inline admin for access tokens."""

    model = OneTimeAccessToken
    extra = 0
    readonly_fields = ("token", "used", "used_at", "used_by", "ip_address", "user_agent", "created")
    fields = ("note", "token", "used", "used_at", "used_by", "ip_address")
    can_delete = True

    def has_add_permission(self, request, obj=None):
        return True


@admin.register(OneTimeContent)
class OneTimeContentAdmin(DefModelAdmin):
    """Admin interface for OneTimeContent."""

    list_display = (
        "name",
        "event",
        "file_display",
        "content_type",
        "file_size_display",
        "token_count",
        "active",
        "created",
    )
    list_filter = ("event", "active", "created")
    search_fields = ("name", "description", "event__name")
    readonly_fields = ("content_type", "file_size", "created", "updated")
    inlines = [OneTimeAccessTokenInline]
    autocomplete_fields = ["event"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "event",
                    "name",
                    "description",
                    "file",
                    "active",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("content_type", "file_size", "duration", "created", "updated"),
                "classes": ("collapse",),
            },
        ),
    )

    def file_display(self, obj):
        """Display file name."""
        if obj.file:
            return obj.file.name.split("/")[-1]
        return "-"

    file_display.short_description = "File"

    def file_size_display(self, obj):
        """Display human-readable file size."""
        if not obj.file_size:
            return "-"
        size = obj.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    file_size_display.short_description = "File size"

    def token_count(self, obj):
        """Display token statistics."""
        from django.utils.html import format_html

        stats = obj.get_token_stats()
        return format_html(
            '<span style="color: green;">{}</span> / <span style="color: gray;">{}</span>',
            stats["used"],
            stats["total"],
        )

    token_count.short_description = "Tokens (used/total)"


@admin.register(OneTimeAccessToken)
class OneTimeAccessTokenAdmin(DefModelAdmin):
    """Admin interface for OneTimeAccessToken."""

    list_display = (
        "token_short",
        "content",
        "note",
        "used",
        "used_at",
        "used_by",
        "ip_address",
        "created",
    )
    list_filter = ("used", "used_at", "created", "content__event")
    search_fields = ("token", "note", "content__name", "used_by__name", "ip_address")
    readonly_fields = ("token", "used", "used_at", "used_by", "ip_address", "user_agent", "created", "updated")
    autocomplete_fields = ["content", "used_by"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "content",
                    "token",
                    "note",
                )
            },
        ),
        (
            "Usage information",
            {
                "fields": ("used", "used_at", "used_by", "ip_address", "user_agent"),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created", "updated"),
                "classes": ("collapse",),
            },
        ),
    )

    def token_short(self, obj):
        """Display shortened token."""
        return f"{obj.token[:12]}..."

    token_short.short_description = "Token"

    def has_add_permission(self, request):
        """Prevent adding tokens through admin - they should be generated via the content."""
        return True
