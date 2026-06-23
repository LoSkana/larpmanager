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
Test: plots, abilities, and secret factions visibility.
Verifies ability assignments, plot character roles, secret vs public faction
visibility, and character field display configurations.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (expect_normalized,
                                     fill_tinymce,
                                     go_to,
                                     login_orga,
                                     login_user, submit_confirm, sidebar,
                                     get_modal_iframe, save_modal, click_and_wait_question, just_wait,
                                     _wait_select2_results,
                                     )

pytestmark = pytest.mark.e2e


def test_ghost_plots_secret_factions(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "test/manage")

    # activate features
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Characters").check()
    page.get_by_role("checkbox", name="Plots").check()
    page.get_by_role("checkbox", name="Factions").check()
    page.get_by_role("checkbox", name="Experience points").check()
    submit_confirm(page)

    # create ability and give them to player
    page.get_by_role("link", name="Ability type").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("www")
    save_modal(page, edit_iframe)
    sidebar(page, "Abilities")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("ggggg")
    save_modal(page, edit_iframe)
    sidebar(page, "Deliveries")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("eeee2")
    edit_iframe.locator("#id_amount").click()
    edit_iframe.locator("#id_amount").fill("2")
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("te")
    _wait_select2_results(edit_iframe)
    edit_iframe.locator(".select2-results__option").first.click()
    save_modal(page, edit_iframe)
    sidebar(page, "Abilities")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_cost").click()
    edit_iframe.locator("#id_cost").fill("1")
    edit_iframe.get_by_role("row", name="Characters").get_by_role("searchbox").click()
    edit_iframe.get_by_role("row", name="Characters").get_by_role("searchbox").fill("te")
    _wait_select2_results(edit_iframe)
    edit_iframe.locator(".select2-results__option").first.click()
    save_modal(page, edit_iframe)

    # create plots, assign them to player
    sidebar(page, "Plots")

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("first")
    # set char role
    searchbox = edit_iframe.get_by_role("searchbox")
    searchbox.click()
    searchbox.fill("te")
    # Wait for the option to appear and click it
    option = edit_iframe.get_by_role("option", name="Test Character")
    option.wait_for(state="visible")
    option.click()
    just_wait(edit_iframe, big=True)
    fill_tinymce(edit_iframe, "ch_1", "prisdsa")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("qweeerr")
    # set char role
    searchbox = edit_iframe.get_by_role("searchbox")
    searchbox.click()
    searchbox.fill("te")
    # Wait for the option to appear and click it
    option = edit_iframe.get_by_role("option", name="Test Character")
    option.wait_for(state="visible")
    option.click()
    just_wait(page, big=True)
    fill_tinymce(edit_iframe, "ch_1", "poelea s")
    save_modal(page, edit_iframe)

    # add factions, one visible, one not
    sidebar(page, "Factions")

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("eefqq")
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("tes")
    _wait_select2_results(edit_iframe)
    edit_iframe.locator(".select2-results__option").first.click()
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("g")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("gggerwe")
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("ted")
    edit_iframe.get_by_text("No results found").click()
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("tes")
    _wait_select2_results(edit_iframe)
    edit_iframe.locator(".select2-results__option").first.click()
    save_modal(page, edit_iframe)

    # add new field
    sidebar(page, "Sheet")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.get_by_role("cell", name="Question name (keep it short)").click()
    edit_iframe.locator("#id_name").fill("teeeeest")
    save_modal(page, edit_iframe)

    # check value now
    sidebar(page, "Characters")
    click_and_wait_question(page, "Experience")
    click_and_wait_question(page, "Faction")
    click_and_wait_question(page, "teeeeest")
    click_and_wait_question(page, "Plots")
    expect_normalized(page,
        page.locator("#one"),
        "Test Character 2 1 1 Test Teaser Test Text eefqq gggerwe first qweeerr",
    )

    # check secret factions
    login_user(page, live_server)
    go_to(page, live_server, "/")
    page.get_by_role("link", name="Test Larp").click()
    page.get_by_role("link", name="Test Character").click()
    _wait_lm_ready(page)
    expect_normalized(page, page.locator("#wrapper"), "Presentation Test Teaser eefqq")
    expect(page.locator("#wrapper")).not_to_contain_text("gggerwe")

    page.get_by_role("link", name="eefqq").click()
    _wait_lm_ready(page)
    expect_normalized(page,
        page.locator("#one"),
        "Characters Test Character Presentation: Test Teaser Factions: eefqq",
    )

    # if i try to go to secret faction, blocked
    page.goto(f"{live_server}/test/faction/u2/")
    banner = page.locator("#banner")
    if banner.count() > 0:
        expect_normalized(page, banner, "404")
