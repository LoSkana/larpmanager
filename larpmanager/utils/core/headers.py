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
"""Association-scoped email header and URL builders.

Split out of larpmanager.models.association: these helpers need
larpmanager.cache.basic (to resolve run/association ids to cached slugs and
names), while cache.basic itself needs the Association/Event model classes at
import time. Keeping these functions in the models module would recreate that
import cycle, so callers (mail templates, notifications, tasks) import them
from here instead.
"""

from __future__ import annotations

from typing import Any

from larpmanager.cache.basic import get_association_basic_cache, get_run_basic_cache
from larpmanager.models.association import Association


def hdr(association_or_related_object: Association | Any) -> str:
    """Return a formatted header string with the association name in brackets.

    Accepts an Association instance, or any object with an `association` attribute.
    For a bare run id, use `hdr_run()` instead.
    """
    # Check if object is an Association instance directly
    if isinstance(association_or_related_object, Association):
        return f"[{association_or_related_object.name}] "
    # Check if object has an associated Association via association attribute
    if association_or_related_object.association:
        return f"[{association_or_related_object.association.name}] "
    return "[LarpManager] "


def hdr_run(run_id: int) -> str:
    """Return a formatted header string with the association name in brackets, from a run id."""
    return hdr_association(get_run_basic_cache(run_id)["association_id"])


def hdr_association(association_id: int) -> str:
    """Return a formatted header string with the association name in brackets, from an association id."""
    return f"[{get_association_basic_cache(association_id)['name']}] "


def get_url(path: str, obj: object = None) -> str:
    """Generate a URL for the given path and object.

    Constructs URLs based on the type of object provided. For Association objects,
    uses the association's slug and domain. For objects with an 'association' attribute,
    uses the associated organization's slug and domain. Falls back to default
    larpmanager.com domain when no object is provided.

    Args:
        path: The path/route to append to the base URL
        obj: Optional object to determine the base URL. Can be Association,
             an object with 'association' attribute, or a string slug

    Returns:
        Complete URL string with proper protocol formatting

    """
    if obj:
        # Handle Association objects directly
        if isinstance(obj, Association):
            url = _build_association_url(path, obj.slug, obj.skin.domain)
        # Handle objects that belong to an association
        elif hasattr(obj, "association"):
            return get_association_url(path, obj.association_id)
        # Handle string slugs or other objects
        else:
            url = f"https://{obj}.larpmanager.com/{path}"
    else:
        # Default to main larpmanager.com domain
        url = "https://larpmanager.com/" + path

    return _clean_url(url)


def _clean_url(url: str) -> str:
    """Clean up double slashes in a URL while preserving the protocol."""
    return url.replace("//", "/").replace(":/", "://")


def _build_association_url(path: str, slug: str, domain: str) -> str:
    """Build the raw (uncleaned) URL for a path under an association's slug/domain."""
    return f"https://{slug}.{domain}/{path}"


def get_association_url(path: str, association_id: int) -> str:
    """Build a URL for path using the association's cached slug/domain."""
    assoc_cache = get_association_basic_cache(association_id)
    url = _build_association_url(path, assoc_cache["slug"], assoc_cache["domain"])
    return _clean_url(url)
