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

"""Tests for the accessibility preferences helpers."""

from unittest.mock import MagicMock

from django.http import HttpResponse
from django.test import RequestFactory

from larpmanager.cache.config import get_member_config
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.users.accessibility import (
    ACCESSIBILITY_CONFIG,
    ACCESSIBILITY_COOKIE,
    accessibility_from_post,
    get_accessibility_tokens,
    parse_accessibility,
    save_accessibility,
)


class TestAccessibility(BaseTestCase):
    """Accessibility token parsing and persistence."""

    def test_parse_filters_invalid_and_duplicates(self) -> None:
        """Unknown tokens, duplicates and a second value of the same group are dropped."""
        tokens = parse_accessibility('font-dyslexic, evil" onload=x,font-sans,nobg,nobg,size-xl')
        self.assertEqual(tokens, ["font-dyslexic", "nobg", "size-xl"])

    def test_parse_empty(self) -> None:
        """Empty or missing values give no tokens."""
        self.assertEqual(parse_accessibility(None), [])
        self.assertEqual(parse_accessibility(""), [])

    def test_from_post(self) -> None:
        """Panel values are converted to tokens, ignoring invalid choices."""
        post = {"font": "dyslexic", "size": "huge", "color": "cb", "nobg": "1", "links": "", "motion": "on"}
        self.assertEqual(accessibility_from_post(post), ["font-dyslexic", "color-cb", "motion", "nobg"])

    def test_anonymous_uses_cookie(self) -> None:
        """Anonymous users read their preferences from the cookie."""
        request = RequestFactory().get("/")
        request.user = MagicMock(is_authenticated=False, spec=["is_authenticated"])
        request.COOKIES[ACCESSIBILITY_COOKIE] = "size-l,links"
        self.assertEqual(get_accessibility_tokens(request), ["size-l", "links"])

    def test_member_saves_config_and_cookie(self) -> None:
        """Logged members store preferences in both member config and cookie."""
        member = self.get_member()
        request = RequestFactory().post("/")
        request.user = member.user
        response = HttpResponse()

        save_accessibility(request, response, ["color-contrast", "spacing"])

        self.assertEqual(response.cookies[ACCESSIBILITY_COOKIE].value, "color-contrast,spacing")
        self.assertEqual(get_member_config(member.id, ACCESSIBILITY_CONFIG), "color-contrast,spacing")
        self.assertEqual(get_accessibility_tokens(request), ["color-contrast", "spacing"])
