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

from larpmanager.tests.utils import go_to, handle_error, login_orga, login_user, logout, page_start


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_exe_assoc_role(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await exe_assoc_role(live_server, page)

        except Exception as e:
            await handle_error(page, e, "exe_assoc")

        finally:
            await context.close()
            await browser.close()


async def exe_assoc_role(live_server, page):
    await login_user(page, live_server)

    await go_to(page, live_server, "/manage/")
    await expect(page.locator("#header")).to_contain_text("Access denied")

    await login_orga(page, live_server)

    await go_to(page, live_server, "/manage/roles")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("test role")
    await page.locator("#id_name").press("Tab")
    await page.get_by_role("searchbox").fill("us")
    await page.get_by_role("option", name="User Test -").click()
    await page.locator("#id_Organization_2").check()
    await page.locator("#id_Accounting_0").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await expect(page.locator('[id="\\32 "]')).to_contain_text("Organization (Configuration), Accounting (Accounting)")

    await logout(page, live_server)
    await login_user(page, live_server)

    await go_to(page, live_server, "/manage/accounting/")
    await expect(page.locator("#banner")).to_contain_text("Accounting - Organization")

    await logout(page, live_server)
    await login_orga(page, live_server)

    await go_to(page, live_server, "/manage/roles")
    await page.get_by_role("row", name=" test role User Test").get_by_role("link").click()
    await page.get_by_role("link", name="Delete").click()
    await asyncio.sleep(2)
    await page.get_by_role("button", name="Confirmation delete").click()

    await logout(page, live_server)
    await login_user(page, live_server)

    await go_to(page, live_server, "/manage/")
    await expect(page.locator("#header")).to_contain_text("Access denied")
