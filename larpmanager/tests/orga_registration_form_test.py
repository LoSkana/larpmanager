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
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_orga, login_user, logout

pytestmark = pytest.mark.e2e


def test_orga_registration_form(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # create form
    go_to(page, live_server, "/test/1/manage/registrations/form/")

    add_text(page)

    add_single(page)

    add_multiple(page)

    add_special(page)

    signup_first(live_server, page)

    signup_check(live_server, page)

    orga_check(live_server, page)

    user_signup(live_server, page)


def add_text(page):
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").select_option("s")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("short text")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("short description")
    page.locator("#id_typ").select_option("t")
    page.locator("#id_max_length").click()
    page.locator("#id_max_length").press("ArrowLeft")
    page.locator("#id_max_length").fill("10")
    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_profile").set_input_files(str(image_path))
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("p")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("long text")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("long description")
    page.locator("#id_max_length").click()
    page.locator("#id_max_length").press("ArrowLeft")
    page.locator("#id_max_length").fill("10")
    page.get_by_role("button", name="Confirm", exact=True).click()


def add_single(page):
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("choice")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("choice descr")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("free")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("free")
    page.locator("#id_price").click()
    page.locator("#id_price").press("ArrowLeft")
    page.locator("#id_price").fill("10")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("many")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("many")
    page.locator("#id_description").press("Tab")
    page.locator("#id_price").press("Tab")
    page.locator("#id_price").click()
    page.locator("#id_price").press("ArrowLeft")
    page.locator("#id_price").fill("20")
    page.locator("#id_max_available").click()
    page.locator("#id_max_available").fill("2")
    page.get_by_role("button", name="Confirm", exact=True).click()
    add_single_options(page)


def add_single_options(page):
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("few")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("few descr")
    page.locator("#id_price").click()
    page.locator("#id_price").press("ArrowLeft")
    page.locator("#id_price").fill("30")
    page.locator("#id_price").press("Tab")
    page.locator("#id_max_available").fill("1")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("rescrited")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("rescrited descr")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("all")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("all descr")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("only")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("only")
    page.locator("#id_description").press("Tab")
    page.locator("#id_price").fill("20")
    page.locator("#id_price").press("Tab")
    page.locator("#id_max_available").fill("1")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("button", name="Confirm", exact=True).click()


def add_multiple(page):
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("m")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("multiple")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("multiple descr")
    page.locator("#id_max_length").click()
    page.locator("#id_max_length").fill("2")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("all")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("all descr")
    page.locator("#id_description").press("Tab")
    page.locator("#id_price").fill("10")
    page.locator("#id_price").press("Tab")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("many")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("many descr")
    page.locator("#id_description").press("Tab")
    page.locator("#id_price").fill("20")
    page.locator("#id_price").press("Tab")
    page.locator("#id_max_available").fill("2")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("few")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("few")
    page.locator("#id_description").press("Tab")
    page.locator("#id_price").fill("30")
    page.locator("#id_price").press("Tab")
    page.locator("#id_max_available").fill("1")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("button", name="Confirm", exact=True).click()


def add_special(page):
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("hidden")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("hidden descr")
    page.locator("#id_status").select_option("h")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("disabled")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("disabled text")
    page.locator("#id_status").select_option("d")
    page.get_by_role("button", name="Confirm", exact=True).click()


def signup_first(live_server, page):
    # sign up as first user
    go_to(page, live_server, "/test/1/register")
    page.get_by_role("textbox", name="short text").click()
    page.get_by_role("textbox", name="short text").fill("aaaaaaaaaa")
    expect(page.get_by_role("textbox", name="short text")).to_have_value("aaaaaaaaaa")
    page.get_by_role("textbox", name="long text").click()
    page.get_by_role("textbox", name="long text").press("CapsLock")
    page.get_by_role("textbox", name="long text").fill("BBBBBBBBBB")
    expect(page.get_by_role("textbox", name="long text")).to_have_value("BBBBBBBBBB")
    page.get_by_label("choice").select_option("2")
    page.get_by_label("rescrited").select_option("5")
    expect(page.locator("#id_q5")).to_contain_text("many (20€) - (Available 2)")
    expect(page.locator("#id_q5")).to_contain_text("few (30€) - (Available 1)")
    page.get_by_role("checkbox", name="many (20€) - (Available 2)").check()
    page.get_by_role("checkbox", name="few (30€) - (Available 1)").check()
    expect(page.get_by_role("checkbox", name="all (10€)")).to_be_disabled()
    expect(page.get_by_role("textbox", name="disabled")).to_be_empty()
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    # add mandatory
    go_to(page, live_server, "/test/1/manage/registrations/form/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("")
    page.locator("#id_name").press("CapsLock")
    page.locator("#id_name").fill("mandatory")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("mandatory text")
    page.locator("#id_status").select_option("m")
    page.get_by_role("button", name="Confirm", exact=True).click()


def signup_check(live_server, page):
    # check values
    go_to(page, live_server, "/test/1/register")
    expect(page.locator("#register_form")).to_contain_text("short description")
    expect(page.get_by_role("textbox", name="short text")).to_have_value("aaaaaaaaaa")
    expect(page.locator("#register_form")).to_contain_text("long description")
    expect(page.locator("#register_form")).to_contain_text("text length: 10 / 10")
    expect(page.get_by_role("textbox", name="long text")).to_have_value("BBBBBBBBBB")
    expect(page.get_by_label("choice")).to_have_value("2")
    expect(page.locator("#register_form")).to_contain_text("choice descrfree freemany manyfew few descr")
    expect(page.get_by_label("rescrited")).to_have_value("5")
    expect(page.locator("#register_form")).to_contain_text("rescrited descrall all descronly only")
    expect(page.get_by_role("checkbox", name="all (10€)")).not_to_be_checked()
    expect(page.get_by_role("checkbox", name="many (20€)")).to_be_checked()
    expect(page.get_by_role("checkbox", name="few (30€)")).to_be_checked()
    page.get_by_role("checkbox", name="few (30€)").uncheck()
    page.get_by_role("checkbox", name="few (30€)").check()
    expect(page.get_by_role("checkbox", name="few (30€)")).to_be_checked()
    page.get_by_text("multiple descrall all").click()
    page.get_by_text("many many descr").click()
    expect(page.locator("#register_form")).to_contain_text("multiple descrall all descrmany many descrfew few")
    expect(page.locator("#register_form")).to_contain_text("options: 2 / 2")
    expect(page.locator("#register_form")).to_contain_text("mandatory (*)")
    page.get_by_role("button", name="Continue").click()
    expect(page.locator("#register_form")).to_contain_text("Please select a value")
    expect(page.locator("#register_form")).to_contain_text("mandatory text")
    page.get_by_role("textbox", name="mandatory (*)").click()
    page.get_by_role("textbox", name="mandatory (*)").fill("ggggg")
    page.get_by_role("button", name="Continue").click()
    expect(page.locator("#riepilogo")).to_contain_text("Your updated registration total is: 90€.")
    page.get_by_role("button", name="Confirm", exact=True).click()


def orga_check(live_server, page):
    # check signups
    go_to(page, live_server, "/test/1/manage/registrations/")
    page.get_by_role("link", name="").click()
    expect(page.locator("#id_q1")).to_have_value("aaaaaaaaaa")
    expect(page.get_by_text("BBBBBBBBBB")).to_have_value("BBBBBBBBBB")
    expect(page.locator("#id_q3")).to_have_value("2")
    expect(page.locator("#id_q4")).to_have_value("5")
    expect(page.get_by_role("checkbox", name="all (10€)")).not_to_be_checked()
    expect(page.get_by_role("checkbox", name="many (20€)")).to_be_checked()
    expect(page.get_by_role("checkbox", name="few (30€)")).to_be_checked()
    page.locator("#id_q6").click()
    expect(page.locator("#lbl_id_q6")).to_contain_text("hidden")
    page.locator("#id_q6").click()
    page.locator("#id_q6").fill("dsadsadsa")
    expect(page.locator("#main_form")).to_contain_text("hidden descr")
    page.locator("#id_q7").click()
    page.locator("#id_q7").fill("asdsadsa")
    expect(page.locator("#id_q8")).to_have_value("ggggg")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="").click()
    expect(page.locator("#id_q6")).to_have_value("dsadsadsa")
    expect(page.locator("#id_q7")).to_have_value("asdsadsa")


def user_signup(live_server, page):
    # signup as user
    logout(page)
    login_user(page, live_server)
    expect(page.locator("#one")).to_contain_text("Hurry: only 9 tickets available.")
    go_to(page, live_server, "/test/1/register/")
    page.get_by_label("choice").select_option("2")
    expect(page.get_by_label("choice")).to_have_value("2")
    page.get_by_label("rescrited").select_option("4")
    expect(page.get_by_label("rescrited")).to_have_value("4")
    expect(page.get_by_label("rescrited")).to_match_aria_snapshot(
        '- combobox "rescrited":\n  - option "all" [selected]\n  - option /only \\(\\d+€\\)/ [disabled]'
    )
    expect(page.get_by_role("checkbox", name="few (30€)")).to_be_disabled()
    page.get_by_role("checkbox", name="many (20€) - (Available 1)").check()
    page.get_by_role("checkbox", name="many (20€) - (Available 1)").press("s")
    page.get_by_role("checkbox", name="many (20€) - (Available 1)").press("d")
    page.get_by_role("textbox", name="mandatory (*)").click()
    page.get_by_role("textbox", name="mandatory (*)").fill("aaaa")
    page.get_by_label("rescrited").click()
    expect(page.get_by_label("rescrited")).to_have_value("4")
    page.get_by_text("rescrited descrall all").click()
    page.get_by_role("button", name="Continue").click()
    expect(page.locator("#riepilogo")).to_contain_text("40€")
    page.get_by_role("button", name="Confirm", exact=True).click()
