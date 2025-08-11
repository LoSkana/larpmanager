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
import asyncio
import re

import pytest
from playwright.async_api import async_playwright, expect

from larpmanager.tests.utils import fill_tinymce, go_to, handle_error, login_orga, page_start


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_exe_template_copy(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await exe_template_copy(live_server, page)

        except Exception as e:
            await handle_error(page, e, "exe_template_copy")

        finally:
            await context.close()
            await browser.close()


async def exe_template_copy(live_server, page):
    await login_orga(page, live_server)

    await template(live_server, page)

    await setup_test(live_server, page)

    await px(live_server, page)

    await copy(live_server, page)

    await campaign(live_server, page)


async def template(live_server, page):
    # Activate template
    await go_to(page, live_server, "/manage/features/179/on")
    await go_to(page, live_server, "/manage/template")
    await page.get_by_role("link", name="New").click()
    await page.get_by_role("row", name="Name").locator("td").click()
    await page.locator("#id_name").fill("template")
    await page.locator("input[type='checkbox'][value='178']").check()  # mark character
    await page.locator("div.feature_checkbox", has_text="Copy").locator("input[type='checkbox']").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="Add").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("base role")
    await page.locator("#id_name").press("Tab")
    await page.get_by_role("searchbox").fill("user")
    await page.get_by_role("option", name="User Test - user@test.it").click()
    await page.locator("#id_Appearance_1").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.locator("#one").get_by_role("link", name="Configuration").click()
    await page.get_by_role("link", name="Gallery ").click()
    await page.locator("#id_gallery_hide_signup").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    # create new event from template
    await go_to(page, live_server, "/manage/events")
    await page.get_by_role("link", name="New event").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("from template")
    await page.locator("#id_name").press("Tab")
    await page.locator("#slug").fill("fromtemplate")
    await page.get_by_label("", exact=True).click()
    await page.get_by_role("searchbox").fill("tem")
    await page.get_by_role("option", name="template").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    # check roles
    await go_to(page, live_server, "/fromtemplate/1/manage/roles/")
    await expect(page.locator('[id="\\35 "]')).to_contain_text("User Test")
    await expect(page.locator('[id="\\35 "]')).to_contain_text("Texts")
    # check configuration
    await go_to(page, live_server, "/fromtemplate/1/manage/config/")
    await page.get_by_role("link", name="Gallery ").click()
    await expect(page.locator("#id_gallery_hide_signup")).to_be_checked()
    # check features
    await go_to(page, live_server, "/fromtemplate/1/manage/characters")
    await expect(page.locator("#header")).to_contain_text("Characters")
    await go_to(page, live_server, "/fromtemplate/1/manage/copy")


async def setup_test(live_server, page):
    # activate factions
    await go_to(page, live_server, "/test/1/manage/features/104/on")
    # activate xp
    await go_to(page, live_server, "/test/1/manage/features/118/on")
    # activate characters
    await go_to(page, live_server, "/test/1/manage/features/178/on")
    # configure test larp
    await go_to(page, live_server, "/test/1/manage/config/")
    await page.get_by_role("link", name="Gallery ").click()
    await page.locator("#id_gallery_hide_login").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/manage/roles/")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("blabla")
    await page.locator("#id_name").press("Tab")
    await page.get_by_role("searchbox").fill("user")
    await page.get_by_role("option", name="User Test - user@test.it").click()
    await page.locator("#id_Appearance_2").check()
    await page.locator("#id_Writing_2").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def px(live_server, page):
    # set up xp
    await go_to(page, live_server, "/test/1/manage/config/")
    await page.get_by_role("link", name=re.compile(r"^Experience points\s.+")).click()
    await page.locator("#id_px_start").click()
    await page.locator("#id_px_start").fill("10")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/manage/px/ability_types/")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("base ability")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/manage/px/abilities/")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("standard")
    await page.locator("#id_cost").click()
    await page.locator("#id_name").dblclick()
    await page.locator("#id_name").fill("sword1")
    await page.locator("#id_cost").click()
    await page.locator("#id_cost").fill("1")
    await fill_tinymce(page, "id_descr_ifr", "sdsfdsfds")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/manage/px/deliveries/")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("first live")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_amount").fill("2")
    await page.get_by_role("searchbox").click()
    await page.get_by_role("searchbox").fill("te")
    await page.get_by_role("option", name="#1 Test Character").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # check px computation
    await go_to(page, live_server, "/test/1/manage/characters/")
    await page.get_by_role("link", name="XP").click()
    await expect(page.locator('[id="\\31 "]')).to_contain_text("12")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("12")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("0")
    await page.get_by_role("link", name="").click()
    await page.wait_for_load_state("load")
    await asyncio.sleep(1)
    row = page.get_by_role("row", name="Abilities Show")
    await row.get_by_role("link").click()
    await row.get_by_role("searchbox").click()
    await row.get_by_role("searchbox").fill("swo")
    await asyncio.sleep(5)
    await page.get_by_role("option", name="sword1").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="XP").click()
    await expect(page.locator('[id="\\31 "]')).to_contain_text("11")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("12")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("1")


async def copy(live_server, page):
    # copy event
    await go_to(page, live_server, "/manage/events")
    await page.get_by_role("link", name="New event").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("copy")
    await page.locator("#id_name").press("Tab")
    await page.locator("#slug").fill("copy")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/copy/1/manage/features/10/on")
    await go_to(page, live_server, "/copy/1/manage/copy/")
    await page.locator("#select2-id_parent-container").click()
    await page.get_by_role("searchbox").fill("tes")
    await page.get_by_role("option", name="Test Larp").click()
    await page.get_by_role("button", name="Submit").click()

    await go_to(page, live_server, "/copy/1/manage/roles/")
    await expect(page.locator('[id="\\39 "]')).to_contain_text("User Test")
    await expect(page.locator('[id="\\39 "]')).to_contain_text("Appearance (Navigation), Writing (Factions) ")
    await go_to(page, live_server, "/copy/1/manage/config/")

    await page.get_by_role("link", name="Gallery ").click()
    await expect(page.locator("#id_gallery_hide_login")).to_be_checked()
    await page.get_by_role("link", name=re.compile(r"^Experience points\s.+")).click()
    await expect(page.locator("#id_px_start")).to_have_value("10")

    await go_to(page, live_server, "/copy/1/manage/characters/")
    await page.get_by_role("link", name="XP").click()
    await expect(page.locator('[id="\\32 "]')).to_contain_text("12")
    await expect(page.locator('[id="\\32 "]')).to_contain_text("1")
    await expect(page.locator('[id="\\32 "]')).to_contain_text("11")


async def campaign(live_server, page):
    # create campaign
    await go_to(page, live_server, "/manage/features/79/on")
    await go_to(page, live_server, "/manage/events")
    await page.get_by_role("link", name="New event").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("campaign")
    await page.locator("#id_name").press("Tab")
    await page.locator("#slug").fill("campaign")
    await asyncio.sleep(2)
    await page.locator("#select2-id_parent-container").click()
    await page.get_by_role("searchbox").fill("tes")
    await page.get_by_role("option", name="Test Larp", exact=True).click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await go_to(page, live_server, "/campaign/1/manage/characters/")
    await page.get_by_role("link", name="XP").click()
    await expect(page.locator('[id="\\31 "]')).to_contain_text("12")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("1")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("11")
