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
from playwright.sync_api import expect

from larpmanager.tests.utils import fill_tinymce, go_to, login_orga, login_user, logout

pytestmark = pytest.mark.e2e


def test_orga_character_form(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # activate characters
    go_to(page, live_server, "/test/1/manage/features/178/on")

    # activate player editor
    go_to(page, live_server, "/test/1/manage/features/120/on")

    # set config
    go_to(page, live_server, "/test/1/manage/config")
    page.get_by_role("link", name="Player editor ").click()
    page.locator("#id_user_character_max").click()
    page.locator("#id_user_character_max").fill("1")
    page.locator("#id_user_character_approval").check()
    page.get_by_role("link", name="Character form ").click()
    page.locator("#id_character_form_wri_que_max").check()
    page.get_by_role("button", name="Confirm", exact=True).click()

    # create character form
    go_to(page, live_server, "/test/1/manage/characters/form/")

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

    go_to(page, live_server, "/test/1/")
    page.get_by_role("link", name="pinoloooooooooo").click()
    expect(page.locator("#one")).to_contain_text("Player: Admin Test public: public Presentation baba")

    create_second_char(live_server, page)


def create_second_char(live_server, page):
    login_user(page, live_server)
    go_to(page, live_server, "/test/1/register/")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="Access character creation!").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("olivaaaa")

    fill_tinymce(page, "id_teaser", "dsfdfsd")

    fill_tinymce(page, "id_text", "sdfdsfds")
    expect(page.locator("#id_q6")).to_match_aria_snapshot(
        '- combobox:\n  - option "-------" [disabled] [selected]\n  - option "all"\n  - option "few - (Available 1)"'
    )
    page.locator("#id_q6").select_option("2")
    page.locator("#id_q8").click()
    page.locator("#id_q8").click()
    expect(page.locator("#id_q8")).to_match_aria_snapshot(
        '- combobox:\n  - option "-------" [disabled] [selected]\n  - option "only" [disabled]\n  - option "all"'
    )
    expect(page.locator("#id_q7")).to_match_aria_snapshot(
        '- checkbox "all"\n- text: all\n- checkbox "many - (Available 1)"\n- text: many - (Available 1)\n- checkbox "few" [disabled]\n- text: few'
    )
    expect(page.get_by_role("checkbox", name="few")).to_be_disabled()
    page.get_by_role("checkbox", name="many - (Available 1)").check()
    expect(page.locator('[id="id_q7_tr"]')).to_contain_text("options: 1 / 2")
    page.locator("#id_q9").click()
    page.locator("#id_q9").fill("asda")
    page.get_by_role("button", name="Confirm", exact=True).click()
    expect(page.locator("#one")).to_contain_text(
        "Player: User Test Status: Creation available text: few multiple text: many mandatory: asda Presentation dsfdfsd Text sdfdsfds"
    )


def show_chars(page, live_server):
    go_to(page, live_server, "/test/1/manage/config")
    page.get_by_role("link", name=re.compile(r"^Writing")).click()
    page.locator("#id_writing_field_visibility").check()
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/test/1/manage/run")
    for s in range(0, 13):
        page.locator(f"#id_show_character_{s}").check()
    page.get_by_role("button", name="Confirm", exact=True).click()


def check_first_char(page, live_server):
    page.get_by_role("link", name="Change").click()
    expect(page.locator("#id_q4")).to_have_value("aaaaaaaaaa")
    page.get_by_text("bbbbbbbbbb").click()
    expect(page.get_by_text("bbbbbbbbbb")).to_have_value("bbbbbbbbbb")
    expect(page.locator("#id_q6")).to_have_value("1")
    page.locator("#id_q8").click()
    expect(page.locator("#id_q8")).to_have_value("6")
    expect(page.locator("#id_q7")).to_match_aria_snapshot(
        '- checkbox "all" [checked]\n- text: all\n- checkbox "many" [checked]\n- text: many\n- checkbox "few - (Available 1)" [disabled]\n- text: few - (Available 1)'
    )
    expect(page.locator("#id_q9")).to_have_value("fill mandatory")
    expect(page.locator("#id_q12")).to_have_value("public")
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/test/1/manage/characters/")
    page.locator('[id="\\32 "]').get_by_role("link", name="").click()
    page.locator("#id_q4").click()
    page.locator("#id_q4").fill("cccccccccc")
    page.locator("#id_q4").press("Tab")
    page.get_by_text("bbbbbbbbbb").click()
    page.get_by_text("bbbbbbbbbb").fill("dddddddddd")
    page.locator("#id_q6").select_option("2")
    page.locator("#id_q8").select_option("7")
    page.get_by_role("checkbox", name="all").uncheck()
    page.get_by_role("checkbox", name="few").check()
    page.locator("#id_q10").click()
    page.locator("#id_q10").press("Tab")
    page.locator("#id_q10").click()
    page.locator("#id_q10").press("Tab")
    page.locator("#id_q9").click()
    page.locator("#id_q9").press("Tab")
    page.locator("#id_q10").fill("disabled")
    page.locator("#id_q10").press("Tab")
    page.locator("#id_q11").fill("hidden")
    page.locator("#id_status").select_option("a")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.locator('[id="\\32 "]').get_by_role("link", name="").click()
    expect(page.locator("#id_q4")).to_have_value("cccccccccc")
    expect(page.get_by_text("dddddddddd")).to_have_value("dddddddddd")
    expect(page.locator("#id_q6")).to_have_value("2")
    expect(page.locator("#id_q8")).to_have_value("7")
    expect(page.locator("#id_q10")).to_have_value("disabled")
    expect(page.locator("#id_q11")).to_have_value("hidden")
    expect(page.locator("#lbl_id_q4")).to_contain_text("short text")
    page.get_by_role("cell", name="long text").dblclick()
    expect(page.locator("#lbl_id_q5")).to_contain_text("long text")
    expect(page.locator("#main_form")).to_contain_text("short descr")
    page.get_by_text("long descr").click()


def recheck_char(live_server, page):
    expect(page.locator("#main_form")).to_contain_text("long descr")
    expect(page.locator("#lbl_id_q8")).to_contain_text("restricted")
    expect(page.locator("#main_form")).to_contain_text("restricted textonly only descrall all descr")
    expect(page.locator('[id="id_q7_tr"]')).to_contain_text("multiple text")
    expect(page.locator('[id="id_q7_tr"]')).to_contain_text("multiple descrall all descrmany many descrfew few descr")
    page.get_by_role("button", name="Confirm", exact=True).click()
    go_to(page, live_server, "/test/1/character/list")
    page.get_by_role("link", name="").click()
    expect(page.locator("#id_q10")).to_have_value("disabled")
    page.get_by_role("button", name="Confirm", exact=True).click()


def create_first_char(live_server, page):
    go_to(page, live_server, "/test/1/register/")
    page.get_by_role("link", name="Register").click()
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="Access character creation!").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("pinoloooooooooo")

    fill_presentation_text(page)

    expect(page.locator("#lbl_id_text")).to_contain_text("Text (*)")
    expect(page.locator("#lbl_id_teaser")).to_contain_text("Presentation (*)")
    expect(page.locator("#lbl_id_name")).to_contain_text("Name (*)")
    expect(page.locator("#main_form")).to_contain_text("short descr")
    page.locator("#id_q4").click()
    page.locator("#id_q4").fill("aaaaaaaaaa")
    page.locator("#id_q4").click()
    page.get_by_text("long text").click()
    page.locator("#id_q5").click()
    page.locator("#id_q5").fill("bbbbbbbbbb")
    expect(page.locator("#id_q5")).to_have_value("bbbbbbbbbb")
    expect(page.locator("#main_form")).to_contain_text("long descr")
    expect(page.locator("#main_form")).to_contain_text("text length: 10 / 10")
    expect(page.locator("#lbl_id_q6")).to_contain_text("available text")
    expect(page.locator("#main_form")).to_contain_text("available descrall allfew few descr")
    page.locator("#id_q6").select_option("1")
    page.locator("#id_q8").select_option("6")
    expect(page.locator("#lbl_id_q8")).to_contain_text("restricted")
    expect(page.locator("#main_form")).to_contain_text("restricted textonly only descrall all descr")
    page.get_by_text("many - (Available 2)").click()
    page.locator("#id_q7 div").filter(has_text="many - (Available 2)").click()
    expect(page.locator("#id_q7")).to_contain_text("many - (Available 2)")
    expect(page.locator("#id_q7")).to_contain_text("few - (Available 1)")
    page.get_by_text("multiple descrall all").click()
    expect(page.locator('[id="id_q7_tr"]')).to_contain_text("multiple descrall all descrmany many descrfew few descr")
    expect(page.locator('[id="id_q7_tr"]')).to_contain_text("multiple text")
    page.get_by_role("checkbox", name="all").check()
    page.get_by_role("checkbox", name="many - (Available 2)").check()
    page.get_by_text("options: 2 /").click()
    page.locator("#id_q12").click()
    page.locator("#id_q12").fill("public")
    page.locator("#id_q12").press("Tab")
    page.locator("#id_q13").fill("create")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.locator("#id_q9").fill("fill mandatory")
    page.locator("#id_propose").check()
    page.get_by_role("button", name="Confirm", exact=True).click()


def fill_presentation_text(page):
    fill_tinymce(page, "id_teaser", "baba")

    fill_tinymce(page, "id_text", "bebe")


def add_field_special(page):
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("mandatory")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("mandatory descr")
    page.locator("#id_status").select_option("m")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("disabled")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("disabled descr")
    page.locator("#id_status").select_option("d")
    page.get_by_role("button", name="Confirm", exact=True).click()
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
    page.locator("#id_name").fill("public")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("public descr")
    page.locator("#id_visibility").select_option("c")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_typ").press("Tab")
    page.locator("#id_name").fill("only creation")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("only descr")
    page.get_by_role("checkbox", name="Creation").check()
    page.get_by_role("button", name="Confirm", exact=True).click()


def add_field_restricted(page):
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
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("few")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("few descr")
    page.locator("#id_description").press("Tab")
    page.locator("#id_max_available").fill("1")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.locator('[id="\\38 "]').get_by_role("link", name="").click()
    page.locator('[id="\\38 "]').get_by_role("link", name="").click()
    page.get_by_role("link", name="").click()
    page.locator('[id="\\37 "]').get_by_role("link", name="").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("w")
    page.locator("#id_name").press("Home")
    page.locator("#id_name").fill("only")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").press("Home")
    page.locator("#id_description").fill("only descr")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("button", name="Confirm", exact=True).click()


def add_field_multiple(page):
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
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("many")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("many descr")
    page.locator("#id_description").press("Tab")
    page.locator("#id_max_available").fill("2")
    page.get_by_role("button", name="Confirm", exact=True).click()
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
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("button", name="Confirm", exact=True).click()


def add_field_available(page):
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
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("few")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("few descr")
    page.locator("#id_description").press("Tab")
    page.locator("#id_max_available").fill("2")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("button", name="Confirm", exact=True).click()


def add_field_text(page):
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
    page.get_by_role("button", name="Confirm", exact=True).click()
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
    page.get_by_role("button", name="Confirm", exact=True).click()
