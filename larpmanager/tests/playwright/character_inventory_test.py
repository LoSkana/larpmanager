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
Test: Character inventory system with pool types and transfers.
Verifies inventory pool type creation, character-specific inventory pools,
resource transfers between pools, and transfer history logging.
"""

import re
from typing import Any

import pytest

from larpmanager.tests.utils import go_to, get_request, login_orga, login_user, submit_confirm, expect_normalized, \
    get_modal_iframe, save_modal

pytestmark = pytest.mark.e2e


def test_character_inventory(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    setup(live_server, page)

    character_inventory_pool_types(live_server, page)

    character_inventory_pool_labels(live_server, page)

    character_inventory_types(live_server, page)

    character_inventory_pools(live_server, page)

    character_inventory_verify_staff(live_server, page)

    character_inventory_transfer(live_server, page)

    endpoint_test(page, live_server)


def setup(live_server: Any, page: Any) -> None:
    # activate features
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Features").first.click()
    # Event
    page.get_by_role("checkbox", name="Player editor").check()
    page.get_by_role("checkbox", name="Character inventory").check()
    # Writing
    page.get_by_role("checkbox", name="Characters").check()
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/config/")
    page.get_by_role("link", name=re.compile(r"^Player editor\s.+")).click()
    page.locator("#id_user_character_max").click()
    page.locator("#id_user_character_max").fill("1")
    submit_confirm(page)

    go_to(page, live_server, "/test/register/")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/quick/")


def character_inventory_pool_types(live_server: Any, page: Any) -> None:
    page.get_by_role("link", name="Pool Types").click()

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Credits")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Junk")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Common Plastics")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Minor RND Secret")
    save_modal(page, edit_iframe)


def character_inventory_pool_labels(live_server: Any, page: Any) -> None:
    page.get_by_role("link", name="Pool Labels").click()

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Crafting")
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("Co")
    edit_iframe.get_by_role("option", name="Common Plastics").click()
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Secrets")
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("Mi")
    edit_iframe.get_by_role("option", name="Minor RND Secret").click()
    save_modal(page, edit_iframe)


def character_inventory_types(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/manage/ci/inventory_types/")

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Crafting Type")
    edit_iframe.locator("#id_restrict_pools").check()
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("Cr")
    edit_iframe.get_by_role("option", name="Crafting").click()
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Secrets Type")
    edit_iframe.locator("#id_restrict_pools").check()
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("Se")
    edit_iframe.get_by_role("option", name="Secrets").click()
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/manage/quick/")


def character_inventory_pools(live_server: Any, page: Any) -> None:
    page.get_by_role("link", name="Character Inventory").click()

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("NPC")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Test Character's Bank")
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("te")
    edit_iframe.get_by_role("option", name="Test Character").click()
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Test Character's Crafting Inventory")
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("te")
    edit_iframe.get_by_role("option", name="Test Character").click()
    edit_iframe.locator("#id_inventory_type").select_option(label="Crafting Type")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Test Character's Secrets")
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("te")
    edit_iframe.get_by_role("option", name="Test Character").click()
    edit_iframe.locator("#id_inventory_type").select_option(label="Secrets Type")
    save_modal(page, edit_iframe)


def character_inventory_verify_staff(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/manage/ci/inventory/")

    # verify Test Character's Crafting Inventory shows only Common Plastics
    page.get_by_role("row", name="Test Character's Crafting Inventory").locator(".fa-solid.fa-book-open").click()
    pool_names = [n for n in page.locator("h2:has-text('Currencies') + table tr td:first-child").all_text_contents() if n != "Name"]
    assert "Common Plastics" in pool_names, "Expected Common Plastics in crafting inventory"
    assert "Credits" not in pool_names, "Credits should not appear in crafting inventory"
    assert "Junk" not in pool_names, "Junk should not appear in crafting inventory"
    assert "Minor RND Secret" not in pool_names, "Minor RND Secret should not appear in crafting inventory"

    go_to(page, live_server, "/test/manage/ci/inventory/")

    # verify Test Character's Secrets shows only Minor RND Secret
    page.get_by_role("row", name="Test Character's Secrets").locator(".fa-solid.fa-book-open").click()
    pool_names = [n for n in page.locator("h2:has-text('Currencies') + table tr td:first-child").all_text_contents() if n != "Name"]
    assert "Minor RND Secret" in pool_names, "Expected Minor RND Secret in secrets inventory"
    assert "Credits" not in pool_names, "Credits should not appear in secrets inventory"
    assert "Junk" not in pool_names, "Junk should not appear in secrets inventory"
    assert "Common Plastics" not in pool_names, "Common Plastics should not appear in secrets inventory"

    go_to(page, live_server, "/test/manage/quick/")


def character_inventory_transfer(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/manage/ci/inventory/")
    page.get_by_role("row", name="Test Character's Bank").locator(".fa-solid.fa-book-open").click()

    # transfer credits to the test character's storage
    page.get_by_role("row", name="Credits 0 NPC Transfer Add").get_by_placeholder("Amount").fill("3")
    page.get_by_role("textbox", name="Reason").nth(1).fill("test")
    page.get_by_role("cell", name="Add from NPC test").get_by_role("button").click()

    # give ownership of a character to the test user account (and thus the inventory)
    go_to(page, live_server, "/test/manage/quick/")
    page.get_by_role("link", name="Characters").click()
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_text("---------").click()
    edit_iframe.get_by_role("searchbox").fill("te")
    edit_iframe.get_by_role("option", name="User Test - user@test.it").click()
    save_modal(page, edit_iframe)

    # log out and log in as the test user
    login_user(page, live_server)

    page.get_by_role("link", name="Test Larp").click()
    page.get_by_role("link", name="Test Character").click()

    # do transfers as a user
    page.get_by_role("link", name="View Details").first.click()
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # submit profile
    page.get_by_role("checkbox", name="Authorisation").check()
    submit_confirm(page)

    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="Test Character").nth(1).click()
    page.locator(".inventory-card").filter(has_text="Test Character's Bank").get_by_role("link",
                                                                                         name="View Details").click()
    page.get_by_role("row", name="Credits 3 NPC Transfer").get_by_role("spinbutton").click()
    page.get_by_role("row", name="Credits 3 NPC Transfer").get_by_role("spinbutton").fill("2")
    page.get_by_role("row", name="Credits 3 NPC Transfer").get_by_placeholder("Reason").click()
    page.get_by_role("row", name="Credits 3 NPC Transfer").get_by_placeholder("Reason").fill("payment")
    page.get_by_role("cell", name="NPC Transfer payment").get_by_role("button").click()

    # check row 1
    row1 = page.locator('#transfer_log tbody tr').first
    expect_normalized(page, row1, "User Test	Test Character's Bank	NPC	Credits	2	payment")

    # check row 2
    row2 = page.locator('#transfer_log tbody tr').nth(1)
    expect_normalized(page, row2, "Admin Test	NPC	Test Character's Bank	Credits	3	test")

    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="Test Character").nth(1).click()
    character_inventory_verify_user(page)


def character_inventory_verify_user(page: Any) -> None:
    page.locator(".inventory-card").filter(has_text="Test Character's Crafting Inventory").get_by_role("link", name="View Details").click()
    pool_names = [n for n in page.locator("h2:has-text('Currencies') + table tr td:first-child").all_text_contents() if n != "Name"]
    assert "Common Plastics" in pool_names, "Expected Common Plastics in crafting inventory (user view)"
    assert "Credits" not in pool_names, "Credits should not appear in crafting inventory (user view)"
    assert "Junk" not in pool_names, "Junk should not appear in crafting inventory (user view)"
    assert "Minor RND Secret" not in pool_names, "Minor RND Secret should not appear in crafting inventory (user view)"
    page.go_back()

    page.locator(".inventory-card").filter(has_text="Test Character's Secrets").get_by_role("link", name="View Details").click()
    pool_names = [n for n in page.locator("h2:has-text('Currencies') + table tr td:first-child").all_text_contents() if n != "Name"]
    assert "Minor RND Secret" in pool_names, "Expected Minor RND Secret in secrets inventory (user view)"
    assert "Credits" not in pool_names, "Credits should not appear in secrets inventory (user view)"
    assert "Junk" not in pool_names, "Junk should not appear in secrets inventory (user view)"
    assert "Common Plastics" not in pool_names, "Common Plastics should not appear in secrets inventory (user view)"
    page.go_back()


def endpoint_test(page: Any, live_server: Any) -> None:
    """Test character abilties endpoint"""

    # Go to character list endpoint
    response = get_request(page, live_server, "/test/character/list/json/")
    char_uuid = response[0]["uuid"]

    # Go to character abilities endpoint
    get_request(page, live_server, f"/test/character/{char_uuid}/inventory/json/")
