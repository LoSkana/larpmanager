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

import html
import re

from django.core.cache import cache
from slugify import slugify

from larpmanager.models.base import Feature
from larpmanager.models.larpmanager import LarpManagerGuide, LarpManagerTutorial


def get_guides_cache_key() -> str:
    """Get the cache key for guides data.

    Returns:
        str: The cache key used for storing/retrieving guides data
    """
    return "guides_cache"


def get_tutorials_cache_key() -> str:
    """Get the cache key for tutorials data.

    Returns:
        str: The cache key used for storing/retrieving tutorials data
    """
    return "tutorials_cache"


def get_features_cache_key() -> str:
    """Get the cache key for features data.

    Returns:
        str: The cache key used for storing/retrieving features data
    """
    return "features_cache"


def get_guides_cache() -> list[dict]:
    """Get cached guides data.

    Returns:
        List of guide items with: slug, title, content_preview
    """
    cache_key = get_guides_cache_key()
    cached_data = cache.get(cache_key)

    if cached_data is not None:
        return cached_data

    # Build cache data
    data = _build_guides_cache()

    # Cache for 1 day (86400 seconds)
    cache.set(cache_key, data, timeout=86400)
    return data


def get_tutorials_cache() -> list[dict]:
    """Get cached tutorials data.

    Returns:
        List of tutorial items with: slug, title, content_preview, section_slug, section_title
    """
    cache_key = get_tutorials_cache_key()
    cached_data = cache.get(cache_key)

    if cached_data is not None:
        return cached_data

    # Build cache data
    data = _build_tutorials_cache()

    # Cache for 1 day (86400 seconds)
    cache.set(cache_key, data, timeout=86400)
    return data


def get_features_cache() -> list[dict]:
    """Get cached features data for 'what would you like to do'.

    Returns:
        List of feature items with: tutorial, name, module_name, descr
    """
    cache_key = get_features_cache_key()
    cached_data = cache.get(cache_key)

    if cached_data is not None:
        return cached_data

    # Build cache data
    data = _build_features_cache()

    # Cache for 1 day (86400 seconds)
    cache.set(cache_key, data, timeout=86400)
    return data


def reset_guides_cache():
    """Reset the guides cache."""
    cache_key = get_guides_cache_key()
    cache.delete(cache_key)


def reset_tutorials_cache():
    """Reset the tutorials cache."""
    cache_key = get_tutorials_cache_key()
    cache.delete(cache_key)


def reset_features_cache():
    """Reset the features cache."""
    cache_key = get_features_cache_key()
    cache.delete(cache_key)


def _build_guides_cache() -> list[dict]:
    """Build cache data for guides."""
    guides = []

    for guide in LarpManagerGuide.objects.filter(published=True).order_by("number"):
        guides.append(
            {"slug": guide.slug, "title": guide.title, "content_preview": _get_content_preview(guide.text, 100)}
        )

    return guides


def _build_tutorials_cache() -> list[dict]:
    """Build cache data for tutorials with sections."""
    tutorials = []

    for tutorial in LarpManagerTutorial.objects.order_by("order"):
        # Extract H2 sections from content
        sections = _extract_h2_sections(tutorial.descr)
        for section_title, section_content in sections:
            section_slug = slugify(section_title)
            tutorials.append(
                {
                    "slug": tutorial.slug,
                    "title": tutorial.name,
                    "content_preview": _get_content_preview(section_content, 100),
                    "section_slug": section_slug,
                    "section_title": section_title,
                }
            )

    return tutorials


def _build_features_cache() -> list[dict]:
    """Build cache data for features with tutorials."""
    features = []

    for feature in (
        Feature.objects.filter(placeholder=False, hidden=False, tutorial__isnull=False)
        .exclude(tutorial__exact="")
        .select_related("module")
    ):
        features.append(
            {
                "tutorial": feature.tutorial,
                "name": feature.name,
                "module_name": feature.module.name if feature.module else None,
                "descr": feature.descr,
            }
        )

    return features


def _extract_h2_sections(content: str) -> list[tuple]:
    """Extract H2 sections from HTML content.

    Args:
        content: HTML content string

    Returns:
        List of (section_title, section_content) tuples
    """
    sections = []

    # Find all H2 headings and their content
    h2_pattern = r"<h2[^>]*>(.*?)</h2>(.*?)(?=<h2|$)"
    matches = re.finditer(h2_pattern, content, re.DOTALL | re.IGNORECASE)

    for match in matches:
        section_title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        section_content = match.group(2).strip()

        if section_title and section_content:
            sections.append((section_title, section_content))

    return sections


def _get_content_preview(content: str, max_length: int = 200) -> str:
    """Get text preview from HTML content.

    Args:
        content: HTML content string
        max_length: Maximum length of preview text

    Returns:
        Clean text preview
    """
    if not content:
        return ""

    # Remove HTML tags
    clean_text = re.sub(r"<[^>]+>", " ", content)

    # Convert HTML entities to text (e.g., &nbsp; to space, &amp; to &)
    clean_text = html.unescape(clean_text)

    # Clean up whitespace (including converted non-breaking spaces)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    # Truncate to max length
    if len(clean_text) > max_length:
        clean_text = clean_text[:max_length].rsplit(" ", 1)[0] + "..."

    return clean_text
