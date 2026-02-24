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

"""
Test: Character "your" link, accounting/payment links, direct ticket links, and refunds.
Verifies invisible tickets with direct links, character "your" shortcut, accounting/payment
URL shortcuts, independent campaign factions, and refund request workflow.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import just_wait, expect_normalized, go_to, login_orga, submit_confirm, sidebar

pytestmark = pytest.mark.e2e


def test_character_your_accounting_pay_ticket_link(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    check_direct_ticket_link(page, live_server)

    check_character_your_link(page, live_server)

    check_accounting_pay_link(page, live_server)

    check_factions_indep_campaign(page, live_server)

    accounting_refund(page, live_server)


def check_direct_ticket_link(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/")
    # Setup NPC ticket
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Tickets ")).click()
    page.locator("#id_ticket_npc").check()
    submit_confirm(page)

    # Create ticket
    page.get_by_role("link", name="Tickets").first.click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_tier").select_option("n")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Staff")
    page.locator("#id_visible").uncheck()
    submit_confirm(page)

    # Test 1: Direct ticket link bypasses "registration not yet open"
    ticket_link_bypasses_not_open(page, live_server)

    # Test 2: Direct ticket link bypasses external registration link
    ticket_link_bypasses_external_link(page, live_server)

    # Test 3: Direct link bypasses ticket not visible
    ticket_link_bypasses_not_visible(live_server, page)


def ticket_link_bypasses_not_visible(live_server, page):
    # Test signup (shouldn't be visible)
    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="Registration is open!").first.click()
    page.get_by_label("Ticket (*)").click()
    expect(page.get_by_label("Ticket (*)")).to_have_value("u1")
    expect(page.get_by_label("Ticket (*)")).to_match_aria_snapshot(
        '- combobox "Ticket (*)":\n  - option "Standard" [selected]'
    )

    # Test direct link
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Tickets").first.click()
    just_wait(page)
    with page.expect_popup() as popup_info:
        page.locator('[id="u2"]').get_by_role("link", name="Signup link").click()
    new_page = popup_info.value
    expect(new_page.get_by_label("Ticket (*)")).to_have_value("u2")
    new_page.get_by_role("button", name="Continue").click()
    submit_confirm(new_page)
    go_to(page, live_server, "/test/")
    expect_normalized(page, page.locator("#one"), "Registration confirmed (Staff)")


def ticket_link_bypasses_not_open(page: Any, live_server: Any) -> None:
    """Test that direct ticket link works when registration is not yet open."""

    page.get_by_role("link", name="Event").first.click()
    page.locator("#id_form2-registration_status").select_option("f")
    page.locator("#id_form2-registration_open").fill("2099-12-31")
    just_wait(page)
    page.locator("#id_form2-registration_open").click()
    just_wait(page)
    submit_confirm(page)

    # Verify normal registration is blocked
    go_to(page, live_server, "/test/register/")
    expect_normalized(page, page.locator("body"), "The registrations to the event Test Larp are not yet open!")

    # Get direct ticket link and verify it still works
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Tickets").first.click()

    # Navigate to direct ticket link - should work despite registration not open
    just_wait(page)
    with page.expect_popup() as popup_info:
        page.locator('[id="u2"]').get_by_role("link", name="Signup link").click()
    new_page = popup_info.value
    # Should show registration form, not "not open" message
    expect(new_page.get_by_label("Ticket (*)")).to_have_value("u2")
    expect(new_page.get_by_label("Ticket (*)")).to_be_visible()
    new_page.close()

    # Reset registration open date
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Event").first.click()
    page.locator("#id_form2-registration_status").select_option("o")
    submit_confirm(page)



def ticket_link_bypasses_external_link(page: Any, live_server: Any) -> None:
    """Test that NPC/Staff ticket links bypass external registration link redirect."""

    # Set an external registration link
    sidebar(page, "Event")
    page.locator("#id_form2-registration_status").select_option("e")
    page.locator("#id_form2-register_link").click()
    page.locator("#id_form2-register_link").fill("https://google.com")
    submit_confirm(page)

    # Verify normal registration redirects to external link
    go_to(page, live_server, "/test/register/")
    # Should be redirected to external site (we can't follow, so just check we're not on our site)
    expect(page).to_have_url(re.compile(r"google\.com"))

    # Go back and test direct ticket link
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Tickets").first.click()

    # Navigate to direct NPC ticket link - should bypass external redirect
    with page.expect_popup() as popup_info:
        page.locator('[id="u2"]').get_by_role("link", name="Signup link").click()
    new_page = popup_info.value
    # Should show registration form, not redirect to external site
    expect(new_page.get_by_label("Ticket (*)")).to_have_value("u2")
    expect(new_page.get_by_label("Ticket (*)")).to_be_visible()
    # Verify we're still on our domain
    expect(new_page).to_have_url(re.compile(r"(localhost|127\.0\.0\.1|testserver)"))
    new_page.close()

    # Clean up: disable external registration link
    page.get_by_role("link", name="Event").click()
    page.locator("#id_form2-registration_status").select_option("o")
    submit_confirm(page)


def check_character_your_link(page: Any, live_server: Any) -> None:
    # Test character your link
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="Characters").check()
    submit_confirm(page)
    page.get_by_role("link", name="Registrations").click()
    page.locator(".fa-edit").click()
    page.get_by_role("cell", name="Show available characters").click()
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("te")
    page.locator(".select2-results__option").first.click()
    submit_confirm(page)

    # Checkout member data
    page.locator(".fa-eye").click()
    just_wait(page)
    expect_normalized(page, page.locator("#uglipop_content_fixed"), "Admin Test Email: orga@test.it")


    # Go to your character, check result
    go_to(page, live_server, "/test/character/your")
    expect_normalized(page, page.locator("#banner"), "Test Character - Test Larp")
    expect_normalized(page, page.locator("#one"), "Player: Admin Test Presentation Test Teaser Text Test Text")


def check_accounting_pay_link(page: Any, live_server: Any) -> None:
    # Test acc pay link
    go_to(page, live_server, "/test/manage/")

    # Set ticket price
    page.get_by_role("link", name="Tickets").first.click()
    page.locator('[id="u2"]').locator(".fa-edit").click()
    page.locator("#id_price").click()
    page.locator("#id_price").press("Home")
    page.locator("#id_price").fill("100.00")
    submit_confirm(page)

    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="please fill in your profile.").click()
    page.get_by_role("checkbox", name="Authorisation").check()
    submit_confirm(page)
    page.get_by_role("link", name="Registration confirmed (Staff)").click()
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # set up payments
    go_to(page, live_server, "/manage")
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="Payments", exact=True).check()
    submit_confirm(page)
    page.get_by_role("checkbox", name="Wire").check()
    just_wait(page)
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("sadsadsa")
    page.locator("#id_wire_fee").click()
    page.locator("#id_wire_fee").fill("2")
    page.locator("#id_wire_payee").click()
    page.locator("#id_wire_payee").fill("dasdsadsasa")
    page.locator("#id_wire_iban").click()
    page.locator("#id_wire_iban").fill("dsasadas")
    page.locator("#id_wire_bic").fill("test iban")
    submit_confirm(page)

    # check payments
    go_to(page, live_server, "/test/")
    page.get_by_role("link", name="to confirm it proceed with").click()

    go_to(page, live_server, "/accounting/pay/test/")
    expect_normalized(page, page.locator("#one"), "Choose the payment method: Wire sadsadsa")

    go_to(page, live_server, "/accounting/pay/test/wire/")
    expect_normalized(page, page.locator("#one"), "You are about to make a payment of: 100 €. Follow the steps below:")

    go_to(page, live_server, "/accounting/pay/test/paypal/")
    expect_normalized(page, page.locator("#one"), "Choose the payment method: Wire sadsadsa")


def check_factions_indep_campaign(page: Any, live_server: Any) -> None:
    # Add first event factions
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="Factions").check()
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("primaaa")
    page.get_by_role("list").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="#1 Test Character").click()
    page.get_by_role("checkbox", name="After confirmation, add").check()
    submit_confirm(page)
    page.locator("#id_typ").select_option("t")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("tranver")
    page.get_by_role("list").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="#1 Test Character").click()
    submit_confirm(page)

    # check result
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect_normalized(page, page.locator("#one"), "primaaa Primary Test Character tranver Transversal Test Character")

    # add second event in campaing
    go_to(page, live_server, "/manage")
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="Campaign").check()
    submit_confirm(page)
    page.get_by_role("link", name="Events").click()
    page.get_by_role("link", name="New event").click()
    page.locator("#id_form1-name").click()
    page.locator("#id_form1-name").fill("second")
    page.locator("#select2-id_form1-parent-container").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="Test Larp").click()

    page.locator("#id_form2-start").fill("2045-06-11")
    just_wait(page)
    page.locator("#id_form2-start").click()
    page.locator("#id_form2-end").fill("2045-06-13")
    just_wait(page)
    page.locator("#id_form2-end").click()
    submit_confirm(page)

    # check we have for now the same factions
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("link", name="Factions").click()
    expect_normalized(page, page.locator("#one"), "primaaa Primary tranver Transversal")

    # set independ factions, check
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Campaign ")).click()
    page.locator("#id_campaign_faction_indep").check()
    submit_confirm(page)
    page.get_by_role("link", name="Factions").click()
    expect_normalized(page, page.locator("#one"), "No elements are currently available")

    # add new factions
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").press("CapsLock")
    page.locator("#id_name").fill("PRIMAAAA")
    page.get_by_role("list").click()
    page.get_by_role("searchbox").fill("TE")
    page.get_by_role("option", name="#1 Test Character").click()
    page.get_by_role("checkbox", name="After confirmation, add").check()
    submit_confirm(page)
    page.locator("#id_typ").select_option("t")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("TRANVERSA")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("TE")
    page.get_by_role("option", name="#1 Test Character").click()
    submit_confirm(page)

    # check situation in second event
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect_normalized(page, page.locator("#one"), "PRIMAAAA Primary Test Character TRANVERSA Transversal Test Character")
    sidebar(page, "Characters")
    page.get_by_role("link", name="Faction", exact=True).click()
    expect_normalized(page, page.locator("#one"), "#1 Test Character Test Teaser Test Text PRIMAAAA TRANVERSA")

    # check situation in first event
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Factions").click()
    page.locator("#one").get_by_role("link", name="Characters").click()
    expect_normalized(page, page.locator("#one"), "primaaa Primary Test Character tranver Transversal Test Character")
    sidebar(page, "Characters")
    page.get_by_role("link", name="Faction", exact=True).click()
    expect_normalized(page, page.locator("#one"), "#1 Test Character Test Teaser Test Text primaaa tranver")


def accounting_refund(page: Any, live_server: Any) -> None:
    # activate features
    go_to(page, live_server, "/manage")
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="Tokens").check()
    page.get_by_role("checkbox", name="Credits").check()
    page.get_by_role("checkbox", name="Refunds").check()
    submit_confirm(page)

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
    page.get_by_role("link", name=re.compile(" Accounting$")).click()
    page.get_by_role("link", name="refund request").click()
    page.get_by_role("textbox", name="Details").click()
    page.get_by_role("textbox", name="Details").fill("asdsadsadsa")
    page.get_by_role("spinbutton", name="Value").click()
    page.get_by_role("spinbutton", name="Value").fill("20")
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Requests open: asdsadsadsa (20.00)")

    go_to(page, live_server, "/manage")
    page.locator("#exe_refunds").get_by_role("link", name="Refunds").click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "asdsadsadsa admin test 20 200 request done")
    page.get_by_role("link", name="Done").click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "asdsadsadsa admin test 20 180 delivered")
