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

from django.core.cache import cache
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils.translation import get_language

from larpmanager.models.association import AssocText
from larpmanager.models.event import EventText


def event_text_key(event_id, typ, lang):
    return f"event_text_{event_id}_{typ}_{lang}"


def update_event_text(event_id, typ, lang):
    res = None
    try:
        res = EventText.objects.get(event_id=event_id, typ=typ, language=lang).text
    except Exception:
        pass
    cache.set(event_text_key(event_id, typ, lang), res)
    return res


def get_event_text_cache(event_id, typ, lang):
    res = cache.get(event_text_key(event_id, typ, lang))
    if not res:
        res = update_event_text(event_id, typ, lang)
    return res


def event_text_key_def(event_id, typ):
    return f"event_text_def_{event_id}_{typ}"


def update_event_text_def(event_id, typ):
    res = None
    try:
        res = EventText.objects.filter(event_id=event_id, typ=typ, default=True).first().text
    except Exception:
        pass
    cache.set(event_text_key_def(event_id, typ), res)
    return res


def get_event_text_cache_def(event_id, typ):
    res = cache.get(event_text_key_def(event_id, typ))
    if not res:
        res = update_event_text_def(event_id, typ)
    return res


def get_event_text(event_id, typ, lang=None):
    if not lang:
        lang = get_language()

    # check if there is an event_text with the requested charateristics
    res = get_event_text_cache(event_id, typ, lang)
    if res:
        return res

    return get_event_text_cache_def(event_id, typ)


# # ASSOC TEXT


@receiver(post_save, sender=AssocText)
def save_assoc_text(sender, instance, created, **kwargs):
    handle_assoc_text_save(instance)


def handle_assoc_text_save(instance):
    update_assoc_text(instance.assoc_id, instance.typ, instance.language)
    if instance.default:
        update_assoc_text_def(instance.assoc_id, instance.typ)


@receiver(pre_delete, sender=AssocText)
def delete_assoc_text(sender, instance, **kwargs):
    handle_assoc_text_del(instance)


def handle_assoc_text_del(instance):
    cache.delete(assoc_text_key(instance.assoc_id, instance.typ, instance.language))
    if instance.default:
        cache.delete(assoc_text_key_def(instance.assoc_id, instance.typ))


# ## EVENT TEXT


@receiver(post_save, sender=EventText)
def save_event_text(sender, instance, created, **kwargs):
    handle_event_text_save(instance)


def handle_event_text_save(instance):
    update_event_text(instance.event_id, instance.typ, instance.language)
    if instance.default:
        update_event_text_def(instance.event_id, instance.typ)


@receiver(pre_delete, sender=EventText)
def delete_event_text(sender, instance, **kwargs):
    handle_event_text_del(instance)


def handle_event_text_del(instance):
    cache.delete(event_text_key(instance.event_id, instance.typ, instance.language))
    if instance.default:
        cache.delete(event_text_key_def(instance.event_id, instance.typ))


# Text cache


def assoc_text_key(assoc_id, typ, lang):
    return f"assoc_text_{assoc_id}_{typ}_{lang}"


def update_assoc_text(assoc_id, typ, lang):
    res = None
    try:
        res = AssocText.objects.get(assoc_id=assoc_id, typ=typ, language=lang).text
    except Exception:
        pass
    cache.set(assoc_text_key(assoc_id, typ, lang), res)
    return res


def get_assoc_text_cache(assoc_id, typ, lang):
    res = cache.get(assoc_text_key(assoc_id, typ, lang))
    if not res:
        res = update_assoc_text(assoc_id, typ, lang)
    return res


# default it


def assoc_text_key_def(assoc_id, typ):
    return f"assoc_text_def_{assoc_id}_{typ}"


def update_assoc_text_def(assoc_id, typ):
    res = None
    try:
        res = AssocText.objects.filter(assoc_id=assoc_id, typ=typ, default=True).first().text
    except Exception:
        pass
    cache.set(assoc_text_key_def(assoc_id, typ), res)
    return res


def get_assoc_text_cache_def(assoc_id, typ):
    res = cache.get(assoc_text_key_def(assoc_id, typ))
    if not res:
        res = update_assoc_text_def(assoc_id, typ)
    return res


def get_assoc_text(assoc_id, typ, lang=None):
    if not lang:
        lang = get_language()

    # check if there is an assoc_text with the requested charateristics
    res = get_assoc_text_cache(assoc_id, typ, lang)
    if res:
        return res

    return get_assoc_text_cache_def(assoc_id, typ)
