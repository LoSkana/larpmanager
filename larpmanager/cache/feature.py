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
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_save
from django.dispatch import receiver

from larpmanager.models.association import Association
from larpmanager.models.event import Event


def reset_assoc_features(assoc_id):
    cache.delete(cache_assoc_features(assoc_id))


def cache_assoc_features(assoc_id):
    return f"assoc_features_{assoc_id}"


def get_assoc_features(assoc_id):
    key = cache_assoc_features(assoc_id)
    res = cache.get(key)
    if not res:
        res = update_assoc_features(assoc_id)
        cache.set(key, res)
    return res


def update_assoc_features(assoc_id):
    res = {}
    try:
        assoc = Association.objects.get(pk=assoc_id)
        for s in assoc.features.values_list("slug", flat=True):
            res[s] = 1
        for sl in [
            "genre",
            "show_event",
            "website",
            "past_events",
            "description",
            "where",
            "authors",
            "visible",
            "tagline",
        ]:
            if assoc.get_config("calendar_" + sl, False):
                res[sl] = 1

        for slug in ["safety", "diet"]:
            if slug in assoc.mandatory_fields or slug in assoc.optional_fields:
                res[slug] = 1

    except ObjectDoesNotExist:
        pass
    return res


def reset_event_features(ev_id):
    cache.delete(cache_event_features_key(ev_id))


def cache_event_features_key(ev_id):
    return f"event_features_{ev_id}"


def get_event_features(ev_id):
    key = cache_event_features_key(ev_id)
    res = cache.get(key)
    if not res:
        res = update_event_features(ev_id)
        cache.set(key, res)
    return res


def update_event_features(ev_id):
    try:
        ev = Event.objects.get(pk=ev_id)
        res = get_assoc_features(ev.assoc_id)
        for slug in ev.features.values_list("slug", flat=True):
            res[slug] = 1
        ex_features = {
            "writing": ["paste_text", "title", "cover", "hide", "assigned"],
            "registration": ["reg_que_age", "reg_que_faction", "reg_que_tickets", "unique_code", "reg_que_allowed"],
            "character_form": ["wri_que_max", "wri_que_tickets", "wri_que_dependents"],
            "casting": ["mirror"],
            "user_character": ["player_relationships"],
        }
        for config_type, config_names in ex_features.items():
            for slug in config_names:
                if ev.get_config(f"{config_type}_{slug}", False):
                    res[slug] = 1
        return res
    except ObjectDoesNotExist:
        return {}


@receiver(post_save, sender=Association)
def update_association_reset_features(sender, instance, **kwargs):
    reset_assoc_features(instance.id)
    for ev_id in instance.events.values_list("pk", flat=True):
        reset_event_features(ev_id)


@receiver(post_save, sender=Event)
def save_event_reset_features(sender, instance, **kwargs):
    reset_event_features(instance.id)
