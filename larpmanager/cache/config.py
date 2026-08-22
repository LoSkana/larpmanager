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
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.apps import apps
from django.conf import settings as conf_settings
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

from larpmanager.models.base import Config
from larpmanager.utils.larpmanager.versions import LATEST_AVAILABLE_VERSION

if TYPE_CHECKING:
    from larpmanager.models.base import BaseModel

# Configs that must always read from the child event, never from the campaign parent (matched as prefixes)
EVENT_CONFIGS_OWN_CHILD: frozenset[str] = frozenset({"payment_custom_reason", "theme", "pub_"})

# Centralized config defaults, used when a caller does not pass an explicit default_value.
# Exact-name match first, then prefix, then suffix; falls back to False if nowhere matched.
CONFIG_DEFAULTS: dict[str, Any] = {
    "debug_toolbar_enabled": False,
    "payment_custom_reason": "",
    # "nebula" mirrors AppearanceTheme.NEBULA.value;
    "theme": "nebula",
    "intro_driver": "",
    "app_integration_algorithm": "HS256",
    "app_integration_button_text": "",
    "app_integration_redirect_url": "",
    "app_integration_secret": "",
    "bring_friend_discount_from": 0,
    "bring_friend_discount_to": 0,
    "casting_add": 0,
    "casting_characters": 1,
    "casting_max": 5,
    "casting_min": 1,
    "casting_pay_priority": 0,
    "casting_reg_priority": 0,
    "centauri_badge": None,
    "centauri_content": None,
    "centauri_descr": None,
    "centauri_prob": 0,
    "character_play_max": 1,
    "collapse_options_min": 5,
    "credits_name": None,
    "deadline_days": 0,
    "deadlines_tolerance": "30",
    "einvoice_aliquotaiva": "",
    "einvoice_cap": None,
    "einvoice_codicedestinatario": None,
    "einvoice_comune": None,
    "einvoice_denominazione": None,
    "einvoice_idcodice": None,
    "einvoice_indirizzo": None,
    "einvoice_natura": "",
    "einvoice_nazione": None,
    "einvoice_numerocivico": None,
    "einvoice_partitaiva": None,
    "einvoice_provincia": None,
    "einvoice_regimefiscale": None,
    "ensemble_default_mode": "book",
    "exp_start": 0,
    "exp_undo": 0,
    "free_abilities": "[]",
    "guild_max_members": 0,
    "guild_max_number": 0,
    "footer_content": "",
    "header_content": "",
    "ildb": "",
    "ildb_api_key": "",
    "ildb_expire": "",
    "ildb_key_hash": "",
    "ildb_team_id": "",
    "interface_version": None,
    "lottery_num_draws": 0,
    "lottery_ticket": "",
    "mail_server_host": "",
    "mail_server_host_password": "",
    "mail_server_host_user": "",
    "mail_server_port": "",
    "member_theme": "",
    "membership_age": "",
    "membership_day": "01-01",
    "membership_fee": 0,
    "membership_grazing": "0",
    "organization_tax_perc": "10",
    "page_css": "",
    "pay_what_you_want_descr": _("Freely indicate the amount of your donation"),
    "pay_what_you_want_label": _("Free donation"),
    "payment_alert": 30,
    "pub_accommodation": "",
    "pub_accommodation_type": "",
    "pub_country": "",
    "pub_event_type": "",
    "pub_language": "",
    "pub_lat": "",
    "pub_lon": "",
    "pub_meals": "",
    "pub_mood": "",
    "pub_place": "",
    "pub_setting": "",
    "receipt_codice_fiscale": "",
    "receipt_legal_name": "",
    "receipt_runts": "",
    "receipt_sede_legale": "",
    "reduced_ratio": 10,
    "remind_days": 5,
    "show_addit": "[]",
    "show_export": False,
    "show_limitations": False,
    "show_shortcuts_mobile": False,
    "sticky": "{}",
    "token_credit_credit_name": None,
    "token_credit_token_name": None,
    "tokens_name": None,
    "treasurer_appointees": "",
    "user_character_max": 1,
    "vat_options": 0,
    "vat_ticket": 0,
    "version": LATEST_AVAILABLE_VERSION,
    "vote_candidates": "",
    "vote_max": "1",
    "vote_min": "1",
    "writing_relationship_length": 10000,
}
CONFIG_DEFAULT_PREFIXES: list[tuple[str, Any]] = [
    ("pub_", ""),
    ("show_", "[]"),
    ("open_", "[]"),
    ("added_", "{}"),
]
CONFIG_DEFAULT_SUFFIXES: list[tuple[str, Any]] = []


def get_config_default(config_name: str) -> Any:
    """Look up the centralized default for a config name (exact, then prefix, then suffix). Fallback as False."""
    if config_name in CONFIG_DEFAULTS:
        return CONFIG_DEFAULTS[config_name]
    for prefix, default in CONFIG_DEFAULT_PREFIXES:
        if config_name.startswith(prefix):
            return default
    for suffix, default in CONFIG_DEFAULT_SUFFIXES:
        if config_name.endswith(suffix):
            return default
    return False


def reset_element_configs(element_id: int, model_name: str) -> None:
    """Delete cached configs for the given element id and model name."""
    cache.delete(cache_configs_key(element_id, model_name))


def reset_event_configs(event_id: int) -> None:
    """Delete cached configs for an event."""
    reset_element_configs(event_id, "event")


def reset_run_configs(run_id: int) -> None:
    """Delete cached configs for a run."""
    reset_element_configs(run_id, "run")


def reset_association_configs(association_id: int) -> None:
    """Delete cached configs for an association."""
    reset_element_configs(association_id, "association")


def reset_member_configs(member_id: int) -> None:
    """Delete cached configs for a member."""
    reset_element_configs(member_id, "member")


def reset_character_configs(character_id: int) -> None:
    """Delete cached configs for a character."""
    reset_element_configs(character_id, "character")


def cache_configs_key(config_owner_id: int, config_model_name: str) -> str:
    """Generate cache key for configuration objects."""
    return f"configs_{config_model_name}_{config_owner_id}"


def get_configs(model_instance: BaseModel) -> dict[str, Any]:
    """Get configuration dictionary for a Django model instance."""
    # noinspection PyProtectedMember
    return get_element_configs(model_instance.id, model_instance._meta.model_name.lower())  # noqa: SLF001  # Django model metadata


def get_element_configs(element_id: int, model_name: str) -> dict[str, Any]:
    """Get element configurations from cache or database."""
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
    """Retrieve configuration values for a given element.

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


def save_all_element_configs(obj: BaseModel, dct: dict[str, str]) -> None:
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
    fk_field: str = _get_fkey_config(obj)

    # Build a lookup dictionary of existing configurations by name
    existing_configs: dict[str, Any] = {config.name: config for config in obj.configs.all()}
    incoming_names: set[str] = set(dct.keys())

    # Update existing configs with new values if they differ
    for name, config in existing_configs.items():
        if name in dct:
            new_value: str = dct[name]
            # Only save if the value has actually changed
            if config.value != new_value:
                config.value = new_value
                config.save()
        # Note: Commented out deletion to preserve existing configs

    # Create new configuration records for names not already present
    for name in incoming_names - set(existing_configs.keys()):
        obj.configs.model.objects.create(**{fk_field: obj, "name": name, "value": dct[name]})


def save_single_config(obj: object, name: str, value: any) -> None:
    """Save single configuration value for an element."""
    fk_field = _get_fkey_config(obj)
    # Include deleted=None in the lookup so safedelete's update_or_create never
    # tries to restore a stale soft-deleted record that conflicts with the live one.
    obj.configs.model.objects.update_or_create(
        defaults={"value": value}, **{fk_field: obj, "name": name, "deleted": None}
    )
    # noinspection PyProtectedMember
    reset_element_configs(obj.id, obj._meta.model_name.lower())  # noqa: SLF001  # Django model metadata


def save_single_config_by_id(model_cls: type, obj_id: int, name: str, value: any) -> None:
    """Save single configuration value for an element, addressed by id without loading it."""
    fk_field = _get_fkey_config_for_class(model_cls)
    config_model = model_cls._meta.get_field("configs").related_model  # noqa: SLF001  # Django model metadata
    config_model.objects.update_or_create(
        defaults={"value": value}, **{f"{fk_field}_id": obj_id, "name": name, "deleted": None}
    )
    reset_element_configs(obj_id, model_cls._meta.model_name.lower())  # noqa: SLF001  # Django model metadata


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
    return _get_fkey_config_for_class(model_instance.__class__)


def _get_fkey_config_for_class(model_cls: type) -> str | None:
    """Get foreign key field name for configuration model, by model class."""
    # Map model class names to their configuration foreign key field names
    foreign_key_field_map = {
        "Event": "event",
        "Run": "run",
        "Association": "association",
        "Character": "character",
        "Member": "member",
    }
    return foreign_key_field_map.get(model_cls.__name__)


def get_element_config(element: Any, config_name: str, *, bypass_cache: bool = False) -> Any:
    """Get configuration value with type conversion and centralized default fallback.

    Retrieves a configuration value from an element's aux_configs, handling
    caching and type conversion based on the centralized default's type.

    Args:
        element: Model instance to get configuration from. Must have aux_configs
            attribute or be compatible with get_configs/update_configs functions.
        config_name: Configuration parameter name to retrieve.
        bypass_cache: Whether to bypass cache and fetch directly from database.
            Useful for background processes where cache might be stale.

    Returns:
        Configuration value converted to the same type as default_value, or default_value
        if the configuration parameter is not found.

    Note:
        If element lacks aux_configs attribute, it will be populated either from
        cache (default) or directly from database (if bypass_cache=True).

    """
    # If element is an Event with a parent, use parent's config directly (except own-child configs)
    if (
        not any(config_name.startswith(p) for p in EVENT_CONFIGS_OWN_CHILD)
        and element._meta.model_name.lower() == "event"  # noqa: SLF001
        and getattr(element, "parent_id", None)
    ):
        element = element.parent

    # Check if element already has cached configurations
    if not hasattr(element, "aux_configs"):
        if bypass_cache:
            # Fetch directly from database for background processes to avoid stale cache
            element.aux_configs = update_configs(element.id, element._meta.model_name.lower())  # noqa: SLF001  # Django model metadata
        else:
            # Use cached configurations for better performance
            element.aux_configs = get_configs(element)

    # Evaluate and return the configuration value with type conversion
    default_value = get_config_default(config_name)
    return evaluate_config(element.aux_configs, config_name, default_value)


def _get_cached_config(
    element_id: int,
    element_type: str,
    config_name: str,
    *,
    context: dict | None = None,
    bypass_cache: bool = False,
) -> any:
    """Get cached configuration for any element type."""
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

    default_value = get_config_default(config_name)
    return evaluate_config(element_configs, config_name, default_value)


def get_association_config(
    association_id: int,
    config_name: str,
    *,
    context: dict | None = None,
    bypass_cache: bool = False,
) -> Any:
    """Get configuration value for association."""
    return _get_cached_config(
        association_id,
        "association",
        config_name,
        context=context,
        bypass_cache=bypass_cache,
    )


def _get_event_parent_id(event_id: int, context: dict | None) -> int | None:
    """Get parent_id for an event, cached in context and Redis."""
    if context is None:
        context = {}
    ctx_key = "event_parent_ids"
    if ctx_key not in context:
        context[ctx_key] = {}
    if event_id in context[ctx_key]:
        return context[ctx_key][event_id]

    redis_key = f"event_parent_{event_id}"
    cached = cache.get(redis_key)
    if cached is not None:
        parent_id = cached if cached != 0 else None
    else:
        from larpmanager.models.event import Event  # noqa: PLC0415

        parent_id = Event.objects.filter(pk=event_id).values_list("parent_id", flat=True).first()
        cache.set(redis_key, parent_id if parent_id is not None else 0, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    context[ctx_key][event_id] = parent_id
    return parent_id


def reset_event_parent_cache(event_id: int) -> None:
    """Invalidate cached parent_id for an event."""
    cache.delete(f"event_parent_{event_id}")


def get_event_config(
    event_id: int,
    config_name: str,
    *,
    context: dict | None = None,
    bypass_cache: bool = False,
) -> Any:
    """Get event configuration value; for campaign always using parent, except for EVENT_CONFIGS_OWN_CHILD."""
    if context is None:
        context = {}

    if any(config_name.startswith(p) for p in EVENT_CONFIGS_OWN_CHILD):
        lookup_id = event_id
    else:
        parent_id = _get_event_parent_id(event_id, context)
        lookup_id = parent_id if parent_id else event_id

    return _get_cached_config(lookup_id, "event", config_name, context=context, bypass_cache=bypass_cache)


def get_member_config(
    member_id: int,
    config_name: str,
    *,
    context: dict | None = None,
    bypass_cache: bool = False,
) -> Any:
    """Get member configuration value from cache or database."""
    return _get_cached_config(member_id, "member", config_name, context=context, bypass_cache=bypass_cache)


def _is_config_set_cached(
    element_id: int,
    element_type: str,
    config_name: str,
    *,
    context: dict | None = None,
    bypass_cache: bool = False,
) -> bool:
    """Check whether a config has been explicitly set, without applying evaluate_config type coercion."""
    cache_key = f"{element_type}_configs"

    if context is None:
        context = {}
    if cache_key not in context:
        context[cache_key] = {}

    element_configs = context[cache_key].get(element_id, None)
    if element_configs is None:
        if bypass_cache:
            element_configs = update_configs(element_id, element_type)
        else:
            element_configs = get_element_configs(element_id, element_type)
        context[cache_key][element_id] = element_configs

    raw_value = element_configs.get(config_name)
    return bool(raw_value) and raw_value != "None"


def is_association_config_set(
    association_id: int, config_name: str, *, context: dict | None = None, bypass_cache: bool = False
) -> bool:
    """Check whether a config has been explicitly set for association."""
    return _is_config_set_cached(association_id, "association", config_name, context=context, bypass_cache=bypass_cache)


def is_event_config_set(
    event_id: int, config_name: str, *, context: dict | None = None, bypass_cache: bool = False
) -> bool:
    """Check whether a config has been explicitly set for event."""
    return _is_config_set_cached(event_id, "event", config_name, context=context, bypass_cache=bypass_cache)


_GLOBAL_CONFIG_CACHE_PREFIX = "global_config_"


def get_config(name: str, default_value: str = "", *, use_cache: bool = True) -> str:
    """Get a value from the standalone Config table."""
    cache_key = f"{_GLOBAL_CONFIG_CACHE_PREFIX}{name}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    obj = Config.objects.filter(name=name).first()
    value = obj.value if obj else default_value
    if use_cache:
        cache.set(cache_key, value, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return value


def save_config(name: str, value: str, *, use_cache: bool = True) -> None:
    """Save a value to the standalone Config table."""
    Config.objects.update_or_create(name=name, defaults={"value": value})
    if use_cache:
        cache.delete(f"{_GLOBAL_CONFIG_CACHE_PREFIX}{name}")


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
