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
Test: Reordering of shared campaign elements (characters, abilities) from a child event.
Verifies that reordering characters/abilities done in a child campaign event is persisted
both on the child event and on the parent event, since these elements are shared.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    _select2_search_and_pick,
    check_feature,
    drag_reorder,
    fill_date,
    get_modal_iframe,
    go_to,
    login_orga,
    save_modal,
    sidebar,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def test_campaign_reorder(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    create_child_event(live_server, page)

    setup_parent(live_server, page)

    reorder_characters(live_server, page)

    reorder_abilities(live_server, page)


def create_child_event(live_server: Any, page: Any) -> None:
    # activate campaign feature and create child event with Test Larp as parent
    go_to(page, live_server, "/manage/features/campaign/on")
    go_to(page, live_server, "/manage/events")
    page.get_by_role("link", name="New event").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_form1-name").click()
    edit_iframe.locator("#id_form1-name").fill("child reorder")
    edit_iframe.locator("#id_form1-name").press("Tab")
    edit_iframe.locator("#slug").fill("childreorder")
    expect(edit_iframe.locator("#slug")).to_have_value("childreorder")
    edit_iframe.locator("#select2-id_form1-parent-container").click()
    edit_iframe.get_by_role("searchbox").fill("tes")
    edit_iframe.get_by_role("option", name="Test Larp", exact=True).click()
    fill_date(edit_iframe, "#id_form2-start", "2050-03-01")
    fill_date(edit_iframe, "#id_form2-end", "2050-03-03")
    save_modal(page, edit_iframe)


def setup_parent(live_server: Any, page: Any) -> None:
    # activate features needed on parent event
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Features")
    check_feature(page, "Characters")
    check_feature(page, "Experience points")
    submit_confirm(page)

    # create a second character on the parent, so there is something to reorder
    go_to(page, live_server, "/test/manage/characters/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Reorder Character")
    save_modal(page, edit_iframe)

    # create ability type + two abilities on the parent
    go_to(page, live_server, "/test/manage/experience/ability_types/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("reorder type")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/manage/experience/abilities/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_typ-container").click()
    _select2_search_and_pick(edit_iframe.locator(".select2-container--open .select2-search__field"), edit_iframe, "reorder")
    edit_iframe.locator("#id_name").fill("ability alpha")
    edit_iframe.locator("#id_cost").fill("1")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_typ-container").click()
    _select2_search_and_pick(edit_iframe.locator(".select2-container--open .select2-search__field"), edit_iframe, "reorder")
    edit_iframe.locator("#id_name").fill("ability beta")
    edit_iframe.locator("#id_cost").fill("1")
    save_modal(page, edit_iframe)


def reorder_characters(live_server: Any, page: Any) -> None:
    # go to child event characters list, both characters are inherited from the parent
    go_to(page, live_server, "/childreorder/manage/characters/")
    rows = page.locator(".writing_list tbody tr")
    first_row = rows.first
    expect(first_row).to_contain_text("Test Character")

    # swap first two rows by dragging the second row onto the first
    drag_reorder(page, rows.nth(1).locator("td.reorder-handle"), rows.nth(0))

    # verify new order persists on the child event
    go_to(page, live_server, "/childreorder/manage/characters/")
    rows = page.locator(".writing_list tbody tr")
    expect(rows.first).to_contain_text("Reorder Character")

    # verify new order persists on the parent event too (shared element)
    go_to(page, live_server, "/test/manage/characters/")
    rows = page.locator(".writing_list tbody tr")
    expect(rows.first).to_contain_text("Reorder Character")


def reorder_abilities(live_server: Any, page: Any) -> None:
    # go to child event abilities list, both abilities are inherited from the parent
    go_to(page, live_server, "/childreorder/manage/experience/abilities/")
    rows = page.locator("#abilities tbody tr")
    first_row = rows.first
    expect(first_row).to_contain_text("ability alpha")

    # swap first two rows by dragging the second row onto the first
    drag_reorder(page, rows.nth(1).locator("td.reorder-handle"), rows.nth(0))

    # verify new order persists on the child event
    go_to(page, live_server, "/childreorder/manage/experience/abilities/")
    rows = page.locator("#abilities tbody tr")
    expect(rows.first).to_contain_text("ability beta")

    # verify new order persists on the parent event too (shared element)
    go_to(page, live_server, "/test/manage/experience/abilities/")
    rows = page.locator("#abilities tbody tr")
    expect(rows.first).to_contain_text("ability beta")
