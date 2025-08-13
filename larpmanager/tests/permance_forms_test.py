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
from playwright.async_api import async_playwright, expect

from larpmanager.tests.utils import go_to, handle_error, login_orga, page_start


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_permanence_form(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await permanence_form(live_server, page)

        except Exception as e:
            await handle_error(page, e, "permanence_form")

        finally:
            await context.close()
            await browser.close()


async def permanence_form(live_server, page):
    await login_orga(page, live_server)

    await go_to(page, live_server, "/manage")

    await check_exe_roles(page)

    await check_exe_features(page)

    await check_exe_config(page)

    await go_to(page, live_server, "/test/1/manage")

    await check_orga_roles(page)

    await check_orga_config(page)

    await check_orga_features(page)

    await check_orga_preferences(page)

    await check_orga_visibility(page)


async def check_orga_visibility(page):
    await page.get_by_role("link", name="Event").click()
    await page.get_by_role("link", name="Configuration").click()
    await page.get_by_role("link", name="Writing ").click()
    await page.locator("#id_writing_field_visibility").check()
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("link", name="Event", exact=True).click()
    await page.locator("#id_form2-show_character_0").check()
    await page.locator("#id_form2-show_character_2").check()
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("link", name="Event", exact=True).click()
    await expect(page.locator("#id_form2-show_character_0")).to_be_checked()
    await expect(page.locator("#id_form2-show_character_2")).to_be_checked()
    await expect(page.locator("#id_form2-show_character_1")).not_to_be_checked()


async def check_orga_preferences(page):
    await page.get_by_role("link", name="Preferences").click(force=True)
    await page.locator("#id_open_registration_1_0").check()
    await page.locator("#id_open_registration_1_2").check()
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("link", name="Preferences").click(force=True)
    await expect(page.locator("#id_open_registration_1_0")).to_be_checked()
    await expect(page.locator("#id_open_registration_1_1")).not_to_be_checked()
    await expect(page.locator("#id_open_registration_1_2")).to_be_checked()
    await expect(page.locator("#id_open_registration_1_3")).not_to_be_checked()
    await page.get_by_role("link", name="Features").click()
    await page.locator("#id_mod_1_0").check(force=True)
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("link", name="Preferences").click(force=True)
    await page.locator("#id_open_character_1_0").check()
    await page.get_by_text("Stats").click()
    await page.locator("#id_open_character_1_2").check()
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("link", name="Preferences").click(force=True)
    await expect(page.locator("#id_open_character_1_0")).to_be_checked()
    await expect(page.locator("#id_open_character_1_1")).not_to_be_checked()
    await expect(page.locator("#id_open_character_1_2")).to_be_checked()


async def check_orga_features(page):
    await page.get_by_role("link", name="Features").click()
    await page.locator("#id_mod_7_0").check(force=True)
    await page.locator("#id_mod_7_2").check(force=True)
    await page.locator("#id_mod_4_1").check(force=True)
    await page.locator("#id_mod_4_3").check(force=True)
    await page.get_by_role("button", name="Confirm").click()
    await expect(page.locator("#one")).to_contain_text("Now you can set customization options")
    await expect(page.locator("#one")).to_contain_text(
        "You have activated the following features, for each here's the links to follow"
    )
    await page.get_by_role("link", name="Features").click()
    await expect(page.locator("#id_mod_7_0")).to_be_checked()
    await expect(page.locator("#id_mod_7_1")).not_to_be_checked()
    await expect(page.locator("#id_mod_7_2")).to_be_checked()
    await expect(page.locator("#id_mod_4_0")).not_to_be_checked()
    await expect(page.locator("#id_mod_4_1")).to_be_checked()
    await expect(page.locator("#id_mod_4_2")).not_to_be_checked()
    await expect(page.locator("#id_mod_4_3")).to_be_checked()


async def check_orga_config(page):
    await page.get_by_role("link", name="Configuration").click()
    await page.get_by_role("link", name="Visualisation ").click()
    await page.locator("#id_show_shortcuts_mobile").check()
    await page.get_by_text("If checked: Show summary page").click()
    await page.locator("#id_show_limitations").check()
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("link", name="Configuration").click()
    await page.get_by_text("Email notifications Disable").click()
    await page.get_by_text("If checked, options no longer").click()
    await page.get_by_role("link", name="Registration form ").click()
    await page.get_by_role("link", name="Visualisation ").click()
    await expect(page.locator("#id_show_shortcuts_mobile")).to_be_checked()
    await expect(page.locator("#id_show_export")).not_to_be_checked()
    await expect(page.locator("#id_show_limitations")).to_be_checked()


async def check_orga_roles(page):
    await page.locator("#orga_roles").get_by_role("link", name="Roles").click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("testona")
    await page.locator("#id_name").press("Tab")
    await page.get_by_role("searchbox").fill("org")
    await page.get_by_role("option", name="Admin Test - orga@test.it").click()
    await page.locator("#id_Event_0").check()
    await page.locator("#id_Event_2").check()
    await page.locator("#id_Event_4").check()
    await page.locator("#id_Appearance_2").check()
    await page.locator("#id_Appearance_1").check()
    await page.get_by_role("button", name="Confirm").click()
    await expect(page.locator('[id="\\32 "]')).to_contain_text(
        "Event (Event, Configuration, Preferences), Appearance (Texts, Navigation)"
    )
    await page.get_by_role("row", name=" testona Admin Test Event (").get_by_role("link").click()
    await expect(page.locator("#id_Event_0")).to_be_checked()
    await expect(page.locator("#id_Event_1")).not_to_be_checked()
    await expect(page.locator("#id_Event_2")).to_be_checked()
    await expect(page.locator("#id_Event_3")).not_to_be_checked()
    await expect(page.locator("#id_Event_4")).to_be_checked()
    await expect(page.locator("#id_Appearance_0")).not_to_be_checked()
    await expect(page.locator("#id_Appearance_1")).to_be_checked()
    await expect(page.locator("#id_Appearance_2")).to_be_checked()


async def check_exe_config(page):
    await page.get_by_role("link", name="Configuration").click()
    await page.get_by_role("link", name="Calendar ").click()
    await page.locator("#id_calendar_past_events").check()
    await page.locator("#id_calendar_description").check()
    await page.locator("#id_calendar_authors").check()
    await page.locator("#id_calendar_tagline").check()
    await page.get_by_role("button", name="Confirm").click()
    await page.get_by_role("link", name="Configuration").click()
    await page.get_by_role("link", name="Calendar ").click()
    await expect(page.locator("#id_calendar_past_events")).to_be_checked()
    await expect(page.locator("#id_calendar_website")).not_to_be_checked()
    await expect(page.locator("#id_calendar_description")).to_be_checked()
    await expect(page.locator("#id_calendar_where")).not_to_be_checked()
    await expect(page.locator("#id_calendar_authors")).to_be_checked()
    await expect(page.locator("#id_calendar_genre")).not_to_be_checked()
    await expect(page.locator("#id_calendar_tagline")).to_be_checked()


async def check_exe_features(page):
    await page.get_by_role("link", name="Features").click()
    await page.locator("#id_mod_12_0").check(force=True)
    await page.locator("#id_mod_6_1").check(force=True)
    await page.get_by_role("button", name="Confirm").click()
    await expect(page.locator("#one")).to_contain_text("Now you can create event templates")
    await page.get_by_role("link", name="Features").click()
    await expect(page.locator("#id_mod_12_0")).to_be_checked()
    await expect(page.locator("#id_mod_12_1")).not_to_be_checked()
    await expect(page.locator("#id_mod_6_0")).not_to_be_checked()
    await expect(page.locator("#id_mod_6_1")).to_be_checked()


async def check_exe_roles(page):
    await page.locator("#exe_roles").get_by_role("link", name="Roles").click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("test")
    await page.get_by_role("searchbox").click()
    await page.get_by_role("searchbox").fill("org")
    await page.get_by_role("option", name="Admin Test - orga@test.it").click()
    await page.locator("#id_Organization_0").check()
    await page.locator("#id_Organization_2").check()
    await page.locator("#id_Appearance_1").check()
    await page.locator("#id_Events_0").check()
    await page.get_by_role("button", name="Confirm").click()
    await expect(page.locator('[id="\\32 "]')).to_contain_text(
        "Organization (Organization, Configuration), Events (Events), Appearance (Texts)"
    )
    await page.locator('[id="\\32 "]').get_by_role("cell", name="").click()
    await expect(page.locator("#id_Organization_0")).to_be_checked()
    await expect(page.locator("#id_Organization_1")).not_to_be_checked()
    await expect(page.locator("#id_Organization_2")).to_be_checked()
    await expect(page.locator("#id_Organization_3")).not_to_be_checked()
    await expect(page.locator("#id_Events_0")).to_be_checked()
    await expect(page.locator("#id_Appearance_0")).not_to_be_checked()
    await expect(page.locator("#id_Appearance_1")).to_be_checked()
