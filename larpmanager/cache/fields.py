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

from django.conf import settings as conf_settings
from django.core.cache import cache

from larpmanager.models.event import Event
from larpmanager.models.form import (
    QuestionApplicable,
    QuestionVisibility,
    WritingOption,
    WritingQuestion,
    get_def_writing_types,
)


def event_fields_key(event_id: int) -> str:
    """Generate cache key for event fields."""
    return f"event_fields_{event_id}"


def clear_event_fields_cache(event_id: int) -> None:
    """Clear cached event fields."""
    cache.delete(event_fields_key(event_id))


def _ensure_cache_structure(cached_fields: dict, applicability_label: str, section: str) -> None:
    """Ensure the nested cache structure exists for given applicability and section.

    Args:
        cached_fields: The cache dictionary to update
        applicability_label: The applicability label key
        section: The section name (e.g., 'questions', 'options', 'names', 'ids')
    """
    if applicability_label not in cached_fields:
        cached_fields[applicability_label] = {}
    if section not in cached_fields[applicability_label]:
        cached_fields[applicability_label][section] = {}


def update_event_fields(event_id: int) -> dict:
    """Update cached event fields including writing questions and registration data.

    This function fetches an event and builds a hierarchical cache structure
    containing writing questions, options, and default field mappings organized
    by question applicability (e.g., 'player', 'character', etc.).

    Args:
        event_id: The primary key of the Event to update fields cache for.

    Returns:
        A nested dictionary containing cached event field data with structure:
        {
            'applicability_label': {
                'questions': {question_id: question_data, ...},
                'options': {option_id: option_data, ...},
                'names': {question_type: question_name, ...},
                'ids': {question_type: question_id, ...}
            }
        }

    """
    cached_fields = {}
    event = Event.objects.get(pk=event_id)

    # Fetch visible writing questions and organize by applicability
    visible_questions = (
        event.get_elements(WritingQuestion).exclude(visibility=QuestionVisibility.HIDDEN).order_by("order")
    )
    for question_data in visible_questions.values("id", "name", "typ", "printable", "visibility", "applicable"):
        applicability_label = QuestionApplicable(question_data["applicable"]).label
        _ensure_cache_structure(cached_fields, applicability_label, "questions")
        cached_fields[applicability_label]["questions"][question_data["id"]] = question_data

    # Fetch writing options and group by parent question's applicability
    writing_options = event.get_elements(WritingOption).order_by("order")
    for option_data in writing_options.values("id", "name", "question_id", "question__applicable"):
        applicability_label = QuestionApplicable(option_data["question__applicable"]).label
        _ensure_cache_structure(cached_fields, applicability_label, "options")
        cached_fields[applicability_label]["options"][option_data["id"]] = option_data

    # Create name and ID mappings for default writing question types
    default_type_questions = event.get_elements(WritingQuestion).filter(typ__in=get_def_writing_types())
    for question_data in default_type_questions.values("id", "typ", "name", "applicable"):
        applicability_label = QuestionApplicable(question_data["applicable"]).label
        question_type = question_data["typ"]
        _ensure_cache_structure(cached_fields, applicability_label, "names")
        _ensure_cache_structure(cached_fields, applicability_label, "ids")
        cached_fields[applicability_label]["names"][question_type] = question_data["name"]
        cached_fields[applicability_label]["ids"][question_type] = question_data["id"]

    # Cache the complete result structure with 1-day timeout
    cache.set(event_fields_key(event_id), cached_fields, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return cached_fields


def get_event_fields_cache(event_id: int) -> dict:
    """Get event fields from cache or update if not cached."""
    # Try to retrieve from cache
    cached_event_fields = cache.get(event_fields_key(event_id))

    # Update cache if not found
    if cached_event_fields is None:
        cached_event_fields = update_event_fields(event_id)

    return cached_event_fields


def _process_visible_questions(writing_fields_data: dict, *, only_visible: bool) -> tuple[dict, list[int], list[int]]:
    """Process questions and return visible ones with tracking lists.

    Args:
        writing_fields_data: Writing fields data containing questions
        only_visible: If True, filter to public and searchable only

    Returns:
        Tuple of (questions_dict, visible_question_ids, searchable_question_ids)
    """
    questions = {}
    visible_question_ids = []
    searchable_question_ids = []

    if "questions" not in writing_fields_data:
        return questions, visible_question_ids, searchable_question_ids

    for question_id, question_data in writing_fields_data["questions"].items():
        # Filter based on visibility settings
        if not only_visible or question_data["visibility"] in [
            QuestionVisibility.PUBLIC,
            QuestionVisibility.SEARCHABLE,
        ]:
            questions[question_id] = question_data
            visible_question_ids.append(question_data["id"])

        # Track searchable questions separately
        if question_data["visibility"] == QuestionVisibility.SEARCHABLE:
            searchable_question_ids.append(question_data["id"])

    return questions, visible_question_ids, searchable_question_ids


def visible_writing_fields(context: dict, applicable: QuestionApplicable, *, only_visible: bool = True) -> None:
    """Filter and cache visible writing fields based on visibility settings.

    This function processes writing fields from the context and filters them based on
    visibility rules, storing the results in separate categories for questions, options,
    and searchable fields.

    Args:
        context: Context dictionary to store filtered results. Must contain 'writing_fields'.
        applicable: QuestionApplicable enum value specifying the field type to process.
        only_visible: If True, includes only PUBLIC and SEARCHABLE fields. If False,
                     includes all fields regardless of visibility. Defaults to True.

    Returns:
        None: Results are stored directly in the context dictionary under 'questions',
              'options', and 'searchable' keys.

    """
    # Get the label key for the applicable question type
    applicable_type_key = QuestionApplicable(applicable).label

    # Initialize result containers in context
    context["questions"] = {}
    context["options"] = {}
    context["searchable"] = {}

    # Early return if no writing fields or key not found
    if "writing_fields" not in context or applicable_type_key not in context["writing_fields"]:
        return

    # Get the relevant writing fields data
    writing_fields_data = context["writing_fields"][applicable_type_key]

    # Process questions and get tracking lists
    questions, visible_question_ids, searchable_question_ids = _process_visible_questions(
        writing_fields_data, only_visible=only_visible
    )
    context["questions"] = questions

    # Process options if they exist, linking them to visible questions
    if "options" in writing_fields_data:
        for option_id, option_data in writing_fields_data["options"].items():
            # Include options for visible questions
            if option_data["question_id"] in visible_question_ids:
                context["options"][option_id] = option_data

            # Build searchable options mapping by question ID
            if option_data["question_id"] in searchable_question_ids:
                if option_data["question_id"] not in context["searchable"]:
                    context["searchable"][option_data["question_id"]] = []
                context["searchable"][option_data["question_id"]].append(option_data["id"])
