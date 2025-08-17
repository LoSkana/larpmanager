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

from larpmanager.tests.utils import (
    fill_tinymce,
    go_to,
    login_orga,
)

pytestmark = pytest.mark.e2e


def test_plot_relationship_reading(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # prepare
    page.get_by_role("link", name="").click()
    page.get_by_role("link", name=" Test Larp").click()
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.locator("#id_mod_1_0").check()
    page.locator("#id_mod_1_4").check()
    page.locator("#id_mod_1_6").check()
    page.get_by_role("button", name="Confirm").click()

    relationships(live_server, page)

    plots(live_server, page)

    reading(live_server, page)


def reading(live_server, page):
    go_to(page, live_server, "/test/1/manage/")

    # set prova presentation and text
    page.get_by_role("link", name="Characters").click()
    page.locator('[id="\\32 "]').get_by_role("link", name="").click()

    fill_tinymce(page, "id_teaser", "pppresssent")

    fill_tinymce(page, "id_text", "totxeet")

    page.get_by_role("button", name="Confirm").click()

    # now read it
    page.get_by_role("link", name="Reading").click()
    page.get_by_role("row", name=" prova character pppresssent").get_by_role("link").click()
    expect(page.locator("#one")).to_contain_text(
        "Test Larp Presentation pppresssent Text totxeet testona wwwwwbruuuu Relationships Test Character ciaaoooooo"
    )

    # test reading with factions
    page.get_by_role("link", name="Features").click()
    page.locator("#id_mod_1_3").check()
    page.get_by_role("button", name="Confirm").click()

    # create faction with test character
    page.get_by_role("link", name="Factions").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("only for testt")
    page.get_by_role("listitem").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="#1 Test Character").click()
    page.get_by_role("button", name="Confirm").click()

    # check faction main list
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect(page.locator("#one")).to_contain_text("only for testt Primary #1 Test Character")

    # check reading for prova
    page.get_by_role("link", name="Reading").click()
    page.get_by_role("row", name=" prova character pppresssent").get_by_role("link").click()
    expect(page.locator("#one")).to_contain_text(
        "Test Larp Presentation pppresssent Text totxeet testona wwwwwbruuuu Relationships Test Character Factions: only for testt ciaaoooooo"
    )

    # check reading plot
    page.get_by_role("link", name="Reading").click()
    page.get_by_role("row", name=" testona plot asadsadas wwwww").get_by_role("link").click()
    expect(page.locator("#one")).to_contain_text("testona Text wwwww prova bruuuu")


def relationships(live_server, page):
    # create second character
    page.get_by_role("link", name="Characters", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("prova")
    page.get_by_role("combobox").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="#1 Test Character").click()
    fill_tinymce(page, "rel_1_direct", "ciaaoooooo")
    page.get_by_role("button", name="Confirm").click()

    # check in main list
    page.get_by_role("link", name="Relationships").click()
    expect(page.locator("#one")).to_contain_text("#1 Test Character Test Teaser Test Text #2 prova #1 Test Character")

    # check in char
    page.locator('[id="\\32 "]').get_by_role("link", name="").click()
    page.get_by_role("row", name="Direct Show How the").get_by_role("link").click()
    expect(page.locator("#form_relationships")).to_contain_text("#1 Test Character Direct Show <p>ciaaoooooo</p>")

    # check in other char
    go_to(page, live_server, "/test/1/manage/characters/#")
    page.locator('[id="\\31 "]').get_by_role("cell", name="").click()
    page.get_by_role("row", name="Inverse Show How the").get_by_role("link").click()
    expect(page.locator("#form_relationships")).to_contain_text("Inverse Show ciaaoooooo")

    # check in gallery
    go_to(page, live_server, "/test/1/")
    page.get_by_role("link", name="prova").click()
    expect(page.locator("#one")).to_contain_text("Relationships Test Character ciaaoooooo")


def plots(live_server, page):
    # create plot
    go_to(page, live_server, "/test/1/manage/")
    page.get_by_role("link", name="Plots").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("testona")

    # set concept
    fill_tinymce(page, "id_teaser", "asadsadas")

    # set text
    fill_tinymce(page, "id_text", "wwwww")

    # set char role
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="#1 Test Character").click()

    fill_tinymce(page, "ch_1", "prova")

    page.get_by_role("button", name="Confirm").click()

    # check in plot list
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect(page.locator("#one")).to_contain_text("T1 testona asadsadas wwwww #1 Test Character")

    # check it is the same
    page.get_by_role("link", name="").click()
    page.wait_for_timeout(2000)
    locator = page.locator('a.my_toggle[tog="f_id_char_role_1"]')
    locator.click()
    expect(page.locator("#one")).to_contain_text("#1 Test Character Show <p>prova</p>")
    locator.click()

    # change it
    fill_tinymce(page, "id_char_role_1", "prova222")
    page.get_by_role("button", name="Confirm").click()

    # check it
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect(page.locator("#one")).to_contain_text("T1 testona asadsadas wwwww #1 Test Character")
    page.get_by_role("link", name="").click()
    page.wait_for_timeout(2000)
    locator = page.locator('a.my_toggle[tog="f_id_char_role_1"]')
    locator.click()
    expect(page.locator("#one")).to_contain_text("#1 Test Character Show <p>prova222</p>")

    # remove first char
    page.get_by_role("listitem", name="#1 Test Character").locator("span").click()
    # add another char
    page.get_by_role("searchbox").fill("pro")
    page.get_by_role("option", name="#2 prova").click()
    page.get_by_role("button", name="Confirm").click()

    # check
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect(page.locator("#one")).to_contain_text("T1 testona asadsadas wwwww #2 prova")

    # set text
    page.get_by_role("link", name="").click()
    fill_tinymce(page, "id_char_role_2", "bruuuu")
    page.get_by_role("button", name="Confirm").click()

    # check in user
    go_to(page, live_server, "/test/1/")
    page.get_by_role("link", name="prova").click()
    expect(page.locator("#one")).to_contain_text("testona wwwwwbruuuu")
