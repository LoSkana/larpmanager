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
Test: Character customization feature.
Verifies activation of character customization, configuration of all custom fields
(name, pronoun, song, public text, private text, profile image), character assignment
to user, user filling customization form including image upload via AJAX, and verification
of public and private field visibility for both regular users and organizers.
"""
import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    expect_normalized,
    go_to,
    just_wait,
    load_image,
    login_orga,
    login_user,
    submit_confirm, logout,
)

pytestmark = pytest.mark.e2e


def test_character_customization(pw_page: Any) -> None:
    """Test complete character customization workflow."""
    page, live_server, _ = pw_page

    # Setup: activate features and configure customization fields
    login_orga(page, live_server)
    activate_customization(page, live_server)
    configure_customization_fields(page, live_server)

    # Create and assign character to user
    create_and_assign_character(page, live_server)

    # User fills customization form
    fill_customization_form(page, live_server)

    # Verify field visibility
    verify_field_visibility(page, live_server)


def activate_customization(page: Any, live_server: Any) -> None:
    """Activate character feature and user character feature."""
    # Activate characters
    go_to(page, live_server, "/test/manage/features/character/on")

    go_to(page, live_server, "/test/manage/features/user_character/on")

    # Activate user character (player editor)
    go_to(page, live_server, "/test/manage/features/custom_character/on")


def configure_customization_fields(page: Any, live_server: Any) -> None:
    """Configure all customization fields in event config."""
    go_to(page, live_server, "/test/manage/config")

    # Navigate to character customization section
    page.get_by_role("link", name=re.compile(r"^Character customisation ")).click()

    # Enable all custom character fields
    page.locator("#id_custom_character_name").check()
    page.locator("#id_custom_character_pronoun").check()
    page.locator("#id_custom_character_song").check()
    page.locator("#id_custom_character_public").check()
    page.locator("#id_custom_character_private").check()
    page.locator("#id_custom_character_profile").check()

    submit_confirm(page)


def create_and_assign_character(page: Any, live_server: Any) -> None:
    """Create a character and assign it to user test."""
    go_to(page, live_server, "/test/manage/characters")
    just_wait(page)

    # Edit character
    page.locator(".fa-edit").click(force=True)

    # Assign to user test
    page.locator("#select2-id_player-container").click()
    page.get_by_role("searchbox").fill("user")
    page.get_by_role("option", name="User Test - user@test.it").click()

    submit_confirm(page)
    just_wait(page)

    # Register user to event
    login_user(page, live_server)
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

def fill_customization_form(page: Any, live_server: Any) -> None:
    """Fill all customization form fields including image upload."""
    go_to(page, live_server, "/test")
    just_wait(page)

    # Access character customization
    page.get_by_role("link", name="Test Character").first.click()
    just_wait(page)

    # Click customize button
    page.get_by_role("link", name="Customize").click()
    just_wait(page)

    # Fill custom name
    page.locator("#id_custom_name").click()
    page.locator("#id_custom_name").fill("My Custom Name")

    # Fill custom pronoun
    page.locator("#id_custom_pronoun").click()
    page.locator("#id_custom_pronoun").fill("they/them")

    # Fill custom song URL
    page.locator("#id_custom_song").click()
    page.locator("#id_custom_song").fill("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    # Fill custom public text
    page.locator("#id_custom_public").click()
    page.locator("#id_custom_public").fill("This is my public character description. Everyone can see this!")

    # Fill custom private text
    page.locator("#id_custom_private").click()
    page.locator("#id_custom_private").fill("This is my private character note. Only I and organizers can see this.")

    # Upload character profile image
    page.locator("#change_photo").click(force=True)
    load_image(page, "#id_image")

    # Wait for AJAX upload to complete
    page.wait_for_load_state("networkidle")
    just_wait(page)

    # Verify image was uploaded by checking if profile image is visible
    expect(page.locator("#profile")).to_be_visible()

    submit_confirm(page)
    just_wait(page)


def verify_field_visibility(page: Any, live_server: Any) -> None:
    """Verify that public and private fields are visible correctly."""
    # Verify customization was saved
    expect_normalized(page, page.locator("body"), "My Custom Name")

    # Check that public field is visible
    expect_normalized(page, page.locator("body"), "This is my public character description")

    # Check that private field is visible
    expect_normalized(page, page.locator("body"), "This is my private character note")

    # Check pronoun is visible
    expect_normalized(page, page.locator("body"), "they/them")

    # Verify profile image is visible (if implemented in the character view)
    avatar = page.locator("#char_profile")
    expect(avatar).to_be_visible()
    expect(avatar).not_to_have_attribute(
        "src",
        r"assets/blank-avatar\.svg"
    )

    # Now logout to check visibility
    logout(page)
    go_to(page, live_server, "/test")
    page.get_by_text("My Custom Name").click()

    # Verify public field is visible to other users, but not private
    expect_normalized(page, page.locator("body"), "This is my public character description")
    expect(page.locator("body")).not_to_contain_text("private")

    # Verify orga can see private field (as staff)
    login_orga(page, live_server)
    go_to(page, live_server, "/test/")
    just_wait(page)

    # Find and view character
    page.get_by_text("My Custom Name").click()
    just_wait(page)

    # Organizers should be able to see both public and private
    expect_normalized(page, page.locator("body"), "This is my public character description")
    expect_normalized(page, page.locator("body"), "This is my private character note")


def verify_characters_shortcut(page: Any, live_server: Any) -> None:
    """Enable the user_characters_shortcut configuration."""

    # Enable characters shortcut
    login_orga(page, live_server)
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name="Interface ").click()
    page.locator("#id_user_characters_shortcut").check()
    submit_confirm(page)

    # Verify the Characters link is visible in the topbar
    login_user(page, live_server)
    go_to(page, live_server, "/")
    just_wait(page)
    characters_link = page.locator("a[href='/characters']").filter(has_text="Characters")
    expect(characters_link).to_be_visible()

    # Click the characters link
    characters_link.click()
    just_wait(page)

    # Verify we're on the characters page
    expect(page).to_have_url(f"{live_server.url}/characters")

    # Verify the page shows characters content
    expect_normalized(page, page.locator("#one"), "Character")

    expect_normalized(page, page.locator("#one"), "character active last event character active last event my character test larp")
