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
Test: Sold ticket counts on the event page.
Verifies the ticket_sold event config, the per-ticket 'Show sold count'
option, and the counts displayed on the event page.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    expect_normalized,
    get_modal_iframe,
    go_to,
    login_orga,
    save_modal,
)

pytestmark = pytest.mark.e2e


def test_event_sold_tickets(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Without the config, no sold counts on the event page
    go_to(page, live_server, "/test/manage/config/ticket_sold/off")
    go_to(page, live_server, "/test/")
    expect(page.locator(".event-fact-sold")).to_have_count(0)

    # The per-ticket option is hidden while the config is off
    go_to(page, live_server, "/test/manage/tickets/")
    page.locator(".fa-edit").first.click()
    edit_iframe = get_modal_iframe(page)
    expect(edit_iframe.locator("#id_show_sold")).to_have_count(0)
    save_modal(page, edit_iframe)

    # With the config on, the total is shown
    go_to(page, live_server, "/test/manage/config/ticket_sold/on")
    expect(page.locator("#id_ticket_sold")).to_be_checked()
    go_to(page, live_server, "/test/")
    expect_normalized(page, page.locator(".event-fact-sold"), "Tickets sold:")

    # Activate the per-ticket detail on the first ticket
    go_to(page, live_server, "/test/manage/tickets/")
    page.locator(".fa-edit").first.click()
    edit_iframe = get_modal_iframe(page)
    ticket_name = edit_iframe.locator("#id_name").input_value()
    edit_iframe.locator("#id_show_sold").check()
    save_modal(page, edit_iframe)

    # The ticket list shows the sold count column
    expect_normalized(page, page.locator("#registration_tickets"), "Show sold count")

    go_to(page, live_server, "/test/")
    expect_normalized(page, page.locator(".event-fact-sold-detail"), ticket_name)
