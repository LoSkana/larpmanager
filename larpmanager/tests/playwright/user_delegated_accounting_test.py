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
Test: Delegated members with accounting features.
Verifies that delegated members can be created and that accounting pages
work correctly when processing delegated member information.
Tests both the /delegated page and /accounting page with delegated members.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_orga, submit

pytestmark = pytest.mark.e2e


def test_user_delegated_accounting(pw_page: Any) -> None:
    """Test delegated members feature with accounting integration.

    This test verifies:
    1. Delegated members feature can be enabled
    2. Delegated members can be created
    3. The /delegated page shows accounting info for delegated members
    4. The /accounting page shows accounting info for delegated members
    5. Can switch to delegated account and access accounting
    6. Can switch back to main account and access accounting
    """
    page, live_server, _ = pw_page

    # Login as organizer
    login_orga(page, live_server)

    # Enable delegated members feature
    go_to(page, live_server, "/manage/features/delegated_members/on")

    # Enable additional features that might be checked in accounting
    go_to(page, live_server, "/manage/features/membership/on")
    go_to(page, live_server, "/manage/features/donate/on")
    go_to(page, live_server, "/manage/features/collection/on")

    # Navigate to delegated members page
    go_to(page, live_server, "/delegated")

    # Create a new delegated member
    page.get_by_role("link", name="Add new").click()
    page.get_by_role("textbox", name="Name (*)", exact=True).click()
    page.get_by_role("textbox", name="Name (*)", exact=True).fill("Child")
    page.get_by_role("textbox", name="Surname (*)").click()
    page.get_by_role("textbox", name="Surname (*)").fill("Test")
    page.get_by_role("checkbox", name="Authorisation").check()
    submit(page)

    # Verify delegated member was created
    go_to(page, live_server, "/delegated")
    expect(page.locator("body")).to_contain_text("Child Test")

    # Navigate to accounting page to verify it works with delegated members
    go_to(page, live_server, "/accounting")
    expect(page.locator("body")).to_contain_text("Accounting")

    # Switch to the delegated account by clicking Login link
    go_to(page, live_server, "/delegated")
    page.get_by_role("link", name="Login").click()

    # Verify we're logged in as the delegated account
    go_to(page, live_server, "/profile")
    expect(page.get_by_role("textbox", name="Name (*)", exact=True)).to_have_value("Child")
    expect(page.get_by_role("textbox", name="Surname (*)")).to_have_value("Test")

    # Test accounting page works when logged in as delegated member
    go_to(page, live_server, "/accounting")
    expect(page.locator("body")).to_contain_text("Accounting")

    # Switch back to main account
    go_to(page, live_server, "/delegated")
    page.get_by_role("link", name="Login").click()

    # Verify we're logged in as the main account
    go_to(page, live_server, "/profile")
    expect(page.get_by_role("textbox", name="Name (*)", exact=True)).to_have_value("Admin")
    expect(page.get_by_role("textbox", name="Surname (*)")).to_have_value("Test")

    # Test accounting page works when back to main account with delegated members
    go_to(page, live_server, "/accounting")
    expect(page.locator("body")).to_contain_text("Accounting")
