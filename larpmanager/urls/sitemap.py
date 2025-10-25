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
def manual_sitemap_view(request: HttpRequest) -> HttpResponse:
    """Generate XML sitemap for organization or global site."""
    # Check if this is the global site (id=0) or organization-specific
    if request.assoc["id"] == 0:
        urls = larpmanager_sitemap()
    else:
        urls = _organization_sitemap(request)

    # Render URLs to XML format
    stream = _render_sitemap(urls)

    return HttpResponse(stream.getvalue(), content_type="application/xml")


def _render_sitemap(urls: list[str]) -> StringIO:
    """Generate XML sitemap from a list of URLs.

    Args:
        urls: List of URL strings to include in the sitemap

    Returns:
        StringIO object containing the generated XML sitemap
    """
    # Initialize XML stream and generator
    xml_stream = StringIO()
    xml_generator = SimplerXMLGenerator(xml_stream, "utf-8")

    # Start XML document and root urlset element
    xml_generator.startDocument()
    xml_generator.startElement("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})

    # Generate URL entries for each location
    for location_url in urls:
        xml_generator.startElement("url", {})
        xml_generator.startElement("loc", {})
        xml_generator.characters(location_url)
        xml_generator.endElement("loc")
        xml_generator.endElement("url")

    # Close root element and document
    xml_generator.endElement("urlset")
    xml_generator.endDocument()
    return xml_stream


def _organization_sitemap(request) -> list[str]:
    """Generate sitemap URLs for an organization's events and runs.

    Args:
        request: HTTP request object containing organization context with assoc dict

    Returns:
        List of fully qualified URLs for the organization's public pages.
        Returns empty list if organization is marked as demo.

    Note:
        Only includes events that are not in START or CANCELLED status
        and have end dates in the future.
    """
    # Get organization and check if it's a demo instance
    organization = Association.objects.get(pk=request.assoc["id"])
    organization_cache = get_cache_assoc(organization.slug)
    if organization_cache.get("demo", False):
        return []

    # Build base organization URL
    domain = organization.skin.domain if organization.skin else "larpmanager.com"
    urls = [f"https://{organization.slug}.{domain}/"]

    # Track processed events to avoid duplicates
    processed_event_ids = {}

    # Query active runs for future events
    runs = (
        Run.objects.exclude(development__in=[DevelopStatus.START, DevelopStatus.CANC])
        .filter(event__assoc_id=request.assoc["id"])
        .filter(end__gte=datetime.now())
        .select_related("event", "event__assoc")
        .order_by("-end")
    )

    # Generate URLs for each unique event
    for run in runs:
        # Skip if event already processed
        if run.event_id in processed_event_ids:
            continue
        processed_event_ids[run.event_id] = 1

        # Build event-specific URL
        event_organization = run.event.assoc
        domain = event_organization.skin.domain if event_organization.skin else "larpmanager.com"
        urls.append(f"https://{event_organization.slug}.{domain}/{run.get_slug()}/event/")

    return urls


def larpmanager_sitemap() -> list[str]:
    """Generate sitemap URLs for LarpManager website.

    Returns:
        List of complete URLs for static pages and blog posts.
    """
    urls = []

    # Static pages
    for el in ["", "usage", "about-us"]:
        urls.append(f"https://larpmanager.com/{el}/")

    # Blog posts from guides
    for el in LarpManagerGuide.objects.all():
        urls.append(f"https://larpmanager.com/guide/{el.slug}/")

    return urls


urlpatterns = [
    path("sitemap.xml", manual_sitemap_view),
]
