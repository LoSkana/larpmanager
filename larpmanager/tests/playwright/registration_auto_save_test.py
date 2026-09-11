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

"""Test: auto-save of the registration form.

An accidental edit on a not-yet-confirmed registration is staged in redis and restored
(with a dismissable banner) only when the registration page is reopened; it never touches
the real record unless the player explicitly confirms the form.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import get_modal_iframe, go_to, login_orga, login_user, logout, save_modal

pytestmark = pytest.mark.e2e


def _auto_save(page: Any) -> None:
    """Trigger the auto-save with the keyboard shortcut, and wait for the answer."""
    with page.expect_response(lambda response: response.request.method == "POST") as response_info:
        page.keyboard.press("Control+s")
    assert response_info.value.ok


def test_registration_auto_save(pw_page: Any) -> None:
    page, live_server, _unused = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/form/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("dietary notes")
    save_modal(page, edit_iframe)
    logout(page)

    login_user(page, live_server)
    go_to(page, live_server, "/test/register/")

    ticket = page.locator('input[name="ticket"]').first
    ticket.check(force=True)
    page.get_by_role("textbox", name="dietary notes").fill("drafted note")
    _auto_save(page)

    # leaving without confirming and coming back restores the unsaved draft
    go_to(page, live_server, "/test/register/")
    expect(page.locator(".auto-save-draft-banner")).to_be_visible()
    expect(page.get_by_role("textbox", name="dietary notes")).to_have_value("drafted note")

    # the draft is consumed on that reload: a further reload proves the real record
    # was never touched (nothing left to restore, and the field is empty again)
    page.reload()
    expect(page.locator(".auto-save-draft-banner")).to_have_count(0)
    expect(page.get_by_role("textbox", name="dietary notes")).to_have_value("")

    # dismissing the banner just hides it, it does not discard the restored values
    ticket = page.locator('input[name="ticket"]').first
    ticket.check(force=True)
    page.get_by_role("textbox", name="dietary notes").fill("drafted again")
    _auto_save(page)
    go_to(page, live_server, "/test/register/")
    expect(page.locator(".auto-save-draft-banner")).to_be_visible()
    page.locator(".auto-save-draft-dismiss").click()
    expect(page.locator(".auto-save-draft-banner")).to_have_count(0)
    expect(page.get_by_role("textbox", name="dietary notes")).to_have_value("drafted again")
