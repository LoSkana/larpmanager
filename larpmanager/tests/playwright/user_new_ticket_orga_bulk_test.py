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
Test: New player tickets and bulk operations.
Verifies new player ticket creation and availability, bulk operations for warehouse
(containers, tags), writing (factions, plots), quest builder, and experience points.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import just_wait, expect_normalized, go_to, login_orga, submit_confirm, sidebar

pytestmark = pytest.mark.e2e


def test_user_new_ticket_orga_bulk(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "test/manage/")

    new_ticket(live_server, page)

    bulk_warehouse(live_server, page)

    bulk_warehouse2(live_server, page)

    bulk_writing(live_server, page)

    bulk_questbuilder(live_server, page)

    bulk_px(live_server, page)


def bulk_writing(live_server: Any, page: Any) -> None:
    # set feature
    go_to(page, live_server, "test/manage/")
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="Characters").check()
    page.get_by_role("checkbox", name="Plots").check()
    page.get_by_role("checkbox", name="Factions").check()
    page.get_by_role("checkbox", name="Quests and Traits").check()
    page.get_by_role("checkbox", name="Experience points").check()
    submit_confirm(page)

    # add plot
    page.get_by_role("link", name="Plots", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("plot")
    submit_confirm(page)

    # add faction
    page.get_by_role("link", name="Factions").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("faz")
    submit_confirm(page)

    # check base
    sidebar(page, "Characters")
    page.get_by_role("link", name="Faction", exact=True).click()
    page.locator("#one").get_by_role("link", name="Plots").click()
    expect_normalized(page, page.locator("#one"), "#1 Test Character Test Teaser Test Text Load")

    # set faction
    page.get_by_role("link", name="Bulk").click()
    page.get_by_role("cell", name="Test Teaser").click()
    page.get_by_role("link", name="Execute").click()
    just_wait(page)

    # check result
    page.get_by_role("link", name="Faction", exact=True).click()
    expect_normalized(page, page.locator("#one"), "#1 Test Character Test Teaser Test Text faz")

    # remove faction
    page.get_by_role("link", name="Bulk").click()
    page.get_by_role("cell", name="Test Teaser").click()
    page.locator("#operation").select_option("5")
    page.get_by_role("link", name="Execute").click()
    just_wait(page)

    # check result
    page.get_by_role("link", name="Faction", exact=True).click()
    expect_normalized(page, page.locator("#one"), "#1 Test Character Test Teaser Test Text Load")

    # add plot
    page.get_by_role("link", name="Bulk").click()
    page.get_by_role("cell", name="Test Teaser").click()
    page.locator("#operation").select_option("6")
    page.get_by_role("link", name="Execute").click()
    just_wait(page)

    # check result
    page.locator("#one").get_by_role("link", name="Plots").click()
    expect_normalized(page, page.locator("#one"), "#1 Test Character Test Teaser Test Text plot")

    # remove plot
    page.get_by_role("link", name="Bulk").click()
    page.get_by_role("cell", name="Test Teaser").click()
    page.locator("#operation").select_option("7")
    page.get_by_role("link", name="Execute").click()
    just_wait(page)

    # check
    page.locator("#one").get_by_role("link", name="Plots").click()
    expect_normalized(page, page.locator("#one"), "#1 Test Character Test Teaser Test Text Load")

    # set quest type
    page.get_by_role("link", name="Quest type").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("typ")
    submit_confirm(page)


def bulk_questbuilder(live_server: Any, page: Any) -> None:
    # create quest
    sidebar(page, "Quest")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("q1")
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("q2")
    submit_confirm(page)

    # create second quest type
    page.get_by_role("link", name="Quest type").click()
    expect_normalized(page, page.locator("#one"), "typ q1 q2")
    page.locator("#one div").filter(has_text="New").nth(3).click()
    page.get_by_role("row", name="Name").locator("td").click()
    page.locator("#id_name").fill("t2")
    submit_confirm(page)

    # test bulk set quest
    sidebar(page, "Quest")
    page.get_by_role("link", name="Bulk").click()
    page.locator('[id="u1"]').get_by_role("cell", name="typ").click()
    page.get_by_role("link", name="Execute").click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "Q1 q1 t2 Q2 q2 typ")

    # create traits
    sidebar(page, "Traits")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("t1")
    submit_confirm(page)

    # test bulk set quest
    page.get_by_role("link", name="Bulk").click()
    page.locator(".writing_list td:nth-child(5)").click()
    page.locator("#objs_9").select_option("u2")
    page.get_by_role("link", name="Execute").click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "T1 t1 Q2 q2")


def bulk_px(live_server: Any, page: Any) -> None:
    # create ability type
    page.get_by_role("link", name="Ability type").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("t1")
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("2")
    submit_confirm(page)

    # create ability
    sidebar(page, "Ability")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("swor")
    page.locator("#id_cost").click()
    page.locator("#id_cost").fill("1")
    submit_confirm(page)

    # test bulk set type
    page.get_by_role("link", name="Bulk").click()
    page.locator(".writing td:nth-child(5)").click()
    page.get_by_role("link", name="Execute").click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "swor 2 1")

    # test bulk change type
    page.get_by_role("link", name="Bulk").click()
    page.locator(".writing td:nth-child(5)").click()
    page.locator("#objs_10").select_option("u1")
    page.get_by_role("link", name="Execute").click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "swor t1 1")


def bulk_warehouse(live_server: Any, page: Any) -> None:
    # activate warehouse
    go_to(page, live_server, "manage/")
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Warehouse").check()
    submit_confirm(page)

    # add box
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("box")
    submit_confirm(page)

    # add tag
    page.get_by_role("link", name="Tags").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("tag")
    submit_confirm(page)

    # add items
    page.get_by_role("link", name="Items").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("item1")
    page.locator("#select2-id_container-container").click()
    page.get_by_role("searchbox").nth(1).fill("bo")
    page.locator(".select2-results__option").first.click()
    page.get_by_role("checkbox", name="After confirmation, add").check()
    submit_confirm(page)

    page.locator("#id_name").click()
    page.locator("#id_name").fill("item2")
    page.locator("#select2-id_container-container").click()
    page.get_by_role("searchbox").nth(1).fill("box")
    page.locator(".select2-results__option").first.click()
    page.get_by_role("checkbox", name="After confirmation, add").check()
    submit_confirm(page)

    page.locator("#id_name").click()
    page.locator("#id_name").fill("item3")
    page.locator("#select2-id_container-container").click()
    page.get_by_role("searchbox").nth(1).fill("box")
    page.locator(".select2-results__option").first.click()
    submit_confirm(page)

    # add second container
    page.get_by_role("link", name="Containers").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("box2")
    submit_confirm(page)


def bulk_warehouse2(live_server: Any, page: Any) -> None:
    # bulk move to box
    page.get_by_role("link", name="Items").click()
    expect_normalized(page, page.locator("#one"), "item1 box")
    expect_normalized(page, page.locator("#one"), "item2 box")
    expect_normalized(page, page.locator("#one"), "item3 box")
    page.get_by_role("link", name="Bulk").click()
    page.locator('[id="u3"]').get_by_role("cell").filter(has_text=re.compile(r"^$")).click()
    page.locator('[id="u1"]').get_by_role("cell").filter(has_text=re.compile(r"^$")).click()
    page.locator("#objs_1").select_option("u2")
    page.get_by_role("link", name="Execute").click()
    expect_normalized(page, page.locator("#one"), "item2 box")
    expect_normalized(page, page.locator("#one"), "item1 box2")
    expect_normalized(page, page.locator("#one"), "item3 box2")

    # bulk add tag
    page.get_by_role("link", name="Bulk").click()
    page.locator("#operation").select_option("2")
    page.locator('[id="u2"]').get_by_role("cell").filter(has_text=re.compile(r"^$")).click()
    page.locator('[id="u1"]').get_by_role("cell").filter(has_text=re.compile(r"^$")).click()
    page.get_by_role("link", name="Execute").click()
    expect_normalized(page, page.locator("#one"), "item3 box2")
    expect_normalized(page, page.locator("#one"), "item2 box tag")
    expect_normalized(page, page.locator("#one"), "item1 box2 tag")

    # bulk remove tag
    page.get_by_role("link", name="Bulk").click()
    page.locator('[id="u2"]').get_by_role("cell").filter(has_text=re.compile(r"^$")).click()
    page.locator("#operation").select_option("3")
    page.get_by_role("link", name="Execute").click()
    expect_normalized(page, page.locator("#one"), "item3 box2")
    expect_normalized(page, page.locator("#one"), "item2 box")
    expect_normalized(page, page.locator("#one"), "item1 box2 tag")

    # check link when bulk active
    page.get_by_role("link", name="Bulk").click()
    page.locator('[id="u1"]').get_by_role("link", name="box2").click()
    expect_normalized(page, page.locator("#banner"), "Warehouse items - Organization")

    # check link when bulk not active
    page.get_by_role("link", name="Bulk").click()
    page.locator('[id="u1"]').get_by_role("link", name="box2").click()
    expect(page.locator("#id_name")).to_have_value("box2")


def new_ticket(live_server: Any, page: Any) -> None:
    # add feature for ticket for new players
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="New player").check()
    submit_confirm(page)

    # add ticket
    page.get_by_role("link", name="New").click()
    page.get_by_text("Type of ticket").click()
    page.locator("#id_tier").select_option("y")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("new")
    submit_confirm(page)

    # sign up with the new ticket
    go_to(page, live_server, "test")
    page.get_by_role("link", name="Register").click()
    expect(page.get_by_label("Ticket")).to_match_aria_snapshot(
        '- combobox "Ticket (*)":\n  - option "-------" [disabled] [selected]\n  - option "Standard"\n  - option "new"'
    )
    page.get_by_label("Ticket").select_option("u2")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # create new event
    go_to(page, live_server, "manage/")
    page.get_by_role("link", name="Events").click()
    page.get_by_role("link", name="New event").click()
    page.locator("#id_form1-name").click()
    page.locator("#id_form1-name").fill("newevent")
    # don't set slug, let it be auto filled

    page.locator("#id_form2-development").select_option("1")
    page.locator("#id_form2-registration_status").select_option("o")
    page.locator("#id_form2-start").fill("2045-06-11")
    just_wait(page)
    page.locator("#id_form2-start").click()
    page.locator("#id_form2-end").fill("2045-06-13")
    just_wait(page)
    page.locator("#id_form2-end").click()
    submit_confirm(page)

    # add feature also to this
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="New player").check()
    submit_confirm(page)

    # add new ticket
    page.get_by_role("link", name="New").click()
    page.locator("#id_tier").select_option("y")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("new")
    submit_confirm(page)

    # check new ticket is not available
    go_to(page, live_server, "newevent/1/")
    page.get_by_role("link", name="Register").click()
    expect(page.get_by_label("Ticket")).to_match_aria_snapshot('- combobox "Ticket (*)":\n  - option "Standard" [selected]')
