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
    expect_normalized,
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
    page.get_by_role("link", name="Player editor ").click()
    page.locator("#id_user_character_max").click()
    page.locator("#id_user_character_max").fill("1")
    page.locator("#id_user_character_approval").check()
    page.get_by_role("link", name="Character form ").click()
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
        '- combobox:\n  - option "-------" [disabled] [selected]\n  - option "all"\n  - option "few - (Available 1)"'
    )
    page.locator("#id_que_u6").select_option("u2")
    page.locator("#id_que_u8").click()
    page.locator("#id_que_u8").click()
    expect(page.locator("#id_que_u8")).to_match_aria_snapshot(
        '- combobox:\n  - option "-------" [disabled] [selected]\n  - option "only" [disabled]\n  - option "all"'
    )
    expect(page.locator("#id_que_u7")).to_match_aria_snapshot(
        '- checkbox "all"\n- text: all\n- checkbox "many - (Available 1)"\n- text: many - (Available 1)\n- checkbox "few" [disabled]\n- text: few'
    )
    expect(page.get_by_role("checkbox", name="few")).to_be_disabled()
    page.get_by_role("checkbox", name="many - (Available 1)").check()
    expect_normalized(page, page.locator('[id="id_que_u7_tr"]'), "options: 1 / 2")
    page.locator("#id_que_u9").click()
    page.locator("#id_que_u9").fill("asda")
    submit_confirm(page)
    expect_normalized(page,
        page.locator("#one"),
        "Player: User Test Status: Creation available text: few multiple text: many mandatory: asda Presentation dsfdfsd Text sdfdsfds",
    )


def show_chars(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Writing")).click()
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
    expect(page.locator("#id_que_u6")).to_have_value("u1")
    page.locator("#id_que_u8").click()
    expect(page.locator("#id_que_u8")).to_have_value("u6")
    expect(page.locator("#id_que_u7")).to_match_aria_snapshot(
        '- checkbox "all" [checked]\n- text: all\n- checkbox "many" [checked]\n- text: many\n- checkbox "few - (Available 1)" [disabled]\n- text: few - (Available 1)'
    )
    expect(page.locator("#id_que_u9")).to_have_value("fill mandatory")
    expect(page.locator("#id_que_u12")).to_have_value("public")
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/characters/")
    page.locator('[id="u2"]').get_by_role("link", name="").click()
    page.locator("#id_que_u4").click()
    page.locator("#id_que_u4").fill("cccccccccc")
    page.locator("#id_que_u4").press("Tab")
    page.get_by_text("bbbbbbbbbb").click()
    page.get_by_text("bbbbbbbbbb").fill("dddddddddd")
    page.locator("#id_que_u6").select_option("u2")
    page.locator("#id_que_u8").select_option("u7")
    page.get_by_role("checkbox", name="all").uncheck()
    page.get_by_role("checkbox", name="few").check()
    page.locator("#id_que_u10").fill("disabled")
    page.locator("#id_que_u11").fill("hidden")
    page.locator("#id_status").select_option("a")
    submit_confirm(page)
    page.locator('[id="u2"]').get_by_role("link", name="").click()
    expect(page.locator("#id_que_u4")).to_have_value("cccccccccc")
    expect(page.get_by_text("dddddddddd")).to_have_value("dddddddddd")
    expect(page.locator("#id_que_u6")).to_have_value("u2")
    expect(page.locator("#id_que_u8")).to_have_value("u7")
    expect(page.locator("#id_que_u10")).to_have_value("disabled")
    expect(page.locator("#id_que_u11")).to_have_value("hidden")
    expect_normalized(page, page.locator("#lbl_id_que_u4"), "short text")
    page.get_by_role("cell", name="long text").dblclick()
    expect_normalized(page, page.locator("#lbl_id_que_u5"), "long text")
    expect_normalized(page, page.locator("#main_form"), "short descr")
    page.get_by_text("long descr").click()


def recheck_char(live_server: Any, page: Any) -> None:
    expect_normalized(page, page.locator("#main_form"), "long descr")
    expect_normalized(page, page.locator("#lbl_id_que_u8"), "restricted")
    expect_normalized(page, page.locator("#main_form"), "restricted text only only descr all all descr")
    expect_normalized(page, page.locator('[id="id_que_u7_tr"]'), "multiple text")
    expect_normalized(page,
        page.locator('[id="id_que_u7_tr"]'), "multiple descr all all descr many many descr few few descr"
    )
    submit_confirm(page)
    go_to(page, live_server, "/test/character/list")
    page.get_by_role("link", name="").click()
    expect(page.locator("#id_que_u10")).to_have_value("disabled")
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
    expect_normalized(page, page.locator("#main_form"), "text length: 10 / 10")
    expect_normalized(page, page.locator("#lbl_id_que_u6"), "available text")
    expect_normalized(page, page.locator("#main_form"), "available descr all all few few descr")
    page.locator("#id_que_u6").select_option("u1")
    page.locator("#id_que_u8").select_option("u6")
    expect_normalized(page, page.locator("#lbl_id_que_u8"), "restricted")
    expect_normalized(page, page.locator("#main_form"), "restricted text only only descr all all descr")
    page.get_by_text("many - (Available 2)").click()
    page.locator("#id_que_u7 div").filter(has_text="many - (Available 2)").click()
    expect_normalized(page, page.locator("#id_que_u7"), "many - (Available 2)")
    expect_normalized(page, page.locator("#id_que_u7"), "few - (Available 1)")
    expect_normalized(page,
        page.locator('[id="id_que_u7_tr"]'), "multiple descr all all descr many many descr few few descr"
    )
    expect_normalized(page, page.locator('[id="id_que_u7_tr"]'), "multiple text")
    page.get_by_role("checkbox", name="all").check()
    page.get_by_role("checkbox", name="many - (Available 2)").check()
    page.get_by_text("options: 2 /").click()
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
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("mandatory")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("mandatory descr")
    page.locator("#id_status").select_option("m")
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("disabled")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("disabled descr")
    page.locator("#id_status").select_option("d")
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("hidden")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("hidden descr")
    page.locator("#id_status").select_option("h")
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("public")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("public descr")
    page.locator("#id_visibility").select_option("c")
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("only creation")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("only descr")
    page.get_by_role("checkbox", name="Creation").check()
    submit_confirm(page)


def add_field_restricted(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("restricted")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("restricted text")

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("all")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("all descr")
    page.locator("#id_description").press("Tab")
    submit_confirm(page)

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("few")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("few descr")
    page.locator("#id_description").press("Tab")
    page.locator("#id_max_available").fill("1")
    submit_confirm(page)

    submit_confirm(page)

    page.locator('[id="u8"]').get_by_role("link", name="").click()
    page.locator('[id="u8"]').get_by_role("link", name="").click()
    page.get_by_role("link", name="").click()

    page.locator('[id="u7"]').get_by_role("link", name="").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("w")
    page.locator("#id_name").press("Home")
    page.locator("#id_name").fill("only")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").press("Home")
    page.locator("#id_description").fill("only descr")
    submit_confirm(page)

    submit_confirm(page)


def add_field_multiple(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("m")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("multiple text")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("multiple descr")
    page.locator("#id_max_length").click()
    page.locator("#id_max_length").fill("2")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("all")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("all descr")
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("many")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("many descr")
    page.locator("#id_description").press("Tab")
    page.locator("#id_max_available").fill("2")
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("few")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("few")
    page.locator("#id_description").press("Tab")
    page.locator("#id_description").click()
    page.locator("#id_description").press("ArrowRight")
    page.locator("#id_description").fill("few descr")
    page.locator("#id_description").press("Tab")
    page.locator("#id_max_available").fill("1")
    submit_confirm(page)
    submit_confirm(page)


def add_field_available(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("available text")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("available descr")
    page.locator("#id_description").press("Tab")
    page.locator("#id_status").press("Tab")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("all")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("all")
    page.locator("#id_description").press("Tab")
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("few")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("few descr")
    page.locator("#id_description").press("Tab")
    page.locator("#id_max_available").fill("2")
    submit_confirm(page)
    submit_confirm(page)


def add_field_text(page: Any) -> None:
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("short text")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("short descr")
    page.locator("#id_description").press("Tab")
    page.locator("#id_max_length").click()
    page.locator("#id_max_length").press("ArrowLeft")
    page.locator("#id_max_length").fill("10")
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("p")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("long text")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("long descr")
    page.locator("#id_description").press("Tab")
    page.locator("#id_status").press("Tab")
    page.locator("#id_visibility").press("Tab")
    page.get_by_role("checkbox", name="Creation").press("Tab")
    page.get_by_role("checkbox", name="Proposed").press("Tab")
    page.get_by_role("checkbox", name="Revision").press("Tab")
    page.get_by_role("checkbox", name="Approved").press("Tab")
    page.locator("#id_max_length").fill("10")
    submit_confirm(page)
