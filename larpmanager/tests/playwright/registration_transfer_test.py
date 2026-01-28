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
Test: Registration transfer between events
- Create two events with tickets and registration questions
- Copy tickets and questions from first event to second
- Create signup for user@test.it in first event
- Transfer registration to second event
- Verify tickets and options are maintained
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    expect_normalized,
    go_to,
    just_wait,
    login_orga,
    login_user,
    logout,
    submit_confirm, new_option, submit_option,
)

pytestmark = pytest.mark.e2e


def test_registration_transfer(pw_page: Any) -> None:
    """Test registration transfer between events with tickets and form questions. """

    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Create first event
    create_event_a(page, live_server)

    # Create second event
    create_event_b(page, live_server)

    # Copy tickets and questions from Event A to Event B
    copy_tickets_and_questions(page, live_server)

    # Create signup for user@test.it in Event A
    create_signup_event_a(page, live_server)

    # Transfer registration to Event B
    transfer_registration(page, live_server)

    # Verify transfer was successful
    verify_transfer(page, live_server)


def create_event_a(page: Any, live_server: Any) -> None:
    """Create Event A with ticket and registration questions."""
    go_to(page, live_server, "/manage/events/")
    page.get_by_role("link", name="New event").click()
    page.locator("#id_form1-name").fill("Event A")

    page.locator("#id_form2-development").select_option("1")
    page.locator("#id_form2-start").fill("2055-06-11")
    page.locator("#id_form2-start").click()
    just_wait(page)
    page.locator("#id_form2-end").fill("2055-06-13")
    page.locator("#id_form2-end").click()
    just_wait(page)
    submit_confirm(page)

    # Create ticket with price and limit
    go_to(page, live_server, "/eventa/manage/tickets/")
    page.locator("a:has(i.fas.fa-edit)").click()
    page.locator("#id_name").fill("Premium Ticket")
    page.locator("#id_price").fill("100.00")
    page.locator("#id_max_available").fill("10")
    submit_confirm(page)

    # Create a second ticket
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("Standard Ticket")
    page.locator("#id_price").fill("50.00")
    page.locator("#id_max_available").fill("20")
    submit_confirm(page)

    # Create registration questions
    go_to(page, live_server, "/eventa/manage/form/")

    # Add text question
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_name").fill("Dietary restrictions")
    page.locator("#id_description").fill("Please specify any dietary restrictions")
    submit_confirm(page)

    # Add single choice question with options
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("s")
    page.locator("#id_name").fill("T-shirt size")
    page.locator("#id_description").fill("Select your t-shirt size")

    # Add options
    iframe = new_option(page)
    iframe.locator("#id_name").fill("Small")
    iframe.locator("#id_description").fill("Small size")
    submit_option(page, iframe)

    iframe = new_option(page)
    iframe.locator("#id_name").fill("Medium")
    iframe.locator("#id_description").fill("Medium size")
    iframe.locator("#id_price").fill("5.00")
    submit_option(page, iframe)

    iframe = new_option(page)
    iframe.locator("#id_name").fill("Large")
    iframe.locator("#id_description").fill("Large size")
    iframe.locator("#id_price").fill("10.00")
    iframe.locator("#id_max_available").fill("5")
    submit_option(page, iframe)

    submit_confirm(page)

    # Add multiple choice question
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("m")
    page.locator("#id_name").fill("Workshop preferences")
    page.locator("#id_description").fill("Select your preferred workshops")
    page.locator("#id_max_length").fill("2")

    # Add options
    iframe = new_option(page)
    iframe.locator("#id_name").fill("Combat")
    iframe.locator("#id_description").fill("Combat workshop")
    iframe.locator("#id_price").fill("15.00")
    submit_option(page, iframe)

    iframe = new_option(page)
    iframe.locator("#id_name").fill("Makeup")
    iframe.locator("#id_description").fill("Makeup workshop")
    iframe.locator("#id_price").fill("20.00")
    submit_option(page, iframe)

    iframe = new_option(page)
    iframe.locator("#id_name").fill("Crafting")
    iframe.locator("#id_description").fill("Crafting workshop")
    iframe.locator("#id_price").fill("10.00")
    submit_option(page, iframe)

    submit_confirm(page)


def create_event_b(page: Any, live_server: Any) -> None:
    """Create Event B."""
    go_to(page, live_server, "/manage/events/")
    page.get_by_role("link", name="New event").click()
    page.locator("#id_form1-name").fill("Event B")

    page.locator("#id_form2-development").select_option("1")
    page.locator("#id_form2-start").fill("2055-07-11")
    just_wait(page)
    page.locator("#id_form2-start").click()
    page.locator("#id_form2-end").fill("2055-07-13")
    just_wait(page)
    page.locator("#id_form2-end").click()
    submit_confirm(page)


def copy_tickets_and_questions(page: Any, live_server: Any) -> None:
    """Copy tickets and registration questions from Event A to Event B."""
    go_to(page, live_server, "/eventb/manage/")

    # Activate copy
    page.get_by_role("link", name="Features").first.click()
    page.locator("div.feature_checkbox", has_text="Copy").locator("input[type='checkbox']").check()
    submit_confirm(page)

    # Navigate to copy page
    page.locator("#orga_copy").get_by_role("link", name="Copy").click()

    # Select Event A as source
    page.locator("#select2-id_parent-container").click()
    page.get_by_role("searchbox").fill("eve")
    page.get_by_role("option", name="Event A").click()

    # Select tickets and registration form
    page.get_by_role("checkbox", name="Registration Tickets").check()
    page.get_by_role("checkbox", name="Registration questions and options").check()

    submit_confirm(page)

    # Verify tickets were copied
    go_to(page, live_server, "/eventb/manage/tickets/")
    expect_normalized(page, page.locator("#one"), "Premium Ticket")
    expect_normalized(page, page.locator("#one"), "Standard Ticket")
    expect_normalized(page, page.locator("#one"), "100")
    expect_normalized(page, page.locator("#one"), "50")

    # Verify form questions were copied
    go_to(page, live_server, "/eventb/manage/form/")
    expect_normalized(page, page.locator("#one"), "Dietary restrictions")
    expect_normalized(page, page.locator("#one"), "T-shirt size")
    expect_normalized(page, page.locator("#one"), "Workshop preferences")


def create_signup_event_a(page: Any, live_server: Any) -> None:
    """Create a signup for user@test.it in Event A."""
    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/eventa/register/")

    # Select Standard Ticket
    page.get_by_label("Ticket").select_option(label="Standard Ticket - 50€ - (Available: 20)")

    # Fill in dietary restrictions
    page.get_by_role("textbox", name="Dietary restrictions").fill("Vegetarian")

    # Select Medium t-shirt
    page.get_by_label("T-shirt size").select_option(label="Large (10€) - (Available 5)")

    # Select workshops (Combat and Crafting)
    page.get_by_role("checkbox", name="Combat (15€)").check()
    page.get_by_role("checkbox", name="Crafting (10€)").check()

    page.get_by_role("button", name="Continue").click()

    # Verify price: 50 (ticket) + 10 (large) + 15 (combat) + 10 (crafting) = 80
    expect_normalized(page, page.locator("#riepilogo"), "85")

    submit_confirm(page)


def transfer_registration(page: Any, live_server: Any) -> None:
    """Transfer the registration from Event A to Event B."""
    logout(page)
    login_orga(page, live_server)

    go_to(page, live_server, "/eventa/manage/registrations/")

    # Navigate to transfer page
    page.get_by_role("link", name="Transfer").click()

    # Select the registration (should be only one)
    page.locator("#select2-id_registration_id-container").click()
    page.get_by_role("searchbox").fill("user")
    page.get_by_role("option", name="event a - user test").click()

    # Select Event B as target
    page.locator("#select2-id_target_run_id-container").click()
    page.get_by_role("searchbox").fill("eve")
    page.get_by_role("option", name="Event b").click()

    # Submit to preview
    page.get_by_role("button", name="Preview").click()

    # Confirm transfer
    page.get_by_role("button", name="Transfer").click()


def verify_transfer(page: Any, live_server: Any) -> None:
    """Verify the registration was transferred correctly."""
    # Check in Event B registrations
    go_to(page, live_server, "/eventb/manage/registrations/")

    # Should see the transferred registration
    expect_normalized(page, page.locator("#one"), "User Test")

    # Click to edit and verify details
    page.locator("a:has(i.fas.fa-edit)").click()

    # Verify ticket type is maintained (Standard Ticket)
    expect(page.locator("#id_ticket option:checked")).to_have_text("Standard Ticket - 50€")

    # Verify dietary restrictions answer
    expect(page.locator("#id_que_u8")).to_have_value("Vegetarian")

    # Verify t-shirt size (Medium)
    expect_normalized(page, page.locator("#main_form"), "Large (10€)")

    # Verify workshop selections (Combat and Crafting)
    expect(page.get_by_role("checkbox", name="Combat (15€)")).to_be_checked()
    expect(page.get_by_role("checkbox", name="Crafting (10€)")).to_be_checked()
    expect(page.get_by_role("checkbox", name="Makeup (20€)")).not_to_be_checked()

    # Verify Event A no longer has the registration
    go_to(page, live_server, "/eventa/manage/registrations/")
    expect(page.locator("#one")).not_to_contain_text("User Test")
