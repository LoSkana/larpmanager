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
"""Cache helpers for writing elements: field values and relationship tags."""

from __future__ import annotations

from django.conf import settings as conf_settings
from django.core.cache import cache

from larpmanager.cache.fields import visible_writing_fields
from larpmanager.models.event import Event
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    WritingAnswer,
    WritingChoice,
    WritingQuestionType,
)
from larpmanager.models.writing import RelationshipTag
from larpmanager.utils.core.common import get_event_elements


def get_character_element_fields(
    context: dict,
    character_id: int,
    *,
    only_visible: bool = True,
) -> dict:
    """Get writing element fields for a character."""
    return get_writing_element_fields(
        context,
        "character",
        QuestionApplicable.CHARACTER,
        character_id,
        only_visible=only_visible,
    )


def get_writing_element_fields(
    context: dict,
    feature_name: str,
    applicable: str,
    element_id: int,
    *,
    only_visible: bool = True,
) -> dict[str, dict]:
    """Get writing fields for a specific element with visibility filtering."""
    batch_results = get_writing_element_fields_batch(
        context,
        feature_name,
        applicable,
        [element_id],
        only_visible=only_visible,
    )
    return batch_results.get(
        element_id, {"questions": context.get("questions", {}), "options": context.get("options", {}), "fields": {}}
    )


def get_writing_element_fields_batch(
    context: dict,
    feature_name: str,
    applicable: str,
    element_ids: list[int],
    *,
    only_visible: bool = True,
) -> dict[int, dict[str, dict]]:
    """Get writing fields for multiple elements with visibility filtering.

    Args:
        context: Context dictionary containing event and configuration data including
             'questions', 'options', and visibility settings
        feature_name: Name of the feature (e.g., 'character', 'faction') used
                     for determining visibility key
        applicable: QuestionApplicable enum value defining question scope
        element_ids: List of element IDs to retrieve fields for
        only_visible: Whether to include only visible fields. Defaults to True

    Returns:
        Dictionary mapping element_id to:
            - questions: Available questions from context
            - options: Available options from context
            - fields: Mapping of question_id to field values (text or list of option_ids)

    """
    # Apply visibility filtering to populate context with visible fields
    fields_data = visible_writing_fields(context, applicable, only_visible=only_visible)

    # Filter questions based on visibility configuration
    # Only include questions that are explicitly shown or when show_all is enabled
    visible_question_ids = []
    for question_uuid in fields_data["questions"]:
        question_config_key = str(question_uuid)
        # Skip questions not marked as visible unless showing all
        if "show_all" not in context and question_config_key not in context.get(f"show_{feature_name}", {}):
            continue
        visible_question_ids.append(question_uuid)

    # Initialize results dictionary for all elements
    results = {element_id: {} for element_id in element_ids}

    # Retrieve text answers for all elements
    # Query WritingAnswer model for text-based responses
    text_answers_query = WritingAnswer.objects.filter(
        element_id__in=element_ids,
        question__uuid__in=visible_question_ids,
        question__typ__in=[
            BaseQuestionType.TEXT,
            BaseQuestionType.PARAGRAPH,
            BaseQuestionType.EDITOR,
            WritingQuestionType.COMPUTED,
        ],
    ).select_related("question")
    for element_id, question_uuid, text in text_answers_query.values_list("element_id", "question__uuid", "text"):
        results[element_id][question_uuid] = text

    # Retrieve choice answers for all elements
    # Group multiple choice options into lists per question
    choice_answers_query = WritingChoice.objects.filter(
        element_id__in=element_ids,
        question__uuid__in=visible_question_ids,
        question__typ__in=[BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE],
    ).select_related("question", "option")
    for element_id, question_uuid, option_uuid in choice_answers_query.values_list(
        "element_id", "question__uuid", "option__uuid"
    ):
        # Initialize list if question not yet in fields
        if question_uuid not in results[element_id]:
            results[element_id][question_uuid] = []
        results[element_id][question_uuid].append(option_uuid)

    # Return full format for each element
    return {
        element_id: {
            "questions": fields_data["questions"],
            "options": fields_data["options"],
            "fields": fields,
        }
        for element_id, fields in results.items()
    }


def get_relationship_tags_key(event_id: int) -> str:
    """Generate cache key for the relationship tags of an event."""
    return f"event_relationship_tags_{event_id}"


def init_relationship_tags_cache(event: Event) -> list[dict]:
    """Build the serialized list of relationship tags available for an event."""
    return [
        {"uuid": tag.uuid, "name": tag.name, "symmetric": tag.symmetric}
        for tag in get_event_elements(event.id, RelationshipTag).order_by("order", "number")
    ]


def get_cached_relationship_tags(event: Event) -> list[dict]:
    """Get cached relationship tags of an event, as dicts with uuid, name and symmetric."""
    cache_key = get_relationship_tags_key(event.id)
    tags_list = cache.get(cache_key)
    if tags_list is None:
        tags_list = init_relationship_tags_cache(event)
        cache.set(cache_key, tags_list, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return tags_list


def clear_relationship_tags_cache(event_id: int) -> None:
    """Clear relationship tags cache of an event, and of all events inheriting from it."""
    cache.delete(get_relationship_tags_key(event_id))
    for child_id in Event.objects.filter(parent_id=event_id).values_list("id", flat=True):
        cache.delete(get_relationship_tags_key(child_id))
