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
from playwright.sync_api import expect

from larpmanager.tests.utils import just_wait, go_to, login_orga, expect_normalized, submit_confirm

pytestmark = pytest.mark.e2e


def test_user_search(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    prepare(page, live_server)

    characters(page, live_server)

    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="Search", exact=True).click()

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
    go_to(page, live_server, "/test/manage")
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="Characters").check()
    page.get_by_role("checkbox", name="Factions").check()
    submit_confirm(page)

    # create faction
    page.get_by_role("link", name="Factions", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("fassione")
    submit_confirm(page)

    # create form options
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("color")

    page.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("iframe").content_frame.locator("#id_name").click()
    page.locator("iframe").content_frame.locator("#id_name").fill("red")
    page.locator("iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    page.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("iframe").content_frame.locator("#id_name").click()
    page.locator("iframe").content_frame.locator("#id_name").fill("blue")
    page.locator("iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    page.get_by_text("After confirmation, add").click()
    submit_confirm(page)
    page.locator("#id_typ").select_option("m")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("tag")

    page.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("iframe").content_frame.locator("#id_name").click()
    page.locator("iframe").content_frame.locator("#id_name").fill("wunder")
    page.locator("iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    page.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("iframe").content_frame.locator("#id_name").click()
    page.locator("iframe").content_frame.locator("#id_name").fill("zapyr")
    page.locator("iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    page.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("iframe").content_frame.locator("#id_name").click()
    page.locator("iframe").content_frame.locator("#id_name").fill("qerfi")
    page.locator("iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    page.locator("#id_visibility").select_option("s")
    submit_confirm(page)

    page.locator('[id="u8"]').get_by_role("link", name="").click()
    page.locator("#id_visibility").select_option("s")
    submit_confirm(page)


def characters(page: Any, live_server: Any) -> None:
    # create characters
    page.get_by_role("link", name="Characters").click()
    page.get_by_role("link", name="").click()
    page.get_by_role("list").click()
    page.get_by_role("searchbox").fill("fas")
    page.get_by_role("option", name="fassione (P)").click()
    page.locator("#id_que_u8").select_option("u1")
    page.get_by_role("checkbox", name="zapyr").check()
    page.get_by_text("After confirmation, add").click()
    submit_confirm(page)
    page.locator("#id_name").click()
    page.locator("#id_name").fill("another")
    page.locator("#id_que_u8").select_option("u2")
    page.locator("#id_que_u9 div").filter(has_text="qerfi").click()
    page.get_by_role("checkbox", name="wunder").check()
    page.get_by_role("checkbox", name="After confirmation, add").check()
    submit_confirm(page)
    page.locator("#id_name").click()
    page.locator("#id_name").fill("wheel")
    page.locator("#id_que_u8").select_option("u2")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("fa")
    page.get_by_role("option", name="fassione (P)").click()
    page.get_by_role("checkbox", name="wunder").check()
    submit_confirm(page)
    page.get_by_role("link", name="Faction", exact=True).click()
    page.get_by_role("link", name="color").first.click()
    page.get_by_role("link", name="tag").first.click()
    expect_normalized(page,
        page.locator("#one"),
        "#1 Test Character Test Teaser Test Text fassione red zapyr #2 another blue wunder | qerfi #3 wheel fassione blue wunder",
    )
