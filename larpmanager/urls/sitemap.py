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
from datetime import datetime
from io import StringIO

from django.http import HttpRequest, HttpResponse
from django.urls import path
from django.utils import translation
from django.utils.xmlutils import SimplerXMLGenerator
from django.views.decorators.cache import cache_page

from larpmanager.cache.association import get_cache_assoc
from larpmanager.models.association import Association
from larpmanager.models.event import DevelopStatus, Run
from larpmanager.models.larpmanager import LarpManagerGuide

translation.activate("en")


@cache_page(60 * 60)
def manual_sitemap_view(request):
    if request.assoc["id"] == 0:
        urls = larpmanager_sitemap()
    else:
        urls = _organization_sitemap(request)

    stream = _render_sitemap(urls)

    return HttpResponse(stream.getvalue(), content_type="application/xml")


def _render_sitemap(urls: list[str]) -> StringIO:
    """Render a list of URLs as XML sitemap format.

    Args:
        urls: List of URL strings to include in the sitemap.

    Returns:
        StringIO: Stream containing the XML sitemap content.
    """
    # Initialize XML stream and generator
    stream = StringIO()
    xml = SimplerXMLGenerator(stream, "utf-8")

    # Start XML document and root urlset element
    xml.startDocument()
    xml.startElement("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})

    # Generate URL entries for each location
    for loc in urls:
        xml.startElement("url", {})
        xml.startElement("loc", {})
        xml.characters(loc)
        xml.endElement("loc")
        xml.endElement("url")

    # Close root element and finalize document
    xml.endElement("urlset")
    xml.endDocument()
    return stream


def _organization_sitemap(request: HttpRequest) -> list[str]:
    """Generate sitemap URLs for an organization's events and runs.

    This function creates a list of public URLs for an organization's website,
    including the main organization page and individual event pages. Only includes
    events that are not in development/cancelled status and have future end dates.

    Args:
        request: HTTP request object containing organization context with assoc info

    Returns:
        List of fully qualified URLs for the organization's public pages.
        Returns empty list if organization is marked as demo.

    Note:
        Uses caching to avoid duplicate event URLs and respects organization
        skin domain settings for URL generation.
    """
    # Get organization and check if it's a demo (skip sitemap for demos)
    assoc = Association.objects.get(pk=request.assoc["id"])
    cache = get_cache_assoc(assoc.slug)
    if cache.get("demo", False):
        return []

    # Build base organization URL using custom domain or default
    domain = assoc.skin.domain if assoc.skin else "larpmanager.com"
    urls = [f"https://{assoc.slug}.{domain}/"]

    # Track processed events to avoid duplicates
    cache_ev = {}

    # Query active runs: exclude development/cancelled, future end dates only
    runs = (
        Run.objects.exclude(development__in=[DevelopStatus.START, DevelopStatus.CANC])
        .filter(event__assoc_id=request.assoc["id"])
        .filter(end__gte=datetime.now())
        .select_related("event", "event__assoc")
        .order_by("-end")
    )

    # Process each run and add unique event URLs
    for el in runs:
        # Skip if we've already processed this event
        if el.event_id in cache_ev:
            continue
        cache_ev[el.event_id] = 1

        # Build event-specific URL with organization domain
        assoc = el.event.assoc
        domain = assoc.skin.domain if assoc.skin else "larpmanager.com"
        urls.append(f"https://{assoc.slug}.{domain}/{el.get_slug()}/event/")

    return urls


def larpmanager_sitemap():
    urls = []
    # Static pages
    for el in ["", "usage", "about-us"]:
        urls.append(f"https://larpmanager.com/{el}/")
    # Blog posts
    for el in LarpManagerGuide.objects.all():
        urls.append(f"https://larpmanager.com/guide/{el.slug}/")
    return urls


urlpatterns = [
    path("sitemap.xml", manual_sitemap_view),
]
