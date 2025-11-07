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
from typing import Any

from django.apps import apps
from django.conf import settings as conf_settings
from django.core.cache import cache

from larpmanager.models.base import BaseModel


def clear_config_cache(config_element: Any) -> None:
    """Clear the cache for a configuration element."""
    # noinspection PyProtectedMember
    cache.delete(cache_configs_key(config_element.id, config_element._meta.model_name.lower()))


def reset_element_configs(element: BaseModel) -> None:
    """Delete cached configs for the given element."""
    cache_key = cache_configs_key(element.id, element._meta.model_name.lower())
    cache.delete(cache_key)


def cache_configs_key(config_owner_id: int, config_model_name: str) -> str:
    """Generate cache key for configuration objects."""
    return f"configs_{config_model_name}_{config_owner_id}"


def get_configs(model_instance: Any) -> dict:
    """Get configuration dictionary for a Django model instance."""
    # noinspection PyProtectedMember
    return get_element_configs(model_instance.id, model_instance._meta.model_name.lower())


def get_element_configs(element_id: int, model_name: str) -> dict:
    """Get element configurations from cache or database.

    Args:
        element_id: The ID of the element to get configs for
        model_name: The name of the model to retrieve configs from

    Returns:
        Dictionary containing the element configurations
    """
    # Generate cache key for the element and model combination
    cache_key = cache_configs_key(element_id, model_name)

    # Try to get cached result first
    cached_configs = cache.get(cache_key)
    if cached_configs is None:
        # Cache miss: update configs from database and cache the result
        cached_configs = update_configs(element_id, model_name)
        cache.set(cache_key, cached_configs, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return cached_configs


def update_configs(element_id: int, model_name: str) -> dict[str, str]:
    """
    Retrieve configuration values for a given element.

    This function fetches configuration key-value pairs for different model types
    (event, association, run, member, character) based on the element ID and model name.

    Args:
        element_id: The ID of the element to retrieve configurations for
        model_name: The type of model ("event", "association", "run", "member", "character")

    Returns:
        A dictionary mapping configuration names to their values, or empty dict if model_name is invalid

    Example:
        >>> update_configs(123, "event")
        {"max_participants": "50", "registration_deadline": "2024-01-15"}
    """
    # Define mapping between model names and their corresponding config models
    model_map = {
        "event": ("EventConfig", "event_id"),
        "association": ("AssociationConfig", "association_id"),
        "run": ("RunConfig", "run_id"),
        "member": ("MemberConfig", "member_id"),
        "character": ("CharacterConfig", "character_id"),
    }

    # Validate that the provided model name exists in our mapping
    # noinspection PyProtectedMember
    if model_name not in model_map:
        return {}

    # Extract the config model class name and foreign key field name
    config_model_name, foreign_key_field = model_map[model_name]

    # Get the actual Django model class using apps registry
    config_model_class = apps.get_model("larpmanager", config_model_name)

    # Query for all config entries matching the element ID
    config_queryset = config_model_class.objects.filter(**{foreign_key_field: element_id})

    # Build and return dictionary of config name-value pairs
    return {config.name: config.value for config in config_queryset}


def save_all_element_configs(obj, dct: dict[str, str]) -> None:
    """Save multiple configuration values for an element.

    Updates existing configurations with new values and creates new configurations
    for any names not already present. Does not delete existing configurations
    that are not included in the input dictionary.

    Args:
        obj: Model instance to save configurations for. Must have a 'configs'
             related manager.
        dct: Dictionary mapping configuration names to their string values.

    Returns:
        None

    Side Effects:
        - Updates existing configuration values in the database
        - Creates new configuration records for new names
    """
    # Get the foreign key field name for linking configs to the parent object
    fk_field = _get_fkey_config(obj)

    # Build a lookup dictionary of existing configurations by name
    existing_configs = {config.name: config for config in obj.configs.all()}
    incoming_names = set(dct.keys())

    # Update existing configs with new values if they differ
    for name, config in existing_configs.items():
        if name in dct:
            new_value = dct[name]
            # Only save if the value has actually changed
            if config.value != new_value:
                config.value = new_value
                config.save()
        # Note: Commented out deletion to preserve existing configs
        # else:
        #     config.delete()

    # Create new configuration records for names not already present
    for name in incoming_names - set(existing_configs.keys()):
        obj.configs.model.objects.create(**{fk_field: obj, "name": name, "value": dct[name]})


def save_single_config(obj: object, name: str, value: any) -> None:
    """Save single configuration value for an element.

    This function creates or updates a configuration entry in the database
    for the given object. It uses the object's foreign key relationship
    to store the configuration with the specified name and value.

    Args:
        obj: Model instance to save configuration for. Must have a 'configs'
             attribute that references a related configuration model.
        name: Configuration name/key to store the value under.
        value: Configuration value to store. Can be any serializable type.

    Returns:
        None

    Side Effects:
        Creates or updates configuration in database through the object's
        configs relationship.

    Raises:
        AttributeError: If obj doesn't have a 'configs' attribute.
        DatabaseError: If the database operation fails.
    """
    # Get the foreign key field name for this object type
    fk_field = _get_fkey_config(obj)

    # Create or update the configuration entry in the database
    # Uses update_or_create to avoid duplicates and handle both insert/update cases
    obj.configs.model.objects.update_or_create(defaults={"value": value}, **{fk_field: obj, "name": name})


def _get_fkey_config(model_instance: object) -> str | None:
    """Get foreign key field name for configuration model.

    This function maps Django model class names to their corresponding
    foreign key field names used in configuration models.

    Args:
        model_instance: Model instance to determine foreign key for. Expected to be
            one of Event, Run, Association, Character, or Member instances.

    Returns:
        Foreign key field name for the configuration model, or None if
        the model type is not supported.

    Example:
        >>> event = Event()
        >>> _get_fkey_config(event)
        'event'
    """
    # Map model class names to their configuration foreign key field names
    foreign_key_field_map = {
        "Event": "event",
        "Run": "run",
        "Association": "association",
        "Character": "character",
        "Member": "member",
    }

    # Extract the model class name from the instance
    model_class_name = model_instance.__class__.__name__

    # Return the corresponding foreign key field name
    foreign_key_field_name = foreign_key_field_map.get(model_class_name)
    return foreign_key_field_name


def get_element_config(element, config_name: str, default_value, bypass_cache: bool = False):
    """Get configuration value with type conversion and default fallback.

    Retrieves a configuration value from an element's aux_configs, handling
    caching and type conversion based on the default value type.

    Args:
        element: Model instance to get configuration from. Must have aux_configs
            attribute or be compatible with get_configs/update_configs functions.
        config_name: Configuration parameter name to retrieve.
        default_value: Default value to return if config not found. Also serves as
            type indicator for conversion of the retrieved value.
        bypass_cache: Whether to bypass cache and fetch directly from database.
            Useful for background processes where cache might be stale.

    Returns:
        Configuration value converted to the same type as default_value, or default_value
        if the configuration parameter is not found.

    Note:
        If element lacks aux_configs attribute, it will be populated either from
        cache (default) or directly from database (if bypass_cache=True).
    """
    # Check if element already has cached configurations
    if not hasattr(element, "aux_configs"):
        if bypass_cache:
            # Fetch directly from database for background processes to avoid stale cache
            element.aux_configs = update_configs(element.id, element._meta.model_name.lower())
        else:
            # Use cached configurations for better performance
            element.aux_configs = get_configs(element)

    # Evaluate and return the configuration value with type conversion
    return evaluate_config(element.aux_configs, config_name, default_value)


def _get_cached_config(element_id, element_type, config_name, default_value=None, context=None, bypass_cache=False):
    """Helper function to get cached configuration for any element type."""
    cache_key = f"{element_type}_configs"

    if context is None:
        context = {}
    if cache_key not in context:
        context[cache_key] = {}

    element_configs = context[cache_key].get(element_id, None)
    if element_configs is None:
        if bypass_cache:
            # do not trust cache for background processes
            element_configs = update_configs(element_id, element_type)
        else:
            element_configs = get_element_configs(element_id, element_type)
        context[cache_key][element_id] = element_configs

    return evaluate_config(element_configs, config_name, default_value)


def get_association_config(association_id, config_name, default_value=None, context=None, bypass_cache=False):
    return _get_cached_config(association_id, "association", config_name, default_value, context, bypass_cache)


def get_event_config(
    event_id: int,
    config_name: str,
    default_value: Any = None,
    context: dict[str, Any] | None = None,
    bypass_cache: bool = False,
) -> Any:
    """Get event configuration value from cache or database."""
    return _get_cached_config(event_id, "event", config_name, default_value, context, bypass_cache)


def evaluate_config(configurations: dict, configuration_name: str, default_value: any) -> any:
    """Evaluate configuration value from element's aux_configs with type conversion.

    Args:
        configurations: dict with all the configs
        configuration_name: Configuration key to lookup in aux_configs
        default_value: Default value to return if key not found or value is empty

    Returns:
        Configuration value with appropriate type conversion, or default value
    """
    # Return default if configuration key doesn't exist
    if configuration_name not in configurations:
        return default_value

    # Get the raw configuration value
    configuration_value = configurations[configuration_name]

    # Handle boolean type conversion for string "True"/"False"
    if isinstance(default_value, bool):
        return configuration_value == "True"

    # Return default for empty or "None" string values
    if not configuration_value or configuration_value == "None":
        return default_value

    # Return the raw value for all other cases
    return configuration_value
