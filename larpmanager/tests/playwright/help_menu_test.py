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

"""Test: help available from the management interface.
Verifies the topbar help menu, the tour replay, the key concepts page and the teaching empty states.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import expect_normalized, get_modal_iframe, go_to, login_orga

pytestmark = pytest.mark.e2e


def test_help_menu(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/manage/")

    # the menu opens on click and closes on any other click
    menu = page.locator("#tv22-help")
    entries = menu.locator("ul")
    expect(entries).to_be_hidden()
    menu.locator("summary").click()
    expect_normalized(page, entries, "All tutorials Key concepts Replay the tour")
    page.locator("#one").click(position={"x": 5, "y": 5})
    expect(entries).to_be_hidden()

    # the replay reloads the dashboard with the tour, which covers the menu too
    menu.locator("summary").click()
    entries.get_by_role("link", name="Replay the tour").click()
    popover = page.locator(".driver-popover")
    expect(popover).to_contain_text("Quick tour")
    popover.get_by_role("button", name="Next").click()
    expect(popover).to_contain_text("How it is organized")
    page.keyboard.press("Escape")
    expect(popover).to_be_hidden()

    # the tour is not shown again on the next visit
    go_to(page, live_server, "/manage/")
    expect(popover).to_be_hidden()

    # the concepts open in a popup
    menu.locator("summary").click()
    entries.get_by_role("link", name="Key concepts").click()
    expect(get_modal_iframe(page).locator("#concepts")).to_contain_text("One edition of an event")


def test_empty_state(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # the page asking to activate a feature explains what it does
    go_to(page, live_server, "/test/manage/discounts/")
    expect(page.locator("body")).to_contain_text("Allows you to generate discount codes")
    page.get_by_role("link", name="Activate", exact=True).click()

    # the empty list explains itself and keeps a single "New" link for the page action
    go_to(page, live_server, "/test/manage/discounts/")
    empty_state = page.locator(".empty-state")
    expect_normalized(page, empty_state, "Discounts offer reduced prices or promo codes to participants.")
    expect(empty_state.get_by_role("button", name="New discount")).to_be_visible()
