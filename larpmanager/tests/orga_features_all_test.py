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

from larpmanager.tests.utils import (
    _checkboxes,
    add_links_to_visit,
    go_to,
    go_to_check,
    handle_error,
    login_orga,
    page_start,
)


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_orga_features_all(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await orga_features_all(live_server, page)

        except Exception as e:
            await handle_error(page, e, "orga_features")

        finally:
            await context.close()
            await browser.close()


async def orga_features_all(live_server, page):
    await login_orga(page, live_server)

    await go_to(page, live_server, "/test/1/manage/features")
    await _checkboxes(page, True)

    await visit_all(page, live_server)

    await go_to(page, live_server, "/test/1/manage/features")
    await _checkboxes(page, False)


async def visit_all(page, live_server):
    # Visit every link
    visited_links = set()
    links_to_visit = {live_server.url + "/manage/"}
    while links_to_visit:
        current_link = links_to_visit.pop()
        if current_link in visited_links:
            continue
        visited_links.add(current_link)

        await go_to_check(page, current_link)

        await add_links_to_visit(links_to_visit, page, visited_links)
