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
Test: Registration form with section, ticket selection, allowed selection.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (just_wait,
                                     go_to,
                                     load_image,
                                     login_orga,
                                     login_user,
                                     logout,
                                     submit_confirm,
                                     expect_normalized, fill_tinymce, check_feature,
                                     )

pytestmark = pytest.mark.e2e


def test_orga_section_form(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Go to event
    page.get_by_role("link", name="").click()
    page.get_by_role("link", name=" Test Larp").click()

    # Activate section feature
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Sections").check()
    page.get_by_role("button", name="Confirm").click()

    # Create first section
    page.get_by_role("link", name="+ New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Preferences")
    page.locator("#id_name").press("Tab")
    fill_tinymce(page, "id_description", "What you prefer", show=False)
    page.get_by_text("After confirmation, add").click()
    page.get_by_role("button", name="Confirm").click()

    # Create second section
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Needs")
    page.locator("#id_name").press("Tab")
    fill_tinymce(page, "id_description", "What you need", show=False)
    page.get_by_role("button", name="Confirm").click()

    # Check reordering
    expect_normalized(page, page.locator("#registration_sections_wrapper"), "Preferences Needs")
    page.get_by_role("link", name="").click()
    expect_normalized(page, page.locator("#one"), "Needs Preferences")

    # Add one question for each section
    page.get_by_role("link", name="Form").click()
    page.get_by_role("link", name="+ New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_name").click()
    page.get_by_text("Question type").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Food")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("fooood")
    page.get_by_role("cell", name="--- Empty The question will").click()
    page.get_by_role("searchbox").fill("pre")
    page.get_by_role("option", name="Preferences").click()
    page.get_by_text("After confirmation, add").click()
    page.get_by_role("button", name="Confirm").click()

    # Second question for second section
    page.locator("#id_typ").select_option("t")
    page.locator("#id_description").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("sleep")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("sleeeep")
    page.get_by_role("cell", name="--- Empty The question will").click()
    page.get_by_role("searchbox").fill("nee")
    page.get_by_role("option", name="Needs").click()
    page.get_by_role("button", name="Confirm").click()

    # Check signup
    go_to(page, live_server, "/test/register")

    page.get_by_role("link", name="Needs ").click()
    page.get_by_role("link", name="Preferences ").click()

    expect_normalized(page, page.locator("#register_form"),
    "Ticket (*) Standard Your registration ticket Needs What you need sleep sleeeep Preferences What you prefer Food fooood")

    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Form").click()

    # check section is still available
    page.locator("#registration_questions_Needs").get_by_role("link", name="").click()
    expect(page.locator("#select2-id_section-container")).to_match_aria_snapshot("- textbox \"Needs\"")

    # Reorder sections, check they are updated
    page.get_by_role("link", name="Sections").click()
    page.get_by_role("link", name="").click()

    go_to(page, live_server, "/test/register")
    page.get_by_role("link", name="Needs ").click()
    page.get_by_role("link", name="Preferences ").click()
    expect_normalized(page, page.locator("#register_form"),
    "Ticket (*) Standard Your registration ticket Preferences What you prefer Food fooood Needs What you need sleep sleeeep")

    # Activate ticket selection / allowed selection
    go_to(page, live_server, "/test/manage/")
    page.locator("#orga_config").get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name="Registrations ").click()
    page.locator("#id_registration_reg_que_allowed").check()
    page.locator("#id_registration_reg_que_tickets").check()
    page.get_by_role("button", name="Confirm").click()

    # Create new ticket
    page.locator("#orga_registration_tickets").get_by_role("link", name="Tickets").click()
    page.get_by_role("link", name="+ New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Depends")
    page.get_by_role("button", name="Confirm").click()

    # Select ticket as dependent
    page.get_by_role("link", name="Form").click()
    page.locator("#registration_questions_Preferences").get_by_role("link", name="").click()
    page.get_by_role("row", name="Ticket list If you select one").get_by_role("searchbox").click()
    page.get_by_role("row", name="Ticket list If you select one").get_by_role("searchbox").fill("de")
    page.get_by_role("option", name="Test Larp (Standard) Depends").click()
    page.get_by_role("button", name="Confirm").click()

    # Check signup
    go_to(page, live_server, "/test/register/")

    # whole section not visible
    expect(page.get_by_role("link", name="Preferences ")).not_to_be_visible()
    expect(page.get_by_role("cell", name="fooood")).not_to_be_visible()
    expect(page.get_by_text("What you prefer Food fooood")).not_to_be_visible()

    # select ticket
    page.get_by_label("Ticket (*)").select_option("u2")

    # section and field are visible
    expect(page.get_by_role("link", name="Preferences ")).to_be_visible()
    page.get_by_role("link", name="Preferences ").click()
    expect(page.get_by_role("cell", name="fooood")).to_be_visible()
    expect(page.get_by_text("What you prefer Food fooood")).to_be_visible()

    # signup
    page.get_by_label("Ticket (*)").select_option("u2")
    page.get_by_role("textbox", name="Food").click()
    page.get_by_role("textbox", name="Food").fill("SADSA")
    page.get_by_role("link", name="Needs ").click()
    page.get_by_role("textbox", name="sleep").click()
    page.get_by_role("textbox", name="sleep").fill("WWWW")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm").click()

    # check allowed
    go_to(page, live_server, "/test/manage")
    page.get_by_role("link", name="Sections").click()
    page.get_by_role("link", name="").click()

    page.get_by_role("link", name="Registrations", exact=True).click()
    page.get_by_role("link", name="Food").click()
    page.get_by_role("link", name="sleep").click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "Admin Test Depends WWWW SADSA")
    expect(page.get_by_role("link", name="Food")).to_be_visible()
    expect(page.get_by_role("link", name="sleep")).to_be_visible()

    # set allowed
    go_to(page, live_server, "/test/manage/roles/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("blabla")
    page.locator("#id_name").press("Tab")
    page.get_by_role("searchbox").fill("user")
    page.get_by_role("option", name="User Test - user@test.it").click()
    check_feature(page, "Navigation")
    check_feature(page, "Registrations")
    submit_confirm(page)

    page.locator("#orga_registration_form").get_by_role("link", name="Form").click()
    page.locator("#registration_questions_Needs").get_by_role("link", name="").click()
    page.get_by_text("Staff members who are allowed").click()
    page.get_by_role("cell", name="Staff members who are allowed").get_by_role("searchbox").click()
    page.get_by_role("cell", name="Staff members who are allowed").get_by_role("searchbox").fill("us")
    page.get_by_role("option", name="User Test").click()
    page.get_by_role("button", name="Confirm").click()

    # login as user
    login_user(page, live_server)
    page.get_by_role("link", name="").click()
    page.get_by_role("link", name=" Test Larp").click()
    page.get_by_role("link", name="Registrations", exact=True).click()

    expect(page.get_by_role("link", name="Food")).to_be_visible()
    expect(page.get_by_role("link", name="sleep")).not_to_be_visible()

    page.get_by_role("link", name="Food").click()

    expect_normalized(page, page.locator("#one"), "Admin Test Depends SADSA")
