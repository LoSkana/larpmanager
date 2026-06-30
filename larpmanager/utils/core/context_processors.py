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
from django.http import HttpRequest

from larpmanager.cache.config import get_association_config
from larpmanager.models.registration import Registration
from larpmanager.utils.core.nav import build_profile_home_nav_items, build_profile_nav_items
from main.settings import CACHE_TIMEOUT_1_DAY


def cache_association(request: HttpRequest) -> dict:
    """Cache association context for template rendering.

    Prepares association-specific context including interface settings,
    staging environment flags, and language options for Django templates.

    Args:
        request: Django HTTP request object containing association context
                and environment information

    Returns:
        dict: Context dictionary containing:
            - association: Association object if present in request
            - staging: Flag (1) if environment is staging
            - languages: Available language options if user has no member
            - google_tag: Google Analytics tag ID from settings
            - hotjar_siteid: Hotjar site ID from settings

    """
    context = {}

    # Add association object if available in request
    if hasattr(request, "association"):
        context["association"] = request.association
        association_id = request.association["id"]
        context["page_theme"] = get_association_config(association_id, "theme") or "nebula"

    # Set staging flag for staging environment
    if request.enviro == "staging":
        context["staging"] = 1

    # Suppresses when out of prod
    if request.enviro != "prod":
        context["testing"] = 1

    # Add language options for users without member association
    if not hasattr(request, "user") or not hasattr(request.user, "member"):
        context["languages"] = conf_settings.LANGUAGES

    # Add tracking and analytics configuration
    context["profile_nav_items"] = build_profile_nav_items(request)
    context["profile_home_nav_items"] = build_profile_home_nav_items(request)

    context["google_tag"] = getattr(conf_settings, "GOOGLE_TAG", None)
    hotjar_siteid = getattr(conf_settings, "HOTJAR_SITEID", None)
    if hotjar_siteid and hasattr(request, "association"):
        association_id = request.association["id"]
        cache_key = f"assoc_reg_count_gte10_{association_id}"
        above_threshold = cache.get(cache_key)
        max_threshold = 10
        if above_threshold is None:
            count = Registration.objects.filter(run__event__association_id=association_id).count()
            above_threshold = count >= max_threshold
            timeout = CACHE_TIMEOUT_1_DAY if above_threshold else 3600
            cache.set(cache_key, above_threshold, timeout)
        if above_threshold:
            hotjar_siteid = None
    context["hotjar_siteid"] = hotjar_siteid

    return context
