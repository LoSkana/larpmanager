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
Test: Event role-based permissions.
Verifies creation of event-specific roles, permission assignment, access control,
and role deletion with permission revocation at event level.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    check_feature,
    go_to,
    login_orga,
    login_user,
    logout,
    submit_confirm,
    expect_normalized,
)

pytestmark = pytest.mark.e2e


def test_orga_event_role(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_user(page, live_server)

    go_to(page, live_server, "/test/manage/")
    expect_normalized(page, page.locator("#banner"), "Access denied")

    go_to(page, live_server, "/test/manage/accounting/")
    expect_normalized(page, page.locator("#banner"), "Access denied")

    login_orga(page, live_server)

    go_to(page, live_server, "/test/manage/roles")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("test role")
    page.locator("#id_name").press("Tab")
    page.get_by_role("searchbox").fill("us")
    page.get_by_role("option", name="User Test -").click()
    check_feature(page, "Configuration")
    check_feature(page, "Accounting")
    submit_confirm(page)
    expect_normalized(page, page.locator('[id="u2"]'), "Event (Configuration), Accounting (Accounting)")

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/test/manage/accounting/")
    expect_normalized(page, page.locator("#banner"), "Event accounting - Test Larp")

    logout(page)
    login_orga(page, live_server)

    go_to(page, live_server, "/test/manage/roles")
    page.get_by_role("row", name=" test role User Test").get_by_role("link").click()
    page.get_by_role("link", name="Delete").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Confirmation delete").click()

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/test/manage/")
    expect_normalized(page, page.locator("#banner"), "Access denied")

    go_to(page, live_server, "/test/manage/accounting/")
    expect_normalized(page, page.locator("#banner"), "Access denied")
