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
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, load_image, login_orga, submit, submit_confirm, expect_normalized

pytestmark = pytest.mark.e2e


def test_user_accounting(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    prepare(page, live_server)

    donation(page, live_server)

    membership_fees(page, live_server)

    collections(page, live_server)


def prepare(page: Any, live_server: Any) -> None:
    # Activate payments
    go_to(page, live_server, "/manage/features/payment/on")

    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_cc").check()
    page.locator("#id_mail_signup_new").check()
    page.locator("#id_mail_signup_update").check()
    page.locator("#id_mail_signup_del").check()
    page.locator("#id_mail_payment").check()

    page.get_by_role("link", name=re.compile(r"^Payments\s.+")).click()
    page.locator("#id_payment_special_code").check()
    page.locator("#id_payment_require_receipt").check()

    submit_confirm(page)

    go_to(page, live_server, "/manage/methods")
    page.locator('#id_payment_methods input[type="checkbox"][value="1"]').check()
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("test wire")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_descr").press("Tab")
    page.locator("#id_wire_payee").fill("test beneficiary")
    page.locator("#id_wire_payee").press("Tab")
    page.locator("#id_wire_iban").fill("test iban")
    submit_confirm(page)


def donation(page: Any, live_server: Any) -> None:
    # test donation
    go_to(page, live_server, "/manage/features/donate/on")

    go_to(page, live_server, "/accounting")
    page.get_by_role("link", name="follow this link").click()
    page.locator("#id_amount").click()
    page.locator("#id_amount").fill("10")
    page.locator("#id_amount").press("Tab")
    page.locator("#id_descr").fill("test donation")
    page.get_by_role("cell", name="test wire").click()
    submit(page)

    load_image(page, "#id_invoice")
    page.get_by_role("checkbox", name="Payment confirmation:").check()

    expect_normalized(page.locator("#one"), "test beneficiary")
    expect_normalized(page.locator("#one"), "test iban")
    submit(page)

    go_to(page, live_server, "/manage/invoices")
    # Check for donation invoice in the table
    expect(page.get_by_role("row", name="Admin Test Wire donation")).to_be_visible()
    page.get_by_role("link", name="Confirm").click()

    go_to(page, live_server, "/accounting")
    expect_normalized(page.locator("#one"), "Donations done")
    expect_normalized(page.locator("#one"), "(10.00€)")


def membership_fees(page: Any, live_server: Any) -> None:
    # test membership fees
    go_to(page, live_server, "/manage/features/membership/on")

    go_to(page, live_server, "/membership")
    page.get_by_role("checkbox", name="Authorisation").check()
    submit(page)

    load_image(page, "#id_request")
    load_image(page, "#id_document")
    submit(page)

    page.locator("#id_confirm_1").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_2").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_3").check()
    page.locator("#id_confirm_4").check()
    submit(page)

    go_to(page, live_server, "/manage/membership/")
    page.get_by_role("link", name="Request").click()
    submit_confirm(page)

    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"Members\s.+")).click()
    page.locator("#id_membership_fee").click()
    page.locator("#id_membership_fee").fill("15")
    page.locator("#id_membership_grazing").click()
    page.locator("#id_membership_grazing").fill("12")
    page.locator("#id_membership_day").click()
    page.locator("#id_membership_day").fill("01-01")
    submit_confirm(page)

    go_to(page, live_server, "/accounting")
    expect_normalized(page.locator("#one"), "Payment membership fee")
    page.get_by_role("link", name="Pay the annual fee").click()
    page.get_by_role("cell", name="test wire").click()
    submit(page)

    expect_normalized(page.locator("#one"), "15")
    load_image(page, "#id_invoice")
    page.get_by_role("checkbox", name="Payment confirmation:").check()

    expect_normalized(page.locator("#one"), "test beneficiary")
    expect_normalized(page.locator("#one"), "test iban")
    submit(page)

    go_to(page, live_server, "/manage/invoices")
    # Check for membership fee invoice in the table
    expect(page.get_by_role("row", name="Admin Test Wire membership")).to_be_visible()
    page.get_by_role("link", name="Confirm").click()

    go_to(page, live_server, "/accounting")
    expect(page.locator("#one")).not_to_contain_text("Payment membership fee")


def collections(page: Any, live_server: Any) -> None:
    # test collections
    go_to(page, live_server, "/manage/features/collection/on")

    go_to(page, live_server, "/accounting")
    page.get_by_role("link", name="Create a new collection").click()
    page.get_by_role("textbox", name="Name").click()
    page.get_by_role("textbox", name="Name").fill("User")
    submit(page)

    page.get_by_role("link", name="Link to participate in").click()
    page.locator("#id_amount").click()
    page.locator("#id_amount").fill("20")
    submit(page)

    expect_normalized(page.locator("#one"), "20")
    load_image(page, "#id_invoice")
    page.get_by_role("checkbox", name="Payment confirmation:").check()

    expect_normalized(page.locator("#one"), "test beneficiary")
    expect_normalized(page.locator("#one"), "test iban")
    submit(page)

    go_to(page, live_server, "/manage/invoices")
    expect_normalized(page.locator("#one"), "Collected contribution of Admin Test for User")
    page.get_by_role("link", name="Confirm").click()

    go_to(page, live_server, "/accounting")
    page.get_by_role("link", name="Manage it here!").click()
    page.get_by_role("link", name="Link to close the collection").click()
    page.get_by_role("link", name="Collection links").click()
    submit_confirm(page)

    go_to(page, live_server, "/accounting")
