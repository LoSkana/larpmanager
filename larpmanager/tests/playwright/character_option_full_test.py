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

"""Test: Limited character options counted on the characters assigned to the run.

Verifies that characters not assigned do not take the spots of limited options, that a
player cannot switch to a character whose options have no spots left, and that organizers
are warned when assigning such a character.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    _select2_search_and_pick,
    click_option,
    fill_tinymce,
    get_modal_iframe,
    go_to,
    login_orga,
    login_user,
    logout,
    new_option,
    save_modal,
    sidebar,
    submit_confirm,
    submit_option,
    submit_register,
)

pytestmark = pytest.mark.e2e


def test_character_option_full(pw_page: Any) -> None:
    """Test the spots of limited options are taken only by assigned characters."""
    page, live_server, _unused = pw_page

    login_orga(page, live_server)
    setup_event(page, live_server)
    logout(page)

    # the player plays alpha, and owns beta (not assigned) with the limited option
    login_user(page, live_server)
    go_to(page, live_server, "/test/register/")
    submit_register(page)
    create_character(page, live_server, "alpha character", "wasteland")
    create_character(page, live_server, "beta character", "bunker", another=True)
    logout(page)

    # beta is not assigned, so the spot is still available to the organizer character
    login_orga(page, live_server)
    go_to(page, live_server, "/test/register/")
    submit_register(page)
    create_character(page, live_server, "gamma character", "bunker")
    logout(page)

    check_player_switch_refused(page, live_server)

    login_orga(page, live_server)
    check_orga_assign_warning(page, live_server)


def setup_event(page: Any, live_server: Any) -> None:
    """Allow two characters per player with one played, and add a question with a limited option."""
    go_to(page, live_server, "/test/manage/features/character/on")
    go_to(page, live_server, "/test/manage/features/user_character/on")

    go_to(page, live_server, "/test/manage/config")
    page.locator("#main_form").get_by_role("link", name=re.compile(r"^Character creation")).click()
    page.locator("#id_user_character_max").click()
    page.locator("#id_user_character_max").fill("2")
    page.locator("#main_form").get_by_role("link", name=re.compile(r"^Characters")).click()
    page.locator("#id_character_play_max").click()
    page.locator("#id_character_play_max").fill("1")
    page.locator("#main_form").get_by_role("link", name=re.compile(r"^Character Sheet")).click()
    page.locator("#id_character_form_wri_que_max").check()
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/writing/form/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("origin")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("wasteland")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("bunker")
    option_row.locator("#id_max_available").fill("1")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)


def create_character(page: Any, live_server: Any, name: str, option: str, *, another: bool = False) -> None:
    """Create a character choosing the given origin."""
    if another:
        go_to(page, live_server, "/test/")
        page.locator(".event-card-char").get_by_role("link", name="Create another character").click()
    else:
        go_to(page, live_server, "/test/register/")
        sidebar(page, "Create your character")
    page.locator("#id_name").click()
    page.locator("#id_name").fill(name)
    fill_tinymce(page, "id_teaser", f"teaser of {name}")
    fill_tinymce(page, "id_text", f"sheet of {name}")

    # the limited option is still free: only assigned characters take its spot
    bunker_label = page.locator("#main_form label", has_text="bunker")
    if another:
        # no free slot, so the character is not auto-assigned and its options are not limited
        expect(bunker_label).not_to_contain_text("available")
    else:
        expect(bunker_label).to_contain_text("1 available")
    click_option(page.locator("#main_form label", has_text=option).locator("input"))
    submit_confirm(page)


def check_player_switch_refused(page: Any, live_server: Any) -> None:
    """Check the player cannot switch to beta, whose limited option has no spots left."""
    login_user(page, live_server)
    go_to(page, live_server, "/test/character/list/")
    page.locator(".char-choose-select").click()
    expect(page.locator(".jq-toast-single")).to_contain_text("cannot be assigned: no spots left for origin: bunker")

    played = page.locator("#characters tbody tr", has=page.locator(".char-choose-badge"))
    expect(played).to_contain_text("alpha character")
    logout(page)


def check_orga_assign_warning(page: Any, live_server: Any) -> None:
    """Check the organizer can assign beta, but is warned about the exceeded spots."""
    go_to(page, live_server, "/test/manage/registrations/")
    page.locator("#one tr", has_text="User Test").locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    btn = edit_iframe.locator(
        ".select2-selection__choice:has-text('alpha character') .select2-selection__choice__remove"
    )
    btn.wait_for(state="attached")
    btn.evaluate("el => el.click()")
    row = edit_iframe.get_by_role("row", name=re.compile(r"^Characters"))
    _select2_search_and_pick(row.get_by_role("searchbox"), edit_iframe, "beta")
    save_modal(page, edit_iframe)

    expect(page.locator(".jq-toast-single", has_text="beta character assigned, but exceeds the spots")).to_be_visible()
