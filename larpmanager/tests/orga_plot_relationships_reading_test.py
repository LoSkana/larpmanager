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

from larpmanager.tests.utils import (
    fill_tinymce,
    go_to,
    handle_error,
    login_orga,
    page_start,
)


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_plot_relationship_reading(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await plot_relationship_reading(live_server, page)

        except Exception as e:
            await handle_error(page, e, "plot_relationship_reading")

        finally:
            await context.close()
            await browser.close()


async def plot_relationship_reading(live_server, page):
    await login_orga(page, live_server)

    # prepare
    await page.get_by_role("link", name="").click()
    await page.get_by_role("link", name=" Test Larp").click()
    await page.locator("#orga_features").get_by_role("link", name="Features").click()
    await page.locator("#id_mod_1_0").check()
    await page.locator("#id_mod_1_4").check()
    await page.locator("#id_mod_1_6").check()
    await page.get_by_role("button", name="Confirm").click()

    await test_relationships(live_server, page)

    await test_plots(live_server, page)

    await test_reading(live_server, page)


async def test_reading(live_server, page):
    await go_to(page, live_server, "/test/1/manage/")

    # set prova presentation and text
    await page.get_by_role("link", name="Characters").click()
    await page.locator('[id="\\32 "]').get_by_role("link", name="").click()

    await fill_tinymce(page, "id_teaser", "pppresssent")

    await fill_tinymce(page, "id_text", "totxeet")

    await page.get_by_role("button", name="Confirm").click()

    # now read it
    await page.get_by_role("link", name="Reading").click()
    await page.get_by_role("row", name=" prova character pppresssent").get_by_role("link").click()
    await expect(page.locator("#one")).to_contain_text(
        "Test Larp Presentation pppresssent Text totxeet testona wwwwwbruuuu Relationships Test Character ciaaoooooo"
    )

    # test reading with factions
    await page.get_by_role("link", name="Features").click()
    await page.locator("#id_mod_1_3").check()
    await page.get_by_role("button", name="Confirm").click()

    # create faction with test character
    await page.get_by_role("link", name="Factions").click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("only for testt")
    await page.get_by_role("listitem").click()
    await page.get_by_role("searchbox").fill("te")
    await page.get_by_role("option", name="#1 Test Character").click()
    await page.get_by_role("button", name="Confirm").click()

    # check faction main list
    await page.locator("#one").get_by_role("link", name="Characters").click()
    await expect(page.locator("#one")).to_contain_text("only for testt Primary #1 Test Character")

    # check reading for prova
    await page.get_by_role("link", name="Reading").click()
    await page.get_by_role("row", name=" prova character pppresssent").get_by_role("link").click()
    await expect(page.locator("#one")).to_contain_text(
        "Test Larp Presentation pppresssent Text totxeet testona wwwwwbruuuu Relationships Test Character Factions: only for testt ciaaoooooo"
    )

    # check reading plot
    page.get_by_role("row", name=" testona plot asadsadas wwwww").get_by_role("link").click()
    expect(page.locator("#one")).to_contain_text("testona Text wwwww prova bruuuu")


async def test_relationships(live_server, page):
    # create second character
    await page.get_by_role("link", name="Characters", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("prova")
    await page.get_by_role("combobox").click()
    await page.get_by_role("searchbox").fill("tes")
    await page.get_by_role("option", name="#1 Test Character").click()
    await fill_tinymce(page, "rel_1_direct", "ciaaoooooo")
    await page.get_by_role("button", name="Confirm").click()

    # check in main list
    await page.get_by_role("link", name="Relationships").click()
    await expect(page.locator("#one")).to_contain_text(
        "#1 Test Character Test Teaser Test Text #2 prova #1 Test Character"
    )

    # check in char
    await page.locator('[id="\\32 "]').get_by_role("link", name="").click()
    await page.get_by_role("row", name="Direct Show How the").get_by_role("link").click()
    await expect(page.locator("#form_relationships")).to_contain_text("#1 Test Character Direct Show <p>ciaaoooooo</p>")

    # check in other char
    await go_to(page, live_server, "/test/1/manage/characters/#")
    await page.locator('[id="\\31 "]').get_by_role("cell", name="").click()
    await page.get_by_role("row", name="Inverse Show How the").get_by_role("link").click()
    await expect(page.locator("#form_relationships")).to_contain_text("Inverse Show ciaaoooooo")

    # check in gallery
    await go_to(page, live_server, "/test/1/")
    await page.get_by_role("link", name="prova").click()
    await expect(page.locator("#one")).to_contain_text("Relationships Test Character ciaaoooooo")


async def test_plots(live_server, page):
    # create plot
    await go_to(page, live_server, "/test/1/manage/")
    await page.get_by_role("link", name="Plots").click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("testona")

    # set concept
    await fill_tinymce(page, "id_teaser", "asadsadas")

    # set text
    await fill_tinymce(page, "id_text", "wwwww")

    # set char role
    await page.get_by_role("searchbox").click()
    await page.get_by_role("searchbox").fill("te")
    await page.get_by_role("option", name="#1 Test Character").click()

    await fill_tinymce(page, "ch_1", "prova")

    await page.get_by_role("button", name="Confirm").click()

    # check in plot list
    await page.locator("#one").get_by_role("link", name="Characters").click()
    await expect(page.locator("#one")).to_contain_text("T1 testona asadsadas wwwww #1 Test Character")

    # check it is the same
    await page.get_by_role("link", name="").click()
    await asyncio.sleep(2)
    locator = page.locator('a.my_toggle[tog="f_id_char_role_1"]')
    await locator.click()
    await expect(page.locator("#one")).to_contain_text("#1 Test Character Show <p>prova</p>")
    await locator.click()

    # change it
    await fill_tinymce(page, "id_char_role_1", "prova222")
    await page.get_by_role("button", name="Confirm").click()

    # check it
    await page.locator("#one").get_by_role("link", name="Characters").click()
    await expect(page.locator("#one")).to_contain_text("T1 testona asadsadas wwwww #1 Test Character")
    await page.get_by_role("link", name="").click()
    await asyncio.sleep(2)
    locator = page.locator('a.my_toggle[tog="f_id_char_role_1"]')
    await locator.click()
    await expect(page.locator("#one")).to_contain_text("#1 Test Character Show <p>prova222</p>")

    # remove first char
    await page.get_by_role("listitem", name="#1 Test Character").locator("span").click()
    # add another char
    await page.get_by_role("searchbox").fill("pro")
    await page.get_by_role("option", name="#2 prova").click()
    await page.get_by_role("button", name="Confirm").click()

    # check
    await page.locator("#one").get_by_role("link", name="Characters").click()
    await expect(page.locator("#one")).to_contain_text("T1 testona asadsadas wwwww #2 prova")

    # set text
    await page.get_by_role("link", name="").click()
    await fill_tinymce(page, "id_char_role_2", "bruuuu")
    await page.get_by_role("button", name="Confirm").click()

    # check in user
    await go_to(page, live_server, "/test/1/")
    await page.get_by_role("link", name="prova").click()
    await expect(page.locator("#one")).to_contain_text("testona wwwwwbruuuu")
