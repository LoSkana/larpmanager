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

"""Test: auto-save of the player profile form.

An accidental edit is staged in redis and restored (with a dismissable banner) only
when the profile page is reopened; it never touches the real member record unless the
player explicitly confirms the form.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_user

pytestmark = pytest.mark.e2e


def _auto_save(page: Any) -> None:
    """Trigger the auto-save with the keyboard shortcut, and wait for the answer."""
    with page.expect_response(lambda response: response.request.method == "POST") as response_info:
        page.keyboard.press("Control+s")
    assert response_info.value.ok


def test_profile_auto_save(pw_page: Any) -> None:
    page, live_server, _unused = pw_page

    login_user(page, live_server)
    go_to(page, live_server, "/profile")

    original_name = page.locator("#id_name").input_value()

    page.locator("#id_name").fill("drafted name")
    _auto_save(page)

    # reopening the page restores the unsaved draft, with the dismiss banner shown
    go_to(page, live_server, "/profile")
    expect(page.locator(".auto-save-draft-banner")).to_be_visible()
    expect(page.locator("#id_name")).to_have_value("drafted name")

    # the draft is consumed on that reload: a further reload proves the real record
    # was never touched (nothing left to restore, and the field holds the original value)
    page.reload()
    expect(page.locator(".auto-save-draft-banner")).to_have_count(0)
    expect(page.locator("#id_name")).to_have_value(original_name)

    # a real confirmed save is exercised in exe_profile_test.py / user_profile_fields_test.py
