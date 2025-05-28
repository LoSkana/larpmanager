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
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from larpmanager.models.association import Association, AssociationConfig
from larpmanager.models.event import Event, EventConfig, Run, RunConfig


def reset_configs(element):
    cache.delete(cache_configs_key(element))


def cache_configs_key(element):
    # noinspection PyProtectedMember
    return f"configs_{element._meta.model_name}_{element.id}"


def get_configs(element):
    key = cache_configs_key(element)
    res = cache.get(key)
    if not res:
        res = update_configs(element)
        cache.set(key, res)
    return res


def update_configs(element):
    if isinstance(element, Event):
        que = EventConfig.objects.filter(event=element)
    elif isinstance(element, Association):
        que = AssociationConfig.objects.filter(assoc=element)
    elif isinstance(element, Run):
        que = RunConfig.objects.filter(run=element)
    else:
        return {}

    res = {}
    for config in que:
        res[config.name] = config.value
    return res


@receiver(post_save, sender=EventConfig)
def post_save_reset_event_config(sender, instance, **kwargs):
    reset_configs(instance.event)


@receiver(post_delete, sender=EventConfig)
def post_delete_reset_event_config(sender, instance, **kwargs):
    reset_configs(instance.event)


@receiver(post_save, sender=AssociationConfig)
def post_save_reset_assoc_config(sender, instance, **kwargs):
    reset_configs(instance.assoc)


@receiver(post_delete, sender=AssociationConfig)
def post_delete_reset_assoc_config(sender, instance, **kwargs):
    reset_configs(instance.assoc)


@receiver(post_save, sender=RunConfig)
def post_save_reset_run_config(sender, instance, **kwargs):
    reset_configs(instance.run)


@receiver(post_delete, sender=RunConfig)
def post_delete_reset_run_config(sender, instance, **kwargs):
    reset_configs(instance.run)


def save_all_element_configs(obj, dct):
    fk_field_map = {
        "Event": "event",
        "Run": "run",
        "Association": "assoc",
        "Character": "character",
    }

    model_name = obj.__class__.__name__
    fk_field = fk_field_map.get(model_name)

    existing_configs = {config.name: config for config in obj.configs.all()}
    incoming_names = set(dct.keys())

    # update or delete existing configs
    for name, config in existing_configs.items():
        if name in dct:
            new_value = dct[name]
            if config.value != new_value:
                config.value = new_value
                config.save()
        else:
            config.delete()

    # add new configs
    for name in incoming_names - set(existing_configs.keys()):
        obj.configs.model.objects.create(**{fk_field: obj, "name": name, "value": dct[name]})


def get_element_config(element, name, def_value):
    if not hasattr(element, "aux_configs"):
        element.aux_configs = get_configs(element)

    if name not in element.aux_configs:
        return def_value

    value = element.aux_configs[name]
    if isinstance(def_value, bool):
        return value == "True"

    if not value or value == "None":
        return def_value

    return value
