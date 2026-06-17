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
Test: Plots, character relationships, and reading functionality.
Verifies plot creation with character roles, relationship management (direct/inverse),
reading view for characters and plots, and faction integration in reading view.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (just_wait,
                                     check_feature,
                                     fill_tinymce,
                                     get_modal_iframe,
                                     go_to,
                                     login_orga,
                                     submit_confirm,
                                     expect_normalized, sidebar,
                                     )

pytestmark = pytest.mark.e2e


def test_plot_relationship_reading(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # prepare

    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Features").first.click()
    check_feature(page, "Characters")
    check_feature(page, "Plots")
    check_feature(page, "Relationships")
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Characters")).click()
    page.locator("#id_writing_reading").check()
    submit_confirm(page)

    relationships(live_server, page)

    plots(live_server, page)

    plots_character(live_server, page)

    reading(live_server, page)

    auto_relationships(live_server, page)


def reading(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/manage/")

    # set prova presentation and text
    page.get_by_role("link", name="Characters").click()
    page.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)

    fill_tinymce(edit_iframe, "id_teaser", "pppresssent")

    fill_tinymce(edit_iframe, "id_text", "totxeet")

    submit_confirm(edit_iframe)

    # now read it
    sidebar(page, "Reading")
    page.locator('[id="character_u2"]').locator(".fa-book-open").click()
    expect_normalized(page,
        page.locator("#one"),
        """
        Presentation pppresssent Text totxeet testona wwwww bruuuu Relationships Test Character test teaser ciaaoooooo
        """,
    )

    # test reading with factions
    page.get_by_role("link", name="Features").first.click()
    check_feature(page, "Factions")
    submit_confirm(page)

    # create faction with test character
    page.get_by_role("link", name="Factions").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("only for testt")
    edit_iframe.get_by_role("listitem").click()
    searchbox = edit_iframe.get_by_role("searchbox")
    searchbox.fill("te")
    # Wait for the option to appear and click it
    option = edit_iframe.get_by_role("option", name="Test Character")
    option.wait_for(state="visible")
    option.click()
    submit_confirm(edit_iframe)

    # check faction main list
    page.locator("#one").get_by_role("link", name="Characters").click()

    expect_normalized(page, page.locator("#one"), "only for testt Primary Test Character")

    # check reading for prova
    sidebar(page, "Reading")
    page.locator('[id="character_u2"]').locator(".fa-book-open").click()
    expect_normalized(page,
        page.locator("#one"),
        "Presentation pppresssent Text totxeet testona wwwww bruuuu Relationships Test Character only for testt test teaser ciaaoooooo",
    )

    # check reading plot
    sidebar(page, "Reading")
    page.locator('[id="plot_u1"]').locator(".fa-book-open").click()
    expect_normalized(page, page.locator("#one"), "testona Text wwwww prova bruuuu")


def relationships(live_server: Any, page: Any) -> None:
    # create second character
    sidebar(page, "Characters")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("prova")
    edit_iframe.locator("#select2-new_rel_select-container").click()
    searchbox = edit_iframe.get_by_role("searchbox")
    searchbox.fill("tes")
    # Wait for the option to appear and click it
    option = edit_iframe.get_by_role("option", name="Test Character")
    option.wait_for(state="visible")
    option.click()
    edit_iframe.wait_for_timeout(5000)
    fill_tinymce(edit_iframe, "rel_u1", "ciaaoooooo")
    submit_confirm(edit_iframe)

    # check in main list
    page.get_by_role("link", name="Relationships").click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "Test Character Test Teaser Test Text prova Test Character")

    # check in char
    page.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    just_wait(page)
    edit_iframe.get_by_role("row", name="Direct Show How the").get_by_role("link").click()
    just_wait(page, big=True)
    expect_normalized(page, edit_iframe.locator("#form_relationships"), "ciaaoooooo")

    # check in other char
    go_to(page, live_server, "/test/manage/characters/#")
    just_wait(page)
    page.locator('[id="u1"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    just_wait(page, big=True)
    edit_iframe.locator("a.my_toggle[tog='f_u2_inverse']").scroll_into_view_if_needed()
    edit_iframe.locator("a.my_toggle[tog='f_u2_inverse']").click()
    edit_iframe.locator(".f_u2_inverse").wait_for(state="visible", timeout=10000)
    expect_normalized(page, edit_iframe.locator("#form_relationships"), "ciaaoooooo")

    # check in gallery
    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="prova").click()
    expect_normalized(page, page.locator("#one"), "Relationships Test Character test teaser ciaaoooooo")


def plots(live_server: Any, page: Any) -> None:
    # create plot
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Plots").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)

    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("testona")

    # set concept
    fill_tinymce(edit_iframe, "id_teaser", "asadsadas")

    # set text
    fill_tinymce(edit_iframe, "id_text", "wwwww")

    # set first char role
    searchbox = edit_iframe.get_by_role("searchbox")
    searchbox.click()
    searchbox.fill("te")
    # Wait for the option to appear and click it
    option = edit_iframe.get_by_role("option", name="Test Character")
    option.wait_for(state="visible")
    option.click()
    page.wait_for_timeout(5000)
    fill_tinymce(edit_iframe, "ch_1", "prova")

    # add second char role
    searchbox = edit_iframe.get_by_role("searchbox")
    searchbox.fill("pro")
    # Wait for the option to appear and click it
    option = edit_iframe.get_by_role("option", name="prova")
    option.wait_for(state="visible")
    option.click()
    page.wait_for_timeout(5000)
    fill_tinymce(edit_iframe, "ch_2", "second char role")

    submit_confirm(edit_iframe)

    # check in plot list - both characters should be there
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect_normalized(page, page.locator("#one"), "testona asadsadas wwwww Test Character prova")

    # check it is the same
    page.locator(".fa-edit").click()
    # Wait for the toggle element to be ready
    locator = page.locator('a.my_toggle[tog="f_id_char_role_1"]')
    locator.wait_for(state="visible")
    locator.click()
    expect_normalized(page, page.locator("#one"), "asadsadas wwwww prova second char role")
    locator.click()

    # change it
    fill_tinymce(page, "id_char_role_1", "prova222")
    submit_confirm(page)

    # check it
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect_normalized(page, page.locator("#one"), "testona asadsadas wwwww Test Character prova")
    page.locator(".fa-edit").click()
    # Wait for the toggle element to be ready
    locator = page.locator('a.my_toggle[tog="f_id_char_role_1"]')
    locator.wait_for(state="visible")
    locator.click()
    expect_normalized(page, page.locator("#one"), "asadsadas wwwww prova222 second char role")

    # remove first char
    page.get_by_role("listitem", name="Test Character").locator("span").click()
    # add another char
    searchbox = page.get_by_role("searchbox")
    searchbox.fill("pro")
    # Wait for the option to appear and click it
    option = page.get_by_role("option", name="prova")
    option.wait_for(state="visible")
    option.click()
    submit_confirm(page)

    # check
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect_normalized(page, page.locator("#one"), "testona asadsadas wwwww prova")

    # set text
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    fill_tinymce(edit_iframe, "id_char_role_2", "bruuuu")
    submit_confirm(edit_iframe)

    # check in user
    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="prova").click()
    expect_normalized(page, page.locator("#one"), "testona wwwww bruuuu")


def plots_character(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/manage/")
    # create other plots
    sidebar(page, "Plots")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("gaga")
    submit_confirm(edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("bibi")
    submit_confirm(edit_iframe)

    # test adding them to character
    sidebar(page, "Characters")
    page.locator('[id="u1"]').locator(".fa-edit").click()
    searchbox = page.get_by_role("searchbox")
    searchbox.click()
    searchbox.fill("gag")
    # Wait for search results to appear and click first option
    page.locator(".select2-results__option").first.wait_for(state="visible")
    page.locator(".select2-results__option").first.click()

    searchbox.fill("bibi")
    # Wait for search results to appear and click first option
    page.locator(".select2-results__option").first.wait_for(state="visible")
    page.locator(".select2-results__option").first.click()
    submit_confirm(page)

    just_wait(page)

    # check there are all three
    page.locator("#one").get_by_role("link", name="Plots").click()
    expect_normalized(page, page.locator('[id="u1"]'), "gaga bibi")

    page.locator('[id="u1"]').locator(".fa-edit").click()

    # remove third
    page.get_by_role("listitem", name="bibi").locator("span").click()

    # change second
    page.get_by_role("row", name=re.compile(r"^gaga")).get_by_role("link", name="Show").click()
    fill_tinymce(page, "id_pl_2", "ffff")
    submit_confirm(page)

    # check
    page.locator('[id="u1"]').locator(".fa-edit").click()
    page.get_by_role("row", name=re.compile(r"^gaga")).get_by_role("link", name="Show")
    expect_normalized(page, page.locator("#id_pl_2_tr"), "gaga <p>ffff</p> ffff")
    submit_confirm(page)

    page.locator("#one").get_by_role("link", name="Plots").click()
    expect_normalized(page, page.locator('[id="u1"]'), "gaga")
    expect(page.locator('[id="u1"]')).not_to_contain_text("bibi")

    # check second, then remove
    page.locator('[id="u1"]').locator(".fa-edit").click()
    page.get_by_role("listitem", name="gaga").locator("span").click()
    page.get_by_role("link", name="Instructions").click()
    submit_confirm(page)

    expect(page.locator('[id="u1"]')).not_to_contain_text("gaga")


def auto_relationships(live_server: Any, page: Any) -> None:
    """Test character mentioned via sheet question/faction/plot get auto relationships.

    For each of the three sources (sheet question, faction text, plot role text), the test
    character cites two characters. One of the two also gets a manual relationship, which must
    win over the auto-detected one. The test character should then show exactly 6 relationships:
    3 manual (one per source) + 3 auto (the other one per source).
    """
    auto_relationships_setup(live_server, page)

    auto_relationships_faction(live_server, page)

    auto_relationships_plot(live_server, page)

    auto_relationships_check(live_server, page)


def auto_relationships_setup(live_server: Any, page: Any) -> None:
    # add a custom character question, so a mention in it counts as "cited in the sheet"
    go_to(page, live_server, "/test/manage/writing/form/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("p")
    edit_iframe.locator("#id_name").fill("Background")
    submit_confirm(edit_iframe)

    # create the six characters that will be auto-related to the test character
    for name in ("AutoSheetA", "AutoSheetB", "AutoFactionA", "AutoFactionB", "AutoPlotA", "AutoPlotB"):
        sidebar(page, "Characters")
        page.get_by_role("link", name="New").click()
        edit_iframe = get_modal_iframe(page)
        edit_iframe.locator("#id_name").click()
        edit_iframe.locator("#id_name").fill(name)
        submit_confirm(edit_iframe)

    # on the test character: cite two characters in the sheet question, and set a manual
    # relationship for one character per source (sheet/faction/plot)
    sidebar(page, "Characters")
    page.locator('[id="u1"]').locator(".fa-edit").click()
    just_wait(page, big=True)

    fill_tinymce(page, "id_text", "mentions @3 and @4")

    for name, target_uuid, manual_text in (
        ("AutoSheetA", "u3", "manual sheet text"),
        ("AutoFactionA", "u5", "manual faction text"),
        ("AutoPlotA", "u7", "manual plot text"),
    ):
        page.locator("#select2-new_rel_select-container").click()
        searchbox = page.get_by_role("searchbox").nth(2)
        searchbox.fill(name)
        option = page.get_by_role("option", name=name)
        option.wait_for(state="visible")
        option.click()
        page.wait_for_timeout(2000)
        fill_tinymce(page, f"rel_{target_uuid}", manual_text)

    submit_confirm(page)


def auto_relationships_faction(live_server: Any, page: Any) -> None:
    # faction citing two other characters, with the test character as member
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Factions").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("AutoFaction")
    fill_tinymce(edit_iframe, "id_text", "mentions @5 and @6")
    edit_iframe.get_by_role("listitem").click()
    searchbox = edit_iframe.get_by_role("searchbox")
    searchbox.fill("Test Char")
    option = edit_iframe.get_by_role("option", name="Test Character")
    option.wait_for(state="visible")
    option.click()
    submit_confirm(edit_iframe)


def auto_relationships_plot(live_server: Any, page: Any) -> None:
    # plot citing two other characters, in the test character's role text
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Plots").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("AutoPlot")
    searchbox = edit_iframe.get_by_role("searchbox")
    searchbox.click()
    searchbox.fill("Test Char")
    option = edit_iframe.get_by_role("option", name="Test Character")
    option.wait_for(state="visible")
    option.click()
    edit_iframe.wait_for_timeout(5000)
    fill_tinymce(edit_iframe, "ch_1", "mentions @7 and @8")
    submit_confirm(edit_iframe)


def auto_relationships_check(live_server: Any, page: Any) -> None:
    # check the test character shows 6 relationships: 3 manual + 3 auto
    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="Test Character").first.click()
    relationships = page.locator(".gallery.single.relationships")
    expect(relationships).to_have_count(6)

    for name, text in (
        ("AutoSheetA", "manual sheet text"),
        ("AutoSheetB", "Text"),
        ("AutoFactionA", "manual faction text"),
        ("AutoFactionB", "AutoFaction"),
        ("AutoPlotA", "manual plot text"),
        ("AutoPlotB", "AutoPlot"),
    ):
        entry = relationships.filter(has_text=name)
        expect(entry).to_have_count(1)
        expect(entry).to_contain_text(text)
