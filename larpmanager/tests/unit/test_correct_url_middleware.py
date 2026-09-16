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

"""Tests for CorrectUrlMiddleware.

Verifies double-slash collapsing only touches the path, never the querystring -
a 'next' parameter carrying an absolute URL (e.g. "https://...") must survive
untouched, since collapsing it would corrupt the post-login redirect target.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory

from larpmanager.middleware.url import CorrectUrlMiddleware


class TestCorrectUrlMiddleware:
    """Test double-slash and malformed-URL handling in CorrectUrlMiddleware."""

    @staticmethod
    def _call(path: str) -> HttpResponse:
        middleware = CorrectUrlMiddleware(get_response=lambda request: HttpResponse("ok"))
        request = RequestFactory().get(path)
        return middleware(request)

    def test_next_param_with_absolute_url_is_untouched(self) -> None:
        """A 'next' querystring param with '//' in its scheme must not be collapsed."""
        path = "/accounts/login/?next=https://sub.domain.com/after_login/test-org/"
        response = self._call(path)

        # No double slash in the path itself, so the request must pass through unchanged
        assert response.status_code == 200
        assert response.content == b"ok"

    def test_double_slash_in_path_is_collapsed(self) -> None:
        """A genuine double slash in the path is still collapsed."""
        response = self._call("/accounts//google/login/")

        assert response.status_code == 302
        assert response.url == "/accounts/google/login/"

    def test_double_slash_in_path_preserves_querystring(self) -> None:
        """Collapsing the path must not drop or mangle an accompanying querystring."""
        response = self._call("/accounts//login/?next=/manage/")

        assert response.status_code == 302
        assert response.url == "/accounts/login/?next=/manage/"

    def test_leading_double_slash_does_not_become_protocol_relative(self) -> None:
        """A path starting with '//' must collapse to a single leading slash.

        Must not be misparsed as a protocol-relative URL (scheme-relative netloc).
        RequestFactory normalizes a leading '//' in the URL it's given (treating it as
        scheme-relative), so PATH_INFO is set directly to simulate the raw request path.
        """
        middleware = CorrectUrlMiddleware(get_response=lambda request: HttpResponse("ok"))
        request = RequestFactory().get("/path/")
        request.path = request.path_info = "//evil.example.com/path/"
        response = middleware(request)

        assert response.status_code == 302
        assert response.url == "/evil.example.com/path/"

    def test_google_callback_double_slash_in_next_param(self) -> None:
        """Google OAuth callback next param with '//' must survive untouched."""
        path = "/accounts/google/login/callback/?next=https://sub.domain.com/after_login/test-org/"
        response = self._call(path)

        assert response.status_code == 200
        assert response.content == b"ok"

    def test_undefined_suffix_is_stripped(self) -> None:
        """Trailing '/undefined' segment from JS redirects is removed."""
        response = self._call("/some/path/undefined")

        assert response.status_code == 302
        assert response.url == "/some/path"

    def test_clean_path_passes_through(self) -> None:
        """A well-formed path with no issues reaches the view unchanged."""
        response = self._call("/accounts/login/?next=/manage/")

        assert response.status_code == 200
        assert response.content == b"ok"
