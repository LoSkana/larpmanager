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

from difflib import SequenceMatcher
from typing import Any

import deepl
from bs4 import BeautifulSoup
from django.conf import settings as conf_settings
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.urls import reverse

from larpmanager.models.access import AssociationPermission, EventPermission
from larpmanager.models.event import Run
from larpmanager.models.larpmanager import LarpManagerGuide, LarpManagerTutorial
from larpmanager.utils.larpmanager.tasks import notify_admins

SEARCH_CONFIG = "english"

SNIPPET_LENGTH = 300

GUIDES_LIMIT = 5

TUTORIALS_LIMIT = 10


def _html_to_text(html: str | None) -> str:
    """Strip HTML tags, returning the plain text content."""
    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)


def _tutorial_sections(html: str | None) -> list[tuple[str, str]]:
    """Split tutorial HTML into (heading, text) pairs, one for each H2/H3 section."""
    sections = []
    soup = BeautifulSoup(html or "", "html.parser")
    for heading in soup.find_all(["h2", "h3"]):
        content = []
        # Collect content following this heading until the next one
        for sibling in heading.find_next_siblings():
            if sibling.name in ["h2", "h3"]:
                break
            content.append(sibling.get_text())
        sections.append((heading.get_text(), "\n".join(content)))
    return sections


def search_guides(search_text: str) -> list[dict[str, str]]:
    """Full-text search published guides, best matches first."""
    search_query = SearchQuery(search_text, config=SEARCH_CONFIG, search_type="websearch")
    vector = SearchVector("title", weight="A", config=SEARCH_CONFIG) + SearchVector(
        "text", weight="B", config=SEARCH_CONFIG
    )
    guides = (
        LarpManagerGuide.objects.filter(published=True)
        .annotate(search=vector, rank=SearchRank(vector, search_query))
        .filter(search=search_query)
        .order_by("-rank")[:GUIDES_LIMIT]
    )
    return [
        {"slug": guide.slug, "title": guide.title, "snippet": _html_to_text(guide.text)[:SNIPPET_LENGTH]}
        for guide in guides
    ]


def search_tutorials(search_text: str) -> list[dict[str, str]]:
    """Full-text search tutorial sections, grouped by tutorial relevance.

    Tutorials are ranked on their whole content, then the H2/H3 sections of the
    matching ones are ranked individually, keeping only the sections that match.
    """
    search_query = SearchQuery(search_text, config=SEARCH_CONFIG, search_type="websearch")
    vector = SearchVector("name", weight="A", config=SEARCH_CONFIG) + SearchVector(
        "descr", weight="B", config=SEARCH_CONFIG
    )
    tutorials = (
        LarpManagerTutorial.objects.annotate(search=vector, rank=SearchRank(vector, search_query))
        .filter(search=search_query)
        .order_by("-rank")[:TUTORIALS_LIMIT]
    )

    sections = [
        (tutorial, section_title, content)
        for tutorial in tutorials
        for section_title, content in _tutorial_sections(tutorial.descr)
    ]
    if not sections:
        return []

    # Rank every section in a single query, weighting headings over their content
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT section.idx
            FROM unnest(%s::text[], %s::text[]) WITH ORDINALITY AS section(title, content, idx),
                 websearch_to_tsquery(%s::regconfig, %s) AS query,
                 LATERAL (
                     SELECT setweight(to_tsvector(%s::regconfig, section.title), 'A')
                         || setweight(to_tsvector(%s::regconfig, section.content), 'B') AS vector
                 ) AS doc
            WHERE doc.vector @@ query
            ORDER BY ts_rank(doc.vector, query) DESC
            """,
            [
                [section_title for _tutorial, section_title, _content in sections],
                [content for _tutorial, _section_title, content in sections],
                SEARCH_CONFIG,
                search_text,
                SEARCH_CONFIG,
                SEARCH_CONFIG,
            ],
        )
        matching_indexes = [row[0] - 1 for row in cursor.fetchall()]

    # Keep tutorial relevance as primary order, section relevance as secondary
    tutorial_order = {tutorial.pk: position for position, tutorial in enumerate(tutorials)}
    matching_indexes.sort(key=lambda index: tutorial_order[sections[index][0].pk])

    return [
        {
            "slug": sections[index][0].slug,
            "title": sections[index][0].name,
            "section": sections[index][1],
            "snippet": sections[index][2][:SNIPPET_LENGTH],
        }
        for index in matching_indexes[:TUTORIALS_LIMIT]
    ]


def similarity(first_string: str, second_string: str) -> float:
    """Calculate similarity ratio between two strings (case-insensitive)."""
    return SequenceMatcher(None, first_string.lower(), second_string.lower()).ratio()


def get_sorted_permissions(model: type, query: str) -> list[dict[str, str]]:
    """Get permissions filtered by query and sorted by name similarity."""
    # Filter permissions by name or description containing the query
    permissions = model.objects.filter(Q(name__icontains=query) | Q(descr__icontains=query)).values(
        "name",
        "slug",
        "descr",
    )

    # Sort by similarity to query string, most similar first
    return sorted(permissions, key=lambda permission: similarity(permission["name"], query), reverse=True)


def query_index(request: HttpRequest) -> JsonResponse:
    """Handle search queries with translation support.

    Processes search requests and translates content using DeepL API,
    then searches through both permission-based navigation links, guides and
    tutorial content to provide relevant results.

    Args:
        request: Django HTTP request object containing POST data with:
            - q: Search query string
            - r: Optional run UUID for event-specific search

    Returns:
        JsonResponse containing search results with guides, tutorials, and links.
        Returns empty JsonResponse if run lookup fails.

    Raises:
        ObjectDoesNotExist: If specified run doesn't exist (handled internally)

    """
    # Extract and validate input parameters
    original_search_query: str = request.POST.get("q", "")
    run_uuid: str = request.POST.get("r", "")

    # Translate query string to English for consistent search
    translator = deepl.Translator(conf_settings.DEEPL_API_KEY)
    translated_query: str = str(translator.translate_text(original_search_query, target_lang="EN-US"))

    # Log search activity for admin monitoring
    notify_admins(f"query_index: {translated_query}", f"{original_search_query} - {request.user}")

    # Build permission-based navigation links
    permission_links: list[dict[str, str]] = []
    if run_uuid:
        # Event-specific permissions and links
        try:
            run = Run.objects.select_related("event").get(
                uuid=run_uuid, event__association_id=request.association["id"]
            )
        except ObjectDoesNotExist:
            return JsonResponse({})

        sorted_permissions: list[dict[str, Any]] = get_sorted_permissions(EventPermission, translated_query)
        permission_links = [
            {
                "name": permission["name"],
                "descr": permission["descr"],
                "href": reverse(permission["slug"], args=[run.get_slug()]),
            }
            for permission in sorted_permissions
        ]
    else:
        # Organization-wide permissions and links
        sorted_permissions = get_sorted_permissions(AssociationPermission, translated_query)
        permission_links = [
            {"name": permission["name"], "descr": permission["descr"], "href": reverse(permission["slug"])}
            for permission in sorted_permissions
        ]

    # Search through guide and tutorial content
    matching_guides = search_guides(translated_query)
    matching_tutorials = search_tutorials(translated_query)

    # Return consolidated search results
    return JsonResponse(
        {"guides": matching_guides, "tutorials": matching_tutorials, "links": permission_links},
        safe=False,
    )
