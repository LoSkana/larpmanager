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

"""Guide video: set up a campaign whose characters carry over between events."""

from __future__ import annotations

import datetime as dt

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
    prepare_data,
    register,
)
from larpmanager.tests.utils import login_orga, login_user

pytestmark = pytest.mark.e2e

TITLE = "Campaigns"

FIRST_EVENT = "Vaelmoor: The Sundering"
SECOND_EVENT = "Vaelmoor: The Last Vigil"
CHARACTER = "Mireille Duskwood"


def test_campaign_video(director: Director) -> None:
    """Record the campaign setup from both the organizer and the player side."""
    page = director.page
    today = dt.datetime.now(tz=dt.UTC).date()
    prepare_data("Vaelmoor Chronicle")
    login_orga(page, director.base_url)
    director.goto("/manage/events")
    director.start()

    director.play_as(ORGANIZER)
    director.step("Step 1: create the first event")
    director.say("Start from a regular event, no special settings needed")
    first_slug = create_event(director, FIRST_EVENT, today + dt.timedelta(days=30))

    director.step("Step 2: enable character creation")
    director.say("Let players create their own characters")
    open_menu(director, "Features")
    director.check(feature_checkbox(page, "Character creation"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("Allow each player one character")
    director.hold(1.0)
    director.type(page.locator("#id_user_character_max"), "1")
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.play_as(PLAYER, login_as(director, login_user, f"/{first_slug}/register/"))

    director.step("Step 3: the player registers")
    director.say("The player signs up for the event...")
    register(director)
    director.say("...then creates their character")
    create_character(director, CHARACTER, "Voice of the Silver Veil.", "You trade in secrets rather than blood.")

    director.play_as(ORGANIZER, login_as(director, login_orga, "/manage/features/"))

    director.step("Step 4: enable campaigns")
    director.say("In the organization features, turn on Campaign")
    director.check(feature_checkbox(page, "Campaign"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 5: create the next event")
    director.say("Features and configuration are imported automatically")
    open_menu(director, "Events")
    second_slug = create_event(director, SECOND_EVENT, today + dt.timedelta(days=210), parent=FIRST_EVENT)

    director.play_as(PLAYER, login_as(director, login_user, f"/{second_slug}/register/"))

    director.step("Step 6: characters carry over")
    director.say("The player registers for the next event...")
    register(director)
    director.say("...and already has the same character")
    character_card = page.locator(".event-card-char")
    expect(character_card).to_contain_text(CHARACTER)
    director.spotlight(character_card, 3.5)

    director.stop()
