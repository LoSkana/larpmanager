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

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import check_feature, go_to, login_orga, submit_confirm

pytestmark = pytest.mark.e2e


def test_exe_template_copy(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    template(live_server, page)

    setup(live_server, page)

    copy(live_server, page)

    campaign(live_server, page)


def template(live_server, page):
    # Activate template
    go_to(page, live_server, "/manage/features/template/on")
    go_to(page, live_server, "/manage/template")
    page.get_by_role("link", name="New").click()
    page.get_by_role("row", name="Name").locator("td").click()
    page.locator("#id_name").fill("template")
    page.get_by_role("checkbox", name="Characters").check()
    page.locator("div.feature_checkbox", has_text="Copy").locator("input[type='checkbox']").check()
    submit_confirm(page)
    page.get_by_role("link", name="Add").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("base role")
    page.locator("#id_name").press("Tab")
    page.get_by_role("searchbox").fill("user")
    page.get_by_role("option", name="User Test - user@test.it").click()
    check_feature(page, "Texts")
    submit_confirm(page)
    page.locator("#one").get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name="Gallery ").click()
    page.locator("#id_gallery_hide_signup").check()
    submit_confirm(page)
    # create new event from template
    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New event").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("from template")
    page.locator("#id_name").press("Tab")
    page.locator("#slug").fill("fromtemplate")
    # the template should be auto-selected
    submit_confirm(page)

    # check roles
    go_to(page, live_server, "/fromtemplate/1/manage/roles/")
    expect(page.locator('[id="\\36 "]')).to_contain_text("User Test")
    expect(page.locator('[id="\\36 "]')).to_contain_text("Texts")
    # check configuration
    go_to(page, live_server, "/fromtemplate/1/manage/config/")
    page.get_by_role("link", name="Gallery ").click()
    expect(page.locator("#id_gallery_hide_signup")).to_be_checked()
    # check features
    go_to(page, live_server, "/fromtemplate/1/manage/characters")
    expect(page.locator("#header")).to_contain_text("Characters")
    go_to(page, live_server, "/fromtemplate/1/manage/copy")


def setup(live_server, page):
    # activate factions
    go_to(page, live_server, "/test/1/manage/features/faction/on")
    # activate xp
    go_to(page, live_server, "/test/1/manage/features/px/on")
    # activate characters
    go_to(page, live_server, "/test/1/manage/features/character/on")
    # configure test larp
    go_to(page, live_server, "/test/manage/config/")
    page.get_by_role("link", name="Gallery ").click()
    page.locator("#id_gallery_hide_login").check()
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/roles/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("blabla")
    page.locator("#id_name").press("Tab")
    page.get_by_role("searchbox").fill("user")
    page.get_by_role("option", name="User Test - user@test.it").click()
    check_feature(page, "Navigation")
    check_feature(page, "Factions")
    submit_confirm(page)


def copy(live_server, page):
    # copy event
    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New event").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("copy")
    page.locator("#id_name").press("Tab")
    page.locator("#slug").fill("copy")
    submit_confirm(page)

    go_to(page, live_server, "/copy/1/manage/features/copy/on")
    go_to(page, live_server, "/copy/1/manage/copy/")
    page.locator("#select2-id_parent-container").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="Test Larp").click()
    page.get_by_role("button", name="Submit").click()

    go_to(page, live_server, "/copy/1/manage/roles/")
    row = page.locator('tr[id="12"]')
    expect(row).to_contain_text("User Test")
    expect(row).to_contain_text("Appearance (Navigation), Writing (Factions) ")
    go_to(page, live_server, "/copy/1/manage/config/")

    page.get_by_role("link", name="Gallery ").click()
    expect(page.locator("#id_gallery_hide_login")).to_be_checked()
    page.get_by_role("link", name=re.compile(r"^Experience points\s.+")).click()
    expect(page.locator("#id_px_start")).to_have_value("10")

    go_to(page, live_server, "/copy/1/manage/characters/")
    page.get_by_role("link", name="XP").click()
    expect(page.locator('[id="\\32 "]')).to_contain_text("12")
    expect(page.locator('[id="\\32 "]')).to_contain_text("1")
    expect(page.locator('[id="\\32 "]')).to_contain_text("11")


def campaign(live_server, page):
    # create campaign
    go_to(page, live_server, "/manage/features/campaign/on")
    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New event").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("campaign")
    page.locator("#id_name").press("Tab")
    page.locator("#slug").fill("campaign")
    page.wait_for_timeout(2000)
    page.locator("#select2-id_parent-container").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="Test Larp", exact=True).click()
    submit_confirm(page)
    go_to(page, live_server, "/campaign/1/manage/characters/")
    page.get_by_role("link", name="XP").click()
    expect(page.locator('[id="\\31 "]')).to_contain_text("12")
    expect(page.locator('[id="\\31 "]')).to_contain_text("1")
    expect(page.locator('[id="\\31 "]')).to_contain_text("11")
