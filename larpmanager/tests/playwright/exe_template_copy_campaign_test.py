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
Test: Event copying, campaigns, and templates.
Verifies copying events with all settings/data, creating campaign events inheriting from parents,
and creating event templates for reusable configurations.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import fill_date, check_feature, go_to, login_orga, submit_confirm, \
    expect_normalized, _checkboxes, fill_tinymce, get_modal_iframe, save_modal, click_and_wait_question, char_dual_pick

pytestmark = pytest.mark.e2e


def test_exe_template_copy(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    setup(live_server, page)

    copy(live_server, page)

    campaign(live_server, page)

    template(live_server, page)


def template(live_server: Any, page: Any) -> None:
    # Activate template
    go_to(page, live_server, "/manage/features/template/on")
    go_to(page, live_server, "/manage/template")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_role("row", name="Name").locator("td").click()
    edit_iframe.locator("#id_name").fill("template")
    edit_iframe.get_by_role("checkbox", name="Characters").check()
    edit_iframe.locator("div.feature_checkbox", has_text="Copy").locator("input[type='checkbox']").check()
    save_modal(page, edit_iframe)
    page.get_by_role("link", name="Add").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("base role")
    page.locator("#id_name").press("Tab")
    page.get_by_role("searchbox").fill("user")
    page.get_by_role("option", name="User Test - user@test.it").click()
    check_feature(page, "Texts")
    submit_confirm(page)
    page.locator("#one").get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name=re.compile(r"^Gallery ")).click()
    page.locator("#id_gallery_hide_signup").check()
    submit_confirm(page)
    # create new event from template
    go_to(page, live_server, "/manage/events")

    page.get_by_role("link", name="New event").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_form1-name").click()
    edit_iframe.locator("#id_form1-name").fill("from template")
    edit_iframe.locator("#id_form1-name").press("Tab")
    edit_iframe.locator("#slug").fill("fromtemplate")
    # the template should be auto-selected
    fill_date(edit_iframe, "#id_form2-start", "2050-01-01")
    fill_date(edit_iframe, "#id_form2-end", "2050-01-03")
    save_modal(page, edit_iframe)

    # check roles
    go_to(page, live_server, "/fromtemplate/manage/roles/")
    row = page.locator('tr:has-text("User Test")')
    expect_normalized(page, row, "User Test")
    expect_normalized(page, row, "Texts")
    # check configuration
    go_to(page, live_server, "/fromtemplate/manage/config/")
    page.get_by_role("link", name=re.compile(r"^Gallery ")).click()
    expect(page.locator("#id_gallery_hide_signup")).to_be_checked()
    # check features
    go_to(page, live_server, "/fromtemplate/manage/features")
    expect(page.get_by_role("checkbox", name="Characters")).to_be_checked()
    expect(page.locator("div.feature_checkbox", has_text="Copy").locator("input[type='checkbox']")).to_be_checked()

def setup(live_server: Any, page: Any) -> None:
    # activate factions
    go_to(page, live_server, "/test/manage/features/faction/on")
    # activate xp
    go_to(page, live_server, "/test/manage/features/experience/on")
    # activate characters
    go_to(page, live_server, "/test/manage/features/character/on")
    # configure test larp
    go_to(page, live_server, "/test/manage/config/")
    page.get_by_role("link", name=re.compile(r"^Gallery ")).click()
    page.locator("#id_gallery_hide_login").check()
    page.get_by_role("link", name=re.compile(r"^Experience points\s.+")).click()
    page.locator("#id_exp_start").click()
    page.locator("#id_exp_start").fill("10")

    submit_confirm(page)

    go_to(page, live_server, "/test/manage/roles/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("blabla")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.get_by_role("searchbox").fill("user")
    edit_iframe.get_by_role("option", name="User Test - user@test.it").click()
    check_feature(edit_iframe, "Navigation")
    check_feature(edit_iframe, "Factions")
    save_modal(page, edit_iframe)

    # give ability xp
    go_to(page, live_server, "/test/manage/experience/ability_types/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("base ability")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/manage/experience/abilities/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("standard")
    edit_iframe.locator("#id_cost").click()
    edit_iframe.locator("#id_name").dblclick()
    edit_iframe.locator("#id_name").fill("sword")
    edit_iframe.locator("#id_cost").click()
    edit_iframe.locator("#id_cost").fill("1")
    fill_tinymce(edit_iframe, "id_descr", "sdsfdsfds", False)
    char_dual_pick(edit_iframe, "te", "Test Character")
    save_modal(page, edit_iframe)

    # give delivery xp
    go_to(page, live_server, "/test/manage/experience/deliveries/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("first live")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_amount").fill("2")
    char_dual_pick(edit_iframe, "te", "Test Character")
    save_modal(page, edit_iframe)


def copy(live_server: Any, page: Any) -> None:
    # copy event
    go_to(page, live_server, "/manage/events")

    page.get_by_role("link", name="New event").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_form1-name").click()
    edit_iframe.locator("#id_form1-name").fill("copy")
    edit_iframe.locator("#id_form1-name").press("Tab")
    edit_iframe.locator("#slug").fill("copy")
    fill_date(edit_iframe, "#id_form2-start", "2050-01-01")
    fill_date(edit_iframe, "#id_form2-end", "2050-01-03")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/copy/manage/features/copy/on")
    go_to(page, live_server, "/copy/manage/copy/")

    page.locator("#select2-id_parent-container").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="Test Larp").click()

    # copy everything
    _checkboxes(page, True)

    go_to(page, live_server, "/copy/manage/roles/")
    row = page.locator('tr:has-text("User Test")')
    expect_normalized(page, row, "User Test")
    expect_normalized(page, row, "Appearance (Navigation), Writing (Factions) ")

    go_to(page, live_server, "/copy/manage/config/")
    page.get_by_role("link", name=re.compile(r"^Gallery ")).click()
    expect(page.locator("#id_gallery_hide_login")).to_be_checked()
    page.get_by_role("link", name=re.compile(r"^Experience points\s.+")).click()
    expect(page.locator("#id_exp_start")).to_have_value("10")

    go_to(page, live_server, "/copy/manage/characters/")
    click_and_wait_question(page, "Experience")
    char_row = page.locator('tr:has-text("Test Character")')
    expect_normalized(page, char_row, "12")
    expect_normalized(page, char_row, "1")
    expect_normalized(page, char_row, "11")


def campaign(live_server: Any, page: Any) -> None:
    # create campaign
    go_to(page, live_server, "/manage/features/campaign/on")
    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New event").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_form1-name").click()
    edit_iframe.locator("#id_form1-name").fill("campaign")
    edit_iframe.locator("#id_form1-name").press("Tab")
    edit_iframe.locator("#slug").fill("campaign")
    expect(edit_iframe.locator("#slug")).to_have_value("campaign")
    edit_iframe.locator("#select2-id_form1-parent-container").click()
    edit_iframe.get_by_role("searchbox").fill("tes")
    edit_iframe.get_by_role("option", name="Test Larp", exact=True).click()
    fill_date(edit_iframe, "#id_form2-start", "2050-01-01")
    fill_date(edit_iframe, "#id_form2-end", "2050-01-03")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/campaign/manage/characters/")
    click_and_wait_question(page, "Experience")
    char_row = page.locator('tr:has-text("Test Character")').first
    expect_normalized(page, char_row, "12")
    expect_normalized(page, char_row, "1")
    expect_normalized(page, char_row, "11")
