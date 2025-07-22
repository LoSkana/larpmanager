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

import pytest
from playwright.async_api import async_playwright, expect

from larpmanager.tests.utils import fill_tinymce, go_to, handle_error, login_orga, page_start


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_user_character_form_editor(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await user_character_form_editor(live_server, page)

        except Exception as e:
            await handle_error(page, e, "user_character_form_editor")

        finally:
            await context.close()
            await browser.close()


async def user_character_form_editor(live_server, page):
    await login_orga(page, live_server)

    await prepare(page, live_server)

    await field_single(page, live_server)

    await field_multiple(page, live_server)

    await field_text(page, live_server)

    await character(page, live_server)


async def prepare(page, live_server):
    # Activate characters
    await go_to(page, live_server, "/test/1/manage/features/178/on")

    # Activate player editor
    await go_to(page, live_server, "/test/1/manage/features/120/on")

    await go_to(page, live_server, "/test/1/manage/config")
    await page.get_by_role("link", name="Player editor ").click()
    await page.locator("#id_user_character_approval").check()
    await page.get_by_role("cell", name="Maximum number of characters").click()
    await page.locator("#id_user_character_max").fill("1")
    await page.get_by_role("link", name="Character form ").click()
    await page.locator("#id_character_form_wri_que_max").check()
    await page.locator("#id_character_form_wri_que_dependents").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/manage/characters/form")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("Name")
    await expect(page.locator('[id="\\32 "]')).to_contain_text("Presentation")
    await expect(page.locator('[id="\\33 "]')).to_contain_text("Sheet")


async def field_single(page, live_server):
    # add single
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_display").click()
    await page.locator("#id_display").fill("single")
    await page.locator("#id_display").press("Tab")
    await page.locator("#id_description").fill("sssssingle")

    await page.get_by_role("link", name="New").click()
    await page.locator("#id_display").click()
    await page.locator("#id_display").fill("ff")
    await page.locator("#id_max_available").click()
    await page.locator("#id_max_available").fill("3")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await page.get_by_role("link", name="New").click()
    await page.locator("#id_display").click()
    await page.locator("#id_display").fill("rrrr")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await page.get_by_role("link", name="New").click()
    await page.locator("#id_display").click()
    await page.locator("#id_display").fill("wwww")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await page.get_by_role("button", name="Confirm", exact=True).click()


async def field_multiple(page, live_server):
    # Add multiple
    await page.get_by_role("link", name="New").click()
    await page.get_by_text("Question type").click()
    await page.locator("#id_typ").select_option("m")
    await page.locator("#id_display").click()
    await page.locator("#id_display").fill("rrrrrr")
    await page.locator("#id_max_length").click()
    await page.locator("#id_max_length").fill("1")

    await page.get_by_role("link", name="New").click()
    await page.locator("#id_display").click()
    await page.locator("#id_display").fill("q1")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await page.get_by_role("link", name="New").click()
    await page.locator("#id_display").click()
    await page.locator("#id_display").fill("q2")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await page.get_by_role("link", name="New").click()
    await page.locator("#id_display").click()
    await page.locator("#id_display").fill("q3")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await page.get_by_role("link", name="New").click()
    await page.locator("#id_display").click()
    await page.locator("#id_display").fill("14")
    await page.locator("#id_max_available").click()
    await page.locator("#id_max_available").fill("3")
    await page.get_by_role("row", name="Prerequisites").get_by_role("searchbox").fill("ww")
    await page.get_by_role("option", name="Test Larp - single wwww").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await page.get_by_role("button", name="Confirm", exact=True).click()


async def field_text(page, live_server):
    # Add text
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("t")
    await page.get_by_role("cell", name="Question name (keep it short)").click()
    await page.locator("#id_display").fill("text")
    await page.locator("#id_max_length").click()
    await page.locator("#id_max_length").fill("10")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # Add paragraph
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("p")
    await page.locator("#id_display").click()
    await page.locator("#id_display").fill("rrr")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # Create new character
    await go_to(page, live_server, "/test/1/manage/characters")
    await page.wait_for_timeout(2000)
    await page.get_by_role("link", name="New").click()
    await asyncio.sleep(1)
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("provaaaa")

    await page.get_by_role("row", name="Presentation (*) Show").get_by_role("link").click()
    await fill_tinymce(page, "id_teaser_ifr", "adsdsadsa")

    await page.get_by_role("row", name="Text (*) Show").get_by_role("link").click()
    await fill_tinymce(page, "id_text_ifr", "rrrr")

    await asyncio.sleep(1)
    await page.locator("#id_q4").select_option("3")
    await page.locator("#id_q4").select_option("1")
    await page.get_by_role("checkbox", name="q2").check()
    await page.locator("#id_q6").click()
    await page.locator("#id_q6").fill("sad")
    await page.locator("#id_q7").click()
    await page.locator("#id_q7").fill("sadsadas")
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def character(page, live_server):
    # signup, create char
    await go_to(page, live_server, "/test/1/register")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await expect(page.locator("#one")).to_contain_text("Access character creation!")
    await page.get_by_role("link", name="Access character creation!").click()
    await asyncio.sleep(1)
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("my character")

    await page.get_by_role("row", name="Presentation (*) Show").get_by_role("link").click()
    await fill_tinymce(page, "id_teaser_ifr", "so coool")

    await page.get_by_role("row", name="Text (*) Show").get_by_role("link").click()
    await fill_tinymce(page, "id_text_ifr", "so braaaave")

    await page.locator("#id_q4").select_option("1")
    await page.locator("#id_q4").select_option("3")
    await page.get_by_role("checkbox", name="- (Available 3)").check()
    await page.locator("#id_q6").click()
    await page.locator("#id_q6").fill("wow")
    await page.locator("#id_q7").click()
    await page.locator("#id_q7").fill("asdsadsa")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # confirm char
    await expect(page.locator("#one")).to_contain_text("my character (Creation)")
    await page.get_by_role("link", name="my character (Creation)").click()
    await page.get_by_role("link", name="Change").click()
    await page.get_by_role("cell", name="Click here to confirm that").click()
    await page.get_by_text("Click here to confirm that").click()
    await page.locator("#id_propose").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # check char
    await expect(page.locator("#one")).to_contain_text("my character (Proposed)")

    # approve char
    await go_to(page, live_server, "/test/1/manage/characters")
    await page.locator('[id="\\33 "]').get_by_role("gridcell", name="").click()
    await page.locator("#id_status").select_option("a")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/register")
    await page.locator("#one").get_by_role("link", name="Characters").click()
    await expect(page.locator("#one")).to_contain_text("my character")

    await go_to(page, live_server, "/test/1")
    await expect(page.locator("#one")).to_contain_text("my character")
