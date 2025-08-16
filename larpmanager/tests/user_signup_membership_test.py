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
from pathlib import Path

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import check_download, go_to, login_orga, submit

pytestmark = pytest.mark.e2e


def test_user_signup_membership(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    signup(live_server, page)

    membership(live_server, page)

    pay(live_server, page)


def signup(live_server, page):
    # Activate payments
    go_to(page, live_server, "/manage/features/111/on")
    # Activate membership
    go_to(page, live_server, "/manage/features/45/on")
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_cc").check()
    page.locator("#id_mail_signup_new").check()
    page.locator("#id_mail_signup_update").check()
    page.locator("#id_mail_signup_del").check()
    page.locator("#id_mail_payment").check()
    page.get_by_role("button", name="Confirm", exact=True).click()
    go_to(page, live_server, "/manage/payments/details")
    page.locator('#id_payment_methods input[type="checkbox"][value="1"]').check()
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("test wire")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_descr").press("Tab")
    page.locator("#id_wire_payee").fill("test beneficiary")
    page.locator("#id_wire_payee").press("Tab")
    page.locator("#id_wire_iban").fill("test iban")
    page.get_by_role("button", name="Confirm", exact=True).click()
    # set ticket price
    go_to(page, live_server, "/test/1/manage/registrations/tickets")
    page.locator("a:has(i.fas.fa-edit)").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("100.00")
    page.get_by_role("button", name="Confirm", exact=True).click()
    # signup
    go_to(page, live_server, "/test/1/register")
    page.get_by_role("button", name="Continue").click()
    expect(page.locator("#riepilogo")).to_contain_text("you must request to register as a member")
    page.get_by_role("button", name="Confirm", exact=True).click()


def membership(live_server, page):
    # send membership
    go_to(page, live_server, "/test/1/register")
    expect(page.locator("#one")).to_contain_text("Provisional registration")
    expect(page.locator("#one")).to_contain_text("please upload your membership application to proceed")
    page.get_by_role("link", name="please upload your membership").click()
    page.get_by_role("checkbox", name="Authorisation").check()
    page.get_by_role("button", name="Submit").click()
    # compile request
    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_request").set_input_files(str(image_path))
    page.locator("#id_document").set_input_files(str(image_path))
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
    page.get_by_role("button", name="Confirm").click()
    # check register
    go_to(page, live_server, "/test/1/register")
    expect(page.locator("#one")).to_contain_text("to confirm it proceed with payment")
    page.get_by_role("link", name="to confirm it proceed with").click()


def pay(live_server, page):
    # pay
    page.get_by_role("cell", name="Wire", exact=True).click()
    expect(page.locator("b")).to_contain_text("100")
    submit(page)
    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_invoice").set_input_files(str(image_path))
    submit(page)
    # approve payment
    go_to(page, live_server, "/test/1/manage/invoices")
    page.get_by_role("link", name="Confirm", exact=True).click()
    # check payment
    go_to(page, live_server, "/test/1/register")
    expect(page.locator("#one")).to_contain_text("Registration confirmed (Standard)")
    page.locator("a#menu-open").click()
    page.get_by_role("link", name="Logout").click()
    expect(page.locator("#one")).to_contain_text("Registration is open!")
    expect(page.locator("#one")).to_contain_text("Hurry: only 9 tickets available")
    # test mails
    go_to(page, live_server, "/debug/mail")
