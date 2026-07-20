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

from larpmanager.admin.base import CSRFTinyMCEModelAdmin, DefModelAdmin
from larpmanager.models.base import PublisherApiKey
from larpmanager.models.larpmanager import (
    LarpManagerBlog,
    LarpManagerChatLog,
    LarpManagerCollaborator,
    LarpManagerDemoHint,
    LarpManagerDemoHintDismissal,
    LarpManagerDemoType,
    LarpManagerDiscover,
    LarpManagerFaq,
    LarpManagerFaqType,
    LarpManagerGuide,
    LarpManagerHighlight,
    LarpManagerNewsletter,
    LarpManagerPartner,
    LarpManagerProfiler,
    LarpManagerReview,
    LarpManagerScreenshot,
    LarpManagerShowcase,
    LarpManagerText,
    LarpManagerTicket,
    LarpManagerTutorial,
)


@admin.register(LarpManagerDemoType)
class LarpManagerDemoTypeAdmin(DefModelAdmin):
    """Admin interface for LarpManagerDemoType model."""

    list_display = ("name", "slug", "icon", "color", "template_association", "order", "active")
    list_filter = ("active",)
    search_fields: ClassVar[list] = ["name", "slug"]
    raw_id_fields: ClassVar[list] = ["template_association"]


@admin.register(LarpManagerDemoHint)
class LarpManagerDemoHintAdmin(CSRFTinyMCEModelAdmin):
    """Admin interface for LarpManagerDemoHint model."""

    list_display = ("key", "view_name", "demo_type", "title", "order", "active")
    list_filter = ("active", "demo_type")
    search_fields: ClassVar[list] = ["key", "view_name", "title"]
    autocomplete_fields: ClassVar[list] = ["demo_type"]


@admin.register(LarpManagerDemoHintDismissal)
class LarpManagerDemoHintDismissalAdmin(DefModelAdmin):
    """Admin interface for LarpManagerDemoHintDismissal model."""

    list_display = ("member", "hint", "created")
    raw_id_fields: ClassVar[list] = ["member", "hint"]


@admin.register(LarpManagerFaq)
class LarpManagerFaqAdmin(CSRFTinyMCEModelAdmin):
    """Admin interface for LarpManagerFaq model."""

    list_display: ClassVar[tuple] = ("question_red", "typ", "number", "answer_red")
    list_filter = ("typ",)
    autocomplete_fields: ClassVar[list] = ["typ"]

    @staticmethod
    def question_red(instance: LarpManagerFaq) -> str:
        """Return truncated question for admin display."""
        return instance.question[:100]

    @staticmethod
    def answer_red(instance: LarpManagerFaq) -> str:
        """Return truncated answer for admin display."""
        return instance.answer[:100] if instance.answer else ""


@admin.register(LarpManagerFaqType)
class LarpManagerFaqTypeAdmin(DefModelAdmin):
    """Admin interface for LarpManagerFaqType model."""

    list_display = ("name", "order")
    search_fields: ClassVar[list] = ["id", "name"]


@admin.register(LarpManagerTutorial)
class LarpManagerTutorialAdmin(CSRFTinyMCEModelAdmin):
    """Admin interface for LarpManagerTutorial model with CSRF-aware TinyMCE."""

    list_display = ("name", "slug", "order", "descr_red")

    @staticmethod
    def descr_red(instance: LarpManagerTutorial) -> str:
        """Return truncated description for admin display."""
        return instance.descr[:100] if instance.descr else ""


@admin.register(LarpManagerGuide)
class LarpManagerGuideAdmin(CSRFTinyMCEModelAdmin):
    """Admin interface for LarpManagerGuide model."""

    list_display = ("title", "slug", "number", "published", "text_red", "show_thumb")
    list_filter = ("published",)
    search_fields = ("title", "description", "slug")


@admin.register(LarpManagerBlog)
class LarpManagerBlogAdmin(CSRFTinyMCEModelAdmin):
    """Admin interface for LarpManagerBlog model."""

    list_display = ("title", "slug", "number", "published")
    list_filter = ("published",)
    search_fields = ("title", "description", "slug", "keywords")


@admin.register(LarpManagerHighlight)
class LarpManagerHighlightAdmin(DefModelAdmin):
    """Admin interface for LarpManagerHighlight model."""

    list_display = ("info", "show_reduced")
    search_fields: ClassVar[list] = ["id", "info"]


@admin.register(LarpManagerScreenshot)
class LarpManagerScreenshotAdmin(DefModelAdmin):
    """Admin interface for LarpManagerScreenshot model."""

    list_display = ("caption", "order", "show_reduced")
    search_fields: ClassVar[list] = ["id", "caption"]


@admin.register(LarpManagerShowcase)
class LarpManagerShowcaseAdmin(CSRFTinyMCEModelAdmin):
    """Admin interface for LarpManagerShowcase model."""

    list_display = ("title", "number", "text_red", "blog")
    autocomplete_fields: ClassVar[list] = ["blog"]


@admin.register(LarpManagerProfiler)
class LarpManagerProfilerAdmin(DefModelAdmin):
    """Admin interface for LarpManagerProfiler model."""

    list_display = ("id", "view_func_name", "domain", "duration")


@admin.register(LarpManagerDiscover)
class LarpManagerDiscoverAdmin(CSRFTinyMCEModelAdmin):
    """Admin interface for LarpManagerDiscover model."""

    list_display = ("name", "order", "text_red", "text_len")

    @staticmethod
    def text_red(instance: LarpManagerDiscover) -> str:
        """Return truncated text for admin display."""
        return instance.text[:100] if instance.text else ""

    @staticmethod
    def text_len(instance: LarpManagerDiscover) -> int:
        """Return text length for admin display."""
        return len(instance.text) if instance.text else 0


@admin.register(LarpManagerReview)
class LMReviewAdmin(DefModelAdmin):
    """Admin interface for LarpManagerReview model."""

    list_display = ("text", "author")


@admin.register(LarpManagerText)
class LarpManagerTextAdmin(CSRFTinyMCEModelAdmin):
    """Admin interface for LarpManagerText model."""

    list_display = ("name", "value_red")
    search_fields: ClassVar[list] = ["name", "value"]

    @staticmethod
    def value_red(instance: LarpManagerText) -> str:
        """Return truncated value for admin display."""
        return instance.value[:100] if instance.value else ""


@admin.register(LarpManagerTicket)
class LarpManagerTicketAdmin(DefModelAdmin):
    """Admin interface for LarpManagerTicket model."""

    list_display = ("id", "reason", "association", "email", "member", "content_red", "show_thumb", "uuid")
    search_fields: ClassVar[list] = ["id", "uuid"]

    @staticmethod
    def content_red(instance: LarpManagerTicket) -> str:
        """Return truncated content for admin display."""
        return instance.content[:100]


@admin.register(PublisherApiKey)
class PublisherApiKeyAdmin(DefModelAdmin):
    """Admin interface for PublisherApiKey model."""

    list_display = ("name", "key", "active", "last_used", "usage_count")


@admin.register(LarpManagerNewsletter)
class LarpManagerNewsletterAdmin(DefModelAdmin):
    """Admin interface for PublisherApiKey model."""

    list_display = ("email", "status")


@admin.register(LarpManagerPartner)
class LarpManagerPartnerAdmin(DefModelAdmin):
    """Admin interface for LarpManagerPartner model."""

    list_display = ("name", "url", "show_thumb")


@admin.register(LarpManagerCollaborator)
class LarpManagerCollaboratorAdmin(DefModelAdmin):
    """Admin interface for LarpManagerCollaborator model."""

    list_display = ("name", "show_thumb")
    search_fields: ClassVar[list] = ["id", "name"]


@admin.register(LarpManagerChatLog)
class LarpManagerChatLogAdmin(DefModelAdmin):
    """Admin interface for LarpManagerCollaborator model."""

    list_display = ("member", "question")
    search_fields: ClassVar[list] = ["id", "question"]
