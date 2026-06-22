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
Test: Manual editing, Excel-style editing, external access, and working tickets.
Verifies character editing via modal and Excel-style interface, character finder,
auto-save functionality, external access URLs, and concurrent editing warnings.
"""
import re
from typing import Any

import pytest

from larpmanager.tests.utils import (just_wait,
                                     check_feature,
                                     expect_normalized,
                                     fill_tinymce,
                                     go_to,
                                     go_to_check,
                                     login_orga,
                                     logout,
                                     submit_confirm, submit_inline_edit, wait_for_inline_edit,
                                     get_modal_iframe, save_modal, sidebar, _wait_select2_results,
                                     )

pytestmark = pytest.mark.e2e


def test_manual_excel_save_external(pw_page: Any) -> None:
    page, live_server, context = pw_page

    login_orga(page, live_server)

    # prepare
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Features")
    check_feature(page, "Characters")
    submit_confirm(page)

    # change name
    page.get_by_role("cell", name="Test Character").dblclick()
    panel = wait_for_inline_edit(page)
    panel.locator("#id_name").press("End")
    panel.locator("#id_name").fill("Test Character2")
    submit_inline_edit(page)
    expect_normalized(page, page.locator('[id="u1"]'), "Test Character2 Test Teaser Test Text")

    # change teaser
    page.locator('[id="u1"]').get_by_role("cell").filter(has_text="Test Teaser").dblclick()
    panel = wait_for_inline_edit(page)
    panel.locator("#id_teaser").fill("Test Teaser + 2")
    submit_inline_edit(page)
    expect_normalized(page, page.locator('[id="u1"]'), "Test Character2 Test Teaser + 2 Test Text")

    # change text
    page.locator('[id="u1"]').get_by_role("cell").filter(has_text="Test Text").dblclick()
    panel = wait_for_inline_edit(page)
    panel.locator("#id_text").fill("Test Text ff")
    submit_inline_edit(page)

    # check by reload
    sidebar(page, "Characters")
    expect_normalized(page, page.locator("#one"), "Test Character2 Test Teaser + 2 Test Text ff")

    # add new
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Another")

    # test char finder
    fill_tinymce(edit_iframe, "id_teaser", "good friends with ")
    editor = edit_iframe.locator("#id_teaser")
    editor.press(" ")
    editor.press("#")
    edit_iframe.get_by_role("searchbox").fill("tes")
    _wait_select2_results(edit_iframe)
    edit_iframe.locator(".select2-results__option").first.click()
    just_wait(edit_iframe)
    save_modal(page, edit_iframe)

    expect_normalized(page,
        page.locator("#one"),
        "Test Character2 Test Teaser + 2 Test Text ff Another good friends with #1",
    )

    excel(page, live_server)

    external(page, live_server)

    working_ticket(page, live_server, context)

    working_ticket_event(page, live_server, context)


def excel(page: Any, live_server: Any) -> None:
    # test char finder on excel edit
    page.locator('[id="u1"]').get_by_role("cell").filter(has_text="Test Text ff").dblclick()
    panel = wait_for_inline_edit(page)
    panel.locator("#id_text").fill("Test Text ff kinda hate ")
    panel.locator("#id_text").press("#")
    page.get_by_role("searchbox").fill("an")
    _wait_select2_results(edit_iframe)
    page.locator(".select2-results__option").first.click()
    just_wait(page)
    submit_inline_edit(page)

    # check by reload
    sidebar(page, "Characters")
    expect_normalized(page,
        page.locator("#one"),
        "Test Character2 Test Teaser + 2 Test Text ff kinda hate #2 Another good friends with #1",
    )

    # test manual save
    page.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    fill_tinymce(edit_iframe, "id_text", "ciaoooo")

    page.locator('body').press("ControlOrMeta+s")
    just_wait(page)

    # check by reload
    page.reload()
    expect_normalized(page,
        page.locator("#one"),
        "Test Character2 Test Teaser + 2 Test Text ff kinda hate #2 Another good friends with #1 ciaoooo",
    )

    # check in page
    page.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator('a.my_toggle[tog="f_id_text"]').click()
    expect_normalized(edit_iframe, edit_iframe.locator("#one"), "<p>good friends with </p> #1 <p>ciaoooo</p> ")
    save_modal(page, edit_iframe)

def external(page: Any, live_server: Any) -> None:
    # enable external access
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Characters")).click()
    page.locator("#id_writing_external_access").check()
    submit_confirm(page)

    # get url
    sidebar(page, "Characters")
    url = page.locator('[id="u2"]').locator(".fa-key").locator('..').get_attribute("href")

    # logout, then go to the page
    logout(page)
    go_to_check(page, live_server + url)
    expect_normalized(page,
        page.locator("#one"),
        "Presentation good friends with Test Character2 Text ciaoooo",
    )


def working_ticket(page: Any, server: Any, context: Any) -> None:
    login_orga(page, server)

    go_to(page, server, "/test/manage")
    sidebar(page, "Characters")
    page.locator('[id="u1"]').locator(".fa-edit").click(button="right")
    page1 = context.new_page()
    page1.goto(server + "/test/manage/characters/u1/edit/")
    page.locator('[id="u1"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect_normalized(edit_iframe,
        edit_iframe.locator("#test-larp"),
        "Warning! Other users are editing this item. You cannot work on it at the same time: the work of one of you would be lost.",
    )


def working_ticket_event(page: Any, server: Any, context: Any) -> None:
    login_orga(page, server)

    go_to(page, server, "/test/manage/config")
    page1 = context.new_page()
    page1.goto(server + "/test/manage/config")
    page.wait_for_function(
        "() => document.body.innerText.toLowerCase().includes('warning! other users are editing')",
        timeout=15000,
    )
    expect_normalized(page,
        page.locator("#test-larp"),
        "Warning! Other users are editing this item. You cannot work on it at the same time: the work of one of you would be lost.",
    )
