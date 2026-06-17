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
from typing import Any

import pytest

from larpmanager.tests.utils import just_wait, go_to, load_image, login_orga, expect_normalized, submit_confirm, \
    sidebar, get_modal_iframe, save_modal

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
    edit_loaded_deployed(page)


def prepare(page: Any) -> None:
    # Activate feature inventory
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Warehouse").check()
    submit_confirm(page)

    # create new boxes
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Box A")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_position").fill("bibi")
    edit_iframe.locator("#id_position").press("Tab")
    edit_iframe.locator("#id_description").fill("asdf dsfds dfdsfs")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Boc B")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_position").fill("dd")
    edit_iframe.locator("#id_position").press("Tab")
    edit_iframe.locator("#id_description").fill("dsf dfsd dfsd")
    save_modal(page, edit_iframe)
    expect_normalized(page, page.locator("#inv_containers tbody"), "box a bibi asdf dsfds dfdsfs boc b dd dsf dfsd dfsd")

    # add new tags
    page.get_by_role("link", name="Tags").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Electrical")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("gg ds")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Gru sad ")
    edit_iframe.locator("#id_description").click()
    edit_iframe.locator("#id_description").fill("dsadsa")
    save_modal(page, edit_iframe)


def add_items(page: Any) -> None:
    # add new items
    page.get_by_role("link", name="Items").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Item 1")
    edit_iframe.locator("#id_description").click()
    edit_iframe.locator("#id_description").fill("sadsada")
    edit_iframe.get_by_label("", exact=True).click()
    edit_iframe.get_by_role("searchbox").nth(1).fill("box A")
    edit_iframe.locator(".select2-results__option").first.click()
    edit_iframe.get_by_role("list").click()
    edit_iframe.get_by_role("searchbox").fill("ele")
    edit_iframe.locator(".select2-results__option").first.click()
    load_image(edit_iframe,"#id_photo")
    save_modal(page, edit_iframe)

    expect_normalized(page, page.locator("#one"), "Item 1 sadsada Box A Electrical")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Item 2")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("sdsadas")
    edit_iframe.locator("#select2-id_container-container").click()
    edit_iframe.get_by_role("searchbox").nth(1).fill("boc")
    edit_iframe.locator(".select2-results__option").first.click()
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Item 3sa")
    edit_iframe.locator("#id_description").click()
    edit_iframe.locator("#id_description").fill("dsad")
    edit_iframe.locator("#select2-id_container-container").click()
    edit_iframe.get_by_role("searchbox").nth(1).fill("box")
    edit_iframe.locator(".select2-results__option").first.click()
    save_modal(page, edit_iframe)

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
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_item-container").click()
    edit_iframe.get_by_role("searchbox").fill("item 3")
    edit_iframe.get_by_role("option", name="Item 3sa").click()
    edit_iframe.locator("#id_notes").click()
    edit_iframe.locator("#id_notes").fill("maintenance")
    save_modal(page, edit_iframe)
    expect_normalized(page, page.locator("#one"), "Item 3sa maintenance")


def area_assigmenents(page: Any) -> None:
    page.get_by_role("link", name="Area").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Kitchen")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_position").fill("ss")
    edit_iframe.locator("#id_description").click()
    edit_iframe.locator("#id_description").fill("sds")
    edit_iframe.locator("#id_description").press("CapsLock")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("sALOON")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_position").fill("SD")
    edit_iframe.locator("#id_position").press("CapsLock")
    edit_iframe.locator("#id_position").fill("SDsad ")
    edit_iframe.locator("#id_description").click()
    edit_iframe.locator("#id_description").fill("saddsadsa")
    save_modal(page, edit_iframe)

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


def edit_loaded_deployed(page: Any) -> None:
    # navigate to manifest
    page.get_by_role("link", name="Manifest").click()

    # find first item row in the manifest table
    first_row = page.locator("table.go_datatable tbody tr").first

    # toggle Loaded on: click the loaded cell and verify check icon appears
    loaded_cell = first_row.locator("td.ajax-toggle[tp='load']")
    loaded_icon = loaded_cell.locator("span.value")
    assert not loaded_icon.is_visible(), "Loaded should be off initially"
    loaded_cell.click()
    just_wait(page)
    assert loaded_icon.is_visible(), "Loaded check icon should be visible after click"

    # reload and verify loaded state persists
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    first_row = page.locator("table.go_datatable tbody tr").first
    loaded_cell = first_row.locator("td.ajax-toggle[tp='load']")
    loaded_icon = loaded_cell.locator("span.value")
    assert loaded_icon.is_visible(), "Loaded check icon should persist after reload"

    # toggle Loaded off
    loaded_cell.click()
    just_wait(page)
    assert not loaded_icon.is_visible(), "Loaded check icon should be hidden after second click"

    # toggle Deployed on: click the deployed cell and verify check icon appears
    deployed_cell = first_row.locator("td.ajax-toggle[tp='depl']")
    deployed_icon = deployed_cell.locator("span.value")
    assert not deployed_icon.is_visible(), "Deployed should be off initially"
    deployed_cell.click()
    just_wait(page)
    assert deployed_icon.is_visible(), "Deployed check icon should be visible after click"

    # reload and verify deployed state persists
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    first_row = page.locator("table.go_datatable tbody tr").first
    deployed_cell = first_row.locator("td.ajax-toggle[tp='depl']")
    deployed_icon = deployed_cell.locator("span.value")
    assert deployed_icon.is_visible(), "Deployed check icon should persist after reload"

    # toggle Deployed off
    deployed_cell.click()
    just_wait(page)
    assert not deployed_icon.is_visible(), "Deployed check icon should be hidden after second click"
