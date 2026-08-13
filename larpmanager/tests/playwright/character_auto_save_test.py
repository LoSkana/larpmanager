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

"""Test: auto-save of the player character form.

Verifies that the character form of the player is saved in background, both when creating a
new character and when editing an existing one, without confirming the form.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    go_to,
    login_orga,
    login_user,
    logout,
    submit_register,
)

pytestmark = pytest.mark.e2e


def test_character_auto_save(pw_page: Any) -> None:
    """Test the background auto-save of the player character form."""
    page, live_server, _unused = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/features/character/on")
    go_to(page, live_server, "/test/manage/features/user_character/on")
    logout(page)

    login_user(page, live_server)
    go_to(page, live_server, "/test/register/")
    submit_register(page)

    auto_save_new_character(page, live_server)
    auto_save_existing_character(page, live_server)
    auto_save_two_pages_open(page)


def auto_save(page: Any) -> None:
    """Trigger the auto-save with the keyboard shortcut, and wait for the answer."""
    with page.expect_response(lambda response: response.request.method == "POST") as response_info:
        page.keyboard.press("Control+s")
    assert response_info.value.ok


def auto_save_new_character(page: Any, live_server: Any) -> None:
    """A new character is created by the auto-save, once it has a name."""
    go_to(page, live_server, "/test/character/create/")

    page.locator("#id_name").fill("auto saved character")
    auto_save(page)

    # the creation page now points to the character just created
    page.wait_for_url("**/change/")
    page.reload()
    expect(page.locator("#id_name")).to_have_value("auto saved character")


def auto_save_existing_character(page: Any, live_server: Any) -> None:
    """The changes of an existing character are stored without confirming the form."""
    page.locator("#id_name").fill("renamed by auto save")
    auto_save(page)

    page.reload()
    expect(page.locator("#id_name")).to_have_value("renamed by auto save")

    # the character exists without the form ever being confirmed
    go_to(page, live_server, "/test/character/list/")
    expect(page.locator("body")).to_contain_text("renamed by auto save")


def auto_save_two_pages_open(page: Any) -> None:
    """With the same character open in two pages, the second one is refused instead of overwriting."""
    page.go_back()
    edit_url = page.url
    second_page = page.context.new_page()
    second_page.goto(edit_url)

    # the first page saves
    page.locator("#id_name").fill("saved by first page")
    auto_save(page)

    # the second page was loaded before, so its auto-save is refused with a warning
    second_page.locator("#id_name").fill("saved by second page")
    auto_save(second_page)
    expect(second_page.locator(".jq-toast-single")).to_be_visible()

    # confirming the form of the second page does not overwrite either
    second_page.locator("#form_submit").click()
    expect(second_page.locator("body")).to_contain_text("modified in another window")

    page.reload()
    expect(page.locator("#id_name")).to_have_value("saved by first page")
    second_page.close()
