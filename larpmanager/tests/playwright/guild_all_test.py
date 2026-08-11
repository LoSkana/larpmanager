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
    char_dual_pick,
    fill_date,
    fill_tinymce,
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
    fill_tinymce(page, "id_teaser", "A guild of silver knights")
    fill_tinymce(page, "id_text", "The full history of the Silver Hand")
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

    check_roles_and_leave(page, live_server)

    logout(page)

    # ========== SECTION 15: Guilds on a campaign child event (characters live on the parent) ==========
    check_campaign_child(page, live_server)

    logout(page)


def check_roles_and_leave(page: Any, live_server: Any) -> None:
    """Verify promote, demote, kick and the last-admin protection on leaving."""
    # ========== SECTION 10: Promote Guild Recruit to admin ==========
    rows = page.locator("#guild-members")
    recruit_row = rows.filter(has_text="Guild Recruit")
    recruit_row.get_by_role("button", name="Promote to admin").click()

    go_to(page, live_server, "/test/guilds/")
    page.get_by_role("link", name="The Silver Hand").click()
    recruit_row = page.locator("#guild-members tr").filter(has_text="Guild Recruit")
    expect(recruit_row).to_contain_text("Admin")

    # ========== SECTION 11: Demote Guild Recruit back to member ==========
    recruit_row.get_by_role("button", name="Remove admin").click()

    go_to(page, live_server, "/test/guilds/")
    page.get_by_role("link", name="The Silver Hand").click()
    recruit_row = page.locator("#guild-members tr").filter(has_text="Guild Recruit")
    expect(recruit_row).to_contain_text("Member")

    # ========== SECTION 12: Kick Guild Recruit ==========
    recruit_row.get_by_role("button", name="Remove from guild").click()

    go_to(page, live_server, "/test/guilds/")
    page.get_by_role("link", name="The Silver Hand").click()
    expect(page.locator("#guild-members")).not_to_contain_text("Guild Recruit")

    # ========== SECTION 13: Last-admin protection blocks leaving ==========
    page.locator("form[action*='/leave/'] button[type=submit]").click()
    expect(page.locator(".jq-toast-single")).to_contain_text("last admin")

    logout(page)

    # ========== SECTION 14: Orga adds a member and changes the guild admins ==========
    check_orga_members_admins(page, live_server)


def check_orga_members_admins(page: Any, live_server: Any) -> None:
    """Verify the organizer can set both guild members and guild admins."""
    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/guilds/")
    expect(page.locator("#one")).to_contain_text("The Silver Hand")
    page.locator(".fa-edit").first.click()
    edit_iframe = get_modal_iframe(page)

    # Add Guild Recruit back as a member, and make it the only admin in place of Guild Founder
    char_dual_pick(edit_iframe.locator("div.char-dual[data-field-id=id_characters]"), "Guild", "Guild Recruit")
    admins = edit_iframe.locator("div.char-dual[data-field-id=id_admins]")
    char_dual_pick(admins, "Guild", "Guild Recruit")
    admins.locator(".char-dual-sel-list li").filter(has_text="Guild Founder").click()
    save_modal(page, edit_iframe)

    logout(page)

    # The recruit is a member and admin, the founder is a plain member
    login_user(page, live_server)
    go_to(page, live_server, "/test/guilds/")
    page.get_by_role("link", name="The Silver Hand").click()
    recruit_row = page.locator("#guild-members tr").filter(has_text="Guild Recruit")
    expect(recruit_row).to_contain_text("Admin")
    founder_row = page.locator("#guild-members tr").filter(has_text="Guild Founder")
    expect(founder_row).to_contain_text("Member")


def check_campaign_child(page: Any, live_server: Any) -> None:
    """Verify invite/accept/leave work on a child event, whose characters belong to the parent."""
    login_orga(page, live_server)
    go_to(page, live_server, "/manage/features/campaign/on")

    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New event").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_form1-name").fill("child guild")
    edit_iframe.locator("#id_form1-name").press("Tab")
    edit_iframe.locator("#slug").fill("childguild")
    expect(edit_iframe.locator("#slug")).to_have_value("childguild")
    edit_iframe.locator("#select2-id_form1-parent-container").click()
    edit_iframe.get_by_role("searchbox").fill("tes")
    edit_iframe.get_by_role("option", name="Test Larp", exact=True).click()
    edit_iframe.locator('label[for="id_form2-development_1"]').click()
    edit_iframe.locator('label[for="id_form2-registration_status_1"]').click()
    fill_date(edit_iframe, "#id_form2-start", "2050-02-01")
    fill_date(edit_iframe, "#id_form2-end", "2050-02-03")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/childguild/manage/features/guild/on")

    # User registers to the child run, then founds a guild with a character of the parent event
    login_user(page, live_server)
    go_to(page, live_server, "/childguild/register")
    submit_register(page)

    go_to(page, live_server, "/childguild/guilds/new/")
    page.locator("#founder_character").select_option(label="Guild Founder")
    page.locator("#id_name").fill("The Iron Chain")
    fill_tinymce(page, "id_teaser", "A guild of the child event")
    fill_tinymce(page, "id_text", "The full history of the Iron Chain")
    page.locator("#form_submit").click()

    # Invite a parent-event character
    page.locator("#select2-guild-invite-select-container").click()
    _select2_search_and_pick(page.get_by_role("searchbox"), page, "Guild Recruit")
    page.get_by_role("button", name="Invite").click()
    expect(page.locator(".jq-toast-single")).to_contain_text("Invite sent")

    # Accept the invite
    go_to(page, live_server, "/childguild/guilds/invites/")
    expect(page.locator("#one")).to_contain_text("Guild Recruit")
    page.get_by_role("button", name="Accept").click()
    expect(page.locator(".jq-toast-single")).to_contain_text("joined the guild")

    # Promote the recruit, so the founder is not the last admin, then leave
    go_to(page, live_server, "/childguild/guilds/")
    page.get_by_role("link", name="The Iron Chain").click()
    recruit_row = page.locator("#guild-members tr").filter(has_text="Guild Recruit")
    recruit_row.get_by_role("button", name="Promote to admin").click()

    page.locator("form[action*='/leave/'] button[type=submit]").click()
    expect(page.locator(".jq-toast-single")).to_contain_text("left the guild")
