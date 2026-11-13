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

"""Guide video: signup requests approved by the organizer, then matchmaker and debrief questions."""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import expect

from larpmanager.models.association import Association
from larpmanager.models.event import Event
from larpmanager.models.form import (
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
)
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.models.writing import Faction
from larpmanager.tests.playwright.guide_videos.director import ORGANIZER, PLAYER
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    create_event,
    feature_checkbox,
    login_as,
    open_menu,
    open_new,
    prepare_data,
    save_modal,
)
from larpmanager.tests.utils import get_modal_iframe, login_orga, login_user, new_option, submit_option

if TYPE_CHECKING:
    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Signup approval, matchmaker and debrief"
PACE = 0.55

ORGANIZATION = "Vaelmoor Chronicle"
EVENT = "Ember Court"
ORGANIZER_EMAIL = "orga@test.it"
PLAYER_NAME = "Alice Stone"

MOTIVATION = "Why do you want to join"
MOTIVATION_ANSWER = "I love political intrigue and slow burning plots"
EXPERIENCE = "Larp experience"
EXPERIENCE_OPTIONS = ("First larp", "A few events", "Veteran")
EXPERIENCE_ANSWER = "A few events"

FACTION = "Faction preference"
FACTIONS = ("Crown", "Guilds", "Exiles")
FACTION_ANSWER = "Exiles"
ROLE = "Role you would like to play"
ROLE_ANSWER = "A disgraced envoy looking for redemption"

BEST_MOMENT = "Your best moment"
BEST_MOMENT_ANSWER = "The midnight council, when the exiles finally spoke"

OTHER_PLAYERS = (
    {
        "name": ("Bruno", "Kell"),
        "motivation": "My friends are playing, and I want to try",
        "experience": "First larp",
        "faction": ("Crown", "Exiles", "Guilds"),
        "role": "A loyal guard",
        "moment": "Defending the gate at dawn",
    },
    {
        "name": ("Carla", "Wynn"),
        "motivation": "Ten years of larp, I am looking for a court game",
        "experience": "Veteran",
        "faction": ("Guilds", "Crown", "Exiles"),
        "role": "A merchant with debts",
        "moment": "Closing the grain deal",
    },
)


def player_email(name: str) -> str:
    """Return the login of a demo player."""
    return f"{name.lower()}@vaelmoor.example"


def add_players() -> None:
    """Create the other players, with a compiled profile and an accepted membership."""
    association = Association.objects.get()
    for player in OTHER_PLAYERS:
        name, surname = player["name"]
        user = User.objects.create(username=player_email(name), email=player_email(name))
        user.set_password("banana")
        user.save()
        member = user.member
        member.name = name
        member.surname = surname
        member.save()
        Membership.objects.update_or_create(
            member=member,
            association=association,
            defaults={"status": MembershipStatus.ACCEPTED, "compiled": True},
        )


def answer(registration: Registration, event: Event, question_name: str, value: str) -> None:
    """Store the answer of a demo player, as text or as the option with that name."""
    question = RegistrationQuestion.objects.get(event=event, name=question_name)
    option = RegistrationOption.objects.filter(question=question, name=value).first()
    if option:
        RegistrationChoice.objects.create(question=question, option=option, registration=registration)
    else:
        RegistrationAnswer.objects.create(question=question, text=value, registration=registration)


def faction_ranking(event: Event, names: tuple[str, ...]) -> str:
    """Return a faction preference answer, as the ranked faction uuids."""
    return ",".join(str(Faction.objects.get(event=event, name=name).uuid) for name in names)


def other_registrations(event: Event) -> list[Registration]:
    """Return the registrations of the other demo players."""
    return [
        Registration.objects.get(run__event=event, member__user__email=player_email(player["name"][0]))
        for player in OTHER_PLAYERS
    ]


def add_requests(slug: str) -> None:
    """Send the signup requests of the other players, with their answers."""
    event = Event.objects.get(slug=slug)
    run = event.runs.first()
    for player in OTHER_PLAYERS:
        member = Member.objects.get(user__email=player_email(player["name"][0]))
        registration = Registration.objects.create(run=run, member=member, pending=True)
        answer(registration, event, MOTIVATION, player["motivation"])
        answer(registration, event, EXPERIENCE, player["experience"])


def accept_others(slug: str) -> None:
    """Approve the other players, register them and store their matchmaker and debrief answers."""
    event = Event.objects.get(slug=slug)
    ticket = event.tickets.get(tier=TicketTier.STANDARD)
    for registration, player in zip(other_registrations(event), OTHER_PLAYERS, strict=True):
        registration.pending = False
        registration.ticket = ticket
        registration.save()
        answer(registration, event, FACTION, faction_ranking(event, player["faction"]))
        answer(registration, event, ROLE, player["role"])
        answer(registration, event, BEST_MOMENT, player["moment"])


def prepare_event(director: Director, start: dt.date) -> str:
    """Create the event, returning its slug."""
    open_menu(director, "Events")
    slug = create_event(director, EVENT, start)
    event = Event.objects.get(slug=slug)
    for number, name in enumerate(FACTIONS, start=1):
        Faction.objects.create(event=event, number=number, name=name)
    director.goto(f"/{slug}/manage/")
    return slug


def open_form_tab(director: Director, name: str) -> None:
    """Switch the Form page to another of its forms."""
    director.click(director.page.locator("#page-wrapper").get_by_role("link", name=name, exact=True), settle=0.8)


def add_choice_question(director: Director, name: str, options: tuple[str, ...], *, typ: str = "s") -> None:
    """Create a choice question with its options."""
    modal = open_new(director)
    director.select(modal.locator("#id_typ"), typ)
    director.type(modal.locator("#id_name"), name)
    for option_name in options:
        option = new_option(modal)
        director.fill(option.locator("#id_name"), option_name)
        submit_option(modal, option)
    director.hold(0.6)
    save_modal(director, modal)
    expect(director.page.locator("tr", has_text=name)).to_be_visible()


def add_text_question(director: Director, name: str, typ: str, *, fast: bool = False) -> None:
    """Create a short text or paragraph question, typed or filled at once."""
    modal = open_new(director)
    director.select(modal.locator("#id_typ"), typ)
    write = director.fill if fast else director.type
    write(modal.locator("#id_name"), name)
    director.hold(0.4)
    save_modal(director, modal)
    expect(director.page.locator("tr", has_text=name)).to_be_visible()


def pick(director: Director, value: str) -> None:
    """Click a choice option of a player form through its label."""
    director.click(director.page.locator("label", has_text=value).first)


def test_approval_video(director: Director) -> None:
    """Record signup requests and their approval, then the matchmaker and debrief forms."""
    page = director.page
    start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=30)
    prepare_data(ORGANIZATION)
    Member.objects.filter(user__email=ORGANIZER_EMAIL).update(name="Mira", surname="Hale")
    Membership.objects.filter(member__user__email=ORGANIZER_EMAIL).update(compiled=True)
    add_players()
    login_orga(page, director.base_url)
    director.goto("/manage")
    director.start()

    slugs = []
    director.play_as(ORGANIZER, lambda: slugs.append(prepare_event(director, start)))
    slug = slugs[0]

    director.step("Step 1: require approval to sign up")
    director.say("Turn it on in the registration settings")
    open_menu(director, "Configuration")
    director.click(page.locator("#main_form").get_by_role("link", name=re.compile(r"^Registrations")))
    approval = page.locator("#id_registration_approval_process")
    director.check(approval)
    director.spotlight(page.locator("tr", has=approval), 3.0)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 2: ask questions with the request")
    director.say("The Form page now has a request form")
    open_menu(director, "Form")
    open_form_tab(director, "Request")
    director.say("Ask what you need to choose your players")
    add_text_question(director, MOTIVATION, "p")
    add_choice_question(director, EXPERIENCE, EXPERIENCE_OPTIONS)
    director.hold(1.0)

    director.step("Step 3: add matchmaker and debrief questions")
    director.say("Both are features of the event")
    open_menu(director, "Features")
    for name in ("Matchmaker", "Debrief"):
        director.check(feature_checkbox(page, name))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("Matchmaker asks what players would like to play")
    open_menu(director, "Form")
    open_form_tab(director, "Matchmaker")
    director.say("A ranking of your factions is already there")
    faction_row = page.locator("tr", has_text=FACTION)
    expect(faction_row).to_be_visible()
    director.spotlight(faction_row, 2.5)
    director.say("Add your own questions next to it")
    add_text_question(director, ROLE, "t", fast=True)
    director.say("Debrief collects feedback after the event")
    open_form_tab(director, "Debrief")
    add_text_question(director, BEST_MOMENT, "p", fast=True)
    director.hold(1.0)

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/"))
    director.step("Step 4: send a signup request")
    director.say("Players register as usual")
    director.click(page.locator('#one a[href$="/register/"], #sidebar a[href$="/register/"]').first, settle=1.0)
    director.say("Instead of the form, they send a request")
    director.type(page.get_by_role("textbox", name=MOTIVATION), MOTIVATION_ANSWER)
    pick(director, EXPERIENCE_ANSWER)
    director.check(page.locator("#id_confirm"))
    director.hold(0.6)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.5)
    director.say("The request waits for the organizers")
    pending = page.get_by_text("awaiting organizer approval")
    expect(pending).to_be_visible()
    director.spotlight(pending, 2.5)

    director.play_as(
        ORGANIZER,
        lambda: (add_requests(slug), login_as(director, login_orga, f"/{slug}/manage/")()),
    )
    director.step("Step 5: approve the request")
    director.say("The dashboard counts the requests waiting")
    waiting = page.locator("td", has_text="signup requests to approve")
    expect(waiting).to_contain_text(str(len(OTHER_PLAYERS) + 1))
    director.spotlight(waiting, 2.0)
    director.say("Requests lists everyone waiting, with their answers")
    director.click(page.locator("#sidebar").get_by_role("link", name=re.compile(r"^Requests")), settle=1.0)
    table = page.locator("#registration_requests")
    row = table.locator("tbody tr", has_text=PLAYER_NAME)
    expect(row).to_contain_text(MOTIVATION_ANSWER)
    director.spotlight(table, 3.0)
    director.say("Approve the players you want, reject the others")
    director.click(row.get_by_role("link", name="Approve"), settle=0.8)
    save_modal(director, get_modal_iframe(page))
    expect(table.locator("tbody tr", has_text=PLAYER_NAME)).to_have_count(0)
    director.hold(1.5)

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/"))
    director.step("Step 6: complete the registration")
    director.say("Approved: the player can now choose a ticket")
    director.click(page.locator('#one a[href$="/register/"], #sidebar a[href$="/register/"]').first, settle=1.0)
    director.confirm(page.get_by_role("button", name="Continue"), settle=1.0)
    summary = page.locator("#register_go")
    if summary.is_visible():
        director.confirm(summary, settle=1.5)
    expect(page.get_by_text("awaiting organizer approval")).to_have_count(0)
    director.hold(1.0)

    director.step("Step 7: answer the matchmaker")
    director.say("Matchmaker is now in the event menu")
    open_menu(director, "Matchmaker")
    director.say("Move the favourite faction to the top")
    exiles = page.locator(".ranking-item", has_text=FACTION_ANSWER)
    for _unused in range(2):
        director.click(exiles.locator(".ranking-up"), settle=0.4)
    expect(page.locator(".ranking-item").first).to_contain_text(FACTION_ANSWER)
    director.type(page.get_by_role("textbox", name=ROLE), ROLE_ANSWER)
    director.hold(0.6)
    director.confirm(page.locator("#matchmaker_go"), settle=1.0)
    expect(page.locator(".jq-toast-single")).to_contain_text("Answers saved")

    director.step("Step 8: fill the debrief")
    director.say("After the event, players share their feedback")
    open_menu(director, "Debrief")
    director.fill(page.get_by_role("textbox", name=BEST_MOMENT), BEST_MOMENT_ANSWER)
    director.hold(0.6)
    director.confirm(page.locator("#debrief_go"), settle=1.0)
    expect(page.locator(".jq-toast-single")).to_contain_text("Answers saved")

    director.play_as(
        ORGANIZER,
        lambda: (accept_others(slug), login_as(director, login_orga, f"/{slug}/manage/")()),
    )
    director.step("Step 9: review the answers")
    director.say("Matchmaker answers helps you assign characters")
    open_menu(director, "Matchmaker answers")
    matchmaker = page.locator("#matchmaker_answers")
    expect(matchmaker.locator("tbody tr")).to_have_count(len(OTHER_PLAYERS) + 1)
    expect(matchmaker.locator("tr", has_text=PLAYER_NAME)).to_contain_text(ROLE_ANSWER)
    director.spotlight(matchmaker, 3.5)
    director.say("Debrief answers shows how the event went")
    open_menu(director, "Debrief answers")
    debrief = page.locator("#debrief_answers")
    expect(debrief).to_contain_text(BEST_MOMENT_ANSWER)
    director.spotlight(debrief, 3.5)

    director.stop()
