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
from pathlib import Path

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_user, submit_confirm, login_orga

pytestmark = pytest.mark.e2e


def test_user_new_ticket_orga_bulk(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)
     
    go_to(page, live_server, "test/1/manage/")

    new_ticket(live_server, page)

    bulk_inventory(live_server, page)

    bulk_writing(live_server, page)

    bulk_questbuilder(live_server, page)

    bulk_px(live_server, page)

def bulk_writing(live_server, page):
    # set feature
    go_to(page, live_server, "test/1/manage/")
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Characters").check()
    page.get_by_role("checkbox", name="Plots").check()
    page.get_by_role("checkbox", name="Factions").check()
    page.get_by_role("checkbox", name="Quests and Traits").check()
    page.get_by_role("checkbox", name="Experience points").check()
    page.get_by_role("button", name="Confirm").click()
    
    # add plot
    page.get_by_role("link", name="Plots", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("plot")
    page.get_by_role("button", name="Confirm").click()
    
    # add faction
    page.get_by_role("link", name="Factions").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("faz")
    page.get_by_role("button", name="Confirm").click()
    
    # check base
    page.locator("#orga_characters").get_by_role("link", name="Characters").click()
    page.get_by_role("link", name="Faction", exact=True).click()
    page.locator("#one").get_by_role("link", name="Plots").click()
    expect(page.locator("#one")).to_contain_text("#1 Test Character Test Teaser Test Text Load")
    
    # set faction
    page.get_by_role("link", name="Bulk").click()
    page.get_by_role("cell", name="Test Teaser").click()
    page.get_by_role("link", name="Execute").click()

    # check result
    page.get_by_role("link", name="Faction", exact=True).click()
    expect(page.locator("#one")).to_contain_text("#1 Test Character Test Teaser Test Text faz")
    
    # remove faction
    page.get_by_role("link", name="Bulk").click()
    page.get_by_role("cell", name="Test Teaser").click()
    page.locator("#operation").select_option("5")
    page.get_by_role("link", name="Execute").click()
    
    # check result
    page.get_by_role("link", name="Faction", exact=True).click()
    expect(page.locator("#one")).to_contain_text("#1 Test Character Test Teaser Test Text Load")
    
    # add plot
    page.get_by_role("link", name="Bulk").click()
    page.get_by_role("cell", name="Test Teaser").click()
    page.locator("#operation").select_option("6")
    page.get_by_role("link", name="Execute").click()
    
    # check result
    page.locator("#one").get_by_role("link", name="Plots").click()
    expect(page.locator("#one")).to_contain_text("#1 Test Character Test Teaser Test Text [T1] plot")

    # remove plot
    page.get_by_role("link", name="Bulk").click()
    page.get_by_role("cell", name="Test Teaser").click()
    page.locator("#operation").select_option("7")
    page.get_by_role("link", name="Execute").click()

    # check
    page.locator("#one").get_by_role("link", name="Plots").click()
    expect(page.locator("#one")).to_contain_text("#1 Test Character Test Teaser Test Text Load")

    # set quest type
    page.get_by_role("link", name="Quest type").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("typ")
    page.get_by_role("button", name="Confirm").click()

def bulk_questbuilder(live_server, page):
    # create quest
    page.get_by_role("link", name="Quest", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("q1")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("q2")
    page.get_by_role("button", name="Confirm").click()

    # create second quest type
    page.get_by_role("link", name="Quest type").click()
    expect(page.locator("#one")).to_contain_text("typ Q1 q1 Q2 q2")
    page.locator("#one div").filter(has_text="New").nth(3).click()
    page.get_by_role("row", name="Name").locator("td").click()
    page.locator("#id_name").fill("t2")
    page.get_by_role("button", name="Confirm").click()

    # test bulk set quest
    page.get_by_role("link", name="Quest", exact=True).click()
    page.get_by_role("link", name="Bulk").click()
    page.locator("[id=\"\\31 \"]").get_by_role("cell", name="typ").click()
    page.get_by_role("link", name="Execute").click()
    expect(page.locator("#one")).to_contain_text("Q1 q1 t2 Q2 q2 typ")

    # create traits
    page.locator("#orga_traits").get_by_role("link", name="Traits").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("t1")
    page.get_by_role("button", name="Confirm").click()

    # test bulk set quest
    page.get_by_role("link", name="Bulk").click()
    page.locator("td:nth-child(5)").click()
    page.locator("#objs_9").select_option("2")
    page.get_by_role("link", name="Execute").click()
    expect(page.locator("#one")).to_contain_text("T1 t1 Q2 q2")

def bulk_px(live_server, page):
    # create ability type
    page.get_by_role("link", name="Ability type").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("t1")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("2")
    page.get_by_role("button", name="Confirm").click()

    # create ability
    page.get_by_role("link", name="Ability", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("swor")
    page.locator("#id_cost").click()
    page.locator("#id_cost").fill("1")
    page.get_by_role("button", name="Confirm").click()

    # test bulk set type
    page.get_by_role("link", name="Bulk").click()
    page.locator("td:nth-child(5)").click()
    page.get_by_role("link", name="Execute").click()
    expect(page.locator("#one")).to_contain_text("swor 2 1")

    # test bulk change type
    page.get_by_role("link", name="Bulk").click()
    page.locator("td:nth-child(5)").click()
    page.locator("#objs_10").select_option("1")
    page.get_by_role("link", name="Execute").click()
    expect(page.locator("#one")).to_contain_text("swor t1 1")


def bulk_inventory(live_server, page):
    # activate inventory
    go_to(page, live_server, "manage/")
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Inventory").check()
    page.get_by_role("button", name="Confirm").click()

    # add box
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("box")
    page.get_by_role("button", name="Confirm").click()

    # add tag
    page.get_by_role("link", name="Tags").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("tag")
    page.get_by_role("button", name="Confirm").click()

    # add items
    page.get_by_role("link", name="Items").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("item1")
    page.locator("#select2-id_container-container").click()
    page.get_by_role("searchbox").nth(1).fill("bo")
    page.locator(".select2-results__option").first.click()
    page.get_by_role("checkbox", name="After confirmation, add").check()
    page.get_by_role("button", name="Confirm").click()

    page.locator("#id_name").click()
    page.locator("#id_name").fill("item2")
    page.locator("#select2-id_container-container").click()
    page.get_by_role("searchbox").nth(1).fill("box")
    page.locator(".select2-results__option").first.click()
    page.get_by_role("checkbox", name="After confirmation, add").check()
    page.get_by_role("button", name="Confirm").click()

    page.locator("#id_name").click()
    page.locator("#id_name").fill("item3")
    page.locator("#select2-id_container-container").click()
    page.get_by_role("searchbox").nth(1).fill("box")
    page.locator(".select2-results__option").first.click()
    page.get_by_role("button", name="Confirm").click()

    # add second container
    page.get_by_role("link", name="Containers").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("box2")
    page.get_by_role("button", name="Confirm").click()

    # bulk move to box
    page.get_by_role("link", name="Items").click()
    expect(page.locator("#one")).to_contain_text("item3 box item2 box item1 box")
    page.get_by_role("link", name="Bulk").click()
    page.locator("[id=\"\\33 \"]").get_by_role("cell").filter(has_text=re.compile(r"^$")).click()
    page.locator("[id=\"\\31 \"]").get_by_role("cell").filter(has_text=re.compile(r"^$")).click()
    page.locator("#objs_1").select_option("2")
    page.get_by_role("link", name="Execute").click()
    expect(page.get_by_text(
        "newevent Test Larp Organization This page shows the inventory items - Config")).to_be_visible()
    expect(page.locator("#one")).to_contain_text("item3 box2 item2 box item1 box2")

    # bulk add tag
    page.get_by_role("link", name="Bulk").click()
    page.locator("#operation").select_option("2")
    page.locator("[id=\"\\32 \"]").get_by_role("cell").filter(has_text=re.compile(r"^$")).click()
    page.locator("[id=\"\\31 \"]").get_by_role("cell").filter(has_text=re.compile(r"^$")).click()
    page.get_by_role("link", name="Execute").click()
    expect(page.locator("#one")).to_contain_text("item3 box2 item2 box tag item1 box2 tag")

    # bulk remove tag
    page.get_by_role("link", name="Bulk").click()
    page.locator("[id=\"\\32 \"]").get_by_role("cell").filter(has_text=re.compile(r"^$")).click()
    page.locator("#operation").select_option("3")
    page.get_by_role("link", name="Execute").click()
    expect(page.locator("#one")).to_contain_text("item3 box2 item2 box item1 box2 tag")

    # check link when bulk active
    page.get_by_role("link", name="Bulk").click()
    page.locator("[id=\"\\31 \"]").get_by_role("link", name="box2").click()
    expect(page.locator("#banner")).to_contain_text("Inventory items - Organization")

    # check link when bulk not active
    page.get_by_role("link", name="Bulk").click()
    page.locator("[id=\"\\31 \"]").get_by_role("link", name="box2").click()
    expect(page.locator("#id_name")).to_have_value("box2")

def new_ticket(live_server, page):
    # add new ticket feature

    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="New player").check()
    page.get_by_role("button", name="Confirm").click()

    # add ticket
    page.get_by_role("link", name="New").click()
    page.get_by_text("Type of ticket").click()
    page.locator("#id_tier").select_option("y")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("new")
    page.get_by_role("button", name="Confirm").click()

    # sign up with the new ticket
    go_to(page, live_server, "test/1")
    page.get_by_role("link", name="Register").click()
    expect(page.get_by_label("Ticket")).to_match_aria_snapshot(
        "- combobox \"Ticket\":\n  - option \"-------\" [disabled] [selected]\n  - option \"Standard\"\n  - option \"new\"")
    page.get_by_label("Ticket").select_option("2")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm").click()

    # create new event
    go_to(page, live_server, "manage/")
    page.get_by_role("link", name="Events").click()
    page.get_by_role("link", name="New event").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("newevent")
    # don't set slug, let it be auto filled
    page.get_by_role("button", name="Confirm").click()

    # add feature also to this
    page.get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="New player").check()
    page.get_by_role("button", name="Confirm").click()

    # add new ticket
    page.get_by_role("link", name="New").click()
    page.locator("#id_tier").select_option("y")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("new")
    page.get_by_role("button", name="Confirm").click()

    # set end date
    go_to(page, live_server, "newevent/1/manage/")
    page.locator("#id_development").select_option("1")
    page.locator("#id_start").fill("2045-06-11")
    page.wait_for_timeout(2000)
    page.locator("#id_start").click()
    page.locator("#id_end").fill("2045-06-13")
    page.wait_for_timeout(2000)
    page.locator("#id_end").click()
    submit_confirm(page)

    # check new ticket is not available
    go_to(page, live_server, "newevent/1/")
    page.get_by_role("link", name="Register").click()
    expect(page.get_by_label("Ticket")).to_match_aria_snapshot(
        "- combobox \"Ticket\":\n  - option \"Standard\" [selected]")

