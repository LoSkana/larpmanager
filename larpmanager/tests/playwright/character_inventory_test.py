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
from playwright.sync_api import expect

from larpmanager.tests.utils import fill_tinymce, go_to, login_orga, submit_confirm

pytestmark = pytest.mark.e2e


def test_character_inventory(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    setup(live_server, page)

    character_inventory_pool_types(live_server, page)

    character_inventory_pools(live_server, page)

    page.pause()


def setup(live_server: Any, page: Any) -> None:
    # activate features
    go_to(page, live_server, "/test/manage")
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Player editor").check()
    page.get_by_role("checkbox", name="Experience points").check()
    page.get_by_role("checkbox", name="Characters").check()
    page.get_by_role("button", name="Confirm").click()

    go_to(page, live_server, "/test/manage/config/")
    page.get_by_role("link", name=re.compile(r"^Player editor\s.+")).click()
    page.locator("#id_user_character_max").click()
    page.locator("#id_user_character_max").fill("1")
    submit_confirm(page)


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
    page.locator("[id=\"1\"]").get_by_role("link", name="").click()
