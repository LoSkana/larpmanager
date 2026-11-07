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

"""Guide video: let players create characters through a staff approval process."""

from __future__ import annotations

import datetime as dt
import re

import pytest
from playwright.sync_api import expect

from larpmanager.tests.playwright.guide_videos.director import ORGANIZER, PLAYER, Director
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    create_event,
    feature_checkbox,
    login_as,
    open_character_form,
    open_menu,
    open_new,
    prepare_data,
    register,
    save_modal,
    submit_character,
)
from larpmanager.tests.utils import get_modal_iframe, login_orga, login_user, new_option, submit_option

pytestmark = pytest.mark.e2e

TITLE = "Character Creation"
PACE = 0.7

EVENT = "Vaelmoor: The Sundering"
CHARACTER = "Mireille Duskwood"
LOCKED_FIELD = "Clan"
LOCKED_OPTIONS = ("Ashblood Court", "Silver Veil")
EDITABLE_FIELD = "Personal Notes"
NOTES = "Trusts no one at court."


def test_creation_video(director: Director) -> None:
    """Record the character approval process from both the organizer and the player side."""
    page = director.page
    start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=30)
    prepare_data("Vaelmoor Chronicle")
    login_orga(page, director.base_url)
    director.goto("/manage/events")
    director.start()

    director.play_as(ORGANIZER)
    director.step("Step 1: create the event")
    director.say("Create the event, then enable character creation")
    slug = create_event(director, EVENT, start)
    open_menu(director, "Features")
    director.check(feature_checkbox(page, "Character creation"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 2: configure the event")
    director.say("Turn on the approval process")
    director.hold(0.8)
    director.check(page.locator("#id_user_character_approval"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 3: define character fields")
    director.say("Add the fields players fill in")
    open_menu(director, "Sheet")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), LOCKED_FIELD)
    director.say("This field locks once the character is approved")
    director.click(modal.locator('label[for="id_editable_3"]'))
    for option_name in LOCKED_OPTIONS:
        option = new_option(modal)
        director.fill(option.locator("#id_name"), option_name)
        submit_option(modal, option)
    save_modal(director, modal)
    director.say("This one stays editable after approval")
    modal = open_new(director)
    director.select(modal.locator("#id_typ"), "t")
    director.type(modal.locator("#id_name"), EDITABLE_FIELD)
    save_modal(director, modal)
    director.hold(1.5)

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/register/"))
    director.step("Step 4: test the player view")
    director.say("Sign up and fill in the character form")
    register(director)
    open_character_form(director, CHARACTER)
    director.click(page.locator("label", has_text=LOCKED_OPTIONS[1]))
    director.type(page.locator('input[type="text"][id^="id_que_"]'), NOTES)
    submit_character(director, "Voice of the Silver Veil.", "You trade in secrets rather than blood.")

    director.step("Step 5: propose the character")
    director.say("The player confirms and submits the character")
    open_menu(director, "Confirm character")
    director.click(page.get_by_text("Click here to confirm that"))
    director.confirm(page.get_by_role("button", name="Confirm"), settle=1.0)
    expect(page.locator("#one")).to_contain_text("Status: Proposed")
    director.hold(1.5)

    director.play_as(ORGANIZER, login_as(director, login_orga, f"/{slug}/manage/"))
    director.say("Staff see the character waiting for approval")
    director.spotlight(page.get_by_text("characters to approve"), 2.0)
    director.say("They can request changes or approve")
    director.click(page.locator("#sidebar").get_by_role("link", name=re.compile(r"^Characters")))
    director.click(page.locator("tr", has_text=CHARACTER).locator(".fa-edit"), settle=0.8)
    modal = get_modal_iframe(page)
    director.select(modal.locator("#id_status"), "a")
    save_modal(director, modal)
    director.hold(1.5)

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/"))
    director.step("Step 6: approval and publishing")
    director.say("The approved character is in the gallery")
    open_menu(director, "Gallery")
    director.spotlight(page.get_by_role("link", name=CHARACTER).last, 2.5)
    director.say(f"{LOCKED_FIELD} is now locked, {EDITABLE_FIELD} stays editable")
    open_menu(director, "Edit")
    expect(page.locator("label", has_text=LOCKED_OPTIONS[1])).to_have_count(0)
    director.spotlight(page.locator('input[type="text"][id^="id_que_"]'), 3.0)

    director.stop()
