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
Test: Character form editor with player editor feature.
Verifies dynamic character form creation with single/multiple choice fields, text fields,
prerequisites, availability limits, and player character creation/approval workflow.
"""
import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import just_wait, fill_tinymce, go_to, login_orga, submit_confirm, expect_normalized, \
    submit_register, \
    submit_option, new_option, \
    get_modal_iframe, save_modal, _wait_lm_ready

pytestmark = pytest.mark.e2e


def test_user_character_form_editor(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    prepare(page, live_server)

    field_single(page, live_server)

    field_multiple(page, live_server)

    field_text(page, live_server)

    field_single_req(page, live_server)

    character(page, live_server)

    verify_characters_shortcut(page, live_server)

    player_relationships(page, live_server)


def prepare(page: Any, live_server: Any) -> None:
    # Activate characters
    go_to(page, live_server, "/test/manage/features/character/on")

    # Activate player editor
    go_to(page, live_server, "/test/manage/features/user_character/on")

    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Player editor ")).click()
    page.locator("#id_user_character_approval").check()
    page.get_by_role("cell", name="Maximum number of characters").click()
    page.locator("#id_user_character_max").fill("1")
    page.get_by_role("link", name=re.compile(r"^Character Sheet")).click()
    page.locator("#id_character_form_wri_que_max").check()
    page.locator("#id_character_form_wri_que_requirements").check()
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/writing/form/")
    expect_normalized(page, page.locator('[id="u1"]'), "Name")
    expect_normalized(page, page.locator('[id="u2"]'), "Presentation")
    expect_normalized(page, page.locator('[id="u3"]'), "Sheet")


def field_single(page: Any, live_server: Any) -> None:
    # add single
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("single")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("sssssingle")

    iframe = new_option(edit_iframe)
    iframe.locator("#id_name").click()
    iframe.locator("#id_name").fill("ff")
    iframe.locator("#id_max_available").click()
    iframe.locator("#id_max_available").fill("3")
    submit_option(edit_iframe, iframe)

    iframe = new_option(edit_iframe)
    iframe.locator("#id_name").click()
    iframe.locator("#id_name").fill("rrrr")
    submit_option(edit_iframe, iframe)

    iframe = new_option(edit_iframe)
    iframe.locator("#id_name").click()
    iframe.locator("#id_name").fill("wwww")
    submit_option(edit_iframe, iframe)

    save_modal(page, edit_iframe)


def field_multiple(page: Any, live_server: Any) -> None:
    # Add multiple
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_text("Question type").click()
    edit_iframe.locator("#id_typ").select_option("m")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("rrrrrr")
    edit_iframe.locator("#id_max_length").click()
    edit_iframe.locator("#id_max_length").fill("1")

    iframe = new_option(edit_iframe)
    iframe.locator("#id_name").click()
    iframe.locator("#id_name").fill("q1")
    submit_option(edit_iframe, iframe)

    iframe = new_option(edit_iframe)
    iframe.locator("#id_name").click()
    iframe.locator("#id_name").fill("q2")
    submit_option(edit_iframe, iframe)

    iframe = new_option(edit_iframe)
    iframe.locator("#id_name").click()
    iframe.locator("#id_name").fill("q3")
    submit_option(edit_iframe, iframe)

    iframe = new_option(edit_iframe)
    iframe.locator("#id_name").click()
    iframe.locator("#id_name").fill("14")
    iframe.locator("#id_max_available").click()
    iframe.locator("#id_max_available").fill("3")
    iframe.searchbox("requirements").fill("ww")
    iframe.get_by_role("option", name="single - wwww").click()
    submit_option(edit_iframe, iframe)

    save_modal(page, edit_iframe)


def field_text(page: Any, live_server: Any) -> None:
    _wait_lm_ready(page)

    # Add text
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.get_by_role("cell", name="Question name (keep it short)").click()
    edit_iframe.locator("#id_name").fill("text")
    edit_iframe.locator("#id_max_length").click()
    edit_iframe.locator("#id_max_length").fill("10")
    save_modal(page, edit_iframe)

    # Add paragraph
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("p")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("rrr")
    save_modal(page, edit_iframe)

    # Create new character
    go_to(page, live_server, "/test/manage/characters")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("provaaaa")

    fill_tinymce(edit_iframe, "id_teaser", "adsdsadsa")

    fill_tinymce(edit_iframe, "id_text", "rrrr")

    edit_iframe.locator('label[for="id_que_u4_2"]').click()  # wwww
    edit_iframe.locator('label[for="id_que_u4_0"]').click()  # ff
    edit_iframe.locator('label[for="id_que_u5_1"]').click()  # q2
    edit_iframe.locator("#id_que_u6").click()
    edit_iframe.locator("#id_que_u6").fill("sad")
    edit_iframe.locator("#id_que_u7").click()
    edit_iframe.locator("#id_que_u7").fill("sadsadas")
    save_modal(page, edit_iframe)


def field_single_req(page: Any, live_server: Any) -> None:
    # Add a second single-choice question where one option requires "wwww" from "single"
    go_to(page, live_server, "/test/manage/writing/form/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("single_req")

    iframe = new_option(edit_iframe)
    iframe.locator("#id_name").fill("dep_a")
    submit_option(edit_iframe, iframe)

    iframe = new_option(edit_iframe)
    iframe.locator("#id_name").fill("dep_b")
    iframe.searchbox("requirements").fill("ww")
    iframe.get_by_role("option", name="single - wwww").click()
    submit_option(edit_iframe, iframe)

    save_modal(page, edit_iframe)


def verify_requirements_hidden(page: Any) -> None:
    """Verify options with unmet requirements are hidden, and shown when requirements are met.

    Tests both question types:
    - multiple-choice (checkbox): option "14" (u7) requires "wwww" (u3)
    - single-choice (radio): option "dep_b" (u9, index 1) in "single_req" (u8) requires "wwww" (u3)
    """
    # the native inputs are visually hidden by lm.css (zero size); the dependency
    # JS toggles the wrapping label, so assert visibility on the label instead
    label_14 = page.locator('label:has(input[type="checkbox"][value="u7"])')
    dep_b_radio = page.locator('label:has(input[type="radio"][value="u9"])')

    # Nothing selected yet in "single" - both dependent options must be hidden
    expect(label_14).to_be_hidden()
    expect(dep_b_radio).to_be_hidden()

    # Select a different option ("rrrr", index 1) - both must still be hidden
    page.locator('label[for="id_que_u4_1"]').click()
    just_wait(page)
    expect(label_14).to_be_hidden()
    expect(dep_b_radio).to_be_hidden()

    # Select "wwww" (index 2) - both must become visible
    page.locator('label[for="id_que_u4_2"]').click()
    just_wait(page)
    expect(label_14).to_be_visible()
    expect(dep_b_radio).to_be_visible()


def character(page: Any, live_server: Any) -> None:
    # signup, create char
    go_to(page, live_server, "/test/register")
    submit_register(page)

    page.get_by_role("checkbox", name="Authorisation").check()
    submit_confirm(page)

    expect_normalized(page, page.locator("#one"), "Create your character!")
    page.get_by_role("link", name="Create your character!").click()
    _wait_lm_ready(page)

    verify_requirements_hidden(page)

    page.locator("#id_name").click()
    page.locator("#id_name").fill("my character")

    fill_tinymce(page, "id_teaser", "so coool")

    fill_tinymce(page, "id_text", "so braaaave")

    page.locator('label[for="id_que_u4_0"]').click()  # ff
    page.locator('label[for="id_que_u4_2"]').click()  # wwww
    page.locator('label[for="id_que_u5_3"]').click()  # 14 (Available 3)
    page.locator("#id_que_u6").click()
    page.locator("#id_que_u6").fill("wow")
    page.locator("#id_que_u7").click()
    page.locator("#id_que_u7").fill("asdsadsa")
    submit_confirm(page)

    # confirm char
    expect_normalized(page, page.locator("#one"), "my character (Creation)")
    page.get_by_role("link", name="my character (Creation)").click()
    page.get_by_role("link", name="Edit").click()
    page.get_by_role("cell", name="Click here to confirm that").click()
    page.get_by_text("Click here to confirm that").click()
    page.locator("#id_propose").check()
    submit_confirm(page)

    # check char
    expect_normalized(page, page.locator("#one"), "my character (Proposed)")

    # approve char
    go_to(page, live_server, "/test/manage/characters")
    page.locator('[id="u3"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_status").select_option("a")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "Your character is: my character")

    go_to(page, live_server, "/test")
    expect_normalized(page, page.locator("#one"), "Your character is: my character")

def verify_characters_shortcut(page: Any, live_server: Any) -> None:
    """Enable the user_characters_shortcut configuration."""

    # Enable characters shortcut
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name="Interface ").click()
    page.locator("#id_user_characters_shortcut").check()
    page.locator("#id_user_registrations_shortcut").check()
    submit_confirm(page)

    # Verify the Characters link is visible in the topbar
    go_to(page, live_server, "/")
    page.get_by_role("link", name=re.compile(" Characters$")).click()

    # Verify the page shows characters content
    expect_normalized(page, page.locator("#one"), "character active last event character active last event my character test larp")

    page.get_by_role("link", name=re.compile(" Registrations$")).click()

    expect_normalized(page, page.locator("#one"),
  "test larp 19 march 2050 registration confirmed (standard) your character is: my character")


def player_relationships(page: Any, live_server: Any) -> None:
    # Enable player relationships in config
    go_to(page, live_server, "/test/manage/features/player_relationships/on")


    # Navigate to relationships page from the registration page
    go_to(page, live_server, "/test/register")
    page.get_by_role("link", name="Relationships").click()
    _wait_lm_ready(page)

    # Create new relationship toward Test Character
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_target-container").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="Test Character").click()
    fill_tinymce(page, "id_text", "my relationship text", show=False)
    submit_confirm(page)
    # Verify relationship appears in list
    expect_normalized(page, page.locator("#player_relationships"), "details relationship test character factions: test teaser (...) my relationship text")

    # Edit the relationship and update the text
    page.locator("#player_relationships").locator(".fa-edit").click()
    _wait_lm_ready(page)
    fill_tinymce(page, "id_text", "updated relationship text", show=False)
    submit_confirm(page)

    # Verify updated text
    expect_normalized(page, page.locator("#player_relationships"), "details relationship test character factions: test teaser (...) updated relationship text")
