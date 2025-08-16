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

from larpmanager.tests.utils import go_to, login_orga, submit

pytestmark = pytest.mark.e2e


def test_signup_accounting(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    setup_payment(live_server, page)

    signup_pay(live_server, page)

    token_credits(live_server, page)

    pay(live_server, page)

    discount(live_server, page)

    check_delete(live_server, page)


def check_delete(live_server, page):
    # update signup - orga
    go_to(page, live_server, "/test/1/manage/registrations")
    page.locator("a:has(i.fas.fa-edit)").click()
    page.get_by_role("button", name="Confirm", exact=True).click()

    # cancel signup
    page.locator("a:has(i.fas.fa-edit)").click()
    page.get_by_role("link", name="Delete").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Confirmation delete").click()
    go_to(page, live_server, "/test/1/manage/cancellations")
    expect(page.locator('[id="\\31 "]')).to_contain_text("orga@test.it")

    # delete payments
    go_to(page, live_server, "/test/1/manage/tokens")
    page.locator("a:has(i.fas.fa-edit)").click()
    page.get_by_role("link", name="Delete").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Confirmation delete").click()
    go_to(page, live_server, "/test/1/manage/credits")
    page.locator("a:has(i.fas.fa-edit)").click()
    page.get_by_role("link", name="Delete").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Confirmation delete").click()
    go_to(page, live_server, "/test/1/manage/payments")
    page.locator('[id="\\35 "]').get_by_role("link", name="").click()
    page.get_by_role("link", name="Delete").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Confirmation delete").click()


def discount(live_server, page):
    # check signup
    go_to(page, live_server, "/test/1/manage/registrations")
    page.get_by_role("link", name="accounting", exact=True).click()
    expect(page.locator('[id="\\31 "]')).to_contain_text("100")
    expect(page.locator('[id="\\31 "]')).to_contain_text("52")
    go_to(page, live_server, "/test/1/register")
    page.locator("#one").get_by_role("link", name="Accounting").click()
    expect(page.locator("#one")).to_contain_text("Total payments: 100")

    # update signup
    go_to(page, live_server, "/test/1/register")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()

    # use discount
    go_to(page, live_server, "/test/1/manage/features/12/on")
    go_to(page, live_server, "/test/1/manage/discounts/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("discount")
    page.get_by_role("checkbox", name="Test Larp").check()
    page.locator("#id_value").click()
    page.locator("#id_value").press("Home")
    page.locator("#id_value").fill("20")
    page.locator("#id_value").press("Tab")
    page.locator("#id_max_redeem").fill("0")
    page.locator("#id_cod").click()
    page.locator("#id_cod").fill("code")
    page.locator("#id_typ").select_option("a")
    page.locator("#id_visible").check()
    page.locator("#id_only_reg").uncheck()
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/test/1/register/")
    page.get_by_role("link", name="Discounts ").click()
    page.locator("#id_discount").click()
    page.locator("#id_discount").fill("code")
    page.locator("#discount_go").click()
    expect(page.locator("#discount_res")).to_contain_text(
        "The discount has been added! It has been reserved for you for 15 minutes, after which it will be removed"
    )
    expect(page.locator("#discount_tbl")).to_contain_text("20.00€")
    page.get_by_role("button", name="Continue").click()
    expect(page.locator("#riepilogo")).to_contain_text("Your updated registration total is: 80€.")
    page.locator("#register_go").click()


def pay(live_server, page):
    # check accounting
    go_to(page, live_server, "/test/1/register")
    page.locator("#one").get_by_role("link", name="Accounting").click()
    expect(page.locator("#one")).to_contain_text("Total registration fee: 100")
    expect(page.locator("#one")).to_contain_text("Total payments: 48")
    expect(page.locator("#one")).to_contain_text("Next payment: 52")
    go_to(page, live_server, "/test/1/manage/registrations")
    page.get_by_role("link", name="accounting", exact=True).click()
    expect(page.locator('[id="\\31 "]')).to_contain_text("52")
    expect(page.locator('[id="\\31 "]')).to_contain_text("48")
    expect(page.locator('[id="\\31 "]')).to_contain_text("100")
    expect(page.locator('[id="\\31 "]')).to_contain_text("100")
    expect(page.locator('[id="\\31 "]')).to_contain_text("24")

    # pay
    go_to(page, live_server, "/accounting/registration/1/")
    expect(page.locator("#one")).to_contain_text("100")
    expect(page.locator("#one")).to_contain_text("48")
    expect(page.locator("#one")).to_contain_text("52")
    submit(page)
    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_invoice").set_input_files(str(image_path))
    expect(page.locator("#one")).to_contain_text("52")
    submit(page)

    # confirm payment
    go_to(page, live_server, "/test/1/manage/invoices")
    expect(page.locator('[id="\\31 "]')).to_contain_text("52")
    page.get_by_role("link", name="Confirm", exact=True).click()


def token_credits(live_server, page):
    # activate tokens credits
    go_to(page, live_server, "/manage/features/107/on")
    go_to(page, live_server, "/manage/tokens")
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("ad")
    page.get_by_role("option", name="Admin Test - orga@test.it").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("7")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("test")
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/manage/credits")
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("org")
    page.get_by_role("option", name="Admin Test - orga@test.it").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("5")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("test")
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/test/1/manage/tokens")
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("org")
    page.get_by_role("option", name="Admin Test - orga@test.it").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("17")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("teeest")
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/test/1/manage/credits")
    page.get_by_role("link", name="New").click()
    page.get_by_text("---------").click()
    page.get_by_role("searchbox").fill("org")
    page.get_by_role("option", name="Admin Test - orga@test.it").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("19")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("testet")
    page.get_by_role("button", name="Confirm", exact=True).click()


def signup_pay(live_server, page):
    # Signup
    go_to(page, live_server, "/test/1/register")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    go_to(page, live_server, "/test/1/register")
    expect(page.locator("#one")).to_contain_text("Provisional registration")
    page.locator("#one").get_by_role("link", name="Accounting").click()
    expect(page.locator("#one")).to_contain_text("100")

    # Check accounting
    go_to(page, live_server, "/accounting")
    expect(page.locator("#one")).to_contain_text("100")

    # check pay
    go_to(page, live_server, "/test/1/register")
    page.get_by_role("link", name=re.compile(r"proceed with payment")).click()
    page.get_by_role("cell", name="Wire", exact=True).click()
    expect(page.locator("b")).to_contain_text("100")
    submit(page)
    expect(page.locator("#one")).to_contain_text("100")
    expect(page.locator("#one")).to_contain_text("test beneficiary")
    expect(page.locator("#one")).to_contain_text("test iban")


def setup_payment(live_server, page):
    # Activate payments
    go_to(page, live_server, "/manage/features/111/on")
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
