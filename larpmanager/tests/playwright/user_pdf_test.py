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

from larpmanager.tests.utils import check_download, fill_tinymce, go_to, go_to_check, login_orga, submit_confirm

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
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="Test Character").click()
    submit_confirm(page)

    # Go to character, test download pdf
    go_to(page, live_server, "/test/character/u1")

    check_download(page, "Portraits (PDF)")

    check_download(page, "Profiles (PDF)")

    check_download(page, "Download complete sheet")

    check_download(page, "Download light sheet")

    check_download(page, "Download relationships")

    # Test orga pdf page: select character and verify HTML test links produce content
    orga_characters_pdf_test(page, live_server)


def orga_characters_pdf_test(page: Any, live_server: Any) -> None:
    # create a second character with a relationship to Test Character so the
    # relationships PDF page has content to render
    go_to(page, live_server, "/test/manage/characters")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("Pdf Rel Character")
    page.get_by_role("combobox").click()
    page.get_by_role("searchbox").fill("test")
    page.get_by_role("option", name="Test Character").click()
    fill_tinymce(page, "rel_u1", "pdf relationship text")
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/pdf/")

    # pick the first real character from the dropdown (skip the disabled placeholder)
    char_uuid = page.locator("#char option:not([disabled])").first.get_attribute("value")
    assert char_uuid, "No characters found in the PDF page dropdown"

    # collect orig URLs for the three HTML test links
    test_links = {
        "Complete sheet (Test)": page.locator("a.link", has_text="Complete sheet (Test)").get_attribute("orig"),
        "Lightweight sheet (Test)": page.locator("a.link", has_text="Lightweight sheet (Test)").get_attribute("orig"),
        "Relationships (Test)": page.locator("a.link", has_text="Relationships (Test)").get_attribute("orig"),
    }

    for label, orig in test_links.items():
        # JS replaces '0/pdf' with '{uuid}/pdf' on change
        url = orig.replace("0/pdf", f"{char_uuid}/pdf")
        go_to_check(page, f"{live_server}{url}")
        body = page.locator("body")
        assert body.inner_text().strip(), f"Empty body for {label} at {url}"
