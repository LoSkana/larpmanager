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
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

from larpmanager.tests.utils import go_to, handle_error, login_orga, page_start, submit


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_upload_download(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await upload_download(live_server, page)

        except Exception as e:
            await handle_error(page, e, "user_accounting")

        finally:
            await context.close()
            await browser.close()

async def upload_download(live_server, page):
    await login_orga(page, live_server)
    await go_to(page, live_server, "/manage/")

    # check shows fee
    await check_user_fee(live_server, page)

    # prepare
    await go_to(page, live_server, "/test/1/manage/")
    await page.locator("#orga_features").get_by_role("link", name="Features").click()
    await page.locator("#id_mod_1_0").check()
    await page.locator("#id_mod_1_3").check()
    await page.locator("#id_mod_1_4").check()
    await page.locator("#id_mod_5_1").check()
    await page.get_by_role("button", name="Confirm").click()

    await page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    await page.get_by_role("link", name="Upload").click()
    with page.expect_download() as download_info:
        await page.get_by_role("link", name="Download example template").click()
    download = download_info.value
    await page.locator("#id_first").click()
    await page.locator("#id_first").set_input_files("char-questions.csv")
    await page.locator("#id_first").click()
    await page.locator("#id_first").set_input_files([])
    await page.locator("#id_second").click()
    await page.locator("#id_second").set_input_files("char-options.csv")
    await page.locator("#id_first").click()
    await page.locator("#id_first").set_input_files("char-questions.csv")
    await page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text(
        "Loading performed, see logs Proceed Logs OK - Created bibiOK - Created babaOK - Created werOK - Created asdOK - Created poiOK - Created huhuOK - Created trtrOK - Created rrrrrrOK - Created tttttt")
    await page.get_by_role("link", name="Proceed").click()
    expect(page.locator("[id=\"\\31 7\"]")).to_contain_text("bibi")
    expect(page.locator("#one")).to_contain_text(
        "Name Name Presentation Presentation Text Sheet Faction Factions Hidden bibi baba Multiple choice Searchable huhu , trtr")
    with page.expect_download() as download1_info:
        await page.get_by_role("button", name="Download").click()
    download1 = download1_info.value
    await page.get_by_role("link", name="Plot", exact=True).click()
    expect(page.locator("#one")).to_contain_text(
        "Name Name Concept Presentation Text Sheet wer fghj Single-line text Hidden")
    await page.get_by_role("link", name="Faction", exact=True).click()
    expect(page.locator("#one")).to_contain_text(
        "Name Name Presentation Presentation Text Sheet baba bebe Multi-line text Private")
    await page.locator("#one").get_by_role("link", name="Quest").click()
    expect(page.locator("#one")).to_contain_text(
        "Name Name Presentation Presentation Text Sheet asd kloi Advanced text editor Public")
    await page.get_by_role("link", name="Trait", exact=True).click()
    expect(page.locator("#one")).to_contain_text(
        "Name Name Presentation Presentation Text Sheet poi rweerw Single choice Public rrrrrr , tttttt")
    await page.get_by_role("link", name="Factions").click()
    await page.get_by_role("link", name="Upload").click()
    with page.expect_download() as download2_info:
        await page.get_by_role("link", name="Download example template").click()
    download2 = download2_info.value
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("button", name="Choose File").set_input_files("faction.csv")
    await page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("OK - Created facction")
    await page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text("facction Primary gh asd oeir sdf")
    with page.expect_download() as download3_info:
        await page.get_by_role("button", name="Download").click()
    download3 = download3_info.value
    await page.locator("#orga_characters").get_by_role("link", name="Characters").click()
    await page.get_by_role("link", name="Upload").click()
    with page.expect_download() as download4_info:
        await page.get_by_role("link", name="Download example template").click()
    download4 = download4_info.value
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("button", name="Choose File").set_input_files("character.csv")
    await page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("OK - Created characcter")
    await page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text(
        "#1 Test Character Test Teaser Test Text #2 characcter trg poor ertd fewr")
    with page.expect_download() as download5_info:
        await page.get_by_role("button", name="Download").click()
    download5 = download5_info.value
    await page.locator("#orga_registration_form").get_by_role("link", name="Form").click()
    await page.get_by_role("link", name="Upload").click()
    with page.expect_download() as download6_info:
        await page.get_by_role("link", name="Download example template").click()
    download6 = download6_info.value
    await page.get_by_role("row", name="Questions Choose File").locator("td").click()
    await page.locator("#id_first").set_input_files("reg-questions.csv")
    await page.locator("#id_second").click()
    await page.locator("#id_second").set_input_files("reg-options.csv")
    await page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text(
        "Loading performed, see logs Proceed Logs OK - Created tbmobwOK - Created qmhcufOK - Created holdmfOK - Created lyucezOK - Created bamkzwOK - Created npyrxdOK - Created rdtbggOK - Created qkcyjrOK - Created fjxkum")
    await page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text(
        "tbmobw npyrxd Multiple choice Optional npyrxd , rdtbgg qmhcuf rdtbgg Multi-line text Mandatory holdmf qkcyjr Single-line text Disabled lyucez fjxkum Advanced text editor Hidden bamkzw fzynqq Single choice Optional qkcyjr , fjxkum")
    with page.expect_download() as download7_info:
        await page.get_by_role("button", name="Download").click()
    download7 = download7_info.value
    await page.get_by_role("link", name="Registrations").click()
    await page.get_by_role("link", name="Upload").click()
    with page.expect_download() as download8_info:
        await page.get_by_role("link", name="Download example template").click()
    download8 = download8_info.value
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("button", name="Choose File").set_input_files("relationships.csv")
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("button", name="Choose File").set_input_files("registration.csv")
    await page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("OK - Created User Test")
    await page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text("User Test Standard #2 characcter")
    with page.expect_download() as download9_info:
        await page.get_by_role("button", name="Download").click()
    download9 = download9_info.value
    await page.get_by_role("link", name="Quest", exact=True).click()
    await page.get_by_role("link", name="Upload").click()
    with page.expect_download() as download10_info:
        await page.get_by_role("link", name="Download example template").click()
    download10 = download10_info.value
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("link", name="Quest type").click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("bhbh")
    await page.once("dialog", lambda dialog: dialog.dismiss())
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("link", name="Quest", exact=True).click()
    await page.get_by_role("link", name="Upload").click()
    with page.expect_download() as download11_info:
        await page.get_by_role("link", name="Download example template").click()
    download11 = download11_info.value
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("button", name="Choose File").set_input_files("quest.csv")
    await page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("Loading performed, see logs Proceed Logs OK - Created questt")
    await page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text("Q1 questt bhbh presenttation ttext")
    with page.expect_download() as download12_info:
        await page.get_by_role("button", name="Download").click()
    download12 = download12_info.value
    await page.locator("#orga_traits").get_by_role("link", name="Traits").click()
    await page.get_by_role("link", name="Upload").click()
    with page.expect_download() as download13_info:
        await page.get_by_role("link", name="Download example template").click()
    download13 = download13_info.value
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("button", name="Choose File").set_input_files("trait.csv")
    await page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("Loading performed, see logs Proceed Logs OK - Created traitt")
    await page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text("T1 traitt Q1 questt ppresentation teeeext")
    with page.expect_download() as download14_info:
        await page.get_by_role("button", name="Download").click()
    download14 = download14_info.value
    await page.get_by_role("link", name="Plots").click()
    await page.get_by_role("link", name="Upload").click()
    with page.expect_download() as download15_info:
        await page.get_by_role("link", name="Download example template").click()
    download15 = download15_info.value
    await page.locator("#id_first").click()
    await page.locator("#id_first").set_input_files("plot.csv")
    await page.locator("#id_second").click()
    await page.locator("#id_second").set_input_files("roles.csv")
    await page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text(
        "Loading performed, see logs Proceed Logs OK - Created plottOK - Plot role characcter plott")
    await page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text("T1 plott conceptt textt")
    await page.get_by_role("link", name="").click()
    await page.get_by_role("cell", name="Show This text will be added").get_by_role("link").click()
    expect(page.locator("#id_ch_2_tr")).to_contain_text("#2 characcter")
    expect(page.locator("#id_ch_2_tr")).to_contain_text("super start")
    await page.goto("http://127.0.0.1:8000/test/1/manage/plots/#")
    with page.expect_download() as download16_info:
        await page.get_by_role("button", name="Download").click()
    download16 = download16_info.value
    await page.locator("#orga_characters").get_by_role("link", name="Characters").click()
    await page.get_by_role("link", name="Upload").click()
    await page.get_by_role("link", name="Features").click()
    await page.locator("#id_mod_1_6").check()
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("link", name="Upload").click()
    with page.expect_download() as download17_info:
        await page.get_by_role("link", name="Download example template").click()
    download17 = download17_info.value
    await page.locator("#id_second").click()
    await page.locator("#id_second").set_input_files("relationships.csv")
    await page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("OK - Relationship characcter test character")
    await page.get_by_role("link", name="Proceed").click()
    await page.get_by_role("link", name="Relationships").click()
    expect(page.locator("#one")).to_contain_text(
        "#1 Test Character Test Teaser Test Text #2 characcter trg poor ertd fewr #1 Test Character")
    await page.get_by_role("link", name="Dashboard").click()
    with page.expect_download() as download18_info:
        await page.get_by_role("link", name="Full backup").click()
    download18 = download18_info.value


async def check_user_fee(live_server, page):
    await go_to(page, live_server, "/manage/")
    await page.locator("#exe_features").get_by_role("link", name="Features").click()
    await page.locator("#id_mod_2_0").check()
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("checkbox", name="Wire").check()
    await page.locator("#id_wire_descr").click()
    await page.locator("#id_wire_descr").fill("aaaa")
    await page.locator("#id_wire_fee").click()
    await page.locator("#id_wire_fee").fill("2")
    await page.locator("#id_wire_payee").click()
    await page.locator("#id_wire_payee").fill("2asdsadas")
    await page.locator("#id_wire_iban").click()
    await page.locator("#id_wire_iban").fill("3sadsadsa")
    await page.get_by_role("button", name="Confirm").click()
    await page.locator("#exe_features").get_by_role("link", name="Features").click()
    await page.locator("#id_mod_2_1").check()
    await page.get_by_role("button", name="Confirm").click()
    await page.locator("#exe_config").get_by_role("link", name="Configuration").click()
    await page.get_by_role("link", name="Payments ").click()
    await page.locator("#id_payment_fees_user").check()
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("link", name=" Accounting").click()
    await page.get_by_role("link", name="follow this link").click()
    await expect(page.locator("#wrapper")).to_contain_text(
        "Test Larp Organization Home Indicate the amount of your donation: Please enter the occasion for which you wish to make the donation Choose the payment method: Wire Fee: +2% aaaa Submit")
