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


def is_ajax(request):
    """Check if request is an AJAX request.

    Args:
        request: HTTP request object

    Returns:
        bool: True if request is AJAX, False otherwise
    """
    return request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"


def show_toolbar(request):
    """
    Default function to determine whether to show the toolbar on a given page.
    """
    return getattr(conf_settings, "DEBUG_TOOLBAR", False) and not is_ajax(request)
