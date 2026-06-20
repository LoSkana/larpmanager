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
import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (just_wait,
                                     go_to,
                                     login_orga,
                                     login_user,
                                     submit_confirm,
                                     expect_normalized, fill_tinymce, check_feature, sidebar, nav,
                                     get_modal_iframe, save_modal,
                                     )

pytestmark = pytest.mark.e2e


def test_orga_section_form(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Go to event
    go_to(page, live_server, "/test/manage/")

    # Activate section feature
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Sections").check()
    page.get_by_role("button", name="Confirm").click()

    # Create first section
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Preferences")
    edit_iframe.locator("#id_name").press("Tab")
    fill_tinymce(edit_iframe, "id_description", "What you prefer", show=False)
    save_modal(page, edit_iframe)

    # Create second section
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Needs")
    edit_iframe.locator("#id_name").press("Tab")
    fill_tinymce(edit_iframe, "id_description", "What you need", show=False)
    save_modal(page, edit_iframe)

    # Check reordering
    expect_normalized(page, page.locator("#registration_sections_wrapper"), "Preferences Needs")
    rows = page.locator("#registration_sections tbody tr")
    rows.nth(1).locator("td.reorder-handle").drag_to(rows.nth(0))
    page.wait_for_timeout(500)
    expect_normalized(page, page.locator("#one"), "Needs Preferences")

    # Add one question for each section
    page.get_by_role("link", name="Form").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_name").click()
    edit_iframe.get_by_text("Question type").click()
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Food")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("fooood")
    edit_iframe.locator("#select2-id_section-container").click()
    edit_iframe.get_by_role("searchbox").fill("pre")
    edit_iframe.get_by_role("option", name="Preferences").click()
    save_modal(page, edit_iframe)

    # Second question for second section
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_description").click()
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("sleep")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("sleeeep")
    edit_iframe.locator("#select2-id_section-container").click()
    edit_iframe.get_by_role("searchbox").fill("nee")
    edit_iframe.get_by_role("option", name="Needs").click()
    save_modal(page, edit_iframe)

    # Check signup
    go_to(page, live_server, "/test/register")

    page.get_by_role("link", name=re.compile(r"^Needs ")).click()
    page.get_by_role("link", name=re.compile(r"^Preferences ")).click()

    expect_normalized(page, page.locator("#register_form"),
    "Ticket (*) Standard Your registration ticket Needs What you need sleep sleeeep Preferences What you prefer Food fooood")

    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Form").click()

    # check section is still available
    page.locator("#registration_questions_needs").locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect(edit_iframe.locator("#select2-id_section-container")).to_match_aria_snapshot("- textbox \"Needs\"")
    save_modal(page, edit_iframe)

    # Reorder sections, check they are updated
    sidebar(page, "Sections")
    rows = page.locator("#registration_sections tbody tr")
    rows.nth(1).locator("td.reorder-handle").drag_to(rows.nth(0))
    page.wait_for_timeout(500)

    go_to(page, live_server, "/test/register")
    page.get_by_role("link", name=re.compile(r"^Needs ")).click()
    page.get_by_role("link", name=re.compile(r"^Preferences ")).click()
    expect_normalized(page, page.locator("#register_form"),
    "Ticket (*) Standard Your registration ticket Preferences What you prefer Food fooood Needs What you need sleep sleeeep")

    # Activate ticket selection / allowed selection
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Configuration")
    page.get_by_role("link", name=re.compile(r"^Registrations ")).click()
    page.locator("#id_registration_reg_que_allowed").check()
    page.locator("#id_registration_reg_que_tickets").check()
    page.get_by_role("button", name="Confirm").click()

    # Create new ticket
    sidebar(page, "Tickets")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Depends")
    save_modal(page, edit_iframe)

    # Select ticket as dependent
    page.get_by_role("link", name="Form").click()
    page.locator("#registration_questions_preferences").locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_role("row", name="Ticket list If you select one").get_by_role("searchbox").click()
    edit_iframe.get_by_role("row", name="Ticket list If you select one").get_by_role("searchbox").fill("de")
    edit_iframe.get_by_role("option", name="Test Larp (Standard) Depends").click()
    save_modal(page, edit_iframe)

    # Check signup
    go_to(page, live_server, "/test/register/")

    # whole section not visible
    expect(page.get_by_role("link", name=re.compile(r"^Preferences "))).not_to_be_visible()
    expect(page.get_by_role("cell", name="fooood")).not_to_be_visible()
    expect(page.get_by_text("What you prefer Food fooood")).not_to_be_visible()

    # select ticket
    page.get_by_label("Ticket (*)").select_option("u2")

    # section and field are visible
    expect(page.get_by_role("link", name=re.compile(r"^Preferences "))).to_be_visible()
    page.get_by_role("link", name=re.compile(r"^Preferences ")).click()
    expect(page.get_by_role("cell", name="fooood")).to_be_visible()
    expect(page.get_by_text("What you prefer Food fooood")).to_be_visible()

    # signup
    page.get_by_label("Ticket (*)").select_option("u2")
    page.get_by_role("textbox", name="Food").click()
    page.get_by_role("textbox", name="Food").fill("SADSA")
    page.get_by_role("link", name=re.compile(r"^Needs ")).click()
    page.get_by_role("textbox", name="sleep").click()
    page.get_by_role("textbox", name="sleep").fill("WWWW")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm").click()

    # check allowed
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Sections")
    rows = page.locator("#registration_sections tbody tr")
    rows.nth(1).locator("td.reorder-handle").drag_to(rows.nth(0))
    page.wait_for_timeout(500)

    sidebar(page, "Form")
    page.locator("#registration_questions_needs").locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_text("Staff members who are allowed").click()
    edit_iframe.get_by_role("cell", name="Staff members who are allowed").get_by_role("searchbox").click()
    edit_iframe.get_by_role("cell", name="Staff members who are allowed").get_by_role("searchbox").fill("ad")
    edit_iframe.get_by_role("option", name="Admin Test").click()
    save_modal(page, edit_iframe)

    sidebar(page, "Registrations")
    page.get_by_role("link", name="Food").click()
    page.get_by_role("link", name="sleep").click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "Admin Test Depends WWWW SADSA")
    expect(page.get_by_role("link", name="Food")).to_be_visible()
    expect(page.get_by_role("link", name="sleep")).to_be_visible()

    # set allowed
    go_to(page, live_server, "/test/manage/roles/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("blabla")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.get_by_role("searchbox").fill("user")
    edit_iframe.get_by_role("option", name="User Test - user@test.it").click()
    check_feature(edit_iframe, "Navigation")
    check_feature(edit_iframe, "Registrations")
    save_modal(page, edit_iframe)

    # login as user
    login_user(page, live_server)
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Registrations")

    expect(page.get_by_role("link", name="Food")).to_be_visible()
    expect(page.get_by_role("link", name="sleep")).not_to_be_visible()

    page.get_by_role("link", name="Food").click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "Admin Test Depends SADSA")

    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)

    expect(edit_iframe.get_by_role("link", name=re.compile(r"^Needs "))).not_to_be_visible()
    expect(edit_iframe.get_by_role("cell", name="sleeeep")).not_to_be_visible()
    expect(edit_iframe.get_by_text("What you need sleep sleeeep")).not_to_be_visible()

    # test factions
    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Configuration")
    page.get_by_role("link", name=re.compile(r"^Registrations ")).click()
    page.locator("#id_registration_reg_que_tickets").check()
    page.locator("#id_registration_reg_que_allowed").uncheck()
    page.locator("#id_registration_reg_que_tickets").uncheck()
    page.get_by_role("button", name="Confirm").click()

    sidebar(page, "Configuration")
    page.get_by_role("link", name=re.compile(r"^Registrations ")).click()
    page.locator("#id_registration_reg_que_faction").check()
    page.get_by_role("button", name="Confirm").click()

    # set up features
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Characters").check()
    check_feature(page, "Factions")
    page.get_by_role("button", name="Confirm").click()

    # create faction
    sidebar(page, "Factions")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("aaaaaccc")
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("te")
    edit_iframe.get_by_role("option", name="Test Character").click()
    save_modal(page, edit_iframe)

    # set up question
    sidebar(page, "Form")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("faaaaacc")
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("aa")
    edit_iframe.get_by_role("option", name="aaaaaccc (P)").click()
    save_modal(page, edit_iframe)

    # delete sign up
    sidebar(page, "Registrations")
    page.locator('.fa-trash').click()

    # check does not show on new sign up
    go_to(page, live_server, "/test/register")
    expect(page.get_by_role("cell", name="faaaaacc")).not_to_be_visible()
    page.get_by_label("Ticket (*)").select_option("u1")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # check does not show on sign up
    go_to(page, live_server, "/test/register")
    expect(page.get_by_role("cell", name="faaaaacc")).not_to_be_visible()

    # assign character
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Registrations")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_role("link", name=re.compile(r"^Character ")).click()
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("te")
    edit_iframe.get_by_role("option", name="Test Character").click()
    save_modal(page, edit_iframe)

    # check it is visible
    go_to(page, live_server, "/test/register")
    nav(page, "Registration")
    expect(page.get_by_role("cell", name="faaaaacc")).to_be_visible()
    expect_normalized(page, page.locator("#register_form"),
                      "ticket (*) standard depends your registration ticket faaaaacc needs preferences")
