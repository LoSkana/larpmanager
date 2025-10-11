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
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

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


def reset_event_fields_cache(event_id):
    cache.delete(event_fields_key(event_id))


def update_event_fields(event_id):
    """Update cached event fields including writing questions and registration data.

    Args:
        event_id: Event ID to update fields cache for

    Returns:
        dict: Updated event fields cache data
    """
    res = {}
    event = Event.objects.get(pk=event_id)

    # add questions
    que = event.get_elements(WritingQuestion).exclude(visibility=QuestionVisibility.HIDDEN).order_by("order")
    for el in que.values("id", "name", "typ", "printable", "visibility", "applicable"):
        first_key = QuestionApplicable(el["applicable"]).label
        if first_key not in res:
            res[first_key] = {}
        if "questions" not in res[first_key]:
            res[first_key]["questions"] = {}
        res[first_key]["questions"][el["id"]] = el

    # add options
    que = event.get_elements(WritingOption).order_by("order")
    for el in que.values("id", "name", "question_id", "question__applicable"):
        first_key = QuestionApplicable(el["question__applicable"]).label
        if first_key not in res:
            res[first_key] = {}
        if "options" not in res[first_key]:
            res[first_key]["options"] = {}
        res[first_key]["options"][el["id"]] = el

    # add default names and ids
    que = event.get_elements(WritingQuestion).filter(typ__in=get_def_writing_types())
    for el in que.values("id", "typ", "name", "applicable"):
        first_key = QuestionApplicable(el["applicable"]).label
        second_key = el["typ"]
        if first_key not in res:
            res[first_key] = {}
        if "names" not in res[first_key]:
            res[first_key]["names"] = {}
        res[first_key]["names"][second_key] = el["name"]
        if "ids" not in res[first_key]:
            res[first_key]["ids"] = {}
        res[first_key]["ids"][second_key] = el["id"]

    cache.set(event_fields_key(event_id), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def get_event_fields_cache(event_id):
    res = cache.get(event_fields_key(event_id))
    if res is None:
        res = update_event_fields(event_id)
    return res


def visible_writing_fields(ctx, applicable, only_visible=True):
    """
    Filter and cache visible writing fields based on visibility settings.

    Args:
        ctx: Context dictionary to store filtered results
        applicable: QuestionApplicable enum value for field type
        only_visible: Whether to include only visible fields (default: True)
    """
    key = QuestionApplicable(applicable).label

    ctx["questions"] = {}
    ctx["options"] = {}
    ctx["searchable"] = {}

    if "writing_fields" not in ctx or key not in ctx["writing_fields"]:
        return

    res = ctx["writing_fields"][key]

    question_ids = []
    searcheable_ids = []

    if "questions" in res:
        for id, el in res["questions"].items():
            if not only_visible or el["visibility"] in [QuestionVisibility.PUBLIC, QuestionVisibility.SEARCHABLE]:
                ctx["questions"][id] = el
                question_ids.append(el["id"])

            if el["visibility"] == QuestionVisibility.SEARCHABLE:
                searcheable_ids.append(el["id"])

    if "options" in res:
        for id, el in res["options"].items():
            if el["question_id"] in question_ids:
                ctx["options"][id] = el

            if el["question_id"] in searcheable_ids:
                if el["question_id"] not in ctx["searchable"]:
                    ctx["searchable"][el["question_id"]] = []
                ctx["searchable"][el["question_id"]].append(el["id"])


@receiver(pre_delete, sender=WritingQuestion)
def del_character_question_reset(sender, instance, **kwargs):
    reset_event_fields_cache(instance.event_id)


@receiver(post_save, sender=WritingQuestion)
def save_fieldsquestion_reset(sender, instance, **kwargs):
    reset_event_fields_cache(instance.event_id)


@receiver(pre_delete, sender=WritingOption)
def del_fieldsoption_reset(sender, instance, **kwargs):
    reset_event_fields_cache(instance.question.event_id)


@receiver(post_save, sender=WritingOption)
def save_fieldsoption_reset(sender, instance, **kwargs):
    reset_event_fields_cache(instance.question.event_id)
