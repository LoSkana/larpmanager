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

"""Guide video: link characters with references, then publish sheet fields to players step by step."""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import expect

from larpmanager.models.base import Feature
from larpmanager.models.event import Event
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import Registration, RegistrationCharacterRel, TicketTier
from larpmanager.models.writing import Character, Relationship
from larpmanager.tests.playwright.guide_videos.director import ORGANIZER, PLAYER
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    create_event,
    login_as,
    open_menu,
    prepare_data,
    save_modal,
    set_avatar,
)
from larpmanager.tests.utils import get_modal_iframe, login_orga, login_user

if TYPE_CHECKING:
    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Publishing characters"
PACE = 0.75
RICH_TEXT = True

EVENT = "Vaelmoor: The Sundering"
HERO = "Lucian Thorne"
RIVAL = "Aurelio Vance"
CHARACTERS = {
    HERO: "The oldest vampire lord of the Ashblood Court.",
    RIVAL: "A young noble hungry for power.",
    "Selene Ashgrave": "The court seer, who speaks only in riddles.",
}
HERO_TEXT = "Three centuries on the Ashblood throne. Your rival for it is "
RIVAL_NUMBER = "#2"
RELATIONSHIP = "He wants your throne: never turn your back on him."
OTHER_PLAYERS = {RIVAL: ("Ben", "Hale"), "Selene Ashgrave": ("Clara", "Wynn")}


def register(event: Event, member: Member, character: str) -> None:
    """Register a member with a character already assigned."""
    registration = Registration.objects.create(
        run=event.runs.first(),
        member=member,
        ticket=event.tickets.get(tier=TicketTier.STANDARD),
    )
    assigned = Character.objects.get(event=event, name=character)
    RegistrationCharacterRel.objects.create(registration=registration, character=assigned)


def add_player(event: Event, name: str, surname: str) -> Member:
    """Create a player, with a profile photo shown in the gallery and in character previews."""
    user = User.objects.create(username=name.lower(), email=f"{name.lower()}@example.com")
    member = user.member
    member.name = name
    member.surname = surname
    set_avatar(member)
    Membership.objects.update_or_create(
        member=member,
        association_id=event.association_id,
        defaults={"status": MembershipStatus.ACCEPTED, "compiled": True},
    )
    return member


def add_characters(slug: str) -> None:
    """Create the characters with their players and a relationship, and enable relationships."""
    event = Event.objects.get(slug=slug)
    event.features.add(Feature.objects.get(slug="relationships"))
    event.save()
    for name, teaser in CHARACTERS.items():
        Character.objects.create(event=event, name=name, teaser=f"<p>{teaser}</p>")
    player = Member.objects.get(user__email="user@test.it")
    set_avatar(player)
    register(event, player, HERO)
    for character, (name, surname) in OTHER_PLAYERS.items():
        register(event, add_player(event, name, surname), character)
    Relationship.objects.create(
        source=Character.objects.get(event=event, name=HERO),
        target=Character.objects.get(event=event, name=RIVAL),
        text=f"<p>{RELATIONSHIP}</p>",
    )


def show_fields(director: Director, labels: tuple[str, ...], note: str | None = None) -> None:
    """Tick the given fields in the Visibility section of the event page, and save."""
    page = director.page
    open_menu(director, "Event")
    for label in labels:
        director.click(page.locator("label[for^='id_form2-show_']", has_text=re.compile(rf"^\s*{label}\s*$")))
    if note:
        director.say(note)
        director.spotlight(page.locator("#id_form2-show_character_tr"), 3.0)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)


def test_publishing_video(director: Director) -> None:
    """Record character references and field visibility, from the organizer and the player side."""
    page = director.page
    start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=30)
    prepare_data("Vaelmoor Chronicle")
    login_orga(page, director.base_url)
    director.goto("/manage/events")
    director.start()
    with director.off_camera():
        slug = create_event(director, EVENT, start)
        add_characters(slug)
        director.goto(f"/{slug}/manage/")

    director.play_as(ORGANIZER)
    director.step("Step 1: reference other characters")
    director.say("Write the sheet of each character")
    open_menu(director, "Characters")
    director.click(page.locator("tr", has_text=HERO).locator(".fa-edit"), settle=0.8)
    modal = get_modal_iframe(page)
    director.click(modal.locator('a.my_toggle[tog^="f_id_text"]'), settle=0.8)
    director.say("Type # and pick a character: its number is inserted")
    director.type(modal.frame_locator('iframe[id^="id_text"]').locator("body"), HERO_TEXT + "#")
    director.type(modal.locator(".select2-search__field").last, RIVAL[:4])
    director.click(modal.locator(".select2-results__option", has_text=RIVAL))
    editor = modal.frame_locator('iframe[id^="id_text"]').locator("body")
    expect(editor).to_contain_text(RIVAL_NUMBER)
    director.say("Use @ for a one-way link, and ^ for a simple mention")
    director.spotlight(editor, 3.0)
    save_modal(director, modal)

    director.step("Step 2: references become links")
    director.say("On the sheet, the number becomes a link to the character")
    director.click(page.locator("tr", has_text=HERO).locator(".fa-book-open"), settle=1.0)
    sheet = page.locator(".sheet")
    link = sheet.get_by_role("link", name=RIVAL).first
    expect(link).to_be_visible()
    director.spotlight(link, 1.5)
    director.say("Hover it to preview the character and their player")
    director.hover(link, 3.5)
    director.say("The relationships of the character are on the sheet too")
    relationships = page.locator(".relationships").first
    expect(relationships).to_contain_text(RELATIONSHIP)
    director.spotlight(relationships, 3.5)

    director.step("Step 3: enable field visibility")
    director.say("By default, players see every field of their sheet")
    open_menu(director, "Configuration")
    director.click(page.locator("#main_form").get_by_role("link", name=re.compile(r"^Characters")))
    director.say("With field visibility, you choose what to show and when")
    toggle = page.locator("#id_writing_field_visibility")
    director.check(toggle)
    director.spotlight(page.locator("tr", has=toggle), 2.0)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/"))
    director.step("Step 4: players see nothing yet")
    director.say("While you are still writing, the sheet stays empty")
    director.click(page.locator("#sidebar").get_by_role("link", name=HERO))
    expect(page.locator("#one")).not_to_contain_text(CHARACTERS[HERO])
    director.spotlight(page.locator("#one"), 3.0)

    director.play_as(ORGANIZER, login_as(director, login_orga, f"/{slug}/manage/"))
    director.step("Step 5: reveal name and presentation")
    director.say("Pick the fields to show in the event settings")
    show_fields(
        director,
        ("Name", "Presentation"),
        "Public fields go to everyone, private ones only to their player",
    )

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/"))
    director.say("Players can now browse the characters in the gallery")
    open_menu(director, "Gallery")
    gallery = page.locator("#one")
    expect(gallery).to_contain_text(RIVAL)
    director.spotlight(gallery, 2.5)
    director.say("Their own sheet shows the presentation, the text is still hidden")
    director.click(page.locator("#sidebar").get_by_role("link", name=HERO))
    expect(page.locator("#one")).to_contain_text(CHARACTERS[HERO])
    expect(page.locator("#one")).not_to_contain_text(HERO_TEXT.strip())
    director.hold(2.5)

    director.play_as(ORGANIZER, login_as(director, login_orga, f"/{slug}/manage/"))
    director.step("Step 6: reveal the full sheet")
    director.say("Right before the event, show the text and relationships")
    show_fields(director, ("Text", "Relationships"))

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/"))
    director.say("Now the player reads the full sheet, with links and relationships")
    director.click(page.locator("#sidebar").get_by_role("link", name=HERO))
    content = page.locator("#one")
    expect(content).to_contain_text(HERO_TEXT.strip())
    rival_link = content.locator(".has_show_char a", has_text=RIVAL).first
    expect(rival_link).to_be_visible()
    director.hover(rival_link, 3.0)
    director.spotlight(content, 4.0)

    director.stop()
