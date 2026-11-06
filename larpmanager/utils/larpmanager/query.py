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

from typing import Any

from bs4 import BeautifulSoup
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import connection
from django.urls import reverse
from slugify import slugify

from larpmanager.models.larpmanager import LarpManagerGuide, LarpManagerTutorial

SEARCH_CONFIG = "english"

GUIDES_LIMIT = 5

TUTORIALS_LIMIT = 10


def _html_to_text(html: str | None) -> str:
    """Strip HTML tags, returning the plain text content."""
    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)


def _html_sections(html: str | None) -> list[tuple[str, str]]:
    """Split HTML into (heading, text) pairs, one for each H2/H3 section."""
    sections = []
    soup = BeautifulSoup(html or "", "html.parser")
    for heading in soup.find_all(["h2", "h3"]):
        content = []
        # Collect content following this heading until the next one
        for sibling in heading.find_next_siblings():
            if sibling.name in ["h2", "h3"]:
                break
            content.append(sibling.get_text())
        sections.append((heading.get_text(strip=True), "\n".join(content)))
    return sections


def _rank_sections(sections: list[tuple[Any, str, str]], search_text: str) -> list[int]:
    """Return the indexes of the (owner, title, content) sections matching, best first."""
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
                [section_title for _owner, section_title, _content in sections],
                [content for _owner, _section_title, content in sections],
                SEARCH_CONFIG,
                search_text,
                SEARCH_CONFIG,
                SEARCH_CONFIG,
            ],
        )
        return [row[0] - 1 for row in cursor.fetchall()]


def _tutorial_doc(tutorial: LarpManagerTutorial, section_title: str, text: str) -> dict[str, str]:
    """Build the result for a tutorial section, linked through its anchor."""
    url = reverse("tutorials", args=[tutorial.slug])
    if section_title:
        url += f"#{slugify(section_title)}"
    return {"title": tutorial.name, "section": section_title, "url": url, "text": text}


def search_guides(search_text: str) -> list[dict[str, str]]:
    """Full-text search published guides, best matches first, each with its best section."""
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

    sections = [
        (guide, section_title, content) for guide in guides for section_title, content in _html_sections(guide.text)
    ]
    best_sections: dict[int, tuple[str, str]] = {}
    for index in _rank_sections(sections, search_text):
        guide, section_title, content = sections[index]
        best_sections.setdefault(guide.pk, (section_title, content))

    results = []
    for guide in guides:
        section_title, text = best_sections.get(guide.pk, ("", _html_to_text(guide.text)))
        results.append(
            {"title": guide.title, "section": section_title, "url": reverse("guide", args=[guide.slug]), "text": text}
        )
    return results


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
        for section_title, content in _html_sections(tutorial.descr)
    ]
    matching_indexes = _rank_sections(sections, search_text)

    # Keep tutorial relevance as primary order, section relevance as secondary
    tutorial_order = {tutorial.pk: position for position, tutorial in enumerate(tutorials)}
    matching_indexes.sort(key=lambda index: tutorial_order[sections[index][0].pk])

    return [
        _tutorial_doc(sections[index][0], sections[index][1], sections[index][2])
        for index in matching_indexes[:TUTORIALS_LIMIT]
    ]


def get_tutorial_doc(tutorial_reference: str) -> dict[str, str] | None:
    """Return the tutorial named by a "slug" or "slug#section" reference, narrowed to that section."""
    slug, _separator, section_slug = tutorial_reference.replace("/", "").partition("#")
    tutorial = LarpManagerTutorial.objects.filter(slug=slug).first()
    if not tutorial:
        return None

    for section_title, content in _html_sections(tutorial.descr):
        if section_slug and slugify(section_title) == section_slug:
            return _tutorial_doc(tutorial, section_title, content)
    return _tutorial_doc(tutorial, "", _html_to_text(tutorial.descr))
