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
from django.http import HttpRequest


def cache_association(request: HttpRequest) -> dict:
    """Cache association context for template rendering.

    Prepares association-specific context including interface settings,
    staging environment flags, and language options for Django templates.

    Args:
        request: Django HTTP request object containing association context
                and environment information

    Returns:
        dict: Context dictionary containing:
            - assoc: Association object if present in request
            - staging: Flag (1) if environment is staging
            - languages: Available language options if user has no member
            - google_tag: Google Analytics tag ID from settings
            - hotjar_siteid: Hotjar site ID from settings
    """
    context = {}

    # Add association object if available in request
    if hasattr(request, "assoc"):
        context["assoc"] = request.assoc

    # Set staging flag for staging environment
    if request.enviro == "staging":
        context["staging"] = 1

    # Add language options for users without member association
    if not hasattr(request, "user") or not hasattr(request.user, "member"):
        context["languages"] = conf_settings.LANGUAGES

    # Add tracking and analytics configuration
    context["google_tag"] = getattr(conf_settings, "GOOGLE_TAG", None)
    context["hotjar_siteid"] = getattr(conf_settings, "HOTJAR_SITEID", None)

    return context
