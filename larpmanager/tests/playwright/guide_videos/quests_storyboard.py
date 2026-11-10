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

"""Guide video: create quest types, quests and traits, and assign traits to characters."""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import expect

from larpmanager.models.association import Association
from larpmanager.models.base import Feature
from larpmanager.models.casting import Casting, Quest, QuestType, Trait
from larpmanager.models.event import Event, EventConfig
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import Registration, RegistrationCharacterRel, TicketTier
from larpmanager.models.writing import Character
from larpmanager.tests.playwright.guide_videos.director import ORGANIZER, PLAYER
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    feature_checkbox,
    login_as,
    open_menu,
    open_new,
    prepare_data,
    save_modal,
    set_avatar,
)
from larpmanager.tests.utils import get_modal_iframe, login_orga, login_user

if TYPE_CHECKING:

    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Quests and traits"
PACE = 0.65
RICH_TEXT = True

EVENT = "Vaelmoor: The Heist"
EVENT_SLUG = "heist"
QUEST_TYPE = "Heist roles"
QUEST = "The Vault of Ashblood"
QUEST_PRESENTATION = "Tonight the crew breaks into the vault of the Ashblood Court."
MIND = "Mind"
MIND_PRESENTATION = "You plan every step of the job."
MIND_TEXT = "Keep the guards busy with "
MUSCLE = "Muscle"
FACE = "Face"
WHEELS = "Wheels"
SEEDED_TRAITS = {
    MUSCLE: "You open any door, one way or another.",
    FACE: "You talk your way past the gate.",
    WHEELS: "You wait outside with the carriage.",
}
PLAYER_CHARACTER = "Lucian Thorne"
PLAYER_NAME = "Alice Stone"
OTHER_PLAYERS = {
    "Ben": ("Hale", "Mara Voss", (MUSCLE, FACE)),
    "Clara": ("Wynn", "Dorian Reed", (FACE, MUSCLE)),
}
LATE_PLAYER = ("Dario", "Kell", "Selene Ashgrave")
LATE_PLAYER_NAME = "Dario Kell"
PLAYER_PREFERENCES = (MIND, FACE)
MUSCLE_CHARACTER = "Mara Voss"
MUSCLE_TEASER = "<p>The strongest arm of the Ashblood docks.</p>"


def add_member(event: Event, name: str, surname: str) -> Member:
    """Create an accepted member of the organization."""
    user = User.objects.create(username=name.lower(), email=f"{name.lower()}@example.com")
    member = user.member
    member.name = name
    member.surname = surname
    member.save()
    set_avatar(member)
    Membership.objects.update_or_create(
        member=member,
        association_id=event.association_id,
        defaults={"status": MembershipStatus.ACCEPTED, "compiled": True},
    )
    return member


def assign(event: Event, member: Member, character: str) -> Registration:
    """Register a member with a character already assigned."""
    run = event.runs.first()
    ticket = event.tickets.get(tier=TicketTier.STANDARD)
    registration = Registration.objects.create(run=run, member=member, ticket=ticket)
    RegistrationCharacterRel.objects.create(
        registration=registration, character=Character.objects.create(event=event, name=character)
    )
    return registration


def prepare_event() -> None:
    """Create the event with its cast, every player already holding a character."""
    association = Association.objects.get()
    event = Event.objects.create(association=association, name=EVENT, slug=EVENT_SLUG)
    run = event.runs.first()
    run.start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=30)
    run.end = run.start + dt.timedelta(days=2)
    run.save()
    event.features.add(Feature.objects.get(slug="character"))
    for name, value in (("casting_min", "2"), ("casting_max", "2")):
        EventConfig.objects.create(event=event, name=name, value=value)
    player = Member.objects.get(user__email="user@test.it")
    set_avatar(player)
    assign(event, player, PLAYER_CHARACTER)
    for name, (surname, character, _preferences) in OTHER_PLAYERS.items():
        assign(event, add_member(event, name, surname), character)
    muscle = Character.objects.get(event=event, name=MUSCLE_CHARACTER)
    muscle.teaser = MUSCLE_TEASER
    muscle.save()
    name, surname, character = LATE_PLAYER
    assign(event, add_member(event, name, surname), character)


def add_traits() -> None:
    """Write the other traits of the quest."""
    event = Event.objects.get(slug=EVENT_SLUG)
    quest = Quest.objects.get(event=event, name=QUEST)
    for name, text in SEEDED_TRAITS.items():
        Trait.objects.create(event=event, quest=quest, name=name, teaser=f"<p>{text}</p>")


def add_preferences() -> None:
    """Send the trait preferences of the other players."""
    event = Event.objects.get(slug=EVENT_SLUG)
    run = event.runs.first()
    quest_type = QuestType.objects.get(event=event, name=QUEST_TYPE)
    for name, (_surname, _character, preferences) in OTHER_PLAYERS.items():
        member = Member.objects.get(user__username=name.lower())
        for rank, trait in enumerate(preferences, start=1):
            element = str(Trait.objects.get(event=event, name=trait).uuid)
            Casting.objects.create(run=run, member=member, element=element, pref=rank, typ=quest_type.number)


def test_quests_video(director: Director) -> None:
    """Record quests and traits from the organizer and the player side."""
    page = director.page
    prepare_data("Vaelmoor Chronicle")
    prepare_event()
    login_orga(page, director.base_url)
    director.goto(f"/{EVENT_SLUG}/manage/")
    director.start()

    director.play_as(ORGANIZER)
    director.step("Step 1: enable quests and traits")
    director.say("Activate them in the event features, with the casting algorithm")
    open_menu(director, "Features")
    director.check(feature_checkbox(page, "Quests and Traits"))
    director.check(feature_checkbox(page, "Casting algorithm"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 2: create a quest type")
    director.say("A quest type groups quests: each character gets one trait per type")
    open_menu(director, "Quest type")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), QUEST_TYPE)
    save_modal(director, modal)
    expect(page.locator("#one")).to_contain_text(QUEST_TYPE)

    director.step("Step 3: write a quest")
    director.say("A quest is a story shared by a set of traits")
    open_menu(director, "Quest")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), QUEST)
    director.say("Its presentation is public, the text only for the assigned characters")
    director.click(modal.locator('a.my_toggle[tog^="f_id_teaser"]'), settle=0.8)
    director.type(modal.frame_locator('iframe[id^="id_teaser"]').locator("body"), QUEST_PRESENTATION)
    save_modal(director, modal)
    expect(page.locator("#one")).to_contain_text(QUEST)

    add_traits()
    director.step("Step 4: add its traits")
    director.say("Each trait is a role in the quest")
    open_menu(director, "Traits")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), MIND)
    director.click(modal.locator('a.my_toggle[tog^="f_id_teaser"]'), settle=0.8)
    director.fill(modal.frame_locator('iframe[id^="id_teaser"]').locator("body"), MIND_PRESENTATION)
    director.click(modal.locator('a.my_toggle[tog^="f_id_text"]'), settle=0.8)
    body = modal.frame_locator('iframe[id^="id_text"]').locator("body")
    director.type(body, MIND_TEXT)
    director.say("Type # to reference another trait")
    page.keyboard.press("#")
    director.type(modal.locator(".select2-container--open .select2-search__field"), MUSCLE[:3])
    director.click(modal.get_by_role("option", name=re.compile(MUSCLE)))
    director.say("It becomes the name of the character who gets it")
    director.hold(2.0)
    save_modal(director, modal)
    expect(page.locator("#one")).to_contain_text(MIND)

    def as_player() -> None:
        add_preferences()
        login_as(director, login_user, f"/{EVENT_SLUG}/")()

    director.play_as(PLAYER, as_player)
    director.step("Step 5: choose your preferred traits")
    director.say("Participants find the quests in the event menu")
    open_menu(director, "Quest")
    director.click(page.locator("#one").get_by_role("link", name=QUEST))
    expect(page.locator("#one")).to_contain_text(MIND_PRESENTATION)
    director.hold(1.5)
    director.say("Then they rank the traits they prefer")
    open_menu(director, "Casting")
    director.click(page.locator("#one").get_by_role("link", name=QUEST_TYPE))
    for trait in PLAYER_PREFERENCES:
        director.click(page.locator("#char-list .char-card").filter(has_text=trait))
    director.confirm(page.locator("#submit"), settle=1.0)

    director.play_as(ORGANIZER, login_as(director, login_orga, f"/{EVENT_SLUG}/manage/"))
    director.step("Step 6: assign the traits")
    director.say("Run the casting algorithm for the quest type")
    open_menu(director, "Casting")
    director.click(page.locator("#one").get_by_role("link", name=QUEST_TYPE))
    director.click(page.locator("#exec"), settle=1.5)
    assigned = page.locator("#assegnazioni")
    expect(assigned).to_contain_text(f"{MIND} - {PLAYER_NAME}")
    director.say("It gives each player a trait, following their preferences")
    director.spotlight(assigned, 3.0)
    director.confirm(page.locator("#go"), settle=1.5)

    director.say("Late sign-ups get a trait by hand, from their registration")
    open_menu(director, "Registrations")
    late_row = page.locator('table[id^="regs_"]').first.locator("tbody tr", has_text=LATE_PLAYER_NAME)
    director.click(late_row.locator(".fa-edit"), settle=1.0)
    modal = get_modal_iframe(page)
    trait_select = modal.locator('select[id^="id_qt_"]')
    options = trait_select.locator("option").all_text_contents()
    wheels = next(option for option in options if option.endswith(WHEELS))
    director.select(trait_select, wheels)
    save_modal(director, modal)
    director.say("Show the assigned traits in the list")
    director.click(page.locator("a.table_toggle", has_text=QUEST_TYPE), settle=1.0)
    participants = page.locator('table[id^="regs_"]').first
    expect(participants.locator("tbody tr", has_text=LATE_PLAYER_NAME)).to_contain_text(WHEELS)
    director.spotlight(participants, 3.0)

    director.play_as(PLAYER, login_as(director, login_user, f"/{EVENT_SLUG}/"))
    director.step("Step 7: read the trait in the character sheet")
    director.say("Open your character from the event page")
    director.click(page.locator("#one").get_by_role("link", name=PLAYER_CHARACTER).first)
    director.say("The reference now shows who holds the Muscle trait")
    reference = page.locator("#one").get_by_text(re.compile(r"Keep the guards busy with Mara Voss"))
    expect(reference).to_be_visible()
    director.spotlight(reference, 3.5)
    director.say("Hover the name to see who plays that character")
    director.hover(page.locator("#one .has_show_char a", has_text=MUSCLE_CHARACTER).first, 3.5)
    expect(page.locator(".qtip").filter(has_text=MUSCLE_CHARACTER).first).to_be_visible()
    director.say("With a link to that character")
    director.spotlight(page.locator("#one .relationships").first, 3.0)

    director.stop()
