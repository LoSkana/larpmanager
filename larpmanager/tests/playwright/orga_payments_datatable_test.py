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
Test: server-side paginated datatable filtering and sorting.

On the orga and organization payments pages, the ColumnControl column search must
filter rows server-side (also on callback columns like User, and on choice labels),
and the order button must sort them.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    SHORT_TIMEOUT,
    get_modal_iframe,
    go_to,
    login_orga,
    login_user,
    save_modal,
    submit_register,
)

pytestmark = pytest.mark.e2e

ROWS = "table.pagin_datatable tbody tr:not(:has(td.dt-empty))"


def test_orga_payments_datatable(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/manage/features/payment/on")

    # one registration for orga, one for user
    go_to(page, live_server, "/test/register")
    submit_register(page)
    login_user(page, live_server)
    go_to(page, live_server, "/test/register")
    submit_register(page)
    login_orga(page, live_server)

    create_payment(page, live_server, "User", "70")
    create_payment(page, live_server, "Admin", "30")

    go_to(page, live_server, "/test/manage/payments/")
    expect(page.locator(ROWS)).to_have_count(2, timeout=SHORT_TIMEOUT)

    # filter on the User column
    search_column(page, "User", "User")
    expect(page.locator(ROWS)).to_have_count(1, timeout=SHORT_TIMEOUT)
    expect(page.locator(ROWS).first).to_contain_text("User Test")

    search_column(page, "User", "Admin")
    expect(page.locator(ROWS)).to_have_count(1, timeout=SHORT_TIMEOUT)
    expect(page.locator(ROWS).first).to_contain_text("Admin Test")

    search_column(page, "User", "")
    expect(page.locator(ROWS)).to_have_count(2, timeout=SHORT_TIMEOUT)

    # sort on the Net column: ascending then descending
    order_column(page, "Net")
    expect(page.locator(ROWS).first).to_contain_text("30")
    expect(page.locator(ROWS).last).to_contain_text("70")

    order_column(page, "Net")
    expect(page.locator(ROWS).first).to_contain_text("70")
    expect(page.locator(ROWS).last).to_contain_text("30")

    # sort on the User column: ascending then descending
    order_column(page, "User")
    expect(page.locator(ROWS).first).to_contain_text("Admin Test")

    order_column(page, "User")
    expect(page.locator(ROWS).first).to_contain_text("User Test")

    # choice columns are filtered on their label
    search_column(page, "Type", "Money")
    expect(page.locator(ROWS)).to_have_count(2, timeout=SHORT_TIMEOUT)
    search_column(page, "Type", "Credit")
    expect(page.locator(ROWS)).to_have_count(0, timeout=SHORT_TIMEOUT)
    search_column(page, "Type", "")

    # columns not backed by the database have no sort or search controls
    expect(column_header(page, "Receipt").locator(".dtcc-button_dropdown")).to_have_count(0)

    # organization payments: same filtering and sorting on the User column
    go_to(page, live_server, "/manage/payments/")
    expect(page.locator(ROWS)).to_have_count(2, timeout=SHORT_TIMEOUT)
    search_column(page, "User", "User")
    expect(page.locator(ROWS)).to_have_count(1, timeout=SHORT_TIMEOUT)
    expect(page.locator(ROWS).first).to_contain_text("User Test")
    search_column(page, "User", "")
    expect(page.locator(ROWS)).to_have_count(2, timeout=SHORT_TIMEOUT)

    order_column(page, "User")
    expect(page.locator(ROWS).first).to_contain_text("Admin Test")
    order_column(page, "User")
    expect(page.locator(ROWS).first).to_contain_text("User Test")


def create_payment(page: Any, live_server: Any, member: str, value: str) -> None:
    go_to(page, live_server, "/test/manage/payments/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_registration-container").click()
    edit_iframe.get_by_role("searchbox").fill(member)
    edit_iframe.get_by_role("option").filter(has_text=member).first.click()
    edit_iframe.locator("#id_value").fill(value)
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


def order_column(page: Any, title: str) -> None:
    """Click the ColumnControl order toggle of a column."""
    column_header(page, title).locator(".dtcc-button_order").click()
