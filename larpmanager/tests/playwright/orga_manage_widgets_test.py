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
- Negative: feature-gated widget hidden when feature is disabled
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    go_to,
    login_orga,
    login_user,
    logout,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def _add_user_to_role(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/roles/u1/edit/")
    page.get_by_role("searchbox").fill("us")
    page.get_by_role("option", name="User Test -").click()
    submit_confirm(page)


def _remove_user_from_role(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/roles/u1/edit/")
    btn = page.locator(".select2-selection__choice:has-text('User Test') .select2-selection__choice__remove")
    btn.evaluate("el => el.click()")
    submit_confirm(page)


def test_orga_manage_widgets_event_role(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # --- Phase 1: Deadlines feature on ---
    go_to(page, live_server, "/manage/features/deadlines/on")
    _add_user_to_role(page, live_server)

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/test/manage/")
    expect(page.locator("#banner")).not_to_contain_text("Access denied")

    widgets = page.locator("#manage h2")

    # Accounting widget visible (permission-only, no feature required)
    expect(widgets.filter(has_text="Accounting")).to_be_visible()

    # Registrations widget always visible for any dashboard user
    expect(widgets.filter(has_text="Registrations")).to_be_visible()

    # Deadlines widget visible (feature enabled + organizer permission)
    expect(widgets.filter(has_text="Deadlines")).to_be_visible()

    logout(page)
    login_orga(page, live_server)

    _remove_user_from_role(page, live_server)

    # --- Phase 2: Deadlines feature off ---
    go_to(page, live_server, "/manage/features/deadlines/off")
    _add_user_to_role(page, live_server)

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/test/manage/")
    expect(page.locator("#banner")).not_to_contain_text("Access denied")

    widgets = page.locator("#manage h2")

    # Accounting widget still visible
    expect(widgets.filter(has_text="Accounting")).to_be_visible()

    # Deadlines widget NOT visible: feature is disabled
    expect(widgets.filter(has_text="Deadlines")).to_have_count(0)

    logout(page)
    login_orga(page, live_server)

    _remove_user_from_role(page, live_server)
