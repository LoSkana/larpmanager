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

from io import StringIO

from django.http import HttpResponse
from django.urls import path
from django.utils import translation
from django.utils.xmlutils import SimplerXMLGenerator
from django.views.decorators.cache import cache_page

from larpmanager.models.association import Association
from larpmanager.models.event import DevelopStatus, Run
from larpmanager.models.larpmanager import LarpManagerBlog, LarpManagerTutorial

translation.activate("en")


@cache_page(60 * 60)
def manual_sitemap_view(request):
    if request.assoc["id"] == 0:
        urls = larpmanager_sitemap()
    else:
        urls = _organization_sitemap(request)

    stream = _render_sitemap(urls)

    return HttpResponse(stream.getvalue(), content_type="application/xml")


def _render_sitemap(urls):
    # XML rendering
    stream = StringIO()
    xml = SimplerXMLGenerator(stream, "utf-8")
    xml.startDocument()
    xml.startElement("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})
    for loc in urls:
        xml.startElement("url", {})
        xml.startElement("loc", {})
        xml.characters(loc)
        xml.endElement("loc")
        xml.endElement("url")
    xml.endElement("urlset")
    xml.endDocument()
    return stream


def _organization_sitemap(request):
    assoc = Association.objects.get(pk=request.assoc["id"])
    domain = assoc.skin.domain if assoc.skin else "larpmanager.com"
    urls = [f"https://{assoc.slug}.{domain}/"]
    # Event runs
    cache_ev = {}
    runs = (
        Run.objects.exclude(development__in=[DevelopStatus.START, DevelopStatus.CANC])
        .filter(event__assoc_id=request.assoc["id"])
        .select_related("event", "event__assoc")
        .order_by("-end")
    )
    for el in runs:
        if el.event_id in cache_ev:
            continue
        cache_ev[el.event_id] = 1
        assoc = el.event.assoc
        domain = assoc.skin.domain if assoc.skin else "larpmanager.com"
        urls.append(f"https://{assoc.slug}.{domain}/{el.event.slug}/{el.number}/event/")
    return urls


def larpmanager_sitemap():
    urls = []
    # Static pages
    for el in ["", "discover", "tutorials", "usage", "about-us"]:
        urls.append(f"https://larpmanager.com/{el}/")
    # Blog posts
    for el in LarpManagerBlog.objects.filter(published=True):
        urls.append(f"https://larpmanager.com/blog/{el.slug}/")
    # Tutorials
    for el in LarpManagerTutorial.objects.all():
        urls.append(f"https://larpmanager.com/tutorials/{el.slug}/")
    return urls


urlpatterns = [
    path("sitemap.xml", manual_sitemap_view),
]
