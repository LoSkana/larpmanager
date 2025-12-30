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
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import expect_normalized, fill_tinymce, go_to, login_orga, submit_confirm

pytestmark = pytest.mark.e2e


def test_px(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    setup(live_server, page)

    ability(live_server, page)

    delivery(live_server, page)

    rules(page)

    player_choice_undo(page, live_server)

    modifiers(page, live_server)


def setup(live_server: Any, page: Any) -> None:
    # activate features
    go_to(page, live_server, "/test/manage")
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Player editor").check()
    page.get_by_role("checkbox", name="Experience points").check()
    page.get_by_role("checkbox", name="Characters").check()
    submit_confirm(page)

    # configure test larp
    go_to(page, live_server, "/test/manage/config/")
    page.get_by_role("link", name=re.compile(r"^Experience points\s.+")).click()
    page.locator("#id_px_start").click()
    page.locator("#id_px_start").fill("10")
    page.locator("#id_px_undo").click()
    page.locator("#id_px_undo").fill("2")
    page.locator("#id_px_user").check()
    page.locator("#id_px_templates").check()
    page.locator("#id_px_rules").check()
    page.locator("#id_px_modifiers").check()

    page.get_by_role("link", name=re.compile(r"^Player editor\s.+")).click()
    page.locator("#id_user_character_max").click()
    page.locator("#id_user_character_max").fill("1")
    submit_confirm(page)

    # create computed field
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("c")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Hit Point")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("sasad")
    page.locator("#id_name").click()
    submit_confirm(page)

    # create class field
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Class")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Mage")
    page.locator("#main_form div").filter(has_text="After confirmation, add").click()
    submit_confirm(page)
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Rogue")
    page.get_by_role("checkbox", name="After confirmation, add").check()
    submit_confirm(page)
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Cleric")
    submit_confirm(page)
    submit_confirm(page)


def ability(live_server: Any, page: Any) -> None:
    # set up xp
    go_to(page, live_server, "/test/manage/px/ability_types/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("base ability")
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/px/abilities/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("standard")
    page.locator("#id_cost").click()
    page.locator("#id_name").dblclick()
    page.locator("#id_name").fill("sword1")
    page.locator("#id_cost").click()
    page.locator("#id_cost").fill("1")
    fill_tinymce(page, "id_descr", "sdsfdsfds", False)
    submit_confirm(page)

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("double shield")
    page.locator("#id_cost").click()
    page.locator("#id_cost").fill("2")
    row = page.get_by_role("row", name="Pre-requisites")
    row.get_by_role("searchbox").click()
    row.get_by_role("searchbox").fill("swo")
    page.locator(".select2-results__option").first.click()
    submit_confirm(page)

    page.get_by_role("link", name="Ability Template").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("test_template")
    page.locator('iframe[title="Rich Text Area"]').content_frame.locator("html").click()
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_label("Rich Text Area").fill(
        "This text should show"
    )
    submit_confirm(page)
    page.get_by_role("link", name="Ability", exact=True).click()
    page.locator("[id='u2']").get_by_role("link", name="").click()
    page.get_by_text("---------").click()
    page.get_by_role("searchbox").nth(3).fill("test_template")
    page.get_by_role("option", name="test_template").click()
    submit_confirm(page)
    page.get_by_role("link", name="Ability", exact=True).click()
    page.get_by_role("cell", name="This text should show").click()


def delivery(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/manage/px/deliveries/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("first live")
    page.locator("#id_name").press("Tab")
    page.locator("#id_amount").fill("2")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="#1 Test Character").click()
    submit_confirm(page)

    # check px computation
    go_to(page, live_server, "/test/manage/characters/")
    page.get_by_role("link", name="XP").click()
    expect_normalized(page, page.locator('[id="u1"]'), "12")
    expect_normalized(page, page.locator('[id="u1"]'), "12")
    expect_normalized(page, page.locator('[id="u1"]'), "0")
    page.get_by_role("link", name="").click()
    page.wait_for_load_state("load")
    page.wait_for_timeout(2000)
    row = page.get_by_role("row", name="Abilities Show")
    row.get_by_role("link").click()
    row.get_by_role("searchbox").click()
    row.get_by_role("searchbox").fill("swo")
    page.locator(".select2-results__option").first.click()
    submit_confirm(page)
    page.get_by_role("link", name="XP").click()
    expect_normalized(page, page.locator('[id="u1"]'), "11")
    expect_normalized(page, page.locator('[id="u1"]'), "12")
    expect_normalized(page, page.locator('[id="u1"]'), "1")


def rules(page: Any) -> None:
    # create first rule - for everyone
    page.get_by_role("link", name="Rules").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_field").select_option("4")
    page.locator("#id_amount").click()
    page.locator("#id_amount").fill("2")
    page.get_by_role("checkbox", name="After confirmation, add").check()
    submit_confirm(page)
    page.get_by_role("searchbox").click()

    # create second rule - only for sword
    page.get_by_role("searchbox").fill("swor")
    page.locator(".select2-results__option").first.click()
    page.locator("#id_field").select_option("4")
    page.locator("#id_operation").select_option("MUL")
    page.locator("#id_amount").click()
    page.locator("#id_amount").fill("3")
    submit_confirm(page)

    # check value
    page.get_by_role("link", name="Characters").click()
    page.get_by_role("link", name="Hit Point").click()
    expect_normalized(page, page.locator("#one"), "#1 Test Character Test Teaser Test Text 6")

    # remove ability
    page.get_by_role("link", name="").click()
    page.get_by_role("row", name="Abilities Show").get_by_role("link").click()
    page.get_by_role("listitem", name="sword1").locator("span").click()
    submit_confirm(page)

    # recheck value
    page.get_by_role("link", name="Hit Point").click()
    page.wait_for_timeout(2000)
    expect_normalized(page, page.locator("#one"), "#1 Test Character Test Teaser Test Text 2")

    # readd ability
    page.get_by_role("link", name="").click()
    page.wait_for_load_state("load")
    page.wait_for_timeout(2000)
    row = page.get_by_role("row", name="Abilities Show")
    row.get_by_role("link").click()
    row.get_by_role("searchbox").click()
    row.get_by_role("searchbox").fill("swo")
    page.locator(".select2-results__option").first.click()
    submit_confirm(page)


def player_choice_undo(page: Any, live_server: Any) -> None:
    # signup
    go_to(page, live_server, "/")
    page.get_by_role("link", name="Registration is open!").click()
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Assign char
    go_to(page, live_server, "/test/manage")
    page.get_by_role("link", name="Registrations", exact=True).click()
    page.get_by_role("link", name="").click()
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="#1 Test Character").click()
    submit_confirm(page)

    # choose
    go_to(page, live_server, "/test")
    page.locator("a").filter(has_text=re.compile(r"^Test Character$")).click()
    page.get_by_role("link", name="Ability").click()
    expect_normalized(page,
        page.locator("#one"),
        "Experience points Total Used Available 12 1 11 Abilities base ability sword1 (1) sdsfdsfds Deliveries first live (2) Obtain ability Select the new ability to get base ability --- Select abilitydouble shield - 2",
    )

    # get ability
    page.locator("#ability_select").select_option("2")
    page.get_by_role("button", name="Submit", exact=True).click()
    expect_normalized(page,
        page.locator("#one"),
        "Experience points Total Used Available 12 3 9 Abilities base ability double shield (2) This text should show sword1 (1) sdsfdsfds Deliveries first live (2) Obtain ability Select the new ability to get --- Select ability",
    )
    expect(page.locator("#ability_select")).not_to_contain_text("double shield")

    # remove ability
    page.get_by_role("heading", name="double shield (2) ").get_by_role("link").click()
    expect_normalized(page,
        page.locator("#one"),
        "Experience points Total Used Available 12 1 11 Abilities base ability sword1 (1) sdsfdsfds Deliveries first live (2) Obtain ability Select the new ability to get base ability --- Select abilitydouble shield - 2",
    )
    expect_normalized(page, page.locator("#ability_select"), "--- Select abilitydouble shield - 2")


def modifiers(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage")
    # add modifier on ability
    page.get_by_role("link", name="Modifiers").click()
    page.get_by_role("link", name="New").click()
    page.get_by_role("row", name="Abilities", exact=True).get_by_role("listitem").click()
    page.get_by_role("row", name="Abilities", exact=True).get_by_role("searchbox").fill("do")
    page.get_by_role("option", name="double shield").click()
    page.get_by_role("cell", name="Indicate the required").get_by_role("searchbox").click()
    page.get_by_role("cell", name="Indicate the required").get_by_role("searchbox").fill("ro")
    page.get_by_role("option", name="Test Larp - Class Rogue").click()
    submit_confirm(page)

    # test out free ability
    go_to(page, live_server, "/test")
    page.locator("a").filter(has_text=re.compile(r"^Test Character$")).click()
    page.get_by_role("link", name="Ability").click()

    # ability is not there
    expect_normalized(page,
        page.locator("#one"),
        "Experience points Total Used Available 12 1 11 Abilities base ability sword1 (1) sdsfdsfds Deliveries first live (2) Obtain ability Select the new ability to get base ability --- Select abilitydouble shield - 2",
    )
    page.get_by_role("link", name="Test Character").click()
    page.get_by_role("link", name="Change").click()
    page.locator("#id_que_u5").select_option("u2")
    submit_confirm(page)
    page.get_by_role("link", name="Ability").click()
    # ability is there (i got the correct class)
    expect_normalized(page,
        page.locator("#one"),
        "Experience points Total Used Available 12 1 11 Abilities base ability double shield (0) This text should show sword1 (1) sdsfdsfds Deliveries first live (2) Obtain ability Select the new ability to get --- Select ability",
    )
    page.get_by_role("link", name="Test Character").click()
    page.get_by_role("link", name="Change").click()
    page.locator("#id_que_u5").select_option("u1")
    submit_confirm(page)
    page.get_by_role("link", name="Ability").click()
    # ability is not there (changed class)
    expect_normalized(page,
        page.locator("#one"),
        "Experience points Total Used Available 12 1 11 Abilities base ability sword1 (1) sdsfdsfds Deliveries first live (2) Obtain ability Select the new ability to get base ability --- Select abilitydouble shield - 2",
    )

    # now test increase cost modifiers
    go_to(page, live_server, "/test/manage")
    page.get_by_role("link", name="Modifiers").click()
    page.get_by_role("link", name="New").click()
    page.get_by_role("row", name="Abilities", exact=True).get_by_role("searchbox").click()
    page.get_by_role("row", name="Abilities", exact=True).get_by_role("searchbox").fill("do")
    page.get_by_role("option", name="double shield").click()
    page.get_by_role("row", name="Abilities", exact=True).get_by_role("searchbox").press("Tab")
    page.locator("#id_cost").fill("3")
    page.get_by_role("cell", name="Indicate the required").get_by_role("searchbox").click()
    page.get_by_role("cell", name="Indicate the required").get_by_role("searchbox").fill("mage")
    page.get_by_role("option", name="Test Larp - Class Mage").click()
    submit_confirm(page)

    go_to(page, live_server, "/test")
    page.locator("a").filter(has_text=re.compile(r"^Test Character$")).click()
    page.get_by_role("link", name="Ability").click()
    page.locator("#ability_select").select_option("2")
    page.get_by_role("button", name="Submit").click()
    expect_normalized(page,
        page.locator("#one"),
        "Experience points Total Used Available 12 4 8 Abilities base ability double shield (3) This text should show sword1 (1) sdsfdsfds Deliveries first live (2) Obtain ability Select the new ability to get --- Select ability",
    )
