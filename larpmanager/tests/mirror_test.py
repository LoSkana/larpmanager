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
from playwright.async_api import async_playwright, expect

from larpmanager.tests.utils import go_to, handle_error, login_orga, page_start, submit


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_orga_mirror(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await orga_mirror(live_server, page)

        except Exception as e:
            await handle_error(page, e, "orga_mirror")

        finally:
            await context.close()
            await browser.close()


async def orga_mirror(live_server, page):
    await login_orga(page, live_server)

    # activate characters
    await go_to(page, live_server, "/test/1/manage/features/178/on")

    # show chars
    await go_to(page, live_server, "/test/1/manage/config")
    await page.get_by_role("link", name=re.compile(r"^Writing")).click()
    await page.locator("#id_writing_field_visibility").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/manage/run")
    await page.locator("#id_show_character_0").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # check gallery
    await go_to(page, live_server, "/test/1/")
    await expect(page.locator("#one")).to_contain_text("Test Character")

    # activate casting
    await go_to(page, live_server, "/test/1/manage/features/27/on")

    # activate mirror
    await go_to(page, live_server, "/test/1/manage/config")
    await page.get_by_role("link", name=re.compile(r"^Casting\s.+")).click()
    await page.locator("#id_casting_mirror").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # create mirror
    await go_to(page, live_server, "/test/1/manage/characters/")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("Mirror")
    await page.locator("#id_mirror").select_option("1")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # check gallery
    await go_to(page, live_server, "/test/1/")
    await expect(page.locator("#one")).to_contain_text("Mirror")
    await expect(page.locator("#one")).to_contain_text("Test Character")

    await casting(live_server, page)


async def casting(live_server, page):
    await go_to(page, live_server, "/test/1/manage/config")
    await page.get_by_role("link", name=re.compile(r"^Casting\s.+")).click()
    await page.locator("#id_casting_characters").click()
    await page.locator("#id_casting_characters").fill("1")
    await page.locator("#id_casting_min").click()
    await page.locator("#id_casting_min").fill("1")
    await page.locator("#id_casting_max").click()
    await page.locator("#id_casting_max").fill("1")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # sign up and fill preferences
    await go_to(page, live_server, "/test/1/register")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/casting")
    await page.locator("#faction0").select_option("all")
    await page.locator("#choice0").click()
    await expect(page.locator("#casting")).to_contain_text("Mirror")
    await expect(page.locator("#casting")).to_contain_text("Test Character")
    await page.locator("#choice0").select_option("2")
    await submit(page)

    # perform casting
    await go_to(page, live_server, "/test/1/manage/casting")
    await page.get_by_role("button", name="Start algorithm").click()
    await expect(page.locator("#assegnazioni")).to_contain_text("#1 Test Character")
    await expect(page.locator("#assegnazioni")).to_contain_text("-> #2 Mirror")
    await page.get_by_role("button", name="Upload").click()

    # check assignment
    await go_to(page, live_server, "/test/1/manage/registrations")
    await expect(page.locator("#one")).to_contain_text("#1 Test Character")

    await go_to(page, live_server, "/test/1")
    await expect(page.locator("#one")).to_contain_text("Test Character")
    await expect(page.locator("#one")).not_to_contain_text("Mirror")
