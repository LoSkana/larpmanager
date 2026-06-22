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
import re
from typing import Any

import pytest

from larpmanager.tests.utils import (just_wait,
                                     check_feature,
                                     fill_tinymce,
                                     get_modal_iframe,
                                     go_to,
                                     login_orga,
                                     submit_confirm, submit_inline_edit, wait_for_inline_edit,
                                     expect_normalized, sidebar, save_modal, _wait_lm_ready, _wait_select2_results,
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
        "player: admin test presentation test teaser text test text torta - nonna saleee aliame con another torta - nonna another player: user test",
    )
    go_to(page, live_server, "test/1/")
    page.get_by_role("link", name="Another").click()
    expect_normalized(page,
        page.locator("#one"),
        "your character is: test character player: user test torta - strudel saleee test character veronese torta - strudel test character player: admin test",
    )
    page.get_by_role("heading", name="Torta - Strudel").first.click()


def quests(page: Any, live_server: Any) -> None:
    # Activate features
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Features")
    check_feature(page, "Characters")
    check_feature(page, "Casting algorithm")
    check_feature(page, "Quests and Traits")
    submit_confirm(page)

    # create quest type
    page.get_by_role("link", name="Quest type").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Lore")
    save_modal(page, edit_iframe)

    # create two quests
    sidebar(page, "Quest")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Torta")
    fill_tinymce(edit_iframe, "id_teaser", "zucchero")
    fill_tinymce(edit_iframe, "id_text", "saleee")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Pizza")
    fill_tinymce(edit_iframe, "id_teaser", "mozzarella")
    fill_tinymce(edit_iframe, "id_text", "americano")
    save_modal(page, edit_iframe)

    # check
    expect_normalized(page, page.locator("#one"), "Q1 Torta Lore zucchero saleee Q2 Pizza Lore mozzarella americano")


def traits(page: Any, live_server: Any) -> None:
    # create traits
    sidebar(page, "Traits")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Strudel")
    fill_tinymce(edit_iframe, "id_teaser", "trentina")
    fill_tinymce(edit_iframe, "id_text", "veronese")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Nonna")
    fill_tinymce(edit_iframe, "id_teaser", "amelia")
    fill_tinymce(edit_iframe, "id_text", "aliame con ")
    editor = edit_iframe.locator("#id_text")
    editor.press("#")
    edit_iframe.get_by_role("searchbox").fill("stru")
    _wait_select2_results(edit_iframe)
    edit_iframe.locator(".select2-results__option").first.click()
    just_wait(edit_iframe)

    save_modal(page, edit_iframe)

    # excel char finder
    page.get_by_role("cell", name="veronese").dblclick()
    panel = wait_for_inline_edit(page)
    just_wait(page)
    panel.locator("textarea").press("#")
    page.get_by_role("searchbox").fill("non")
    _wait_select2_results(page)
    page.locator(".select2-results__option").first.click()
    just_wait(page)
    submit_inline_edit(page)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_quest").select_option("u2")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Capriciossa")
    fill_tinymce(edit_iframe, "id_teaser", "normale")
    fill_tinymce(edit_iframe, "id_text", "senza pomodoro")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_quest").select_option("u2")
    edit_iframe.locator("#id_quest").press("Tab")
    edit_iframe.locator("#id_name").fill("Mare")
    save_modal(page, edit_iframe)

    # check how they appear on user side
    go_to(page, live_server, "/test")
    page.get_by_role("link", name="Quest").click()
    expect_normalized(page, page.locator("#one"), "Name Quest Lore Torta | Pizza")
    page.get_by_role("link", name="Torta").click()
    expect_normalized(page, page.locator("#one"), "Presentation zucchero Traits Strudel - trentina Nonna - amelia")


def signups(page: Any, live_server: Any) -> None:
    # create signup for my char
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Registrations")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").nth(1).fill("org")
    edit_iframe.get_by_role("option", name="Admin Test - orga@test.it").click()
    edit_iframe.get_by_role("list").click()
    edit_iframe.get_by_role("searchbox").fill("te")
    edit_iframe.get_by_role("option", name="Test Character").click()
    save_modal(page, edit_iframe)

    # create another char
    sidebar(page, "Characters")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("Another")
    save_modal(page, edit_iframe)

    # create signup for another
    sidebar(page, "Registrations")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").nth(1).fill("user")
    edit_iframe.get_by_role("option", name="User Test - user@test.it").click()
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("an")
    edit_iframe.get_by_role("option", name="Another").click()
    save_modal(page, edit_iframe)


def casting(page: Any, live_server: Any) -> None:
    # config casting
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Casting ")).click()
    page.get_by_text("Maximum number of preferences").click()
    page.locator("#id_casting_max").click()
    page.locator("#id_casting_max").fill("3")
    page.locator("#id_casting_min").click()
    page.locator("#id_casting_min").fill("2")
    submit_confirm(page)

    # perform casting
    go_to(page, live_server, "/test")
    page.get_by_role("link", name="Casting").click()
    page.get_by_role("link", name="Lore").click()
    page.locator("#faction0").select_option("Torta")
    page.locator("#choice0").select_option("u2")
    page.locator("#faction1").select_option("Torta")
    page.locator("#choice1").select_option("u1")
    page.locator("#faction2").select_option("Pizza")
    page.locator("#choice2").select_option("u3")
    submit_confirm(page)

    # test toggle casting
    go_to(page, live_server, "/test/manage/casting")
    page.get_by_role("link", name="Lore").click()
    just_wait(page)
    expect_normalized(page, page.locator(".change").first, "YES")
    page.locator(".change").first.click()
    just_wait(page)

    go_to(page, live_server, "/test/manage/casting")
    page.get_by_role("link", name="Lore").click()
    just_wait(page)
    expect_normalized(page, page.locator(".change").first, "NO")
    page.locator(".change").first.click()
    just_wait(page)

    # make casting
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Casting")
    page.get_by_role("link", name="Lore").click()
    page.get_by_role("button", name="Start algorithm").click()
    just_wait(page)
    page.get_by_role("button", name="Upload").click()

    # check signups
    sidebar(page, "Registrations")
    page.get_by_role("link", name="Lore").click()
    expect_normalized(page,
        page.locator("#one"), "User Test Another Standard "
    )
    expect_normalized(page,
        page.locator("#one"), "Admin Test Test Character Torta - Nonna Standard"
    )

    # manual trait assignments
    page.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_qt_u1").select_option("u1")
    save_modal(page, edit_iframe)

    # check result
    _wait_lm_ready(page)
    expect_normalized(page,
        page.locator("#one"),
        "User Test Another Torta - Strudel Standard Admin Test Test Character Torta - Nonna Standard",
    )
