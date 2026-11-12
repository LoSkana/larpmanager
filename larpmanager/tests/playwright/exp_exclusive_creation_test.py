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

"""Test: Experience points creation only abilities and exclusive groups.
Verifies that participants cannot obtain more abilities of an exclusive group than its maximum,
and that creation only abilities disappear once the character is approved.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    _select2_search_and_pick,
    _wait_lm_ready,
    get_modal_iframe,
    go_to,
    login_orga,
    save_modal,
    submit_confirm,
    submit_register,
)

pytestmark = pytest.mark.e2e


def test_exp_exclusive_creation(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    setup(live_server, page)

    abilities(live_server, page)

    exclusive_group(live_server, page)

    assign_character(live_server, page)

    player_choice(live_server, page)

    approve_character(live_server, page)

    player_after_approval(live_server, page)


def setup(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/manage/features/character/on")
    go_to(page, live_server, "/test/manage/features/user_character/on")
    go_to(page, live_server, "/test/manage/features/experience/on")

    go_to(page, live_server, "/test/manage/config/")
    page.locator("#main_form").get_by_role("link", name=re.compile(r"^Experience points")).click()
    page.locator("#id_exp_start").fill("10")
    page.locator("#id_exp_user").check()
    page.locator("#id_exp_exclusives").check()
    page.locator("#main_form").get_by_role("link", name=re.compile(r"^Character creation")).click()
    page.locator("#id_user_character_max").fill("1")
    page.locator("#id_user_character_approval").check()
    submit_confirm(page)


def new_ability(page: Any, name: str, *, creation_only: bool = False) -> None:
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_typ-container").click()
    _select2_search_and_pick(edit_iframe.locator(".select2-container--open .select2-search__field"), edit_iframe, "base")
    edit_iframe.locator("#id_name").fill(name)
    edit_iframe.locator("#id_cost").fill("1")
    if creation_only:
        edit_iframe.locator("#id_creation_only").check()
    save_modal(page, edit_iframe)


def abilities(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/manage/experience/ability_types/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("base ability")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/manage/experience/abilities/")
    new_ability(page, "sword")
    new_ability(page, "axe")
    new_ability(page, "noble birth", creation_only=True)


def exclusive_group(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/manage/experience/exclusives/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Weapons")
    edit_iframe.locator("#id_max_count").fill("1")
    searchbox = edit_iframe.locator("#id_abilities_tr").get_by_role("searchbox")
    _select2_search_and_pick(searchbox, edit_iframe, "swo")
    _select2_search_and_pick(searchbox, edit_iframe, "axe")
    save_modal(page, edit_iframe)
    expect(page.locator("#exclusives")).to_contain_text("Weapons")
    expect(page.locator("#exclusives")).to_contain_text("sword")
    expect(page.locator("#exclusives")).to_contain_text("axe")


def assign_character(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/")
    page.get_by_role("link", name="Registrations are open!").click()
    submit_register(page)

    go_to(page, live_server, "/test/manage/registrations/")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_role("searchbox").fill("te")
    edit_iframe.get_by_role("option", name="Test Character").click()
    save_modal(page, edit_iframe)

    # make sure the character is still in creation
    go_to(page, live_server, "/test/manage/characters/")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_status").select_option("c")
    save_modal(page, edit_iframe)


def open_abilities(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/gallery/")
    # with the approval process the gallery also links the confirm page: open the character sheet link
    href = page.locator("a[href*='/character/']", has_text="Test Character").evaluate_all(
        "els => els.map(el => el.getAttribute('href')).find(h => /\\/character\\/[^/]+\\/$/.test(h))"
    )
    go_to(page, live_server, re.sub(r"^https?://[^/]+", "", href) + "abilities/")
    _wait_lm_ready(page)


def player_choice(live_server: Any, page: Any) -> None:
    open_abilities(live_server, page)
    grid = page.locator(".ability-cards-grid")
    expect(grid).to_contain_text("sword")
    expect(grid).to_contain_text("axe")
    expect(grid).to_contain_text("noble birth")
    expect(page.locator(".ability-card", has_text="axe")).to_contain_text("Exclusive group: Weapons (0/1)")
    expect(page.locator(".ability-card", has_text="noble birth")).to_contain_text(
        "Available only until the character is approved"
    )

    # obtaining one ability of the group hides the other one
    page.locator(".ability-card", has_text="sword").click()
    submit_confirm(page)
    _wait_lm_ready(page)
    expect(grid).to_contain_text("noble birth")
    expect(grid).not_to_contain_text("axe")
    expect(grid).not_to_contain_text("sword")


def approve_character(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/manage/characters/")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_status").select_option("a")
    save_modal(page, edit_iframe)


def player_after_approval(live_server: Any, page: Any) -> None:
    open_abilities(live_server, page)
    expect(page.locator(".ability-cards-grid")).not_to_contain_text("noble birth")
    expect(page.locator("#one")).to_contain_text("No abilities found")
