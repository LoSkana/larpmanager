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
Test: Warehouse inventory management system.
Verifies container creation, item management with tags, item movements between containers,
area assignments, external item tracking, and historical movement records.
"""
import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import just_wait, go_to, load_image, login_orga, expect_normalized, submit_confirm

pytestmark = pytest.mark.e2e


def test_warehouse(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/manage")
    prepare(page)
    add_items(page)
    bulk(page)

    go_to(page, live_server, "/test/manage/")
    area_assigmenents(page)
    checks(page)


def prepare(page: Any) -> None:
    # Activate feature inventory
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Warehouse").check()
    submit_confirm(page)

    # create new boxes
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Box A")
    page.locator("#id_name").press("Tab")
    page.locator("#id_position").fill("bibi")
    page.locator("#id_position").press("Tab")
    page.locator("#id_description").fill("asdf dsfds dfdsfs")
    page.get_by_text("After confirmation, add").click()
    submit_confirm(page)
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Boc B")
    page.locator("#id_name").press("Tab")
    page.locator("#id_position").fill("dd")
    page.locator("#id_position").press("Tab")
    page.locator("#id_description").fill("dsf dfsd dfsd")
    submit_confirm(page)
    expect_normalized(page, page.locator("#inv_containers tbody"), "box a bibi asdf dsfds dfdsfs boc b dd dsf dfsd dfsd")

    # add new tags
    page.get_by_role("link", name="Tags").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Electrical")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("gg ds")
    page.get_by_text("After confirmation, add").click()
    submit_confirm(page)
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Gru sad ")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("dsadsa")
    submit_confirm(page)


def add_items(page: Any) -> None:
    # add new items
    page.get_by_role("link", name="Items").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Item 1")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("sadsada")
    page.get_by_label("", exact=True).click()
    page.get_by_role("searchbox").nth(1).fill("box A")
    page.locator(".select2-results__option").first.click()
    page.get_by_role("list").click()
    page.get_by_role("searchbox").fill("ele")
    page.locator(".select2-results__option").first.click()
    load_image(page, "#id_photo")
    submit_confirm(page)

    expect_normalized(page, page.locator("#one"), "Item 1 sadsada Box A Electrical")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Item 2")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("sdsadas")
    page.locator("#select2-id_container-container").click()
    page.get_by_role("searchbox").nth(1).fill("boc")
    page.locator(".select2-results__option").first.click()
    page.get_by_text("After confirmation, add").click()
    submit_confirm(page)
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Item 3sa")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("dsad")
    page.locator("#select2-id_container-container").click()
    page.get_by_role("searchbox").nth(1).fill("box")
    page.locator(".select2-results__option").first.click()
    submit_confirm(page)

    # check items
    expect_normalized(page,
        page.locator("#one"), "item 1 sadsada box a electrical item 2 sdsadas boc b item 3sa dsad box a"
    )


def bulk(page: Any) -> None:
    # test bulk
    page.get_by_role("link", name="Bulk").click()

    # Test links not working when bulk active
    page.locator('[id="u1"]').get_by_role("cell", name="Electrical").click()
    page.locator('[id="u1"]').get_by_role("cell", name="Box A").click()
    page.get_by_role("link", name="Execute").click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "item 1 sadsada boc b electrical")
    expect_normalized(page, page.locator("#one"), "item 2 sdsadas boc b")
    expect_normalized(page, page.locator("#one"), "item 3sa dsad box a")


    page.get_by_role("link", name="Bulk").click()
    page.locator('[id="u2"]').get_by_role("cell", name="Boc B").click()
    page.locator('[id="u1"]').get_by_role("cell", name="Boc B").click()
    page.get_by_role("cell", name="Electrical").click()
    page.locator("#operation").select_option("2")
    page.locator("#objs_2").select_option("u2")
    page.get_by_role("link", name="Execute").click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "item 3sa dsad box a")
    expect_normalized(page, page.locator("#one"), "Item 2 sdsadas Boc B Gru sad")
    expect_normalized(page, page.locator("#one"), "Item 1 sadsada Boc B Electrical | Gru sad")


    # add movement
    page.get_by_role("link", name="Movements").click()
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_item-container").click()
    page.get_by_role("searchbox").fill("item 3")
    page.get_by_role("option", name="Item 3sa").click()
    page.locator("#id_notes").click()
    page.locator("#id_notes").fill("maintenance")
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Item 3sa maintenance")


def area_assigmenents(page: Any) -> None:
    page.get_by_role("link", name="Area").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Kitchen")
    page.locator("#id_name").press("Tab")
    page.locator("#id_position").fill("ss")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("sds")
    page.locator("#id_description").press("CapsLock")
    page.get_by_role("checkbox", name="After confirmation, add").check()
    submit_confirm(page)

    page.locator("#id_name").fill("sALOON")
    page.locator("#id_name").press("Tab")
    page.locator("#id_position").fill("SD")
    page.locator("#id_position").press("CapsLock")
    page.locator("#id_position").fill("SDsad ")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("saddsadsa")
    submit_confirm(page)

    # check
    expect_normalized(page, page.locator("#one"), "sALOON SDsad saddsadsa Item assignments")
    expect_normalized(page, page.locator("#one"), "Kitchen ss sds Item assignments")

    # assign items
    page.locator('[id="u2"]').get_by_role("link", name="Item assignments").click()
    page.locator(".selected").first.click()
    page.locator('[id="u3"]').get_by_role("textbox").click()
    page.locator('[id="u3"]').get_by_role("textbox").fill("sss")
    page.locator('[id="u1"] > .selected').click()
    page.locator('[id="u1"]').get_by_role("textbox").click()
    page.locator('[id="u1"]').get_by_role("textbox").fill("ffff")
    page.get_by_role("cell", name="ffff").get_by_role("textbox").click()
    just_wait(page)

    # check
    page.get_by_role("link", name="Area").click()
    page.locator('[id="u2"]').get_by_role("link", name="Item assignments").click()

    row = page.locator("tr#u1")
    assert row.locator("textarea").input_value() == "ffff"

    row = page.locator("tr#u2")
    assert row.locator("textarea").input_value() == ""

    row = page.locator("tr#u3")
    assert row.locator("textarea").input_value() == "sss"

    # add for second
    page.get_by_role("link", name="Area").click()
    page.locator('[id="u1"]').get_by_role("link", name="Item assignments").click()
    page.get_by_role("row", name="item 3sa dsad box a").get_by_role("textbox").click()
    page.get_by_role("row", name="item 3sa dsad box a").get_by_role("textbox").fill("b")
    page.locator('[id="u1"] > .selected').click()
    just_wait(page)


def checks(page: Any) -> None:
    # check manifest
    page.get_by_role("link", name="Manifest").click()
    expect_normalized(page, page.locator("#one"), "New Kitchen Position: ss Description: sds")
    expect_normalized(page,
        page.locator("#one"), "Item 1 Boc B - dd Item 3sa Box A - bibi	 b sALOON Position: SDsad Description: saddsadsa "
    )
    expect_normalized(page, page.locator("#one"), "Item 1 Boc B - dd ffff Item 3sa Box A - bibi	 sss")

    # check checks
    page.get_by_role("link", name="Checks").click()
    expect_normalized(page, page.locator("#one"), "Item 1 Description: sadsada Photo")
    expect_normalized(page, page.locator("#one"), "Kitchen sALOON ffff Item 3sa Description: dsad")
    expect_normalized(page, page.locator("#one"), "Kitchen b sALOON sss")
