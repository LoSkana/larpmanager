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

"""Guide video: create an organization, activate it and open the first event to participants."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from django.core.cache import cache
from playwright.sync_api import expect

from larpmanager.cache.larpmanager import cache_larpmanager_home_key, update_cache_lm_home
from larpmanager.models.access import AssociationRole, EventRole
from larpmanager.models.association import Association
from larpmanager.models.event import Event
from larpmanager.models.larpmanager import LarpManagerDemoType, LarpManagerText
from larpmanager.models.member import Member, Membership
from larpmanager.models.utils import get_payment_details_path
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    feature_checkbox,
    open_menu,
    open_new,
    save_modal,
)
from larpmanager.tests.utils import fill_date, get_modal_iframe, login_orga

if TYPE_CHECKING:
    from typing import Any

    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Your first event"
PACE = 0.65

ORGANIZATION = "Vaelmoor Chronicle"
EVENT = "Vaelmoor: The Sundering"
ORGANIZER_EMAIL = "orga@test.it"
WIRE_DESCRIPTION = "Bank transfer to the organization"
WIRE_PAYEE = "Vaelmoor Chronicle"
WIRE_IBAN = "XX00 DEMO 0000 0000 0000"
WIRE_BIC = "DEMOXXXX"
TICKET_PRICE = "80"
QUESTION = "Dietary restrictions"
ANSWER = "Vegetarian"
CHARACTER = "Mireille Duskwood"
FEATURE = "Waiting list"
HELP_BUTTON = "#tv22-help summary"

LANDING_TEXTS = {
    "hero_brand": "The antidote to LARP organizer burnout",
    "hero_title": "Spend time on the game,",
    "hero_title_em": "not spreadsheets.",
    "hero_description": (
        "Manage registrations, ticketing, payments, and characters all in one platform, free and ready to go."
    ),
    "join_title": "Create your organization",
    "join_sub": "Your organization gets its own space on LarpManager, where you and your team manage every event. "
        "Free, no questions asked.",
}
LANDING_STATS = {"cnt_run": 210, "cnt_character": 12000, "cnt_registration": 16000, "cnt_paymentinvoice": 25000}
DEMO_TYPES = {
    "Ticketing & Accounting": (
        "fa-solid fa-receipt",
        "Tiered ticketing, a sectioned registration form with priced options, discounts, pay-what-you-want, "
        "installments, and the full organizer money lifecycle.",
    ),
    "Story Writing": (
        "fa-solid fa-feather-pointed",
        "Characters, plots with per-character text, factions, relationships, handouts, editorial progress "
        "and PDF sheets.",
    ),
    "Casting": (
        "fa-solid fa-people-arrows",
        "Pre-written characters, factions, player preference lists and organizer-run casting assignment, "
        "resolving deliberately conflicting picks.",
    ),
}


def prepare_landing() -> None:
    """Fill the public pages with the content they show on larpmanager.com."""
    for name, value in LANDING_TEXTS.items():
        LarpManagerText.objects.update_or_create(name=name, defaults={"value": value})
    template = Association.objects.get(slug="def")
    for order, (name, (icon, description)) in enumerate(DEMO_TYPES.items()):
        slug = re.sub(r"[^a-z]", "", name.lower())
        LarpManagerDemoType.objects.create(
            name=name, slug=slug, icon=icon, descr=description, template_association=template, order=order
        )
    cache.set(cache_larpmanager_home_key(), {**update_cache_lm_home(), **LANDING_STATS}, timeout=3600)


def prepare_organizer() -> None:
    """Turn the test organizer into someone with no organization or event yet."""
    organizer = Member.objects.get(user__email=ORGANIZER_EMAIL)
    Member.objects.filter(pk=organizer.pk).update(name="Alice", surname="Stone")
    Event.objects.get(slug="test").delete()
    for role in (*EventRole.objects.filter(members=organizer), *AssociationRole.objects.filter(members=organizer)):
        role.members.remove(organizer)


def open_checklist(director: Director) -> None:
    """Open the activation checklist from the organization dashboard."""
    page = director.page
    director.click(page.locator("#topbar").get_by_role("link", name=ORGANIZATION))
    director.click(page.locator("#lite-mode a"))


def checklist_row(page: Any, name: str) -> Any:
    """Return the row of a checklist step."""
    return page.locator("tr", has_text=name)


def checklist_body(page: Any) -> Any:
    """Return the steps of the checklist."""
    return page.locator("table.go_datatable tbody", has_text="Event creation")


def test_first_video(director: Director) -> None:
    """Record the creation of an organization up to its advanced mode, and the participant view of the event."""
    page = director.page
    start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=60)
    prepare_landing()
    login_orga(page, director.base_url)
    prepare_organizer()
    director.goto("/debug")
    director.start()

    director.step("Step 1: create your organization")
    director.say("Everything starts from the Get started button on larpmanager.com")
    director.hold(1.5)
    director.say("Try a demo, or skip it to create your own organization")
    director.click(page.locator(".cta-row").get_by_role("link", name="Get started"), settle=1.0)
    director.hold(1.0)
    director.say("Pick a name: the preview shows your address on LarpManager")
    director.click(page.locator(".get-started-skip"), settle=1.0)
    director.type(page.locator("#id_name"), ORGANIZATION)
    expect(page.locator("#slug")).not_to_have_value("")
    organization_slug = page.locator("#slug").input_value()
    director.spotlight(page.locator(".slug_pre"), 1.5)
    director.say("Choose the currency used for tickets and payments")
    director.spotlight(page.locator("#id_payment_currency"), 1.5)
    director.confirm(page.locator("#id_submit"), settle=1.0)

    association = Association.objects.get(slug=organization_slug)
    Path(get_payment_details_path(association)).unlink(missing_ok=True)
    Membership.objects.filter(member__user__email=ORGANIZER_EMAIL, association=association).update(compiled=True)

    director.step("Step 2: create your first event")
    director.say("Your dashboard asks for just one thing")
    director.click(page.get_by_role("link", name="Create your first event"), settle=1.0)
    director.say("A name and dates are all you need")
    director.type(page.locator("#id_form1-name"), EVENT)
    fill_date(page, "#id_form2-start", start.isoformat())
    fill_date(page, "#id_form2-end", (start + dt.timedelta(days=2)).isoformat())
    director.hold(1.0)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.5)
    director.say("Your first event opens its registrations automatically")
    registrations = page.locator("tr", has_text="Registrations").filter(has_text="Open")
    expect(registrations).to_be_visible()
    director.spotlight(registrations, 2.5)
    director.say("The organization pill manages what all your events share")
    director.spotlight(page.locator("#topbar").get_by_role("link", name=ORGANIZATION), 3.0)
    director.say("The event pill manages this single event")
    director.spotlight(page.locator("#topbar").get_by_role("link", name=EVENT), 3.0)

    director.step("Step 3: follow the activation checklist")
    director.say("New organizations start in Lite Mode, with only the essentials")
    director.spotlight(page.locator("#lite-mode"), 2.0)
    director.say("Complete these seven steps to unlock every feature")
    director.click(page.locator("#lite-mode a"), settle=1.0)
    director.spotlight(checklist_body(page), 3.0)
    director.say("First, choose how participants will pay")
    director.click(checklist_row(page, "Payment methods").get_by_role("link", name="Go", exact=True), settle=1.0)
    director.check(page.get_by_role("checkbox", name="Wire"))
    director.type(page.locator("#id_wire_descr"), WIRE_DESCRIPTION)
    director.fill(page.locator("#id_wire_fee"), "0")
    director.fill(page.locator("#id_wire_payee"), WIRE_PAYEE)
    director.fill(page.locator("#id_wire_iban"), WIRE_IBAN)
    director.fill(page.locator("#id_wire_bic"), WIRE_BIC)
    director.hold(0.8)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 4: set your ticket price")
    director.say("Every event starts with a Standard ticket")
    director.click(page.locator("#topbar").get_by_role("link", name=EVENT))
    open_menu(director, "Tickets")
    director.click(page.locator(".fa-edit").first, settle=0.8)
    modal = get_modal_iframe(page)
    director.fill(modal.locator("#id_price"), TICKET_PRICE)
    director.hold(1.0)
    save_modal(director, modal)
    director.hold(1.0)

    director.step("Step 5: set up the registration form")
    director.say("Add the questions you need to ask participants")
    open_menu(director, "Form")
    modal = open_new(director)
    director.select(modal.locator("#id_typ"), "t")
    director.type(modal.locator("#id_name"), QUESTION)
    director.hold(0.8)
    save_modal(director, modal)
    question = page.locator("tr", has_text=QUESTION)
    expect(question).to_be_visible()
    director.spotlight(question, 2.0)

    director.step("Step 6: reach your event page")
    director.say("Back to the checklist: four steps are done")
    open_checklist(director)
    expect(checklist_row(page, "Registration form")).to_contain_text("Done")
    director.spotlight(checklist_row(page, "Registration form"), 1.5)
    director.say("Admin is where you manage, User is what participants see")
    director.spotlight(page.locator("#tv22-switch"), 3.5)
    director.click(page.locator("#topbar").get_by_role("link", name="User"), settle=1.0)
    director.say("Your organization home lists the upcoming events")
    card = page.locator(".only_v22 .run-card", has_text=EVENT)
    expect(card).to_contain_text("Registrations are open")
    director.spotlight(card, 2.0)
    director.click(card.locator(".run-card-cover-link"), settle=1.0)
    event_slug = page.url.rstrip("/").rsplit("/", 1)[-1]
    director.say(f"Share this page: {organization_slug}.larpmanager.com/{event_slug}")
    director.hold(3.0)

    director.step("Step 7: register for your event")
    director.say("Try it yourself, as the checklist asks")
    director.click(page.locator('#one a[href$="/register/"], #sidebar a[href$="/register/"]').first, settle=1.0)
    director.type(page.locator("tr", has_text=QUESTION).locator("input"), ANSWER)
    director.confirm(page.get_by_role("button", name="Continue"), settle=1.0)
    director.hold(1.0)
    director.confirm(page.locator("#register_go"), settle=1.0)
    director.say("Registrations stay provisional until the ticket is paid")
    provisional = page.get_by_text("Your registration is provisional")
    expect(provisional).to_be_visible()
    director.spotlight(provisional, 2.5)

    director.step("Step 8: add a character and assign it")
    director.say("Create a character from the event management")
    director.click(page.locator("#topbar").get_by_role("link", name="Admin"), settle=0.8)
    open_menu(director, "Characters")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), CHARACTER)
    save_modal(director, modal)
    director.say("Then assign it to a registered participant")
    open_menu(director, "Registrations")
    director.click(page.locator(".fa-edit").first, settle=0.8)
    modal = get_modal_iframe(page)
    director.type(modal.get_by_role("searchbox"), CHARACTER[:4])
    director.click(modal.get_by_role("option", name=CHARACTER))
    director.hold(0.8)
    save_modal(director, modal)
    assigned = page.locator("tr", has_text="Alice Stone").filter(has_text=CHARACTER)
    expect(assigned).to_be_visible()
    director.spotlight(assigned, 2.0)

    director.step("Step 9: unlock all features")
    director.say("With every step done, activate advanced mode")
    open_checklist(director)
    expect(checklist_row(page, "First character assignment")).to_contain_text("Done")
    director.spotlight(checklist_body(page), 2.0)
    director.confirm(page.get_by_role("button", name="Activate advanced mode"), settle=1.0)
    director.say("The sidebar now shows everything, including Features")
    director.spotlight(page.locator("#sidebar").get_by_role("link", name="Features", exact=True), 2.0)
    director.say("Over 100 features, activated only when you need them")
    director.click(page.locator("#topbar").get_by_role("link", name=EVENT))
    open_menu(director, "Features")
    director.say("For example, let's activate the Waiting list feature")
    director.check(feature_checkbox(page, FEATURE))
    director.hold(1.0)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.5)
    director.say("Waiting list is active, with its own ticket ready to use")
    waiting = page.locator("tr", has_text="Waiting")
    expect(waiting).to_be_visible()
    director.spotlight(waiting, 3.0)
    director.say("Need help? Search, ask a question or read the tutorials from here")
    director.spotlight(page.locator(HELP_BUTTON), 3.5)

    director.stop()
