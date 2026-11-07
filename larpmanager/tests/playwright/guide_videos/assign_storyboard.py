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

"""Guide video: collect preferences, run the casting algorithm and assign characters."""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import expect

from larpmanager.models.casting import Casting
from larpmanager.models.event import Event
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.models.writing import Character
from larpmanager.tests.playwright.guide_videos.director import ORGANIZER, PLAYER
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    create_event,
    feature_checkbox,
    login_as,
    open_menu,
    prepare_data,
    register,
)
from larpmanager.tests.utils import login_orga, login_user

if TYPE_CHECKING:
    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Casting"
PACE = 0.7

EVENT = "Vaelmoor: The Sundering"
FIRST_CHOICE = "Lucian Thorne"
SECOND_CHOICE = "Mara Voss"
THIRD_CHOICE = "Dorian Reed"
CHARACTERS = (FIRST_CHOICE, "Aurelio Vance", "Selene Ashgrave", SECOND_CHOICE, THIRD_CHOICE)
OTHER_PLAYERS = {
    "Ben": ("Hale", ("Aurelio Vance", "Selene Ashgrave", SECOND_CHOICE)),
    "Clara": ("Wynn", ("Selene Ashgrave", "Aurelio Vance", THIRD_CHOICE)),
    "Dario": ("Kell", (THIRD_CHOICE, SECOND_CHOICE, "Aurelio Vance")),
}
PLAYER_NAME = "Alice Stone"


def add_characters(slug: str) -> None:
    """Create the characters players will choose from."""
    event = Event.objects.get(slug=slug)
    for name in CHARACTERS:
        Character.objects.create(event=event, name=name)


def add_other_players(slug: str) -> None:
    """Register other players, with their preferences already sent."""
    event = Event.objects.get(slug=slug)
    run = event.runs.first()
    ticket = event.tickets.get(tier=TicketTier.STANDARD)
    for name, (surname, preferences) in OTHER_PLAYERS.items():
        user = User.objects.create(username=name.lower(), email=f"{name.lower()}@example.com")
        member = user.member
        member.name = name
        member.surname = surname
        member.save()
        Membership.objects.update_or_create(
            member=member,
            association_id=event.association_id,
            defaults={"status": MembershipStatus.ACCEPTED, "compiled": True},
        )
        Registration.objects.create(run=run, member=member, ticket=ticket)
        for rank, character in enumerate(preferences, start=1):
            element = str(Character.objects.get(event=event, name=character).uuid)
            Casting.objects.create(run=run, member=member, element=element, pref=rank, typ=0)


def choice(slug: str, character: str) -> str:
    """Return the selector of the lock toggle of a character, in the row of the player."""
    member = Member.objects.get(user__email="user@test.it")
    element = Character.objects.get(event__slug=slug, name=character).uuid
    return f'#main_grid a.change[pid="{member.uuid}"][oid="{element}"]'


def test_assign_video(director: Director) -> None:
    """Record casting from the organizer and the player side."""
    page = director.page
    start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=30)
    prepare_data("Vaelmoor Chronicle")
    login_orga(page, director.base_url)
    director.goto("/manage/events")
    director.start()

    director.play_as(ORGANIZER)
    director.step("Step 1: create the event")
    director.say("Create the event, then enable the casting algorithm")
    slug = create_event(director, EVENT, start)
    open_menu(director, "Features")
    director.check(feature_checkbox(page, "Casting algorithm"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    add_characters(slug)
    director.say("Prepare the characters players will choose from")
    open_menu(director, "Characters")
    characters = page.locator('table.writing_list[id^="writing_list"]')
    expect(characters).to_contain_text(CHARACTERS[-1])
    director.spotlight(characters, 2.5)

    director.step("Step 2: configure the event")
    director.say("Choose how many preferences each player can send")
    open_menu(director, "Configuration")
    director.click(page.locator("#main_form").get_by_role("link", name=re.compile(r"^Casting")))
    director.type(page.locator("#id_casting_min"), "2")
    director.type(page.locator("#id_casting_max"), "3")
    director.hold(1.0)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/register/"))
    director.step("Step 3: test the player view")
    director.say("Sign up for the event...")
    register(director)
    director.say("...then choose characters, in order of preference")
    open_menu(director, "Casting")
    for character in (FIRST_CHOICE, SECOND_CHOICE, THIRD_CHOICE):
        director.click(page.locator("#char-list .char-card").filter(has_text=character))
    expect(page.locator("#pref-list")).to_contain_text(THIRD_CHOICE)
    director.hold(1.5)
    director.confirm(page.locator("#submit"), settle=1.0)
    expect(page.locator("#pref-list")).to_contain_text(FIRST_CHOICE)
    director.hold(1.5)

    def back_to_organizer() -> None:
        add_other_players(slug)
        login_as(director, login_orga, f"/{slug}/manage/")()

    director.play_as(ORGANIZER, back_to_organizer)
    director.step("Step 4: run the casting algorithm")
    director.say("Review the preferences of every player")
    open_menu(director, "Casting")
    grid = page.locator("#main_grid")
    expect(grid).to_contain_text(PLAYER_NAME)
    director.spotlight(grid, 3.0)
    director.say("Then start the algorithm")
    director.click(page.locator("#exec"), settle=1.5)
    assigned = page.locator("#assegnazioni")
    expect(assigned).to_contain_text(f"{FIRST_CHOICE} - {PLAYER_NAME}")
    director.say("It finds the distribution that satisfies everyone most")
    director.spotlight(assigned, 3.0)

    director.step("Step 5: refine and re-run")
    director.say("Block any assignment that is not possible")
    blocked = page.locator(choice(slug, FIRST_CHOICE))
    director.click(blocked, settle=1.0)
    expect(blocked).to_have_text("NO")
    director.spotlight(blocked.locator("xpath=ancestor::td"), 2.5)
    director.say("Run it again, as many times as needed")
    director.click(page.locator("#exec"), settle=1.5)
    expect(assigned).to_contain_text(f"{SECOND_CHOICE} - {PLAYER_NAME}")
    director.spotlight(assigned, 3.0)

    director.step("Step 6: finalize assignments")
    director.say("When satisfied, upload the result")
    director.confirm(page.locator("#go"), settle=1.5)

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/"))
    director.say("Characters are now officially assigned")
    director.spotlight(page.locator("#one").get_by_role("link", name=SECOND_CHOICE), 3.5)

    director.stop()
