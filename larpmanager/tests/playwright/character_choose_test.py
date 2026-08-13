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

"""Test: Character choose page.

Verifies the character list rendered as a card grid, the actions shown in the registration
status, the badge marking the character played in the event, and switching the played
character when the player created more characters than they can play.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    fill_date,
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


def test_character_choose(pw_page: Any) -> None:
    """Test the character choose page workflow."""
    page, live_server, _unused = pw_page

    login_orga(page, live_server)
    setup_event(page, live_server)
    logout(page)

    login_user(page, live_server)
    go_to(page, live_server, "/test/register/")
    submit_register(page)

    create_character(page, live_server, "alpha character")
    create_character(page, live_server, "beta character")

    check_card_grid(page, live_server)
    check_played_character(page, live_server)
    switch_character(page, live_server)
    check_sidebar_badge(page, live_server)


def setup_event(page: Any, live_server: Any) -> None:
    """Allow creating two characters, while only one can be played."""
    go_to(page, live_server, "/test/manage/features/character/on")
    go_to(page, live_server, "/test/manage/features/user_character/on")

    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Character creation ")).click()
    page.locator("#id_user_character_max").click()
    page.locator("#id_user_character_max").fill("2")
    page.get_by_role("link", name=re.compile(r"^Characters ")).click()
    page.locator("#id_character_play_max").click()
    page.locator("#id_character_play_max").fill("1")
    submit_confirm(page)


def create_character(page: Any, live_server: Any, name: str) -> None:
    """Create a new character from the registration status action."""
    go_to(page, live_server, "/test/register/")
    sidebar(page, "Create your character")
    page.locator("#id_name").click()
    page.locator("#id_name").fill(name)
    fill_tinymce(page, "id_teaser", f"teaser of {name}")
    fill_tinymce(page, "id_text", f"sheet of {name}")
    submit_confirm(page)


def check_card_grid(page: Any, live_server: Any) -> None:
    """Check both characters are shown as cards, with no datatable."""
    go_to(page, live_server, "/test/character/list/")
    expect(page.locator(".char-choose-card")).to_have_count(2)
    expect(page.locator("#characters")).to_have_count(0)
    expect(page.locator(".char-choose-card").first).to_contain_text("teaser of")
    expect(page.locator(".char-choose-grid")).to_contain_text("alpha character")
    expect(page.locator(".char-choose-grid")).to_contain_text("beta character")


def check_played_character(page: Any, live_server: Any) -> None:
    """Check only one character is played, and the other one offers to take its place."""
    expect(page.locator(".char-choose-badge")).to_have_count(1)
    expect(page.locator(".char-choose-select")).to_have_count(1)
    expect(page.locator(".char-choose-select")).to_contain_text("Play this character instead")

    go_to(page, live_server, "/test/register/")
    expect(page.get_by_role("link", name=re.compile("Create your character"))).to_have_count(0)

    # with no free slot left, the status still offers to change the played character
    expect(page.get_by_role("link", name=re.compile("Change (your|the) character")).first).to_be_visible()


def switch_character(page: Any, live_server: Any) -> None:
    """Switch the played character, and check the badge moves to the other card."""
    go_to(page, live_server, "/test/character/list/")
    played = page.locator(".char-choose-card", has=page.locator(".char-choose-badge"))
    expect(played).to_contain_text("alpha character")

    page.locator(".char-choose-select").click()

    expect(page.locator(".char-choose-badge")).to_have_count(1)
    played = page.locator(".char-choose-card", has=page.locator(".char-choose-badge"))
    expect(played).to_contain_text("beta character")


def check_sidebar_badge(page: Any, live_server: Any) -> None:
    """Check the sidebar marks the played character, as the player owns more than one."""
    go_to(page, live_server, "/test/register/")
    expect(page.locator(".sidebar-playing-badge")).to_have_count(1)


def test_character_choose_campaign(pw_page: Any) -> None:
    """Test changing which of the player's characters is played in the next campaign run."""
    page, live_server, _unused = pw_page

    login_orga(page, live_server)
    setup_event(page, live_server)
    create_child_event(page, live_server)
    logout(page)

    login_user(page, live_server)
    go_to(page, live_server, "/test/register/")
    submit_register(page)

    create_character(page, live_server, "alpha character")
    create_character(page, live_server, "beta character")

    # signing up to the next run of the campaign carries over the played character
    go_to(page, live_server, "/childchoose/register/")
    submit_register(page)

    check_carried_character(page, live_server)
    switch_campaign_character(page, live_server)
    check_other_run_untouched(page, live_server)


def create_child_event(page: Any, live_server: Any) -> None:
    """Create a second event of the same campaign, with Test Larp as parent."""
    go_to(page, live_server, "/manage/features/campaign/on")
    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New event").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_form1-name").click()
    edit_iframe.locator("#id_form1-name").fill("child choose")
    edit_iframe.locator("#id_form1-name").press("Tab")
    edit_iframe.locator("#slug").fill("childchoose")
    expect(edit_iframe.locator("#slug")).to_have_value("childchoose")
    edit_iframe.locator("#select2-id_form1-parent-container").click()
    edit_iframe.get_by_role("searchbox").fill("tes")
    edit_iframe.get_by_role("option", name="Test Larp", exact=True).click()
    edit_iframe.locator('label[for="id_form2-development_1"]').click()
    edit_iframe.locator('label[for="id_form2-registration_status_1"]').click()
    fill_date(edit_iframe, "#id_form2-start", "2050-03-01")
    fill_date(edit_iframe, "#id_form2-end", "2050-03-03")
    save_modal(page, edit_iframe)


def check_carried_character(page: Any, live_server: Any) -> None:
    """Check the character played in the previous run is carried over to the new one."""
    go_to(page, live_server, "/childchoose/character/list/")
    expect(page.locator(".char-choose-card")).to_have_count(2)

    played = page.locator(".char-choose-card", has=page.locator(".char-choose-badge"))
    expect(played).to_contain_text("alpha character")
    expect(page.locator(".char-choose-select")).to_have_count(1)
    expect(page.locator(".char-choose-select")).to_contain_text("Play this character instead")


def switch_campaign_character(page: Any, live_server: Any) -> None:
    """Change the character played in the new run."""
    page.locator(".char-choose-select").click()

    played = page.locator(".char-choose-card", has=page.locator(".char-choose-badge"))
    expect(played).to_contain_text("beta character")

    go_to(page, live_server, "/childchoose/")
    expect(page.locator("#one")).to_contain_text("beta character")


def check_other_run_untouched(page: Any, live_server: Any) -> None:
    """Check the character played in the previous run did not change."""
    go_to(page, live_server, "/test/character/list/")
    played = page.locator(".char-choose-card", has=page.locator(".char-choose-badge"))
    expect(played).to_contain_text("alpha character")
