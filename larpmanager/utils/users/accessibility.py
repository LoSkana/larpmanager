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

from typing import TYPE_CHECKING

from larpmanager.cache.config import get_member_config, save_single_config

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

ACCESSIBILITY_CONFIG = "member_a11y"
ACCESSIBILITY_COOKIE = "lm_a11y"
ACCESSIBILITY_COOKIE_MAX_AGE = 60 * 60 * 24 * 365

# Exclusive groups: form field name -> allowed values
ACCESSIBILITY_CHOICES = {
    "font": ["dyslexic", "sans"],
    "size": ["l", "xl"],
    "color": ["contrast", "cb"],
}

# Independent on/off toggles
ACCESSIBILITY_FLAGS = ["spacing", "links", "motion", "nobg"]


def parse_accessibility(value: str | None) -> list[str]:
    """Return the valid accessibility tokens contained in a comma-separated string."""
    if not value:
        return []

    allowed = {f"{group}-{choice}" for group, choices in ACCESSIBILITY_CHOICES.items() for choice in choices}
    allowed.update(ACCESSIBILITY_FLAGS)

    tokens = []
    seen_groups = set()
    for raw_token in str(value).split(","):
        token = raw_token.strip()
        if token not in allowed or token in tokens:
            continue
        group = token.split("-", 1)[0] if "-" in token else None
        if group:
            if group in seen_groups:
                continue
            seen_groups.add(group)
        tokens.append(token)
    return tokens


def accessibility_from_post(post: dict) -> list[str]:
    """Build the accessibility tokens from submitted panel values."""
    tokens = [f"{group}-{post.get(group)}" for group in ACCESSIBILITY_CHOICES if post.get(group)]
    tokens.extend(flag for flag in ACCESSIBILITY_FLAGS if post.get(flag) in ("1", "true", "on"))
    return parse_accessibility(",".join(tokens))


def get_accessibility_tokens(request: HttpRequest) -> list[str]:
    """Return the accessibility tokens for the request, from member config or cookie."""
    member = getattr(getattr(request, "user", None), "member", None)
    if member is not None and request.user.is_authenticated:
        saved = get_member_config(member.id, ACCESSIBILITY_CONFIG)
        if saved:
            return parse_accessibility(saved)
    return parse_accessibility(request.COOKIES.get(ACCESSIBILITY_COOKIE))


def save_accessibility(request: HttpRequest, response: HttpResponse, tokens: list[str]) -> None:
    """Persist accessibility tokens in the cookie and, for logged users, in the member config."""
    value = ",".join(tokens)
    if value:
        response.set_cookie(
            ACCESSIBILITY_COOKIE,
            value,
            max_age=ACCESSIBILITY_COOKIE_MAX_AGE,
            samesite="Lax",
            secure=request.is_secure(),
        )
    else:
        response.delete_cookie(ACCESSIBILITY_COOKIE)

    member = getattr(request.user, "member", None) if request.user.is_authenticated else None
    if member is not None:
        save_single_config(member, ACCESSIBILITY_CONFIG, value)
