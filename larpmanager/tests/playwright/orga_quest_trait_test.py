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
Test: Quests and Traits system with casting integration.
Verifies quest types, quest creation, trait creation with character references,
and casting algorithm integration with quest/trait assignments.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (just_wait,
    check_feature,
    fill_tinymce,
    go_to,
    login_orga,
    submit_confirm,
    expect_normalized,
)

pytestmark = pytest.mark.e2e


def test_quest_trait(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    quests(page, live_server)

    traits(page, live_server)

    signups(page, live_server)

    casting(page, live_server)

    # check result
    go_to(page, live_server, "/test")
    page.get_by_role("link", name="Test Character").nth(1).click()
    expect_normalized(page,
        page.locator("#one"),
        "player: admin test presentation test teaser text test text torta - nonna saleee anotheraliame con torta - nonna another player: user test",
    )
    go_to(page, live_server, "test/1/")
    page.get_by_role("link", name="Another").click()
    expect_normalized(page,
        page.locator("#one"),
        "your character is test character player: user test torta - strudel saleee test characterveronese torta - strudel test character player: admin test",
    )
    page.get_by_role("heading", name="Torta - Strudel").first.click()


def quests(page: Any, live_server: Any) -> None:
    # Activate features
    page.get_by_role("link", name="").click()
    page.get_by_role("link", name=" Test Larp").click()
    page.get_by_role("link", name="Features").first.click()
    check_feature(page, "Characters")
    check_feature(page, "Casting algorithm")
    check_feature(page, "Quests and Traits")
    submit_confirm(page)

    # create quest type
    page.get_by_role("link", name="Quest type").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Lore")
    submit_confirm(page)

    # create two quests
    page.get_by_role("link", name="Quest", exact=True).click(force=True)
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("Torta")
    fill_tinymce(page, "id_teaser", "zucchero")
    fill_tinymce(page, "id_text", "saleee")
    page.get_by_text("After confirmation, add").click()
    submit_confirm(page)

    page.locator("#id_name").click()
    page.locator("#id_name").fill("Pizza")
    fill_tinymce(page, "id_teaser", "mozzarella")
    fill_tinymce(page, "id_text", "americano")
    submit_confirm(page)

    # check
    expect_normalized(page, page.locator("#one"), "Q1 Torta Lore zucchero saleee Q2 Pizza Lore mozzarella americano")


def traits(page: Any, live_server: Any) -> None:
    # create traits
    page.locator("#orga_traits").get_by_role("link", name="Traits").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Strudel")
    fill_tinymce(page, "id_teaser", "trentina")
    fill_tinymce(page, "id_text", "veronese")
    submit_confirm(page)

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Nonna")
    fill_tinymce(page, "id_teaser", "amelia")
    fill_tinymce(page, "id_text", "aliame con ")
    frame_locator = page.frame_locator("iframe#id_text_ifr")
    editor = frame_locator.locator("body#tinymce")
    editor.press("#")
    page.get_by_role("searchbox").fill("stru")
    page.locator(".select2-results__option").first.click()
    submit_confirm(page)

    # excel char finder
    page.get_by_role("cell", name="veronese").dblclick()
    frame = page.locator('iframe[title="Rich Text Area"]').content_frame
    frame.get_by_label("Rich Text Area").press("#")
    page.get_by_role("searchbox").fill("non")
    page.locator(".select2-results__option").first.click()
    just_wait(page)
    submit_confirm(page)

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_quest").select_option("u2")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Capriciossa")
    fill_tinymce(page, "id_teaser", "normale")
    fill_tinymce(page, "id_text", "senza pomodoro")
    submit_confirm(page)

    page.get_by_role("link", name="New").click()
    page.locator("#id_quest").select_option("u2")
    page.locator("#id_quest").press("Tab")
    page.locator("#id_name").fill("Mare")
    submit_confirm(page)

    # check how they appear on user side
    go_to(page, live_server, "/test")
    page.get_by_role("link", name="Quest").click()
    expect_normalized(page, page.locator("#one"), "Name Quest Lore Torta | Pizza")
    page.get_by_role("link", name="Torta").click()
    expect_normalized(page, page.locator("#one"), "Presentation zucchero Traits Strudel - trentina Nonna - amelia")


def signups(page: Any, live_server: Any) -> None:
    # create signup for my char
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Registrations", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").nth(1).fill("org")
    page.get_by_role("option", name="Admin Test - orga@test.it").click()
    page.get_by_role("list").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="#1 Test Character").click()
    submit_confirm(page)

    # create another char
    page.get_by_role("link", name="Characters").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Another")
    submit_confirm(page)

    # create signup for another
    page.get_by_role("link", name="Registrations", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").nth(1).fill("user")
    page.get_by_role("option", name="User Test - user@test.it").click()
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("an")
    page.get_by_role("option", name="#2 Another").click()
    submit_confirm(page)


def casting(page: Any, live_server: Any) -> None:
    # config casting
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name="Casting ").click()
    page.get_by_text("Maximum number of preferences").click()
    page.locator("#id_casting_max").click()
    page.locator("#id_casting_max").fill("3")
    page.locator("#id_casting_min").click()
    page.locator("#id_casting_min").fill("2")
    submit_confirm(page)

    # perform casting
    go_to(page, live_server, "/test")
    page.get_by_role("link", name="Casting", exact=True).click()
    page.get_by_role("link", name="Lore").click()
    page.locator("#faction0").select_option("Torta")
    page.locator("#choice0").select_option("u2")
    page.locator("#faction1").select_option("Torta")
    page.locator("#choice1").select_option("u1")
    page.locator("#faction2").select_option("Pizza")
    page.locator("#choice2").select_option("u3")
    submit_confirm(page)

    # make casting
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Casting", exact=True).click()
    page.get_by_role("link", name="Lore").click()
    page.get_by_role("button", name="Start algorithm").click()
    just_wait(page)
    page.get_by_role("button", name="Upload").click()

    # check signups
    page.get_by_role("link", name="Registrations", exact=True).click()
    page.get_by_role("link", name="Lore").click()
    expect_normalized(page,
        page.locator("#one"), "User Test #2 Another Standard "
    )
    expect_normalized(page,
        page.locator("#one"), "Admin Test #1 Test Character Torta - Nonna Standard"
    )

    # manual trait assignments
    page.locator('[id="u2"]').get_by_role("link", name="").click()
    page.locator("#id_qt_u1").select_option("u1")
    submit_confirm(page)

    # check result
    page.get_by_role("link", name="Lore").click()
    expect_normalized(page,
        page.locator("#one"),
        "User Test #2 Another Torta - Strudel Standard Admin Test #1 Test Character Torta - Nonna Standard",
    )
