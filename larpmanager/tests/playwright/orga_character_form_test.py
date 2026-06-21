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
Test: Character form creation with complex field types and player editor.
Verifies text/paragraph fields, single/multiple choice with availability limits,
restricted/mandatory/hidden/disabled fields, character creation/approval workflow, and field visibility.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (just_wait,
                                     fill_tinymce,
                                     go_to,
                                     login_orga,
                                     login_user,
                                     logout,
                                     submit_confirm,
                                     expect_normalized, new_option, submit_option, get_option,
                                     get_modal_iframe, save_modal, _wait_lm_ready,
                                     )

pytestmark = pytest.mark.e2e


def test_orga_character_form(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # activate characters
    go_to(page, live_server, "/test/manage/features/character/on")

    # activate player editor
    go_to(page, live_server, "/test/manage/features/user_character/on")

    # set config
    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Player editor ")).click()
    page.locator("#id_user_character_max").click()
    page.locator("#id_user_character_max").fill("1")
    page.locator("#id_user_character_approval").check()
    page.get_by_role("link", name=re.compile(r"^Character Sheet")).click()
    page.locator("#id_character_form_wri_que_max").check()
    submit_confirm(page)

    # create character form
    go_to(page, live_server, "/test/manage/writing/form/")

    add_field_text(page)

    add_field_available(page)

    add_field_multiple(page)

    add_field_restricted(page)

    add_field_special(page)

    create_first_char(live_server, page)

    check_first_char(page, live_server)

    recheck_char(live_server, page)

    show_chars(page, live_server)

    logout(page)

    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="pinoloooooooooo").click()
    expect_normalized(page, page.locator("#one"), "Player: Admin Test public: public Presentation baba")

    create_second_char(live_server, page)


def create_second_char(live_server: Any, page: Any) -> None:
    login_user(page, live_server)
    go_to(page, live_server, "/test/register/")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    go_to(page, live_server, "/test/register/")
    page.get_by_role("link", name="Create your character!").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("olivaaaa")

    fill_tinymce(page, "id_teaser", "dsfdfsd")

    fill_tinymce(page, "id_text", "sdfdsfds")
    expect(page.locator("#id_que_u6")).to_match_aria_snapshot(
        '- radio /all.*/\n- radio /few.*/'
    )
    page.locator("#id_que_u6_0").click(force=True)
    expect(page.locator("#id_que_u8")).to_match_aria_snapshot(
        '- radio /only.*/\n- radio /all.*/'
    )
    expect(page.locator("#id_que_u7")).to_match_aria_snapshot("""
      - checkbox "all all descr"
      - text: all all descr
      - checkbox "many many descr 1 available"
      - text: many many descr 1 available
      - checkbox "few few descr" [disabled]
      - text: few few descr
    """)
    expect(page.locator("#id_que_u7_2")).to_be_disabled()
    page.locator("#id_que_u7_1").check(force=True)
    expect_normalized(page, page.locator('[id="id_que_u7_tr"]'), "options: 1 / 2")
    page.locator("#id_que_u9").click()
    page.locator("#id_que_u9").fill("asda")
    submit_confirm(page)
    expect_normalized(page,
        page.locator("#one"),
        "player: user test status: creation available text: all multiple text: many mandatory: asda presentation dsfdfsd text sdfdsfds",
    )


def show_chars(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Characters")).click()
    page.locator("#id_writing_field_visibility").check()
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/run")
    for s in range(0, 13):
        page.locator(f"#id_show_character_{s}").check()
    submit_confirm(page)


def check_first_char(page: Any, live_server: Any) -> None:
    page.get_by_role("link", name="Edit").click()
    expect(page.locator("#id_que_u4")).to_have_value("aaaaaaaaaa")
    page.get_by_text("bbbbbbbbbb").click()
    expect(page.get_by_text("bbbbbbbbbb")).to_have_value("bbbbbbbbbb")
    expect(page.locator('input[name="que_u6"]:checked')).to_have_value("u1")
    expect(page.locator('input[name="que_u8"]:checked')).to_have_value("u6")
    expect(page.locator("#id_que_u7")).to_match_aria_snapshot(
        '- checkbox /all.*/ [checked]\n- checkbox /many.*/ [checked]'
    )
    expect(page.locator("#id_que_u9")).to_have_value("fill mandatory")
    expect(page.locator("#id_que_u12")).to_have_value("public")
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/characters/")
    page.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_que_u4").click()
    edit_iframe.locator("#id_que_u4").fill("cccccccccc")
    edit_iframe.locator("#id_que_u4").press("Tab")
    edit_iframe.get_by_text("bbbbbbbbbb").click()
    edit_iframe.get_by_text("bbbbbbbbbb").fill("dddddddddd")
    edit_iframe.locator('#id_que_u6_1').click(force=True)
    edit_iframe.locator('#id_que_u8_0').click(force=True)
    edit_iframe.locator("#id_que_u7_0").uncheck(force=True)
    edit_iframe.locator("#id_que_u7_2").check(force=True)
    edit_iframe.locator("#id_que_u10").fill("disabled")
    edit_iframe.locator("#id_que_u11").fill("hidden")
    edit_iframe.locator("#id_status").select_option("a")
    save_modal(page, edit_iframe)

    edit_iframe.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect(edit_iframe.locator("#id_que_u4")).to_have_value("cccccccccc")
    expect(edit_iframe.get_by_text("dddddddddd")).to_have_value("dddddddddd")
    expect(edit_iframe.locator('input[name="que_u6"]:checked')).to_have_value("u2")
    expect(edit_iframe.locator('input[name="que_u8"]:checked')).to_have_value("u7")
    expect_normalized(edit_iframe, edit_iframe.locator("#lbl_id_que_u4"), "short text")
    edit_iframe.get_by_role("cell", name="long text").dblclick()
    expect_normalized(edit_iframe, edit_iframe.locator("#lbl_id_que_u5"), "long text")
    expect_normalized(edit_iframe, edit_iframe.locator("#main_form"), "short descr")
    edit_iframe.get_by_text("long descr").click()
    save_modal(page, edit_iframe)

def recheck_char(live_server: Any, page: Any) -> None:
    edit_iframe = get_modal_iframe(page)
    expect_normalized(page, edit_iframe.locator("#main_form"), "long descr")
    expect_normalized(page, edit_iframe.locator("#lbl_id_que_u8"), "restricted")
    expect_normalized(page, edit_iframe.locator("#main_form"), "only only descr all all descr restricted text")
    expect_normalized(page, edit_iframe.locator('[id="id_que_u7_tr"]'), "multiple text")
    expect_normalized(page,
        page.locator('[id="id_que_u7_tr"]'), "all all descr many many descr few few descr multiple descr"
    )
    save_modal(page, edit_iframe)
    go_to(page, live_server, "/test/character/list")
    page.locator(".fa-edit").click()
    expect(page.locator("#id_que_u10")).to_have_count(0)
    expect_normalized(page, page.locator("#id_que_u10_tr"), "disabled")
    expect(page.locator("#id_que_u11")).to_have_count(0)
    expect(page.locator("#one")).not_to_contain_text("Hidden")
    submit_confirm(page)


def create_first_char(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/register/")
    page.get_by_role("link", name="Register").click()
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    go_to(page, live_server, "/test/register/")
    page.get_by_role("link", name="Create your character!").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("pinoloooooooooo")

    fill_presentation_text(page)

    expect_normalized(page, page.locator("#lbl_id_text"), "Text (*)")
    expect_normalized(page, page.locator("#lbl_id_teaser"), "Presentation (*)")
    expect_normalized(page, page.locator("#lbl_id_name"), "Name (*)")
    expect_normalized(page, page.locator("#main_form"), "short descr")
    page.locator("#id_que_u4").click()
    page.locator("#id_que_u4").fill("aaaaaaaaaa")
    page.locator("#id_que_u4").click()
    page.get_by_text("long text").click()
    page.locator("#id_que_u5").click()
    page.locator("#id_que_u5").fill("bbbbbbbbbb")
    expect(page.locator("#id_que_u5")).to_have_value("bbbbbbbbbb")
    expect_normalized(page, page.locator("#main_form"), "long descr")
    expect_normalized(page, page.locator("#lbl_id_que_u6"), "available text")
    expect_normalized(page, page.locator("#main_form"), "available text all all few few descr 2 available available descr")
    page.locator("#id_que_u6_0").click(force=True)
    page.locator("#id_que_u8_1").click(force=True)
    expect_normalized(page, page.locator("#lbl_id_que_u8"), "restricted")
    expect_normalized(page, page.locator("#main_form"), "restricted only only descr 1 available all all descr restricted text")
    page.locator("#id_que_u7_1").click(force=True)
    expect_normalized(page,
        page.locator('[id="id_que_u7_tr"]'), "multiple text all all descr many many descr 2 available few few descr 1 available multiple descr options: 1 / 2"
    )
    expect_normalized(page, page.locator('[id="id_que_u7_tr"]'), "multiple text")
    page.locator("#id_que_u7_0").check(force=True)
    page.locator("#id_que_u12").click()
    page.locator("#id_que_u12").fill("public")
    page.locator("#id_que_u12").press("Tab")
    page.locator("#id_que_u13").fill("create")
    submit_confirm(page)
    page.locator("#id_que_u9").fill("fill mandatory")
    page.locator("#id_propose").check()
    submit_confirm(page)


def fill_presentation_text(page: Any) -> None:
    fill_tinymce(page, "id_teaser", "baba")

    fill_tinymce(page, "id_text", "bebe")


def add_field_special(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_typ").press("Tab")
    edit_iframe.locator("#id_name").fill("mandatory")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("mandatory descr")
    edit_iframe.locator("#id_status").select_option("m")
    save_modal(page, edit_iframe)
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_typ").press("Tab")
    edit_iframe.locator("#id_name").fill("disabled")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("disabled descr")
    edit_iframe.locator("#id_status").select_option("d")
    save_modal(page, edit_iframe)
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
    edit_iframe.locator("#id_name").fill("public")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("public descr")
    edit_iframe.locator("#id_visibility").select_option("c")
    save_modal(page, edit_iframe)
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_typ").press("Tab")
    edit_iframe.locator("#id_name").fill("only creation")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("only descr")
    edit_iframe.get_by_role("checkbox", name="Creation").check()
    save_modal(page, edit_iframe)


def add_field_restricted(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("restricted")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("restricted text")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("all")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").fill("all descr")
    option_row.locator("#id_description").press("Tab")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("few")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").fill("few descr")
    option_row.locator("#id_description").press("Tab")
    option_row.locator("#id_max_available").fill("1")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)

    page.locator('tr[id="u8"] td.reorder-handle').drag_to(
        page.locator('tr[id="u8"]').locator("xpath=preceding-sibling::tr[1]")
    )
    page.wait_for_timeout(300)
    page.locator('[id="u8"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)

    opts = edit_iframe.locator("#inline-options .inline-option")
    opts.nth(1).locator("td.reorder-handle").drag_to(opts.nth(0))
    just_wait(page)
    option_row = get_option(edit_iframe, "u7")
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("w")
    option_row.locator("#id_name").press("Home")
    option_row.locator("#id_name").fill("only")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").press("Home")
    option_row.locator("#id_description").fill("only descr")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)


def add_field_multiple(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("m")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("multiple text")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("multiple descr")
    edit_iframe.locator("#id_max_length").click()
    edit_iframe.locator("#id_max_length").fill("2")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("all")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").fill("all descr")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("many")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").fill("many descr")
    option_row.locator("#id_description").press("Tab")
    option_row.locator("#id_max_available").fill("2")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("few")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").fill("few")
    option_row.locator("#id_description").press("Tab")
    option_row.locator("#id_description").click()
    option_row.locator("#id_description").press("ArrowRight")
    option_row.locator("#id_description").fill("few descr")
    option_row.locator("#id_description").press("Tab")
    option_row.locator("#id_max_available").fill("1")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)


def add_field_available(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("available text")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("available descr")
    edit_iframe.locator("#id_description").press("Tab")
    edit_iframe.locator("#id_status").press("Tab")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("all")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").fill("all")
    option_row.locator("#id_description").press("Tab")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("few")
    option_row.locator("#id_name").press("Tab")
    option_row.locator("#id_description").fill("few descr")
    option_row.locator("#id_description").press("Tab")
    option_row.locator("#id_max_available").fill("2")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)


def add_field_text(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_typ").press("Tab")
    edit_iframe.locator("#id_name").fill("short text")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("short descr")
    edit_iframe.locator("#id_description").press("Tab")
    edit_iframe.locator("#id_max_length").click()
    edit_iframe.locator("#id_max_length").press("ArrowLeft")
    edit_iframe.locator("#id_max_length").fill("10")
    save_modal(page, edit_iframe)
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("p")
    edit_iframe.locator("#id_typ").press("Tab")
    edit_iframe.locator("#id_name").fill("long text")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("long descr")
    edit_iframe.locator("#id_description").press("Tab")
    edit_iframe.locator("#id_status").press("Tab")
    edit_iframe.locator("#id_visibility").press("Tab")
    edit_iframe.get_by_role("checkbox", name="Creation").press("Tab")
    edit_iframe.get_by_role("checkbox", name="Proposed").press("Tab")
    edit_iframe.get_by_role("checkbox", name="Revision").press("Tab")
    edit_iframe.get_by_role("checkbox", name="Approved").press("Tab")
    edit_iframe.locator("#id_max_length").fill("10")
    save_modal(page, edit_iframe)
