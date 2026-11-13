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
Test: self-service deletion of runs and events.
Verifies that the organization admin can delete a session and then the whole event
from the events list, through a warning popup that requires typing the full name;
that a wrong name is rejected server-side; and that members without the main
association role cannot see or reach the deletion page.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    _wait_select2_results,
    check_feature,
    expect_normalized,
    fill_date,
    get_modal_iframe,
    go_to,
    login_orga,
    login_user,
    logout,
    save_modal,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def _run_row(page: Any, name: str) -> Any:
    """Return the events table row of the run with this name."""
    return page.locator("#events tbody tr").filter(has=page.get_by_role("cell", name=name, exact=True))


def _open_delete_popup(page: Any, name: str) -> Any:
    """Open the delete popup for the run and return its iframe."""
    _run_row(page, name).locator("a:has(i.fa-trash)").click(force=True)
    return get_modal_iframe(page)


def _delete_run(page: Any, name: str) -> None:
    """Open the delete popup for the run, check the name guard, and confirm."""
    frame = _open_delete_popup(page, name)
    expect(frame.locator(".delete-confirm-message")).to_contain_text("dangerous")

    submit_btn = frame.get_by_role("button", name="Confirm")
    expect(submit_btn).to_be_disabled()
    frame.locator("#id_confirm_name").fill("wrong name")
    expect(submit_btn).to_be_disabled()
    frame.locator("#id_confirm_name").fill(name)
    expect(submit_btn).to_be_enabled()
    save_modal(page, frame)


def test_exe_events_delete(pw_page: Any) -> None:
    page, live_server, _unused = pw_page

    login_orga(page, live_server)

    # Add a second session to the test event
    go_to(page, live_server, "/manage/runs/new/")
    page.locator("#select2-id_event-container").click()
    page.get_by_role("searchbox").last.wait_for(state="visible")
    page.get_by_role("searchbox").last.fill("Test")
    _wait_select2_results(page)
    page.get_by_role("option", name="Test Larp").click()
    fill_date(page, "#id_start", "2060-01-10")
    fill_date(page, "#id_end", "2060-01-12")
    submit_confirm(page)
    expect_normalized(page, page.locator("#events"), "Test Larp #2")

    # A wrong name bypassing the client-side guard is rejected by the server
    frame = _open_delete_popup(page, "Test Larp #2")
    frame.locator("#id_confirm_name").fill("wrong name")
    frame.locator("#events_delete_submit").evaluate("el => el.disabled = false")
    frame.locator("#events_delete_submit").click()
    expect(frame.locator(".errorlist")).to_contain_text("does not match")
    go_to(page, live_server, "/manage/events")
    expect_normalized(page, page.locator("#events"), "Test Larp #2")

    # Delete only the second session: the event and its first session remain
    _delete_run(page, "Test Larp #2")
    expect(page.locator("#events")).not_to_contain_text("Test Larp #2")
    expect(page.locator("#events")).to_contain_text("Test Larp")

    # Delete the last session: the whole event is removed
    _delete_run(page, "Test Larp")
    go_to(page, live_server, "/manage/events")
    expect(page.locator("#one")).not_to_contain_text("Test Larp")


def test_exe_events_delete_non_admin(pw_page: Any) -> None:
    page, live_server, _unused = pw_page

    login_orga(page, live_server)

    # Grab the delete url of the test run
    go_to(page, live_server, "/manage/events")
    delete_url = _run_row(page, "Test Larp").locator("a:has(i.fa-trash)").get_attribute("href")

    # Give the test user an organization role with events access, but not the main role
    go_to(page, live_server, "/manage/roles")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("events role")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.get_by_role("searchbox").fill("us")
    edit_iframe.get_by_role("option", name="User Test -").click()
    check_feature(edit_iframe, "Events")
    save_modal(page, edit_iframe)

    logout(page)
    login_user(page, live_server)

    # The events list is reachable, but without the delete icon
    go_to(page, live_server, "/manage/events")
    expect(_run_row(page, "Test Larp")).to_be_visible()
    expect(page.locator("#events a:has(i.fa-trash)")).to_have_count(0)

    # Direct access to the deletion page is denied
    go_to(page, live_server, delete_url)
    expect_normalized(page, page.locator("body"), "Access denied")
