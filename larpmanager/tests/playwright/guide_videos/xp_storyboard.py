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

"""Guide video: set up abilities and experience points for character progression."""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from larpmanager.tests.playwright.guide_videos.director import ORGANIZER, PLAYER, Director
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    create_character,
    create_event,
    feature_checkbox,
    login_as,
    open_menu,
    open_new,
    pick_character,
    prepare_data,
    register,
    save_modal,
)
from larpmanager.tests.utils import login_orga, login_user

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

pytestmark = pytest.mark.e2e

TITLE = "Character Progression"
PACE = 0.65

EVENT = "Vaelmoor: The Sundering"
CHARACTER = "Mireille Duskwood"
ABILITY_TYPE = "Disciplines"
FIRST_ABILITY = "Blood Sense"
SECOND_ABILITY = "Dominate"
STARTING_XP = "10"
AWARD = "Chapter One Reward"
AWARD_XP = "5"
TOTAL_XP = "15"
BLOCKED_HOLD_SECONDS = 2.5
OWNED_HOLD_SECONDS = 2.0


def owned_ability(page: Page, name: str) -> Locator:
    """Return the entry of an ability in the list of those bought by the character."""
    return page.locator(".inline-p", has_text=name)


def create_ability(director: Director, name: str, cost: str, prerequisite: str = "") -> None:
    """Create an ability; once the basics were shown, only its prerequisite is shown in full."""
    modal = open_new(director)
    director.click(modal.locator("#select2-id_typ-container"))
    director.click(modal.get_by_role("option", name=ABILITY_TYPE))
    enter_text = director.fill if prerequisite else director.type
    enter_text(modal.locator("#id_name"), name)
    enter_text(modal.locator("#id_cost"), cost)
    if prerequisite:
        director.type(modal.get_by_role("row", name="Pre-requisites").get_by_role("searchbox"), prerequisite[:5])
        director.click(modal.get_by_role("option", name=prerequisite))
        director.hold(1.0)
    save_modal(director, modal)


def test_xp_video(director: Director) -> None:
    """Record the experience setup from both the organizer and the player side."""
    page = director.page
    start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=30)
    prepare_data("Vaelmoor Chronicle")
    login_orga(page, director.base_url)
    director.goto("/manage/events")
    director.start()

    director.play_as(ORGANIZER)
    director.step("Step 1: create the event")
    director.say("Create the event, then enable its features")
    slug = create_event(director, EVENT, start)
    open_menu(director, "Features")
    director.check(feature_checkbox(page, "Character creation"))
    director.check(feature_checkbox(page, "Experience points"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 2: configure the event")
    director.say("Set starting XP, and let players pick abilities")
    open_menu(director, "Configuration")
    director.click(page.locator("#main_form").get_by_role("link", name=re.compile(r"^Experience points")))
    director.type(page.locator("#id_exp_start"), STARTING_XP)
    director.check(page.locator("#id_exp_user"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 3: define ability types")
    director.say("Types group abilities for players")
    open_menu(director, "Ability type")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), ABILITY_TYPE)
    save_modal(director, modal)

    director.step("Step 4: create abilities")
    director.say("Each ability has a name, a type and an XP cost")
    open_menu(director, "Abilities")
    create_ability(director, FIRST_ABILITY, "5")
    director.say("Prerequisites build progression trees")
    create_ability(director, SECOND_ABILITY, "10", prerequisite=FIRST_ABILITY)
    expect(page.locator("tr", has_text=SECOND_ABILITY)).to_be_visible()

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/register/"))
    director.step("Step 5: test the player view")
    director.say("Sign up and create a character...")
    register(director)
    create_character(director, CHARACTER, "Voice of the Silver Veil.", "You trade in secrets rather than blood.")
    director.say("...then spend XP on an ability")
    open_menu(director, "Abilities")
    director.click(page.locator(".ability-card", has_text=FIRST_ABILITY))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.spotlight(owned_ability(page, FIRST_ABILITY), OWNED_HOLD_SECONDS)
    director.say(f"{SECOND_ABILITY} is not available: it costs 10 XP, only 5 left")
    expect(page.locator(".ability-card", has_text=SECOND_ABILITY)).to_have_count(0)
    director.spotlight(page.locator("div.exp-stat-row").first, BLOCKED_HOLD_SECONDS)

    director.play_as(ORGANIZER, login_as(director, login_orga, f"/{slug}/manage/"))
    director.step("Step 6: award experience points")
    director.say("Give XP to any group of characters")
    open_menu(director, "Awards")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), AWARD)
    director.type(modal.locator("#id_amount"), AWARD_XP)
    pick_character(director, modal, CHARACTER)
    save_modal(director, modal)
    expect(page.locator("tr", has_text=AWARD)).to_be_visible()

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/"))
    director.say(f"With the award, {SECOND_ABILITY} can now be bought")
    open_menu(director, "Abilities")
    second_ability = page.locator(".ability-card", has_text=SECOND_ABILITY)
    director.click(second_ability)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("All 15 XP are now spent")
    summary = page.locator("div.exp-stat-row").first
    expect(summary.locator(".exp-stat-value").nth(0)).to_have_text(TOTAL_XP)
    expect(summary.locator(".exp-stat-value").nth(1)).to_have_text(TOTAL_XP)
    director.spotlight(summary, 2.0)
    director.say("Bought abilities are listed on the character")
    expect(owned_ability(page, FIRST_ABILITY)).to_be_visible()
    director.spotlight(owned_ability(page, SECOND_ABILITY), 3.0)

    director.stop()
