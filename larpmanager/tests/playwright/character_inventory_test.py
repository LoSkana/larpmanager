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
import re
from typing import Any

import pytest

from larpmanager.tests.utils import go_to, login_orga, submit_confirm, expect_normalized

pytestmark = pytest.mark.e2e


def test_character_inventory(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    setup(live_server, page)

    character_inventory_pool_types(live_server, page)

    character_inventory_pools(live_server, page)

    character_inventory_transfer(live_server, page)


def setup(live_server: Any, page: Any) -> None:
    # activate features
    go_to(page, live_server, "/test/manage")
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    # Event
    page.get_by_role("checkbox", name="Player editor").check()
    page.get_by_role("checkbox", name="Character inventory").check()
    # Writing
    page.get_by_role("checkbox", name="Characters").check()
    page.get_by_role("button", name="Confirm").click()

    go_to(page, live_server, "/test/manage/config/")
    page.get_by_role("link", name=re.compile(r"^Player editor\s.+")).click()
    page.locator("#id_user_character_max").click()
    page.locator("#id_user_character_max").fill("1")
    submit_confirm(page)

    go_to(page, live_server, "/test/register/")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm").click()

    go_to(page, live_server, "/test/manage/quick/")


def character_inventory_pool_types(live_server: Any, page: Any) -> None:
    page.get_by_role("link", name="Pool Types").click()
    page.get_by_role("link", name="+ New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Credits")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="+ New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Junk")
    page.get_by_role("button", name="Confirm").click()


def character_inventory_pools(live_server: Any, page: Any) -> None:
    page.get_by_role("link", name="Character Inventory").click()
    page.get_by_role("link", name="+ New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("NPC")
    page.get_by_text("After confirmation, add").click()
    page.get_by_role("button", name="Confirm").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Test Character's Bank")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="#1 Test Character").click()
    page.get_by_role("button", name="Confirm").click()
    page.locator('[id="u1"]').get_by_role("link", name="").click()


def character_inventory_transfer(live_server: Any, page: Any) -> None:
    # transfer credits to the test character's storage
    page.get_by_role("row", name="Credits 0 NPC Transfer Add").get_by_placeholder("Amount").click()
    page.get_by_role("row", name="Credits 0 NPC Transfer Add").get_by_placeholder("Amount").fill("3")
    page.get_by_role("row", name="Credits 0 NPC Transfer Add").get_by_placeholder("Amount").click()
    page.get_by_role("textbox", name="Reason").nth(1).click()
    page.get_by_role("textbox", name="Reason").nth(1).fill("test")
    page.get_by_role("cell", name="Add from NPC test").get_by_role("button").click()

    # give ownership of a character to the test user account (and thus the inventory)
    go_to(page, live_server, "/test/manage/quick/")
    page.get_by_role("link", name="Characters").click()
    page.get_by_role("link", name="").click()
    page.get_by_text("---------").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="User Test - user@test.it").click()
    # page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("button", name="Confirm").click()

    # log out and log in as the test user
    page.get_by_role("link", name=" Hi, Admin Test!").click()
    page.get_by_role("link", name=" Logout").click()
    page.get_by_role("link", name=" Menu").click()
    page.get_by_role("link", name=" Log In").click()
    page.get_by_role("textbox", name="email").click()
    page.get_by_role("textbox", name="email").fill("user@test.it")
    page.get_by_role("textbox", name="email").press("Tab")
    page.get_by_role("textbox", name="password").fill("banana")
    page.get_by_role("button", name="Submit").click()
    page.get_by_role("link", name="Test Larp").click()
    page.get_by_role("link", name="Test Character").click()

    # do transfers as a user
    page.get_by_role("link", name="View Details").first.click()
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Test Character").nth(1).click()
    page.get_by_role("link", name="View Details").first.click()
    page.get_by_role("row", name="Credits 3 NPC Transfer").get_by_role("spinbutton").click()
    page.get_by_role("row", name="Credits 3 NPC Transfer").get_by_role("spinbutton").fill("2")
    page.get_by_role("row", name="Credits 3 NPC Transfer").get_by_placeholder("Reason").click()
    page.get_by_role("row", name="Credits 3 NPC Transfer").get_by_placeholder("Reason").fill("payment")
    page.get_by_role("cell", name="NPC Transfer payment").get_by_role("button").click()

    # check row 1
    row1 = page.locator('#transfer_log tbody tr').first
    expect_normalized(page, row1, "User Test	Test Character's Personal Storage	NPC	Credits	2	payment")

    # check row 2
    row2 = page.locator('#transfer_log tbody tr').nth(1)
    expect_normalized(page, row2, "Admin Test	NPC	Test Character's Personal Storage	Credits	3	test")
