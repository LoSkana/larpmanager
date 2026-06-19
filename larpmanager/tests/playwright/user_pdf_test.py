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
Test: PDF generation for character sheets.
Verifies PDF download functionality for character portraits, profiles, complete sheets,
light sheets, and relationship documents.
"""

from typing import Any

import pytest

from larpmanager.tests.utils import (
    check_download,
    check_pdf_zip_download,
    fill_tinymce,
    get_modal_iframe,
    go_to,
    go_to_check,
    just_wait,
    login_orga,
    submit_confirm, save_modal,
)

pytestmark = pytest.mark.e2e


def test_user_pdf(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # activate characters
    go_to(page, live_server, "/test/manage/features/character/on")

    # activate relationships
    go_to(page, live_server, "/test/manage/features/relationships/on")

    # activate pdf
    go_to(page, live_server, "/test/manage/features/print_pdf/on")

    # signup
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Assign character
    go_to(page, live_server, "/test/manage/registrations")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("te")
    edit_iframe.get_by_role("option", name="Test Character").click()
    save_modal(page, edit_iframe)

    # create a second character (no relationship yet)
    go_to(page, live_server, "/test/manage/characters")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Pdf Rel Character")
    save_modal(page, edit_iframe)

    # add the relationship from Test Character (u1) to Pdf Rel Character (u2)
    go_to(page, live_server, "/test/manage/characters")
    page.locator('[id="u1"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    # select Pdf Rel Character from the combobox so the JS creates the rel_u2 section
    edit_iframe.locator("#select2-new_rel_select-container").click()
    edit_iframe.get_by_role("searchbox").fill("pdf")
    edit_iframe.get_by_role("option", name="Pdf Rel Character").click()
    just_wait(edit_iframe)
    fill_tinymce(edit_iframe, "rel_u2", "pdf relationship text")
    save_modal(page, edit_iframe)

    # Set page_css so the "complete sheet" button is shown on the character page
    go_to(page, live_server, "/test/manage/pdf/")
    page.locator("#id_page_css").fill("/* custom css */")
    submit_confirm(page)

    # Go to character, test download pdf
    go_to(page, live_server, "/test/character/u1")

    check_download(page, "Portraits (PDF)")

    check_download(page, "Profiles (PDF)")

    check_download(page, "Download complete sheet")

    check_download(page, "printable sheet")

    # Test orga pdf page: select character, verify HTML test links, and bundle download
    orga_characters_pdf_test(page, live_server)

    # Test player relationship: enable feature, delete orga relationship, add via player
    player_relationship_pdf_test(page, live_server)

    # Test again orga pdf page
    login_orga(page, live_server)
    orga_characters_pdf_test(page, live_server)


def orga_characters_pdf_test(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/pdf/")

    # pick the first real character from the dropdown (skip the disabled placeholder)
    char_uuid = page.locator("#char option:not([disabled])").first.get_attribute("value")
    assert char_uuid, "No characters found in the PDF page dropdown"

    # collect orig URLs for the HTML test links
    test_links = {
        "Complete sheet (Test)": page.locator("a.link", has_text="Complete sheet (Test)").get_attribute("orig"),
        "Lightweight sheet (Test)": page.locator("a.link", has_text="Lightweight sheet (Test)").get_attribute("orig"),
    }

    for label, orig in test_links.items():
        # JS replaces '0/pdf' with '{uuid}/pdf' on change
        url = orig.replace("0/pdf", f"{char_uuid}/pdf")
        go_to_check(page, f"{live_server}{url}")
        body = page.locator("body")
        assert body.inner_text().strip(), f"Empty body for {label} at {url}"


def player_relationship_pdf_test(page: Any, live_server: Any) -> None:
    # Enable player relationships feature
    go_to(page, live_server, "/test/manage/features/player_relationships/on")

    # Delete the orga-created character: this cascades the orga relationship deletion
    go_to(page, live_server, "/test/manage/characters")
    page.get_by_role("row", name="Pdf Rel Character").locator(".fa-trash").click()
    just_wait(page)

    # Create a new target character for the player relationship
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Player Rel Target")
    save_modal(page, edit_iframe)

    # As player (orga user, who has Test Character assigned), add a player relationship
    go_to(page, live_server, "/test/register")
    page.get_by_role("link", name="Relationships").click()
    just_wait(page)

    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_target-container").click()
    page.get_by_role("searchbox").fill("player")
    page.get_by_role("option", name="Player Rel Target").click()
    fill_tinymce(page, "id_text", "player relationship text", show=False)
    submit_confirm(page)

    # Go to character page and verify printable sheet (which now includes relationships) still works
    go_to(page, live_server, "/test/character/u1")
    check_download(page, "printable sheet")
