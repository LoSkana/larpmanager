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
Test: Character search with filters.
Verifies character search functionality with faction filters, single-choice filters,
and multi-choice filters with include/exclude logic.
"""

from typing import Any

import pytest

from larpmanager.tests.utils import go_to, login_orga, expect_normalized, submit_confirm, new_option, \
    submit_option, sidebar, nav, get_modal_iframe

pytestmark = pytest.mark.e2e


def test_user_search(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    prepare(page, live_server)

    characters(page, live_server)

    go_to(page, live_server, "/test/")
    nav(page, "Search")

    filter_faction(page)

    filter_single(page)

    filter_multi(page)


def filter_multi(page: Any) -> None:
    # filter multi choice
    page.get_by_role("link", name="tag").click()
    page.get_by_role("link", name="wunder").click()
    expect_normalized(page,
        page.locator("#search-results"),
        "You are including (at least one of these filters) You are excluding (none of these filters) tag: wunder None another Player: Absent color: blue tag: wunder | qerfi wheel Player: Absent color: blue tag: wunder Factions: fassione",
    )
    page.get_by_role("link", name="qerfi").click()
    expect_normalized(page,
        page.locator("#search-results"),
        "You are including (at least one of these filters) You are excluding (none of these filters) tag: wunder | qerfi None another Player: Absent color: blue tag: wunder | qerfi wheel Player: Absent color: blue tag: wunder Factions: fassione",
    )
    page.get_by_role("link", name="wunder").click()
    page.get_by_role("link", name="zapyr").click()
    expect_normalized(page,
        page.locator("#search-results"),
        "You are including (at least one of these filters) You are excluding (none of these filters) tag: qerfi | zapyr tag: wunder Test Character Player: Absent color: red tag: zapyr Factions: fassione",
    )
    page.get_by_role("link", name="qerfi").click()
    page.get_by_role("link", name="zapyr").click()
    page.get_by_role("link", name="zapyr").click()
    expect_normalized(page,
        page.locator("#search-results"),
        "You are including (at least one of these filters) You are excluding (none of these filters) All tag: wunder | qerfi Test Character Player: Absent color: red tag: zapyr Factions: fassione",
    )
    page.get_by_role("link", name="qerfi").click()
    page.get_by_role("link", name="wunder").click()
    page.get_by_role("link", name="qerfi").click()
    page.get_by_role("link", name="qerfi").click()
    expect_normalized(page,
        page.locator("#search-results"),
        "You are including (at least one of these filters) You are excluding (none of these filters) All tag: qerfi Test Character Player: Absent color: red tag: zapyr Factions: fassione Test Teaser wheel Player: Absent color: blue tag: wunder Factions: fassione",
    )


def filter_single(page: Any) -> None:
    # filter single choice
    page.get_by_role("link", name="color").click()
    page.get_by_role("link", name="red").click()
    expect_normalized(page,
        page.locator("#search-results"),
        "You are including (at least one of these filters) You are excluding (none of these filters) color: red None Test Character Player: Absent color: red tag: zapyr Factions: fassione",
    )
    page.get_by_role("link", name="red").click()
    expect_normalized(page,
        page.locator("#search-results"),
        "You are including (at least one of these filters) You are excluding (none of these filters) All color: red another Player: Absent color: blue tag: wunder | qerfi wheel Player: Absent color: blue tag: wunder Factions: fassione",
    )
    page.get_by_role("link", name="red").click()
    page.get_by_role("link", name="color").click()


def filter_faction(page: Any) -> None:
    # filter factions
    expect_normalized(page,
        page.locator("#search-results"),
        "You are including (at least one of these filters) You are excluding (none of these filters) All None Test Character Player: Absent color: red tag: zapyr Factions: fassione Test Teaser another Player: Absent color: blue tag: wunder | qerfi wheel Player: Absent color: blue tag: wunder Factions: fassione",
    )
    page.get_by_role("link", name="Factions").nth(1).click()
    page.locator("#factions").get_by_role("link", name="fassione").click()
    expect_normalized(page,
        page.locator("#search-results"),
        "You are including (at least one of these filters) You are excluding (none of these filters) Factions: fassione None Test Character Player: Absent color: red tag: zapyr Factions: fassione Test Teaser wheel Player: Absent color: blue tag: wunder Factions: fassione",
    )
    page.locator("#factions").get_by_role("link", name="fassione").click()
    expect_normalized(page,
        page.locator("#search-results"),
        "You are including (at least one of these filters) You are excluding (none of these filters) All Factions: fassione another Player: Absent color: blue tag: wunder | qerfi",
    )
    page.get_by_role("link", name="fassione").click()
    page.get_by_role("link", name="Factions").nth(1).click()


def prepare(page: Any, live_server: Any) -> None:
    # prepare
    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="Characters").check()
    page.get_by_role("checkbox", name="Factions").check()
    submit_confirm(page)

    # create faction
    sidebar(page, "Factions")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("fassione")
    submit_confirm(edit_iframe)

    # create form options
    sidebar(page, "Sheet")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("color")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("red")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("blue")
    submit_option(edit_iframe, option_row)

    submit_confirm(edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("m")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("tag")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("wunder")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("zapyr")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("qerfi")
    submit_option(edit_iframe, option_row)

    edit_iframe.locator("#id_visibility").select_option("s")
    submit_confirm(edit_iframe)

    page.locator('[id="u8"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_visibility").select_option("s")
    submit_confirm(edit_iframe)


def characters(page: Any, live_server: Any) -> None:
    # create characters
    page.get_by_role("link", name="Characters").click()
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_role("list").click()
    edit_iframe.get_by_role("searchbox").fill("fas")
    edit_iframe.get_by_role("option", name="fassione (P)").click()
    edit_iframe.locator("#id_que_u8").select_option("u1")
    edit_iframe.get_by_role("checkbox", name="zapyr").check()
    submit_confirm(edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("another")
    edit_iframe.locator("#id_que_u8").select_option("u2")
    edit_iframe.locator("#id_que_u9 div").filter(has_text="qerfi").click()
    edit_iframe.get_by_role("checkbox", name="wunder").check()
    submit_confirm(edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("wheel")
    edit_iframe.locator("#id_que_u8").select_option("u2")
    edit_iframe.get_by_role("searchbox").click()
    edit_iframe.get_by_role("searchbox").fill("fa")
    edit_iframe.get_by_role("option", name="fassione (P)").click()
    edit_iframe.get_by_role("checkbox", name="wunder").check()
    submit_confirm(edit_iframe)
    page.get_by_role("link", name="Faction", exact=True).click()
    page.get_by_role("link", name="color").first.click()
    page.get_by_role("link", name="tag").first.click()
    expect_normalized(page,
        page.locator("#one"),
        "Test Character Test Teaser Test Text fassione red zapyr another blue wunder | qerfi wheel fassione blue wunder",
    )
