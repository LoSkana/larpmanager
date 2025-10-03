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

from django.conf import settings
from django.conf import settings as conf_settings


def cache_association(request):
    """Cache association context for template rendering.

    Prepares association-specific context including interface settings,
    staging environment flags, and language options.

    Args:
        request: Django HTTP request with association context

    Returns:
        dict: Context dictionary with association and environment data
    """
    ctx = {}
    if hasattr(request, "assoc"):
        ctx["assoc"] = request.assoc
    if request.enviro == "staging":
        ctx["staging"] = 1
    if not hasattr(request, "user") or not hasattr(request.user, "member"):
        ctx["languages"] = conf_settings.LANGUAGES

    ctx["google_tag"] = getattr(settings, "GOOGLE_TAG", None)
    ctx["hotjar_siteid"] = getattr(settings, "HOTJAR_SITEID", None)

    return ctx
