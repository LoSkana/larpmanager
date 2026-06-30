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

"""Test: Experience points system with abilities, deliveries, rules, and modifiers.
Verifies ability creation with prerequisites, XP delivery, computed field rules,
player ability selection with undo functionality, and conditional ability modifiers.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    _select2_search_and_pick,
    _wait_lm_ready,
    char_dual_pick,
    click_and_wait_question,
    expect_normalized,
    fill_tinymce,
    get_modal_iframe,
    get_request,
    go_to,
    just_wait,
    login_orga,
    new_option,
    save_modal,
    sidebar,
    submit_confirm,
    submit_option,
    submit_register,
)

pytestmark = pytest.mark.e2e


def test_exp(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    setup(live_server, page)

    ability(live_server, page)

    delivery(live_server, page)

    rules(page)

    player_choice_undo(page, live_server)

    modifiers(page, live_server)

    delivery_auto_populate(page, live_server)

    free_invisible_not_auto_assigned(page, live_server)

    endpoint_test(page, live_server)


def setup(live_server: Any, page: Any) -> None:
    # activate features
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Player editor").check()
    page.get_by_role("checkbox", name="Experience points").check()
    page.get_by_role("checkbox", name="Characters").check()
    submit_confirm(page)

    # configure test larp
    go_to(page, live_server, "/test/manage/config/")
    page.get_by_role("link", name=re.compile(r"^Experience points\s.+")).click()
    page.locator("#id_exp_start").click()
    page.locator("#id_exp_start").fill("10")
    page.locator("#id_exp_undo").click()
    page.locator("#id_exp_undo").fill("2")
    page.locator("#id_exp_user").check()
    page.locator("#id_exp_templates").check()
    page.locator("#id_exp_rules").check()
    page.locator("#id_exp_modifiers").check()

    page.get_by_role("link", name=re.compile(r"^Player editor\s.+")).click()
    page.locator("#id_user_character_max").click()
    page.locator("#id_user_character_max").fill("1")
    submit_confirm(page)

    # create computed field
    sidebar(page, "Sheet")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("c")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Hit Point")
    edit_iframe.locator("#id_description").click()
    edit_iframe.locator("#id_description").fill("sasad")
    edit_iframe.locator("#id_name").click()
    save_modal(page, edit_iframe)

    # create class field
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Class")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").fill("Mage")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").fill("Rogue")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").fill("Cleric")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)


def ability(live_server: Any, page: Any) -> None:
    # set up xp
    go_to(page, live_server, "/test/manage/experience/ability_types/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("base ability")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/manage/experience/abilities/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_typ-container").click()
    _select2_search_and_pick(edit_iframe.locator(".select2-container--open .select2-search__field"), edit_iframe, "base")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("standard")
    edit_iframe.locator("#id_cost").click()
    edit_iframe.locator("#id_name").dblclick()
    edit_iframe.locator("#id_name").fill("sword1")
    edit_iframe.locator("#id_cost").click()
    edit_iframe.locator("#id_cost").fill("1")
    fill_tinymce(edit_iframe, "id_descr", "sdsfdsfds", False)
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_typ-container").click()
    _select2_search_and_pick(edit_iframe.locator(".select2-container--open .select2-search__field"), edit_iframe, "base")
    edit_iframe.locator("#id_name").fill("double shield")
    edit_iframe.locator("#id_cost").click()
    edit_iframe.locator("#id_cost").fill("2")
    row = edit_iframe.get_by_role("row", name="Pre-requisites")
    _select2_search_and_pick(row.get_by_role("searchbox"), edit_iframe, "swo")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="Ability Template").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("test_template")
    fill_tinymce(edit_iframe, "id_descr", "This text should show", False)
    save_modal(page, edit_iframe)
    sidebar(page, "Abilities")
    page.locator("[id='u2']").locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_text("---------").click()
    edit_iframe.locator(".select2-container--open .select2-search__field").fill("test_template")
    edit_iframe.get_by_role("option", name="test_template").click()
    save_modal(page, edit_iframe)
    sidebar(page, "Abilities")
    page.get_by_role("cell", name="test_template").click()


def delivery(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/manage/experience/deliveries/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("first live")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_amount").fill("2")
    char_dual_pick(edit_iframe, "te", "Test Character")
    save_modal(page, edit_iframe)

    # check experience computation
    go_to(page, live_server, "/test/manage/characters/")
    click_and_wait_question(page, "Experience")
    expect_normalized(page, page.locator('[id="u1"]'), "12")
    expect_normalized(page, page.locator('[id="u1"]'), "12")
    expect_normalized(page, page.locator('[id="u1"]'), "0")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    row = edit_iframe.get_by_role("row", name="Abilities")
    row.get_by_role("link").click()
    _select2_search_and_pick(row.get_by_role("searchbox"), edit_iframe, "swo")
    save_modal(page, edit_iframe)

    expect_normalized(page, page.locator('[id="u1"]'), "11")
    expect_normalized(page, page.locator('[id="u1"]'), "12")
    expect_normalized(page, page.locator('[id="u1"]'), "1")


def rules(page: Any) -> None:
    # create first rule - for everyone
    page.get_by_role("link", name="Rules").click()

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_field-container").click()
    _select2_search_and_pick(edit_iframe.get_by_role("searchbox").nth(1), edit_iframe, "Hit")
    edit_iframe.locator("#id_amount").click()
    edit_iframe.locator("#id_amount").fill("2")
    save_modal(page, edit_iframe)

    # create second rule - only for sword
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    _select2_search_and_pick(edit_iframe.get_by_role("searchbox").first, edit_iframe, "swor")

    edit_iframe.locator("#select2-id_field-container").click()
    _select2_search_and_pick(edit_iframe.get_by_role("searchbox").nth(1), edit_iframe, "Hit")

    edit_iframe.locator("#id_operation").select_option("MUL")
    edit_iframe.locator("#id_amount").click()
    edit_iframe.locator("#id_amount").fill("3")
    save_modal(page, edit_iframe)

    # check value
    sidebar(page, "Characters")
    click_and_wait_question(page, "Hit Point")
    expect_normalized(page, page.locator("#one"), "Test Character Test Teaser Test Text 6")

    # remove ability
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_role("row", name="Abilities").get_by_role("link").click()
    just_wait(page)
    btn = edit_iframe.locator(".select2-selection__choice:has-text('sword1') .select2-selection__choice__remove")
    btn.evaluate("el => el.click()")
    save_modal(page, edit_iframe)

    # recheck value
    expect_normalized(page, page.locator("#one"), "Test Character Test Teaser Test Text 2")

    # readd ability
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    row = edit_iframe.get_by_role("row", name="Abilities")
    row.get_by_role("link").click()
    _select2_search_and_pick(row.get_by_role("searchbox"), edit_iframe, "swo")
    save_modal(page, edit_iframe)


def player_choice_undo(page: Any, live_server: Any) -> None:
    # signup
    go_to(page, live_server, "/")
    page.get_by_role("link", name="Registration is open!").click()
    submit_register(page)

    # Assign char
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Registrations")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("te")
    edit_iframe.get_by_role("option", name="Test Character").click()
    save_modal(page, edit_iframe)

    # choose
    go_to(page, live_server, "/test")
    page.locator("a").filter(has_text=re.compile(r"^Test Character$")).click()
    page.get_by_role("link", name="Abilities").click()
    _wait_lm_ready(page)
    expect(page.locator(".ability-cards-grid")).to_contain_text("double shield")
    expect_normalized(page,
        page.locator("#one"),
        """
        Obtain ability All base ability double shield 2 This text should show Requires: sword1
        select the new ability to get
        Experience points 12 Total 1 Used 11 Available Abilities base ability sword1 (1) sdsfdsfds deliveries 2 first live""",
    )

    # get ability
    page.locator(".ability-card", has_text="double shield").click()
    submit_confirm(page)
    _wait_lm_ready(page)
    expect_normalized(page,
        page.locator("#one"),
        """Obtain ability all No abilities found. Select the new ability to get
        Experience points 12 Total 3 Used 9 Available Abilities base ability double shield (2)
        This text should show sword1 (1) sdsfdsfds deliveries 2 first live """,
    )
    expect(page.locator(".ability-cards-grid")).not_to_contain_text("double shield")

    # remove ability
    page.get_by_role("heading", name=re.compile("^double shield")).get_by_role("link").click()
    _wait_lm_ready(page)
    expect(page.locator(".ability-cards-grid")).to_contain_text("double shield")
    expect_normalized(page,
        page.locator("#one"),
        """
        Obtain ability All base ability double shield 2 This text should show Requires: sword1
        Select the new ability to get
        Experience points 12 Total 1 Used 11 Available
        Abilities base ability sword1 (1) sdsfdsfds deliveries 2 first live""",
    )


def modifiers(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/")
    # add modifier on ability
    page.get_by_role("link", name="Modifiers").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_abilities_tr").get_by_role("listitem").click()
    edit_iframe.locator("#id_abilities_tr").get_by_role("searchbox").fill("do")
    edit_iframe.get_by_role("option", name="double shield").click()
    edit_iframe.get_by_role("cell", name="Indicate the required").get_by_role("searchbox").click()
    edit_iframe.get_by_role("cell", name="Indicate the required").get_by_role("searchbox").fill("ro")
    edit_iframe.get_by_role("option", name="Test Larp - Class Rogue").click()
    save_modal(page, edit_iframe)

    # test out free ability
    go_to(page, live_server, "/test")
    page.locator("a").filter(has_text=re.compile(r"^Test Character$")).click()
    page.get_by_role("link", name="Abilities").click()

    # ability is not bought
    expect_normalized(page,
        page.locator("#one"),
        """
        Obtain ability All base ability double shield 2
        this text should show requires: sword1 Select the new ability to get
        Experience points 12 Total 1 Used 11 Available
        Abilities base ability sword1 (1) sdsfdsfds deliveries 2 first live""",
    )
    page.get_by_role("link", name="Test Character").click()
    page.get_by_role("link", name="Edit").click()
    page.locator('label[for="id_que_u5_1"]').click()
    submit_confirm(page)
    page.get_by_role("link", name="Abilities").click()
    # ability is there (i got the correct class)
    expect_normalized(page,
        page.locator("#one"),
        """
        Obtain ability All No abilities found. Select the new ability to get
        Experience points 12 Total 1 Used 11 Available Abilities base ability double shield (0)
        This text should show sword1 (1) sdsfdsfds deliveries 2 first live""",
    )
    page.get_by_role("link", name="Test Character").click()
    page.get_by_role("link", name="Edit").click()
    page.locator('label[for="id_que_u5_0"]').click()
    submit_confirm(page)
    page.get_by_role("link", name="Abilities").click()
    # ability is not there (changed class)
    expect_normalized(page,
        page.locator("#one"),
        """
        Obtain ability All base ability double shield 2
        this text should show requires: sword1 Select the new ability to get
        Experience points 12 Total 1 Used 11 Available
        Abilities base ability sword1 (1) sdsfdsfds deliveries 2 first live""",
    )

    # now test increase cost modifiers
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Modifiers").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_abilities_tr").get_by_role("searchbox").click()
    edit_iframe.locator("#id_abilities_tr").get_by_role("searchbox").fill("do")
    edit_iframe.get_by_role("option", name="double shield").click()
    edit_iframe.locator("#id_abilities_tr").get_by_role("searchbox").press("Tab")
    edit_iframe.locator("#id_cost").fill("3")
    edit_iframe.get_by_role("cell", name="Indicate the required").get_by_role("searchbox").click()
    edit_iframe.get_by_role("cell", name="Indicate the required").get_by_role("searchbox").fill("mage")
    edit_iframe.get_by_role("option", name="Test Larp - Class Mage").click()
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test")
    page.locator("a").filter(has_text=re.compile(r"^Test Character$")).click()
    page.get_by_role("link", name="Edit").click()
    page.locator('label[for="id_que_u5_0"]').click()
    submit_confirm(page)
    page.get_by_role("link", name="Abilities").click()
    page.locator(".ability-card", has_text="double shield").click()
    submit_confirm(page)
    expect_normalized(page,
        page.locator("#one"),
        """
        Obtain ability All No abilities found. Select the new ability to get
        Experience points 12 Total 4 Used 8 Available Abilities base ability double shield (3)
        This text should show sword1 (1) sdsfdsfds deliveries 2 first live""",
    )


def delivery_auto_populate(page: Any, live_server: Any) -> None:
    """Test auto-populate delivery from run via Load participants button."""
    # Go to deliveries page and click Load participants
    go_to(page, live_server, "/test/manage/experience/deliveries/")
    page.get_by_role("link", name="Load participants").click()
    edit_iframe = get_modal_iframe(page)

    # Select run in the load form
    edit_iframe.locator("#select2-id_run-container").click()
    _select2_search_and_pick(edit_iframe.locator(".select2-container--open .select2-search__field"), edit_iframe, "tes")

    # Submit the load form - iframe redirects to new delivery form with characters pre-populated
    submit_confirm(edit_iframe)
    edit_iframe = get_modal_iframe(page)

    # Fill in delivery name and amount inside the modal
    edit_iframe.locator("#id_name").fill("auto populated delivery")
    edit_iframe.locator("#id_amount").fill("5")
    save_modal(page, edit_iframe)

    expect_normalized(page, page.locator('[id="u2"]'), "5 Test Character")

def free_invisible_not_auto_assigned(page: Any, live_server: Any) -> None:
    """Test that a cost-0 ability with visible=False is NOT auto-assigned."""
    # Create ability with cost=0 and visible unchecked
    go_to(page, live_server, "/test/manage/experience/abilities/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_typ-container").click()
    _select2_search_and_pick(edit_iframe.locator(".select2-container--open .select2-search__field"), edit_iframe, "base")
    edit_iframe.locator("#id_name").fill("hidden_zero")
    edit_iframe.locator("#id_cost").fill("0")
    edit_iframe.locator("#id_visible").uncheck()
    save_modal(page, edit_iframe)

    # Trigger recalculation by saving the character via orga
    go_to(page, live_server, "/test/manage/characters/")
    page.locator(".fa-edit").first.click()
    edit_iframe = get_modal_iframe(page)
    save_modal(page, edit_iframe)

    # Verify hidden_zero is NOT in the character's abilities
    go_to(page, live_server, "/test")
    page.locator("a").filter(has_text=re.compile(r"^Test Character$")).click()
    page.get_by_role("link", name="Abilities").click()
    expect(page.locator("#one")).not_to_contain_text("hidden_zero")


def endpoint_test(page: Any, live_server: Any) -> None:
    """Test character abilties endpoint"""

    # Go to character list endpoint
    response = get_request(page, live_server, "/test/character/list/json/")
    char_uuid = response[0]["uuid"]

    # Go to character abilities endpoint
    get_request(page, live_server, f"/test/character/{char_uuid}/abilities/json/")
