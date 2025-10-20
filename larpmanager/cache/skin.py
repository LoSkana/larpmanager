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

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.models.association import AssociationSkin


def clear_skin_cache(s):
    key = cache_skin_key(s)
    cache.delete(key)


def cache_skin_key(s):
    return f"skin_{s}"


def get_cache_skin(s):
    key = cache_skin_key(s)
    res = cache.get(key)
    if res is None:
        res = init_cache_skin(s)
        if not res:
            return None
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def init_cache_skin(domain: str) -> dict | None:
    """Initialize skin cache data for a given domain.

    Retrieves the AssociationSkin object for the specified domain and builds
    a standardized skin configuration dictionary with default values and
    skin-specific data.

    Args:
        domain (str): Domain name to lookup skin configuration for.

    Returns:
        dict | None: Skin configuration dictionary containing skin metadata
            and styling information, or None if no skin found for domain.

    Raises:
        ObjectDoesNotExist: When no AssociationSkin exists for the domain.
    """
    try:
        # Lookup skin configuration by domain
        skin = AssociationSkin.objects.get(domain=domain)
    except ObjectDoesNotExist:
        # Return None if no skin configuration exists for this domain
        return None

    # Build standardized skin configuration dictionary
    # with default LarpManager branding and skin-specific data
    return {
        "id": 0,
        "name": skin.name,
        "shuttle": [],
        "features": ["assoc_css"],
        # Default CSS configuration
        "css_code": "main",
        "slug": "lm",
        # Default LarpManager branding assets
        "logo": "https://larpmanager.com/static/lm_logo.png",
        "main_mail": "info@larpmanager.com",
        "favicon": "https://larpmanager.com/static/lm_fav.png",
        # Domain and skin identification
        "base_domain": domain,
        "skin_id": skin.id,
    }
