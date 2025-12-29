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

from larpmanager.tests.utils import go_to, login_orga, expect_normalized_text

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
    expect_normalized_text(
        page.locator("#one"),
        "You are including (at least one of these filters) You are excluding (none of these filters) tag: wunder None anotherPlayer: Absentcolor: bluetag: qerfi, wunderwheelPlayer: Absentcolor: bluetag: wunderFactions: fassione Test Teaser",
    )
    page.get_by_role("link", name="qerfi").click()
    expect_normalized_text(
        page.locator("#one"),
        "You are including (at least one of these filters) You are excluding (none of these filters) tag: wunder, qerfi None anotherPlayer: Absentcolor: bluetag: qerfi, wunderwheelPlayer: Absentcolor: bluetag: wunderFactions: fassione Test Teaser",
    )
    page.get_by_role("link", name="wunder").click()
    page.get_by_role("link", name="zapyr").click()
    expect_normalized_text(
        page.locator("#one"),
        "You are including (at least one of these filters) You are excluding (none of these filters) tag: qerfi, zapyr tag: wunder Test CharacterPlayer: Absentcolor: redtag: zapyrFactions: fassioneTest Teaser Test Teaser",
    )
    page.get_by_role("link", name="qerfi").click()
    page.get_by_role("link", name="zapyr").click()
    page.get_by_role("link", name="zapyr").click()
    expect_normalized_text(
        page.locator("#one"),
        "You are including (at least one of these filters) You are excluding (none of these filters) All tag: wunder, qerfi Test CharacterPlayer: Absentcolor: redtag: zapyrFactions: fassioneTest Teaser Test Teaser",
    )
    page.get_by_role("link", name="qerfi").click()
    page.get_by_role("link", name="wunder").click()
    page.get_by_role("link", name="qerfi").click()
    page.get_by_role("link", name="qerfi").click()
    expect_normalized_text(
        page.locator("#one"),
        "You are including (at least one of these filters) You are excluding (none of these filters) All tag: qerfi Test CharacterPlayer: Absentcolor: redtag: zapyrFactions: fassioneTest Teaser wheelPlayer: Absentcolor: bluetag: wunderFactions: fassione Test Teaser",
    )


def filter_single(page: Any) -> None:
    # filter single choice
    page.get_by_role("link", name="color").click()
    page.get_by_role("link", name="red").click()
    expect_normalized_text(
        page.locator("#one"),
        "You are including (at least one of these filters) You are excluding (none of these filters) color: red None Test CharacterPlayer: Absentcolor: redtag: zapyrFactions: fassioneTest Teaser Test Teaser",
    )
    page.get_by_role("link", name="red").click()
    expect_normalized_text(
        page.locator("#one"),
        "You are including (at least one of these filters) You are excluding (none of these filters) All color: red anotherPlayer: Absentcolor: bluetag: qerfi, wunderwheelPlayer: Absentcolor: bluetag: wunderFactions: fassione Test Teaser",
    )
    page.get_by_role("link", name="red").click()
    page.get_by_role("link", name="color").click()


def filter_faction(page: Any) -> None:
    # filter factions
    expect_normalized_text(
        page.locator("#one"),
        "You are including (at least one of these filters) You are excluding (none of these filters) All None Test CharacterPlayer: Absentcolor: redtag: zapyrFactions: fassioneTest Teaser anotherPlayer: Absentcolor: bluetag: qerfi, wunderwheelPlayer: Absentcolor: bluetag: wunderFactions: fassione Test Teaser",
    )
    page.get_by_role("link", name="Factions").nth(1).click()
    page.locator("#factions").get_by_role("link", name="fassione").click()
    expect_normalized_text(
        page.locator("#one"),
        "You are including (at least one of these filters) You are excluding (none of these filters) Factions: fassione None Test CharacterPlayer: Absentcolor: redtag: zapyrFactions: fassioneTest Teaser wheelPlayer: Absentcolor: bluetag: wunderFactions: fassione Test Teaser",
    )
    page.locator("#factions").get_by_role("link", name="fassione").click()
    expect_normalized_text(
        page.locator("#wrapper"),
        "You are including (at least one of these filters) You are excluding (none of these filters) All Factions: fassione anotherPlayer: Absentcolor: bluetag: qerfi, wunder Test Teaser",
    )
    page.get_by_role("link", name="fassione").click()
    page.get_by_role("link", name="Factions").nth(1).click()


def prepare(page: Any, live_server: Any) -> None:
    # prepare
    login_orga(page, live_server)
    go_to(page, live_server, "/test/manage")
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Characters").check()
    page.get_by_role("checkbox", name="Factions").check()
    page.get_by_role("button", name="Confirm").click()

    # create faction
    page.get_by_role("link", name="Factions", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("fassione")
    page.get_by_role("button", name="Confirm").click()

    # create form options
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    page.get_by_role("link", name="New").click()
    page.get_by_role("cell", name="Question name (keep it short)").click()
    page.locator("#id_name").fill("color")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("red")
    page.get_by_role("checkbox", name="After confirmation, add").check()
    page.get_by_role("button", name="Confirm").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("blue")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_text("After confirmation, add").click()
    page.get_by_role("button", name="Confirm").click()
    page.locator("#id_typ").select_option("m")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("tag")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("wunder")
    page.get_by_text("After confirmation, add").click()
    page.get_by_role("button", name="Confirm").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("zapyr")
    page.get_by_text("After confirmation, add").click()
    page.get_by_role("button", name="Confirm").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("qerfi")
    page.get_by_role("button", name="Confirm").click()
    page.locator("#id_visibility").select_option("s")
    page.get_by_role("button", name="Confirm").click()
    page.locator('[id="u8"]').get_by_role("link", name="").click()
    page.locator("#id_visibility").select_option("s")
    page.get_by_role("button", name="Confirm").click()


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
    page.get_by_role("button", name="Confirm").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("another")
    page.locator("#id_que_u8").select_option("u2")
    page.locator("#id_que_u9 div").filter(has_text="qerfi").click()
    page.get_by_role("checkbox", name="wunder").check()
    page.get_by_role("checkbox", name="After confirmation, add").check()
    page.get_by_role("button", name="Confirm").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("wheel")
    page.locator("#id_que_u8").select_option("u2")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("fa")
    page.get_by_role("option", name="fassione (P)").click()
    page.get_by_role("checkbox", name="wunder").check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Faction", exact=True).click()
    page.get_by_role("link", name="color").first.click()
    page.get_by_role("link", name="tag").first.click()
    expect_normalized_text(
        page.locator("#one"),
        "#1 Test Character Test Teaser Test Text fassione redzapyr #2 another bluewunder, qerfi #3 wheel fassione bluewunder",
    )
