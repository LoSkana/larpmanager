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

"""Guide video: a player applies for membership, the organizer approves, the member pays the fee."""

from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import expect

from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member
from larpmanager.models.registration import RegistrationTicket
from larpmanager.models.utils import get_payment_details_path
from larpmanager.tests.playwright.guide_videos.director import ORGANIZER, PLAYER
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    feature_checkbox,
    login_as,
    open_menu,
    open_new,
    save_modal,
)
from larpmanager.tests.utils import get_modal_iframe, go_to, login_orga, login_user, submit_confirm

if TYPE_CHECKING:
    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Membership"
PACE = 0.65
RICH_TEXT = True

ORGANIZATION = "Vaelmoor Chronicle"
EVENT = "Vaelmoor: The Sundering"
EVENT_DESCRIPTION = "<p>Three days in the fallen city of Vaelmoor.</p>"
PLAYER_NAME = "Alice"
PLAYER_SURNAME = "Stone"
TICKET_PRICE = 100
FEE = "20"
TOTAL = "120"
TEMPLATE = "I, {{ member.name }} {{ member.surname }}, ask to join the association."
REQUEST_TEXT = (f"I, {PLAYER_NAME} {PLAYER_SURNAME}, ask to join the association.",)
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
DOCUMENTS_DIR = Path(".guide_videos/membership_documents")


def prepare_data() -> None:
    """Rename test labels, move the event to the current year and price its ticket."""
    Association.objects.update(name=ORGANIZATION)
    event = Event.objects.get(slug="test")
    event.name = EVENT
    event.description = EVENT_DESCRIPTION
    event.save()
    start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=14)
    for run in Run.objects.filter(event=event):
        run.start = start
        run.end = start + dt.timedelta(days=2)
        run.save()
    for ticket in RegistrationTicket.objects.filter(event=event):
        ticket.price = TICKET_PRICE
        ticket.save()
    Member.objects.filter(user__email="user@test.it").update(name=PLAYER_NAME, surname=PLAYER_SURNAME)


def setup_payments(director: Director) -> None:
    """Activate payments with a wire transfer method, shown in the Payments guide."""
    page = director.page
    go_to(page, director.base_url, "/manage/features/payment/on")
    go_to(page, director.base_url, "/manage/methods")
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").fill("Bank transfer to the organization")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_payee").fill(ORGANIZATION)
    page.locator("#id_wire_iban").fill("XX00 DEMO 0000 0000 0000")
    page.locator("#id_wire_bic").fill("DEMOXXXX")
    submit_confirm(page)


def _signature(draw: ImageDraw.ImageDraw, left: int, top: int) -> None:
    """Draw a hand-written looking signature, as a row of loops."""
    points = []
    for step in range(220):
        angle = step / 12
        size = 18 + 8 * math.sin(step / 30)
        points.append((left + step * 1.1 + size * math.cos(angle), top + size * math.sin(angle) - step * 0.08))
    draw.line(points, fill=(30, 50, 140), width=3, joint="curve")


def demo_documents() -> tuple[Path, Path]:
    """Create a signed request scan and an identity card, both fictional."""
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    serif = ImageFont.truetype(str(FONT_DIR / "DejaVuSerif.ttf"), 30)
    title = ImageFont.truetype(str(FONT_DIR / "DejaVuSerif-Bold.ttf"), 42)
    sans = ImageFont.truetype(str(FONT_DIR / "DejaVuSans.ttf"), 32)
    bold = ImageFont.truetype(str(FONT_DIR / "DejaVuSans-Bold.ttf"), 40)

    request = Image.new("RGB", (1200, 800), (250, 248, 240))
    draw = ImageDraw.Draw(request)
    draw.text((600, 90), "Membership request", font=title, fill=(20, 20, 20), anchor="mm")
    draw.text((600, 140), ORGANIZATION, font=serif, fill=(90, 90, 90), anchor="mm")
    for index, line in enumerate(REQUEST_TEXT):
        draw.text((90, 260 + index * 50), line, font=serif, fill=(20, 20, 20))
    today = dt.datetime.now(tz=dt.UTC).date().strftime("%d/%m/%Y")
    draw.text((90, 560), f"Date: {today}", font=serif, fill=(20, 20, 20))
    draw.text((700, 560), "Signature", font=serif, fill=(20, 20, 20))
    _signature(draw, 700, 650)
    request_path = DOCUMENTS_DIR / "membership_request.png"
    request.save(request_path)

    card = Image.new("RGB", (1200, 760), (214, 228, 236))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((20, 20, 1180, 740), radius=40, outline=(60, 90, 120), width=6)
    draw.text((600, 90), "IDENTITY CARD - DEMO", font=bold, fill=(40, 70, 100), anchor="mm")
    draw.rounded_rectangle((70, 170, 400, 600), radius=20, fill=(160, 180, 195))
    draw.ellipse((170, 230, 300, 360), fill=(110, 130, 150))
    draw.pieslice((120, 380, 350, 640), 180, 360, fill=(110, 130, 150))
    for index, (label, value) in enumerate(
        (("Surname", PLAYER_SURNAME), ("Name", PLAYER_NAME), ("Born", "01/01/1990"), ("Number", "DEMO 000000"))
    ):
        draw.text((460, 190 + index * 105), label, font=sans, fill=(70, 90, 110))
        draw.text((460, 228 + index * 105), value, font=bold, fill=(20, 20, 20))
    _signature(draw, 470, 660)
    card_path = DOCUMENTS_DIR / "identity_card.png"
    card.save(card_path)
    return request_path, card_path


def test_membership_video(director: Director) -> None:
    """Record a membership request, its approval and the payment of the fee."""
    page = director.page
    prepare_data()
    request_path, card_path = demo_documents()
    Path(get_payment_details_path(Association.objects.get())).unlink(missing_ok=True)
    login_orga(page, director.base_url)
    setup_payments(director)
    director.goto("/manage")
    director.start()

    director.play_as(ORGANIZER)
    director.step("Step 1: enable membership")
    director.say("Activate Membership in the organization features")
    open_menu(director, "Features")
    director.check(feature_checkbox(page, "Membership"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("Set the annual fee, added to the first payment of the year")
    director.type(page.locator("#id_membership_fee"), FEE)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 2: write the membership request")
    director.say("The dashboard reminds you to write the request text")
    director.spotlight(page.locator("#priorities").locator("..").get_by_text("Set up the membership request text"), 2.0)
    open_menu(director, "Texts")
    director.say("It is filled in with the data of each member")
    modal = open_new(director)
    director.select(modal.locator("#id_typ"), "m")
    director.type(modal.frame_locator('iframe[id^="id_text"]').locator("body"), TEMPLATE)
    director.hold(0.8)
    save_modal(director, modal)
    row = page.locator("tr", has_text="Membership request")
    expect(row).to_be_visible()
    director.spotlight(row, 1.5)

    director.play_as(PLAYER, login_as(director, login_user, "/test/register/"))
    director.step("Step 3: register for the event")
    director.say("The annual fee is added to the registration total")
    director.confirm(page.get_by_role("button", name="Continue"), settle=1.0)
    summary = page.locator("#riepilogo")
    expect(summary).to_contain_text(f"{TOTAL}")
    director.spotlight(summary.get_by_text(re.compile("Includes membership fee")), 2.5)
    director.say("Becoming a member is required to confirm the registration")
    director.spotlight(summary.get_by_text(re.compile("request to register as a member")), 2.5)
    director.confirm(page.locator("#register_go"), settle=1.0)
    director.say("Consent to share personal data with the organization")
    director.check(page.get_by_role("checkbox", name="Authorisation"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 4: upload the signed request")
    director.say("Download the request pre-filled with your data, then sign it")
    director.spotlight(page.get_by_role("link", name="download it here"), 2.5)
    director.say("Upload the signed request and a photo of an ID")
    director.upload(page.locator("#id_request"), request_path)
    director.upload(page.locator("#id_document"), card_path)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("Check the documents, then send the request")
    for index in range(1, 5):
        director.check(page.locator(f"#id_confirm_{index}"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.5)

    director.play_as(ORGANIZER, login_as(director, login_orga, "/manage/"))
    director.step("Step 5: approve the request")
    director.say("New requests are at the top of the members list")
    director.click(page.locator("#sidebar").get_by_role("link", name=re.compile(r"^Members")))
    member_row = page.locator("tr", has_text=PLAYER_SURNAME)
    expect(member_row).to_contain_text("Review")
    director.spotlight(member_row, 1.5)
    director.click(member_row.get_by_role("link", name="Request"), settle=1.0)
    director.say("Review the documents, then approve")
    director.spotlight(page.locator("img").first, 2.5)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    expect(member_row).to_contain_text("Accepted")
    director.spotlight(member_row, 1.5)

    director.play_as(PLAYER, login_as(director, login_user, "/test/"))
    director.step("Step 6: pay registration and fee")
    director.say("Now the new member can pay, fee included")
    director.click(page.get_by_role("link", name=re.compile(f"A payment of {TOTAL}")), settle=1.0)
    director.spotlight(page.get_by_text(re.compile(r"Membership fee \d+:")).first, 2.5)
    director.say("After the transfer, notify the organizer")
    director.check(page.get_by_role("checkbox", name="Payment confirmation:"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.play_as(ORGANIZER, login_as(director, login_orga, "/test/manage/"))
    director.step("Step 7: confirm the payment")
    director.say("Confirm the transfer once received")
    director.click(page.locator("#sidebar").get_by_role("link", name=re.compile(r"^Payments")))
    director.click(page.get_by_role("link", name="Confirm").first, settle=0.8)
    save_modal(director, get_modal_iframe(page))
    director.say("Membership status and payments are tracked in the registrations")
    open_menu(director, "Registrations")
    director.click(page.get_by_role("link", name="accounting", exact=True), settle=1.0)
    director.click(page.get_by_role("link", name="member", exact=True), settle=1.0)
    registration = page.locator("tr[id]", has_text=PLAYER_SURNAME)
    expect(registration).to_contain_text("Accepted")
    director.spotlight(registration, 3.5)

    director.stop()
