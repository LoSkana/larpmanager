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

from typing import TYPE_CHECKING

from django.conf import settings as conf_settings
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.cache import cache
from django.db.models import F, Prefetch

from larpmanager.models.form import (
    QuestionApplicable,
    RegistrationOption,
    RegistrationQuestion,
    WritingOption,
    WritingQuestion,
)

if TYPE_CHECKING:
    from larpmanager.models.event import Event


def get_event_questions_cache_key(event_id: int, question_type: str) -> str:
    """Generate cache key for event questions."""
    return f"event_questions_{question_type}_{event_id}"


def init_writing_questions_cache(event: Event) -> dict:
    """Initialize cache for all writing questions grouped by applicable type."""
    # Load all writing questions with prefetched options
    all_questions = list(
        event.get_elements(WritingQuestion)
        .order_by("order")
        .prefetch_related(Prefetch("options", queryset=WritingOption.objects.order_by("order")))
    )

    # Group questions by applicable type
    questions_by_applicable = {}
    for applicable, _label in QuestionApplicable.choices:
        questions_by_applicable[applicable] = [q for q in all_questions if q.applicable == applicable]

    return questions_by_applicable


def init_registration_questions_cache(event: Event, features: list[str]) -> list:
    """Initialize cache for registration questions."""
    # Get all questions for the event, ordered by section first, then by question order
    questions = RegistrationQuestion.objects.filter(event=event).order_by(
        F("section__order").asc(nulls_first=True),
        "order",
    )

    # Conditionally add annotations based on enabled features
    if "reg_que_tickets" in features:
        questions = questions.annotate(tickets_map=ArrayAgg("tickets__uuid"))
    if "reg_que_faction" in features:
        questions = questions.annotate(factions_map=ArrayAgg("factions__id"))
    if "reg_que_allowed" in features:
        questions = questions.annotate(allowed_map=ArrayAgg("allowed__id"))

    # Prefetch options to avoid N+1 queries
    return questions.prefetch_related(Prefetch("options", queryset=RegistrationOption.objects.order_by("order")))


def get_cached_writing_questions(event: Event, applicable: str) -> list:
    """Get cached writing questions for a specific applicable type.

    Args:
        event: Event instance
        applicable: Question applicable type (e.g., QuestionApplicable.CHARACTER)

    Returns:
        list: List of WritingQuestion objects filtered by applicable type

    """
    cache_key = get_event_questions_cache_key(event.id, "writing")

    # Try to get from cache
    cached_questions = cache.get(cache_key)

    if cached_questions is None:
        # Initialize cache with all applicable types
        cached_questions = init_writing_questions_cache(event)
        cache.set(cache_key, cached_questions, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    # Return questions for the requested applicable type
    return cached_questions.get(applicable, [])


def get_cached_registration_questions(event: Event, features: list[str]) -> list:
    """Get cached registration questions."""
    cache_key = get_event_questions_cache_key(event.id, "registration")

    # Try to get from cache
    cached_questions = cache.get(cache_key)

    if cached_questions is None:
        # Initialize cache
        cached_questions = init_registration_questions_cache(event, features)
        cache.set(cache_key, cached_questions, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_questions


def clear_writing_questions_cache(event_id: int) -> None:
    """Clear writing questions cache for an event."""
    cache_key = get_event_questions_cache_key(event_id, "writing")
    cache.delete(cache_key)


def clear_registration_questions_cache(event_id: int) -> None:
    """Clear registration questions cache for an event."""
    cache_key = get_event_questions_cache_key(event_id, "registration")
    cache.delete(cache_key)
