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

from larpmanager.tests.utils import check_download, go_to, handle_error, login_orga, page_start


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_user_pdf(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await user_pdf(live_server, page)

        except Exception as e:
            await handle_error(page, e, "user_pdf")

        finally:
            await context.close()
            await browser.close()


async def user_pdf(live_server, page):
    await login_orga(page, live_server)

    # activate characters
    await go_to(page, live_server, "/test/1/manage/features/178/on")

    # activate relationships
    await go_to(page, live_server, "/test/1/manage/features/75/on")

    # activate pdf
    await go_to(page, live_server, "/test/1/manage/features/21/on")

    # signup
    await go_to(page, live_server, "/test/1/register")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # Assign character
    await go_to(page, live_server, "/test/1/manage/registrations")
    await page.locator("a:has(i.fas.fa-edit)").click()
    await page.get_by_role("searchbox").click()
    await page.get_by_role("searchbox").fill("te")
    await page.get_by_role("option", name="#1 Test Character").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # Go to character, test download pdf
    await go_to(page, live_server, "/test/1/character/1")

    await check_download(page, "Portraits (PDF)")

    await check_download(page, "Profiles (PDF)")

    await check_download(page, "Download complete sheet")

    await check_download(page, "Download light sheet")

    await check_download(page, "Download relationships")
