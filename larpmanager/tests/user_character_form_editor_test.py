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

from larpmanager.tests.utils import fill_tinymce, go_to, login_orga

pytestmark = pytest.mark.e2e


def test_user_character_form_editor(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    prepare(page, live_server)

    field_single(page, live_server)

    field_multiple(page, live_server)

    field_text(page, live_server)

    character(page, live_server)


def prepare(page, live_server):
    # Activate characters
    go_to(page, live_server, "/test/1/manage/features/178/on")

    # Activate player editor
    go_to(page, live_server, "/test/1/manage/features/120/on")

    go_to(page, live_server, "/test/1/manage/config")
    page.get_by_role("link", name="Player editor ").click()
    page.locator("#id_user_character_approval").check()
    page.get_by_role("cell", name="Maximum number of characters").click()
    page.locator("#id_user_character_max").fill("1")
    page.get_by_role("link", name="Character form ").click()
    page.locator("#id_character_form_wri_que_max").check()
    page.locator("#id_character_form_wri_que_dependents").check()
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/test/1/manage/characters/form")
    expect(page.locator('[id="\\31 "]')).to_contain_text("Name")
    expect(page.locator('[id="\\32 "]')).to_contain_text("Presentation")
    expect(page.locator('[id="\\33 "]')).to_contain_text("Sheet")


def field_single(page, live_server):
    # add single
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("single")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("sssssingle")

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("ff")
    page.locator("#id_max_available").click()
    page.locator("#id_max_available").fill("3")
    page.get_by_role("button", name="Confirm", exact=True).click()

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("rrrr")
    page.get_by_role("button", name="Confirm", exact=True).click()

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("wwww")
    page.get_by_role("button", name="Confirm", exact=True).click()

    page.get_by_role("button", name="Confirm", exact=True).click()


def field_multiple(page, live_server):
    # Add multiple
    page.get_by_role("link", name="New").click()
    page.get_by_text("Question type").click()
    page.locator("#id_typ").select_option("m")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("rrrrrr")
    page.locator("#id_max_length").click()
    page.locator("#id_max_length").fill("1")

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("q1")
    page.get_by_role("button", name="Confirm", exact=True).click()

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("q2")
    page.get_by_role("button", name="Confirm", exact=True).click()

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("q3")
    page.get_by_role("button", name="Confirm", exact=True).click()

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("14")
    page.locator("#id_max_available").click()
    page.locator("#id_max_available").fill("3")
    page.get_by_role("row", name="Prerequisites").get_by_role("searchbox").fill("ww")
    page.get_by_role("option", name="Test Larp - single wwww").click()
    page.get_by_role("button", name="Confirm", exact=True).click()

    page.get_by_role("button", name="Confirm", exact=True).click()


def field_text(page, live_server):
    # Add text
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.get_by_role("cell", name="Question name (keep it short)").click()
    page.locator("#id_name").fill("text")
    page.locator("#id_max_length").click()
    page.locator("#id_max_length").fill("10")
    page.get_by_role("button", name="Confirm", exact=True).click()

    # Add paragraph
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("p")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("rrr")
    page.get_by_role("button", name="Confirm", exact=True).click()

    # Create new character
    go_to(page, live_server, "/test/1/manage/characters")
    page.wait_for_timeout(2000)
    page.get_by_role("link", name="New").click()
    page.wait_for_timeout(2000)
    page.locator("#id_name").click()
    page.locator("#id_name").fill("provaaaa")

    fill_tinymce(page, "id_teaser", "adsdsadsa")

    fill_tinymce(page, "id_text", "rrrr")

    page.wait_for_timeout(2000)
    page.locator("#id_q4").select_option("3")
    page.locator("#id_q4").select_option("1")
    page.get_by_role("checkbox", name="q2").check()
    page.locator("#id_q6").click()
    page.locator("#id_q6").fill("sad")
    page.locator("#id_q7").click()
    page.locator("#id_q7").fill("sadsadas")
    page.get_by_role("button", name="Confirm", exact=True).click()


def character(page, live_server):
    # signup, create char
    go_to(page, live_server, "/test/1/register")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    expect(page.locator("#one")).to_contain_text("Access character creation!")
    page.get_by_role("link", name="Access character creation!").click()
    page.wait_for_timeout(2000)
    page.locator("#id_name").click()
    page.locator("#id_name").fill("my character")

    fill_tinymce(page, "id_teaser", "so coool")

    fill_tinymce(page, "id_text", "so braaaave")

    page.locator("#id_q4").select_option("1")
    page.locator("#id_q4").select_option("3")
    page.get_by_role("checkbox", name="- (Available 3)").check()
    page.locator("#id_q6").click()
    page.locator("#id_q6").fill("wow")
    page.locator("#id_q7").click()
    page.locator("#id_q7").fill("asdsadsa")
    page.get_by_role("button", name="Confirm", exact=True).click()

    # confirm char
    expect(page.locator("#one")).to_contain_text("my character (Creation)")
    page.get_by_role("link", name="my character (Creation)").click()
    page.get_by_role("link", name="Change").click()
    page.get_by_role("cell", name="Click here to confirm that").click()
    page.get_by_text("Click here to confirm that").click()
    page.locator("#id_propose").check()
    page.get_by_role("button", name="Confirm", exact=True).click()

    # check char
    expect(page.locator("#one")).to_contain_text("my character (Proposed)")

    # approve char
    go_to(page, live_server, "/test/1/manage/characters")
    page.locator('[id="\\33 "]').get_by_role("link", name="").click()
    page.locator("#id_status").select_option("a")
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/test/1/register")
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect(page.locator("#one")).to_contain_text("my character")

    go_to(page, live_server, "/test/1")
    expect(page.locator("#one")).to_contain_text("my character")
