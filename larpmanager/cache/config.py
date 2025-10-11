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
from calmjs.parse.asttypes import Object
from django.apps import apps
from django.conf import settings as conf_settings
from django.core.cache import cache


def reset_configs(element):
    # noinspection PyProtectedMember
    cache.delete(cache_configs_key(element.id, element._meta.model_name.lower()))


def reset_element_configs(element_id, model_name):
    cache.delete(cache_configs_key(element_id, model_name))


def cache_configs_key(element_id, model_name):
    return f"configs_{model_name}_{element_id}"


def get_configs(element):
    # noinspection PyProtectedMember
    return get_element_configs(element.id, element._meta.model_name.lower())


def get_element_configs(element_id, model_name):
    key = cache_configs_key(element_id, model_name)
    res = cache.get(key)
    if not res:
        res = update_configs(element_id, model_name)
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def update_configs(element_id, model_name):
    model_map = {
        "event": ("EventConfig", "event_id"),
        "association": ("AssociationConfig", "assoc_id"),
        "run": ("RunConfig", "run_id"),
        "member": ("MemberConfig", "member_id"),
        "character": ("CharacterConfig", "character_id"),
    }
    # noinspection PyProtectedMember
    if model_name not in model_map:
        return {}
    config_model, fk_field = model_map[model_name]
    cls = apps.get_model("larpmanager", config_model)
    que = cls.objects.filter(**{fk_field: element_id})
    return {c.name: c.value for c in que}


def save_all_element_configs(obj, dct):
    """Save multiple configuration values for an element.

    Args:
        obj: Model instance to save configurations for
        dct (dict): Configuration name-value pairs to save

    Side effects:
        Updates existing configurations and creates new ones
    """
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
    """Save single configuration value for an element.

    Args:
        obj: Model instance to save configuration for
        name (str): Configuration name
        value: Configuration value

    Side effects:
        Creates or updates configuration in database
    """
    fk_field = _get_fkey_config(obj)
    obj.configs.model.objects.update_or_create(defaults={"value": value}, **{fk_field: obj, "name": name})


def _get_fkey_config(obj):
    """Get foreign key field name for configuration model.

    Args:
        obj: Model instance to determine foreign key for

    Returns:
        str: Foreign key field name for the configuration model
    """
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
    """Get configuration value with type conversion and default fallback.

    Args:
        element: Model instance to get configuration from
        name (str): Configuration name
        def_value: Default value and type indicator

    Returns:
        Configuration value converted to appropriate type, or default value
    """
    if not hasattr(element, "aux_configs"):
        element.aux_configs = get_configs(element)

    return evaluate_config(element, name, def_value)


def get_assoc_config(assoc_id, name, def_value=None, holder=None):
    if not holder:
        holder = Object()

    if not hasattr(holder, "aux_configs"):
        holder.aux_configs = get_element_configs(assoc_id, "association")

    return evaluate_config(holder, name, def_value)


def evaluate_config(element, name, def_value):
    if name not in element.aux_configs:
        return def_value

    value = element.aux_configs[name]
    if isinstance(def_value, bool):
        return value == "True"

    if not value or value == "None":
        return def_value

    return value
