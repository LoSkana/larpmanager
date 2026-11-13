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
Test: Character concept field.
Verifies the staff-only concept question is created hidden with locked visibility,
is shown and searchable in staff character pickers (relationships, plots),
and is never shown to participants, nor in their pickers (guild invite, player relationships).
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    _wait_lm_ready,
    char_dual_pick,
    check_feature,
    expect_normalized,
    fill_tinymce,
    get_modal_iframe,
    go_to,
    login_orga,
    login_user,
    logout,
    save_modal,
    sidebar,
    submit_confirm,
    submit_register,
)

pytestmark = pytest.mark.e2e


def test_orga_character_concept(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    concept_setup(page, live_server)

    concept_relationships(page)

    concept_plots(page, live_server)

    concept_hidden_to_players(page, live_server)


def concept_setup(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Features")
    check_feature(page, "Characters")
    check_feature(page, "Plots")
    check_feature(page, "Relationships")
    submit_confirm(page)

    # enable concept field
    go_to(page, live_server, "/test/manage/config/")
    page.locator("#main_form").get_by_role("link", name=re.compile(r"^Character Sheet")).click()
    page.locator("#id_writing_concept").check()
    submit_confirm(page)

    # concept question is created hidden
    sidebar(page, "Sheet")
    expect_normalized(
        page, page.locator("#one"), "Name Name Public Presentation Presentation Public Text Sheet Private Concept Concept Hidden"
    )

    # visibility and status cannot be changed
    page.locator("tr", has_text="Concept").locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").wait_for(state="visible")
    expect(edit_iframe.locator("#id_visibility")).to_have_count(0)
    expect(edit_iframe.locator("#id_status")).to_have_count(0)
    save_modal(page, edit_iframe)
    expect_normalized(
        page, page.locator("#one"), "Name Name Public Presentation Presentation Public Text Sheet Private Concept Concept Hidden"
    )

    # set concept on test character
    sidebar(page, "Characters")
    page.locator('[id="u1"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("tr", has_text="Concept").locator("input").fill("secret spy")
    save_modal(page, edit_iframe)


def concept_relationships(page: Any) -> None:
    # new character, add relationship searching by concept
    sidebar(page, "Characters")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("prova")
    edit_iframe.locator("#select2-new_rel_select-container").click()
    edit_iframe.get_by_role("searchbox").fill("spy")
    option = edit_iframe.get_by_role("option", name="Test Character (secret spy)")
    option.wait_for(state="visible")
    option.click()
    expect(edit_iframe.locator("#form_relationships")).to_contain_text("Test Character (secret spy)")
    fill_tinymce(edit_iframe, "rel_u1", "ciaaoooooo")
    save_modal(page, edit_iframe)

    # existing relationship row shows the concept
    page.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect(edit_iframe.locator("#form_relationships")).to_contain_text("Test Character (secret spy)")


def concept_plots(page: Any, live_server: Any) -> None:
    # new plot, add character searching by concept
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Plots")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("concept plot")
    char_dual_pick(edit_iframe, "spy", "Test Character (secret spy)")
    save_modal(page, edit_iframe)

    # role field label shows the concept
    page.locator('[id="u1"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect(edit_iframe.locator(".char-dual-sel-list")).to_contain_text("Test Character (secret spy)")
    expect(edit_iframe.locator("#main_form")).to_contain_text("Test Character (secret spy)")


def concept_hidden_to_players(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/")
    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/test/gallery/")
    page.get_by_role("link", name="Test Character").first.click()
    _wait_lm_ready(page)
    expect(page.locator("#one")).not_to_contain_text("secret spy")
    expect(page.locator("#one")).not_to_contain_text("Concept")


def test_player_pickers_concept(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/features/character/on")
    go_to(page, live_server, "/test/manage/features/user_character/on")
    go_to(page, live_server, "/test/manage/features/guild/on")
    go_to(page, live_server, "/test/manage/features/player_relationships/on")

    # let the player play both owned characters
    go_to(page, live_server, "/test/manage/config")
    page.locator("#main_form").get_by_role("link", name=re.compile(r"^Characters")).click()
    page.locator("#id_character_play_max").fill("2")
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/config/")
    page.locator("#main_form").get_by_role("link", name=re.compile(r"^Character Sheet")).click()
    page.locator("#id_writing_concept").check()
    submit_confirm(page)

    create_player_character(page, live_server, "Guild Founder", "")
    create_player_character(page, live_server, "Guild Recruit", "secret spy")

    # player registers, getting both characters
    go_to(page, live_server, "/test/manage/")
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/test/register")
    submit_register(page)

    # guild invite picker: no concept in labels, no match by concept
    go_to(page, live_server, "/test/guilds/new/")
    page.locator("#founder_character").select_option(label="Guild Founder")
    page.locator("#id_name").fill("The Silver Hand")
    fill_tinymce(page, "id_teaser", "A guild of silver knights")
    page.locator("#form_submit").click()
    page.locator("#select2-guild-invite-select-container").click()
    check_player_picker(page)

    # player relationship picker: no concept in labels, no match by concept
    go_to(page, live_server, "/test/character/u2/relationships/new/")
    page.locator("#select2-id_target-container").click()
    check_player_picker(page)


def create_player_character(page: Any, live_server: Any, name: str, concept: str) -> None:
    """Create a character with a concept, assigned to user@test.it."""
    go_to(page, live_server, "/test/manage/characters")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill(name)
    edit_iframe.locator("#select2-id_player-container").click()
    edit_iframe.get_by_role("searchbox").fill("user")
    edit_iframe.get_by_role("option", name="User Test - user@test.it").click()
    if concept:
        edit_iframe.locator("tr", has_text="Concept").locator("input").fill(concept)
    save_modal(page, edit_iframe)


def check_player_picker(page: Any) -> None:
    """Check an open select2 character picker neither shows nor searches the concept."""
    searchbox = page.get_by_role("searchbox")
    searchbox.fill("Guild Recruit")
    page.locator(".select2-results__option").first.wait_for(state="visible")
    expect(page.locator(".select2-results")).to_contain_text("Guild Recruit")
    expect(page.locator(".select2-results")).not_to_contain_text("secret spy")

    searchbox.fill("spy")
    expect(page.locator(".select2-results")).to_contain_text("No results found")
    expect(page.locator(".select2-results")).not_to_contain_text("Guild Recruit")
