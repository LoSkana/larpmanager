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

from larpmanager.tests.utils import go_to, handle_error, login_orga, login_user, logout, page_start


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_orga_registration_form(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await orga_registration_form(live_server, page)

        except Exception as e:
            await handle_error(page, e, "orga_registration_form")

        finally:
            await context.close()
            await browser.close()


async def orga_registration_form(live_server, page):
    await login_orga(page, live_server)

    # create form
    await go_to(page, live_server, "/test/1/manage/registrations/form/")

    await add_text(page)

    await add_single(page)

    await add_multiple(page)

    await add_special(page)

    await signup_first(live_server, page)

    await signup_check(live_server, page)

    await orga_check(live_server, page)

    await user_signup(live_server, page)


async def add_text(page):
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("t")
    await page.locator("#id_typ").select_option("s")
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("short text")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("short description")
    await page.locator("#id_typ").select_option("t")
    await page.locator("#id_max_length").click()
    await page.locator("#id_max_length").press("ArrowLeft")
    await page.locator("#id_max_length").fill("10")
    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_profile").set_input_files(str(image_path))
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("p")
    await page.locator("#id_typ").press("Tab")
    await page.locator("#id_name").fill("long text")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("long description")
    await page.locator("#id_max_length").click()
    await page.locator("#id_max_length").press("ArrowLeft")
    await page.locator("#id_max_length").fill("10")
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def add_single(page):
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("choice")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("choice descr")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("free")
    await page.locator("#id_description").click()
    await page.locator("#id_description").fill("free")
    await page.locator("#id_price").click()
    await page.locator("#id_price").press("ArrowLeft")
    await page.locator("#id_price").fill("10")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("many")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("many")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_price").press("Tab")
    await page.locator("#id_price").click()
    await page.locator("#id_price").press("ArrowLeft")
    await page.locator("#id_price").fill("20")
    await page.locator("#id_max_available").click()
    await page.locator("#id_max_available").fill("2")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await add_single_options(page)


async def add_single_options(page):
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("few")
    await page.locator("#id_description").click()
    await page.locator("#id_description").fill("few descr")
    await page.locator("#id_price").click()
    await page.locator("#id_price").press("ArrowLeft")
    await page.locator("#id_price").fill("30")
    await page.locator("#id_price").press("Tab")
    await page.locator("#id_max_available").fill("1")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("rescrited")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("rescrited descr")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("all")
    await page.locator("#id_description").click()
    await page.locator("#id_description").fill("all descr")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("only")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("only")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_price").fill("20")
    await page.locator("#id_price").press("Tab")
    await page.locator("#id_max_available").fill("1")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def add_multiple(page):
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("m")
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("multiple")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("multiple descr")
    await page.locator("#id_max_length").click()
    await page.locator("#id_max_length").fill("2")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("all")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("all descr")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_price").fill("10")
    await page.locator("#id_price").press("Tab")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("many")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("many descr")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_price").fill("20")
    await page.locator("#id_price").press("Tab")
    await page.locator("#id_max_available").fill("2")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("few")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("few")
    await page.locator("#id_description").press("Tab")
    await page.locator("#id_price").fill("30")
    await page.locator("#id_price").press("Tab")
    await page.locator("#id_max_available").fill("1")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def add_special(page):
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
    await page.locator("#id_name").fill("disabled")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("disabled text")
    await page.locator("#id_status").select_option("d")
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def signup_first(live_server, page):
    # sign up as first user
    await go_to(page, live_server, "/test/1/register")
    await page.get_by_role("textbox", name="short text").click()
    await page.get_by_role("textbox", name="short text").fill("aaaaaaaaaa")
    await expect(page.get_by_role("textbox", name="short text")).to_have_value("aaaaaaaaaa")
    await page.get_by_role("textbox", name="long text").click()
    await page.get_by_role("textbox", name="long text").press("CapsLock")
    await page.get_by_role("textbox", name="long text").fill("BBBBBBBBBB")
    await expect(page.get_by_role("textbox", name="long text")).to_have_value("BBBBBBBBBB")
    await page.get_by_label("choice").select_option("2")
    await page.get_by_label("rescrited").select_option("5")
    await expect(page.locator("#id_q5")).to_contain_text("many (20€) - (Available 2)")
    await expect(page.locator("#id_q5")).to_contain_text("few (30€) - (Available 1)")
    await page.get_by_role("checkbox", name="many (20€) - (Available 2)").check()
    await page.get_by_role("checkbox", name="few (30€) - (Available 1)").check()
    await expect(page.get_by_role("checkbox", name="all (10€)")).to_be_disabled()
    await expect(page.get_by_role("textbox", name="disabled")).to_be_empty()
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    # add mandatory
    await go_to(page, live_server, "/test/1/manage/registrations/form/")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("t")
    await page.locator("#id_typ").press("Tab")
    await page.locator("#id_name").fill("")
    await page.locator("#id_name").press("CapsLock")
    await page.locator("#id_name").fill("mandatory")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("mandatory text")
    await page.locator("#id_status").select_option("m")
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def signup_check(live_server, page):
    # check values
    await go_to(page, live_server, "/test/1/register")
    await expect(page.locator("#register_form")).to_contain_text("short description")
    await expect(page.get_by_role("textbox", name="short text")).to_have_value("aaaaaaaaaa")
    await expect(page.locator("#register_form")).to_contain_text("long description")
    await expect(page.locator("#register_form")).to_contain_text("text length: 10 / 10")
    await expect(page.get_by_role("textbox", name="long text")).to_have_value("BBBBBBBBBB")
    await expect(page.get_by_label("choice")).to_have_value("2")
    await expect(page.locator("#register_form")).to_contain_text("choice descrfree freemany manyfew few descr")
    await expect(page.get_by_label("rescrited")).to_have_value("5")
    await expect(page.locator("#register_form")).to_contain_text("rescrited descrall all descronly only")
    await expect(page.get_by_role("checkbox", name="all (10€)")).not_to_be_checked()
    await expect(page.get_by_role("checkbox", name="many (20€)")).to_be_checked()
    await expect(page.get_by_role("checkbox", name="few (30€)")).to_be_checked()
    await page.get_by_role("checkbox", name="few (30€)").uncheck()
    await page.get_by_role("checkbox", name="few (30€)").check()
    await expect(page.get_by_role("checkbox", name="few (30€)")).to_be_checked()
    await page.get_by_text("multiple descrall all").click()
    await page.get_by_text("many many descr").click()
    await expect(page.locator("#register_form")).to_contain_text("multiple descrall all descrmany many descrfew few")
    await expect(page.locator("#register_form")).to_contain_text("options: 2 / 2")
    await expect(page.locator("#register_form")).to_contain_text("mandatory (*)")
    await page.get_by_role("button", name="Continue").click()
    await expect(page.locator("#register_form")).to_contain_text("Please select a value")
    await expect(page.locator("#register_form")).to_contain_text("mandatory text")
    await page.get_by_role("textbox", name="mandatory (*)").click()
    await page.get_by_role("textbox", name="mandatory (*)").fill("ggggg")
    await page.get_by_role("button", name="Continue").click()
    await expect(page.locator("#riepilogo")).to_contain_text("Your updated registration total is: 90€.")
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def orga_check(live_server, page):
    # check signups
    await go_to(page, live_server, "/test/1/manage/registrations/")
    await page.get_by_role("link", name="").click()
    await expect(page.locator("#id_q1")).to_have_value("aaaaaaaaaa")
    await expect(page.get_by_text("BBBBBBBBBB")).to_have_value("BBBBBBBBBB")
    await expect(page.locator("#id_q3")).to_have_value("2")
    await expect(page.locator("#id_q4")).to_have_value("5")
    await expect(page.get_by_role("checkbox", name="all (10€)")).not_to_be_checked()
    await expect(page.get_by_role("checkbox", name="many (20€)")).to_be_checked()
    await expect(page.get_by_role("checkbox", name="few (30€)")).to_be_checked()
    await page.locator("#id_q6").click()
    await expect(page.locator("#lbl_id_q6")).to_contain_text("hidden")
    await page.locator("#id_q6").click()
    await page.locator("#id_q6").fill("dsadsadsa")
    await expect(page.locator("#main_form")).to_contain_text("hidden descr")
    await page.locator("#id_q7").click()
    await page.locator("#id_q7").fill("asdsadsa")
    await expect(page.locator("#id_q8")).to_have_value("ggggg")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="").click()
    await expect(page.locator("#id_q6")).to_have_value("dsadsadsa")
    await expect(page.locator("#id_q7")).to_have_value("asdsadsa")


async def user_signup(live_server, page):
    # signup as user
    await logout(page, live_server)
    await login_user(page, live_server)
    await expect(page.locator("#one")).to_contain_text("Hurry: only 9 tickets available.")
    await go_to(page, live_server, "/test/1/register/")
    await page.get_by_label("choice").select_option("2")
    await expect(page.get_by_label("choice")).to_have_value("2")
    await page.get_by_label("rescrited").select_option("4")
    await expect(page.get_by_label("rescrited")).to_have_value("4")
    await expect(page.get_by_label("rescrited")).to_match_aria_snapshot(
        '- combobox "rescrited":\n  - option "all" [selected]\n  - option /only \\(\\d+€\\)/ [disabled]'
    )
    await expect(page.get_by_role("checkbox", name="few (30€)")).to_be_disabled()
    await page.get_by_role("checkbox", name="many (20€) - (Available 1)").check()
    await page.get_by_role("checkbox", name="many (20€) - (Available 1)").press("s")
    await page.get_by_role("checkbox", name="many (20€) - (Available 1)").press("d")
    await page.get_by_role("textbox", name="mandatory (*)").click()
    await page.get_by_role("textbox", name="mandatory (*)").fill("aaaa")
    await page.get_by_label("rescrited").click()
    await expect(page.get_by_label("rescrited")).to_have_value("4")
    await page.get_by_text("rescrited descrall all").click()
    await page.get_by_role("button", name="Continue").click()
    await expect(page.locator("#riepilogo")).to_contain_text("40€")
    await page.get_by_role("button", name="Confirm", exact=True).click()
