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

from larpmanager.tests.utils import go_to, handle_error, login_orga, page_start, submit


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_exe_membership(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await exe_membership(live_server, page)

        except Exception as e:
            await handle_error(page, e, "exe_membership")

        finally:
            await context.close()
            await browser.close()


async def exe_membership(live_server, page):
    await login_orga(page, live_server)

    # activate members
    await go_to(page, live_server, "/manage/features/45/on")

    # register
    await go_to(page, live_server, "/test/1/register")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # confirm profile
    await page.get_by_role("checkbox", name="Authorisation").check()
    await submit(page)

    # compile request
    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_request").set_input_files(str(image_path))
    await page.locator("#id_document").set_input_files(str(image_path))
    await submit(page)

    # confirm request
    await page.locator("#id_confirm_1").check()
    await page.get_by_text("I confirm that I have").click()
    await page.locator("#id_confirm_2").check()
    await page.get_by_text("I confirm that I have").click()
    await page.locator("#id_confirm_3").check()
    await page.locator("#id_confirm_4").check()
    await submit(page)

    # go to memberships
    await go_to(page, live_server, "/manage/membership/")
    await expect(page.locator("#one")).to_contain_text("Total members: 1 - Request: 1")
    await expect(page.locator("#one")).to_contain_text("Test")
    await expect(page.locator("#one")).to_contain_text("Admin")
    await expect(page.locator("#one")).to_contain_text("orga@test.it")
    await expect(page.locator("#one")).to_contain_text("Test Larp")

    # approve
    await go_to(page, live_server, "/manage/membership/")
    await page.get_by_role("link", name="Request").click()
    await page.get_by_role("button", name="Confirm").click()

    # test
    await expect(page.locator("#one")).to_contain_text("Total members: 1 - Accepted: 1")
    await expect(page.locator("#one")).to_contain_text("Test")
    await expect(page.locator("#one")).to_contain_text("Admin")
    await expect(page.locator("#one")).to_contain_text("orga@test.it")
    await expect(page.locator("#one")).to_contain_text("Test Larp")
