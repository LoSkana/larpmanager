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
Test: Event creation and basic setup.
Verifies creation of new events with slug generation, quick setup workflow,
date configuration, and event dashboard access.
"""

from typing import Any

import pytest

from larpmanager.tests.utils import fill_date, just_wait, go_to, login_orga, submit_confirm, expect_normalized, \
    get_modal_iframe, save_modal, fill_tinymce

pytestmark = pytest.mark.e2e


def test_exe_runs_new_session(pw_page: Any) -> None:
    """Test creating a new session for an existing event via exe_runs_new."""
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/manage/runs/new/")

    # Select the existing event using the Select2 widget
    page.locator("#select2-id_event-container").click()
    just_wait(page)
    page.get_by_role("searchbox").last.fill("Test")
    just_wait(page)
    page.get_by_role("option", name="Test Larp").click()
    just_wait(page)

    fill_date(page, "#id_start", "2060-01-10")
    fill_date(page, "#id_end", "2060-01-12")
    submit_confirm(page)

    # After saving, we are redirected to the events list
    expect_normalized(page, page.locator("#one"), "Test Larp")


def test_exe_events_run(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New event").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_form1-name").click()
    edit_iframe.locator("#id_form1-name").fill("Prova Event")
    edit_iframe.locator("#id_form1-name").press("Tab")
    edit_iframe.locator("#slug").fill("prova")
    fill_tinymce(edit_iframe, "id_form1-description", "sadsadasdsaas", False)
    edit_iframe.locator("#id_form1-max_pg").click()
    edit_iframe.locator("#id_form1-max_pg").fill("10")
    edit_iframe.locator("#id_form2-development").select_option("1")
    edit_iframe.locator("#id_form2-registration_status").select_option("o")
    fill_date(edit_iframe, "#id_form2-start", "2055-06-11")
    fill_date(edit_iframe, "#id_form2-end", "2055-06-13")
    save_modal(page, edit_iframe)

    expect_normalized(page, page.locator("#one"), "Prova Event")
    go_to(page, live_server, "/prova/manage/")

    expect_normalized(page, page.locator("#banner"), "Prova Event")
    go_to(page, live_server, "")
    expect_normalized(page, page.locator("#one"), "Prova Event")
