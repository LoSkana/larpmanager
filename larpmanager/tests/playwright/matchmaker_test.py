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
Test: Matchmaker feature.
Fully separate from casting: organizer builds a matchmaker form (text, paragraph,
single choice, multiple choice questions) reusing the orga_registration_form
machinery with registration_type="matchmaker", a participant fills it on a
dedicated page linked to their registration, and the organizer reviews all
participants' answers on a dedicated review page.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    click_option,
    expand_options,
    expect_normalized,
    get_modal_iframe,
    go_to,
    login_orga,
    login_user,
    logout,
    new_option,
    save_modal,
    submit_option,
    submit_register,
)

pytestmark = pytest.mark.e2e


def test_matchmaker(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    enable_matchmaker(page, live_server)

    create_matchmaker_form(page, live_server)

    register(page, live_server)

    fill_matchmaker(page, live_server, short_value="orga likes elves", long_value="orga backstory notes")

    check_answers_after_orga_fill(page, live_server)

    logout(page)
    login_user(page, live_server)

    register(page, live_server)

    fill_matchmaker(page, live_server, short_value="user likes rogues", long_value="user backstory notes")

    logout(page)
    login_orga(page, live_server)

    check_answers(page, live_server)


def enable_matchmaker(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/features/matchmaker/on")


def create_matchmaker_form(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/form/matchmaker/")

    # short text question
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("what would you like to play")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("short description of your ideal role")
    save_modal(page, edit_iframe)

    # long text (paragraph) question
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("p")
    edit_iframe.locator("#id_typ").press("Tab")
    edit_iframe.locator("#id_name").fill("backstory notes")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("anything else the staff should know")
    save_modal(page, edit_iframe)

    # single choice question
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("preferred faction")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("choose one faction")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("heroes")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("villains")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)

    # multiple choice question
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("m")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("preferred themes")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("choose any number of themes")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("mystery")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("romance")
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("intrigue")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)

    # the standard registration form must not show the matchmaker questions
    go_to(page, live_server, "/test/manage/form/")
    expect(page.get_by_text("what would you like to play")).to_have_count(0)


def register(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/register")
    submit_register(page)


def fill_matchmaker(page: Any, live_server: Any, short_value: str, long_value: str) -> None:
    go_to(page, live_server, "/test/matchmaker/")

    # matchmaker questions must not be mixed into the standard registration form
    expect(page.locator("#matchmaker")).to_be_visible()

    # the form is bound to the existing registration: the options start collapsed
    expand_options(page)

    page.get_by_role("textbox", name="what would you like to play").fill(short_value)
    page.get_by_role("textbox", name="backstory notes").fill(long_value)

    click_option(page.get_by_role("radio", name="villains"))
    click_option(page.get_by_role("checkbox", name="mystery"))
    click_option(page.get_by_role("checkbox", name="intrigue"))

    page.locator("#matchmaker_go").click()
    expect(page.locator(".jq-toast-single")).to_contain_text("Answers saved")

    # reload and check the answers were actually persisted
    go_to(page, live_server, "/test/matchmaker/")
    # the answers are already saved: unselected options start collapsed
    expand_options(page)
    expect(page.get_by_role("textbox", name="what would you like to play")).to_have_value(short_value)
    expect(page.get_by_role("textbox", name="backstory notes")).to_have_value(long_value)
    expect(page.get_by_role("radio", name="villains")).to_be_checked()
    expect(page.get_by_role("radio", name="heroes")).not_to_be_checked()
    expect(page.get_by_role("checkbox", name="mystery")).to_be_checked()
    expect(page.get_by_role("checkbox", name="intrigue")).to_be_checked()
    expect(page.get_by_role("checkbox", name="romance")).not_to_be_checked()


def check_answers_after_orga_fill(page: Any, live_server: Any) -> None:
    # sanity check: the GM review page loads and lists the orga's own answers
    go_to(page, live_server, "/test/manage/matchmaker/")
    expect_normalized(page, page.locator("#matchmaker_answers"), "orga likes elves")
    expect_normalized(page, page.locator("#matchmaker_answers"), "orga backstory notes")
    expect_normalized(page, page.locator("#matchmaker_answers"), "villains")
    expect_normalized(page, page.locator("#matchmaker_answers"), "mystery")
    expect_normalized(page, page.locator("#matchmaker_answers"), "intrigue")


def check_answers(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/matchmaker/")

    table = page.locator("#matchmaker_answers")
    expect_normalized(page, table, "what would you like to play")
    expect_normalized(page, table, "backstory notes")
    expect_normalized(page, table, "preferred faction")
    expect_normalized(page, table, "preferred themes")

    # both participants show up with their own answers
    expect_normalized(page, table, "orga likes elves")
    expect_normalized(page, table, "orga backstory notes")
    expect_normalized(page, table, "user likes rogues")
    expect_normalized(page, table, "user backstory notes")

    rows = table.locator("tbody tr")
    expect(rows).to_have_count(2)
