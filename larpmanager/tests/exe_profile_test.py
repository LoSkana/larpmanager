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
from playwright.async_api import async_playwright

from larpmanager.tests.utils import go_to, handle_error, login_orga, page_start, submit


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_exe_profile(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await exe_profile(live_server, page)

        except Exception as e:
            await handle_error(page, e, "exe_profile")

        finally:
            await context.close()
            await browser.close()


async def exe_profile(live_server, page):
    await login_orga(page, live_server)

    await go_to(page, live_server, "/manage/profile")
    await page.locator("#id_gender").select_option("o")
    await page.locator("#id_birth_place").select_option("m")
    await page.locator("#id_document_type").select_option("m")
    await page.locator("#id_diet").select_option("o")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/profile")
    await page.get_by_role("textbox", name="Name (*)", exact=True).click()
    await page.get_by_role("textbox", name="Name (*)", exact=True).press("End")
    await page.get_by_role("textbox", name="Name (*)", exact=True).fill("Orga")
    await page.get_by_role("textbox", name="Surname (*)").click()
    await page.get_by_role("textbox", name="Surname (*)").press("End")
    await page.get_by_role("textbox", name="Surname (*)").fill("Test")
    await page.get_by_label("Gender").select_option("f")
    await page.get_by_role("textbox", name="Diet").click()
    await page.get_by_role("textbox", name="Diet").fill("sadsada")
    await page.get_by_role("textbox", name="Diet").press("Shift+Home")
    await page.get_by_role("textbox", name="Diet").fill("s")
    await page.get_by_role("textbox", name="Diet").press("Shift+Home")
    await page.get_by_role("textbox", name="Diet").fill("test")
    await page.get_by_role("textbox", name="Birth place (*)").click()
    await page.get_by_role("textbox", name="Diet").click()
    await page.get_by_role("textbox", name="Diet").fill("")
    await page.get_by_role("textbox", name="Birth place (*)").click()
    await page.get_by_role("textbox", name="Birth place (*)").fill("test")
    await page.get_by_label("Document type (*)").select_option("p")
    await page.get_by_role("checkbox", name="Authorisation").check()
    await submit(page)
