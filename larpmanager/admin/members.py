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
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.html import format_html

from larpmanager.admin.base import AssociationFilter, DefModelAdmin, MemberFilter, reduced
from larpmanager.models.member import Badge, Member, MemberConfig, Membership, VolunteerRegistry, Vote


class MyUserAdmin(UserAdmin):
    """Custom admin interface for Django User model."""

    list_display = ("username", "is_staff", "email", "is_superuser", "character_link")
    list_filter = ("is_staff", "is_superuser")
    fieldsets = (
        (None, {"fields": ("username", "password", "email")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
            },
        ),
    )
    ordering = ("id",)

    @staticmethod
    def character_link(instance: User) -> str:
        """Generate admin link for member."""
        url = reverse("admin:larpmanager_member_change", args=[instance.member.id])
        return format_html('<a href="{}">{}</a>', url, instance.member)


admin.site.unregister(User)
admin.site.register(User, MyUserAdmin)


@admin.register(Member)
class MemberAdmin(DefModelAdmin):
    """Admin interface for Member model."""

    search_fields = ("search", "name", "surname", "nickname", "language")
    list_display = (
        "display_member",
        "name",
        "surname",
        "nickname",
        "legal_name",
        "user_link",
        "diet_red",
        "safety_red",
    )

    list_filter = ("newsletter", "first_aid", "language")
    autocomplete_fields: ClassVar[list] = ["user", "badges", "parent"]

    @staticmethod
    def user_link(instance: Member) -> str:
        """Generate HTML link to admin page for the user."""
        url = reverse("admin:auth_user_change", args=[instance.user.id])
        return format_html('<a href="{}">{}</a>', url, instance.user)

    @staticmethod
    def diet_red(instance: Member) -> str:
        """Return reduced diet info for admin display."""
        return reduced(instance.diet)

    @staticmethod
    def safety_red(instance: Member) -> str:
        """Return reduced safety info for admin display."""
        return reduced(instance.safety)


@admin.register(MemberConfig)
class MemberConfigAdmin(DefModelAdmin):
    """Admin interface for MemberConfig model."""

    list_display = ("member", "name", "value")
    search_fields: ClassVar[tuple] = ("name",)
    list_filter = (MemberFilter,)
    autocomplete_fields: ClassVar[list] = ["member"]


@admin.register(Membership)
class MembershipAdmin(DefModelAdmin):
    """Admin interface for Membership model."""

    list_display: ClassVar[tuple] = ("member", "association", "status", "card_number", "date", "created")
    list_filter = (AssociationFilter, MemberFilter)
    autocomplete_fields: ClassVar[list] = ["member", "association"]


@admin.register(VolunteerRegistry)
class VolunteerRegistryAdmin(DefModelAdmin):
    """Admin interface for VolunteerRegistry model."""

    list_display: ClassVar[tuple] = ("member", "association", "start", "end")
    list_filter = (MemberFilter, AssociationFilter)
    autocomplete_fields: ClassVar[list] = ["member", "association"]


@admin.register(Vote)
class VoteAdmin(DefModelAdmin):
    """Admin interface for Vote model."""

    list_display: ClassVar[tuple] = ("member", "association", "year", "number", "candidate")
    list_filter = (MemberFilter, AssociationFilter, "year")
    autocomplete_fields: ClassVar[list] = ["member", "association", "candidate"]


@admin.register(Badge)
class BadgeAdmin(DefModelAdmin):
    """Admin interface for Badge model."""

    list_display: ClassVar[tuple] = ("name", "cod", "descr", "number", "thumb")
    autocomplete_fields: ClassVar[list] = ["members"]
    search_fields: ClassVar[list] = ["name"]
