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
import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_orga

pytestmark = pytest.mark.e2e


def test_exe_events_run(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New event").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Prova Event")
    page.locator("#id_name").press("Tab")
    page.locator("#slug").fill("prova")

    frame = page.frame_locator("iframe.tox-edit-area__iframe")
    frame.locator("body").fill("sadsadasdsaas")
    page.locator("#id_max_pg").click()
    page.locator("#id_max_pg").fill("10")
    page.get_by_role("button", name="Confirm", exact=True).click()

    # confirm quick setup
    page.get_by_role("button", name="Confirm", exact=True).click()

    page.locator("#id_development").select_option("1")
    page.locator("#id_start").fill("2025-06-11")
    page.wait_for_timeout(2000)
    page.locator("#id_start").click()
    page.locator("#id_end").fill("2025-06-13")
    page.wait_for_timeout(2000)
    page.locator("#id_end").click()
    page.get_by_role("button", name="Confirm", exact=True).click()

    expect(page.locator("#one")).to_contain_text("Prova Event")
    go_to(page, live_server, "/prova/1/manage/")

    expect(page.locator("#banner")).to_contain_text("Prova Event")
    go_to(page, live_server, "")
    expect(page.locator("#one")).to_contain_text("Prova Event")
