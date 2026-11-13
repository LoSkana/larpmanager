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


def is_ajax(http_request: HttpRequest) -> bool:
    """Check if request is an AJAX request."""
    return http_request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"


def show_toolbar(request: HttpRequest) -> bool:
    """Determine whether to show the toolbar on a given page."""
    if not getattr(conf_settings, "DEBUG_TOOLBAR", False) or is_ajax(request):
        return False

    if not request.user.is_authenticated or not request.user.is_superuser:
        return False

    return bool(request.user.member.get_config("debug_toolbar_enabled"))
