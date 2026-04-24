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
Test: Dashboard widgets visibility for event-role-only organizers.
Regression test for bug where _orga_widgets used has_association_permission instead of
has_event_permission, causing widgets to be hidden for users with only an event-level role.

Covers:
- Accounting widget (permission only, no feature required)
- Deadlines widget (permission + feature required)
- Registrations widget (always visible to any dashboard user)
- Negative: widgets hidden when permission is absent
- Negative: feature-gated widget hidden when feature is disabled
"""

from typing import Any

import pytest

from larpmanager.tests.utils import (
    _checkboxes,
    check_feature,
    go_to,
    login_orga,
    login_user,
    logout,
    submit_confirm,
)
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def _create_role(page: Any, live_server: Any, *permissions: str) -> None:
    go_to(page, live_server, "/test/manage/roles")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("widget test role")
    page.locator("#id_name").press("Tab")
    page.get_by_role("searchbox").fill("us")
    page.get_by_role("option", name="User Test -").click()
    for perm in permissions:
        check_feature(page, perm)
    submit_confirm(page)


def _delete_role(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/roles")
    page.locator('[id="u2"] .fa-trash').click()


def test_orga_manage_widgets_event_role(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # --- Phase 1: Accounting only ---
    # Enable Deadlines feature so the widget can potentially appear (to test it doesn't without permission).
    go_to(page, live_server, "/test/manage/features")
    check_feature(page, "Deadlines")
    submit_confirm(page)

    _create_role(page, live_server, "Accounting")

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/test/manage/")
    expect(page.locator("#banner")).not_to_contain_text("Access denied")

    # Accounting widget visible (permission-only, no feature required)
    expect(page.locator("h2")).to_contain_text("Accounting")

    # Registrations widget always visible for any dashboard user
    expect(page.locator("h2")).to_contain_text("Registrations")

    # Deadlines widget NOT visible: feature is enabled but permission is missing
    expect(page.locator("h2")).not_to_contain_text("Deadlines")

    logout(page)
    login_orga(page, live_server)

    _delete_role(page, live_server)

    # --- Phase 2: Deadlines only (feature already enabled) ---
    _create_role(page, live_server, "Deadlines")

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/test/manage/")
    expect(page.locator("#banner")).not_to_contain_text("Access denied")

    # Deadlines widget visible (permission + feature both satisfied)
    expect(page.locator("h2")).to_contain_text("Deadlines")

    # Registrations widget still always visible
    expect(page.locator("h2")).to_contain_text("Registrations")

    # Accounting widget NOT visible: no accounting permission
    expect(page.locator("h2")).not_to_contain_text("Accounting")

    logout(page)
    login_orga(page, live_server)

    _delete_role(page, live_server)

    # --- Phase 3: Disable Deadlines feature, assign Deadlines permission ---
    # Even with the permission, the widget must be hidden when the feature is off.
    go_to(page, live_server, "/test/manage/features")
    check_feature(page, "Deadlines")  # uncheck (toggle off)
    submit_confirm(page)

    _create_role(page, live_server, "Deadlines")

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/test/manage/")
    expect(page.locator("#banner")).not_to_contain_text("Access denied")

    # Deadlines widget NOT visible: feature disabled even though permission is granted
    expect(page.locator("h2")).not_to_contain_text("Deadlines")

    logout(page)
    login_orga(page, live_server)

    _delete_role(page, live_server)
