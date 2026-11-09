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

"""Guide video: staff expenses, outflows and inflows, the final balance of an event, and a refund of credits."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.models import User
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import expect

from larpmanager.models.access import EventPermission, EventRole
from larpmanager.models.accounting import (
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemInflow,
    AccountingItemMembership,
    AccountingItemOther,
    AccountingItemOutflow,
    AccountingItemPayment,
    AccountingItemTransaction,
    PaymentChoices,
)
from larpmanager.models.association import Association
from larpmanager.models.event import Event
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import Registration
from larpmanager.tests.playwright.guide_videos.director import ORGANIZER, STAFF
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    feature_checkbox,
    login_as,
    open_menu,
    open_new,
    save_modal,
)
from larpmanager.tests.utils import get_modal_iframe, login_orga, login_user

if TYPE_CHECKING:
    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Event accounting"
PACE = 0.55

ORGANIZATION = "Vaelmoor Chronicle"
EVENT = "Vaelmoor: The Sundering"
STAFF_NAME = "Elena Marsh"
TICKET_PRICE = Decimal(120)
PLAYERS = (("Alice", "Stone"), ("Bruno", "Hale"), ("Clara", "Voss"), ("Dario", "Fenn"), ("Edith", "Crane"))
EXPENSE_VALUE = "85"
EXPENSE_DESCRIPTION = "Foam swords for the duel"
SECOND_EXPENSE_VALUE = "45"
SECOND_EXPENSE_DESCRIPTION = "Lanterns for the night camp"
CREDITS = "130"
REFUND_DETAILS = "Bank transfer to IBAN XX00 DEMO 1111 2222 3333"
OUTFLOW_VALUE = "400"
OUTFLOW_DESCRIPTION = "Campsite rent"
INFLOW_VALUE = "150"
INFLOW_DESCRIPTION = "Sponsorship from a local game shop"
REVENUE = "750"
COSTS = "530"
PROFIT = "220"

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
DOCUMENTS_DIR = Path(".guide_videos/accounting_documents")

ACCOUNTING_MODELS = (
    AccountingItemPayment,
    AccountingItemTransaction,
    AccountingItemOther,
    AccountingItemExpense,
    AccountingItemInflow,
    AccountingItemOutflow,
    AccountingItemMembership,
    AccountingItemDonation,
)


def prepare_data() -> None:
    """Rename test labels and clear any accounting, so every total on screen is known."""
    association = Association.objects.get()
    association.name = ORGANIZATION
    association.save()
    for model in ACCOUNTING_MODELS:
        model.objects.filter(association=association).delete()
    Membership.objects.filter(association=association).update(tokens=0, credit=0)
    Member.objects.filter(user__email="orga@test.it").update(name="Mira", surname="Hale")
    Member.objects.filter(user__email="user@test.it").update(name="Elena", surname="Marsh")
    Membership.objects.filter(member__user__email="user@test.it").update(compiled=True)

    event = Event.objects.get(slug="test")
    event.name = EVENT
    event.save()
    run = event.runs.get()
    Registration.objects.filter(run=run).delete()
    run.save()

    role = EventRole.objects.create(event=event, number=2, name="Props crew")
    role.permissions.add(EventPermission.objects.get(slug="orga_expenses_my"))
    role.members.add(Member.objects.get(user__email="user@test.it"))


def prepare_registrations() -> None:
    """Add paid registrations, so the event already has its revenue from tickets."""
    association = Association.objects.get()
    run = Event.objects.get(slug="test").runs.get()
    ticket = run.event.tickets.order_by("number").first()
    ticket.price = TICKET_PRICE
    ticket.save()
    for name, surname in PLAYERS:
        username = f"{name.lower()}.{surname.lower()}@vaelmoor.example"
        user = User.objects.create_user(username=username, email=username, password="banana")  # noqa: S106
        member = user.member
        member.name = name
        member.surname = surname
        member.save()
        Membership.objects.update_or_create(
            member=member, association=association, defaults={"status": MembershipStatus.JOINED, "compiled": True}
        )
        registration = Registration.objects.create(run=run, member=member, ticket=ticket)
        AccountingItemPayment.objects.create(
            member=member,
            association=association,
            registration=registration,
            pay=PaymentChoices.MONEY,
            value=TICKET_PRICE,
        )


def demo_document(name: str, heading: str, lines: tuple[str, ...], total: str) -> Path:
    """Draw a fictional receipt or invoice."""
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    title = ImageFont.truetype(str(FONT_DIR / "DejaVuSans-Bold.ttf"), 44)
    text = ImageFont.truetype(str(FONT_DIR / "DejaVuSansMono.ttf"), 30)
    bold = ImageFont.truetype(str(FONT_DIR / "DejaVuSansMono-Bold.ttf"), 34)
    image = Image.new("RGB", (800, 1000), (252, 251, 246))
    draw = ImageDraw.Draw(image)
    draw.text((400, 90), heading, font=title, fill=(30, 30, 30), anchor="mm")
    draw.line((60, 160, 740, 160), fill=(120, 120, 120), width=2)
    for index, line in enumerate(lines):
        draw.text((70, 200 + index * 50), line, font=text, fill=(40, 40, 40))
    draw.line((60, 820, 740, 820), fill=(120, 120, 120), width=2)
    draw.text((70, 850), f"TOTAL  {total}.00", font=bold, fill=(20, 20, 20))
    path = DOCUMENTS_DIR / name
    image.save(path)
    return path


def test_accounting_video(director: Director) -> None:
    """Record expenses, outflows and inflows of an event, and read its final balance."""
    page = director.page
    sidebar = page.locator("#sidebar")
    prepare_data()
    receipt = demo_document("receipt.png", "Ironwood Props", ("Foam sword x 5", "Leather grip x 5"), EXPENSE_VALUE)
    invoice = demo_document("invoice.png", "Pinecrest Camping", ("Campsite, 3 nights", "Group area"), OUTFLOW_VALUE)
    contract = demo_document(
        "sponsorship.png", "Dice and Dragons", ("Event sponsorship", "Banner at the entrance"), INFLOW_VALUE
    )
    second_receipt = demo_document(
        "receipt_2.png", "Old Town Hardware", ("Oil lantern x 3", "Lamp oil 1 l"), SECOND_EXPENSE_VALUE
    )
    login_orga(page, director.base_url)
    director.goto("/manage/features/payment/on")
    prepare_registrations()
    director.goto("/manage/")
    director.start()

    director.play_as(ORGANIZER)
    director.step("Step 1: enable the accounting tools")
    director.say("Each kind of money movement is a feature to activate")
    open_menu(director, "Features")
    director.check(feature_checkbox(page, "Expenses"))
    director.check(feature_checkbox(page, "Inflows"))
    director.check(feature_checkbox(page, "Outflows"))
    director.check(feature_checkbox(page, "Refunds"))
    director.hold(1.0)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.play_as(STAFF, login_as(director, login_user, "/test/manage/"))
    director.step("Step 2: staff upload their receipts")
    director.say("Staff upload what they paid out of pocket")
    director.click(sidebar.get_by_role("link", name=re.compile(r"^Upload expenses", re.IGNORECASE)))
    modal = open_new(director)
    director.type(modal.locator("#id_value"), EXPENSE_VALUE)
    director.upload(modal.locator("#id_invoice"), receipt)
    director.select(modal.locator("#id_exp"), "c")
    director.type(modal.locator("#id_descr"), EXPENSE_DESCRIPTION)
    director.hold(1.0)
    save_modal(director, modal)
    expect(page.locator("tr", has_text=EXPENSE_DESCRIPTION)).to_be_visible()
    director.say("Add one request for each receipt")
    modal = open_new(director)
    director.fill(modal.locator("#id_value"), SECOND_EXPENSE_VALUE)
    director.upload(modal.locator("#id_invoice"), second_receipt)
    director.select(modal.locator("#id_exp"), "a")
    director.fill(modal.locator("#id_descr"), SECOND_EXPENSE_DESCRIPTION)
    director.hold(0.6)
    save_modal(director, modal)
    expense_rows = page.locator("tbody tr").filter(has_text=re.compile("Foam swords|Lanterns"))
    expect(expense_rows).to_have_count(2)
    director.spotlight(page.locator("tbody:visible").first, 2.0)

    director.play_as(ORGANIZER, login_as(director, login_orga, "/test/manage/"))
    director.step("Step 3: approve the expenses")
    director.say("Review each receipt before approving it")
    director.click(sidebar.get_by_role("link", name=re.compile(r"^Expenses")))
    for description in (EXPENSE_DESCRIPTION, SECOND_EXPENSE_DESCRIPTION):
        expense_row = page.locator("tr", has_text=description)
        director.click(expense_row.get_by_role("link", name="Approve"), settle=0.8)
        save_modal(director, get_modal_iframe(page))
        expect(page.locator("tr", has_text=description).get_by_role("link", name="Approve")).to_have_count(0)
        director.say("The amounts become credits owed to the staff member")
    director.spotlight(page.locator("tbody:visible").first, 2.5)

    director.play_as(STAFF, login_as(director, login_user, "/"))
    director.step("Step 4: staff request a refund of their credits")
    director.say("Staff find their credits in their accounting")
    open_menu(director, "Accounting")
    credits = page.locator("p", has_text="Would you like to request a reimbursement?")
    expect(page.locator("#one")).to_contain_text(CREDITS)
    director.spotlight(credits, 2.0)
    director.say("They can ask for the money back instead of using them")
    director.click(page.get_by_role("link", name="Submit a new refund request"), settle=1.0)
    director.type(page.locator("#id_details"), REFUND_DETAILS)
    expect(page.locator("#id_value")).to_have_value(re.compile(f"^{CREDITS}"))
    director.spotlight(page.locator("#id_value"), 1.5)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("The organization reviews the request and sends the transfer")
    request = page.locator("p.refund-requests")
    expect(request).to_contain_text(REFUND_DETAILS)
    director.spotlight(request, 3.0)

    director.play_as(ORGANIZER, login_as(director, login_orga, "/test/manage/"))
    director.step("Step 5: record the outflows")
    director.say("Outflows are paid from the organization accounts")
    open_menu(director, "Outflows")
    modal = open_new(director)
    director.type(modal.locator("#id_value"), OUTFLOW_VALUE)
    director.type(modal.locator("#id_descr"), OUTFLOW_DESCRIPTION)
    director.upload(modal.locator("#id_invoice"), invoice)
    director.select(modal.locator("#id_exp"), "h")
    director.hold(1.0)
    save_modal(director, modal)
    outflow_row = page.locator("tr", has_text=OUTFLOW_DESCRIPTION)
    expect(outflow_row).to_be_visible()
    director.spotlight(outflow_row, 2.0)

    director.step("Step 6: record the inflows")
    director.say("Inflows cover income beyond registration fees")
    open_menu(director, "Inflows")
    modal = open_new(director)
    director.type(modal.locator("#id_value"), INFLOW_VALUE)
    director.type(modal.locator("#id_descr"), INFLOW_DESCRIPTION)
    director.upload(modal.locator("#id_invoice"), contract)
    director.hold(1.0)
    save_modal(director, modal)
    inflow_row = page.locator("tr", has_text=INFLOW_DESCRIPTION)
    expect(inflow_row).to_be_visible()
    director.spotlight(inflow_row, 2.0)

    director.step("Step 7: read the event balance")
    director.say("Everything adds up in the event accounting")
    open_menu(director, "Accounting")
    revenue = page.locator("h2", has_text="Realized revenue")
    costs = page.locator("h2", has_text="Total costs")
    profit = page.locator("h2", has_text="Net profit")
    expect(revenue).to_contain_text(REVENUE)
    expect(costs).to_contain_text(COSTS)
    expect(profit).to_contain_text(PROFIT)
    director.say("Revenue: registration fees plus inflows")
    director.spotlight(revenue, 2.5)
    director.say("Costs: approved expenses plus outflows")
    director.spotlight(costs, 2.5)
    director.say("The difference is the net profit of the event")
    director.spotlight(profit, 2.5)

    director.step("Step 8: close the event")
    director.say("Once the event is over, mark it as concluded")
    director.click(page.locator("#topbar").get_by_role("link", name=EVENT, exact=True), settle=0.8)
    director.click(page.locator('a[href$="/quick-development/"]'), settle=0.8)
    modal = get_modal_iframe(page)
    director.click(modal.locator('label[for="id_development_3"]'))
    save_modal(director, modal)
    director.say("Its profit joins the global balance of the organization")
    director.click(page.locator("#topbar").get_by_role("link", name=ORGANIZATION), settle=0.8)
    open_menu(director, "Accounting")
    global_balance = page.locator("h2", has_text="Global balance")
    expect(global_balance).to_contain_text(PROFIT)
    director.spotlight(global_balance, 3.5)

    director.stop()
