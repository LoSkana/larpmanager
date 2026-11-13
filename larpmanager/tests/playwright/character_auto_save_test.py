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

Verifies that the character form of the player is staged in background as a redis draft
(never touching the real record), and that leaving without confirming the form restores it
on the next visit without ever having created or modified anything in the database.
"""

import re
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
    """Test the background draft auto-save of the player character form."""
    page, live_server, _unused = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/features/character/on")
    go_to(page, live_server, "/test/manage/features/user_character/on")
    logout(page)

    login_user(page, live_server)
    go_to(page, live_server, "/test/register/")
    submit_register(page)

    auto_save_new_character_not_created(page, live_server)
    auto_save_existing_character_restored(page, live_server)


def auto_save(page: Any) -> None:
    """Trigger the auto-save with the keyboard shortcut, and wait for the answer."""
    with page.expect_response(lambda response: response.request.method == "POST") as response_info:
        page.keyboard.press("Control+s")
    assert response_info.value.ok


def auto_save_new_character_not_created(page: Any, live_server: Any) -> None:
    """A not-yet-created character is never saved to the real record, only staged as a draft."""
    go_to(page, live_server, "/test/character/create/")

    page.locator("#id_name").fill("drafted character")
    auto_save(page)

    # the draft never creates the character: the page stays on the creation URL
    expect(page).to_have_url(re.compile(r".*/character/create/$"))

    # leaving without confirming the form leaves no trace in the character list
    go_to(page, live_server, "/test/character/list/")
    expect(page.locator("body")).not_to_contain_text("drafted character")

    # reopening the creation form restores the unsaved draft and shows the restore banner
    go_to(page, live_server, "/test/character/create/")
    expect(page.locator(".auto-save-draft-banner")).to_be_visible()
    expect(page.locator("#id_name")).to_have_value("drafted character")

    # dismissing the banner does not touch the field values
    page.locator(".auto-save-draft-dismiss").click()
    expect(page.locator(".auto-save-draft-banner")).to_have_count(0)
    expect(page.locator("#id_name")).to_have_value("drafted character")

    # the draft was consumed on that reload: a further reload shows nothing to restore
    page.reload()
    expect(page.locator(".auto-save-draft-banner")).to_have_count(0)
    expect(page.locator("#id_name")).to_have_value("")

    # confirming the form for real is the only way to actually create the character
    page.locator("#id_name").fill("confirmed character")
    page.locator("#form_submit").click()
    # a real submit redirects to the character detail page
    page.wait_for_url(re.compile(r".*/character/[^/]+/$"))

    go_to(page, live_server, "/test/character/list/")
    expect(page.locator("body")).to_contain_text("confirmed character")
    expect(page.locator("body")).not_to_contain_text("drafted character")


def auto_save_existing_character_restored(page: Any, live_server: Any) -> None:
    """An accidental edit on an existing character is never persisted unless explicitly confirmed."""
    go_to(page, live_server, "/test/character/list/")
    page.locator("#characters tbody tr", has_text="confirmed character").locator("a").first.click()

    page.locator("#id_name").fill("accidentally renamed")
    auto_save(page)

    # leaving without confirming leaves the real record untouched
    go_to(page, live_server, "/test/character/list/")
    expect(page.locator("body")).to_contain_text("confirmed character")
    expect(page.locator("body")).not_to_contain_text("accidentally renamed")

    # reopening the form restores the unsaved draft
    page.locator("#characters tbody tr", has_text="confirmed character").locator("a").first.click()
    expect(page.locator(".auto-save-draft-banner")).to_be_visible()
    expect(page.locator("#id_name")).to_have_value("accidentally renamed")

    # discarding the restored value and reloading again shows no draft (it was consumed already)
    page.reload()
    expect(page.locator(".auto-save-draft-banner")).to_have_count(0)
    expect(page.locator("#id_name")).to_have_value("confirmed character")
