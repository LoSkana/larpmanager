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


def event_fields_key(event_id):
    return f"event_fields_{event_id}"


def clear_event_fields_cache(event_id):
    cache.delete(event_fields_key(event_id))


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
    res = {}
    event = Event.objects.get(pk=event_id)

    # Fetch visible writing questions and organize by applicability
    que = event.get_elements(WritingQuestion).exclude(visibility=QuestionVisibility.HIDDEN).order_by("order")
    for el in que.values("id", "name", "typ", "printable", "visibility", "applicable"):
        first_key = QuestionApplicable(el["applicable"]).label
        # Initialize nested dictionary structure for each applicability type
        if first_key not in res:
            res[first_key] = {}
        if "questions" not in res[first_key]:
            res[first_key]["questions"] = {}
        res[first_key]["questions"][el["id"]] = el

    # Fetch writing options and group by parent question's applicability
    que = event.get_elements(WritingOption).order_by("order")
    for el in que.values("id", "name", "question_id", "question__applicable"):
        first_key = QuestionApplicable(el["question__applicable"]).label
        # Ensure options section exists in the nested structure
        if first_key not in res:
            res[first_key] = {}
        if "options" not in res[first_key]:
            res[first_key]["options"] = {}
        res[first_key]["options"][el["id"]] = el

    # Create name and ID mappings for default writing question types
    que = event.get_elements(WritingQuestion).filter(typ__in=get_def_writing_types())
    for el in que.values("id", "typ", "name", "applicable"):
        first_key = QuestionApplicable(el["applicable"]).label
        second_key = el["typ"]
        # Initialize names and ids dictionaries for quick type-based lookups
        if first_key not in res:
            res[first_key] = {}
        if "names" not in res[first_key]:
            res[first_key]["names"] = {}
        res[first_key]["names"][second_key] = el["name"]
        if "ids" not in res[first_key]:
            res[first_key]["ids"] = {}
        res[first_key]["ids"][second_key] = el["id"]

    # Cache the complete result structure with 1-day timeout
    cache.set(event_fields_key(event_id), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def get_event_fields_cache(event_id: int) -> dict:
    """Get event fields from cache or update if not cached."""
    # Try to retrieve from cache
    res = cache.get(event_fields_key(event_id))

    # Update cache if not found
    if res is None:
        res = update_event_fields(event_id)

    return res


def visible_writing_fields(context: dict, applicable: QuestionApplicable, only_visible: bool = True) -> None:
    """
    Filter and cache visible writing fields based on visibility settings.

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

    # Initialize tracking lists for question and searchable IDs
    visible_question_ids = []
    searchable_question_ids = []

    # Process questions if they exist in the data
    if "questions" in writing_fields_data:
        for question_id, question_data in writing_fields_data["questions"].items():
            # Filter based on visibility settings
            if not only_visible or question_data["visibility"] in [
                QuestionVisibility.PUBLIC,
                QuestionVisibility.SEARCHABLE,
            ]:
                context["questions"][question_id] = question_data
                visible_question_ids.append(question_data["id"])

            # Track searchable questions separately
            if question_data["visibility"] == QuestionVisibility.SEARCHABLE:
                searchable_question_ids.append(question_data["id"])

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
