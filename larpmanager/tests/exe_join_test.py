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

from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

from larpmanager.tests.utils import go_to, handle_error, page_start, submit


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_exe_join(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await exe_join(live_server, page)

        except Exception as e:
            await handle_error(page, e, "exe_join")

        finally:
            await context.close()
            await browser.close()


async def exe_join(live_server, page):
    await go_to(page, live_server, "/debug")

    await go_to(page, live_server, "/join")
    await page.get_by_role("link", name="Register").click()
    await page.get_by_role("textbox", name="Email address").click()
    await page.get_by_role("textbox", name="Email address").fill("orga@prova.it")
    await page.get_by_role("textbox", name="Email address").press("Tab")
    await page.get_by_role("textbox", name="Password", exact=True).fill("banana1234!")
    await page.get_by_role("textbox", name="Password", exact=True).press("Tab")
    await page.get_by_role("textbox", name="Password confirmation").fill("banana1234!")
    await page.get_by_role("textbox", name="Name", exact=True).click()
    await page.get_by_role("textbox", name="Name", exact=True).fill("prova")
    await page.get_by_role("cell", name="Yes, keep me posted! Do you").click()
    await page.get_by_label("Newsletter").select_option("o")
    await page.get_by_role("textbox", name="Surname").click()
    await page.get_by_role("textbox", name="Surname").fill("orga")
    await page.get_by_role("checkbox", name="Authorisation").check()
    await submit(page)

    await go_to(page, live_server, "/join")
    await page.get_by_role("textbox", name="Name").click()
    await page.get_by_role("textbox", name="Name").fill("Prova Larp")
    await page.locator("#id_profile").wait_for(state="visible")
    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_profile").set_input_files(str(image_path))
    await page.locator("#slug").fill("prova")
    await submit(page)

    await page.wait_for_timeout(1000)
    await go_to(page, live_server, "/debug/prova")

    await expect(page.locator("#header")).to_contain_text("Prova Larp")
