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
import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    fill_tinymce,
    go_to,
    go_to_check,
    login_orga,
    logout,
)

pytestmark = pytest.mark.e2e


def test_manual_excel_save_external(pw_page):
    page, server, context = pw_page

    login_orga(page, server)

    # prepare
    page.get_by_role("link", name="").click()
    page.get_by_role("link", name=" Test Larp").click()
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.locator("#id_mod_1_0").check()
    page.get_by_role("button", name="Confirm").click()

    # change name
    page.get_by_role("cell", name="#1 Test Character").dblclick()
    page.locator("#id_name").click()
    page.locator("#id_name").press("End")
    page.locator("#id_name").fill("Test Character2")
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator("#one")).to_contain_text("Test Character2 Test Teaser Test Text")

    # change teaser
    page.get_by_role("cell", name="Test Teaser").dblclick()
    page.locator('iframe[title="Rich Text Area"]').content_frame.locator("html").click()
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_text("Test Teaser").click()
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_label("Rich Text Area").fill("Test Teaser + 2")
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_label("Rich Text Area").press("ControlOrMeta+s")
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator("#one")).to_contain_text("Test Character2 Test Teaser + 2 Test Text")

    # change text
    page.get_by_role("cell", name="Test Text").dblclick()
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_text("Test Text").click()
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_label("Rich Text Area").fill("Test Text ff")
    page.get_by_role("button", name="Confirm").click()

    # check by reload
    page.get_by_role("link", name="Characters").click()
    expect(page.locator("#one")).to_contain_text("#1 Test Character2 Test Teaser + 2 Test Text ff")

    # add new
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Another")

    # test char finder
    fill_tinymce(page, "id_teaser", "good friends with ")
    frame_locator = page.frame_locator("iframe#id_teaser_ifr")
    editor = frame_locator.locator("body#tinymce")
    editor.press("#")
    page.get_by_role("searchbox").fill("tes")
    page.locator(".select2-results__option").first.click()

    # check
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator("#one")).to_contain_text(
        "#1 Test Character2 Test Teaser + 2 Test Text ff #2 Another good friends with #1"
    )

    excel(page, server)

    external(page, server)

    working_ticket(page, server, context)


def excel(page, live_server):
    # test char finder on excel edit
    page.get_by_role("cell", name="Test Text ff").dblclick()
    frame = page.locator('iframe[title="Rich Text Area"]').content_frame
    frame.get_by_label("Rich Text Area").fill("Test Text ff kinda hate ")
    frame.get_by_label("Rich Text Area").press("#")
    page.get_by_role("searchbox").fill("an")
    page.locator(".select2-results__option").first.click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Confirm").click()

    # check by reload
    page.get_by_role("link", name="Characters").click()
    expect(page.locator("#one")).to_contain_text(
        "#1 Test Character2 Test Teaser + 2 Test Text ff kinda hate #2 #2 Another good friends with #1"
    )

    # test manual save
    page.locator('[id="\\32 "]').get_by_role("link", name="").click()
    fill_tinymce(page, "id_text", "ciaoooo")
    frame_locator = page.frame_locator("iframe#id_text_ifr")
    editor = frame_locator.locator("body#tinymce")
    editor.press("ControlOrMeta+s")
    page.wait_for_timeout(2000)

    # check by reload
    page.get_by_role("link", name="Characters").click()
    expect(page.locator("#one")).to_contain_text(
        "#1 Test Character2 Test Teaser + 2 Test Text ff kinda hate #2 #2 Another good friends with #1 ciaoooo"
    )

    # check in page
    page.locator('[id="\\32 "]').get_by_role("link", name="").click()
    page.locator('a.my_toggle[tog="f_id_text"]').click()
    expect(page.locator("#one")).to_contain_text("Text (*) Show <p>ciaoooo</p>")


def external(page, live_server):
    # enable external access
    page.get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name="Writing ").click()
    page.locator("#id_writing_external_access").check()
    page.get_by_role("button", name="Confirm").click()

    # get url
    page.get_by_role("link", name="Characters").click()
    url = page.locator('[id="\\32 "]').get_by_role("link", name="").get_attribute("href")

    # logout, then go to the page
    logout(page)
    go_to_check(page, live_server + url)
    expect(page.locator("#one")).to_contain_text(
        "Presentation good friends with Test Character2Test Character2Test Teaser + 2 (...) Text ciaoooo"
    )


def working_ticket(page, server, context):
    login_orga(page, server)

    go_to(page, server, "/test/1/manage")
    page.get_by_role("link", name="Characters").click()
    page.locator('[id="\\31 "]').get_by_role("link", name="").click(button="right")
    page1 = context.new_page()
    page1.goto(server + "/test/1/manage/characters/edit/1/")
    page.locator('[id="\\31 "]').get_by_role("link", name="").click()
    page.wait_for_timeout(2000)
    expect(page.locator("#test-larp")).to_contain_text(
        "Warning! Other users are editing this item. You cannot work on it at the same time: the work of one of you would be lost."
    )
