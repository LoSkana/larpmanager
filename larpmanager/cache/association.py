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

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.accounting.base import get_payment_details
from larpmanager.cache.feature import get_assoc_features
from larpmanager.models.association import Association
from larpmanager.models.registration import Registration


def clear_association_cache(association_slug):
    key = cache_assoc_key(association_slug)
    cache.delete(key)


def cache_assoc_key(association_slug):
    return f"assoc_{association_slug}"


def get_cache_assoc(association_slug: str) -> dict | None:
    """Get cached association data or initialize if not found.

    Args:
        association_slug: Association identifier string.

    Returns:
        Association data dictionary or None if initialization fails.
    """
    # Generate cache key for the association
    cache_key = cache_assoc_key(association_slug)
    cached_data = cache.get(cache_key)

    # Initialize cache if not found
    if cached_data is None:
        cached_data = init_cache_assoc(association_slug)
        if not cached_data:
            return None
        # Cache the result for one day
        cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return cached_data


def init_cache_assoc(a_slug: str) -> dict | None:
    """Initialize association cache with configuration data.

    Retrieves association data and builds a comprehensive cache dictionary
    containing configuration, features, payment info, and UI assets.

    Args:
        a_slug: Association slug identifier used to look up the association.

    Returns:
        Dictionary containing association cache data with configuration,
        features, payment settings, and UI assets. Returns None if the
        association is not found.

    Raises:
        No exceptions are raised - ObjectDoesNotExist is caught internally.
    """
    # Retrieve association object or return None if not found
    try:
        assoc = Association.objects.get(slug=a_slug)
    except ObjectDoesNotExist:
        return None

    # Convert association to dictionary for cache storage
    assoc_dict = assoc.as_dict()

    # Initialize payment configuration and member field settings
    _init_payments(assoc, assoc_dict)
    _init_member_fields(assoc, assoc_dict)

    # Add profile images (favicon, logo, main image) if available
    if assoc.profile:
        try:
            assoc_dict["favicon"] = assoc.profile_fav.url
            assoc_dict["logo"] = assoc.profile_thumb.url
            assoc_dict["image"] = assoc.profile.url
        except FileNotFoundError:
            pass

    # Remove sensitive and unnecessary fields from cache
    for m in [
        "created",
        "updated",
        "mandatory_fields",
        "optional_fields",
        "voting_candidates",
        "profile",
        "activated",
        "key",
    ]:
        if m in assoc_dict:
            del assoc_dict[m]

    # Initialize feature flags and skin configuration
    _init_features(assoc, assoc_dict)
    _init_skin(assoc, assoc_dict)

    # Determine if association qualifies for demo mode (< 10 registrations)
    max_demo = 10
    assoc_dict["demo"] = Registration.objects.filter(run__event__assoc_id=assoc.id).count() < max_demo

    return assoc_dict


def _init_skin(assoc, element_context: dict) -> None:
    """Initialize skin-related properties in the element dictionary."""
    # Set CSS and domain configuration from association skin
    element_context["skin_css"] = assoc.skin.default_css
    element_context["main_domain"] = assoc.skin.domain
    element_context["platform"] = assoc.skin.name

    # Set skin identification and management status
    element_context["skin_id"] = assoc.skin.id
    element_context["skin_managed"] = assoc.skin.managed


def _init_features(assoc: Association, cache_element: dict) -> None:
    """Initialize association features and related configuration in cache element.

    Populates the cache element with association features and their corresponding
    configuration values. Handles custom mail server settings, token/credit
    configurations, and Centauri probability settings based on enabled features.

    Args:
        assoc: Association object to get features from
        cache_element: Cache element dictionary to populate with features and configs

    Returns:
        None: Modifies the cache_element dictionary in-place
    """
    # Get all features for this association
    cache_element["features"] = get_assoc_features(assoc.id)

    # Configure custom mail server settings if feature is enabled
    if "custom_mail" in cache_element["features"]:
        config_key = "mail_server_use_tls"
        cache_element[config_key] = assoc.get_config(config_key, False)

        # Add mail server connection parameters
        for setting in ["host", "port", "host_user", "host_password"]:
            config_key = "mail_server_" + setting
            cache_element[config_key] = assoc.get_config(config_key)

    # Configure token and credit naming if feature is enabled
    if "token_credit" in cache_element["features"]:
        for setting in ["token_name", "credit_name"]:
            cache_element[setting] = assoc.get_config("token_credit_" + setting, None)

    # Configure Centauri probability settings if feature is enabled
    if "centauri" in cache_element["features"]:
        probability = assoc.get_config("centauri_prob")
        if probability:
            cache_element["centauri_prob"] = probability


def _init_member_fields(assoc: Association, el: dict[str, Any]) -> None:
    """Initialize member fields set from association's mandatory and optional fields."""
    el["members_fields"] = set()
    # Collect mandatory fields
    for field in assoc.mandatory_fields.split(","):
        el["members_fields"].add(field)
    # Collect optional fields
    for field in assoc.optional_fields.split(","):
        el["members_fields"].add(field)


def _init_payments(assoc, payment_info: dict) -> None:
    """Initialize payment information for the given association element.

    Args:
        assoc: Association object containing payment configuration
        payment_info: Dictionary to populate with payment information
    """
    # Set currency display information
    payment_info["payment_currency"] = assoc.get_payment_currency_display()
    payment_info["currency_symbol"] = assoc.get_currency_symbol()
    payment_info["methods"] = {}

    # Get payment details configuration
    payment_details = get_payment_details(assoc)

    # Process each payment method for the association
    for payment_method in assoc.payment_methods.all():
        method_element = payment_method.as_dict()
        # Add fee and description from payment details
        for setting_key in ["fee", "descr"]:
            method_element[setting_key] = payment_details.get(f"{payment_method.slug}_{setting_key}")
        payment_info["methods"][payment_method.slug] = method_element
