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
Test: PDF access for staff members who are not registered to the event.

Verifies that:
1. Staff/organizers can download PDFs from player views even without registration
2. Regular users without registration are redirected to the registration page
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import check_download, go_to, login_orga, login_user, logout, submit_confirm, go_to_check

pytestmark = pytest.mark.e2e


def test_staff_unregistered_can_access_pdf(pw_page: Any) -> None:
    """Test that staff members can download PDFs without being registered."""
    page, live_server, _ = pw_page

    # Login as organizer (staff)
    login_orga(page, live_server)

    # Activate character feature
    go_to(page, live_server, "/test/manage/features/character/on")

    # Activate relationships feature
    go_to(page, live_server, "/test/manage/features/relationships/on")

    # Activate PDF printing feature
    go_to(page, live_server, "/test/manage/features/print_pdf/on")

    # Create a character (staff can do this without being registered)
    go_to(page, live_server, "/test/manage/characters")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("Test Staff Character")
    submit_confirm(page)

    # Get the character ID from the URL
    character_url = page.locator(".fa-edit").first.locator('..').get_attribute("href")
    character_id = character_url.split("/")[-3]

    # Try to access the character page from player view
    # Staff should be able to access this even without registration
    go_to(page, live_server, f"/test/character/{character_id}")

    # Verify staff can download PDFs without being registered
    # These should all work without redirecting to registration page
    check_download(page, "Download complete sheet")
    check_download(page, "Download light sheet")
    check_download(page, "Download relationships")

    download_page = page.locator(f"text=Download complete sheet").get_attribute("href")

    # Now test that regular users without registration are redirected to registration page
    login_user(page, live_server)

    # Try to access the character page as a non-registered user
    # This should redirect to the registration page
    go_to(page, live_server, f"/test/character/{character_id}")

    go_to(page, live_server, download_page)

    # Verify we are redirected to the registration page
    expect(page).to_have_url(f"{live_server}/test/register/")

    # Verify we see the registration prompt message
    expect(page.locator("#banner")).to_contain_text("Register - Test Larp")
