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

"""Guide video: set tickets and capacity, build the registration form, and sign up as a player and as staff."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from larpmanager.models.association import Association
from larpmanager.models.member import Member, Membership
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
from larpmanager.tests.utils import get_modal_iframe, login_orga, login_user, new_option, submit_option

if TYPE_CHECKING:
    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Tickets and registration form"
PACE = 0.55

EVENT = "Vaelmoor: The Sundering"
ORGANIZER_EMAIL = "orga@test.it"
WIRE_DESCRIPTION = "Bank transfer to the organization"
TICKET = "Standard"
TICKET_DESCRIPTION = "Full weekend, meals included"
TICKET_PRICE = "100"
TICKET_AVAILABLE = "20"
STAFF_TICKET = "Staff"
STAFF_DESCRIPTION = "For the crew running the event"
MAX_PARTICIPANTS = "20"
TEXT_QUESTION = "Dietary restrictions"
TEXT_ANSWER = "Vegetarian"
CHOICE_QUESTION = "Accommodation"
FREE_OPTION = "Tent"
PAID_OPTION = "Private room"
OPTION_PRICE = "40"
OPTION_AVAILABLE = "4"
TOTAL = "140"


def prepare_event(director: Director, start: dt.date) -> str:
    """Activate payments and create the event off camera, returning its slug."""
    page = director.page
    open_menu(director, "Features")
    feature_checkbox(page, "Payments").check()
    page.get_by_role("button", name=CONFIRM).click()
    open_menu(director, "Methods")
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").fill(WIRE_DESCRIPTION)
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_payee").fill("Vaelmoor Chronicle")
    page.locator("#id_wire_iban").fill("XX00 DEMO 0000 0000 0000")
    page.locator("#id_wire_bic").fill("DEMOXXXX")
    page.get_by_role("button", name=CONFIRM).click()
    open_menu(director, "Events")
    slug = create_event(director, EVENT, start)
    director.goto(f"/{slug}/manage/")
    return slug


def test_tickets_video(director: Director) -> None:
    """Record tickets, event capacity and form setup, then both the public and the hidden ticket signup."""
    page = director.page
    start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=30)
    prepare_data("Vaelmoor Chronicle")
    Member.objects.filter(user__email=ORGANIZER_EMAIL).update(name="Mira", surname="Hale")
    Membership.objects.filter(member__user__email=ORGANIZER_EMAIL).update(compiled=True)
    Path(get_payment_details_path(Association.objects.get())).unlink(missing_ok=True)
    login_orga(page, director.base_url)
    director.goto("/manage")
    director.start()

    slugs = []
    director.play_as(ORGANIZER, lambda: slugs.append(prepare_event(director, start)))
    slug = slugs[0]

    director.step("Step 1: set price and availability")
    director.say("Every event starts with a Standard ticket")
    open_menu(director, "Tickets")
    director.click(page.locator(".fa-edit").first, settle=0.8)
    modal = get_modal_iframe(page)
    director.say("Set what it includes, its price and how many are for sale")
    director.fill(modal.locator("#id_description"), TICKET_DESCRIPTION)
    director.fill(modal.locator("#id_price"), TICKET_PRICE)
    director.type(modal.locator("#id_max_available"), TICKET_AVAILABLE)
    director.hold(0.5)
    save_modal(director, modal)
    ticket = page.locator("tr", has_text=TICKET_DESCRIPTION)
    expect(ticket).to_be_visible()
    director.spotlight(ticket, 2.0)

    director.step("Step 2: unlock the staff tier")
    director.say("Tiers beyond Standard come from the event configuration")
    open_menu(director, "Configuration")
    director.click(page.locator("#main_form").get_by_role("link", name="Tickets", exact=True))
    director.check(page.locator("#id_ticket_staff"))
    director.spotlight(page.locator("tr", has_text="allow ticket tier: Staff"), 3.5)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 3: add a hidden staff ticket")
    director.say("Pick the new tier and keep it free")
    open_menu(director, "Tickets")
    modal = open_new(director)
    director.select(modal.locator("#id_tier"), "t")
    director.type(modal.locator("#id_name"), STAFF_TICKET)
    director.fill(modal.locator("#id_description"), STAFF_DESCRIPTION)
    director.say("Not visible: players never see it in the form")
    director.click(modal.locator("#id_visible"))
    director.hold(1.0)
    save_modal(director, modal)
    staff = page.locator("tr", has_text=STAFF_DESCRIPTION)
    expect(staff).to_be_visible()
    director.say("Your crew signs up from its direct link instead")
    director.spotlight(staff.get_by_role("link", name="Signup link"), 3.0)

    director.step("Step 4: cap the whole event")
    director.say("Maximum participants limits the event, staff tickets excluded")
    open_menu(director, "Event")
    participants = page.locator('input[name$="max_pg"]')
    director.type(participants, MAX_PARTICIPANTS)
    director.spotlight(participants, 5.5)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 5: add custom questions")
    director.say("Ask what you need to know, and make it mandatory")
    open_menu(director, "Form")
    modal = open_new(director)
    director.select(modal.locator("#id_typ"), "t")
    director.type(modal.locator("#id_name"), TEXT_QUESTION)
    director.select(modal.locator("#id_status"), "m")
    director.hold(0.4)
    save_modal(director, modal)
    expect(page.locator("tr", has_text=TEXT_QUESTION)).to_be_visible()
    director.say("Choice options can add a price and have a limit")
    modal = open_new(director)
    director.select(modal.locator("#id_typ"), "s")
    director.type(modal.locator("#id_name"), CHOICE_QUESTION)
    option = new_option(modal)
    director.type(option.locator("#id_name"), FREE_OPTION)
    submit_option(modal, option)
    option = new_option(modal)
    director.type(option.locator("#id_name"), PAID_OPTION)
    director.fill(option.locator("#id_price"), OPTION_PRICE)
    director.fill(option.locator("#id_max_available"), OPTION_AVAILABLE)
    submit_option(modal, option)
    director.hold(1.0)
    save_modal(director, modal)
    director.say("Drag a question to change its position")
    rows = page.locator("table.row_reorder tbody tr")
    choice = rows.filter(has_text=CHOICE_QUESTION)
    expect(choice).to_be_visible()
    first_question = rows.filter(has_text=TEXT_QUESTION)
    director.drag(choice.locator("td.reorder-handle"), first_question)
    expect(rows.nth(1)).to_contain_text(CHOICE_QUESTION)
    director.spotlight(rows.nth(1), 1.5)

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/"))
    director.step("Step 6: see the form as a player")
    director.say("Players register from the event page")
    director.click(page.locator('#one a[href$="/register/"], #sidebar a[href$="/register/"]').first, settle=1.0)
    director.say("Only the visible ticket is offered, with the spots left")
    form = page.locator("#register_form")
    expect(form).to_contain_text(TICKET)
    expect(form).not_to_contain_text(STAFF_DESCRIPTION)
    director.spotlight(page.locator("label", has_text=TICKET_DESCRIPTION), 2.5)
    director.say("Options show their price, and the questions you added")
    director.click(page.locator("label", has_text=PAID_OPTION))
    director.type(page.locator("tr", has_text=TEXT_QUESTION).locator("input"), TEXT_ANSWER)
    director.hold(0.8)
    director.confirm(page.get_by_role("button", name="Continue"), settle=1.0)
    director.say("The summary adds up ticket and options")
    expect(page.locator("#riepilogo")).to_contain_text(TOTAL)
    director.hold(2.5)
    director.confirm(page.locator("#register_go"), settle=1.0)

    director.play_as(ORGANIZER, login_as(director, login_orga, f"/{slug}/manage/tickets/"))
    director.step("Step 7: use the direct link")
    director.say("The link opens the form with the hidden ticket")
    signup = page.locator("tr", has_text=STAFF_DESCRIPTION).get_by_role("link", name="Signup link")
    signup.evaluate("(element) => element.removeAttribute('target')")
    director.click(signup, settle=1.0)
    staff_card = page.locator("label", has_text=STAFF_DESCRIPTION)
    expect(staff_card).to_be_visible()
    director.spotlight(staff_card, 2.5)
    director.fill(page.locator("tr", has_text=TEXT_QUESTION).locator("input"), "None")
    director.say("It is free, so the signup is confirmed at once")
    director.confirm(page.get_by_role("button", name="Continue"), settle=1.0)
    director.hold(0.5)
    director.confirm(page.locator("#register_go"), settle=1.0)
    expect(page.get_by_text("has been confirmed")).to_be_visible()
    director.hold(1.0)
    director.say("Both signups land in Registrations, each with its ticket")
    director.click(page.locator("#topbar").get_by_role("link", name="Admin"), settle=0.8)
    open_menu(director, "Registrations")
    registered = page.locator("tr[id]", has_text="Mira Hale").filter(has_text=STAFF_TICKET)
    expect(registered).to_be_visible()
    player = page.locator("tr[id]", has_text="Alice Stone").filter(has_text=TICKET)
    expect(player).to_be_visible()
    director.spotlight(player, 1.5)
    director.spotlight(registered, 2.0)

    director.stop()
