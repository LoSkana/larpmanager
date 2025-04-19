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

from django.contrib import (
    sitemaps,
)
from django.contrib.sitemaps.views import (
    sitemap,
)
from django.urls import (
    path,
)
from django.utils import (
    translation,
)
from django.utils.translation import (
    gettext_lazy as _,
)

from larpmanager.models.association import (
    Association,
)
from larpmanager.models.event import (
    Run,
)
from larpmanager.models.larpmanager import (
    LarpManagerTutorial,
    LarpManagerBlog,
)

translation.activate("en")


class MainSitemap(sitemaps.Sitemap):
    def _urls(
        self,
        page,
        protocol,
        domain,
    ):
        s = []
        for el in [
            "",
            "discover",
            "tutorials",
            "usage",
            "about-us",
        ]:
            s.append(
                {
                    "item": el,
                    "location": f"https://larpmanager.com/{el}/",
                    "lastmod": None,
                    "changefreq": "daily",
                    "priority": "",
                    "alternates": [],
                }
            )
        for el in LarpManagerBlog.objects.filter(published=True):
            s.append(
                {
                    "item": el.title,
                    "location": f"https://larpmanager.com/blog/{el.slug}/",
                    "lastmod": None,
                    "changefreq": "daily",
                    "priority": "",
                    "alternates": [],
                }
            )
        for el in LarpManagerTutorial.objects.all():
            s.append(
                {
                    "item": "Tutorials - " + _(el.name),
                    "location": f"https://larpmanager.com/tutorials/{el.slug}/",
                    "lastmod": None,
                    "changefreq": "daily",
                    "priority": "",
                    "alternates": [],
                }
            )
        return s


class EventSitemap(sitemaps.Sitemap):
    def _urls(
        self,
        page,
        protocol,
        domain,
    ):
        s = []
        cache = {}
        que = Run.objects.exclude(development=Run.START).exclude(development=Run.CANC)
        que = que.select_related(
            "event",
            "event__assoc",
        ).order_by("-end")
        for el in que:
            if el.event_id in cache:
                continue
            cache[el.event_id] = 1
            s.append(
                {
                    "item": el.event.name,
                    "location": f"https://{el.event.assoc.slug}.larpmanager.com/{el.event.slug}/{el.number}/event/",
                    "lastmod": None,
                    "changefreq": "daily",
                    "priority": "",
                    "alternates": [],
                }
            )
        return s


class AssociationMap(sitemaps.Sitemap):
    def _urls(
        self,
        page,
        protocol,
        domain,
    ):
        return [
            {
                "item": assoc.name,
                "location": f"https://{assoc.slug}.larpmanager.com/",
                "lastmod": None,
                "changefreq": "daily",
                "priority": "",
                "alternates": [],
            }
            for assoc in Association.objects.all()
        ]


sitemaps = {
    "sitemaps": {
        "main": MainSitemap,
        "larp": EventSitemap,
        "assoc": AssociationMap,
    }
}

urlpatterns = [
    path(
        "sitemap.xml",
        sitemap,
        sitemaps,
        name="django.contrib.sitemaps.views.sitemap",
    )
]
