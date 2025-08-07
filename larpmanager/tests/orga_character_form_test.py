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

import pytest
from playwright.async_api import async_playwright, expect

from larpmanager.tests.utils import fill_tinymce, go_to, handle_error, login_orga, login_user, logout, page_start


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_orga_character_form(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await orga_character_form(live_server, page)

        except Exception as e:
            await handle_error(page, e, "orga_character_form")

        finally:
            await context.close()
            await browser.close()


async def orga_character_form(live_server, page):
    await login_orga(page, live_server)

    # activate characters
    await go_to(page, live_server, "/test/1/manage/features/178/on")

    # activate player editor
    await go_to(page, live_server, "/test/1/manage/features/120/on")

    # set config
    await go_to(page, live_server, "/test/1/manage/config")
    await page.get_by_role("link", name="Player editor ").click()
    await page.locator("#id_user_character_max").click()
    await page.locator("#id_user_character_max").fill("1")
    await page.locator("#id_user_character_approval").check()
    await page.get_by_role("link", name="Character form ").click()
    await page.locator("#id_character_form_wri_que_max").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # create character form
    await go_to(page, live_server, "/test/1/manage/characters/form/")

    await add_field_text(page)

    await add_field_available(page)

    await add_field_multiple(page)

    await add_field_restricted(page)

    await add_field_special(page)

    await create_first_char(live_server, page)

    await check_first_char(page, live_server)

    await recheck_char(live_server, page)

    await show_chars(page, live_server)

    await logout(page, live_server)

    await go_to(page, live_server, "/test/1/")
    await page.get_by_role("link", name="pinoloooooooooo").click()
    await expect(page.locator("#one")).to_contain_text("Player: Admin Test public: public Presentation baba")

    await create_second_char(live_server, page)


async def create_second_char(live_server, page):
    await login_user(page, live_server)
    await go_to(page, live_server, "/test/1/register/")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="Access character creation!").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("olivaaaa")
    await page.get_by_role("row", name="Presentation (*) Show").get_by_role("link").click()
    await fill_tinymce(page, "id_teaser_ifr", "dsfdfsd")
    await page.get_by_role("row", name="Text (*) Show").get_by_role("link").click()
    await fill_tinymce(page, "id_text_ifr", "sdfdsfds")
    await expect(page.locator("#id_q6")).to_match_aria_snapshot(
        '- combobox:\n  - option "-------" [disabled] [selected]\n  - option "all"\n  - option "few - (Available 1)"'
    )
    await page.locator("#id_q6").select_option("2")
    await page.locator("#id_q8").click()
    await page.locator("#id_q8").click()
    await expect(page.locator("#id_q8")).to_match_aria_snapshot(
        '- combobox:\n  - option "-------" [disabled] [selected]\n  - option "only" [disabled]\n  - option "all"'
    )
    await expect(page.locator("#id_q7")).to_match_aria_snapshot(
        '- checkbox "all"\n- text: all\n- checkbox "many - (Available 1)"\n- text: many - (Available 1)\n- checkbox "few" [disabled]\n- text: few'
    )
    await expect(page.get_by_role("checkbox", name="few")).to_be_disabled()
    await page.get_by_role("checkbox", name="many - (Available 1)").check()
    await expect(page.locator('[id="id_q7_tr"]')).to_contain_text("options: 1 / 2")
    await page.locator("#id_q9").click()
    await page.locator("#id_q9").fill("asda")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await expect(page.locator("#one")).to_contain_text(
        "Player: User Test Status: Creation available text: few multiple text: many mandatory: asda Presentation dsfdfsd Text sdfdsfds"
    )


async def show_chars(page, live_server):
    await go_to(page, live_server, "/test/1/manage/config")
    await page.get_by_role("link", name=re.compile(r"^Writing")).click()
    await page.locator("#id_writing_field_visibility").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/manage/run")
    for s in range(0, 13):
        await page.locator(f"#id_show_character_{s}").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def check_first_char(page, live_server):
    await page.get_by_role("link", name="Change").click()
    await expect(page.locator("#id_q4")).to_have_value("aaaaaaaaaa")
    await page.get_by_text("bbbbbbbbbb").click()
    await expect(page.get_by_text("bbbbbbbbbb")).to_have_value("bbbbbbbbbb")
    await expect(page.locator("#id_q6")).to_have_value("1")
    await page.locator("#id_q8").click()
    await expect(page.locator("#id_q8")).to_have_value("6")
    await expect(page.locator("#id_q7")).to_match_aria_snapshot(
        '- checkbox "all" [checked]\n- text: all\n- checkbox "many" [checked]\n- text: many\n- checkbox "few - (Available 1)" [disabled]\n- text: few - (Available 1)'
    )
    await expect(page.locator("#id_q9")).to_have_value("fill mandatory")
    await expect(page.locator("#id_q12")).to_have_value("public")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/manage/characters/")
    await page.locator('[id="\\32 "]').get_by_role("link", name="").click()
    await page.locator("#id_q4").click()
    await page.locator("#id_q4").fill("cccccccccc")
    await page.locator("#id_q4").press("Tab")
    await page.get_by_text("bbbbbbbbbb").click()
    await page.get_by_text("bbbbbbbbbb").fill("dddddddddd")
    await page.locator("#id_q6").select_option("2")
    await page.locator("#id_q8").select_option("7")
    await page.get_by_role("checkbox", name="all").uncheck()
    await page.get_by_role("checkbox", name="few").check()
    await page.locator("#id_q10").click()
    await page.locator("#id_q10").press("Tab")
    await page.locator("#id_q10").click()
    await page.locator("#id_q10").press("Tab")
    await page.locator("#id_q9").click()
    await page.locator("#id_q9").press("Tab")
    await page.locator("#id_q10").fill("disabled")
    await page.locator("#id_q10").press("Tab")
    await page.locator("#id_q11").fill("hidden")
    await page.locator("#id_status").select_option("a")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.locator('[id="\\32 "]').get_by_role("link", name="").click()
    await expect(page.locator("#id_q4")).to_have_value("cccccccccc")
    await expect(page.get_by_text("dddddddddd")).to_have_value("dddddddddd")
    await expect(page.locator("#id_q6")).to_have_value("2")
    await expect(page.locator("#id_q8")).to_have_value("7")
    await expect(page.locator("#id_q10")).to_have_value("disabled")
    await expect(page.locator("#id_q11")).to_have_value("hidden")
    await expect(page.locator("#lbl_id_q4")).to_contain_text("short text")
    await page.get_by_role("cell", name="long text").dblclick()
    await expect(page.locator("#lbl_id_q5")).to_contain_text("long text")
    await expect(page.locator("#main_form")).to_contain_text("short descr")
    await page.get_by_text("long descr").click()


async def recheck_char(live_server, page):
    await expect(page.locator("#main_form")).to_contain_text("long descr")
    await expect(page.locator("#lbl_id_q8")).to_contain_text("restricted")
    await expect(page.locator("#main_form")).to_contain_text("restricted textonly only descrall all descr")
    await expect(page.locator('[id="id_q7_tr"]')).to_contain_text("multiple text")
    await expect(page.locator('[id="id_q7_tr"]')).to_contain_text(
        "multiple descrall all descrmany many descrfew few descr"
    )
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await go_to(page, live_server, "/test/1/character/list")
    await page.get_by_role("link", name="").click()
    await expect(page.locator("#id_q10")).to_have_value("disabled")
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def create_first_char(live_server, page):
    await go_to(page, live_server, "/test/1/register/")
    await page.get_by_role("link", name="Register").click()
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="Access character creation!").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("pinoloooooooooo")

    await fill_presentation_text(page)

    await expect(page.locator("#lbl_id_text")).to_contain_text("Text (*)")
    await expect(page.locator("#lbl_id_teaser")).to_contain_text("Presentation (*)")
    await expect(page.locator("#lbl_id_name")).to_contain_text("Name (*)")
    await expect(page.locator("#main_form")).to_contain_text("short descr")
    await page.locator("#id_q4").click()
    await page.locator("#id_q4").fill("aaaaaaaaaa")
    await page.locator("#id_q4").click()
    await page.get_by_text("long text").click()
    await page.locator("#id_q5").click()
    await page.locator("#id_q5").fill("bbbbbbbbbb")
    await expect(page.locator("#id_q5")).to_have_value("bbbbbbbbbb")
    await expect(page.locator("#main_form")).to_contain_text("long descr")
    await expect(page.locator("#main_form")).to_contain_text("text length: 10 / 10")
    await expect(page.locator("#lbl_id_q6")).to_contain_text("available text")
    await expect(page.locator("#main_form")).to_contain_text("available descrall allfew few descr")
    await page.locator("#id_q6").select_option("1")
    await page.locator("#id_q8").select_option("6")
    await expect(page.locator("#lbl_id_q8")).to_contain_text("restricted")
    await expect(page.locator("#main_form")).to_contain_text("restricted textonly only descrall all descr")
    await page.get_by_text("many - (Available 2)").click()
    await page.locator("#id_q7 div").filter(has_text="many - (Available 2)").click()
    await expect(page.locator("#id_q7")).to_contain_text("many - (Available 2)")
    await expect(page.locator("#id_q7")).to_contain_text("few - (Available 1)")
    await page.get_by_text("multiple descrall all").click()
    await expect(page.locator('[id="id_q7_tr"]')).to_contain_text(
        "multiple descrall all descrmany many descrfew few descr"
    )
    await expect(page.locator('[id="id_q7_tr"]')).to_contain_text("multiple text")
    await page.get_by_role("checkbox", name="all").check()
    await page.get_by_role("checkbox", name="many - (Available 2)").check()
    await page.get_by_text("options: 2 /").click()
    await page.locator("#id_q12").click()
    await page.locator("#id_q12").fill("public")
    await page.locator("#id_q12").press("Tab")
    await page.locator("#id_q13").fill("create")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.locator("#id_q9").fill("fill mandatory")
    await page.locator("#id_propose").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def fill_presentation_text(page):
    await page.get_by_role("row", name="Presentation (*) Show").get_by_role("link").click()
    await fill_tinymce(page, "id_teaser_ifr", "baba")
    await page.get_by_role("row", name="Text (*) Show").get_by_role("link").click()
    await fill_tinymce(page, "id_text_ifr", "bebe")


async def add_field_special(page):
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("t")
    await page.locator("#id_typ").press("Tab")
    await page.locator("#id_name").fill("mandatory")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("mandatory descr")
    await page.locator("#id_status").select_option("m")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("t")
    await page.locator("#id_typ").press("Tab")
    await page.locator("#id_name").fill("disabled")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("disabled descr")
    await page.locator("#id_status").select_option("d")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("t")
    await page.locator("#id_typ").press("Tab")
    await page.locator("#id_name").fill("hidden")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("hidden descr")
    await page.locator("#id_status").select_option("h")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("t")
    await page.locator("#id_typ").press("Tab")
    await page.locator("#id_name").fill("public")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("public descr")
    await page.locator("#id_visibility").select_option("c")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("t")
    await page.locator("#id_typ").press("Tab")
    await page.locator("#id_name").fill("only creation")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("only descr")
    await page.get_by_role("checkbox", name="Creation").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def add_field_restricted(page):
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("restricted")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("restricted text")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("all")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("all descr")
    await page.locator("#id_description").press("Tab")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("few")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("few descr")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_max_available").fill("1")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.locator('[id="\\38 "]').get_by_role("link", name="").click()
    await page.locator('[id="\\38 "]').get_by_role("link", name="").click()
    await page.get_by_role("link", name="").click()
    await page.locator('[id="\\37 "]').get_by_role("link", name="").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("w")
    await page.locator("#id_name").press("Home")
    await page.locator("#id_name").fill("only")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").press("Home")
    await page.locator("#id_description").fill("only descr")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def add_field_multiple(page):
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("m")
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("multiple text")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("multiple descr")
    await page.locator("#id_max_length").click()
    await page.locator("#id_max_length").fill("2")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("all")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("all descr")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("many")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("many descr")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_max_available").fill("2")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("few")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("few")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_description").click()
    await page.locator("#id_description").press("ArrowRight")
    await page.locator("#id_description").fill("few descr")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_max_available").fill("1")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def add_field_available(page):
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("available text")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("available descr")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_status").press("Tab")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("all")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("all")
    await page.locator("#id_description").press("Tab")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("few")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("few descr")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_max_available").fill("2")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def add_field_text(page):
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("t")
    await page.locator("#id_typ").press("Tab")
    await page.locator("#id_name").fill("short text")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("short descr")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_max_length").click()
    await page.locator("#id_max_length").press("ArrowLeft")
    await page.locator("#id_max_length").fill("10")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("p")
    await page.locator("#id_typ").press("Tab")
    await page.locator("#id_name").fill("long text")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("long descr")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_status").press("Tab")
    await page.locator("#id_visibility").press("Tab")
    await page.get_by_role("checkbox", name="Creation").press("Tab")
    await page.get_by_role("checkbox", name="Proposed").press("Tab")
    await page.get_by_role("checkbox", name="Revision").press("Tab")
    await page.get_by_role("checkbox", name="Approved").press("Tab")
    await page.locator("#id_max_length").fill("10")
    await page.get_by_role("button", name="Confirm", exact=True).click()
