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

"""Test: Copy of single elements between events.

Verifies the selection step of the copy, copying only the chosen registration questions,
and leaving untouched the elements already present in the target event.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    fill_date,
    get_modal_iframe,
    go_to,
    login_orga,
    save_modal,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def test_orga_copy_selection(pw_page: Any) -> None:
    """Copy a single registration question from another event."""
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    prepare_source(live_server, page)

    prepare_target(live_server, page)

    copy_selected(live_server, page)

    check_result(live_server, page)


def add_question(page: Any, name: str) -> None:
    """Add a short text registration question with the given name."""
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill(name)
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_max_length").fill("10")
    save_modal(page, edit_iframe)


def prepare_source(live_server: Any, page: Any) -> None:
    """Add the questions of the source event."""
    # add two questions in the event the copy is done from
    go_to(page, live_server, "/test/manage/form/")
    add_question(page, "alpha question")
    add_question(page, "beta question")


def prepare_target(live_server: Any, page: Any) -> None:
    """Create the target event, with a question of its own."""
    # create the event the copy is done to
    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New event").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_form1-name").click()
    edit_iframe.locator("#id_form1-name").fill("target")
    edit_iframe.locator("#id_form1-name").press("Tab")
    edit_iframe.locator("#slug").fill("target")
    fill_date(edit_iframe, "#id_form2-start", "2050-01-01")
    fill_date(edit_iframe, "#id_form2-end", "2050-01-03")
    save_modal(page, edit_iframe)

    # add a question only in the target event, it must survive the copy
    go_to(page, live_server, "/target/manage/form/")
    add_question(page, "gamma question")


def copy_selected(live_server: Any, page: Any) -> None:
    """Run the copy, selecting a single question."""
    go_to(page, live_server, "/target/manage/features/copy/on")
    go_to(page, live_server, "/target/manage/copy/")

    # choose the source event, and the registration form as only type of elements
    page.locator("#select2-id_parent-container").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="Test Larp").click()
    page.locator("input[name='target'][value='question']").check(force=True)
    submit_confirm(page)

    # the selection step lists the questions of the source event
    section = page.locator('.copy-pick-section[data-copy-type="question"]')
    expect(section).to_be_visible()
    expect(section.locator(".copy-pick-card")).to_contain_text(["alpha question", "beta question"])

    # copy only the first question
    section.locator(".copy-pick-none").click()
    section.locator('.copy-pick-card:has-text("alpha question") input').check(force=True)
    expect(section.locator('.copy-pick-card:has-text("beta question") input')).not_to_be_checked()
    submit_confirm(page)


def check_result(live_server: Any, page: Any) -> None:
    """Check which questions are present in the target event."""
    go_to(page, live_server, "/target/manage/form/")

    # the selected question has been copied, the other one has not
    expect(page.get_by_text("alpha question")).to_have_count(1)
    expect(page.get_by_text("beta question")).to_have_count(0)

    # the question already present in the target event is still there
    expect(page.get_by_text("gamma question")).to_have_count(1)
