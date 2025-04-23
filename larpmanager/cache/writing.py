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

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from larpmanager.models.event import RunText
from larpmanager.models.writing import Character, Writing


def cache_text_field_key(typ, event):
    return f"cache_text_field_{typ.__name__}_{event.id}"


def remove_html_tags(text):
    """Remove html tags from a string"""
    clean = re.compile("<.*?>")
    return re.sub(clean, "", text)


def get_single_cache_text_field(el, f, v):
    if v is None:
        v = ""
    red = remove_html_tags(v)
    ln = len(red)
    limit = 80
    if f == "text":
        limit = 200
    if ln > limit:
        red = red[:limit]
        red += f"... <a href='#' class='post_popup' pop='{el.number}' fie='{f}'><i class='fas fa-eye'></i></a>"
    res = (red, ln)
    return res


def init_cache_text_field(typ, event):
    res = {}
    for el in typ.objects.filter(event=event.get_class_parent(typ)):
        update_element_cache_text_field(el, res)
    return res


def update_element_cache_text_field(el, res):
    if el.number not in res:
        res[el.number] = {}

    for f in ["concept", "teaser", "text", "preview"]:
        v = getattr(el, f)
        res[el.number][f] = get_single_cache_text_field(el, f, v)


def get_cache_text_field(typ, event, el=None):
    key = cache_text_field_key(typ, event)
    res = cache.get(key)
    if not res:
        res = init_cache_text_field(typ, event)
        cache.set(key, res)
    if el:
        update_element_cache_text_field(el, res)
        cache.set(key, res)
    return res


def update_cache_text_fields(el):
    get_cache_text_field(el.__class__, el.event, el)


def cache_cocreation_key(run):
    return f"cocreation_{run.id}"


def init_cache_cocreation(run):
    res = {}

    for rt in RunText.objects.filter(run=run, typ=RunText.COCREATION):
        update_element_cache_cocreation(rt, res, run)

    return res


def update_element_cache_cocreation(rt, res, run):
    try:
        el = Character.objects.get(event=run.event.get_class_parent("character"), number=rt.eid)
    except ObjectDoesNotExist:
        return

    res[el.number] = {
        "co_creation_question": get_single_cache_text_field(el, "co_creation_question", rt.first),
        "co_creation_answer": get_single_cache_text_field(el, "co_creation_answer", rt.second),
    }
    return


def get_cache_cocreation(run, el=None):
    key = cache_cocreation_key(run)
    res = cache.get(key)
    if not res:
        res = init_cache_cocreation(run)
        cache.set(key, res)
    if el:
        update_element_cache_cocreation(el, res, run)
        cache.set(key, res)
    return res


@receiver(post_save, sender=RunText)
def update_cache_text_field_RunText(sender, instance, **kwargs):
    if instance.typ == RunText.COCREATION:
        get_cache_cocreation(instance.run, instance)


@receiver(post_save)
def post_save_callback(sender, instance, *args, **kwargs):
    update_acc_callback(instance)


@receiver(post_delete)
def post_delete_callback(sender, instance, **kwargs):
    update_acc_callback(instance, True)


def update_acc_callback(instance, delete=False):
    if issubclass(instance.__class__, Writing):
        update_cache_text_fields(instance)
