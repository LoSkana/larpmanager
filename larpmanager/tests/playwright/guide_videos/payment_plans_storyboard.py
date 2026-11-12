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

"""Guide video: fixed instalments, a late surcharge, the deadlines dashboard and the payment reminders."""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from playwright.sync_api import expect

from larpmanager.mail.remind import remember_pay
from larpmanager.models.association import Association
from larpmanager.models.event import Event
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.miscellanea import EmailContent, EmailRecipient
from larpmanager.models.registration import Registration
from larpmanager.tests.playwright.guide_videos.director import ORGANIZER, PLAYER
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    feature_checkbox,
    login_as,
    open_menu,
    open_new,
    save_modal,
)
from larpmanager.tests.utils import fill_date, login_orga, login_user

if TYPE_CHECKING:
    from typing import Any

    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Payment plans and deadlines"
PACE = 0.65

ORGANIZATION = "Vaelmoor Chronicle"
EVENT = "Vaelmoor: The Sundering"
EVENT_DESCRIPTION = "<p>Three days in the drowned city of Vaelmoor, as the old pact breaks apart.</p>"
TICKET = "Standard"
TICKET_PRICE = Decimal(120)
FIRST_INSTALMENT = "40"
FIRST_DAYS = "7"
SURCHARGE = "20"
TOTAL = "140"
# Demo players already registered, with the days since their registration
LATE_PLAYERS = (("Ben", "Hale", 12), ("Clara", "Voss", 15), ("Dario", "Fenn", 45))
TOLERANCE = "30"
SUMMARY_DAYS = "7"
REMIND_DAYS = "5"


def prepare_data() -> Event:
    """Rename test labels, price the ticket and move the event three months ahead."""
    association = Association.objects.get()
    association.name = ORGANIZATION
    association.save()
    EmailRecipient.objects.all().delete()
    EmailContent.objects.all().delete()
    Member.objects.filter(user__email="orga@test.it").update(name="Mira", surname="Hale")
    Member.objects.filter(user__email="user@test.it").update(name="Alice", surname="Stone")
    Membership.objects.filter(member__user__email__in=["orga@test.it", "user@test.it"]).update(compiled=True)

    event = Event.objects.get(slug="test")
    event.name = EVENT
    event.description = EVENT_DESCRIPTION
    event.save()
    run = event.runs.get()
    Registration.objects.filter(run=run).delete()
    run.start = timezone.localdate() + dt.timedelta(days=90)
    run.end = run.start + dt.timedelta(days=2)
    run.save()
    ticket = event.tickets.order_by("number").first()
    ticket.price = TICKET_PRICE
    ticket.save()
    return event


def prepare_late_players(event: Event) -> None:
    """Add players who registered weeks ago and have not paid yet."""
    association = Association.objects.get()
    run = event.runs.get()
    ticket = event.tickets.order_by("number").first()
    for name, surname, days_ago in LATE_PLAYERS:
        email = f"{name.lower()}.{surname.lower()}@vaelmoor.example"
        user = User.objects.create_user(username=email, email=email, password="banana")  # noqa: S106
        member = user.member
        member.name = name
        member.surname = surname
        member.save()
        Membership.objects.update_or_create(
            member=member, association=association, defaults={"status": MembershipStatus.JOINED, "compiled": True}
        )
        registration = Registration.objects.create(run=run, member=member, ticket=ticket)
        created = timezone.now() - dt.timedelta(days=days_ago)
        Registration.objects.filter(pk=registration.pk).update(created=created)


def refresh_registrations(event: Event) -> None:
    """Recompute the payment deadlines of every registration with the current instalments."""
    for registration in Registration.objects.filter(run__event=event):
        registration.save()


def pick_ticket(director: Director, modal: Any) -> None:
    """Select the ticket an instalment applies to."""
    director.type(modal.locator(".select2-search__field").first, TICKET[:4])
    director.click(modal.locator(".select2-results__option", has_text=TICKET))


def test_payment_plans_video(director: Director) -> None:
    """Record instalments, a surcharge, a registration, the deadlines dashboard and the reminders."""
    page = director.page
    event = prepare_data()
    final_deadline = event.runs.get().start - dt.timedelta(days=30)
    login_orga(page, director.base_url)
    director.goto("/manage/features/payment/on/")
    prepare_late_players(event)
    director.goto("/test/manage/")
    director.start()

    director.play_as(ORGANIZER)
    director.step("Step 1: turn on fixed instalments")
    director.say("Split the ticket into instalments with their own deadlines")
    open_menu(director, "Features")
    director.say("Dynamic rates are the alternative: players choose how many rates")
    director.spotlight(page.locator(".feature_checkbox").filter(has=page.get_by_text("Dynamic rates", exact=True)), 2.5)
    director.say("Here we use fixed instalments, the same for everyone")
    director.check(feature_checkbox(page, "Fixed instalments"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 2: split the fee into instalments")
    director.say(f"First instalment: {FIRST_INSTALMENT} within {FIRST_DAYS} days of signing up")
    modal = open_new(director)
    director.type(modal.locator("#id_amount"), FIRST_INSTALMENT)
    director.type(modal.locator("#id_days_deadline"), FIRST_DAYS)
    director.say("Choose the tickets it applies to")
    pick_ticket(director, modal)
    director.hold(1.0)
    save_modal(director, modal)
    expect(page.locator("tbody:visible").first.locator("tr")).to_have_count(1)
    director.say("Amount 0 asks for the rest, here a month before the event")
    modal = open_new(director)
    director.fill(modal.locator("#id_amount"), "0")
    fill_date(modal, "#id_date_deadline", final_deadline.isoformat())
    pick_ticket(director, modal)
    director.hold(1.5)
    save_modal(director, modal)
    instalments = page.locator("tbody:visible").first
    expect(instalments.locator("tr")).to_have_count(2)
    director.spotlight(instalments, 2.5)

    director.step("Step 3: charge late registrations more")
    director.say("A surcharge rewards the early birds")
    open_menu(director, "Features")
    director.check(feature_checkbox(page, "Surcharge"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say(f"From this date on, every new registration pays {SURCHARGE} more")
    modal = open_new(director)
    director.type(modal.locator("#id_amount"), SURCHARGE)
    fill_date(modal, "#id_date", (timezone.localdate() - dt.timedelta(days=1)).isoformat())
    director.hold(1.5)
    save_modal(director, modal)
    surcharges = page.locator("tbody:visible").first
    expect(surcharges).to_contain_text(SURCHARGE)
    director.spotlight(surcharges, 2.0)

    director.play_as(PLAYER, login_as(director, login_user, "/test/register/"))
    director.step("Step 4: the player signs up")
    director.say("The surcharge is added to the ticket price")
    director.confirm(page.get_by_role("button", name="Continue"), settle=1.0)
    expect(page.locator("#riepilogo")).to_contain_text(TOTAL)
    director.hold(2.5)
    director.confirm(page.locator("#register_go"), settle=1.5)
    director.say("Only the first instalment is due now, with its deadline")
    banner = page.get_by_text(re.compile(f"A payment of {FIRST_INSTALMENT}.* is due within {FIRST_DAYS} days"))
    expect(banner).to_be_visible()
    director.spotlight(banner, 2.5)
    next_payment = page.locator("a:visible", has_text=re.compile(f"Next payment: {FIRST_INSTALMENT}"))
    director.spotlight(next_payment, 2.0)

    director.play_as(ORGANIZER, login_as(director, login_orga, "/manage/"))
    refresh_registrations(event)
    director.step("Step 5: track deadlines and send reminders")
    director.say("Two features of the organization watch the deadlines for you")
    open_menu(director, "Features")
    director.check(feature_checkbox(page, "Deadlines"))
    director.check(feature_checkbox(page, "Reminder"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    open_menu(director, "Configuration")
    director.click(page.locator("#main_form").get_by_role("link", name=re.compile(r"^Deadline")))
    director.say("Days of delay before a registration is marked for cancellation")
    director.type(page.locator("#id_deadline_tolerance"), TOLERANCE)
    director.say("How often organizers get a summary of the missed deadlines")
    director.type(page.locator("#id_deadline_days"), SUMMARY_DAYS)
    director.click(page.locator("#main_form").get_by_role("link", name=re.compile(r"^Reminder")))
    director.say("How often players get a reminder of what they still owe")
    director.type(page.locator("#id_remind_days"), REMIND_DAYS)
    director.hold(1.0)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 6: review the deadlines dashboard")
    director.say("Who is late, on every upcoming event")
    open_menu(director, "Deadlines")
    late = page.locator("tr", has_text="Delay in payment")
    expect(late).to_contain_text("Ben Hale")
    expect(late).to_contain_text("Clara Voss")
    director.spotlight(late, 3.0)
    director.say("Past the tolerance, you decide whether to cancel")
    overdue = page.locator("tr", has_text="Cancellation for missing payment")
    expect(overdue).to_contain_text("Dario Fenn")
    director.spotlight(overdue, 4.0)

    director.step("Step 7: players are reminded automatically")
    with director.off_camera():
        late = Registration.objects.filter(run__event=event, alert=True, deadline__lt=0).select_related("member")
        for registration in late:
            remember_pay(registration)
    director.say("Every few days, each player late on a payment gets an email")
    open_menu(director, "Archive")
    rows = page.locator("tbody:visible").first.locator("tr")
    reminders = rows.filter(has_text=re.compile(r"(registration|payment) for"))
    expect(reminders).to_have_count(len(LATE_PLAYERS))
    director.spotlight(reminders.first, 2.5)
    director.say("It tells them how much to pay, with a link to do it")
    director.spotlight(reminders.last, 3.5)

    director.stop()
