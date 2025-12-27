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

"""Playwright tests for additional tickets feature."""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_orga, login_user, logout, submit_confirm

pytestmark = pytest.mark.e2e


def test_additional_tickets_full_workflow(pw_page: Any) -> None:
    """Test complete workflow for additional tickets feature.

    Tests:
    - Enabling additional tickets feature
    - Configuring ticket price
    - User registration with different numbers of additional tickets
    - Price calculation including additional tickets
    - Display in organizer dashboard
    - Editing additional tickets count
    """
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Enable additional tickets feature and configure ticket
    enable_additional_tickets_feature(page, live_server)

    # Test user registration with 3 additional tickets
    registration_with_additionals(page, live_server)

    # Verify organizer can see additional tickets count
    verify_organizer_view(page, live_server)

    # Test editing additional tickets
    edit_additionals(page, live_server)

    # Test edge cases
    additional_tickets_edge_cases(page, live_server)


def enable_additional_tickets_feature(page: Any, live_server: Any) -> None:
    """Enable additional tickets feature and configure ticket price."""
    go_to(page, live_server, "test/manage")

    # Enable additional tickets feature
    page.get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Additional tickets").check()
    page.get_by_role("button", name="Confirm").click()

    # Verify feature is enabled and form question is created
    page.locator("#orga_registration_form").get_by_role("link", name="Form").click()
    expect(page.locator("#one")).to_contain_text("Additional")

    # Configure ticket price
    go_to(page, live_server, "test/manage")
    page.locator("#orga_registration_tickets").get_by_role("link", name="Tickets").click()
    page.locator('[id="u1"]').get_by_role("link", name="").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("50")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("Standard ticket with meals")
    page.get_by_role("button", name="Confirm").click()


def registration_with_additionals(page: Any, live_server: Any) -> None:
    """Test user registration with additional tickets."""
    # Navigate to registration page
    go_to(page, live_server, "test/")
    page.get_by_role("link", name="Register").click()

    # Select 3 additional tickets
    page.get_by_label("Additional").select_option("3")

    # Continue to summary
    page.get_by_role("button", name="Continue").click()

    # Verify price calculation: 50€ (base) + 150€ (3 additional) = 200€
    expect(page.locator("#riepilogo")).to_contain_text("200€")

    # Confirm registration
    page.get_by_role("button", name="Confirm").click()

    # Verify registration confirmation shows correct total
    go_to(page, live_server, "accounting/")
    expect(page.locator("#one")).to_contain_text("200€")


def verify_organizer_view(page: Any, live_server: Any) -> None:
    """Verify organizer can see additional tickets in registrations list."""
    go_to(page, live_server, "test/manage/registrations/")

    # Verify additional tickets column is visible
    page.locator("#one").get_by_role("link", name="Additional").click()
    expect(page.locator("#one")).to_contain_text("3")


def edit_additionals(page: Any, live_server: Any) -> None:
    """Test editing additional tickets count after registration."""
    # Open the registration for editing
    go_to(page, live_server, "test/manage/registrations/")
    page.locator('[id="u1"]').get_by_role("link", name="").click()

    # Change additional tickets from 3 to 2
    page.locator("#id_additionals").fill("2")

    # Save changes
    submit_confirm(page)

    # Verify new price: 50€ (base) + 100€ (2 additional) = 150€
    go_to(page, live_server, "test/manage/registrations/")
    page.locator("#one").get_by_role("link", name="Additional").click()
    expect(page.locator("#one")).to_contain_text("2")


def additional_tickets_edge_cases(page: Any, live_server: Any) -> None:
    """Test edge cases for additional tickets feature."""
    # Test with 0 additional tickets (just base ticket)
    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "test/register/")

    # Don't select any additional tickets (default should be none/0)
    page.get_by_role("button", name="Continue").click()

    # Verify price is just the base ticket: 50€
    expect(page.locator("#riepilogo")).to_contain_text("50€")
    page.get_by_role("button", name="Confirm").click()

    # Test with maximum (5) additional tickets
    logout(page)
    login_orga(page, live_server)

    go_to(page, live_server, "test/register/")

    # Select maximum 5 additional tickets
    page.get_by_label("Additional").select_option("5")
    page.get_by_role("button", name="Continue").click()

    # Verify price: 50€ (base) + 250€ (5 additional) = 300€
    expect(page.locator("#riepilogo")).to_contain_text("300€")
    page.get_by_role("button", name="Confirm").click()


def test_additional_tickets_with_other_options(pw_page: Any) -> None:
    """Test additional tickets combined with other registration options.

    Tests interaction between additional tickets and:
    - Pay what you want donations
    - Registration options/surcharges
    - Ticket pricing
    """
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Enable multiple features
    go_to(page, live_server, "test/manage")
    page.get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Additional tickets").check()
    page.get_by_role("checkbox", name="Pay what you want").check()
    page.get_by_role("button", name="Confirm").click()

    # Set ticket price
    page.locator("#orga_registration_tickets").get_by_role("link", name="Tickets").click()
    page.locator('[id="u1"]').get_by_role("link", name="").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("30")
    page.get_by_role("button", name="Confirm").click()

    # Register with both additional tickets and pay what you want
    go_to(page, live_server, "test/")
    page.get_by_role("link", name="Register").click()

    # Select 2 additional tickets
    page.get_by_label("Additional").select_option("2")

    # Add pay what you want donation
    page.get_by_role("spinbutton", name="Pay what you want").click()
    page.get_by_role("spinbutton", name="Pay what you want").fill("10")

    page.get_by_role("button", name="Continue").click()

    # Verify total: 30€ (base) + 60€ (2 additional) + 10€ (donation) = 100€
    expect(page.locator("#riepilogo")).to_contain_text("100€")
    page.get_by_role("button", name="Confirm").click()

    # Verify in organizer view
    go_to(page, live_server, "test/manage/registrations/")
    page.locator("#one").get_by_role("link", name="Additional").click()
    expect(page.locator("#one")).to_contain_text("2")


def test_additional_tickets_disabled_without_feature(pw_page: Any) -> None:
    """Test that additional tickets field doesn't appear when feature is disabled."""
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Make sure additional tickets feature is disabled
    go_to(page, live_server, "test/manage")
    page.get_by_role("link", name="Features").click()

    # Uncheck additional tickets if it's checked
    if page.get_by_role("checkbox", name="Additional tickets").is_checked():
        page.get_by_role("checkbox", name="Additional tickets").uncheck()
        page.get_by_role("button", name="Confirm").click()

    # Navigate to registration
    go_to(page, live_server, "test/")
    page.get_by_role("link", name="Register").click()

    # Verify additional tickets field is not present
    expect(page.locator("body")).not_to_contain_text("Additional")

    # Verify form can still be submitted
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm").click()

    # Verify registration succeeded
    expect(page.locator("#one")).to_be_visible()
