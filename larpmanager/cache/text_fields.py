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

import re
from typing import Any

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.models.base import BaseModel
from larpmanager.models.event import Run
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    RegistrationAnswer,
    RegistrationQuestion,
    WritingAnswer,
    WritingQuestion,
)
from larpmanager.models.registration import Registration
from larpmanager.models.writing import Writing


def cache_text_field_key(typ, element):
    return f"cache_text_fields_{typ.__name__}_{element.id}"


def remove_html_tags(text):
    """Remove html tags from a string"""
    clean = re.compile("<.*?>")
    return re.sub(clean, "", text)


def get_single_cache_text_field(el_id: str, f: str, v: str | None) -> tuple[str, int]:
    """Get a single cache text field with optional truncation and popup link.

    Args:
        el_id: Element ID for the popup link
        f: Field name for the popup link
        v: Text value to process, can be None

    Returns:
        A tuple containing the processed text and its original length
    """
    # Handle None values by setting to empty string
    if v is None:
        v = ""

    # Remove HTML tags from the text value
    red = remove_html_tags(v)

    # Get the length of the cleaned text
    ln = len(red)

    # Get the snippet limit from configuration
    limit = conf_settings.FIELD_SNIPPET_LIMIT

    # Truncate text if it exceeds the limit and add popup link
    if ln > limit:
        red = red[:limit]
        red += f"... <a href='#' class='post_popup' pop='{el_id}' fie='{f}'><i class='fas fa-eye'></i></a>"

    # Return the processed text and original length
    res = (red, ln)
    return res


# Writing


def init_cache_text_field(typ, event):
    res = {}
    for el in typ.objects.filter(event=event.get_class_parent(typ)):
        _init_element_cache_text_field(el, res, typ)
    return res


def _init_element_cache_text_field(el: BaseModel, res: dict[int, dict[str, Any]], typ: Any) -> None:
    """Initialize cache for text fields of a single element.

    This function populates the cache dictionary with text field data for a given element,
    including basic text fields (teaser, text) and editor-type writing questions.

    Args:
        el: Element instance to cache text fields for
        res: Result dictionary to populate with cached text data
        typ: Element type class for determining applicable questions

    Returns:
        None

    Side Effects:
        Populates res[el.id] with cached text field data including teaser, text,
        and editor questions
    """
    # Initialize element entry in result dictionary if not exists
    if el.id not in res:
        res[el.id] = {}

    # Cache basic text fields (teaser and text)
    for f in ["teaser", "text"]:
        v = getattr(el, f)
        res[el.id][f] = get_single_cache_text_field(el.id, f, v)

    # Get applicable writing questions for this element type
    # noinspection PyProtectedMember
    applicable = QuestionApplicable.get_applicable(typ._meta.model_name)
    que = el.event.get_elements(WritingQuestion).filter(applicable=applicable)

    # Process editor-type questions and cache their answers
    for que_id in que.filter(typ=BaseQuestionType.EDITOR).values_list("pk", flat=True):
        els = WritingAnswer.objects.filter(question_id=que_id, element_id=el.id)
        if els:
            # Cache the text content of the first matching answer
            v = els.first().text
            field = str(que_id)
            res[el.id][field] = get_single_cache_text_field(el.id, field, v)


def get_cache_text_field(typ: str, event: object) -> str:
    """Get cached text field value for a given type and event.

    Retrieves a cached text field value. If not found in cache, initializes
    the value and stores it in cache for future use.

    Args:
        typ: The type identifier for the text field
        event: The event object to get the text field for

    Returns:
        The cached or newly initialized text field value
    """
    # Generate cache key for the text field
    key = cache_text_field_key(typ, event)

    # Attempt to retrieve value from cache
    res = cache.get(key)

    # If not in cache, initialize and store the value
    if res is None:
        res = init_cache_text_field(typ, event)
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def update_cache_text_fields(el: object) -> None:
    """Update cache for text fields of a given element.

    This function retrieves the current cached text fields for an element's type
    and event, initializes the element's cache, and updates the cache with a
    1-day timeout.

    Args:
        el: The element object containing event and class information for caching.
    """
    # Get element type and associated event
    typ = el.__class__
    event = el.event

    # Generate cache key and retrieve current cached data
    key = cache_text_field_key(typ, event)
    res = get_cache_text_field(typ, event)

    # Initialize element cache and update with new data
    _init_element_cache_text_field(el, res, typ)
    cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


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
    if instance.question.typ != BaseQuestionType.EDITOR:
        return

    # Get the applicable type and event for cache key generation
    typ = QuestionApplicable.get_applicable_inverse(instance.question.applicable)
    event = instance.question.event

    # Generate cache key and retrieve existing cached data
    key = cache_text_field_key(typ, event)
    res = get_cache_text_field(typ, event)

    # Prepare field identifier and ensure element structure exists
    field = str(instance.question_id)
    if instance.element_id not in res:
        res[instance.element_id] = {}

    # Update cache with new text field data and persist to cache
    res[instance.element_id][field] = get_single_cache_text_field(instance.element_id, field, instance.text)
    cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


# Registration


def init_cache_reg_field(run):
    res = {}
    for el in Registration.objects.filter(run=run):
        _init_element_cache_reg_field(el, res)
    return res


def _init_element_cache_reg_field(el: Registration, res: dict[int, dict[str, str]]) -> None:
    """Initialize registration field cache for a given element.

    Populates the cache dictionary with registration answers for EDITOR type questions
    associated with the element's event.

    Args:
        el: Registration instance to process
        res: Cache dictionary to populate, keyed by registration ID then field name
    """
    # Initialize cache entry for this registration if not exists
    if el.id not in res:
        res[el.id] = {}

    # Get all registration questions for the event
    # noinspection PyProtectedMember
    que = RegistrationQuestion.objects.filter(event_id=el.run.event_id)

    # Process only EDITOR type questions
    for que_id in que.filter(typ=BaseQuestionType.EDITOR).values_list("pk", flat=True):
        try:
            # Retrieve the answer text for this question and registration
            v = RegistrationAnswer.objects.get(question_id=que_id, reg_id=el.id).text
            field = str(que_id)

            # Cache the processed text field value
            res[el.id][field] = get_single_cache_text_field(el.id, field, v)
        except ObjectDoesNotExist:
            # Skip if no answer exists for this question
            pass


def get_cache_reg_field(run: Run) -> dict:
    """Retrieve cached registration field data for a given run.

    This function implements a cache-aside pattern to store and retrieve
    registration field configurations. If the data is not in cache, it
    initializes the cache with fresh data.

    Args:
        run: The Run instance for which to retrieve registration field data.

    Returns:
        Dictionary containing the cached registration field configuration.
    """
    # Generate the cache key for this specific run's registration fields
    key = cache_text_field_key(Registration, run)

    # Attempt to retrieve cached data
    res = cache.get(key)

    # If cache miss, initialize and store the data
    if res is None:
        res = init_cache_reg_field(run)
        # Cache for 24 hours to balance performance and data freshness
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return res


def update_cache_reg_fields(el):
    run = el.run
    key = cache_text_field_key(Registration, run)
    res = get_cache_reg_field(run)
    _init_element_cache_reg_field(el, res)
    cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


def update_cache_reg_fields_answer(instance: BaseModel) -> None:
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
    # Skip processing if question is not an editor type
    if instance.question.typ != BaseQuestionType.EDITOR:
        return

    # Get the run context from the registration
    run = instance.reg.run

    # Generate cache key and retrieve current cached field data
    key = cache_text_field_key(Registration, run)
    res = get_cache_reg_field(run)

    # Update the specific field for this registration with new text content
    field = str(instance.question_id)
    res[instance.reg_id][field] = get_single_cache_text_field(instance.reg_id, field, instance.text)

    # Store updated cache data with 1-day timeout
    cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


def update_text_fields_cache(instance: object) -> None:
    """Update text fields cache for various model instances.

    This function determines the type of the given instance and calls the
    appropriate cache update function based on the instance's class type.
    Supports Writing, WritingAnswer, Registration, and RegistrationAnswer models.

    Args:
        instance: Model instance to update cache for. Can be Writing, WritingAnswer,
                 Registration, or RegistrationAnswer type.

    Returns:
        None
    """
    # Update cache for Writing model instances
    if issubclass(instance.__class__, Writing):
        update_cache_text_fields(instance)

    # Update cache for WritingAnswer model instances
    if issubclass(instance.__class__, WritingAnswer):
        update_cache_text_fields_answer(instance)

    # Update cache for Registration model instances
    if issubclass(instance.__class__, Registration):
        update_cache_reg_fields(instance)

    # Update cache for RegistrationAnswer model instances
    if issubclass(instance.__class__, RegistrationAnswer):
        update_cache_reg_fields_answer(instance)
