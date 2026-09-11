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

"""Test: auto-save of the guild edit form.

An accidental edit is staged in redis and restored (with a dismissable banner) only
when the guild edit page is reopened; it never touches the real record unless the
guild admin explicitly confirms the form.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    fill_tinymce,
    get_modal_iframe,
    go_to,
    login_orga,
    login_user,
    logout,
    save_modal,
    submit_register,
)

pytestmark = pytest.mark.e2e


def _auto_save(page: Any) -> None:
    """Trigger the auto-save with the keyboard shortcut, and wait for the answer."""
    with page.expect_response(lambda response: response.request.method == "POST") as response_info:
        page.keyboard.press("Control+s")
    assert response_info.value.ok


def test_guild_auto_save(pw_page: Any) -> None:
    page, live_server, _unused = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/features/user_character/on")
    go_to(page, live_server, "/test/manage/features/guild/on")
    go_to(page, live_server, "/test/manage/features/character/on")
    go_to(page, live_server, "/test/manage/characters")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Guild Founder")
    edit_iframe.locator("#select2-id_player-container").click()
    edit_iframe.get_by_role("searchbox").fill("user")
    edit_iframe.get_by_role("option", name="User Test - user@test.it").click()
    save_modal(page, edit_iframe)
    logout(page)

    login_user(page, live_server)
    go_to(page, live_server, "/test/register")
    submit_register(page)

    go_to(page, live_server, "/test/guilds/new/")
    page.locator("#founder_character").select_option(label="Guild Founder")
    page.locator("#id_name").fill("The Silver Hand")
    fill_tinymce(page, "id_teaser", "original teaser")
    fill_tinymce(page, "id_text", "original text")
    page.locator("#form_submit").click()
    page.wait_for_url(re.compile(r".*/guilds/u\d+/?$"))

    go_to(page, live_server, "/test/guilds/")
    page.get_by_role("link", name="The Silver Hand").click()
    page.get_by_role("link", name="Edit guild").click()

    page.locator("#id_name").fill("drafted name")
    _auto_save(page)

    # leaving without confirming and coming back restores the unsaved draft
    edit_url = page.url
    go_to(page, live_server, "/test/guilds/")
    page.goto(edit_url)
    expect(page.locator(".auto-save-draft-banner")).to_be_visible()
    expect(page.locator("#id_name")).to_have_value("drafted name")

    # the draft is consumed on that reload: a further reload proves the real record
    # was never touched (nothing left to restore, and the field holds the original name)
    page.reload()
    expect(page.locator(".auto-save-draft-banner")).to_have_count(0)
    expect(page.locator("#id_name")).to_have_value("The Silver Hand")

    # confirming the form for real is the only way to persist the change
    page.locator("#id_name").fill("confirmed name")
    page.locator("#form_submit").click()

    go_to(page, live_server, "/test/guilds/")
    expect(page.locator("body")).to_contain_text("confirmed name")
    expect(page.locator("body")).not_to_contain_text("drafted name")
