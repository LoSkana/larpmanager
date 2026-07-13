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

"""Test: Guild feature end-to-end.

Covers guild creation by a player, inviting a second character, accepting the
invite, promoting/demoting an admin, kicking a member, and the last-admin
protection that blocks leaving/demoting the sole remaining admin.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    _select2_search_and_pick,
    get_modal_iframe,
    go_to,
    login_orga,
    login_user,
    logout,
    save_modal,
    submit_register,
)

pytestmark = pytest.mark.e2e


def create_and_assign_character(page: Any, live_server: Any, name: str) -> None:
    """Create a character as organizer and assign it to user@test.it."""
    go_to(page, live_server, "/test/manage/characters")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill(name)
    edit_iframe.locator("#select2-id_player-container").click()
    edit_iframe.get_by_role("searchbox").fill("user")
    edit_iframe.get_by_role("option", name="User Test - user@test.it").click()
    save_modal(page, edit_iframe)


def test_guild_all(pw_page: Any) -> None:
    """Comprehensive test for the guild player self-service lifecycle."""
    page, live_server, _ = pw_page

    # ========== SECTION 1: Setup & Feature Activation ==========
    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/features/user_character/on")
    go_to(page, live_server, "/test/manage/features/guild/on")
    go_to(page, live_server, "/test/manage/features/character/on")

    # ========== SECTION 2: Orga creates two characters, both owned by user@test.it ==========
    create_and_assign_character(page, live_server, "Guild Founder")
    create_and_assign_character(page, live_server, "Guild Recruit")

    # ========== SECTION 3: User registers to the event ==========
    login_user(page, live_server)
    go_to(page, live_server, "/test/register")
    submit_register(page)

    # ========== SECTION 4: User creates a guild founded by "Guild Founder" ==========
    go_to(page, live_server, "/test/guilds/new/")
    page.locator("#founder_character").select_option(label="Guild Founder")
    page.locator("#id_name").fill("The Silver Hand")
    page.locator("#form_submit").click()

    expect(page).to_have_url(re.compile(r"/guilds/u1"))

    # ========== SECTION 5: Guild appears in the public list ==========
    go_to(page, live_server, "/test/guilds/")
    expect(page.locator("#one")).to_contain_text("The Silver Hand")
    page.get_by_role("link", name="The Silver Hand").click()

    # ========== SECTION 6: Founder is admin, sees edit/invite/manage controls ==========
    expect(page.get_by_role("link", name="Edit guild")).to_be_visible()
    expect(page.get_by_role("heading", name="Invite a character")).to_be_visible()

    # ========== SECTION 7: Invite "Guild Recruit" ==========
    page.locator("#select2-guild-invite-select-container").click()
    _select2_search_and_pick(page.get_by_role("searchbox"), page, "Guild Recruit")
    page.get_by_role("button", name="Invite").click()

    # ========== SECTION 8: Accept the pending invite ==========
    go_to(page, live_server, "/test/guilds/invites/")
    expect(page.locator("#one")).to_contain_text("Guild Recruit")
    page.get_by_role("button", name="Accept").click()

    # ========== SECTION 9: Verify Guild Recruit is now a member ==========
    go_to(page, live_server, "/test/guilds/")
    page.get_by_role("link", name="The Silver Hand").click()
    founder_row = page.locator("#guild-members tr").filter(has_text="Guild Founder")
    expect(founder_row).to_contain_text("Admin")
    recruit_row = page.locator("#guild-members tr").filter(has_text="Guild Recruit")
    expect(recruit_row).to_contain_text("Member")

    # ========== SECTION 10: Promote Guild Recruit to admin ==========
    rows = page.locator("#guild-members")
    recruit_row = rows.filter(has_text="Guild Recruit")
    recruit_row.get_by_role("button", name="Promote").click()

    go_to(page, live_server, "/test/guilds/")
    page.get_by_role("link", name="The Silver Hand").click()
    recruit_row = page.locator("#guild-members tr").filter(has_text="Guild Recruit")
    expect(recruit_row).to_contain_text("Admin")

    # ========== SECTION 11: Demote Guild Recruit back to member ==========
    recruit_row.get_by_role("button", name="Demote").click()

    go_to(page, live_server, "/test/guilds/")
    page.get_by_role("link", name="The Silver Hand").click()
    recruit_row = page.locator("#guild-members tr").filter(has_text="Guild Recruit")
    expect(recruit_row).to_contain_text("Member")

    # ========== SECTION 12: Kick Guild Recruit ==========
    recruit_row.get_by_role("button", name="Kick").click()

    go_to(page, live_server, "/test/guilds/")
    page.get_by_role("link", name="The Silver Hand").click()
    expect(page.locator("#guild-members")).not_to_contain_text("Guild Recruit")

    # ========== SECTION 13: Last-admin protection blocks leaving ==========
    page.locator("form[action*='/leave/'] button[type=submit]").click()
    expect(page.locator(".jq-toast-single")).to_contain_text("last admin")

    logout(page)
