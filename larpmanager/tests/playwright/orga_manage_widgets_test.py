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
    # Enable Deadlines feature so the widget can potentially appear
    go_to(page, live_server, "/manage/features/deadlines/on")

    _create_role(page, live_server, "Accounting")

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/test/manage/")
    expect(page.locator("#banner")).not_to_contain_text("Access denied")

    widgets = page.locator("#manage h2")

    # Accounting widget visible (permission-only, no feature required)
    expect(widgets.filter(has_text="Accounting")).to_be_visible()

    # Registrations widget always visible for any dashboard user
    expect(widgets.filter(has_text="Registrations")).to_be_visible()

    # Deadlines widget NOT visible: feature is enabled but permission is missing
    expect(widgets.filter(has_text="Deadlines")).to_have_count(0)

    logout(page)
    login_orga(page, live_server)

    _delete_role(page, live_server)

    # --- Phase 2: Deadlines only (feature already enabled) ---
    _create_role(page, live_server, "Deadlines")

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/test/manage/")
    expect(page.locator("#banner")).not_to_contain_text("Access denied")

    widgets = page.locator("#manage h2")

    # Deadlines widget visible (permission + feature both satisfied)
    expect(widgets.filter(has_text="Deadlines")).to_be_visible()

    # Registrations widget still always visible
    expect(widgets.filter(has_text="Registrations")).to_be_visible()

    # Accounting widget NOT visible: no accounting permission
    expect(widgets.filter(has_text="Accounting")).to_have_count(0)

    logout(page)
    login_orga(page, live_server)

    _delete_role(page, live_server)

    # --- Phase 3: Disable Deadlines feature, assign Deadlines permission ---
    # Even with the permission, the widget must be hidden when the feature is off.
    go_to(page, live_server, "/manage/features/deadlines/off")

    _create_role(page, live_server, "Deadlines")

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/test/manage/")
    expect(page.locator("#banner")).not_to_contain_text("Access denied")

    widgets = page.locator("#manage h2")

    # Deadlines widget NOT visible: feature disabled even though permission is granted
    expect(widgets.filter(has_text="Deadlines")).to_have_count(0)

    logout(page)
    login_orga(page, live_server)

    _delete_role(page, live_server)
