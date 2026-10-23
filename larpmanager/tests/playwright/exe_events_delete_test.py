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
from the events list, through a warning popup that requires typing the full name.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    _wait_select2_results,
    expect_normalized,
    fill_date,
    get_modal_iframe,
    go_to,
    login_orga,
    save_modal,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def _delete_run(page: Any, name: str) -> None:
    """Open the delete popup for the run, check the name guard, and confirm."""
    row = page.locator("#events tbody tr").filter(has=page.get_by_role("cell", name=name, exact=True))
    row.locator("a:has(i.fa-trash)").click(force=True)
    frame = get_modal_iframe(page)
    expect(frame.locator(".delete-confirm-message")).to_contain_text("dangerous")

    submit_btn = frame.get_by_role("button", name="Confirm")
    expect(submit_btn).to_be_disabled()
    frame.locator("#id_confirm_name").fill("wrong name")
    expect(submit_btn).to_be_disabled()
    frame.locator("#id_confirm_name").fill(name)
    expect(submit_btn).to_be_enabled()
    save_modal(page, frame)


def test_exe_events_delete(pw_page: Any) -> None:
    page, live_server, _ = pw_page

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

    # Delete only the second session: the event and its first session remain
    _delete_run(page, "Test Larp #2")
    expect(page.locator("#events")).not_to_contain_text("Test Larp #2")
    expect(page.locator("#events")).to_contain_text("Test Larp")

    # Delete the last session: the whole event is removed
    _delete_run(page, "Test Larp")
    go_to(page, live_server, "/manage/events")
    expect(page.locator("#one")).not_to_contain_text("Test Larp")
