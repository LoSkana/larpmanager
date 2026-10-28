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

"""
Test: Organizer edit of participant casting preferences.
Verifies the edit icon is gated by the casting_orga_edit config, that preferences
saved from the popup show up in the organizer grid and in the participant casting page.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    expect_normalized,
    get_modal_iframe,
    go_to,
    login_orga,
    submit_confirm,
    submit_register,
)

pytestmark = pytest.mark.e2e


def test_orga_casting_edit(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # activate characters and casting
    go_to(page, live_server, "/test/manage/features/character/on")
    go_to(page, live_server, "/test/manage/features/casting/on")

    # sign up, without sending preferences
    go_to(page, live_server, "/test/register")
    submit_register(page)

    # edit icon not available while config is disabled
    go_to(page, live_server, "/test/manage/casting")
    expect_normalized(page, page.locator("#didnt_choose"), "Admin Test")
    expect(page.locator(".casting-edit-pref")).to_have_count(0)

    # enable organizer edit
    go_to(page, live_server, "/test/manage/config")
    page.locator("#main_form").get_by_role("link", name=re.compile(r"^Casting")).click()
    page.locator("#id_casting_min").fill("2")
    page.locator("#id_casting_orga_edit").check()
    submit_confirm(page)

    # fill preferences from the popup, below the participant minimum
    go_to(page, live_server, "/test/manage/casting")
    page.locator("#didnt_choose .casting-edit-pref").first.click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#char-list .char-card").filter(has_text="Test Character").click()
    expect_normalized(page, edit_iframe.locator("#pref-list"), "Test Character")
    edit_iframe.get_by_role("button", name="Submit").click()
    page.locator("#lm-modal").wait_for(state="hidden")

    # participant now appears in the grid with the preference
    expect(page.locator("#didnt_choose")).not_to_contain_text("Admin Test")
    expect_normalized(page, page.locator("#main_grid"), "Admin Test")
    expect(page.locator("#main_grid .casting-edit-pref")).to_have_count(1)

    # participant sees the preference saved by the organizer
    go_to(page, live_server, "/test/casting")
    expect_normalized(page, page.locator("#pref-list"), "Test Character")
