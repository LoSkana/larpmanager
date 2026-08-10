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
Test: datatable column filters survive the modal edit refresh.

After confirming an edit in the iframe modal, the listing is re-fetched and the
datatable rebuilt; the ColumnControl column search must be reapplied.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    get_modal_iframe,
    go_to,
    login_orga,
    save_modal,
    SHORT_TIMEOUT,
)

pytestmark = pytest.mark.e2e


def test_orga_datatable_search(pw_page: Any) -> None:
    page, live_server, _ = pw_page

LAZY_QUESTION = "Lazyfield"


def test_orga_datatable_search(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/features/character/on")

    create_lazy_question(page, live_server)
    for name, answer in [("Alphaone", "keepme"), ("Betatwo", "other1"), ("Betathree", "other2")]:
        create_character(page, live_server, name, answer)

    go_to(page, live_server, "/test/manage/characters/")
    search_column(page, "Name", "Alphaone")
    expect_visible_rows(page, 1)

    # edit the filtered row through the modal and confirm
    edit_first_row(page)

    # the column filter must still be applied after the listing refresh
    expect_visible_rows(page, 1)
    expect(column_header(page, "Name").locator(".dtcc-button_dropdown")).to_have_class(
        re.compile("dtcc-button_active")
    )

    # same check on a column whose content is fetched lazily after the listing refresh
    go_to(page, live_server, "/test/manage/characters/")
    page.get_by_role("link", name=LAZY_QUESTION).first.click()
    search_column(page, LAZY_QUESTION, "keepme")
    expect_visible_rows(page, 1)

    edit_first_row(page)
    expect_visible_rows(page, 1)


def create_lazy_question(page: Any, live_server: Any) -> None:
    """Create a short text writing question: its column is loaded by ajax, not inline."""
    go_to(page, live_server, "/test/manage/writing/form/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_name").fill(LAZY_QUESTION)
    save_modal(page, edit_iframe)


def create_character(page: Any, live_server: Any, name: str, answer: str) -> None:
    go_to(page, live_server, "/test/manage/characters/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill(name)
    edit_iframe.get_by_role("row").filter(has_text=LAZY_QUESTION).get_by_role("textbox").fill(answer)
    save_modal(page, edit_iframe)


def edit_first_row(page: Any) -> None:
    page.locator("table.go_datatable tbody tr a:has(i.fa-edit)").first.click()
    edit_iframe = get_modal_iframe(page)
    save_modal(page, edit_iframe)


def column_header(page: Any, title: str) -> Any:
    """Visible header cell of the column with the given title."""
    return page.locator(f"thead th:visible:has(span.dt-column-title:text-is('{title}'))").first


def search_column(page: Any, title: str, value: str) -> None:
    """Open the ColumnControl dropdown of a column and type a search term."""
    column_header(page, title).locator(".dtcc-button_dropdown").click()
    search_input = page.locator(".dtcc-search input:visible").first
    search_input.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    search_input.fill(value)
    page.keyboard.press("Escape")


def expect_visible_rows(page: Any, expected: int) -> None:
    rows = page.locator("table.go_datatable tbody tr:visible")
    expect(rows).to_have_count(expected, timeout=SHORT_TIMEOUT)
