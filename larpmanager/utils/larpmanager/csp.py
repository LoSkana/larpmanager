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
"""Aggregation of Content-Security-Policy violation reports into a daily admin digest."""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from django.core.cache import cache
from django.utils.html import escape

from larpmanager.utils.larpmanager.tasks import notify_admins

# Cache key holding the details of each distinct violation, keyed by signature
CSP_INDEX_KEY = "csp_report_index"

# Prefix of the per-signature hit counters
CSP_COUNT_PREFIX = "csp_report_count:"

# Reports are kept a bit longer than the daily digest interval
CSP_REPORT_TIMEOUT = 2 * 24 * 60 * 60

# Distinct violations tracked between two digests; further ones are only counted if already known
CSP_MAX_SIGNATURES = 500

# Violations listed in the digest, the most frequent first
CSP_DIGEST_SIZE = 50

# Longest value kept for each report field
CSP_FIELD_MAX_LENGTH = 300

# Sources injected by browser extensions, which the site cannot fix
CSP_IGNORED_SCHEMES = ("chrome-extension", "moz-extension", "safari-extension", "safari-web-extension")


def _strip_query(url: str) -> str:
    """Drop querystring and fragment from a URL, so tokens never end up in the digest."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _field(report: dict, name: str) -> str:
    """Return a report field as a bounded string."""
    return str(report.get(name, ""))[:CSP_FIELD_MAX_LENGTH]


def record_csp_report(payload: Any) -> bool:
    """Count a violation report sent by the browser, returning False if it was discarded."""
    if not isinstance(payload, dict):
        return False
    report = payload.get("csp-report")
    if not isinstance(report, dict):
        return False

    directive = _field(report, "effective-directive") or _field(report, "violated-directive")
    blocked = _strip_query(_field(report, "blocked-uri")) or _field(report, "blocked-uri")
    source = _strip_query(_field(report, "source-file"))
    line = _field(report, "line-number")

    if not directive or any(value.startswith(CSP_IGNORED_SCHEMES) for value in (blocked, source)):
        return False

    signature = hashlib.md5(f"{directive}|{blocked}|{source}|{line}".encode(), usedforsecurity=False).hexdigest()
    count_key = CSP_COUNT_PREFIX + signature

    # First hit of a new violation: register it in the index, unless the index is full
    if cache.add(count_key, 0, CSP_REPORT_TIMEOUT):
        index = cache.get(CSP_INDEX_KEY) or {}
        if len(index) >= CSP_MAX_SIGNATURES:
            cache.delete(count_key)
            return False
        index[signature] = {
            "directive": directive,
            "blocked": blocked,
            "source": source,
            "line": line,
            "document": _strip_query(_field(report, "document-uri")),
        }
        cache.set(CSP_INDEX_KEY, index, CSP_REPORT_TIMEOUT)

    try:
        cache.incr(count_key)
    except ValueError:
        # Counter expired between add and incr
        return False
    return True


def pop_csp_reports() -> list[dict]:
    """Return the collected violations sorted by frequency, clearing them."""
    index = cache.get(CSP_INDEX_KEY) or {}
    cache.delete(CSP_INDEX_KEY)
    if not index:
        return []

    count_keys = {CSP_COUNT_PREFIX + signature: signature for signature in index}
    counts = cache.get_many(list(count_keys))
    cache.delete_many(list(count_keys))

    violations = [{**index[signature], "count": counts.get(key, 0)} for key, signature in count_keys.items()]
    violations = [violation for violation in violations if violation["count"]]
    return sorted(violations, key=lambda violation: violation["count"], reverse=True)


def send_csp_digest() -> None:
    """Email admins the most frequent violations collected since the last digest."""
    violations = pop_csp_reports()
    if not violations:
        return

    total = sum(violation["count"] for violation in violations)
    lines = [f"{total} reports, {len(violations)} distinct violations"]
    for violation in violations[:CSP_DIGEST_SIZE]:
        location = escape(violation["source"])
        if violation["line"]:
            location += f":{escape(violation['line'])}"
        lines.append(
            f"<b>{violation['count']}x</b> {escape(violation['directive'])} - blocked {escape(violation['blocked'])}"
            f"<br />at {location or '-'}<br />page {escape(violation['document']) or '-'}"
        )
    notify_admins("CSP violations daily digest", "<br /><br />".join(lines))
