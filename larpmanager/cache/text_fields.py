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

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from larpmanager.models.form import (
    QuestionApplicable,
    QuestionType,
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


def get_single_cache_text_field(el_id, f, v):
    if v is None:
        v = ""
    red = remove_html_tags(v)
    ln = len(red)
    limit = conf_settings.FIELD_SNIPPET_LIMIT
    if ln > limit:
        red = red[:limit]
        red += f"... <a href='#' class='post_popup' pop='{el_id}' fie='{f}'><i class='fas fa-eye'></i></a>"
    res = (red, ln)
    return res


# Writing


def init_cache_text_field(typ, event):
    res = {}
    for el in typ.objects.filter(event=event.get_class_parent(typ)):
        _init_element_cache_text_field(el, res, typ)
    return res


def _init_element_cache_text_field(el, res, typ):
    if el.id not in res:
        res[el.id] = {}

    for f in ["teaser", "text"]:
        v = getattr(el, f)
        res[el.id][f] = get_single_cache_text_field(el.id, f, v)

    # noinspection PyProtectedMember
    applicable = QuestionApplicable.get_applicable(typ._meta.model_name)
    que = el.event.get_elements(WritingQuestion).filter(applicable=applicable)
    for que_id in que.filter(typ=QuestionType.EDITOR).values_list("pk", flat=True):
        els = WritingAnswer.objects.filter(question_id=que_id, element_id=el.id)
        if els:
            v = els.first().text
            field = str(que_id)
            res[el.id][field] = get_single_cache_text_field(el.id, field, v)


def get_cache_text_field(typ, event):
    key = cache_text_field_key(typ, event)
    res = cache.get(key)
    if not res:
        res = init_cache_text_field(typ, event)
        cache.set(key, res)
    return res


def update_cache_text_fields(el):
    typ = el.__class__
    event = el.event
    key = cache_text_field_key(typ, event)
    res = get_cache_text_field(typ, event)
    _init_element_cache_text_field(el, res, typ)
    cache.set(key, res)


def update_cache_text_fields_answer(instance):
    if instance.question.typ != QuestionType.EDITOR:
        return

    typ = QuestionApplicable.get_applicable_inverse(instance.question.applicable)
    event = instance.question.event

    key = cache_text_field_key(typ, event)
    res = get_cache_text_field(typ, event)
    field = str(instance.question_id)
    if instance.element_id not in res:
        res[instance.element_id] = {}
    res[instance.element_id][field] = get_single_cache_text_field(instance.element_id, field, instance.text)
    cache.set(key, res)


# Registration


def init_cache_reg_field(run):
    res = {}
    for el in Registration.objects.filter(run=run):
        _init_element_cache_reg_field(el, res)
    return res


def _init_element_cache_reg_field(el, res):
    if el.id not in res:
        res[el.id] = {}

    # noinspection PyProtectedMember
    que = RegistrationQuestion.objects.filter(event=el.run.event)
    for que_id in que.filter(typ=QuestionType.EDITOR).values_list("pk", flat=True):
        try:
            v = RegistrationAnswer.objects.get(question_id=que_id, reg_id=el.id).text
            field = str(que_id)
            res[el.id][field] = get_single_cache_text_field(el.id, field, v)
        except ObjectDoesNotExist:
            pass


def get_cache_reg_field(run):
    key = cache_text_field_key(Registration, run)
    res = cache.get(key)
    if not res:
        res = init_cache_reg_field(run)
        cache.set(key, res)
    return res


def update_cache_reg_fields(el):
    run = el.run
    key = cache_text_field_key(Registration, run)
    res = get_cache_reg_field(run)
    _init_element_cache_reg_field(el, res)
    cache.set(key, res)


def update_cache_reg_fields_answer(instance):
    if instance.question.typ != QuestionType.EDITOR:
        return

    run = instance.reg.run

    key = cache_text_field_key(Registration, run)
    res = get_cache_reg_field(run)
    field = str(instance.question_id)
    res[instance.reg_id][field] = get_single_cache_text_field(instance.reg_id, field, instance.text)
    cache.set(key, res)


@receiver(post_save)
def post_save_callback(sender, instance, *args, **kwargs):
    update_acc_callback(instance)


@receiver(post_delete)
def post_delete_callback(sender, instance, **kwargs):
    update_acc_callback(instance)


def update_acc_callback(instance):
    if issubclass(instance.__class__, Writing):
        update_cache_text_fields(instance)

    if issubclass(instance.__class__, WritingAnswer):
        update_cache_text_fields_answer(instance)

    if issubclass(instance.__class__, Registration):
        update_cache_reg_fields(instance)

    if issubclass(instance.__class__, RegistrationAnswer):
        update_cache_reg_fields_answer(instance)
