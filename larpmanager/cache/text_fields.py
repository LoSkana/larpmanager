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

import html as html_stdlib
import re
from typing import TYPE_CHECKING, Any

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.utils.html import escape

from larpmanager.cache.question import get_cached_registration_questions, get_cached_writing_questions
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    RegistrationAnswer,
    WritingAnswer,
)
from larpmanager.models.registration import Registration
from larpmanager.models.writing import Writing

if TYPE_CHECKING:
    from larpmanager.models.base import BaseModel
    from larpmanager.models.event import Event, Run

ALLOWED_TYPES = [BaseQuestionType.EDITOR, BaseQuestionType.PARAGRAPH]


def cache_text_field_key(model_type: type[BaseModel], model_instance: object) -> str:
    """Generate cache key for model text fields."""
    return f"cache_text_fields_{model_type.__name__}_{model_instance.id}"


def remove_html_tags(text: str) -> str:
    """Remove html tags from a string."""
    html_tag_pattern = re.compile("<.*?>")
    return re.sub(html_tag_pattern, "", text)


def get_single_cache_text_field(element_uuid: str, field_name: str, text_value: str | None) -> tuple[str, int]:
    """Get a single cache text field with optional truncation and popup link.

    Args:
        element_uuid: Element ID for the popup link
        field_name: Field name for the popup link
        text_value: Text value to process, can be None

    Returns:
        A tuple containing the processed text and its original length

    """
    # Handle None values by setting to empty string
    if text_value is None:
        text_value = ""

    # Remove HTML tags, then unescape HTML entities to actual Unicode characters
    cleaned_text = html_stdlib.unescape(remove_html_tags(text_value))

    # Get the length of the cleaned text
    original_length = len(cleaned_text)

    # Get the snippet limit from configuration
    limit = conf_settings.FIELD_SNIPPET_LIMIT

    truncated = original_length > limit

    # Truncate on actual characters before re-escaping
    if truncated:
        cleaned_text = cleaned_text[:limit]

    # Escape for XSS prevention after truncation
    cleaned_text = escape(cleaned_text)

    if truncated:
        cleaned_text += (
            f"... <a href='#' class='post_popup' pop='{element_uuid}' fie='{field_name}'><i class='fas fa-eye'></i></a>"
        )

    # Return the processed text and original length
    return cleaned_text, original_length


# Writing


def init_cache_text_field(model_class: type[BaseModel], event: Event) -> dict:
    """Initialize cache for text fields of model instances related to an event."""
    cache_result = {}
    # Iterate through all instances of the given type for the event's parent
    for instance in model_class.objects.filter(event=event.get_class_parent(model_class)):
        _init_element_cache_text_field(instance, cache_result, model_class)
    return cache_result


def _init_element_cache_text_field(
    element: BaseModel,
    result_cache: dict[str, dict[str, Any]],
    element_type: Any,
) -> None:
    """Initialize cache for text fields of a single element.

    This function populates the cache dictionary with text field data for a given element,
    including basic text fields (teaser, text) and editor-type writing questions.

    Args:
        element: Element instance to cache text fields for
        result_cache: Result dictionary to populate with cached text data
        element_type: Element type class for determining applicable questions

    Returns:
        None

    Side Effects:
        Populates result_cache[element.uuid] with cached text field data including teaser, text,
        and editor questions

    """
    # Get element UUID for cache key
    element_uuid = str(element.uuid)

    # Initialize element entry in result dictionary if not exists
    if element_uuid not in result_cache:
        result_cache[element_uuid] = {}

    # Cache basic text fields (teaser and text)
    for field_name in ["teaser", "text"]:
        field_value = getattr(element, field_name)
        result_cache[element_uuid][field_name] = get_single_cache_text_field(element_uuid, field_name, field_value)

    # Get applicable writing questions for this element type
    applicable = QuestionApplicable.get_applicable(element_type._meta.model_name)  # noqa: SLF001  # Django model metadata
    questions = get_cached_writing_questions(element.event, applicable)

    # Process editor-type questions and cache their answers
    for question in [q for q in questions if q["typ"] in ALLOWED_TYPES]:
        field_key = question["uuid"]
        if field_key in result_cache[element_uuid]:
            continue

        answers = WritingAnswer.objects.filter(question_id=question["id"], element_id=element.id).order_by("-updated")
        if not answers:
            continue

        # Cache the text content of the first matching answer
        answer_text = answers.first().text
        result_cache[element_uuid][field_key] = get_single_cache_text_field(element_uuid, field_key, answer_text)


def get_cache_text_field(field_type: type[BaseModel], event: Event) -> str:
    """Get cached text field value for event, initializing if not found."""
    # Generate cache key for the specific type and event
    cache_key = cache_text_field_key(field_type, event)

    # Try to retrieve cached value
    cached_value = cache.get(cache_key)

    # Initialize and cache if not found
    if cached_value is None:
        cached_value = init_cache_text_field(field_type, event)
        cache.set(cache_key, cached_value, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_value


def update_cache_text_fields(el: object) -> None:
    """Update cache for text fields of the given element.

    Args:
        el: Element object to update cache for

    """
    # Get element type and associated event
    element_type = el.__class__
    event = el.event

    # Generate cache key
    cache_key = cache_text_field_key(element_type, event)

    # Use cache lock to prevent race conditions with concurrent updates
    lock_key = f"{cache_key}_lock"
    try:
        with cache.lock(lock_key, timeout=5):
            _update_cache_text_fields(cache_key, el, element_type, event)
    except AttributeError:
        # Fallback for cache backends that don't support locking
        _update_cache_text_fields(cache_key, el, element_type, event)


def _update_cache_text_fields(cache_key: str, el: object, element_type: type[BaseModel], event: Event) -> None:
    """Update cache for text fields - internal helper."""
    # Retrieve current cache data inside lock
    cached_data = get_cache_text_field(element_type, event)
    # Initialize element cache and update cache storage
    _init_element_cache_text_field(el, cached_data, element_type)
    cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


def update_cache_text_fields_answer(instance: BaseModel) -> None:
    """Update cache with text field answer data for editor-type questions.

    Updates the cached text field answers when a new answer is provided for
    an editor-type question. The cache is organized by question type and event,
    with answers stored by element ID and question ID.

    Args:
        instance: Answer instance containing question, element_id, and text data.
            Must have question, element_id, question_id, and text attributes.

    """
    # Only process editor-type questions
    if instance.question.typ not in ALLOWED_TYPES:
        return

    # Get the applicable type and event for cache key generation
    applicable_type = QuestionApplicable.get_applicable_inverse(instance.question.applicable)
    event = instance.question.event

    # Generate cache key
    cache_key = cache_text_field_key(applicable_type, event)

    # Use cache lock to prevent race conditions with concurrent updates
    lock_key = f"{cache_key}_lock"
    try:
        with cache.lock(lock_key, timeout=5):
            _update_cache_text_fields_answer(applicable_type, cache_key, event, instance)
    except AttributeError:
        # Fallback for cache backends that don't support locking
        _update_cache_text_fields_answer(applicable_type, cache_key, event, instance)


def _update_cache_text_fields_answer(
    applicable_type: type[BaseModel],
    cache_key: str,
    event: Event,
    instance: BaseModel,
) -> None:
    """Update cache for editor-type question answer - internal helper.

    This is a helper function used by update_cache_text_fields_answer to avoid
    code duplication in the lock try-except block. Updates a single editor question
    answer in the cache.

    Args:
        applicable_type: Model class type that the question applies to (e.g., Character)
        cache_key: The cache key to update
        event: Event instance associated with the answer
        instance: WritingAnswer instance containing the question, element_id, and text data

    """
    # Retrieve existing cached data inside lock
    cached_text_fields = get_cache_text_field(applicable_type, event)

    # Fetch the element to get its UUID
    try:
        element = applicable_type.objects.get(id=instance.element_id)
        element_uuid = str(element.uuid)
    except ObjectDoesNotExist:
        # If element doesn't exist, skip cache update
        return

    # Prepare field identifier and ensure element structure exists
    question_field_id = instance.question.uuid
    if element_uuid not in cached_text_fields:
        cached_text_fields[element_uuid] = {}

    # Update cache with new text field data and persist to cache
    cached_text_fields[element_uuid][question_field_id] = get_single_cache_text_field(
        element_uuid,
        question_field_id,
        instance.text,
    )

    cache.set(cache_key, cached_text_fields, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


# Registration


def init_cache_registration_field(run: Run) -> dict:
    """Initialize registration field cache for all registrations in a run."""
    cache_data = {}
    # Iterate through all registrations for this run and populate cache
    for registration in Registration.objects.filter(run=run):
        _init_element_cache_registration_field(registration, cache_data)
    return cache_data


def _init_element_cache_registration_field(registration: Registration, cache_result: dict[str, dict[str, Any]]) -> None:
    """Initialize cache for registration element fields.

    Args:
        registration: Registration element to process
        cache_result: Result dictionary to populate with cached data

    """
    # Get registration UUID for cache key
    registration_uuid = str(registration.uuid)

    # Initialize element entry in result dictionary if not present
    if registration_uuid not in cache_result:
        cache_result[registration_uuid] = {}

    # Get all editor/paragraph-type questions for the event
    questions = [
        question
        for question in get_cached_registration_questions(registration.run.event)
        if question["typ"] in ALLOWED_TYPES
    ]

    # Process each editor question and cache the answer text
    for question in questions:
        try:
            answer_text = RegistrationAnswer.objects.get(
                question_id=question["id"], registration_id=registration.id
            ).text
            field_key = str(question["uuid"])
            cache_result[registration_uuid][field_key] = get_single_cache_text_field(
                registration_uuid,
                field_key,
                answer_text,
            )
        except ObjectDoesNotExist:
            pass


def get_cache_registration_field(run: Run) -> dict:
    """Get cached registration field data for a run.

    Args:
        run: The run instance to get cached registration fields for.

    Returns:
        Dictionary containing cached registration field data.

    """
    # Generate cache key for the run's registration fields
    cache_key = cache_text_field_key(Registration, run)

    # Try to retrieve cached result
    cached_result = cache.get(cache_key)

    # If not cached, initialize and cache the result
    if cached_result is None:
        cached_result = init_cache_registration_field(run)
        cache.set(cache_key, cached_result, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_result


def update_cache_registration_fields(registration: Registration) -> None:
    """Update cached registration fields for the given element's run."""
    # Get the run associated with the registration element
    run = registration.run

    # Generate cache key and retrieve current cached registration fields
    cache_key = cache_text_field_key(Registration, run)
    cached_registration_fields = get_cache_registration_field(run)

    # Initialize element cache and update cache with new data
    _init_element_cache_registration_field(registration, cached_registration_fields)
    cache.set(cache_key, cached_registration_fields, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


def update_cache_registration_fields_answer(instance: BaseModel) -> None:
    """Update cached registration field answers for editor-type questions.

    This function updates the cache with new text field answers when a registration
    answer is modified. Only processes editor-type questions to maintain text field
    cache consistency.

    Args:
        instance: The registration answer instance containing question, registration,
                 and text data to be cached.

    Returns:
        None

    """
    # Skip processing if question is not an editor or paragraph type
    if instance.question.typ not in ALLOWED_TYPES:
        return

    # Get the run context from the registration
    run = instance.registration.run

    # Generate cache key and retrieve current cached field data
    cache_key = cache_text_field_key(Registration, run)
    cached_registration_fields = get_cache_registration_field(run)

    # Fetch the registration to get its UUID
    try:
        registration = Registration.objects.get(id=instance.registration_id)
        registration_uuid = str(registration.uuid)
    except ObjectDoesNotExist:
        # If registration doesn't exist, skip cache update
        return

    # Ensure registration structure exists in cache
    if registration_uuid not in cached_registration_fields:
        cached_registration_fields[registration_uuid] = {}

    # Update the specific field for this registration with new text content
    question_field = str(instance.question.uuid)
    cached_registration_fields[registration_uuid][question_field] = get_single_cache_text_field(
        registration_uuid,
        question_field,
        instance.text,
    )

    # Store updated cache data with 1-day timeout
    cache.set(cache_key, cached_registration_fields, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


def update_text_fields_cache(model_instance: object) -> None:
    """Update text fields cache for various model instances.

    This function determines the type of the given instance and calls the
    appropriate cache update function based on the instance's class type.
    Supports Writing, WritingAnswer, Registration, and RegistrationAnswer models.

    Args:
        model_instance: Model instance to update cache for. Can be Writing, WritingAnswer,
                 Registration, or RegistrationAnswer type.

    Returns:
        None

    """
    # Update cache for Writing model instances
    if issubclass(model_instance.__class__, Writing):
        update_cache_text_fields(model_instance)

    # Update cache for WritingAnswer model instances
    if issubclass(model_instance.__class__, WritingAnswer):
        update_cache_text_fields_answer(model_instance)

    # Update cache for Registration model instances
    if issubclass(model_instance.__class__, Registration):
        update_cache_registration_fields(model_instance)

    # Update cache for RegistrationAnswer model instances
    if issubclass(model_instance.__class__, RegistrationAnswer):
        update_cache_registration_fields_answer(model_instance)


def reset_text_fields_cache(run: Run) -> None:
    """Reset all text fields cache for a run."""
    # Invalidate text field caches for all Writing model types
    for applicable_type in ["character", "faction", "plot", "quest", "trait", "prologue"]:
        # Get the model class for this applicable type
        try:
            applicable_code = QuestionApplicable.get_applicable(applicable_type)
            if applicable_code:
                model_class = QuestionApplicable.get_applicable_inverse(applicable_code)
                # Delete cache for this model type and event
                cache_key = cache_text_field_key(model_class, run.event)
                cache.delete(cache_key)
        except (ValueError, LookupError):
            # Skip if applicable type doesn't exist
            pass

    # Invalidate registration text field cache
    cache_key = cache_text_field_key(Registration, run)
    cache.delete(cache_key)
