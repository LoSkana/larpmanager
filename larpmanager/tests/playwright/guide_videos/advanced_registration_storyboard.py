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

"""Guide video: secret link, discount codes, waiting list, and keeping freed spots for the waiting list."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import expect

from larpmanager.models.association import Association
from larpmanager.models.event import Event
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.models.utils import get_payment_details_path
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
from larpmanager.tests.utils import get_modal_iframe, login, login_orga, login_user

if TYPE_CHECKING:
    from typing import Any

    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Advanced registration"
PACE = 0.55

ORGANIZATION = "Vaelmoor Chronicle"
EVENT = "Ashen Vigil"
ORGANIZER_EMAIL = "orga@test.it"
FEATURES = ("Secret link", "Discount", "Waiting list")
TICKET_PRICE = 100
DISCOUNT_NAME = "Early friends"
DISCOUNT_VALUE = "20"
DISCOUNT_USES = "10"
DISCOUNT_CODE = "VIGIL20"
DISCOUNTED_TOTAL = "80"
WAITING_DESCRIPTION = "A place in line if a spot frees up"
MAX_PARTICIPANTS = "2"
MAX_WAITING = "10"
CANCELLED = ("Carla", "Wynn")
WAITING_PLAYER = ("Bruno", "Kell")


def player_email(name: str) -> str:
    """Return the login of a demo player."""
    return f"{name.lower()}@vaelmoor.example"


def add_players() -> None:
    """Create the other players, with a compiled profile and an accepted membership."""
    association = Association.objects.get()
    for name, surname in (CANCELLED, WAITING_PLAYER):
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


def prepare_event(director: Director, start: dt.date) -> str:
    """Activate wire payments and create the event with a priced ticket, returning its slug."""
    page = director.page
    open_menu(director, "Features")
    feature_checkbox(page, "Payments").check()
    page.get_by_role("button", name=CONFIRM).click()
    open_menu(director, "Methods")
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").fill("Bank transfer to the organization")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_payee").fill(ORGANIZATION)
    page.locator("#id_wire_iban").fill("XX00 DEMO 0000 0000 0000")
    page.locator("#id_wire_bic").fill("DEMOXXXX")
    page.get_by_role("button", name=CONFIRM).click()
    open_menu(director, "Events")
    slug = create_event(director, EVENT, start)
    ticket = Event.objects.get(slug=slug).tickets.get(tier=TicketTier.STANDARD)
    ticket.price = TICKET_PRICE
    ticket.save()
    director.goto(f"/{slug}/manage/")
    return slug


def secret_path(slug: str) -> str:
    """Return the secret registration link of the event."""
    return f"/{slug}/register/{Event.objects.get(slug=slug).runs.first().registration_secret}/"


def fill_the_event(director: Director, slug: str) -> None:
    """Register the second participant, so the event is full, and log in as the next player."""
    event = Event.objects.get(slug=slug)
    member = Member.objects.get(user__email=player_email(CANCELLED[0]))
    Registration.objects.create(
        run=event.runs.first(), member=member, ticket=event.tickets.get(tier=TicketTier.STANDARD)
    )

    def login_waiting(page: Any, base_url: str) -> None:
        login(page, base_url, player_email(WAITING_PLAYER[0]))

    login_as(director, login_waiting, f"/{slug}/")()


def test_advanced_registration_video(director: Director) -> None:
    """Record a secret link with a discount code, then a waiting list kept for those already in line."""
    page = director.page
    start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=30)
    prepare_data(ORGANIZATION)
    Member.objects.filter(user__email=ORGANIZER_EMAIL).update(name="Mira", surname="Hale")
    Membership.objects.filter(member__user__email=ORGANIZER_EMAIL).update(compiled=True)
    Path(get_payment_details_path(Association.objects.get())).unlink(missing_ok=True)
    add_players()
    login_orga(page, director.base_url)
    director.goto("/manage")
    slug = prepare_event(director, start)
    director.start()

    director.play_as(ORGANIZER)
    director.step("Step 1: turn on the advanced options")
    director.say("Each option is a feature of the event")
    open_menu(director, "Features")
    for name in FEATURES:
        director.check(feature_checkbox(page, name))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    activated = page.locator("tr", has_text="Waiting list")
    expect(activated).to_be_visible()
    director.spotlight(page.locator("table").filter(has=activated), 2.0)

    director.step("Step 2: open a private signup")
    director.say("Keep registrations closed to the public")
    open_menu(director, "Event")
    director.click(page.locator("#id_form2-registration_status_tr .sl-show"), settle=0.8)
    director.click(page.locator('label[for="id_form2-registration_status_0"]'))
    director.say("The secret code is ready, or write your own")
    director.spotlight(page.locator("#id_form2-registration_secret_tr"), 2.5)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("Copy the link from the dashboard and share it")
    secret_link = page.locator(".grid-item p").filter(has=page.locator(".copy-link-btn"))
    expect(secret_link).to_contain_text("Secret registration link")
    director.spotlight(secret_link, 3.0)

    director.step("Step 3: create a discount code")
    director.say("A fixed amount off, for a limited number of uses")
    open_menu(director, "Discounts")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), DISCOUNT_NAME)
    director.fill(modal.locator("#id_value"), DISCOUNT_VALUE)
    director.fill(modal.locator("#id_max_redeem"), DISCOUNT_USES)
    director.say("Players type this code in the form")
    director.type(modal.locator("#id_cod"), DISCOUNT_CODE)
    director.select(modal.locator("#id_typ"), "a")
    director.check(modal.locator("#id_visible"))
    director.hold(0.8)
    save_modal(director, modal)
    discount = page.locator("tr", has_text=DISCOUNT_CODE)
    expect(discount).to_be_visible()
    director.spotlight(discount, 2.0)

    director.play_as(PLAYER, login_as(director, login_user, secret_path(slug)))
    director.step("Step 4: sign up with the link")
    director.say("Registrations are closed, but the link opens the form")
    director.spotlight(page.locator("#id_ticket_tr"), 2.5)
    director.say("Enter the code under Discounts")
    director.click(page.locator("#register_form").get_by_role("link", name=re.compile(r"^Discounts")))
    director.type(page.locator("#id_discount"), DISCOUNT_CODE)
    director.confirm(page.locator("#discount_go"), settle=1.0)
    expect(page.locator("#discount_tbl")).to_contain_text(DISCOUNT_NAME)
    director.spotlight(page.locator("#discount_tbl"), 2.0)
    director.confirm(page.get_by_role("button", name="Continue"), settle=1.0)
    director.say("The total already takes the discount off")
    summary = page.locator("#riepilogo")
    expect(summary).to_contain_text(DISCOUNTED_TOTAL)
    director.hold(2.0)
    director.confirm(page.locator("#register_go"), settle=1.5)

    director.play_as(ORGANIZER, login_as(director, login_orga, f"/{slug}/manage/"))
    director.step("Step 5: set up the waiting list")
    director.say("The waiting list comes with its own ticket")
    open_menu(director, "Tickets")
    waiting = page.locator("tbody tr").filter(has_text="Waiting")
    director.click(waiting.locator(".fa-edit"), settle=0.8)
    modal = get_modal_iframe(page)
    director.type(modal.locator("#id_description"), WAITING_DESCRIPTION)
    save_modal(director, modal)
    expect(page.locator("tbody tr", has_text=WAITING_DESCRIPTION)).to_be_visible()
    director.say("It shows up once the event is full")
    open_menu(director, "Event")
    director.type(page.locator('input[name$="max_pg"]'), MAX_PARTICIPANTS)
    director.type(page.locator('input[name$="max_waiting"]'), MAX_WAITING)
    director.say("Now open registrations to everyone")
    director.click(page.locator("#id_form2-registration_status_tr .sl-show"), settle=0.8)
    director.click(page.locator('label[for="id_form2-registration_status_1"]'))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.play_as(PLAYER, lambda: fill_the_event(director, slug))
    director.step("Step 6: join the waiting list")
    director.say("Both spots are taken: the event is sold out")
    sold_out = page.get_by_role("link", name=re.compile("join the waiting list"))
    expect(sold_out).to_be_visible()
    director.spotlight(sold_out, 2.5)
    director.click(sold_out, settle=1.0)
    director.say("Only the waiting list ticket is offered")
    expect(page.locator("#id_ticket_tr")).to_contain_text(WAITING_DESCRIPTION)
    director.spotlight(page.locator("#id_ticket_tr"), 2.5)
    director.confirm(page.get_by_role("button", name="Continue"), settle=1.0)
    director.confirm(page.locator("#register_go"), settle=1.5)

    director.play_as(ORGANIZER, login_as(director, login_orga, f"/{slug}/manage/"))
    director.step("Step 7: keep freed spots for the waiting list")
    director.say("If someone cancels, anyone could grab the free spot")
    director.hold(1.5)
    director.say("Set Maximum participants to 1 to stop that")
    open_menu(director, "Event")
    director.type(page.locator('input[name$="max_pg"]'), "1")
    director.hold(1.0)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("Now a participant cancels")
    open_menu(director, "Registrations")
    cancelled = page.locator("tr[id]", has_text=" ".join(CANCELLED))
    director.click(cancelled.locator("a:has(i.fa-trash)"), settle=0.8)
    save_modal(director, get_modal_iframe(page))
    expect(cancelled).to_have_count(0)
    director.hold(1.0)
    director.say("New players still see only the waiting list")
    director.click(page.locator("#topbar").get_by_role("link", name="User"), settle=1.0)
    still_full = page.get_by_role("link", name=re.compile("join the waiting list"))
    expect(still_full).to_be_visible()
    director.spotlight(still_full, 2.5)

    director.step("Step 8: move up from the waiting list")
    director.say("You choose who takes the spot")
    director.click(page.locator("#topbar").get_by_role("link", name="Admin"), settle=0.8)
    open_menu(director, "Registrations")
    waiting_player = page.locator("tr[id]", has_text=" ".join(WAITING_PLAYER))
    director.click(waiting_player.locator(".fa-edit"), settle=0.8)
    modal = get_modal_iframe(page)
    director.say("Switch the ticket to Standard")
    director.click(modal.locator("#id_ticket_tr label").filter(has_text="Standard"))
    director.hold(0.8)
    save_modal(director, modal)
    upgraded = page.locator("tr[id]", has_text=" ".join(WAITING_PLAYER)).filter(has_text="Standard")
    expect(upgraded).to_be_visible()
    director.say("Bruno is now a participant")
    director.spotlight(upgraded, 2.5)

    director.stop()
