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

from django.apps import apps
from django.core.cache import cache


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
    model_map = {
        "event": ("EventConfig", "event"),
        "association": ("AssociationConfig", "assoc"),
        "run": ("RunConfig", "run"),
        "member": ("MemberConfig", "member"),
    }
    # noinspection PyProtectedMember
    model = element._meta.model_name.lower()
    if model not in model_map:
        return {}
    config_model, fk_field = model_map[model]
    cls = apps.get_model("larpmanager", config_model)
    que = cls.objects.filter(**{fk_field: element})
    return {c.name: c.value for c in que}


def save_all_element_configs(obj, dct):
    fk_field = _get_fkey_config(obj)

    existing_configs = {config.name: config for config in obj.configs.all()}
    incoming_names = set(dct.keys())

    # update or delete existing configs
    for name, config in existing_configs.items():
        if name in dct:
            new_value = dct[name]
            if config.value != new_value:
                config.value = new_value
                config.save()
        # else:
        #     config.delete()

    # add new configs
    for name in incoming_names - set(existing_configs.keys()):
        obj.configs.model.objects.create(**{fk_field: obj, "name": name, "value": dct[name]})


def save_single_config(obj, name, value):
    fk_field = _get_fkey_config(obj)
    obj.configs.model.objects.update_or_create(defaults={"value": value}, **{fk_field: obj, "name": name})


def _get_fkey_config(obj):
    fk_field_map = {
        "Event": "event",
        "Run": "run",
        "Association": "assoc",
        "Character": "character",
        "Member": "member",
    }
    model_name = obj.__class__.__name__
    fk_field = fk_field_map.get(model_name)
    return fk_field


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
