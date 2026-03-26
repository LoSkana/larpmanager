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

"""Test: Character and faction hide/locked access control.

Verifies that:
- hide=True on character hides it from public gallery and direct access.
- locked=True on character prevents the assigned player from viewing the full sheet and PDFs.
- hide=True on faction propagates to all characters in that faction.
- locked=True on faction propagates to all characters in that faction.
- Orga always has full access regardless of hide/locked.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    fill_tinymce,
    go_to,
    login_orga,
    login_user,
    logout,
    sidebar,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def test_orga_character_hide_locked(pw_page: Any) -> None:  # noqa: D103
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # ===== SETUP: Enable features and configs =====
    go_to(page, live_server, "test/manage")
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="Characters").check()
    page.get_by_role("checkbox", name="Factions").check()
    submit_confirm(page)

    # Enable writing_hide and writing_locked configs
    go_to(page, live_server, "test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Characters ")).click()
    page.locator("#id_writing_hide").check()
    page.locator("#id_writing_locked").check()
    submit_confirm(page)

    char_counter = [2]
    faction_counter = [1]

    # ===== SECTION 1: Character hide =====
    _test_character_hide(page, live_server, char_counter)

    # ===== SECTION 2: Character locked =====
    _test_character_locked(page, live_server, char_counter)

    # ===== SECTION 3: Faction hide =====
    _test_faction_hide(page, live_server, char_counter, faction_counter)

    # ===== SECTION 4: Faction locked =====
    _test_faction_locked(page, live_server, char_counter, faction_counter)


def _create_character(page: Any, live_server: Any, name: str, teaser: str, text: str, counter: list) -> str:  # noqa: ARG001
    """Create a character via orga form and return its UUID using the sequential debug counter."""
    sidebar(page, "Characters")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill(name)
    fill_tinymce(page, "id_teaser", teaser)
    fill_tinymce(page, "id_text", text)
    submit_confirm(page)
    uuid = f"u{counter[0]}"
    counter[0] += 1
    return uuid


def _create_faction(page: Any, live_server: Any, name: str, teaser: str, counter: list) -> str:
    """Create a faction via orga form and return its UUID using the sequential debug counter."""
    go_to(page, live_server, "test/manage/factions/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill(name)
    fill_tinymce(page, "id_teaser", teaser)
    submit_confirm(page)
    uuid = f"u{counter[0]}"
    counter[0] += 1
    return uuid


def _assign_to_user(page: Any, live_server: Any, char_name: str) -> None:
    """Assign a character to user@test.it via registration."""
    go_to(page, live_server, "test/manage/")
    sidebar(page, "Registrations")
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").nth(1).fill("user")
    page.get_by_role("option", name="User Test - user@test.it").click()
    page.get_by_role("list").click()
    page.get_by_role("searchbox").fill(char_name[:5])
    page.get_by_role("option", name=char_name).click()
    submit_confirm(page)


def _set_char_field(page: Any, live_server: Any, char_uuid: str, field_id: str) -> None:
    """Check a boolean field on a character via its edit URL."""
    go_to(page, live_server, f"test/manage/characters/{char_uuid}/edit/")
    page.locator(f"#{field_id}").check()
    submit_confirm(page)


def _set_faction_field(page: Any, live_server: Any, faction_uuid: str, field_id: str) -> None:
    """Check a boolean field on a faction via its edit URL."""
    go_to(page, live_server, f"test/manage/factions/{faction_uuid}/edit/")
    page.locator(f"#{field_id}").check()
    submit_confirm(page)


def _test_character_hide(page: Any, live_server: Any, char_counter: list) -> None:
    """hide=True on character: hidden from gallery and direct URL for non-orga."""
    # Create visible and hidden characters
    _create_character(page, live_server, "VisibleChar", "visible teaser", "visible text", char_counter)
    hidden_uuid = _create_character(page, live_server, "HiddenChar", "hidden teaser", "hidden text", char_counter)

    # Set hide=True on HiddenChar
    _set_char_field(page, live_server, hidden_uuid, "id_hide")

    # As user: gallery shows VisibleChar but not HiddenChar
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "test/")
    expect(page.locator("#one")).to_contain_text("VisibleChar")
    expect(page.locator("#one")).not_to_contain_text("HiddenChar")

    # Direct URL to hidden char shows "not found"
    page.goto(f"{live_server}/test/character/{hidden_uuid}/")
    page.wait_for_load_state("domcontentloaded")
    expect(page.locator("#one")).to_contain_text("does not exist")

    # As orga: hidden char is visible and accessible
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, f"test/character/{hidden_uuid}/")
    expect(page.locator("#one")).to_contain_text("hidden teaser")


def _test_character_locked(page: Any, live_server: Any, char_counter: list) -> None:
    """locked=True on character: assigned player sees only public fields, PDF denied."""
    go_to(page, live_server, "test/manage/")
    locked_uuid = _create_character(page, live_server, "LockedChar", "locked teaser", "locked private text", char_counter)

    # Assign to user
    _assign_to_user(page, live_server, "LockedChar")

    # Set locked=True
    _set_char_field(page, live_server, locked_uuid, "id_locked")

    # As user: character visible in gallery
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "test/")
    expect(page.locator("#one")).to_contain_text("LockedChar")

    # Character page shows public teaser but NOT private text
    go_to(page, live_server, f"test/character/{locked_uuid}/")
    expect(page.locator("#one")).to_contain_text("locked teaser")
    expect(page.locator("#one")).not_to_contain_text("locked private text")

    # PDF denied (Http404)
    page.goto(f"{live_server}/test/character/{locked_uuid}/pdf/sheet/")
    page.wait_for_load_state("domcontentloaded")
    expect(page.locator("#banner")).to_contain_text("404")

    # As orga: full sheet visible including private text
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, f"test/character/{locked_uuid}/")
    expect(page.locator("#one")).to_contain_text("locked private text")

    go_to(page, live_server, "test/manage/")
    sidebar(page, "Registrations")
    page.locator("a:has(i.fas.fa-trash)").click(force=True)


def _test_faction_hide(page: Any, live_server: Any, char_counter: list, faction_counter: list) -> None:
    """hide=True on faction: all characters in that faction hidden from gallery."""
    # User@test.it has no registration (deleted at end of previous section).
    # Verify they can access a visible non-locked character but only see public fields.
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "test/character/u2/")  # VisibleChar: non-hidden, non-locked, unassigned
    expect(page.locator("#one")).to_contain_text("visible teaser")
    expect(page.locator("#one")).not_to_contain_text("visible text")
    logout(page)
    login_orga(page, live_server)

    faction_uuid = _create_faction(page, live_server, "HiddenFaction", "hidden faction teaser", faction_counter)
    _set_faction_field(page, live_server, faction_uuid, "id_hide")

    # Create character in that faction
    sidebar(page, "Characters")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("FactionHiddenChar")
    fill_tinymce(page, "id_teaser", "fhidden teaser")
    fill_tinymce(page, "id_text", "fhidden text")
    # Assign faction via select2
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("Hidd")
    page.wait_for_timeout(500)
    page.locator(".select2-results__option").filter(has_text="HiddenFaction").first.click()
    submit_confirm(page)
    char_uuid = f"u{char_counter[0]}"
    char_counter[0] += 1

    # As user: character not visible in gallery
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "test/")
    expect(page.locator("#one")).not_to_contain_text("FactionHiddenChar")

    # Direct URL shows "not found"
    page.goto(f"{live_server}/test/character/{char_uuid}/")
    page.wait_for_load_state("domcontentloaded")
    expect(page.locator("#one")).to_contain_text("does not exist")

    # As orga: character accessible
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, f"test/character/{char_uuid}/")
    expect(page.locator("#one")).to_contain_text("fhidden teaser")


def _test_faction_locked(page: Any, live_server: Any, char_counter: list, faction_counter: list) -> None:
    """locked=True on faction: assigned player sees only public fields for chars in that faction."""
    faction_uuid = _create_faction(page, live_server, "LockedFaction", "locked faction teaser", faction_counter)
    _set_faction_field(page, live_server, faction_uuid, "id_locked")

    # Create character in that faction
    sidebar(page, "Characters")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("FactionLockedChar")
    fill_tinymce(page, "id_teaser", "flocked teaser")
    fill_tinymce(page, "id_text", "flocked private text")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("Lock")
    page.wait_for_timeout(500)
    page.locator(".select2-results__option").filter(has_text="LockedFaction").first.click()
    submit_confirm(page)
    char_uuid = f"u{char_counter[0]}"
    char_counter[0] += 1

    # Assign to user
    _assign_to_user(page, live_server, "FactionLockedChar")

    # As user: character visible in gallery
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "test/")
    expect(page.locator("#one")).to_contain_text("FactionLockedChar")

    # Character page shows public teaser but NOT private text
    go_to(page, live_server, f"test/character/{char_uuid}/")
    expect(page.locator("#one")).to_contain_text("flocked teaser")
    expect(page.locator("#one")).not_to_contain_text("flocked private text")

    # PDF denied
    page.goto(f"{live_server}/test/character/{char_uuid}/pdf/sheet/")
    page.wait_for_load_state("domcontentloaded")
    expect(page.locator("#banner")).to_contain_text("404")

    # As orga: full sheet with private text visible
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, f"test/character/{char_uuid}/")
    expect(page.locator("#one")).to_contain_text("flocked private text")
