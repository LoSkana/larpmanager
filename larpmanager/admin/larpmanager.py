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

from larpmanager.admin.base import DefModelAdmin
from larpmanager.models.base import PublisherApiKey
from larpmanager.models.larpmanager import (
    LarpManagerDiscover,
    LarpManagerFaq,
    LarpManagerFaqType,
    LarpManagerGuide,
    LarpManagerProfiler,
    LarpManagerReview,
    LarpManagerShowcase,
    LarpManagerTicket,
    LarpManagerTutorial,
)


@admin.register(LarpManagerFaq)
class LarpManagerFaqAdmin(DefModelAdmin):
    list_display: ClassVar[tuple] = ("question_red", "typ", "number", "answer_red")
    list_filter = ("typ",)
    autocomplete_fields: ClassVar[list] = ["typ"]

    @staticmethod
    def question_red(instance):
        """Return truncated question for admin display."""
        return instance.question[:100]

    @staticmethod
    def answer_red(instance):
        """Return truncated answer for admin display."""
        return instance.answer[:100]


@admin.register(LarpManagerFaqType)
class LarpManagerFaqTypeAdmin(DefModelAdmin):
    list_display = ("name", "order")
    search_fields: ClassVar[list] = ["name"]


@admin.register(LarpManagerTutorial)
class LarpManagerTutorial(DefModelAdmin):
    list_display = ("name", "slug", "order", "descr_red")

    @staticmethod
    def descr_red(instance):
        """Return truncated description for admin display."""
        return instance.descr[:100]


@admin.register(LarpManagerGuide)
class LarpManagerBlogAdmin(DefModelAdmin):
    list_display = ("title", "slug", "number", "published", "text_red", "show_thumb")


@admin.register(LarpManagerShowcase)
class LarpManagerShowcaseAdmin(DefModelAdmin):
    list_display = ("title", "number", "text_red", "show_reduced")


@admin.register(LarpManagerProfiler)
class LarpManagerProfilerAdmin(DefModelAdmin):
    list_display = ("id", "view_func_name", "domain", "duration", "created")


@admin.register(LarpManagerDiscover)
class LarpManagerDiscoverAdmin(DefModelAdmin):
    list_display = ("name", "order", "text_red", "text_len")

    @staticmethod
    def text_red(instance):
        """Return truncated text for admin display."""
        return instance.text[:100]

    @staticmethod
    def text_len(instance):
        """Return text length for admin display."""
        return len(instance.text)


@admin.register(LarpManagerReview)
class LMReviewAdmin(DefModelAdmin):
    list_display = ("text", "author")


@admin.register(LarpManagerTicket)
class LarpManagerTicketAdmin(DefModelAdmin):
    list_display = ("id", "reason", "association", "email", "member", "content_red", "show_thumb")

    @staticmethod
    def content_red(instance):
        """Return truncated content for admin display."""
        return instance.content[:100]


@admin.register(PublisherApiKey)
class PublisherApiKeyAdmin(DefModelAdmin):
    list_display = ("name", "key", "active", "last_used", "usage_count")
