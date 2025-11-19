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

import logging
from typing import Any

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.accounting.base import get_payment_details
from larpmanager.cache.feature import get_association_features
from larpmanager.models.association import Association
from larpmanager.models.registration import Registration

logger = logging.getLogger(__name__)

# Demo mode threshold (Associations with fewer than this many registrations are considered demo/trial accounts)
MAX_DEMO_REGISTRATIONS = 10


def clear_association_cache(association_slug: str) -> None:
    """Clear cached association data."""
    key = cache_association_key(association_slug)
    cache.delete(key)


def cache_association_key(association_slug: str) -> str:
    """Generate cache key for association data."""
    return f"association_{association_slug}"


def get_cache_association(association_slug: str) -> dict | None:
    """Get cached association data or initialize if not found.

    Args:
        association_slug: Association identifier string.

    Returns:
        Association data dictionary or None if initialization fails.

    """
    # Generate cache key for the association
    cache_key = cache_association_key(association_slug)
    cached_data = cache.get(cache_key)

    # Initialize cache if not found
    if cached_data is None:
        cached_data = init_cache_association(association_slug)
        if not cached_data:
            return None
        # Cache the result for one day
        cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return cached_data


def init_cache_association(a_slug: str) -> dict | None:
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
        association = Association.objects.get(slug=a_slug)
    except ObjectDoesNotExist:
        return None

    # Convert association to dictionary for cache storage
    association_dict = association.as_dict()

    # Initialize payment configuration and member field settings
    _init_payments(association, association_dict)
    _init_member_fields(association, association_dict)

    # Add profile images (favicon, logo, main image) if available
    if association.profile:
        try:
            association_dict["favicon"] = association.profile_fav.url
            association_dict["logo"] = association.profile_thumb.url
            association_dict["image"] = association.profile.url
        except FileNotFoundError:
            logger.warning("Profile image files not found for association %s", association.slug)

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
        if m in association_dict:
            del association_dict[m]

    # Initialize feature flags and skin configuration
    _init_features(association, association_dict)
    _init_skin(association, association_dict)

    # Determine if association qualifies for demo mode (< MAX_DEMO_REGISTRATIONS)
    association_dict["demo"] = (
        Registration.objects.filter(run__event__association_id=association.id).count() < MAX_DEMO_REGISTRATIONS
    )

    return association_dict


def _init_skin(association: Association, element_context: dict) -> None:
    """Initialize skin-related properties in the element dictionary."""
    # Set CSS and domain configuration from association skin
    element_context["skin_css"] = association.skin.default_css
    element_context["main_domain"] = association.skin.domain
    element_context["platform"] = association.skin.name

    # Set skin identification and management status
    element_context["skin_id"] = association.skin.id
    element_context["skin_managed"] = association.skin.managed


def _init_features(association: Association, cache_element: dict) -> None:
    """Initialize association features and related configuration in cache element.

    Populates the cache element with association features and their corresponding
    configuration values. Handles custom mail server settings, token/credit
    configurations, and Centauri probability settings based on enabled features.

    Args:
        association: Association object to get features from
        cache_element: Cache element dictionary to populate with features and configs

    Returns:
        None: Modifies the cache_element dictionary in-place

    """
    # Get all features for this association
    cache_element["features"] = get_association_features(association.id)

    # Configure custom mail server settings if feature is enabled
    if "custom_mail" in cache_element["features"]:
        config_key = "mail_server_use_tls"
        cache_element[config_key] = association.get_config(config_key, default_value=False)

        # Add mail server connection parameters
        for setting in ["host", "port", "host_user", "host_password"]:
            config_key = "mail_server_" + setting
            cache_element[config_key] = association.get_config(config_key, default_value="")

    # Configure token and credit naming if feature is enabled
    if "token_credit" in cache_element["features"]:
        for setting in ["token_name", "credit_name"]:
            cache_element[setting] = association.get_config("token_credit_" + setting, default_value=None)

    # Configure Centauri probability settings if feature is enabled
    if "centauri" in cache_element["features"]:
        probability = association.get_config("centauri_prob", default_value=0)
        if probability:
            cache_element["centauri_prob"] = probability


def _init_member_fields(association: Association, el: dict[str, Any]) -> None:
    """Initialize member fields set from association's mandatory and optional fields."""
    el["members_fields"] = set()
    # Collect mandatory fields
    for field in association.mandatory_fields.split(","):
        el["members_fields"].add(field)
    # Collect optional fields
    for field in association.optional_fields.split(","):
        el["members_fields"].add(field)


def _init_payments(association: Any, payment_info: dict) -> None:
    """Initialize payment information for the given association element.

    Args:
        association: Association object containing payment configuration
        payment_info: Dictionary to populate with payment information

    """
    # Set currency display information
    payment_info["payment_currency"] = association.get_payment_currency_display()
    payment_info["currency_symbol"] = association.get_currency_symbol()
    payment_info["methods"] = {}

    # Get payment details configuration
    payment_details = get_payment_details(association)

    # Process each payment method for the association
    for payment_method in association.payment_methods.all():
        method_element = payment_method.as_dict()
        # Add fee and description from payment details
        for setting_key in ["fee", "descr"]:
            method_element[setting_key] = payment_details.get(f"{payment_method.slug}_{setting_key}")
        payment_info["methods"][payment_method.slug] = method_element
