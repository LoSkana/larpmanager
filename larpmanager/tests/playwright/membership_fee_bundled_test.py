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

"""Test: Membership fee bundled with event registration payment.

Verifies that when membership_fee_separated is disabled, the annual membership fee
is included in the registration total shown during signup for both events, bundled
into the first payment invoice, and then excluded from the second event's total once
the reservation is held by the first invoice. After payment confirmation the membership
accounting entry and reg_status display are verified for both events.
"""

from typing import Any

import re

import pytest

from larpmanager.tests.utils import (
    expect_normalized,
    get_modal_iframe,
    go_to,
    just_wait,
    load_image,
    login_orga,
    sidebar,
    submit,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def test_membership_fee_bundled(pw_page: Any) -> None:
    """Test that the membership fee is bundled with event registration payment."""
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    setup(live_server, page)
    request_and_approve_membership(live_server, page)
    register_and_pay_bundled(live_server, page)


def setup(live_server: Any, page: Any) -> None:
    """Activate membership with bundled fee mode, wire payments, set ticket prices, and create second event."""
    # Activate payment
    go_to(page, live_server, "/manage/features/payment/on")

    # Activate membership - redirects to membership config section
    go_to(page, live_server, "/manage")
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Membership").check()
    submit_confirm(page)

    # Set membership fee
    page.locator("#id_membership_fee").fill("20")
    submit_confirm(page)

    # Set up wire payment method
    go_to(page, live_server, "/manage/methods")
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").fill("test wire")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_payee").fill("test beneficiary")
    page.locator("#id_wire_iban").fill("test iban")
    page.locator("#id_wire_bic").fill("test bic")
    submit_confirm(page)

    # Set ticket price to 100 for first event
    go_to(page, live_server, "/test/manage/tickets")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_price").fill("100.00")
    submit_confirm(edit_iframe)

    # Create second event (slug auto-generated as "testsecond" from "Test Second")
    go_to(page, live_server, "/manage/events/")
    page.get_by_role("link", name="New event").click()
    page.locator("#id_form1-name").fill("Test Second")
    page.locator("#id_form1-name").press("Tab")
    page.locator("#id_form2-development").select_option("1")
    page.locator("#id_form2-registration_status").select_option("o")
    just_wait(page, big=True)
    page.locator("#id_form2-start").scroll_into_view_if_needed()
    page.locator("#id_form2-start").fill("2050-06-11")
    page.locator("#id_form2-start").click()
    just_wait(page, big=True)
    page.locator("#id_form2-end").scroll_into_view_if_needed()
    page.locator("#id_form2-end").fill("2050-06-13")
    page.locator("#id_form2-end").click()
    just_wait(page, big=True)
    submit_confirm(page)

    # Set ticket price to 70 for second event
    go_to(page, live_server, "/testsecond/manage/tickets")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_price").fill("70.00")
    submit_confirm(edit_iframe)


def request_and_approve_membership(live_server: Any, page: Any) -> None:
    """Verify bundled-fee riepilogo behaviour, submit a membership request, approve it."""

    # First event: riepilogo shows ticket 100 + membership 20 = 120, don't confirm
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    expect_normalized(page, page.locator("#riepilogo"), "Your updated registration total is: 120")
    expect_normalized(page, page.locator("#riepilogo"), "Includes membership fee 2050: 20")

    # Second event: riepilogo shows 90 (70 ticket + 20 membership, not yet reserved by any invoice)
    go_to(page, live_server, "/testsecond/register")
    page.get_by_role("button", name="Continue").click()
    expect_normalized(page, page.locator("#riepilogo"), "Your updated registration total is: 90")
    expect_normalized(page, page.locator("#riepilogo"), "Includes membership fee 2050: 20")

    # First event: register and confirm (creates provisional registration)
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    expect_normalized(page, page.locator("#riepilogo"), "you must request to register as a member")
    submit_confirm(page)

    # Follow link to membership application
    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "Provisional registration")
    page.get_by_role("link", name="Accounting", exact=True).click()
    expect_normalized(page, page.locator("#one"), "Total registration fee: 100")
    page.get_by_role("link", name="Upload your membership application to proceed").click()

    # Confirm profile
    page.get_by_role("checkbox", name="Authorisation").check()
    submit_confirm(page)

    # Upload membership documents
    load_image(page, "#id_request")
    load_image(page, "#id_document")
    submit(page)

    # Confirm membership request checkboxes
    page.locator("#id_confirm_1").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_2").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_3").check()
    page.locator("#id_confirm_4").check()
    submit(page)

    # Approve request as organiser
    go_to(page, live_server, "/manage/membership/")
    page.get_by_role("link", name="Request").click()
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Accepted")

    # Go to payment page: single method auto-selected, verify total 120 includes membership fee of 20
    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "Proceed with payment to confirm your registration")
    page.get_by_role("link", name=re.compile(r"Proceed with payment")).click()
    expect_normalized(page, page.locator("#one"), "The total registration fee is: 100")
    expect_normalized(page, page.locator("#one"), "membership fee 2050: 20")
    expect_normalized(page, page.locator("#one"), "you are about to make a payment of: 120 €")

    # Second event: riepilogo now shows 70 only (membership reserved by first event's invoice)
    go_to(page, live_server, "/testsecond/register")
    page.get_by_role("button", name="Continue").click()
    expect_normalized(page, page.locator("#riepilogo"), "Your updated registration total is: 70")

    # Pay first event
    go_to(page, live_server, "/test/register")
    page.get_by_role("link", name="Accounting", exact=True).click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "Total registration fee: 100")
    expect_normalized(page, page.locator("#one"), "Next payment: 120€ (Includes membership fee 2050: 20€)")
    page.get_by_role("link", name=re.compile(r"Proceed with payment")).click()
    page.get_by_role("checkbox", name="Payment confirmation:").check()
    submit(page)



def register_and_pay_bundled(live_server: Any, page: Any) -> None:
    """Verify reg_status, then register and pay second event."""

    # Approve first event payment
    go_to(page, live_server, "/test/manage/payments")
    page.get_by_role("link", name="Confirm").click()

    # First event registration is confirmed
    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "Registration confirmed")

    # reg_status accounting section shows event fee paid 100 and membership fee 20
    go_to(page, live_server, "/test/register")
    page.get_by_role("link", name="Accounting", exact=True).click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "Total registration fee: 100")
    expect_normalized(page, page.locator("#one"), "Total payments: 100")
    expect_normalized(page, page.locator("#one"), "Membership fee 2050: 20€ ")

    # Second event: register (riepilogo shows 70, no membership fee since already paid)
    go_to(page, live_server, "/testsecond/register")
    page.get_by_role("button", name="Continue").click()
    expect_normalized(page, page.locator("#riepilogo"), "70")
    just_wait(page)
    submit_confirm(page)

    # Second event: proceed to wire payment (total 70, no membership shown, single method auto-selected)
    go_to(page, live_server, "/testsecond/register")
    expect_normalized(page, page.locator("#one"), "Proceed with payment to confirm your registration")
    page.get_by_role("link", name=re.compile(r"Proceed with payment")).click()
    expect_normalized(page, page.locator("#one"), "70 EUR")
    page.get_by_role("checkbox", name="Payment confirmation:").check()
    submit(page)

    # Approve second event payment
    go_to(page, live_server, "/testsecond/manage/payments")
    page.get_by_role("link", name="Confirm").click()

    # reg_status for second event shows event fee 100 and membership fee 20 (already paid via first event)
    go_to(page, live_server, "/testsecond/register")
    page.get_by_role("link", name="Accounting", exact=True).click()
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "Total registration fee: 70")
    expect_normalized(page, page.locator("#one"), "Total payments: 70")
    expect_normalized(page, page.locator("#one"), "Membership fee 2050: 20€ ")
