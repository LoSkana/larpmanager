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
import re
import time

import pytest
from playwright.sync_api import expect, sync_playwright

from larpmanager.tests.utils import fill_tinymce, go_to, handle_error, login_orga, page_start


@pytest.mark.django_db
def test_exe_template_copy(live_server):
    with sync_playwright() as p:
        browser, context, page = page_start(p)
        try:
            exe_template_copy(live_server, page)

        except Exception as e:
            handle_error(page, e, "exe_template_copy")

        finally:
            context.close()
            browser.close()


def exe_template_copy(live_server, page):
    login_orga(page, live_server)

    template(live_server, page)

    setup_test(live_server, page)

    px(live_server, page)

    copy(live_server, page)

    campaign(live_server, page)


def template(live_server, page):
    # Activate template
    go_to(page, live_server, "/manage/features/179/on")
    go_to(page, live_server, "/manage/template")
    page.get_by_role("link", name="New").click()
    page.get_by_role("row", name="Name").locator("td").click()
    page.locator("#id_name").fill("template")
    page.get_by_role("checkbox", name="Characters").check()
    page.get_by_role("checkbox", name="Copy").check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Add").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("base role")
    page.locator("#id_name").press("Tab")
    page.get_by_role("searchbox").fill("user")
    page.get_by_role("option", name="User Test - user@test.it").click()
    page.locator("#id_Appearance div").filter(has_text="Texts").click()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("gridcell", name="Configuration").get_by_role("link").click()
    page.get_by_role("link", name="Gallery ").click()
    page.locator("#id_gallery_hide_signup").check()
    page.get_by_role("button", name="Confirm").click()
    # create new event from template
    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("from template")
    page.locator("#id_name").press("Tab")
    page.locator("#slug").fill("fromtemplate")
    page.get_by_label("", exact=True).click()
    page.get_by_role("searchbox").fill("tem")
    page.get_by_role("option", name="template").click()
    page.get_by_role("button", name="Confirm").click()
    # check roles
    go_to(page, live_server, "/fromtemplate/1/manage/roles/")
    expect(page.locator('[id="\\35 "]')).to_contain_text("User Test")
    expect(page.locator('[id="\\35 "]')).to_contain_text("Texts")
    # check configuration
    go_to(page, live_server, "/fromtemplate/1/manage/config/")
    page.get_by_role("link", name="Gallery ").click()
    expect(page.locator("#id_gallery_hide_signup")).to_be_checked()
    # check features
    go_to(page, live_server, "/fromtemplate/1/manage/characters")
    expect(page.locator("#header")).to_contain_text("Characters")
    go_to(page, live_server, "/fromtemplate/1/manage/copy")


def setup_test(live_server, page):
    # activate factions
    go_to(page, live_server, "/test/1/manage/features/104/on")
    # activate xp
    go_to(page, live_server, "/test/1/manage/features/118/on")
    # activate characters
    go_to(page, live_server, "/test/1/manage/features/178/on")
    # configure test larp
    go_to(page, live_server, "/test/1/manage/config/")
    page.get_by_role("link", name="Gallery ").click()
    page.locator("#id_gallery_hide_login").check()
    page.get_by_role("button", name="Confirm").click()

    go_to(page, live_server, "/test/1/manage/roles/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("blabla")
    page.locator("#id_name").press("Tab")
    page.get_by_role("searchbox").fill("user")
    page.get_by_role("option", name="User Test - user@test.it").click()
    page.locator("#id_Appearance").get_by_text("Navigation").click()
    page.locator("#id_Writing").get_by_text("Factions").click()
    page.get_by_role("button", name="Confirm").click()


def px(live_server, page):
    # set up xp
    go_to(page, live_server, "/test/1/manage/config/")
    page.get_by_role("link", name=re.compile(r"^Experience points")).click()
    page.locator("#id_px_start").click()
    page.locator("#id_px_start").fill("10")
    page.get_by_role("button", name="Confirm").click()

    go_to(page, live_server, "/test/1/manage/px/ability_types/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("base ability")
    page.get_by_role("button", name="Confirm").click()

    go_to(page, live_server, "/test/1/manage/px/abilities/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("standard")
    page.locator("#id_cost").click()
    page.locator("#id_name").dblclick()
    page.locator("#id_name").fill("sword1")
    page.locator("#id_cost").click()
    page.locator("#id_cost").fill("1")
    frame = page.locator('iframe[title="Rich Text Area"]')
    fill_tinymce(frame, "sdsfdsfds")
    page.get_by_role("button", name="Confirm").click()

    go_to(page, live_server, "/test/1/manage/px/deliveries/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("first live")
    page.locator("#id_name").press("Tab")
    page.locator("#id_amount").fill("2")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="#1 Test Character").click()
    page.get_by_role("button", name="Confirm").click()

    # check px computation
    go_to(page, live_server, "/test/1/manage/characters/")
    page.get_by_role("link", name="XP").click()
    expect(page.locator('[id="\\31 "]')).to_contain_text("12")
    expect(page.locator('[id="\\31 "]')).to_contain_text("12")
    expect(page.locator('[id="\\31 "]')).to_contain_text("0")
    page.get_by_role("link", name="").click()
    row = page.get_by_role("row").filter(has_text="Abilities")
    time.sleep(2)
    row.get_by_role("link", name="Show").click()
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("swo")
    page.get_by_role("option", name="sword1").click()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="XP").click()
    expect(page.locator('[id="\\31 "]')).to_contain_text("11")
    expect(page.locator('[id="\\31 "]')).to_contain_text("12")
    expect(page.locator('[id="\\31 "]')).to_contain_text("1")


def copy(live_server, page):
    # copy event
    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("copy")
    page.locator("#id_name").press("Tab")
    page.locator("#slug").fill("copy")
    page.get_by_role("button", name="Confirm").click()

    go_to(page, live_server, "/copy/1/manage/features/10/on")
    go_to(page, live_server, "/copy/1/manage/copy/")
    page.locator("#select2-id_parent-container").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="Test Larp").click()
    page.get_by_role("button", name="Submit").click()

    go_to(page, live_server, "/copy/1/manage/roles/")
    expect(page.locator('[id="\\39 "]')).to_contain_text("User Test")
    expect(page.locator('[id="\\39 "]')).to_contain_text("Navigation , Factions")
    go_to(page, live_server, "/copy/1/manage/config/")

    page.get_by_role("link", name="Gallery ").click()
    expect(page.locator("#id_gallery_hide_login")).to_be_checked()
    page.get_by_role("link", name=re.compile(r"^Experience points")).click()
    expect(page.locator("#id_px_start")).to_have_value("10")

    go_to(page, live_server, "/copy/1/manage/characters/")
    page.get_by_role("link", name="XP").click()
    expect(page.locator('[id="\\32 "]')).to_contain_text("12")
    expect(page.locator('[id="\\32 "]')).to_contain_text("1")
    expect(page.locator('[id="\\32 "]')).to_contain_text("11")


def campaign(live_server, page):
    # create campaign
    go_to(page, live_server, "/manage/features/79/on")
    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("campaign")
    page.locator("#id_name").press("Tab")
    page.locator("#slug").fill("campaign")
    time.sleep(2)
    page.locator("#select2-id_parent-container").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="Test Larp", exact=True).click()
    page.get_by_role("button", name="Confirm").click()
    go_to(page, live_server, "/campaign/1/manage/characters/")
    page.get_by_role("link", name="XP").click()
    expect(page.locator('[id="\\33 "]')).to_contain_text("12")
    expect(page.locator('[id="\\33 "]')).to_contain_text("1")
    expect(page.locator('[id="\\33 "]')).to_contain_text("11")
