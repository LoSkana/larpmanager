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
is included in the registration total shown during signup, bundled into the payment
invoice, and recorded as a separate membership accounting item after confirmation.
"""

from typing import Any

import pytest

from larpmanager.tests.utils import (
    expect_normalized,
    go_to,
    load_image,
    login_orga,
    sidebar,
    submit,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def test_membership_fee_bundled(pw_page: Any) -> None:
    """Test that the annual membership fee is bundled with event registration payment."""
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    setup(live_server, page)
    request_and_approve_membership(live_server, page)
    register_and_pay_bundled(live_server, page)


def setup(live_server: Any, page: Any) -> None:
    """Activate membership with bundled fee mode, wire payments, and set ticket price."""
    # Activate payment
    go_to(page, live_server, "/manage/features/payment/on")

    # Activate membership - redirects to membership config section
    go_to(page, live_server, "/manage")
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Membership").check()
    submit_confirm(page)

    # Set membership fee and disable separated mode (bundle with registration)
    page.locator("#id_membership_fee").fill("20")
    page.locator("#id_membership_fee_separated").uncheck()
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

    # Set ticket price to 100
    go_to(page, live_server, "/test/manage/tickets")
    page.locator(".fa-edit").click()
    page.locator("#id_price").fill("100.00")
    submit_confirm(page)


def request_and_approve_membership(live_server: Any, page: Any) -> None:
    """Submit a membership request and approve it as organiser."""
    # Sign up to trigger provisional registration (membership required)
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    expect_normalized(page, page.locator("#riepilogo"), "you must request to register as a member")
    submit_confirm(page)

    # Follow link to membership application
    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "Provisional registration")
    page.get_by_role("link", name="please upload your membership").click()

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


def register_and_pay_bundled(live_server: Any, page: Any) -> None:
    """Pay for the event with the membership fee bundled into the invoice."""
    # Registration now shows proceed with payment
    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "to confirm it proceed with payment")
    page.get_by_role("link", name="to confirm it proceed with").click()

    # Select wire payment - total is ticket (100) + membership fee (20) = 120
    page.get_by_role("cell", name="Wire", exact=True).click()
    expect_normalized(page, page.locator("b"), "120")

    # Membership fee is shown separately on the payment page
    expect_normalized(page, page.locator("#one"), "Annual membership fee")
    expect_normalized(page, page.locator("#one"), "20")

    submit(page)
    load_image(page, "#id_invoice")
    page.get_by_role("checkbox", name="Payment confirmation:").check()
    submit(page)

    # Approve payment
    go_to(page, live_server, "/test/manage/invoices")
    page.get_by_role("link", name="Confirm", exact=True).click()

    # Registration is confirmed
    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "Registration confirmed")

    # Membership fee was recorded: page shows fee received for this year
    go_to(page, live_server, "/membership")
    expect_normalized(page, page.locator("#one"), "You are a regular member")
    expect_normalized(page, page.locator("#one"), "membership fee for this year has been received")
