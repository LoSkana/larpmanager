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
"""Helpers to remember which organization subdomain a social login started from.

Social logins always begin on the main domain (the OAuth redirect URI is only
registered there), and the target subdomain normally travels in the 'next'
parameter that django-allauth stashes in its per-attempt session state. That
state is dropped when more than a handful of logins are pending, so the slug is
also kept in a single session key that survives, used as a fallback when the
allauth state is gone.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

# Session key holding (slug, timestamp) of the subdomain the login started from
SSO_SLUG_SESSION_KEY = "sso_login_slug"

# Discard the stashed slug after this many seconds, so an abandoned social login
# cannot redirect a later, unrelated login away from the main domain
SSO_SLUG_MAX_AGE = 600

# Lifetime of the one-shot token that carries the login across subdomains: long
# enough for a slow mobile hop, short enough to stay a single-use handoff
SESSION_TOKEN_TTL = 300

_AFTER_LOGIN_RE = re.compile(r"/after_login/(?P<slug>[-\w]+)/")


def session_token_key(token: str) -> str:
    """Return the cache key holding the user id for a cross-subdomain token."""
    return f"session_token:{token}"


def extract_after_login_slug(next_url: str | None) -> str | None:
    """Return the organization slug of an /after_login/<slug>/ URL, if any."""
    if not next_url:
        return None
    match = _AFTER_LOGIN_RE.search(next_url)
    return match.group("slug") if match else None


def stash_login_slug(request: HttpRequest, slug: str) -> None:
    """Remember the subdomain slug the current social login started from."""
    request.session[SSO_SLUG_SESSION_KEY] = [slug, time.time()]


def pop_login_slug(request: HttpRequest) -> str | None:
    """Return and clear the stashed subdomain slug, ignoring stale entries."""
    session = getattr(request, "session", None)
    if session is None:
        return None

    stashed = session.pop(SSO_SLUG_SESSION_KEY, None)
    if not stashed:
        return None

    try:
        slug, stashed_at = stashed
    except (TypeError, ValueError):
        return None

    if time.time() - stashed_at > SSO_SLUG_MAX_AGE:
        return None

    return slug
