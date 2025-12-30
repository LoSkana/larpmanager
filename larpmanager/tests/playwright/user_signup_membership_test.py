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

from larpmanager.tests.utils import (
    check_download,
    go_to,
    load_image,
    login_orga,
    submit,
    submit_confirm,
    expect_normalized,
)

pytestmark = pytest.mark.e2e


def test_user_signup_membership(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    signup(live_server, page)

    membership(live_server, page)

    pay(live_server, page)


def signup(live_server: Any, page: Any) -> None:
    # Activate payments
    go_to(page, live_server, "/manage/features/payment/on")
    # Activate membership
    go_to(page, live_server, "/manage/features/membership/on")
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_cc").check()
    page.locator("#id_mail_signup_new").check()
    page.locator("#id_mail_signup_update").check()
    page.locator("#id_mail_signup_del").check()
    page.locator("#id_mail_payment").check()

    page.get_by_role("link", name="Payments ").click()
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
    # set ticket price
    go_to(page, live_server, "/test/manage/tickets")
    page.locator("a:has(i.fas.fa-edit)").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("100.00")
    submit_confirm(page)
    # signup
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    expect_normalized(page, page.locator("#riepilogo"), "you must request to register as a member")
    submit_confirm(page)


def membership(live_server: Any, page: Any) -> None:
    # send membership
    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "Provisional registration")
    expect_normalized(page, page.locator("#one"), "please upload your membership application to proceed")
    page.get_by_role("link", name="please upload your membership").click()
    page.get_by_role("checkbox", name="Authorisation").check()
    page.get_by_role("button", name="Submit").click()
    # compile request
    load_image(page, "#id_request")
    load_image(page, "#id_document")
    check_download(page, "download it here")
    submit(page)
    # confirm request
    page.locator("#id_confirm_1").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_2").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_3").check()
    page.locator("#id_confirm_4").check()
    submit(page)
    # approve request signup
    go_to(page, live_server, "/manage/membership/")
    page.get_by_role("link", name="Request").click()
    submit_confirm(page)
    # check register
    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "to confirm it proceed with payment")
    page.get_by_role("link", name="to confirm it proceed with").click()


def pay(live_server: Any, page: Any) -> None:
    # pay
    page.get_by_role("cell", name="Wire", exact=True).click()
    expect_normalized(page, page.locator("b"), "100")
    submit(page)
    load_image(page, "#id_invoice")
    page.get_by_role("checkbox", name="Payment confirmation:").check()

    submit(page)
    # approve payment
    go_to(page, live_server, "/test/manage/invoices")
    page.get_by_role("link", name="Confirm", exact=True).click()
    # check payment
    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "Registration confirmed (Standard)")
    page.locator("a#menu-open").click()
    page.get_by_role("link", name="Logout").click()
    expect_normalized(page, page.locator("#one"), "Registration is open!")
    expect_normalized(page, page.locator("#one"), "Hurry: only 9 tickets available")
    # test mails
    go_to(page, live_server, "/debug/mail")
