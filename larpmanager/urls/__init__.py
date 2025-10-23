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

from django.conf import (
    settings as conf_settings,
)
from django.conf.urls.static import static
from django.urls import path

from larpmanager.views.api import published_events
from larpmanager.views.user import event as views_ue

from .event import urlpatterns as event_urls
from .exe import urlpatterns as exe_urls
from .lm import urlpatterns as lm_urls
from .orga import urlpatterns as orga_urls
from .sitemap import urlpatterns as sitemap_urls
from .user import urlpatterns as user_urls

static_urls = static(
    conf_settings.MEDIA_URL,
    document_root=conf_settings.MEDIA_ROOT,
)

urlpatterns = (
    sitemap_urls
    + user_urls
    + exe_urls
    + lm_urls
    + event_urls
    + orga_urls
    + static_urls
    + [
        path(
            "api/v1/published-events/",
            published_events,
            name="api_published_events",
        ),
        path(
            "<slug:s>/",
            views_ue.event_redirect,
            name="event_redirect",
        ),
    ]
)

handler404 = "larpmanager.views.error_404"
handler500 = "larpmanager.views.error_500"


def walk_patterns(patterns) -> set[str]:
    """Extract URL prefixes from Django URL patterns.

    Args:
        patterns: Collection of URL pattern objects.

    Returns:
        Set of URL prefixes without angle brackets or regex anchors.
    """
    prefixes = set()
    for element in patterns:
        # Extract first path segment from pattern string
        part = str(element.pattern).strip("/").split("/")[0]

        # Remove regex anchor and filter valid prefixes
        part = part.replace("^", "")
        if part and not part.startswith("<"):
            prefixes.add(part)
    return prefixes


STATIC_PREFIXES = walk_patterns(urlpatterns)
conf_settings.STATIC_PREFIXES = STATIC_PREFIXES
