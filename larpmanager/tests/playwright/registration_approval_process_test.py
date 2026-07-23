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
Test: Registration approval process.
When the "Approval process" config is enabled, players cannot sign up directly:
they submit a signup request instead, which shows up in a dedicated organizer
"Requests" panel. Approving lets the player complete a normal registration;
rejecting removes the request.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    _wait_lm_ready,
    click_option,
    confirm_modal,
    expect_normalized,
    get_modal_iframe,
    go_to,
    login_orga,
    login_user,
    logout,
    new_option,
    save_modal,
    submit_confirm,
    submit_option,
    test_user,
)

pytestmark = pytest.mark.e2e


def test_registration_approval_process(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    enable_approval_process(page, live_server)

    create_request_form(page, live_server)

    logout(page)
    login_user(page, live_server)

    submit_request(page, live_server)

    request_blocks_normal_registration(page, live_server)

    logout(page)
    login_orga(page, live_server)

    approve_request(page, live_server)

    logout(page)
    login_user(page, live_server)

    complete_registration_after_approval(page, live_server)


def enable_approval_process(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Registrations ")).click()
    page.locator("#id_registration_approval_process").check()
    submit_confirm(page)


def create_request_form(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/form/request/")

    # short text question
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("preferred role")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("what role would you like to play")
    save_modal(page, edit_iframe)

    # long text (paragraph) question
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("p")
    edit_iframe.locator("#id_typ").press("Tab")
    edit_iframe.locator("#id_name").fill("motivation")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("why do you want to attend")
    save_modal(page, edit_iframe)

    # single choice question
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("experience level")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("your larp experience")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("beginner")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("veteran")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)

    # multiple choice question
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("m")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("interests")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("choose any number of interests")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("combat")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("diplomacy")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)

    # the standard registration form must not show the request questions
    go_to(page, live_server, "/test/manage/form/")
    expect(page.get_by_text("preferred role")).to_have_count(0)


def submit_request(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/register/")
    expect(page).to_have_url(re.compile(r"/register/request/"))

    page.locator("#id_confirm").check()

    page.get_by_role("textbox", name="preferred role").fill("wandering healer")
    page.get_by_role("textbox", name="motivation").fill("love the setting")
    click_option(page.get_by_role("radio", name="veteran"))
    click_option(page.get_by_role("checkbox", name="combat"))
    click_option(page.get_by_role("checkbox", name="diplomacy"))

    page.get_by_role("button", name="Confirm").click()

    expect(page.locator(".jq-toast-single")).to_contain_text("Your signup request has been submitted")


def request_blocks_normal_registration(page: Any, live_server: Any) -> None:
    # A pending request cannot be edited through the normal registration form
    go_to(page, live_server, "/test/register/")
    expect(page.locator(".jq-toast-single")).to_contain_text("awaiting organizer approval")


def approve_request(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/registrations/requests/")
    table = page.locator("#registration_requests")
    expect_normalized(page, table, "user@test.it")
    expect_normalized(page, table, "wandering healer")
    expect_normalized(page, table, "love the setting")
    expect_normalized(page, table, "veteran")
    expect_normalized(page, table, "combat")
    expect_normalized(page, table, "diplomacy")

    page.get_by_role("link", name="Approve").click()
    confirm_modal(page)

    go_to(page, live_server, "/test/manage/registrations/requests/")
    expect(page.locator("body")).to_contain_text("No pending signup requests")


def complete_registration_after_approval(page: Any, live_server: Any) -> None:
    # The approved request has no ticket yet: the player completes normal registration.
    # With a single, free-priced ticket the summary auto-submits instead of showing.
    go_to(page, live_server, "/test/register/")
    page.get_by_role("button", name="Continue").click()
    page.wait_for_timeout(500)
    riepilogo = page.locator("#riepilogo")
    if riepilogo.is_visible():
        page.locator("#register_go").click()
    _wait_lm_ready(page)

    # Verify from the organizer side that the registration is now confirmed, not pending
    logout(page)
    login_orga(page, live_server)

    go_to(page, live_server, "/test/manage/registrations/requests/")
    expect(page.locator("body")).to_contain_text("No pending signup requests")

    go_to(page, live_server, "/test/manage/registrations/")
    expect(page.locator("body")).to_contain_text(test_user)
