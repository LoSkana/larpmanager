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

from larpmanager.tests.utils import check_download, go_to, handle_error, login_orga, page_start


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


def get_path(file):
    return Path(__file__).parent / "resources" / "test_upload" / file


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

    await char_form(page)

    await factions(page)

    await characters(page)

    await reg_form(page)

    await registrations(page)

    await quest_trait(page)

    await plots(live_server, page)

    await relationships(page)

    await full(page)


async def full(page):
    await page.get_by_role("link", name="Dashboard").click()
    await check_download(page, "Full backup")


async def relationships(page):
    await page.get_by_role("link", name="Features").click()
    await page.locator("#id_mod_1_6").check()
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("link", name="Upload").click()
    await check_download(page, "Download example template")
    await page.locator("#id_second").click()
    await page.locator("#id_second").set_input_files(get_path("relationships.csv"))
    await page.get_by_role("button", name="Submit").click()
    await expect(page.locator("#one")).to_contain_text("OK - Relationship characcter test character")
    await page.get_by_role("link", name="Proceed").click()
    await page.get_by_role("link", name="Relationships").click()
    await expect(page.locator("#one")).to_contain_text(
        "#1 Test Character Test Teaser Test Text #2 characcter trg poor ertd fewr #1 Test Character"
    )


async def plots(live_server, page):
    await page.get_by_role("link", name="Plots").click()
    await page.get_by_role("link", name="Upload").click()
    await check_download(page, "Download example template")
    await page.locator("#id_first").click()
    await page.locator("#id_first").set_input_files(get_path("plot.csv"))
    await page.locator("#id_second").click()
    await page.locator("#id_second").set_input_files(get_path("roles.csv"))
    await page.get_by_role("button", name="Submit").click()
    await expect(page.locator("#one")).to_contain_text(
        "Loading performed, see logs Proceed Logs OK - Created plottOK - Plot role characcter plott"
    )
    await page.get_by_role("link", name="Proceed").click()
    await expect(page.locator("#one")).to_contain_text("T1 plott conceptt textt")
    await page.get_by_role("link", name="").click()
    await page.get_by_role("cell", name="Show This text will be added").get_by_role("link").click()
    await expect(page.locator("#id_ch_2_tr")).to_contain_text("#2 characcter")
    await expect(page.locator("#id_ch_2_tr")).to_contain_text("super start")
    await go_to(page, live_server, "/test/1/manage/plots/")
    await check_download(page, "Download")


async def quest_trait(page):
    await page.get_by_role("link", name="Quest", exact=True).click()
    await page.get_by_role("link", name="Upload").click()
    await check_download(page, "Download example template")
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("link", name="Quest type").click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("bhbh")
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("link", name="Quest", exact=True).click()
    await page.get_by_role("link", name="Upload").click()
    await check_download(page, "Download example template")
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("button", name="Choose File").set_input_files(get_path("quest.csv"))
    await page.get_by_role("button", name="Submit").click()
    await expect(page.locator("#one")).to_contain_text("Loading performed, see logs Proceed Logs OK - Created questt")
    await page.get_by_role("link", name="Proceed").click()
    await expect(page.locator("#one")).to_contain_text("Q1 questt bhbh presenttation ttext")
    await check_download(page, "Download")
    await page.locator("#orga_traits").get_by_role("link", name="Traits").click()
    await page.get_by_role("link", name="Upload").click()
    await check_download(page, "Download example template")
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("button", name="Choose File").set_input_files(get_path("trait.csv"))
    await page.get_by_role("button", name="Submit").click()
    await expect(page.locator("#one")).to_contain_text("Loading performed, see logs Proceed Logs OK - Created traitt")
    await page.get_by_role("link", name="Proceed").click()
    await expect(page.locator("#one")).to_contain_text("T1 traitt Q1 questt ppresentation teeeext")
    await check_download(page, "Download")


async def registrations(page):
    await page.get_by_role("link", name="Registrations").click()
    await page.get_by_role("link", name="Upload").click()
    await check_download(page, "Download example template")
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("button", name="Choose File").set_input_files(get_path("relationships.csv"))
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("button", name="Choose File").set_input_files(get_path("registration.csv"))
    await page.get_by_role("button", name="Submit").click()
    await expect(page.locator("#one")).to_contain_text("OK - Created User Test")
    await page.get_by_role("link", name="Proceed").click()
    await expect(page.locator("#one")).to_contain_text("User Test Standard #2 characcter")
    await check_download(page, "Download")


async def reg_form(page):
    await page.locator("#orga_registration_form").get_by_role("link", name="Form").click()
    await page.get_by_role("link", name="Upload").click()
    await check_download(page, "Download example template")
    await page.get_by_role("row", name="Questions Choose File").locator("td").click()
    await page.locator("#id_first").set_input_files(get_path("reg-questions.csv"))
    await page.locator("#id_second").click()
    await page.locator("#id_second").set_input_files(get_path("reg-options.csv"))
    await page.get_by_role("button", name="Submit").click()
    await expect(page.locator("#one")).to_contain_text(
        "Loading performed, see logs Proceed Logs OK - Created tbmobwOK - Created qmhcufOK - Created holdmfOK - Created lyucezOK - Created bamkzwOK - Created npyrxdOK - Created rdtbggOK - Created qkcyjrOK - Created fjxkum"
    )
    await page.get_by_role("link", name="Proceed").click()
    await expect(page.locator("#one")).to_contain_text(
        "tbmobw npyrxd Multiple choice Optional npyrxd , rdtbgg qmhcuf rdtbgg Multi-line text Mandatory holdmf qkcyjr Single-line text Disabled lyucez fjxkum Advanced text editor Hidden bamkzw fzynqq Single choice Optional qkcyjr , fjxkum"
    )
    await check_download(page, "Download")


async def characters(page):
    await page.locator("#orga_characters").get_by_role("link", name="Characters").click()
    await page.get_by_role("link", name="Upload").click()
    await check_download(page, "Download example template")
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("button", name="Choose File").set_input_files(get_path("character.csv"))
    await page.get_by_role("button", name="Submit").click()
    await expect(page.locator("#one")).to_contain_text("OK - Created characcter")
    await page.get_by_role("link", name="Proceed").click()
    await expect(page.locator("#one")).to_contain_text(
        "#1 Test Character Test Teaser Test Text #2 characcter trg poor ertd fewr"
    )
    await check_download(page, "Download")


async def factions(page):
    await page.get_by_role("link", name="Factions").click()
    await page.get_by_role("link", name="Upload").click()
    await check_download(page, "Download example template")
    await page.get_by_role("button", name="Choose File").click()
    await page.get_by_role("button", name="Choose File").set_input_files(get_path("faction.csv"))
    await page.get_by_role("button", name="Submit").click()
    await expect(page.locator("#one")).to_contain_text("OK - Created facction")
    await page.get_by_role("link", name="Proceed").click()
    await expect(page.locator("#one")).to_contain_text("facction Primary gh asd oeir sdf")
    await check_download(page, "Download")


async def char_form(page):
    await page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    await page.get_by_role("link", name="Upload").click()
    await check_download(page, "Download example template")
    await page.locator("#id_first").set_input_files(get_path("char-questions.csv"))
    await page.locator("#id_second").set_input_files(get_path("char-options.csv"))
    await page.get_by_role("button", name="Submit").click()
    await expect(page.locator("#one")).to_contain_text(
        "Loading performed, see logs Proceed Logs OK - Created bibiOK - Created babaOK - Created werOK - Created asdOK - Created poiOK - Created huhuOK - Created trtrOK - Created rrrrrrOK - Created tttttt"
    )
    await page.get_by_role("link", name="Proceed").click()
    await expect(page.locator("#one")).to_contain_text(
        "Name Name Presentation Presentation Text Sheet Faction Factions Hidden bibi baba Multiple choice Searchable huhu , trtr"
    )
    await check_download(page, "Download")
    await page.get_by_role("link", name="Plot", exact=True).click()
    await expect(page.locator("#one")).to_contain_text(
        "Name Name Concept Presentation Text Sheet wer fghj Single-line text Hidden"
    )
    await page.get_by_role("link", name="Faction", exact=True).click()
    await expect(page.locator("#one")).to_contain_text(
        "Name Name Presentation Presentation Text Sheet baba bebe Multi-line text Private"
    )
    await page.locator("#one").get_by_role("link", name="Quest").click()
    await expect(page.locator("#one")).to_contain_text(
        "Name Name Presentation Presentation Text Sheet asd kloi Advanced text editor Public"
    )
    await page.get_by_role("link", name="Trait", exact=True).click()
    await expect(page.locator("#one")).to_contain_text(
        "Name Name Presentation Presentation Text Sheet poi rweerw Single choice Public rrrrrr , tttttt"
    )


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
        "Test Larp Organization Home Indicate the amount of your donation: Please enter the occasion for which you wish to make the donation Choose the payment method: Wire Fee: +2% aaaa Submit"
    )
