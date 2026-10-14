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
Test: Ranking registration question.
Organizer creates a ranking question (options to put in order, only the first
max_length ranked) both in the registration form and in the matchmaker form;
the participant reorders the options, the ranking is persisted, shown as
comma-separated option names in the registration list, and summarized as
average rank per option in the matchmaker answers page.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    click_and_wait_question,
    expect_normalized,
    get_modal_iframe,
    go_to,
    login_orga,
    new_option,
    save_modal,
    submit_option,
    submit_register,
)

pytestmark = pytest.mark.e2e


def test_ranking_question(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # registration form: rank only the first two of three options
    go_to(page, live_server, "/test/manage/form/")
    create_ranking_question(page, "favorite roles", ["warrior", "mage", "rogue"], max_rank="2")

    go_to(page, live_server, "/test/register")
    ranking = page.locator(".ranking")
    expect_order(ranking, ["warrior", "mage", "rogue"])
    # the third option is not ranked
    expect(ranking.locator(".ranking-item").nth(2)).to_have_class("ranking-item ranking-unranked")

    # move rogue to the top with the buttons
    move_up(ranking, "rogue")
    move_up(ranking, "rogue")
    expect_order(ranking, ["rogue", "warrior", "mage"])
    submit_register(page)

    # the saved order is restored
    go_to(page, live_server, "/test/register")
    expect_order(page.locator(".ranking"), ["rogue", "warrior", "mage"])

    # the registration list shows the ranked option names only
    go_to(page, live_server, "/test/manage/registrations/")
    click_and_wait_question(page, "favorite roles")
    expect_normalized(page, page.locator("#one"), "rogue, warrior")

    # matchmaker form: rank all the options, then check the average rank
    go_to(page, live_server, "/test/manage/features/matchmaker/on")
    go_to(page, live_server, "/test/manage/form/matchmaker/")
    create_ranking_question(page, "preferred themes", ["mystery", "romance", "intrigue"], max_rank="0")

    go_to(page, live_server, "/test/matchmaker/")
    ranking = page.locator(".ranking").filter(has_text="intrigue")
    move_up(ranking, "intrigue")
    expect_order(ranking, ["mystery", "intrigue", "romance"])
    page.locator("#matchmaker_go").click()
    expect(page.locator(".jq-toast-single")).to_contain_text("Answers saved")

    go_to(page, live_server, "/test/manage/matchmaker/")
    expect_normalized(page, page.locator("#matchmaker_answers"), "1. mystery, 2. intrigue, 3. romance")
    chart_table = page.locator(".ranking-chart-table")
    expect_normalized(page, chart_table, "mystery 1.0 1")
    expect_normalized(page, chart_table, "intrigue 2.0 1")
    expect_normalized(page, chart_table, "romance 3.0 1")


def create_ranking_question(page: Any, name: str, options: list[str], max_rank: str) -> None:
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("r")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill(name)
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("order them by preference")
    # the max length field is relabeled for the ranking meaning
    expect(edit_iframe.locator("#lbl_id_max_length")).to_have_text("Options to rank")
    edit_iframe.locator("#id_max_length").fill(max_rank)

    for option_name in options:
        option_row = new_option(edit_iframe)
        option_row.locator("#id_name").click()
        option_row.locator("#id_name").fill(option_name)
        submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)


def move_up(ranking: Any, name: str) -> None:
    ranking.locator(".ranking-item", has_text=name).locator(".ranking-up").click()


def expect_order(ranking: Any, names: list[str]) -> None:
    expect(ranking.locator(".ranking-name")).to_have_text(names)
