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

from larpmanager.tests.utils import go_to, handle_error, login_orga, page_start


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_exe_events_run(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await exe_events_run(live_server, page)

        except Exception as e:
            await handle_error(page, e, "exe_events")

        finally:
            await context.close()
            await browser.close()


async def exe_events_run(live_server, page):
    await login_orga(page, live_server)

    await go_to(page, live_server, "/manage/events")
    await page.get_by_role("link", name="New event").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("Prova Event")
    await page.locator("#id_name").press("Tab")
    await page.locator("#slug").fill("prova")

    frame = page.frame_locator("iframe.tox-edit-area__iframe")
    await frame.locator("body").fill("sadsadasdsaas")
    await page.locator("#id_max_pg").click()
    await page.locator("#id_max_pg").fill("10")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # confirm quick setup
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await page.locator("#id_development").select_option("1")
    await page.locator("#id_start").fill("2025-06-11")
    await asyncio.sleep(2)
    await page.locator("#id_start").click()
    await page.locator("#id_end").fill("2025-06-13")
    await asyncio.sleep(2)
    await page.locator("#id_end").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await expect(page.locator("#one")).to_contain_text("Prova Event")
    await go_to(page, live_server, "/prova/1/manage/")

    await expect(page.locator("#banner")).to_contain_text("Prova Event")
    await go_to(page, live_server, "")
    await expect(page.locator("#one")).to_contain_text("Prova Event")
