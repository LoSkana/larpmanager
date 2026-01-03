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

from typing import TYPE_CHECKING, ClassVar

from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin
from django.utils.html import format_html

from larpmanager.admin.base import AssociationFilter, DefModelAdmin, EventFilter, RunFilter, reduced
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
    Problem,
    ShuttleService,
    UrlShortner,
    Util,
    WarehouseArea,
    WarehouseContainer,
    WarehouseItem,
    WarehouseItemAssignment,
    WarehouseMovement,
    WarehouseTag,
    WorkshopMemberRel,
    WorkshopModule,
    WorkshopOption,
    WorkshopQuestion,
)

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.register(Contact)
class ContactAdmin(DefModelAdmin):
    """Admin interface for Contact model."""

    list_display = ("me", "you", "channel")
    autocomplete_fields: ClassVar[list] = ["me", "you", "association"]


@admin.register(ChatMessage)
class ChatMessageAdmin(DefModelAdmin):
    """Admin interface for ChatMessage model."""

    list_display = ("id", "sender", "receiver")
    autocomplete_fields = ("sender", "receiver", "association")


@admin.register(Album)
class AlbumAdmin(DefModelAdmin):
    """Admin interface for Album model."""

    list_display: ClassVar[tuple] = ("name", "parent", "run", "show_thumb", "uuid")
    autocomplete_fields: ClassVar[list] = ["parent", "run", "association"]
    search_fields: ClassVar[list] = ["id", "name", "uuid"]


@admin.register(AlbumImage)
class AlbumImageAdmin(DefModelAdmin):
    """Admin interface for AlbumImage model."""

    list_display = ("upload", "show_thumb", "width", "height")


@admin.register(AlbumUpload)
class AlbumUploadAdmin(DefModelAdmin):
    """Admin interface for AlbumUpload model."""

    list_display = ("id", "album")
    autocomplete_fields: ClassVar[list] = ["album"]


class WorkshopQuestionInline(admin.TabularInline):
    """Inline admin for WorkshopQuestion model within parent admin."""

    model = WorkshopQuestion
    exclude = ("search",)
    show_change_link = True


@admin.register(WorkshopModule)
class WorkshopModuleAdmin(DefModelAdmin):
    """Admin interface for WorkshopModule model."""

    search_fields: ClassVar[tuple] = ("id", "search", "uuid")
    list_display = ("name", "event", "number", "is_generic", "uuid")
    inlines: ClassVar[list] = [
        WorkshopQuestionInline,
    ]
    autocomplete_fields: ClassVar[list] = ["event", "members"]


class WorkshopModuleFilter(AutocompleteFilter):
    """Admin filter for WorkshopModule autocomplete."""

    title = "WorkshopModule"
    field_name = "module"


class WorkshopOptionInline(admin.TabularInline):
    """Inline admin for WorkshopOption model within parent admin."""

    model = WorkshopOption
    exclude = ("search",)


@admin.register(WorkshopQuestion)
class WorkshopQuestionAdmin(DefModelAdmin):
    """Admin interface for WorkshopQuestion model."""

    search_fields: ClassVar[tuple] = ("id", "search", "uuid")
    list_display = ("name", "number", "module", "uuid")
    autocomplete_fields: ClassVar[tuple] = ("module", "event")
    list_filter = (WorkshopModuleFilter,)
    inlines: ClassVar[list] = [
        WorkshopOptionInline,
    ]


class WorkshopOptionFilter(AutocompleteFilter):
    """Admin filter for WorkshopOption autocomplete."""

    title = "WorkshopQuestion"
    field_name = "question"


@admin.register(WorkshopOption)
class WorkshopOptionAdmin(DefModelAdmin):
    """Admin interface for WorkshopOption model."""

    list_display = ("name", "question", "is_correct", "uuid")
    search_fields: ClassVar[tuple] = ("id", "uuid")
    autocomplete_fields = ("question",)
    list_filter = (WorkshopOptionFilter,)


@admin.register(WorkshopMemberRel)
class WorkshopMemberRelAdmin(DefModelAdmin):
    """Admin interface for WorkshopMemberRel model."""

    list_display = ("workshop", "member")


@admin.register(HelpQuestion)
class HelpQuestionAdmin(DefModelAdmin):
    """Admin interface for HelpQuestion model."""

    list_display = ("member", "is_user", "small_text")
    autocomplete_fields: ClassVar[list] = ["member", "run", "association"]


@admin.register(WarehouseContainer)
class WarehouseContainerAdmin(DefModelAdmin):
    """Admin interface for WarehouseContainer model."""

    list_display: ClassVar[tuple] = ("name", "position", "uuid")
    autocomplete_fields: ClassVar[list] = ["association"]
    search_fields: ClassVar[list] = ["id", "name", "uuid"]


@admin.register(WarehouseTag)
class WarehouseTagAdmin(DefModelAdmin):
    """Admin interface for WarehouseTag model."""

    list_display = ("name", "description", "uuid")
    search_fields: ClassVar[list] = ["id", "name", "uuid"]


@admin.register(WarehouseItem)
class WarehouseItemAdmin(DefModelAdmin):
    """Admin interface for WarehouseItem model."""

    list_display: ClassVar[tuple] = ("name", "quantity", "container", "description", "uuid")
    autocomplete_fields: ClassVar[list] = ["association", "container", "tags"]
    search_fields: ClassVar[list] = ["id", "name", "uuid"]


@admin.register(WarehouseArea)
class WarehouseAreaAdmin(DefModelAdmin):
    """Admin interface for WarehouseArea model."""

    list_display = ("name", "position", "description", "uuid")
    search_fields: ClassVar[list] = ["id", "name", "uuid"]


@admin.register(WarehouseItemAssignment)
class WarehouseItemAssignmentAdmin(DefModelAdmin):
    """Admin interface for WarehouseItemAssignment model."""

    list_display = ("area", "quantity", "item", "notes")
    autocomplete_fields: ClassVar[list] = ["event", "item", "area"]


@admin.register(ShuttleService)
class ShuttleServiceAdmin(DefModelAdmin):
    """Admin interface for ShuttleService model."""

    list_display = ("member", "passengers", "address", "info", "working", "uuid")
    search_fields: ClassVar[tuple] = ("id", "uuid")
    autocomplete_fields: ClassVar[list] = ["member", "working", "association"]


@admin.register(Util)
class UtilAdmin(DefModelAdmin):
    """Admin interface for Util model."""

    list_display = ("name", "cod", "event", "uuid")
    search_fields: ClassVar[tuple] = ("id", "uuid")
    autocomplete_fields: ClassVar[list] = ["event"]


@admin.register(PlayerRelationship)
class PlayerRelationshipAdmin(DefModelAdmin):
    """Admin interface for PlayerRelationship model."""

    list_display: ClassVar[tuple] = ("reg_red", "target", "text_red")
    list_filter = (TargetFilter,)
    autocomplete_fields: ClassVar[list] = ["target", "reg"]

    @staticmethod
    def text_red(instance: PlayerRelationship) -> str:
        """Return reduced text for admin display."""
        return reduced(instance.text)

    @staticmethod
    def reg_red(instance: PlayerRelationship) -> str:
        """Return registration with run number for admin display."""
        return f"{instance.reg} ({instance.reg.run.number})"


@admin.register(Email)
class EmailAdmin(DefModelAdmin):
    """Admin interface for Email model."""

    list_display: ClassVar[tuple] = ("id", "association", "run", "recipient", "sent", "subj", "body_red", "uuid")
    list_filter: ClassVar[tuple] = (AssociationFilter, RunFilter)
    autocomplete_fields: ClassVar[list] = ["association", "run"]
    search_fields: ClassVar[list] = ["id", "subj", "body", "recipient", "uuid"]

    @staticmethod
    def body_red(instance: Email) -> str:
        """Return reduced body text for admin display."""
        return reduced(instance.body)


class OneTimeAccessTokenInline(admin.TabularInline):
    """Inline admin for access tokens."""

    model = OneTimeAccessToken
    extra = 0
    readonly_fields = ("token", "used", "used_at", "used_by", "ip_address", "user_agent")
    fields = ("note", "token", "used", "used_at", "used_by", "ip_address")
    can_delete = True

    def has_add_permission(self, request: object, obj: object | None = None) -> bool:  # noqa: ARG002
        """Allow adding new tokens."""
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
        "uuid",
    )
    list_filter = ("event", "active")
    search_fields: ClassVar[tuple] = ("id", "name", "description", "event__name", "uuid")
    readonly_fields: ClassVar[tuple] = ("content_type", "file_size")
    inlines: ClassVar[list] = [OneTimeAccessTokenInline]
    autocomplete_fields: ClassVar[list] = ["event"]

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
                ),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("content_type", "file_size", "duration"),
                "classes": ("collapse",),
            },
        ),
    )

    def file_display(self, obj: OneTimeContent) -> str:
        """Display file name."""
        if obj.file:
            return obj.file.name.split("/")[-1]
        return "-"

    file_display.short_description = "File"

    def file_size_display(self, obj: OneTimeContent) -> str:
        """Display human-readable file size."""
        if not obj.file_size:
            return "-"
        size = obj.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            max_size = 1024.0
            if size < max_size:
                return f"{size:.1f} {unit}"
            size /= max_size
        return f"{size:.1f} TB"

    file_size_display.short_description = "File size"

    def token_count(self, obj: OneTimeContent) -> str:
        """Display token statistics."""
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

    list_display = ("token_short", "content", "note", "used", "used_at", "used_by", "ip_address")
    list_filter = ("used", "used_at", "content__event")
    search_fields: ClassVar[tuple] = ("id", "token", "note", "content__name", "used_by__name", "ip_address")
    readonly_fields = ("token", "used", "used_at", "used_by", "ip_address", "user_agent")
    autocomplete_fields: ClassVar[list] = ["content", "used_by"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "content",
                    "token",
                    "note",
                ),
            },
        ),
        (
            "Usage information",
            {
                "fields": ("used", "used_at", "used_by", "ip_address", "user_agent"),
                "classes": ("collapse",),
            },
        ),
    )

    def token_short(self, obj: OneTimeAccessToken) -> str:
        """Display shortened token."""
        return f"{obj.token[:12]}..."

    token_short.short_description = "Token"

    def has_add_permission(self, request: HttpRequest) -> bool:  # noqa: ARG002
        """Prevent adding tokens through admin - they should be generated via the content."""
        return True


@admin.register(UrlShortner)
class UrlShortnerAdmin(DefModelAdmin):
    """Admin interface for UrlShortner model."""

    list_display: ClassVar[tuple] = ("id", "number", "name", "cod", "url", "association", "uuid")
    search_fields: ClassVar[tuple] = ("id", "name", "cod", "uuid")
    autocomplete_fields: ClassVar[list] = ["association"]
    list_filter = (AssociationFilter,)


@admin.register(WarehouseMovement)
class WarehouseMovementAdmin(DefModelAdmin):
    """Admin interface for WarehouseMovement model."""

    list_display: ClassVar[tuple] = ("id", "item", "quantity", "notes", "association", "uuid")
    search_fields: ClassVar[tuple] = ("id", "notes", "uuid")
    autocomplete_fields: ClassVar[list] = ["item", "association"]
    list_filter = (AssociationFilter,)


@admin.register(Problem)
class ProblemAdmin(DefModelAdmin):
    """Admin interface for Problem model."""

    list_display: ClassVar[tuple] = ("id", "event", "number", "severity", "uuid")
    search_fields: ClassVar[tuple] = ("id", "uuid")
    autocomplete_fields: ClassVar[list] = ["event"]
    list_filter = (EventFilter, "severity")
