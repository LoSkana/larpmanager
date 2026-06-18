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

"""
Test: Registration form with various field types.
Verifies text/paragraph fields, single/multiple choice with pricing and availability,
hidden/disabled fields, mandatory fields, and organizer editing capabilities.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (go_to,
                                     load_image,
                                     login_orga,
                                     login_user,
                                     logout,
                                     submit_confirm,
                                     expect_normalized, new_option, submit_option, get_modal_iframe, save_modal,
                                     )

pytestmark = pytest.mark.e2e


def test_orga_registration_form(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # create form
    go_to(page, live_server, "/test/manage/form/")

    add_text(page)

    add_single(page)

    add_multiple(page)

    add_special(page)

    signup_first(live_server, page)

    signup_check(live_server, page)

    orga_check(live_server, page)

    user_signup(live_server, page)


def add_text(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_typ").select_option("s")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("short text")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("short description")
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_max_length").click()
    edit_iframe.locator("#id_max_length").press("ArrowLeft")
    edit_iframe.locator("#id_max_length").fill("10")
    load_image(edit_iframe, "#id_profile")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("p")
    edit_iframe.locator("#id_typ").press("Tab")
    edit_iframe.locator("#id_name").fill("long text")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("long description")
    edit_iframe.locator("#id_max_length").click()
    edit_iframe.locator("#id_max_length").press("ArrowLeft")
    edit_iframe.locator("#id_max_length").fill("10")
    save_modal(page, edit_iframe)


def add_single(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("choice")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("choice descr")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("free")
    option_row.locator("#id_description").click()
    option_row.locator("#id_description").fill("free")
    option_row.locator("#id_price").click()
    option_row.locator("#id_price").press("ArrowLeft")
    option_row.locator("#id_price").fill("10")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("many")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").fill("many")
    option_row.locator("#id_description").press("Tab")
    option_row.locator("#id_price").press("Tab")
    option_row.locator("#id_price").click()
    option_row.locator("#id_price").press("ArrowLeft")
    option_row.locator("#id_price").fill("20")
    option_row.locator("#id_max_available").click()
    option_row.locator("#id_max_available").fill("2")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("few")
    option_row.locator("#id_description").click()
    option_row.locator("#id_description").fill("few descr")
    option_row.locator("#id_price").click()
    option_row.locator("#id_price").press("ArrowLeft")
    option_row.locator("#id_price").fill("30")
    option_row.locator("#id_price").press("Tab")
    option_row.locator("#id_max_available").fill("1")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("rescrited")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("rescrited descr")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("all")
    option_row.locator("#id_description").click()
    option_row.locator("#id_description").fill("all descr")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("only")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").fill("only")
    option_row.locator("#id_description").press("Tab")
    option_row.locator("#id_price").fill("20")
    option_row.locator("#id_price").press("Tab")
    option_row.locator("#id_max_available").fill("1")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)


def add_multiple(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("m")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("multiple")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("multiple descr")
    edit_iframe.locator("#id_max_length").click()
    edit_iframe.locator("#id_max_length").fill("2")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("all")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").fill("all descr")
    option_row.locator("#id_description").press("Tab")
    option_row.locator("#id_price").fill("10")
    option_row.locator("#id_price").press("Tab")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("many")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").fill("many descr")
    option_row.locator("#id_description").press("Tab")
    option_row.locator("#id_price").fill("20")
    option_row.locator("#id_price").press("Tab")
    option_row.locator("#id_max_available").fill("2")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("few")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").fill("few")
    option_row.locator("#id_description").press("Tab")
    option_row.locator("#id_price").fill("30")
    option_row.locator("#id_price").press("Tab")
    option_row.locator("#id_max_available").fill("1")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)


def add_special(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_typ").press("Tab")
    edit_iframe.locator("#id_name").fill("hidden")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("hidden descr")
    edit_iframe.locator("#id_status").select_option("h")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_typ").press("Tab")
    edit_iframe.locator("#id_name").fill("disabled")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("disabled text")
    edit_iframe.locator("#id_status").select_option("d")
    save_modal(page, edit_iframe)


def signup_first(live_server: Any, page: Any) -> None:
    # sign up as first user
    go_to(page, live_server, "/test/register")
    page.get_by_role("textbox", name="short text").click()
    page.get_by_role("textbox", name="short text").fill("aaaaaaaaaa")
    expect(page.get_by_role("textbox", name="short text")).to_have_value("aaaaaaaaaa")
    page.get_by_role("textbox", name="long text").click()
    page.get_by_role("textbox", name="long text").press("CapsLock")
    page.get_by_role("textbox", name="long text").fill("BBBBBBBBBB")
    expect(page.get_by_role("textbox", name="long text")).to_have_value("BBBBBBBBBB")
    page.get_by_label("choice").select_option("u2")
    page.get_by_label("rescrited").select_option("u5")
    expect_normalized(page, page.locator("#id_que_u6"), "many (20€) - (Available 2)")
    expect_normalized(page, page.locator("#id_que_u6"), "few (30€) - (Available 1)")
    page.get_by_role("checkbox", name="many (20€) - (Available 2)").check()
    page.get_by_role("checkbox", name="few (30€) - (Available 1)").check()
    expect(page.get_by_role("checkbox", name="all (10€)")).to_be_disabled()
    expect(page.get_by_role("textbox", name="disabled")).to_have_count(0)
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)
    # add mandatory
    go_to(page, live_server, "/test/manage/form/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_typ").press("Tab")
    edit_iframe.locator("#id_name").fill("")
    edit_iframe.locator("#id_name").press("CapsLock")
    edit_iframe.locator("#id_name").fill("mandatory")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("mandatory text")
    edit_iframe.locator("#id_status").select_option("m")
    save_modal(page, edit_iframe)


def signup_check(live_server: Any, page: Any) -> None:
    # check values
    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#register_form"), "short description")
    expect(page.get_by_role("textbox", name="short text")).to_have_value("aaaaaaaaaa")
    expect_normalized(page, page.locator("#register_form"), "long description")
    expect_normalized(page, page.locator("#register_form"), "text length: 10 / 10")
    expect(page.get_by_role("textbox", name="long text")).to_have_value("BBBBBBBBBB")
    expect(page.get_by_label("choice")).to_have_value("u2")
    expect_normalized(page, page.locator("#register_form"), "choice descr free free many many few few descr")
    expect(page.get_by_label("rescrited")).to_have_value("u5")
    expect_normalized(page, page.locator("#register_form"), "rescrited descr all all descr only only")
    expect(page.get_by_role("checkbox", name="all (10€)")).not_to_be_checked()
    expect(page.get_by_role("checkbox", name="many (20€)")).to_be_checked()
    expect(page.get_by_role("checkbox", name="few (30€)")).to_be_checked()
    page.get_by_role("checkbox", name="few (30€)").uncheck()
    page.get_by_role("checkbox", name="few (30€)").check()
    expect(page.get_by_role("checkbox", name="few (30€)")).to_be_checked()
    page.get_by_text("multiple descrall all").click()
    page.get_by_text("many many descr").click()
    expect_normalized(page, page.locator("#register_form"), "multiple descr all all descr many many descr few few")
    expect_normalized(page, page.locator("#register_form"), "options: 2 / 2")
    expect_normalized(page, page.locator("#register_form"), "mandatory (*)")
    page.get_by_role("button", name="Continue").click()
    expect_normalized(page, page.locator("#register_form"), "Please select a value")
    expect_normalized(page, page.locator("#register_form"), "mandatory text")
    page.get_by_role("textbox", name="mandatory (*)").click()
    page.get_by_role("textbox", name="mandatory (*)").fill("ggggg")
    page.get_by_role("button", name="Continue").click()
    expect_normalized(page, page.locator("#riepilogo"), "Your updated registration total is: 90€.")
    submit_confirm(page)


def orga_check(live_server: Any, page: Any) -> None:
    # check signups
    go_to(page, live_server, "/test/manage/registrations/")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect(edit_iframe.locator("#id_que_u2")).to_have_value("aaaaaaaaaa")
    expect(edit_iframe.get_by_text("BBBBBBBBBB")).to_have_value("BBBBBBBBBB")
    expect(edit_iframe.locator("#id_que_u4")).to_have_value("u2")
    expect(edit_iframe.locator("#id_que_u5")).to_have_value("u5")
    expect(edit_iframe.get_by_role("checkbox", name="all (10€)")).not_to_be_checked()
    expect(edit_iframe.get_by_role("checkbox", name="many (20€)")).to_be_checked()
    expect(edit_iframe.get_by_role("checkbox", name="few (30€)")).to_be_checked()
    edit_iframe.locator("#id_que_u7").click()
    expect_normalized(page, edit_iframe.locator("#lbl_id_que_u7"), "hidden")
    edit_iframe.locator("#id_que_u7").click()
    edit_iframe.locator("#id_que_u7").fill("dsadsadsa")
    expect_normalized(page, edit_iframe.locator("#main_form"), "hidden descr")
    edit_iframe.locator("#id_que_u8").click()
    edit_iframe.locator("#id_que_u8").fill("asdsadsa")
    expect(edit_iframe.locator("#id_que_u9")).to_have_value("ggggg")
    save_modal(page, edit_iframe)
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect(edit_iframe.locator("#id_que_u7")).to_have_value("dsadsadsa")
    expect(edit_iframe.locator("#id_que_u8")).to_have_value("asdsadsa")

    # orga removes a multiple choice selection
    page.get_by_role("checkbox", name="many (20€)").uncheck()
    submit_confirm(page)
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect(edit_iframe.get_by_role("checkbox", name="many (20€)")).not_to_be_checked()
    expect(edit_iframe.get_by_role("checkbox", name="few (30€)")).to_be_checked()
    # orga removes all multiple choice selections
    edit_iframe.get_by_role("checkbox", name="few (30€)").uncheck()
    save_modal(page, edit_iframe)

    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect(edit_iframe.get_by_role("checkbox", name="all (10€)")).not_to_be_checked()
    expect(edit_iframe.get_by_role("checkbox", name="many (20€)")).not_to_be_checked()
    expect(edit_iframe.get_by_role("checkbox", name="few (30€)")).not_to_be_checked()


def user_signup(live_server: Any, page: Any) -> None:
    # signup as user
    logout(page)
    login_user(page, live_server)
    expect_normalized(page, page.locator("#one"), "Hurry: only 9 tickets available.")
    go_to(page, live_server, "/test/register/")
    page.get_by_label("choice").select_option("u2")
    expect(page.get_by_label("choice")).to_have_value("u2")
    page.get_by_label("rescrited").select_option("u4")
    expect(page.get_by_label("rescrited")).to_have_value("u4")
    expect(page.get_by_label("rescrited")).to_match_aria_snapshot(
        '- combobox "rescrited":\n  - option "all" [selected]\n  - option /only \\(\\d+€\\)/ [disabled]'
    )
    expect(page.get_by_role("checkbox", name="few (30€)")).not_to_be_checked()
    page.get_by_role("checkbox", name="many (20€)").check()
    page.get_by_role("textbox", name="mandatory (*)").click()
    page.get_by_role("textbox", name="mandatory (*)").fill("aaaa")
    page.get_by_label("rescrited").click()
    expect(page.get_by_label("rescrited")).to_have_value("u4")
    page.get_by_text("rescrited descrall all").click()
    page.get_by_role("button", name="Continue").click()
    expect_normalized(page, page.locator("#riepilogo"), "40€")
    submit_confirm(page)

    # user removes all multiple choice selections
    go_to(page, live_server, "/test/register/")
    expect(page.get_by_role("checkbox", name="many (20€)")).to_be_checked()
    page.get_by_role("checkbox", name="many (20€)").uncheck()
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)
    go_to(page, live_server, "/test/register/")
    expect(page.get_by_role("checkbox", name="all (10€)")).not_to_be_checked()
    expect(page.get_by_role("checkbox", name="many (20€)")).not_to_be_checked()
    expect(page.get_by_role("checkbox", name="few (30€)")).not_to_be_checked()
