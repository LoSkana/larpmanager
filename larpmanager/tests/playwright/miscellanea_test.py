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
Test: Miscellanea tests that don't fit a single test suite
- Check user fees are shown
- Check require login / register in events
- Check that organizers can access gallery regardless of restrictions
- Check reset cache
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    check_feature,
    expect_normalized,
    go_to,
    just_wait,
    login_orga,
    login_user,
    logout,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def test_miscellanea(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/manage/")

    # Test gallery hide configs
    gallery_hide_configs(live_server, page)

    # Test event / assocs resets
    reset_caches(live_server, page)

    # check shows fee
    check_user_fee(live_server, page)


def check_user_fee(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/manage/")
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    check_feature(page, "Payments")
    submit_confirm(page)
    page.get_by_role("checkbox", name="Wire").check()
    just_wait(page)
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("aaaa")
    page.locator("#id_wire_fee").click()
    page.locator("#id_wire_fee").fill("2")
    page.locator("#id_wire_payee").click()
    page.locator("#id_wire_payee").fill("2asdsadas")
    page.locator("#id_wire_iban").click()
    page.locator("#id_wire_iban").fill("3sadsadsa")
    page.locator("#id_wire_bic").fill("test iban")
    submit_confirm(page)
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    check_feature(page, "Donation")
    submit_confirm(page)
    page.locator("#exe_config").get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name="Payments ").click()
    page.locator("#id_payment_fees_user").check()
    submit_confirm(page)
    page.get_by_role("link", name=" Accounting").click()
    page.get_by_role("link", name="follow this link").click()
    expect_normalized(
        page,
        page.locator("#wrapper"),
        "Indicate the amount of your donation: Please enter the occasion for which you wish to make "
        "the donation Choose the payment method: Wire Fee: +2% aaaa",
    )


def gallery_hide_configs(live_server: Any, page: Any) -> None:
    """Test gallery_hide_login and gallery_hide_signup configurations."""

    # create event
    go_to(page, live_server, "/manage/events/")
    page.get_by_role("link", name="New event").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Test Access")

    page.locator("#id_development").select_option("1")
    page.locator("#id_start").fill("2055-06-11")
    just_wait(page)
    page.locator("#id_start").click()
    page.locator("#id_end").fill("2055-06-13")
    just_wait(page)
    page.locator("#id_end").click()
    submit_confirm(page)

    # Verify we're on the new event
    go_to(page, live_server, "/testaccess/manage/")

    # Enable Characters feature
    page.get_by_role("link", name="Features").first.click()
    check_feature(page, "Characters")
    submit_confirm(page)

    # Create a test character to have something in the gallery
    page.locator("#orga_characters").get_by_role("link", name="Characters").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Test Gallery Character")
    submit_confirm(page)

    # Test 1: Gallery should be visible without any restrictions
    logout(page)
    go_to(page, live_server, "/testaccess/")
    expect_normalized(page, page.locator("body"), "Test Gallery Character")

    # Test 2: Enable gallery_hide_login and verify non-authenticated users cannot access
    login_orga(page, live_server)
    go_to(page, live_server, "/testaccess/manage/")
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name="Gallery ").click()
    page.locator("#id_gallery_hide_login").check()
    submit_confirm(page)

    # Logout and try to access gallery - should be redirected
    logout(page)
    go_to(page, live_server, "/testaccess/")

    # Should be redirected to register page with warning message
    expect_normalized(page, page.locator("body"), "Login")
    expect(page.locator("#one")).not_to_contain_text("Test Gallery Character")

    # Login as regular user and verify access is now allowed
    login_user(page, live_server)
    go_to(page, live_server, "/testaccess/")
    expect_normalized(page, page.locator("body"), "Test Gallery Character")

    # Test 3: Enable gallery_hide_signup and verify non-registered users cannot access
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/testaccess/manage/")
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name="Gallery ").click()
    page.locator("#id_gallery_hide_login").uncheck()
    page.locator("#id_gallery_hide_signup").check()
    submit_confirm(page)

    # Logout and login as regular user who is NOT registered
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/testaccess/")

    # Should be redirected with warning message
    expect_normalized(page, page.locator("body"), "Register")
    expect(page.locator("#one")).not_to_contain_text("Test Gallery Character")

    # Register the user to the event
    page.get_by_role("link", name="Register").click()
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Now user is registered, they should be able to access the gallery
    go_to(page, live_server, "/testaccess/")
    expect_normalized(page, page.locator("body"), "Test Gallery Character")

    # Delete registration and verify access is denied again
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/testaccess/manage/")
    page.locator("#orga_registrations").get_by_role("link", name="Registrations").click()
    # Find and delete the user's registration
    page.locator("a:has(i.fas.fa-edit)").click()
    page.get_by_role("link", name="Delete").click()
    just_wait(page)
    page.get_by_role("button", name="Confirmation delete").click()

    # Logout and login as user - now without registration
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/testaccess/")

    # Should be redirected because user is no longer registered
    expect_normalized(page, page.locator("body"), "Register")
    expect(page.locator("#one")).not_to_contain_text("Test Gallery Character")

    # Test 4: Both configs enabled - must be logged in AND registered
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/testaccess/manage/")
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name="Gallery ").click()
    page.locator("#id_gallery_hide_login").check()
    page.locator("#id_gallery_hide_signup").check()
    submit_confirm(page)

    # Logout and try to access - should be blocked (not logged in)
    logout(page)
    go_to(page, live_server, "/testaccess/")
    expect_normalized(page, page.locator("body"), "Login")
    expect(page.locator("#one")).not_to_contain_text("Test Gallery Character")

    # login as user - now without registration
    login_user(page, live_server)
    go_to(page, live_server, "/testaccess/")

    # Should be redirected because user is no longer registered
    expect_normalized(page, page.locator("body"), "Register")
    expect(page.locator("#one")).not_to_contain_text("Test Gallery Character")

    # Register again
    page.get_by_role("link", name="Register").click()
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Now can access again
    go_to(page, live_server, "/testaccess/")
    expect_normalized(page, page.locator("body"), "Test Gallery Character")

    # Test 5: Orga can access even with both configs enabled and without being registered
    login_orga(page, live_server)

    # Verify both configs are still enabled
    go_to(page, live_server, "/testaccess/manage/")
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name="Gallery ").click()
    expect(page.locator("#id_gallery_hide_login")).to_be_checked()
    expect(page.locator("#id_gallery_hide_signup")).to_be_checked()

    # Verify orga is NOT registered to the event
    go_to(page, live_server, "/testaccess/manage/")
    page.locator("#orga_registrations").get_by_role("link", name="Registrations").click()
    # Check that "Admin Test" (orga user) is NOT in the registrations list
    expect(page.locator("#one")).not_to_contain_text("Admin Test")

    # Now go to gallery - orga should have access even without being registered
    go_to(page, live_server, "/testaccess/")
    expect_normalized(page, page.locator("body"), "Test Gallery Character")

    # Cleanup: Disable both configs
    go_to(page, live_server, "/testaccess/manage/")
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name="Gallery ").click()
    page.locator("#id_gallery_hide_login").uncheck()
    page.locator("#id_gallery_hide_signup").uncheck()
    submit_confirm(page)


def reset_caches(live_server, page):
    """Test cache reset for run, text fields, and registration fields."""

    # Test event-level reset
    go_to(page, live_server, "/test/manage/")

    page.get_by_role("link", name="Reset Cache").click()
    expect_normalized(page, page.locator("#banner"), "Dashboard")

    # Test association-level cache reset
    go_to(page, live_server, "/manage/")

    page.get_by_role("link", name="Reset Cache").click()
    expect_normalized(page, page.locator("#banner"), "Dashboard")
