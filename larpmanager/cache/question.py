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

from typing import TYPE_CHECKING, Any

from django.conf import settings as conf_settings
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.cache import cache
from django.db.models import F, Prefetch

from larpmanager.models.form import (
    QuestionApplicable,
    QuestionStatus,
    RegistrationOption,
    RegistrationQuestion,
    WritingOption,
    WritingQuestion,
    get_def_writing_types,
)
from larpmanager.models.registration import Registration, RegistrationCharacterRel

if TYPE_CHECKING:
    from larpmanager.models.event import Event


def skip_registration_question(
    question: dict,
    registration: Any,
    features: Any,
    params: Any = None,
    *,
    is_organizer: Any = False,
) -> bool:
    """Determine if a registration question should be skipped.

    Evaluates question visibility rules including hidden status, ticket restrictions,
    faction filtering, and organizer permissions to decide if question should be shown.

    Args:
        question: Question dict with question data and maps (tickets_map, factions_map, allowed_map)
        registration: Registration instance to check against
        features: List of enabled features
        params: Additional parameters including run and member
        is_organizer: Whether user is organizer

    Returns:
        True if question should be skipped, False otherwise

    """
    if question["status"] == QuestionStatus.HIDDEN and not is_organizer:
        return True

    # Check ticket restrictions
    if _skip_question_tickets(features, registration, question):
        return True

    # Check faction restrictions
    if _skip_question_factions(features, registration, question):
        return True

    # Check allowed organizer restrictions
    return bool(_skip_question_allowed(features, registration, question, params, is_organizer=is_organizer))


def _skip_question_allowed(
    features: dict, registration: Registration, question: dict, params: dict, *, is_organizer: bool
) -> bool:
    """Check if skip showing question due to staff member not allowed."""
    if "reg_que_allowed" not in features or not registration or not registration.pk or not is_organizer or not params:
        return False

    allowed_map = [a for a in question.get("allowed_map", []) if a is not None]
    if not allowed_map:
        return False

    run_id = params["run"].id
    is_run_organizer = 1 in params["all_runs"].get(run_id, {})

    return bool(not is_run_organizer and params["member"].id not in allowed_map)


def _skip_question_tickets(features: dict, registration: Registration, question: dict) -> bool:
    """Check if skip showing question if the correct ticket is not selected."""
    if "reg_que_tickets" not in features or not registration or not registration.pk:
        return False

    allowed_ticket_uuids = [ticket_uuid for ticket_uuid in question.get("tickets_map", []) if ticket_uuid is not None]
    if allowed_ticket_uuids:
        if not registration.ticket:
            return True

        if registration.ticket.uuid not in allowed_ticket_uuids:
            return True

    return False


def _skip_question_factions(features: dict, registration: Registration, question: dict) -> bool:
    """Check if skip showing question if the correct faction is not assigned."""
    if "reg_que_faction" not in features:
        return False

    allowed_faction_ids = [faction_id for faction_id in question.get("factions_map", []) if faction_id is not None]
    if allowed_faction_ids:
        registration_faction_ids = []
        if registration and registration.pk:
            for character_relation in RegistrationCharacterRel.objects.filter(registration=registration):
                character_factions = character_relation.character.factions_list.values_list("id", flat=True)
                registration_faction_ids.extend(character_factions)

        if not set(allowed_faction_ids).intersection(set(registration_faction_ids)):
            return True

    return False


def get_event_questions_cache_key(event_id: int, question_type: str) -> str:
    """Generate cache key for event questions."""
    return f"event_questions_{question_type}_{event_id}"


def init_writing_questions_cache(event: Event) -> dict:
    """Initialize cache for all writing questions grouped by applicable type.

    Returns:
        Dict mapping applicable types to lists of question dicts with serialized options

    """
    # Load all writing questions with options annotated with tickets_map
    options_queryset = WritingOption.objects.order_by("order").annotate(tickets_map=ArrayAgg("tickets__id"))

    all_questions = (
        event.get_elements(WritingQuestion)
        .order_by("order")
        .prefetch_related(Prefetch("options", queryset=options_queryset))
    )

    # Serialize questions to dicts
    serialized_questions = [q.as_dict() for q in all_questions]

    # Group questions by applicable type
    questions_by_applicable = {}
    for applicable, _label in QuestionApplicable.choices:
        questions_by_applicable[applicable] = [q for q in serialized_questions if q["applicable"] == applicable]

    return questions_by_applicable


def init_registration_questions_cache(event: Event) -> list:
    """Initialize cache for registration questions.

    Returns a list of question dicts with serialized options and annotation maps.

    Note: We always compute all annotations regardless of enabled features to ensure
    cache consistency across different feature configurations.
    """
    # Get all questions for the event, ordered by section first, then by question order
    questions = RegistrationQuestion.objects.filter(event=event).order_by(
        F("section__order").asc(nulls_first=True),
        "order",
    )

    # Add all annotations to ensure cache consistency
    questions = questions.annotate(
        tickets_map=ArrayAgg("tickets__uuid"),
        factions_map=ArrayAgg("factions__id"),
        allowed_map=ArrayAgg("allowed__id"),
    )

    # Prefetch section and options
    questions = questions.select_related("section").prefetch_related(
        Prefetch("options", queryset=RegistrationOption.objects.order_by("order"))
    )

    # Serialize questions to dicts
    return [question.as_dict() for question in questions]


def get_cached_writing_questions(event: Event, applicable: str) -> list:
    """Get cached writing questions for a specific applicable type.

    Args:
        event: Event instance
        applicable: Question applicable type (e.g., QuestionApplicable.CHARACTER)

    Returns:
        list: List of question dicts filtered by applicable type, ordered by 'order' field.
              Each dict contains question fields and 'options' list with serialized options.

    """
    cache_key = get_event_questions_cache_key(event.id, "writing")

    # Try to get from cache
    cached_questions = cache.get(cache_key)

    if cached_questions is None:
        # Initialize cache with all applicable types
        cached_questions = init_writing_questions_cache(event)
        cache.set(cache_key, cached_questions, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    # Explicitly sort to ensure order is preserved after cache deserialization
    questions = cached_questions.get(applicable, [])
    return sorted(questions, key=lambda q: q["order"])


def get_cached_registration_questions(event: Event) -> list:
    """Get cached registration questions.

    Returns:
        list: List of question dicts ordered by section order (nulls first) then by question order.
              Each dict contains question fields, annotation maps, and 'options' list.

    """
    cache_key = get_event_questions_cache_key(event.id, "registration")

    # Try to get from cache
    cached_data = cache.get(cache_key)

    if cached_data is None:
        # Initialize cache
        cached_data = init_registration_questions_cache(event)
        cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    # Explicitly sort to ensure order is preserved after cache deserialization
    return sorted(cached_data, key=lambda q: (q.get("section_order") or -1, q["order"]))


def get_writing_field_names(event: Event, applicable: str) -> dict:
    """Get a mapping of default field type to field name for an applicable type."""
    def_types = get_def_writing_types()
    questions = get_cached_writing_questions(event, applicable)
    return {q["typ"]: q["name"] for q in questions if q["typ"] in def_types}


def clear_writing_questions_cache(event_id: int) -> None:
    """Clear writing questions cache for an event."""
    cache_key = get_event_questions_cache_key(event_id, "writing")
    cache.delete(cache_key)


def clear_registration_questions_cache(event_id: int) -> None:
    """Clear registration questions cache for an event."""
    cache_key = get_event_questions_cache_key(event_id, "registration")
    cache.delete(cache_key)
