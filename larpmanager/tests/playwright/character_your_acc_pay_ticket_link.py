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
import re

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, load_image, login_user, submit_confirm, login_orga

pytestmark = pytest.mark.e2e


def test_character_your_acc_pay_ticket_link(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    check_direct_ticket_link(page, live_server)

    check_character_your_link(page, live_server)

    check_acc_pay_link(page, live_server)

    check_factions_indep_campaign(page, live_server)

    acc_refund(page, live_server)

def check_direct_ticket_link(page, live_server):
    go_to(page, live_server, "/test/manage")
    # Setup NPC ticket
    page.get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name="Tickets ").click()
    page.locator("#id_ticket_npc").check()
    page.get_by_role("button", name="Confirm").click()

    # Create ticket
    page.locator("#orga_registration_tickets").get_by_role("link", name="Tickets").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_tier").select_option("n")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Staff")
    page.locator("#id_visible").uncheck()
    page.get_by_role("button", name="Confirm").click()

    # Test signup (shouldn't be visible)
    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="Registration is open!").click()
    page.get_by_label("Ticket (*)").click()
    expect(page.get_by_label("Ticket (*)")).to_have_value("1")
    expect(page.get_by_label("Ticket (*)")).to_match_aria_snapshot("- combobox \"Ticket (*)\":\n  - option \"Standard\" [selected]")

    # Test direct link
    go_to(page, live_server, "/test/manage")
    page.locator("#orga_registration_tickets").get_by_role("link", name="Tickets").click()
    page.locator("[id=\"\\32 \"]").get_by_role("link", name="Link").click()
    expect(page.get_by_label("Ticket (*)")).to_have_value("2")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator("#one")).to_contain_text("Registration confirmed (Staff)")

def check_character_your_link(page, live_server):
    # Test character your link
    go_to(page, live_server, "/test/manage")
    page.get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Characters").check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Registrations").click()
    page.get_by_role("link", name="").click()
    page.get_by_role("cell", name="Show available characters").click()
    page.get_by_text("Please enter 2 or more").click()
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("te")
    page.locator(".select2-results__option").first.click()
    page.get_by_role("button", name="Confirm").click()

    # Go to your character, check result
    go_to(page, live_server, "/test/character/your")
    expect(page.locator("#banner")).to_contain_text("Test Character - Test Larp")
    expect(page.locator("#one")).to_contain_text("Player: Admin Test Presentation Test Teaser Text Test Text")

def check_acc_pay_link(page, live_server):
    # Test acc pay link
    go_to(page, live_server, "/test/manage")

    # Set ticket price
    page.get_by_role("link", name="Tickets").click()
    page.locator("[id=\"\\32 \"]").get_by_role("link", name="").click()
    page.locator("#id_price").click()
    page.locator("#id_price").press("Home")
    page.locator("#id_price").fill("100.00")
    page.get_by_role("button", name="Confirm").click()

    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="please fill in your profile.").click()
    page.get_by_role("checkbox", name="Authorisation").check()
    page.get_by_role("button", name="Submit").click()
    page.get_by_role("link", name="Registration confirmed (Staff)").click()
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm").click()

    # set up payments
    go_to(page, live_server, "/manage")
    page.get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Payments", exact=True).check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("sadsadsa")
    page.locator("#id_wire_fee").click()
    page.locator("#id_wire_fee").fill("2")
    page.locator("#id_wire_payee").click()
    page.locator("#id_wire_payee").fill("dasdsadsasa")
    page.locator("#id_wire_iban").click()
    page.locator("#id_wire_iban").fill("dsasadas")
    page.get_by_role("button", name="Confirm").click()

    # check payments
    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="to confirm it proceed with").click()

    go_to(page, live_server, "/accounting/pay/test/")
    expect(page.locator("#one")).to_contain_text("Choose the payment method: Wire sadsadsa Submit")

    go_to(page, live_server, "/accounting/pay/test/wire/")
    expect(page.locator("#one")).to_contain_text("You are about to make a payment of: 100 €. Follow the steps below:")

    go_to(page, live_server, "/accounting/pay/test/paypal/")
    expect(page.locator("#one")).to_contain_text("Choose the payment method: Wire sadsadsa Submit")

def check_factions_indep_campaign(page, live_server):
    # Add first event factions
    go_to(page, live_server, "/test/manage")
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Factions").check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("primaaa")
    page.get_by_role("list").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="#1 Test Character").click()
    page.get_by_role("checkbox", name="After confirmation, add").check()
    page.get_by_role("button", name="Confirm").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("tranver")
    page.get_by_role("list").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="#1 Test Character").click()
    page.get_by_role("button", name="Confirm").click()

    # check result
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect(page.locator("#one")).to_contain_text("primaaa Primary Test Character tranver Transversal Test Character")

    # add second event in campaing
    go_to(page, live_server, "/manage")
    page.get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Campaign").check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Events").click()
    page.get_by_role("link", name="New event").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("second")
    page.locator("#select2-id_parent-container").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="Test Larp").click()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("button", name="Confirm").click()
    page.locator("#id_start").fill("2045-06-11")
    page.wait_for_timeout(2000)
    page.locator("#id_start").click()
    page.locator("#id_end").fill("2045-06-13")
    page.wait_for_timeout(2000)
    page.locator("#id_end").click()
    page.get_by_role("button", name="Confirm").click()

    # check we have for now the same factions
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.get_by_role("link", name="Factions").click()
    expect(page.locator("#one")).to_contain_text("primaaa Primary tranver Transversal")

    # set independ factions, check
    page.get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name="Campaign ").click()
    page.locator("#id_campaign_faction_indep").check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Factions").click()
    expect(page.locator("#one")).to_contain_text("No elements are currently available")

    # add new factions
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").press("CapsLock")
    page.locator("#id_name").fill("PRIMAAAA")
    page.get_by_role("list").click()
    page.get_by_role("searchbox").fill("TE")
    page.get_by_role("option", name="#1 Test Character").click()
    page.get_by_role("checkbox", name="After confirmation, add").check()
    page.get_by_role("button", name="Confirm").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("TRANVERSA")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("TE")
    page.get_by_role("option", name="#1 Test Character").click()
    page.get_by_role("button", name="Confirm").click()

    # check situation in second event
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect(page.locator("#one")).to_contain_text("PRIMAAAA Primary Test Character TRANVERSA Transversal Test Character")
    page.locator("#orga_characters").get_by_role("link", name="Characters").click()
    page.get_by_role("link", name="Faction", exact=True).click()
    expect(page.locator("#one")).to_contain_text("#1 Test Character Test Teaser Test Text PRIMAAAA TRANVERSA")

    # check situation in first event
    go_to(page, live_server, "/test/manage")
    page.get_by_role("link", name="Factions").click()
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect(page.locator("#one")).to_contain_text("primaaa Primary Test Character tranver Transversal Test Character")
    page.locator("#orga_characters").get_by_role("link", name="Characters").click()
    page.get_by_role("link", name="Faction", exact=True).click()
    expect(page.locator("#one")).to_contain_text("#1 Test Character Test Teaser Test Text primaaa tranver")

def acc_refund(page, live_server):
    # activate features
    go_to(page, live_server, "/manage")
    page.get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name=re.compile(r"^Tokens")).check()
    page.get_by_role("checkbox", name="Refunds").check()
    page.get_by_role("button", name="Confirm").click()

    # give out credits
    page.get_by_role("link", name="Credits", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("org")
    page.locator(".select2-results__option").first.click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("300")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("teer")
    submit_confirm(page)

    # open request
    page.get_by_role("link", name=" Accounting").click()
    page.get_by_role("link", name="refund request").click()
    page.get_by_role("textbox", name="Details").click()
    page.get_by_role("textbox", name="Details").fill("asdsadsadsa")
    page.get_by_role("spinbutton", name="Value").click()
    page.get_by_role("spinbutton", name="Value").fill("20")
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("Requests open: asdsadsadsa (20.00)")

    go_to(page, live_server, "/manage")
    page.get_by_role("link", name="Refunds").click()
    expect(page.locator("#one")).to_contain_text("asdsadsadsaAdmin Test2030RequestDone")
    page.get_by_role("link", name="Done").click()
    expect(page.locator("#one")).to_contain_text("asdsadsadsaAdmin Test2010Delivered")
