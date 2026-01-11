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
Test: Event creation and basic setup.
Verifies creation of new events with slug generation, quick setup workflow,
date configuration, and event dashboard access.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import just_wait, go_to, login_orga, submit_confirm, expect_normalized

pytestmark = pytest.mark.e2e


def test_exe_events_run(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New event").click()
    page.locator("#id_form1-name").click()
    page.locator("#id_form1-name").fill("Prova Event")
    page.locator("#id_form1-name").press("Tab")
    page.locator("#slug").fill("prova")

    frame = page.frame_locator("iframe.tox-edit-area__iframe")
    frame.locator("body").fill("sadsadasdsaas")
    page.locator("#id_form1-max_pg").click()
    page.locator("#id_form1-max_pg").fill("10")

    page.locator("#id_form2-development").select_option("1")
    page.locator("#id_form2-start").fill("2055-06-11")
    just_wait(page)
    page.locator("#id_form2-start").click()
    page.locator("#id_form2-end").fill("2055-06-13")
    just_wait(page)
    page.locator("#id_form2-end").click()
    submit_confirm(page)

    expect_normalized(page, page.locator("#one"), "Prova Event")
    go_to(page, live_server, "/prova/manage/")

    expect_normalized(page, page.locator("#banner"), "Prova Event")
    go_to(page, live_server, "")
    expect_normalized(page, page.locator("#one"), "Prova Event")
