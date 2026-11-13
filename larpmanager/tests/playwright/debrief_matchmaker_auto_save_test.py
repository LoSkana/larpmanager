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

"""Test: auto-save of the debrief and matchmaker forms.

Both reuse the same staging-draft machinery as the character form: an accidental edit
left on the page is staged in redis and never touches the real registration record
unless the player explicitly confirms the form.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    get_modal_iframe,
    go_to,
    login_orga,
    login_user,
    logout,
    save_modal,
    submit_register,
)

pytestmark = pytest.mark.e2e


def test_debrief_matchmaker_auto_save(pw_page: Any) -> None:
    page, live_server, _unused = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/features/debrief/on")
    go_to(page, live_server, "/test/manage/features/matchmaker/on")
    _create_short_text_question(page, live_server, "/test/manage/form/debrief/", "debrief notes")
    _create_short_text_question(page, live_server, "/test/manage/form/matchmaker/", "matchmaker notes")
    logout(page)

    login_user(page, live_server)
    go_to(page, live_server, "/test/register/")
    submit_register(page)

    _check_auto_save_flow(page, live_server, "/test/debrief/", "debrief notes", "#debrief_go", "Answers saved")
    _check_auto_save_flow(page, live_server, "/test/matchmaker/", "matchmaker notes", "#matchmaker_go", "Answers saved")


def _create_short_text_question(page: Any, live_server: Any, form_url: str, label: str) -> None:
    """Create a single short-text question on the given player-facing form."""
    go_to(page, live_server, form_url)
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill(label)
    save_modal(page, edit_iframe)


def _auto_save(page: Any) -> None:
    """Trigger the auto-save with the keyboard shortcut, and wait for the answer."""
    with page.expect_response(lambda response: response.request.method == "POST") as response_info:
        page.keyboard.press("Control+s")
    assert response_info.value.ok


def _check_auto_save_flow(
    page: Any, live_server: Any, form_path: str, label: str, submit_id: str, success_text: str
) -> None:
    go_to(page, live_server, form_path)
    page.get_by_role("textbox", name=label).fill("drafted answer")
    _auto_save(page)

    # leaving without confirming and coming back restores the unsaved draft
    go_to(page, live_server, form_path)
    expect(page.locator(".auto-save-draft-banner")).to_be_visible()
    expect(page.get_by_role("textbox", name=label)).to_have_value("drafted answer")

    # the draft is consumed on that reload: a further reload proves the real record
    # was never touched (nothing left to restore, and the field is empty again)
    page.reload()
    expect(page.locator(".auto-save-draft-banner")).to_have_count(0)
    expect(page.get_by_role("textbox", name=label)).to_have_value("")

    # confirming the form for real is the only way to persist the answer
    page.get_by_role("textbox", name=label).fill("confirmed answer")
    page.locator(submit_id).click()
    expect(page.locator(".jq-toast-single")).to_contain_text(success_text)

    go_to(page, live_server, form_path)
    expect(page.get_by_role("textbox", name=label)).to_have_value("confirmed answer")
