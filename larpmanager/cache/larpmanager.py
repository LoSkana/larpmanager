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
from __future__ import annotations

import random
import re
from datetime import UTC, datetime
from html import unescape

from django.core.cache import cache
from django.db.models import Count

from larpmanager.models.accounting import PaymentInvoice
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.larpmanager import LarpManagerHighlight, LarpManagerReview, LarpManagerShowcase, LarpManagerText
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration
from larpmanager.models.writing import Character
from larpmanager.utils.core.common import round_to_two_significant_digits


def clear_larpmanager_home_cache() -> None:
    """Clear the cached larpmanager home page."""
    cache.delete(cache_larpmanager_home_key())


def cache_larpmanager_home_key() -> str:
    """Generate cache key for larpmanager home data."""
    return "cache_lm_home"


def get_cache_lm_home() -> dict:
    """Get cached LM home data, computing if not cached.

    Returns:
        Cached or freshly computed home data.

    """
    # Get cache key and attempt to retrieve cached data
    cache_key = cache_larpmanager_home_key()
    cached_data = cache.get(cache_key)

    # If cache miss, compute fresh data and cache it
    if cached_data is None:
        cached_data = update_cache_lm_home()
        cache.set(cache_key, cached_data, timeout=300)

    return cached_data


def update_cache_lm_home() -> dict[str, int | list]:
    """Update and return cached data for the LarpManager home page.

    Collects statistics for various models including events, characters,
    registrations, members, and payment invoices. Also gathers data about
    active runs, promoters, showcases, and reviews.

    Returns:
        dict[str, int | list]: Dictionary containing:
            - cnt_<model>: Rounded count for each model type
            - cnt_run: Count of runs with more than 5 registrations
            - promoters: List of promoter data
            - showcase: List of showcase items
            - reviews: List of review data

    """
    context = {}

    # Count objects for main models and round to two significant digits
    for model_class in [Event, Character, Registration, Member, PaymentInvoice]:
        model_name = str(model_class.__name__).lower()
        model_count = model_class.objects.count()
        context[f"cnt_{model_name}"] = int(round_to_two_significant_digits(model_count))

    # Count runs that have more than 5 registrations
    runs_query = Run.objects.annotate(num_registration=Count("registrations")).filter(num_registration__gt=5)
    context["cnt_run"] = int(round_to_two_significant_digits(runs_query.count()))

    # Gather additional display data
    context["promoters"] = _get_promoters()
    context["showcase"] = _get_showcases()
    context["reviews"] = _get_reviews()

    return context


def _get_reviews() -> list[dict]:
    """Get all LARP manager reviews as dictionaries."""
    # Convert each review object to dictionary representation
    return [review.as_dict() for review in LarpManagerReview.objects.all()]


def _get_showcases() -> list[dict]:
    """Return all showcases with unique highlight assignments and blog links.

    Each showcase is assigned one unique highlight from the randomized pool.
    If there are more showcases than highlights, highlights are reused in a cycle.

    Returns:
        List of showcase dictionaries with assigned highlight data and blog links.

    """
    # Get showcases ordered by number, select_related blog
    showcases = list(LarpManagerShowcase.objects.select_related("blog").order_by("number"))

    # Get randomized highlights
    highlights = list(LarpManagerHighlight.objects.all())
    random.shuffle(highlights)

    # Assign one unique highlight to each showcase
    result = []
    for idx, showcase in enumerate(showcases):
        showcase_dict = showcase.as_dict()

        # Add blog data if present
        if showcase.blog:
            showcase_dict["blog"] = {
                "slug": showcase.blog.slug,
                "title": showcase.blog.title,
            }

        # Assign a highlight (cycle through if more showcases than highlights)
        if highlights:
            assigned_highlight = highlights[idx % len(highlights)]
            showcase_dict["highlight"] = assigned_highlight.as_dict()

        result.append(showcase_dict)

    return result


def _get_promoters() -> list[dict]:
    """Get all promoters from associations that have promoter data."""
    # Filter associations that have promoter data
    associations_queryset = Association.objects.exclude(promoter__isnull=True)
    associations_queryset = associations_queryset.exclude(promoter__exact="")

    # Convert each association's promoter to dictionary format
    return [association.promoter_dict() for association in associations_queryset]


def get_blog_content_with_images(blog_id: int, html_content: str) -> list[dict]:
    """Split blog content by h2/h3 headings and assign random daily images.

    Args:
        blog_id: ID of the blog post
        html_content: HTML content to split

    Returns:
        List of sections with format: [
            {"heading": "Title", "content": "HTML content", "image": highlight_dict},
            ...
        ]

    """
    cache_key = get_blog_cache_key(blog_id)
    cached_sections = cache.get(cache_key)

    if cached_sections:
        return cached_sections

    # Split content by h2 tags
    sections = _split_content_by_headings(html_content)

    # Get random highlights for today
    highlights = list(LarpManagerHighlight.objects.all())
    if highlights:
        random.shuffle(highlights)

        # Assign one highlight to each section (cycle if needed)
        for idx, section in enumerate(sections):
            section["image"] = highlights[idx % len(highlights)].as_dict()

    # Cache for 24 hours (86400 seconds)
    cache.set(cache_key, sections, timeout=86400)

    return sections


def _split_content_by_headings(html_content: str) -> list[dict]:
    """Split HTML content by h2 and h3 headings.

    Args:
        html_content: HTML content to split

    Returns:
        List of sections: [{"heading": "Title", "content": "HTML"}, ...]

    """
    if not html_content:
        return []

    sections = []

    # Check if there's content before the first h2 tag
    first_h2_match = re.search(r"<h[2]", html_content, re.IGNORECASE)
    if first_h2_match:
        initial_content = html_content[: first_h2_match.start()].strip()
        if initial_content:
            # Add initial content as first section with no heading
            sections.append(
                {
                    "heading": "",
                    "heading_level": "h2",
                    "content": initial_content,
                }
            )

    # Pattern to match h2 tags and capture content until next heading
    pattern = r"<(h[2])[^>]*>(.*?)</\1>(.*?)(?=<h[2]|$)"
    matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)

    for match in matches:
        heading_level = match[0]  # h2 or h3
        heading_text = unescape(re.sub(r"<[^>]+>", "", match[1])).strip()
        content_html = match[2].strip()

        if heading_text or content_html:
            sections.append(
                {
                    "heading": heading_text,
                    "heading_level": heading_level,
                    "content": content_html,
                }
            )

    return sections


def clear_blog_cache(blog_id: int) -> None:
    """Clear cached blog content for a specific blog post."""
    cache_key = get_blog_cache_key(blog_id)
    cache.delete(cache_key)


def get_blog_cache_key(blog_id: int) -> str:
    """Get key for a blog content cache."""
    return f"blog_content_{blog_id}_{datetime.now(tz=UTC).date()}"


def cache_larpmanager_texts_key() -> str:
    """Generate cache key for larpmanager texts."""
    return "cache_lm_texts"


def get_larpmanager_texts() -> dict[str, str]:
    """Get cached LarpManager texts as a dictionary.

    Returns:
        Dictionary mapping text names to their values.

    """
    cache_key = cache_larpmanager_texts_key()
    cached_texts = cache.get(cache_key)

    if cached_texts is None:
        cached_texts = {text.name: text.value for text in LarpManagerText.objects.all()}
        cache.set(cache_key, cached_texts, timeout=86400)

    return cached_texts


def clear_larpmanager_texts_cache() -> None:
    """Clear the cached larpmanager texts."""
    cache.delete(cache_larpmanager_texts_key())
