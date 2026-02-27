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

from larpmanager.forms.association import ExeConfigForm
from larpmanager.forms.event import OrgaConfigForm
from larpmanager.models.base import Feature
from larpmanager.models.larpmanager import LarpManagerGuide, LarpManagerTutorial


def get_orga_configs_cache_key(event_id: int) -> str:
    """Get the cache key for orga (event) config data."""
    return f"orga_configs_cache_{event_id}"


def get_exe_configs_cache_key(association_id: int) -> str:
    """Get the cache key for exe (association) config data."""
    return f"exe_configs_cache_{association_id}"


def get_guides_cache_key() -> str:
    """Get the cache key for guides data."""
    return "guides_cache"


def get_tutorials_cache_key() -> str:
    """Get the cache key for tutorials data."""
    return "tutorials_cache"


def get_features_cache_key() -> str:
    """Get the cache key for features data."""
    return "features_cache"


def get_guides_cache() -> list[dict]:
    """Get cached guides data.

    Returns:
        List of guide items with: slug, title, content_preview

    """
    cache_key = get_guides_cache_key()
    cached_guides = cache.get(cache_key)

    if cached_guides is not None:
        return cached_guides

    # Build cache data
    guides_data = _build_guides_cache()

    # Cache for 1 day (86400 seconds)
    cache.set(cache_key, guides_data, timeout=86400)
    return guides_data


def get_tutorials_cache() -> list[dict]:
    """Get cached tutorials data.

    Returns:
        List of tutorial items with: slug, title, content_preview, section_slug, section_title

    """
    cache_key = get_tutorials_cache_key()
    cached_tutorials = cache.get(cache_key)

    if cached_tutorials is not None:
        return cached_tutorials

    # Build cache data
    tutorials_data = _build_tutorials_cache()

    # Cache for 1 day (86400 seconds)
    cache.set(cache_key, tutorials_data, timeout=86400)
    return tutorials_data


def get_features_cache() -> list[dict]:
    """Get cached features data for 'what would you like to do'.

    Returns:
        List of feature items with: tutorial, name, module_name, descr

    """
    cache_key = get_features_cache_key()
    cached_features = cache.get(cache_key)

    if cached_features is not None:
        return cached_features

    # Build cache data
    features_list = _build_features_cache()

    # Cache for 1 day (86400 seconds)
    cache.set(cache_key, features_list, timeout=86400)
    return features_list


def get_orga_configs_cache(event_id: int, features: set) -> list[dict]:
    """Get cached orga (event) config field definitions for a specific event."""
    cache_key = get_orga_configs_cache_key(event_id)
    cached = cache.get(cache_key)

    if cached is not None:
        return cached

    data = _extract_config_fields(OrgaConfigForm, features)
    cache.set(cache_key, data, timeout=86400)
    return data


def get_exe_configs_cache(association_id: int, features: set) -> list[dict]:
    """Get cached exe (association) config field definitions for a specific association."""
    cache_key = get_exe_configs_cache_key(association_id)
    cached = cache.get(cache_key)

    if cached is not None:
        return cached

    data = _extract_config_fields(ExeConfigForm, features)
    cache.set(cache_key, data, timeout=86400)
    return data


def reset_guides_cache() -> None:
    """Reset the guides cache."""
    guides_cache_key = get_guides_cache_key()
    cache.delete(guides_cache_key)


def reset_tutorials_cache() -> None:
    """Reset the tutorials cache."""
    tutorials_cache_key = get_tutorials_cache_key()
    cache.delete(tutorials_cache_key)


def reset_features_cache() -> None:
    """Reset the features cache."""
    features_cache_key = get_features_cache_key()
    cache.delete(features_cache_key)


def reset_orga_configs_cache(event_id: int) -> None:
    """Reset the orga configs cache for a specific event."""
    cache.delete(get_orga_configs_cache_key(event_id))


def reset_exe_configs_cache(association_id: int) -> None:
    """Reset the exe configs cache for a specific association."""
    cache.delete(get_exe_configs_cache_key(association_id))


def _build_guides_cache() -> list[dict]:
    """Build cache data for guides."""
    return [
        {
            "slug": published_guide.slug,
            "title": published_guide.title,
            "content_preview": _get_content_preview(published_guide.text, 100),
        }
        for published_guide in LarpManagerGuide.objects.filter(published=True).order_by("number")
    ]


def _build_tutorials_cache() -> list[dict]:
    """Build cache data for tutorials with sections."""
    tutorials = []

    for tutorial in LarpManagerTutorial.objects.order_by("order"):
        # Extract H2 sections from content
        h2_sections = _extract_h2_sections(tutorial.descr)
        for section_title, section_content in h2_sections:
            section_slug = slugify(section_title)
            tutorials.append(
                {
                    "slug": tutorial.slug,
                    "title": tutorial.name,
                    "content_preview": _get_content_preview(section_content, 100),
                    "section_slug": section_slug,
                    "section_title": section_title,
                },
            )

    return tutorials


def _build_features_cache() -> list[dict]:
    """Build cache data for features with tutorials."""
    return [
        {
            "tutorial": feature.tutorial,
            "name": feature.name,
            "module_name": feature.module.name if feature.module else None,
            "descr": feature.descr,
        }
        for feature in Feature.objects.filter(placeholder=False, hidden=False, tutorial__isnull=False)
        .exclude(tutorial__exact="", module__order=0)
        .select_related("module")
    ]


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
    h2_matches = re.finditer(h2_pattern, content, re.DOTALL | re.IGNORECASE)

    for h2_match in h2_matches:
        section_title = re.sub(r"<[^>]+>", "", h2_match.group(1)).strip()
        section_content = h2_match.group(2).strip()

        if section_title and section_content:
            sections.append((section_title, section_content))

    return sections


class _MockInstance:
    """Minimal stub for set_config_* methods that access self.instance attributes.

    Provides truthy values so all config entries are included regardless of the
    specific instance state. extra_data (e.g. self.instance.id) is ignored by the
    overridden add_configs, so id=0 is safe.
    """

    id = 0
    main_mail = "mock"  # include email-gated configs with a truthy value


def _extract_config_fields(form_class: type, features: set) -> list[dict]:
    """Extract config field definitions from a ConfigForm subclass without full initialization.

    Uses __new__ to bypass ModelForm.__init__ and injects lightweight overrides for
    set_section and add_configs to capture field metadata with section slugs.

    Args:
        form_class: A ConfigForm subclass (e.g. OrgaConfigForm, ExeConfigForm)
        features: Set of activated feature slugs for this event or association.

    Returns:
        List of dicts with: key, label, help_text, section, section_slug

    """
    # Create instance without calling __init__ to avoid DB access / model requirements
    form = form_class.__new__(form_class)
    form.config_fields = []
    form._section = None  # noqa: SLF001
    form._section_slug = None  # noqa: SLF001
    form.jump_section = None

    form.params = {
        "features": features,
        "skin_id": 1,
    }

    # Provide a minimal mock instance so set_config_* methods that check
    # self.instance.main_mail or use self.instance.id as extra_data don't fail.
    # extra_data is ignored by our _add_configs override; main_mail=True includes
    # those config entries (since the association may have it set).
    form.instance = _MockInstance()

    # Override set_section to also capture section_slug (via closure over form)
    def _set_section(section_slug: str, section_name: str) -> None:
        form._section = section_name  # noqa: SLF001
        form._section_slug = section_slug  # noqa: SLF001

    # Override add_configs to record key, label, help_text and section_slug
    def _add_configs(
        configuration_key: str,
        config_type: object,  # noqa: ARG001
        field_label: str,
        field_help_text: str,
        extra_data: object = None,  # noqa: ARG001
    ) -> None:
        form.config_fields.append(
            {
                "key": configuration_key,
                "label": field_label,
                "help_text": field_help_text,
                "section": form._section,  # noqa: SLF001
                "section_slug": form._section_slug,  # noqa: SLF001
            }
        )

    # Store as plain instance attributes; Python finds instance attrs before class methods
    form.set_section = _set_section
    form.add_configs = _add_configs

    form.set_configs()
    return form.config_fields


def _get_content_preview(html_content: str, maximum_preview_length: int = 200) -> str:
    """Get text preview from HTML content.

    Args:
        html_content: HTML content string
        maximum_preview_length: Maximum length of preview text

    Returns:
        Clean text preview

    """
    if not html_content:
        return ""

    # Remove HTML tags
    plain_text = re.sub(r"<[^>]+>", " ", html_content)

    # Convert HTML entities to text (e.g., &nbsp; to space, &amp; to &)
    plain_text = html.unescape(plain_text)

    # Clean up whitespace (including converted non-breaking spaces)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()

    # Truncate to max length
    if len(plain_text) > maximum_preview_length:
        plain_text = plain_text[:maximum_preview_length].rsplit(" ", 1)[0] + "..."

    return plain_text
