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


from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    expect_normalized,
    fill_tinymce,
    go_to,
    login_orga,
    login_user, submit_confirm,
)

pytestmark = pytest.mark.e2e


def test_ghost_plots_secret_factions(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "test/manage")

    # select in quick
    page.locator("#id_character").check()
    submit_confirm(page)

    # activate features
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Plots").check()
    page.get_by_role("checkbox", name="Factions").check()
    page.get_by_role("checkbox", name="Experience points").check()
    submit_confirm(page)

    # create ability and give them to player
    page.get_by_role("link", name="Ability type").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("www")
    submit_confirm(page)
    page.get_by_role("link", name="Ability", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("ggggg")
    submit_confirm(page)
    page.get_by_role("link", name="Delivery").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("eeee2")
    page.locator("#id_amount").click()
    page.locator("#id_amount").fill("2")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("te")
    page.locator(".select2-results__option").first.click()
    submit_confirm(page)
    page.get_by_role("link", name="Ability", exact=True).click()
    page.get_by_role("link", name="").click()
    page.locator("#id_cost").click()
    page.locator("#id_cost").fill("1")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("te")
    page.locator(".select2-results__option").first.click()
    submit_confirm(page)

    # create plots, assign them to player
    page.get_by_role("link", name="Plots").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("first")

    # set char role
    searchbox = page.get_by_role("searchbox")
    searchbox.click()
    searchbox.fill("te")
    # Wait for the option to appear and click it
    option = page.get_by_role("option", name="#1 Test Character")
    option.wait_for(state="visible")
    option.click()
    page.wait_for_timeout(5000)
    fill_tinymce(page, "ch_1", "prisdsa")
    page.locator("#main_form div").filter(has_text="After confirmation, add").click()
    submit_confirm(page)

    page.locator("#id_name").click()
    page.locator("#id_name").fill("qweeerr")
    # set char role
    searchbox = page.get_by_role("searchbox")
    searchbox.click()
    searchbox.fill("te")
    # Wait for the option to appear and click it
    option = page.get_by_role("option", name="#1 Test Character")
    option.wait_for(state="visible")
    option.click()
    page.wait_for_timeout(5000)
    fill_tinymce(page, "ch_1", "poelea s")
    submit_confirm(page)

    # add factions, one visible, one not
    page.get_by_role("link", name="Factions").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("eefqq")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("tes")
    page.locator(".select2-results__option").first.click()
    page.get_by_role("checkbox", name="After confirmation, add").check()
    submit_confirm(page)

    page.locator("#id_typ").select_option("g")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("gggerwe")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("ted")
    page.get_by_text("No results found").click()
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("tes")
    page.locator(".select2-results__option").first.click()
    submit_confirm(page)

    # add new field
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.get_by_role("cell", name="Question name (keep it short)").click()
    page.locator("#id_name").fill("teeeeest")
    submit_confirm(page)

    # check value now
    page.get_by_role("link", name="Characters").click()
    page.get_by_role("link", name="XP").click()
    page.get_by_role("link", name="Faction", exact=True).click()
    page.get_by_role("link", name="teeeeest").click()
    page.locator("#one").get_by_role("link", name="Plots").click()
    page.wait_for_load_state("networkidle")
    expect_normalized(page,
        page.locator("#one"),
        "#1 Test Character 2 1 1 Test Teaser Test Text eefqq gggerwe first qweeerr",
    )

    # change teaser
    page.get_by_role("cell", name="Test Teaser").dblclick()
    page.locator('iframe[title="Rich Text Area"]').content_frame.locator("html").click()
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_label("Rich Text Area").fill("Test Teaser2")
    submit_confirm(page)

    # reload page, check everything is correct
    go_to(page, live_server, "/test/manage/characters/")
    page.wait_for_timeout(2000)
    page.get_by_role("link", name="XP").click()
    page.get_by_role("link", name="teeeeest").click()
    page.get_by_role("link", name="Faction", exact=True).click()
    page.locator("#one").get_by_role("link", name="Plots").click()

    expect_normalized(page,
        page.locator("#one"),
        "#1 Test Character 2 1 1 Test Teaser2 Test Text eefqq gggerwe first qweeerr",
    )

    # change new field value
    page.get_by_role("cell", name="#1 Test Character").dblclick()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Test Character3")
    page.wait_for_timeout(2000)
    submit_confirm(page)

    # reload page, check everything is correct
    go_to(page, live_server, "/test/manage/characters/")
    page.get_by_role("link", name="XP").click()
    page.get_by_role("link", name="Faction", exact=True).click()
    page.locator("#one").get_by_role("link", name="Plots").click()
    page.get_by_role("link", name="teeeeest").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    expect_normalized(page,
        page.locator("#one"),
        "Test Character3 2 1 1 Test Teaser2 Test Text eefqq gggerwe first qweeerr",
    )

    # check secret factions
    login_user(page, live_server)
    go_to(page, live_server, "/")
    page.get_by_role("link", name="Test Larp").click()
    page.get_by_role("link", name="Test Character").click()
    expect_normalized(page, page.locator("#wrapper"), "Presentation Test Teaser2 eefqq")
    expect(page.locator("#wrapper")).not_to_contain_text("gggerwe")

    page.get_by_role("link", name="eefqq").click()
    expect_normalized(page,
        page.locator("#one"),
        "Characters Test Character3 Presentation: Test Teaser2 Factions: eefqq",
    )

    # if i try to go to secret faction, blocked
    page.goto(f"{live_server}/test/faction/2/")
    banner = page.locator("#banner")
    if banner.count() > 0:
        expect_normalized(page, banner, "404")
