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
"""Tests that a password reset brings the user back to the page it started from."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from larpmanager.templatetags.show_tags import auth_next_query
from larpmanager.utils.auth.sso import (
    PASSWORD_RESET_NEXT_URL_SESSION_KEY,
    pop_password_reset_next_url,
    stash_password_reset_next_url,
)

if TYPE_CHECKING:
    from django.test import Client


def test_reset_email_link_carries_next() -> None:
    """The emailed reset link carries the page the reset started from."""
    body = render_to_string(
        "registration/password_reset_email_next.html",
        {
            "protocol": "https",
            "domain": "test.larpmanager.com",
            "uid": "abc",
            "token": "tok-en",
            "site_name": "test",
            "next_query": "?next=%2Fevent%2Ftest%2F",
        },
    )

    assert "https://test.larpmanager.com/reset/abc/tok-en/?next=%2Fevent%2Ftest%2F" in body


@pytest.mark.django_db
def test_password_reset_keeps_next(client: Client) -> None:
    """The 'next' of the emailed link survives until the login link after the reset."""
    user = User.objects.create_user(username="reset@test.it", email="reset@test.it", password="Old-pass-123")

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    response = client.get(f"/reset/{uid}/{token}/", {"next": "/event/test/"})
    response = client.post(
        response["Location"], {"new_password1": "New-pass-98765x", "new_password2": "New-pass-98765x"}
    )

    assert "next=%2Fevent%2Ftest%2F" in response["Location"]
    response = client.get(response["Location"])
    assert b'href="/login/?next=%2Fevent%2Ftest%2F"' in response.content


def test_reset_next_roundtrip() -> None:
    """The stashed destination is returned once, then cleared."""
    request = RequestFactory().get("/reset/abc/set-password/")
    request.session = {}
    stash_password_reset_next_url(request, "/event/test/register/")

    assert pop_password_reset_next_url(request, 60) == "/event/test/register/"
    assert pop_password_reset_next_url(request, 60) is None


def test_reset_next_stale_is_ignored() -> None:
    """A destination older than the reset timeout is dropped."""
    request = RequestFactory().get("/reset/abc/set-password/")
    request.session = {PASSWORD_RESET_NEXT_URL_SESSION_KEY: ["/event/test/", time.time() - 120]}

    assert pop_password_reset_next_url(request, 60) is None


def test_reset_complete_link_passes_next() -> None:
    """The login link on the reset complete page keeps the destination."""
    request = RequestFactory().get("/accounts/reset/done/", {"next": "/event/test/"})

    assert auth_next_query({"request": request}) == "?next=%2Fevent%2Ftest%2F"
