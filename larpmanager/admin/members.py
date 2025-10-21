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
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.safestring import mark_safe

from larpmanager.admin.base import AssocFilter, DefModelAdmin, MemberFilter, reduced
from larpmanager.models.member import Badge, Member, MemberConfig, Membership, VolunteerRegistry, Vote


class MyUserAdmin(UserAdmin):
    list_display = ("username", "is_staff", "email", "is_superuser", "character_link")
    list_filter = ("is_staff", "is_superuser")
    fieldsets = (
        (None, {"fields": ("username", "password", "email")}),
        (
            "Permissions",
            {
                "fields": ("is_active", "is_staff", "is_superuser"),
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
    def character_link(instance):
        url = reverse("admin:larpmanager_member_change", args=[instance.member.id])
        return mark_safe(f"<a href='{url}'>{instance.member}</a>")


admin.site.unregister(User)
admin.site.register(User, MyUserAdmin)


@admin.register(Member)
class MemberAdmin(DefModelAdmin):
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
    autocomplete_fields = ["user", "badges", "parent"]

    @staticmethod
    def user_link(instance):
        url = reverse("admin:auth_user_change", args=[instance.user.id])
        return mark_safe(f"<a href='{url}'>{instance.user}</a>")

    @staticmethod
    def diet_red(instance):
        return reduced(instance.diet)

    @staticmethod
    def safety_red(instance):
        return reduced(instance.safety)


@admin.register(MemberConfig)
class MemberConfigAdmin(DefModelAdmin):
    list_display = ("member", "name", "value")
    search_fields = ("name",)
    list_filter = (MemberFilter,)
    autocomplete_fields = ["member"]


@admin.register(Membership)
class MembershipAdmin(DefModelAdmin):
    list_display = ("member", "assoc", "status", "card_number", "date", "created")
    list_filter = (AssocFilter, MemberFilter)
    autocomplete_fields = ["member", "assoc"]


@admin.register(VolunteerRegistry)
class VolunteerRegistryAdmin(DefModelAdmin):
    list_display = ("member", "assoc", "start", "end")
    list_filter = (MemberFilter, AssocFilter)
    autocomplete_fields = ["member", "assoc"]


@admin.register(Vote)
class VoteAdmin(DefModelAdmin):
    list_display = ("member", "assoc", "year", "number", "candidate")
    list_filter = (MemberFilter, AssocFilter, "year")
    autocomplete_fields = ["member", "assoc", "candidate"]


@admin.register(Badge)
class BadgeAdmin(DefModelAdmin):
    list_display = ("name", "cod", "descr", "number", "thumb")
    autocomplete_fields = ["members"]
    search_fields = ["name"]
