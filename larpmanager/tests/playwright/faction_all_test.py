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
Test: Comprehensive faction sheet functionality.
Tests WritingQuestions (public/private) for factions, faction creation with different types,
character creation with faction assignments, user visibility rules, faction reordering,
and visibility of teaser/text/WritingQuestions based on character assignment.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    expect_normalized,
    fill_tinymce,
    go_to,
    login_orga,
    login_user,
    logout,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def test_faction_all(pw_page: Any) -> None:
    """
    Comprehensive test for faction system covering:
    - WritingQuestion creation (public/private, faction-applicable)
    - Faction creation (9 total: 3 primary, 3 transversal, 3 secret)
    - Character creation with various faction combinations
    - User visibility verification (public vs secret)
    - Faction reordering and cache refresh
    - Gallery display verification
    - Character sheet visibility (teaser, text, WritingQuestions)
    """
    page, live_server, _ = pw_page

    # ========== SECTION 1: Setup & Feature Activation ==========
    login_orga(page, live_server)
    go_to(page, live_server, "test/manage")

    # Activate Factions and Characters features
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Factions").check()
    page.get_by_role("checkbox", name="Characters").check()
    submit_confirm(page)

    # ========== SECTION 2: Create WritingQuestions for Factions ==========
    # Navigate to Factions form (WritingQuestions applicable to factions)
    go_to(page, live_server, "test/manage/writing/form/faction/")

    # Create PUBLIC WritingQuestion
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")  # Text type
    page.locator("#id_name").fill("Public Faction Question")
    page.locator("#id_description").fill("This is visible to everyone")
    page.locator("#id_visibility").select_option("c")  # PUBLIC
    # Note: applicable is automatically set to FACTION by the form
    submit_confirm(page)

    # Create PRIVATE WritingQuestion
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("p")  # Paragraph type
    page.locator("#id_name").fill("Private Faction Question")
    page.locator("#id_description").fill("Only visible to assigned members")
    page.locator("#id_visibility").select_option("e")  # PRIVATE
    # Note: applicable is automatically set to FACTION by the form
    submit_confirm(page)

    # ========== SECTION 3: Create 9 Factions (3 Primary, 3 Transversal, 3 Secret) ==========
    page.get_by_role("link", name="Factions").click()

    # Helper to create factions
    def create_faction(typ: str, name: str, teaser: str, text: str, public_ans: str, private_ans: str) -> None:
        # Navigate to factions list before creating new one
        go_to(page, live_server, "test/manage/writing/factions/")
        page.get_by_role("link", name="New").click()
        page.locator("#id_typ").select_option(typ)
        page.locator("#id_name").fill(name)
        fill_tinymce(page, "id_teaser", teaser)
        fill_tinymce(page, "id_text", text)

        # Fill WritingQuestion answers (find input fields dynamically)
        question_inputs = page.locator("input[name^='que_']").all()
        if len(question_inputs) >= 2:
            question_inputs[0].fill(public_ans)
            question_inputs[1].fill(private_ans)

        submit_confirm(page)

    # PRIMARY FACTIONS (typ="s")
    create_faction("s", "Primary Faction 1", "PF1 teaser", "PF1 private text",
                   "PF1 public answer", "PF1 private answer")
    create_faction("s", "Primary Faction 2", "PF2 teaser", "PF2 private text",
                   "PF2 public answer", "PF2 private answer")
    create_faction("s", "Primary Faction 3", "PF3 teaser", "PF3 private text",
                   "PF3 public answer", "PF3 private answer")

    # TRANSVERSAL FACTIONS (typ="t")
    create_faction("t", "Transversal Faction 1", "TF1 teaser", "TF1 private text",
                   "TF1 public answer", "TF1 private answer")
    create_faction("t", "Transversal Faction 2", "TF2 teaser", "TF2 private text",
                   "TF2 public answer", "TF2 private answer")
    create_faction("t", "Transversal Faction 3", "TF3 teaser", "TF3 private text",
                   "TF3 public answer", "TF3 private answer")

    # SECRET FACTIONS (typ="g")
    create_faction("g", "Secret Faction 1", "SF1 teaser", "SF1 private text",
                   "SF1 public answer", "SF1 private answer")
    create_faction("g", "Secret Faction 2", "SF2 teaser", "SF2 private text",
                   "SF2 public answer", "SF2 private answer")
    create_faction("g", "Secret Faction 3", "SF3 teaser", "SF3 private text",
                   "SF3 public answer", "SF3 private answer")

    # ========== SECTION 4: Create 3 Characters with Different Faction Combinations ==========
    page.get_by_role("link", name="Characters").click()

    # Helper to create characters with faction assignments
    def create_character(name: str, teaser: str, text: str, faction_names: list) -> None:
        page.get_by_role("link", name="New").click()
        page.locator("#id_name").fill(name)
        fill_tinymce(page, "id_teaser", teaser)
        fill_tinymce(page, "id_text", text)

        # Assign factions using select2 widget
        for faction in faction_names:
            page.get_by_role("searchbox").click()
            page.get_by_role("searchbox").fill(faction[:5])  # Type first 5 chars
            page.wait_for_timeout(500)  # Wait for dropdown
            page.locator(".select2-results__option").filter(has_text=faction).first.click()

        submit_confirm(page)

    # Character 1: Primary Faction 1 + all 3 Transversals (will be assigned to user@test.it)
    create_character("Character Alpha", "Alpha teaser", "Alpha private text",
                     ["Primary Faction 1", "Transversal Faction 1",
                      "Transversal Faction 2", "Transversal Faction 3"])

    # Character 2: Primary Faction 1 (shared) + 1 Transversal + 2 Secrets
    create_character("Character Beta", "Beta teaser", "Beta private text",
                     ["Primary Faction 1", "Transversal Faction 1",
                      "Secret Faction 1", "Secret Faction 2"])

    # Character 3: Primary Faction 2 + 2 Transversals + 1 Secret
    create_character("Character Gamma", "Gamma teaser", "Gamma private text",
                     ["Primary Faction 2", "Transversal Faction 1",
                      "Transversal Faction 2", "Secret Faction 3"])

    # ========== SECTION 5: Verify Visibility for Non-Assigned User ==========
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/")

    # Navigate to factions gallery
    page.get_by_role("link", name="Test Larp").click()
    page.get_by_role("link", name="Factions").click()

    # Verify PRIMARY and TRANSVERSAL factions are visible
    expect_normalized(page, page.locator("#one"),
                     "Primary Primary Faction 1 Primary Faction 2 Primary Faction 3")
    expect_normalized(page, page.locator("#one"),
                     "Transversal Transversal Faction 1 Transversal Faction 2 Transversal Faction 3")

    # Verify SECRET factions are NOT visible
    expect(page.locator("#one")).not_to_contain_text("Secret Faction 1")
    expect(page.locator("#one")).not_to_contain_text("Secret Faction 2")
    expect(page.locator("#one")).not_to_contain_text("Secret Faction 3")

    # Open Primary Faction 1 details
    page.get_by_role("link", name="Primary Faction 1").click()

    # Verify PUBLIC teaser is visible
    expect_normalized(page, page.locator("#one"), "PF1 teaser")

    # Verify PUBLIC WritingQuestion answer is visible
    expect_normalized(page, page.locator("#one"), "Public Faction Question")
    expect_normalized(page, page.locator("#one"), "PF1 public answer")

    # Verify PRIVATE text is NOT visible
    expect(page.locator("#one")).not_to_contain_text("PF1 private text")

    # Verify PRIVATE WritingQuestion is NOT visible
    expect(page.locator("#one")).not_to_contain_text("Private Faction Question")
    expect(page.locator("#one")).not_to_contain_text("PF1 private answer")

    # ========== SECTION 6: Reorder Factions (as Organizer) ==========
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "test/manage/writing/factions")

    # Get first faction UUID and move it down (swap with second)
    # The first row should be Primary Faction 1, move it down
    first_row = page.locator("tbody tr").first
    expect(first_row).to_contain_text("Primary Faction 1")

    # Find the down arrow (order=0) button for first faction
    down_button = first_row.locator("a[href*='/order/0']")
    down_button.click()

    # Wait for page reload
    page.wait_for_load_state("networkidle")

    # Verify order changed - Primary Faction 2 should now be first
    go_to(page, live_server, "test/manage/writing/factions")
    new_first_row = page.locator("tbody tr").first
    expect(new_first_row).to_contain_text("Primary Faction 2")

    # ========== SECTION 7: Verify Gallery Order Update (as User) ==========
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/test/factions/")

    # Verify new order reflected in gallery
    # Find Primary section and check first faction link
    primary_factions = page.locator("h2").filter(has_text="Primary").locator("xpath=following-sibling::*")
    first_primary_link = primary_factions.locator("a").first
    expect(first_primary_link).to_have_text("Primary Faction 2")

    # ========== SECTION 8: Assign Character Alpha to User ==========
    logout(page)
    login_orga(page, live_server)

    # Navigate to characters list
    go_to(page, live_server, "test/manage/writing/characters")

    # Find Character Alpha and click to edit
    page.get_by_role("link", name="Character Alpha").click()

    # Assign to user@test.it registration
    # Using the "assigned" field with select2
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("user")
    page.wait_for_timeout(500)
    page.locator(".select2-results__option").filter(has_text="user@test.it").first.click()

    submit_confirm(page)

    # ========== SECTION 9: Verify Visibility with Assigned Character ==========
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/")

    # Navigate to Character Alpha
    page.get_by_role("link", name="Test Larp").click()
    page.get_by_role("link", name="Character Alpha").click()

    # Verify character TEASER is visible
    expect_normalized(page, page.locator("#one"), "Alpha teaser")

    # Verify character PRIVATE TEXT is visible (character is assigned to user)
    expect_normalized(page, page.locator("#one"), "Alpha private text")

    # Verify character has all assigned factions listed
    expect_normalized(page, page.locator("#one"), "Primary Faction 1")
    expect_normalized(page, page.locator("#one"), "Transversal Faction 1")
    expect_normalized(page, page.locator("#one"), "Transversal Faction 2")
    expect_normalized(page, page.locator("#one"), "Transversal Faction 3")

    # Navigate to Primary Faction 1 (via character's faction)
    page.get_by_role("link", name="Primary Faction 1").click()

    # Now verify PRIVATE text is visible (because character belongs to this faction)
    expect_normalized(page, page.locator("#one"), "PF1 teaser")
    expect_normalized(page, page.locator("#one"), "PF1 private text")

    # Verify PUBLIC WritingQuestion is visible
    expect_normalized(page, page.locator("#one"), "Public Faction Question")
    expect_normalized(page, page.locator("#one"), "PF1 public answer")

    # Verify PRIVATE WritingQuestion is visible (character assigned to faction)
    expect_normalized(page, page.locator("#one"), "Private Faction Question")
    expect_normalized(page, page.locator("#one"), "PF1 private answer")

    # Go back to character list
    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="Test Larp").click()

    # Try to access Character Beta (NOT assigned to user)
    page.get_by_role("link", name="Character Beta").click()

    # Verify Beta TEASER is visible
    expect_normalized(page, page.locator("#one"), "Beta teaser")

    # Verify Beta PRIVATE TEXT is NOT visible (not assigned)
    expect(page.locator("#one")).not_to_contain_text("Beta private text")

    # Verify that Secret Factions in Character Alpha's factions are NOT visible
    # (Character Alpha doesn't have secret factions)
    go_to(page, live_server, "/test/factions/")

    # Secret factions should still be hidden in gallery
    expect(page.locator("#one")).not_to_contain_text("Secret Faction 1")
    expect(page.locator("#one")).not_to_contain_text("Secret Faction 2")
    expect(page.locator("#one")).not_to_contain_text("Secret Faction 3")
