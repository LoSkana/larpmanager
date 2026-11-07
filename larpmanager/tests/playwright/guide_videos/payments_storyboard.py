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

"""Guide video: set payment methods and prices, pay a registration, read the accounting."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from larpmanager.models.association import Association
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

TITLE = "Payments"
PACE = 0.65

EVENT = "Vaelmoor: The Sundering"
WIRE_DESCRIPTION = "Bank transfer to the organization"
WIRE_PAYEE = "Vaelmoor Chronicle"
WIRE_IBAN = "XX00 DEMO 0000 0000 0000"
WIRE_BIC = "DEMOXXXX"
FREEFORM_DESCRIPTION = "Pay in person at the next meeting"
TICKET_PRICE = "100"
QUESTION = "Accommodation"
FREE_OPTION = "Tent"
PAID_OPTION = "Private room"
OPTION_PRICE = "40"
TOTAL = "140"


def test_payments_video(director: Director) -> None:
    """Record the payment setup, a paid registration and the resulting accounting."""
    page = director.page
    start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=30)
    prepare_data("Vaelmoor Chronicle")
    Path(get_payment_details_path(Association.objects.get())).unlink(missing_ok=True)
    login_orga(page, director.base_url)
    director.goto("/manage")
    director.start()

    director.play_as(ORGANIZER)
    director.step("Step 1: enable payments")
    director.say("Activate the feature for the organization")
    open_menu(director, "Features")
    director.check(feature_checkbox(page, "Payments"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 2: configure payment methods")
    director.say("Choose the gateways available to players")
    open_menu(director, "Methods")
    director.check(page.get_by_role("checkbox", name="Wire"))
    director.type(page.locator("#id_wire_descr"), WIRE_DESCRIPTION)
    director.fill(page.locator("#id_wire_fee"), "0")
    director.type(page.locator("#id_wire_payee"), WIRE_PAYEE)
    director.type(page.locator("#id_wire_iban"), WIRE_IBAN)
    director.type(page.locator("#id_wire_bic"), WIRE_BIC)
    director.check(page.get_by_role("checkbox", name="Freeform"))
    director.type(page.locator("#id_any_descr"), FREEFORM_DESCRIPTION)
    director.fill(page.locator("#id_any_fee"), "0")
    director.hold(1.0)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 3: create the event and set ticket prices")
    director.say("Create the event, then price its tickets")
    open_menu(director, "Events")
    slug = create_event(director, EVENT, start)
    open_menu(director, "Tickets")
    director.click(page.locator(".fa-edit").first, settle=0.8)
    modal = get_modal_iframe(page)
    director.fill(modal.locator("#id_price"), TICKET_PRICE)
    director.hold(1.0)
    save_modal(director, modal)

    director.step("Step 4: add paid registration options")
    director.say("Any option of the form can have its own price")
    open_menu(director, "Form")
    modal = open_new(director)
    director.select(modal.locator("#id_typ"), "s")
    director.type(modal.locator("#id_name"), QUESTION)
    option = new_option(modal)
    director.type(option.locator("#id_name"), FREE_OPTION)
    submit_option(modal, option)
    option = new_option(modal)
    director.type(option.locator("#id_name"), PAID_OPTION)
    director.fill(option.locator("#id_price"), OPTION_PRICE)
    submit_option(modal, option)
    director.hold(1.5)
    save_modal(director, modal)

    director.play_as(PLAYER, login_as(director, login_user, f"/{slug}/register/"))
    director.step("Step 5: player registration")
    director.say("The total updates with tickets and options")
    director.click(page.locator("label", has_text=PAID_OPTION))
    director.hold(2.0)
    director.confirm(page.get_by_role("button", name="Continue"), settle=1.0)
    expect(page.locator("#riepilogo")).to_contain_text(TOTAL)
    director.hold(2.0)
    director.confirm(page.locator("#register_go"), settle=1.0)

    director.step("Step 6: process payment")
    director.say("Players choose one of the configured gateways")
    director.click(page.get_by_role("link", name=re.compile(f"A payment of {TOTAL}")), settle=1.0)
    director.hold(1.5)
    director.click(page.get_by_role("columnheader", name="Wire", exact=True))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    expect(page.locator("#one")).to_contain_text(WIRE_IBAN)
    director.hold(3.0)
    director.say("After the transfer, they notify the organizer")
    director.check(page.get_by_role("checkbox", name="Payment confirmation:"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.hold(2.0)

    director.play_as(ORGANIZER, login_as(director, login_orga, f"/{slug}/manage/"))
    director.say("Confirm the transfer once received")
    director.click(page.locator("#sidebar").get_by_role("link", name=re.compile(r"^Payments")))
    director.click(page.get_by_role("link", name="Confirm").first, settle=0.8)
    save_modal(director, get_modal_iframe(page))
    confirmed = page.locator("tr", has_text="Alice Stone").filter(has_text="Confirmed")
    director.spotlight(confirmed, 2.5)

    director.step("Step 7: accurate, real-time accounting")
    director.say("Revenue and balances are always up to date")
    open_menu(director, "Accounting")
    revenue = page.locator("h2", has_text="Realized revenue")
    expect(revenue).to_contain_text(TOTAL)
    director.spotlight(revenue, 3.5)

    director.stop()
